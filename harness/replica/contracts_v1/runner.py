"""Single-source live contract gate around the unchanged v8 native worker."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import sys

from .. import monitor, resource_guard, transport, operation_lease
from .. import runner_playwright as shared
from .observation import load_checkpoint
from .validator import validate, commit_prediction
from .oracle_process import BoundedOracle

SCHEMA = "component-contract-run/v1"
RUNTIME = Path(__file__).resolve().parents[1] / "runtime_versions/evaluation-playwright-semantics-v8"
_IMPORTED_FILES = {str(Path(module.__file__).resolve()): shared._file_sha(module.__file__)
                   for module in list(sys.modules.values()) if module and getattr(module, "__file__", None)
                   and str(getattr(module, "__name__", "")).startswith("harness.replica")
                   and str(module.__file__).endswith(".py")}


def _verify_loaded_files():
    for path, expected in _IMPORTED_FILES.items():
        if shared._file_sha(path) != expected:
            raise ValueError("loaded generic code changed after import; start a fresh controller process: " + path)


def _incomplete(value):
    if value is False or value is None:
        return True
    if isinstance(value, dict):
        return any(_incomplete(v) for v in value.values())
    if isinstance(value, list):
        return any(_incomplete(v) for v in value)
    return value in {"unconfirmed", "unknown", "unsupported", "fail", "missing"} if isinstance(value, str) else False


def _bad_checks(value):
    """Checks need explicit pass markers; empty/numeric truthiness is not evidence."""
    if value is True or isinstance(value, str) and value in {"pass", "confirmed"}:
        return False
    if isinstance(value, dict):
        markers = [v for k, v in value.items() if k in {"pass", "passed", "complete", "status", "verdict"}]
        if markers:
            metadata = {"id", "name", "label", "reason", "message", "detail", "expected", "actual", "evidence_refs"}
            rest = {k: v for k, v in value.items() if k not in metadata | {"pass", "passed", "complete", "status", "verdict"}}
            return (any(v is not True and not (isinstance(v, str) and v in {"pass", "confirmed"}) for v in markers)
                    or any(_bad_checks(v) for v in rest.values()))
        return not value or any(_bad_checks(v) for v in value.values())
    if isinstance(value, list):
        return not value or any(_bad_checks(v) for v in value)
    return True


def business_checkpoint(oracle, case_ref, record, observation, previous, preparation):
    result = {"verdict": "unconfirmed", "reason": "independent_oracle_missing"}
    if oracle is None:
        return result, previous
    checkpoint = {"kind": record.get("checkpoint"), "action": record.get("action", 0),
                  "case_ref": case_ref, "lane": "source", "record": record, "observation": observation,
                  "observations": {"source": record.get("observation")},
                  "evidence_directories": {"source": record.get("evidence_directory")},
                  "private_trees_directories": {"source": record.get("private_trees_directory")}}
    try:
        current = oracle.capture("source", case_ref, checkpoint)
        action = {key: record.get(key) for key in shared.ACTION_SCHEMA["required"]}
        assessment = oracle.assess(case_ref, checkpoint, previous if previous is not None else current, current, action)
        complete = (current.get("status") in {"pass", "confirmed"}
                    and ("facts" in current or "canonical_facts" in current)
                    and "logical_object_identities" in current and bool(current.get("coverage"))
                    and not _bad_checks(current["coverage"]) and bool(current.get("evidence_refs"))
                    and bool(assessment.get("evidence_refs")) and bool(assessment.get("checks"))
                    and not _bad_checks(assessment["checks"])
                    and preparation.get("initial_equivalence") in (True, "pass")
                    and bool(preparation.get("reset_receipt")))
        verdict = assessment.get("verdict", "unconfirmed")
        if verdict == "pass" and not complete:
            verdict = "unconfirmed"
        result = {"verdict": verdict, "required_evidence_present": complete,
                  "capture": current, "assessment": assessment}
        return result, current
    except Exception as error:
        return {"verdict": "unconfirmed", "reason": "oracle_error",
                "error": {"type": type(error).__name__, "message": str(error)}}, previous


def prior_prediction(record, configured=None):
    """Read the fsynced action_before JSON; never adopt action_after as a prior."""
    if record.get("checkpoint") != "after_action":
        return deepcopy(configured), None
    path = Path(record["evidence_directory"]) / "actions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    before = [row for row in rows if row.get("kind") == "action_before" and row.get("action") == record.get("action")]
    after = [row for row in rows if row.get("kind") == "action_after" and row.get("action") == record.get("action")]
    if len(before) != 1 or len(after) != 1 or rows.index(before[0]) >= rows.index(after[0]):
        return None, "missing_or_ambiguous_prior_prediction"
    if (commit_prediction(before[0].get("prediction")) != commit_prediction(record.get("prediction"))
            or commit_prediction(after[0].get("prediction")) != commit_prediction(record.get("prediction"))):
        return before[0].get("prediction"), "prediction_rewritten"
    return before[0].get("prediction"), None


def check_checkpoint(record, bundle, configured_prediction, *, oracle, case_ref, previous, preparation, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    observation = load_checkpoint(record)
    prediction, prior_error = prior_prediction(record, configured_prediction)
    commitment = commit_prediction(prediction) if isinstance(prediction, dict) else None
    # This immutable file commits the already-persisted action_before payload.
    shared._write(destination / "prior-prediction.json", {"prediction": prediction, "sha256": commitment,
                  "source": "worker action_before (fsynced before dispatch)" if record.get("checkpoint") == "after_action" else "preregistration",
                  "error": prior_error})
    contract = bundle.get("contracts", {}).get((prediction or {}).get("contract_ref"))
    if prior_error or not isinstance(prediction, dict) or not isinstance(contract, dict):
        validation = {"verdict": "fail" if prior_error == "prediction_rewritten" else "unknown",
                      "reason": prior_error or "missing_prediction_or_contract", "checks": [], "bindings": {},
                      "coverage": [], "prediction_score": None, "observation_binding_score": None}
    else:
        validation = validate(contract, prediction, observation, commitment=commitment)
    business, current = business_checkpoint(oracle, case_ref, record, observation, previous, preparation)
    acquisition = observation.get("complete") is True
    action_error_free = not record.get("error") and not record.get("observation", {}).get("error")
    final_ok = record.get("checkpoint") != "final" or record.get("status") == "completed"
    readpoint = bool(record.get("reading_request") or record.get("status") == "needs_reading")
    action_identity = record.get("checkpoint") != "after_action" or all(record.get(k) is not None for k in shared.ACTION_SCHEMA["required"])
    layers = {"acquisition": acquisition, "prediction_immutable": not prior_error and prediction is not None,
              "contract": validation.get("verdict") == "pass", "independent_truth": business["verdict"] == "pass",
              "action_identity_present": action_identity, "action_error_free": action_error_free,
              "no_readpoint": not readpoint, "final_completed": final_ok}
    primary = all(layers.values())
    result = {"schema": SCHEMA, "checkpoint": record.get("checkpoint"), "action": record.get("action"),
              "method": record.get("method"), "primary_pass": primary, "layers": layers,
              "first_failure_layer": next((k for k, v in layers.items() if not v), None),
              "contract_validation": validation, "business": business,
              "prior_prediction_sha256": commitment, "contract_ref": (prediction or {}).get("contract_ref"),
              "release_decision": "continue" if primary else "stop"}
    shared._write(destination / "observation.json", observation)
    shared._write(destination / "observation-update.json", {"schema": "component-observation-update/v1",
                  "prior_prediction_sha256": commitment, "bindings": validation.get("bindings", {}),
                  "evidence_refs": observation.get("evidence_refs", []), "rewrites_prior_prediction": False,
                  "prediction_score": validation.get("prediction_score"),
                  "observation_binding_score": validation.get("observation_binding_score")})
    shared._write(destination / "result.json", result)
    return result, current


def _run_source(source_plan, script_path, out, contracts_path, *, modules=(), policy=None, oracle=None,
                case_ref=None, state0_prediction=None, final_prediction=None, runtime_source=None,
                started=None, adapter_file=None):
    """Run one native script; release every barrier only after independent checks."""
    policy = {"wall_seconds": 600, "progress_seconds": 90, "barrier_wait_seconds": 55,
              "action_limit": 120, "resource_limits": None, "min_memory_bytes": 512 * 1024**2,
              "min_disk_bytes": 256 * 1024**2, **(policy or {})}
    if state0_prediction is None or final_prediction is None:
        raise ValueError("state0_prediction and final_prediction must be preregistered")
    runtime_source = transport.resolve_runtime_source(runtime_source or RUNTIME)
    settle = transport._module("settle", runtime_source=runtime_source)
    semantics = transport._module("playwright_semantics", runtime_source=runtime_source)
    gateway = transport._module("unix_gateway", runtime_source=runtime_source)
    sandbox = transport._module("worker_sandbox", runtime_source=runtime_source)
    guard = transport._module("process_guard", runtime_source=runtime_source)
    policy["stability"] = settle.normalize_policy(policy.get("stability", True))
    if not policy["stability"]["enabled"] or policy["stability"]["version"] != shared.STABILITY_VERSION:
        raise ValueError("bounded v8 stability is required")
    source = Path(script_path).read_text()
    module_sources = {}
    for item in modules:
        path = Path(item)
        if path.suffix != ".py" or not path.stem.isidentifier() or path.stem in module_sources:
            raise ValueError("modules require unique plain Python names")
        module_sources[path.stem] = path.read_text()
    shared._validate_common_script(source, module_sources, [source_plan["origin"]], runtime_source=runtime_source)
    bundle = shared._json(contracts_path)
    if bundle.get("schema") != "component-contract-bundle/v1" or not bundle.get("contracts"):
        raise ValueError("nonempty component-contract-bundle/v1 required")
    description = oracle.describe() if oracle else None
    if oracle is not None and description.get("independent") is not True:
        raise ValueError("oracle must attest independent=True")
    out = Path(out).resolve()
    frozen = out / "frozen"
    frozen.mkdir()
    (frozen / "script.py").write_text(source)
    for name, code in module_sources.items():
        (frozen / (name + ".py")).write_text(code)
    shared._write(frozen / "contracts.json", bundle)
    hashes = shared._freeze_runtime(frozen / "runtime", runtime_source=runtime_source)
    shared._freeze_dependencies(frozen, semantics)
    shutil.copyfile(shared.__file__, frozen / "controller-dependencies/runner_playwright.py")
    shutil.copytree(Path(__file__).parent, frozen / "contracts_v1", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copyfile(operation_lease.__file__, frozen / "operation_lease.py")
    if adapter_file:
        shutil.copyfile(adapter_file, frozen / "oracle-adapter.py")
    fixture = shared._fixture(source_plan)
    registration = {"schema": SCHEMA, "mode": "single_source_component_contract", "policy": policy,
                    "runtime_sha256": hashes, "runtime_source": str(runtime_source),
                    "script_sha256": shared._sha(source), "contracts_sha256": shared._file_sha(frozen / "contracts.json"),
                    "state0_prediction": state0_prediction, "final_prediction": final_prediction,
                    "oracle_description": description, "public_fixture": fixture, "teacher_forcing": False,
                    "model_calls": 0, "live_gate": "unchanged v8 synchronous checkpoint release",
                    "frozen_file_sha256": {str(p.relative_to(frozen)): shared._file_sha(p) for p in sorted(frozen.rglob("*")) if p.is_file()},
                    "scope": "Parameterized structural contracts and independent business truth; not exact complete website replication."}
    shared._write(out / "registration.json", registration)
    _verify_loaded_files()
    try:
        preparation = oracle.prepare("source", case_ref) if oracle else {}
    except Exception as error:
        preparation = {"initial_equivalence": "unconfirmed", "error": str(error)}
    shared._write(out / "oracle-preparation.json", preparation)
    if preparation.get("initial_equivalence") not in (True, "pass") or not preparation.get("reset_receipt"):
        raise ValueError("independent oracle preparation unconfirmed; no browser launched")
    if time.monotonic() - started >= policy["wall_seconds"]:
        raise TimeoutError("run wall deadline exhausted during preparation; no browser launched")
    directory = out / "source"
    directory.mkdir()
    jobdir, barrier = directory / "job", directory / "barrier"
    jobdir.mkdir()
    barrier.mkdir()
    plan = {**source_plan, "runtime": str(frozen / "runtime"), "socket": str(transport.make_socket_path())}
    job = {"origin": plan["origin"], "socket": plan["socket"], "fixture": fixture, "script": source,
           "modules": module_sources, "action_limit": policy["action_limit"], "state_path": str(jobdir / "state.json"),
           "step_barrier_dir": str(barrier), "state_barriers": True, "initial_url": plan["origin"] + "/",
           "collect_private_control_state": bool(policy.get("collect_private_control_state", False)),
           "settle_policy": policy["stability"], "step_barrier_timeout_seconds": min(60, policy["barrier_wait_seconds"] + 4),
           "init_script": plan.get("init_script")}
    shared._write(jobdir / "job.json", job)
    lease_directory = Path(policy.get("lease_directory", out.parent / "browser-operation-lease")).resolve()
    lease_directory.mkdir(parents=True, exist_ok=True)
    nonce, receipt = uuid.uuid4().hex, directory / "cleanup.json"
    leased_command = [transport.PYTHON, str(frozen / "operation_lease.py"), "--directory", str(lease_directory),
                     "--kind", "browser-call", "--guard", str(frozen / "runtime/process_guard.py"),
                     "--wait-seconds", "0", "--timeout-seconds", str(policy["wall_seconds"] + 20), "--",
                     *sandbox.command(plan["runtime"], jobdir / "job.json", plan["socket"], step_barrier_dir=barrier)]
    command = [transport.PYTHON, str(frozen / "runtime/process_guard.py"), "--receipt", str(receipt),
               "--nonce", nonce, "--", *leased_command]
    checks, previous = [], None
    reason = failure = None
    next_step, state0_seen, final_seen = 1, False, False
    last_record = None
    progress = time.monotonic()
    last_sample_at, workload_sample = 0, None
    with ExitStack() as stack:
        stack.enter_context(shared._origin_gateway(plan, gateway))
        stdout = stack.enter_context((directory / "stdout.log").open("xb"))
        stderr = stack.enter_context((directory / "stderr.log").open("xb"))
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True,
                                 env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        stack.callback(shared._terminate, child)
        lane = {"barrier": barrier, "child": child}
        workload = resource_guard.ResourceGuard([child.pid], out, limits=policy["resource_limits"]) if policy["resource_limits"] else None
        events = stack.enter_context((out / "progress.jsonl").open("x"))
        try:
            while True:
                now = time.monotonic()
                name = "state0" if not state0_seen else f"step-{next_step:04d}"
                if state0_seen and not (barrier / (name + ".json")).exists() and (barrier / "final.json").exists():
                    name = "final"
                path = barrier / (name + ".json")
                if now - last_sample_at >= 1:
                    resources = monitor.resources(out)
                    workload_sample = workload.sample() if workload else None
                    status = {"elapsed_seconds": now - started, "idle_seconds": now - progress,
                              "checkpoint": name, "resources": resources, "workload_resources": workload_sample}
                    shared._atomic(out / "status.json", status)
                    events.write(json.dumps(status) + "\n")
                    events.flush()
                    last_sample_at = now
                    if workload_sample and workload_sample["stop_required"]:
                        reason = "resource_limit_exceeded"
                    elif resources["available_memory_bytes"] < policy["min_memory_bytes"]:
                        reason = "memory_guard"
                    elif resources["available_disk_bytes"] < policy["min_disk_bytes"]:
                        reason = "disk_guard"
                settle_path = jobdir / "settle-status.json"
                if settle_path.exists():
                    settling = shared._json(settle_path)
                    if settling.get("status") == "running" and now > settling["watchdog_deadline_monotonic"]:
                        reason = "capture_stability_timeout"
                if (out / "STOP").exists():
                    reason = "coordinator_stop"
                elif now - started > policy["wall_seconds"]:
                    reason = "wall_time_exhausted"
                elif now - progress > policy["progress_seconds"]:
                    reason = "no_checkpoint_progress"
                if path.exists() and not reason:
                    record = shared._json(path)
                    last_record = record
                    configured = state0_prediction if name == "state0" else final_prediction if name == "final" else None
                    checked, previous = check_checkpoint(record, bundle, configured, oracle=oracle, case_ref=case_ref,
                                                         previous=previous, preparation=preparation, destination=out / "checks" / name)
                    checks.append({"checkpoint": record["checkpoint"], "action": record.get("action"), "method": record.get("method"),
                                   "primary_pass": checked["primary_pass"], "first_failure_layer": checked["first_failure_layer"],
                                   "contract_verdict": checked["contract_validation"]["verdict"],
                                   "business_verdict": checked["business"]["verdict"], "directory": "checks/" + name})
                    if not checked["primary_pass"]:
                        reason = "first_contract_gate_failure"
                        failure = {"checkpoint": name, "layer": checked["first_failure_layer"], "directory": "checks/" + name}
                    shared._release(lane, name, "stop" if reason else "continue", reason or "contract_and_truth_pass")
                    if name == "state0":
                        state0_seen = True
                    elif name == "final":
                        final_seen = True
                    else:
                        next_step += 1
                    progress = time.monotonic()
                if reason or final_seen:
                    break
                if child.poll() is not None:
                    reason = "missing_required_checkpoint"
                    break
                time.sleep(.04)
        except Exception as error:
            reason = "controller_error"
            failure = {"checkpoint": name, "layer": "controller_error", "error": type(error).__name__ + ": " + str(error)}
        finally:
            deadline = time.monotonic() + 12
            while child.poll() is None and time.monotonic() < deadline:
                for pending in barrier.glob("*.json"):
                    if ".release." not in pending.name:
                        shared._release(lane, pending.stem, "stop", reason or "cleanup")
                time.sleep(.05)
            shared._terminate(child)
        clean = guard.receipt_valid(receipt, nonce=nonce, supervisor_pid=child.pid)
        worker_path = jobdir / "evidence/result.json"
        worker = shared._json(worker_path) if worker_path.exists() else None
        actions = sum(check["checkpoint"] == "after_action" for check in checks)
        completed = bool(final_seen and state0_seen and actions > 0 and worker and worker.get("status") == "completed")
        success = completed and clean and child.returncode == 0 and not reason and all(check["primary_pass"] for check in checks)
        reason = reason or ("worker_completed" if success else "cleanup_or_completion_unconfirmed")
        if not success:
            line = ((last_record or {}).get("source_location") or {}).get("line")
            (directory / "unexecuted-source-suffix.py").write_text("".join(source.splitlines(keepends=True)[line:]) if line else source)
        result = {"schema": SCHEMA, "primary_pass": bool(success), "reason": reason, "first_failure": failure,
                  "live_gate": True, "teacher_forcing": False, "model_calls": 0, "state0_checked": state0_seen,
                  "final_checked": final_seen, "checked_actions": actions, "steps": checks,
                  "source": {"worker": worker, "exit_code": child.returncode, "process_tree_clean": clean,
                             "cleanup_receipt": str(receipt), "command": command},
                  "elapsed_seconds": time.monotonic() - started, "resource_last_sample": workload_sample,
                  "scope": registration["scope"]}
        shared._write(out / "result.json", result)
    return result


def run_source(source_plan, script_path, out, contracts_path, *, modules=(), policy=None, oracle=None,
               case_ref=None, state0_prediction=None, final_prediction=None, runtime_source=None):
    """Wall budget begins at entry, including freeze, reset and all independent calls."""
    started = time.monotonic()
    _verify_loaded_files()
    policy = {"wall_seconds": 600, "oracle_call_seconds": 15, **(policy or {})}
    if not 0 < policy["wall_seconds"] < float("inf") or not 0 < policy["oracle_call_seconds"] <= 25:
        raise ValueError("finite wall budget and oracle_call_seconds in (0,25] required")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = oracle
    proxy = None
    guard = transport._module("process_guard", runtime_source=runtime_source or RUNTIME)
    if oracle is not None:
        proxy = BoundedOracle(oracle, deadline=started + policy["wall_seconds"],
                              call_seconds=policy["oracle_call_seconds"], receipt=out / "oracle-cleanup.json", guard=guard)
    result = None
    try:
        result = _run_source(source_plan, script_path, out, contracts_path, modules=modules, policy=policy,
                             oracle=proxy, case_ref=case_ref, state0_prediction=state0_prediction,
                             final_prediction=final_prediction, runtime_source=runtime_source,
                             started=started, adapter_file=inspect.getsourcefile(type(original)) if original else None)
    except Exception as error:
        result = {"schema": SCHEMA, "primary_pass": False, "reason": "controller_preflight_error",
                  "first_failure": {"layer": "preflight", "error": type(error).__name__ + ": " + str(error)},
                  "checked_actions": 0, "steps": [], "state0_checked": False, "final_checked": False,
                  "live_gate": False, "source": {"process_tree_clean": None}, "elapsed_seconds": time.monotonic() - started}
    finally:
        clean = proxy.close() if proxy else True
    result["oracle_process_tree_clean"] = clean
    result["elapsed_seconds"] = time.monotonic() - started
    if not clean:
        result["primary_pass"] = False
        result["reason"] = "oracle_cleanup_unconfirmed"
    shared._atomic(out / "result.json", result)
    return result
