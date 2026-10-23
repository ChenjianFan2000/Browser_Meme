"""Prepare supervised construction workspaces and serve their browser gateway.

This mode does not enforce a learner OS boundary or call a model. Its browser
workers retain transport's namespace isolation. It produces no strict score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

from . import transport
from .operation_lease import boot_id

EXCLUDED = {"browser.py", "browser-requests", "browserrequests", "TASK.md", "CONTRACT.md",
            "PUBLIC_FIXTURE.json", "BROWSER_INTERFACE.md", "public-runtime", "generic-runtime",
            "observation.py", "script_policy.py", "__pycache__", ".git", "STOP"}


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _new_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _text(config, key, default=None):
    if key in config and key + "_path" in config:
        raise ValueError("provide only " + key + " or " + key + "_path")
    value = Path(config[key + "_path"]).read_text(encoding="utf-8") if key + "_path" in config else config.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key + " must contain nonempty text")
    return value


def _copy_previous(source, destination):
    copied = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in EXCLUDED or part.startswith(".browser-") for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("continuation artifacts may not contain symlinks: " + str(relative))
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copied[str(relative)] = _digest(target)
    return copied


_WRAPPER = r'''"""Coordinator browser handoff: --script relative.py [--module helper.py].
Requests and raw broker output remain in browser-requests/. No model is called.
"""
import argparse,json,os,subprocess,sys,time,uuid
from pathlib import Path
COMMAND = __COMMAND__
LEASE_COMMAND = __LEASE_COMMAND__
STOP_PATHS = __STOP_PATHS__
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script',required=True,help='Workspace-relative Python file exporting run(h)')
    parser.add_argument('--module',action='append',default=[],help='Workspace-relative pure helper module; repeatable')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if any(Path(p).exists() for p in STOP_PATHS):
        raise SystemExit('Construction session has a STOP marker; no request dispatched')
    for value in [args.script,*args.module]:
        path=Path(value)
        if path.is_absolute() or '..' in path.parts:
            raise SystemExit('Browser inputs must be workspace-relative')
        resolved=(root/path).resolve()
        try: resolved.relative_to(root)
        except ValueError: raise SystemExit('Browser input escapes workspace')
        if not resolved.is_file(): raise SystemExit('Browser input file missing')
    requests=root/'browser-requests';requests.mkdir(exist_ok=True)
    stem=str(time.time_ns())+'-'+uuid.uuid4().hex[:8]
    request=requests/(stem+'.json')
    with request.open('x') as stream: json.dump({'script_path':args.script,'modules':args.module},stream)
    started=time.monotonic()
    status={'request':request.name,'state':'running','started_at_ns':time.time_ns()}
    status_path=requests/(stem+'.status.json')
    status_path.write_text(json.dumps(status,indent=2))
    try:
        result=subprocess.run(LEASE_COMMAND+['--expected-parent',str(os.getpid()),'--']+
            COMMAND+['--execute-file',str(request)],cwd=root,capture_output=True,text=True,start_new_session=True)
        (requests/(stem+'.stdout.txt')).write_text(result.stdout)
        (requests/(stem+'.stderr.txt')).write_text(result.stderr)
        status.update(state='finished',exit_code=result.returncode,elapsed_seconds=time.monotonic()-started)
        try: status['broker_status']=json.loads(result.stdout).get('result',{}).get('status')
        except ValueError: status['broker_status']='unparseable_output'
        status_path.write_text(json.dumps(status,indent=2))
        print(result.stdout,end='')
        if result.stderr: print(result.stderr,end='',file=sys.stderr)
        return result.returncode
    except BaseException as error:
        status.update(state='interrupted',error=type(error).__name__,elapsed_seconds=time.monotonic()-started)
        status_path.write_text(json.dumps(status,indent=2))
        raise
if __name__=='__main__': raise SystemExit(main())
'''


def _operation_command(lease, kind, *, wait_seconds=None, timeout_seconds=None, stop_paths=()):
    waiting = lease["browser_wait_seconds"] if wait_seconds is None else wait_seconds
    timeout = lease["browser_timeout_seconds"] if timeout_seconds is None else timeout_seconds
    command = [transport.PYTHON, lease["module"], "--directory", lease["directory"],
               "--kind", kind, "--guard", lease["guard"], "--wait-seconds", str(waiting),
               "--timeout-seconds", str(timeout)]
    if kind == "browser-call":
        budget = lease["run_budget"]
        command += ["--deadline-ns", str(budget["deadline_ns"]), "--budget-boot-id", budget["boot_id"]]
    for path in stop_paths:
        command += ["--stop-path", path]
    return command


def prepare(config: dict) -> dict:
    """Create a new construction run without resetting a website or calling a model.

    Required: run_dir, origin, task (or task_path). Optional: contract/contract_path,
    fixture and transport budget/upstream/auth selectors. from_previous_workspace
    requires explicit same-author or new-context artifact continuation; neither
    becomes an independent run.
    Caller supplies public task/fixture data; this helper adds no website rules.
    """
    budget_started_ns = time.monotonic_ns()
    budget_started_wall_ns = time.time_ns()
    call_timeout = config.get("browser_call_timeout_seconds")
    if "browser_call_timeout_seconds" in config and (
        isinstance(call_timeout, bool) or not isinstance(call_timeout, (int, float))
        or not 0 < call_timeout < float("inf")
    ):
        raise ValueError("browser_call_timeout_seconds must be a positive finite number")
    if not isinstance(config.get("fixture", {}), dict):
        raise ValueError("fixture must be a JSON object; the coordinator must load any fixture file before prepare")
    task = _text(config, "task")
    source = config.get("from_previous_workspace")
    same_author = bool(source and config.get("same_author_continuation") is True)
    inherited_context = bool(source and config.get("new_context_with_inherited_artifacts") is True)
    if source and same_author == inherited_context:
        raise ValueError("from_previous_workspace requires exactly one explicit continuation provenance")
    if source:
        source = Path(source).resolve(strict=True)
        if not source.is_dir():
            raise ValueError("from_previous_workspace must be a directory")
        run_root = Path(config["run_dir"]).resolve()
        if run_root == source or source in run_root.parents or run_root in source.parents:
            raise ValueError("continuation source and new run may not contain one another")
    default_contract = (Path(__file__).with_name("LEARNER_CONTRACT.md")).read_text(encoding="utf-8")
    default_contract = default_contract.replace(
        "You are an independent `gpt-6.1-sol` learner. The manager supplies a public\nfixture and one browser origin. You receive no website source or prior model.",
        "You are the construction author. The manager supplies a public fixture and\none browser origin. You receive no website source. Declared artifact\ncontinuations may reuse only the supplied public construction artifacts.")
    scope = ("# Construction execution scope\n\n"
             "Learner OS isolation is limited and is NOT enforced in this construction mode.\n"
             "Browser workers use the isolated generic runtime. This run is not an independent\n"
             "strict experiment and has no strict score. Do not inspect files outside this workspace.\n"
             + ("This is a same-author continuation; inherited artifacts are prior author knowledge.\n" if same_author else
                "This is a new author context inheriting earlier construction artifacts; it is not an independent experiment.\n" if inherited_context else
                "This is a new construction workspace; no independence claim is certified.\n")
             + "Use `python browser.py --script relative.py [--module helper.py]` for browser execution.\n\n")
    contract = scope + _text(config, "contract", default_contract)
    session_config = {k: v for k, v in config.items() if k in {
        "run_dir", "origin", "fixture", "action_limit", "script_call_limit", "time_limit_seconds",
        "upstream_host", "upstream_port", "auth_source", "reasoning_effort", "init_script", "runtime_source"}}
    session_config["prompt"] = task
    plan = transport.prepare_session(session_config)
    root, workspace, private = (Path(plan[key]) for key in ("run_dir", "workspace", "private"))
    copied = _copy_previous(source, workspace) if source else {}
    (workspace / "CONTRACT.md").write_text(contract, encoding="utf-8")
    (workspace / "TASK.md").write_text(task, encoding="utf-8")
    shutil.copyfile(private / "public-fixture.json", workspace / "PUBLIC_FIXTURE.json")
    public_runtime = workspace / "public-runtime"
    shutil.copytree(plan["public_runtime"], public_runtime)
    for path in public_runtime.iterdir():
        if path.is_file():
            shutil.copyfile(path, workspace / path.name)
    stop_paths = [str(root / "STOP"), str(workspace / "STOP"), str(private / "STOP")]
    control = private / "control"
    control.mkdir()
    budget = {"schema": "construction-run-budget/v1", "clock": "monotonic_ns", "boot_id": boot_id(),
              "started_ns": budget_started_ns, "started_wall_ns": budget_started_wall_ns,
              "deadline_ns": budget_started_ns+int(plan["time_limit_seconds"]*1e9),
              "wall_seconds": plan["time_limit_seconds"], "starts_from": "prepare_entry",
              "scope": "browser calls including admission wait and execution; maintenance never extends deadline"}
    budget_file = control / "run-budget.json"
    _new_json(budget_file, budget)
    lease_module = control / "operation_lease.py"
    shutil.copyfile(Path(__file__).with_name("operation_lease.py"), lease_module)
    lease_directory = private / "operation-lease"
    lease_directory.mkdir(mode=0o700)
    lease = {"schema": "construction-operation-lease/v2", "module": str(lease_module),
             "directory": str(lease_directory), "guard": str(Path(plan["runtime"]) / "process_guard.py"),
             "browser_wait_seconds": plan["time_limit_seconds"],
             "browser_timeout_seconds": plan["time_limit_seconds"] if call_timeout is None else call_timeout,
             "run_budget": budget,
             "scope": "calls and maintenance routed through this construction run; cooperative management interface"}
    lease_command = _operation_command(lease, "browser-call", stop_paths=stop_paths)
    command = [transport.PYTHON, str(Path(plan["runtime"]) / "browser_broker.py"), "--config", plan["broker_config"]]
    wrapper = (_WRAPPER.replace("__COMMAND__", repr(command)).replace("__STOP_PATHS__", repr(stop_paths))
               .replace("__LEASE_COMMAND__", repr(lease_command)))
    (workspace / "browser.py").write_text(wrapper, encoding="utf-8")
    frozen = [workspace / name for name in ("CONTRACT.md", "TASK.md", "PUBLIC_FIXTURE.json", "browser.py")]
    frozen += [p for directory in (Path(plan["runtime"]), Path(plan["public_runtime"]), public_runtime)
               for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    frozen += [workspace / p.name for p in public_runtime.iterdir() if p.is_file()]
    frozen += [private / "launch-plan.json", private / "broker-config.json", private / "public-fixture.json", private / "prompt.txt"]
    frozen += [lease_module, budget_file]
    registration = {"schema_version": 1, "kind": "supervised_construction_inputs", "workspace": str(root),
        "isolation_limited": True, "forced_learner_isolation": False, "forced_browser_isolation": True,
        "independent": False, "strict_scores": None, "strict_score": None,
        "same_author_continuation": same_author,
        "new_context_with_inherited_artifacts": inherited_context,
        "from_previous_workspace": str(source) if source else None,
        "inherited_artifact_hashes": copied, "files": {str(p.relative_to(root)): _digest(p) for p in frozen},
        "construction_helper_sha256": _digest(__file__), "stop_paths": stop_paths,
        "operation_lease": lease,
        "run_budget": budget,
        "meaning": "Frozen input bytes and declared provenance; no strict independence or behavioral score."}
    _new_json(private / "input-registration.json", registration)
    return {"plan": plan, "plan_path": str(private / "launch-plan.json"),
            "registration_path": str(private / "input-registration.json"),
            "workspace": str(workspace), "isolation_limited": True, "independent": False,
            "operation_lease": lease,
            "same_author_continuation": same_author,
            "new_context_with_inherited_artifacts": inherited_context, "strict_scores": None}


def maintenance(plan_path, command, *, wait_seconds=0, timeout_seconds=300):
    """Run an explicit management command under this run's maintenance lease.

    Never reads target source or invents a reset command. Old frozen runs that
    lack the lease are rejected; creating a new run does not retrofit them.
    """
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text())
    root, private = Path(plan["run_dir"]), Path(plan["private"])
    registration = json.loads((private / "input-registration.json").read_text())
    changed = _verify(root, registration)
    if changed:
        raise ValueError("registered construction inputs changed: " + ", ".join(changed))
    lease = registration.get("operation_lease")
    if not lease:
        raise ValueError("this frozen run has no operation lease; prepare a new construction run")
    if not command:
        raise ValueError("explicit maintenance command required")
    args = _operation_command(lease, "maintenance", wait_seconds=wait_seconds, timeout_seconds=timeout_seconds)
    args += ["--expected-parent", str(os.getpid()), "--", *command]
    result = subprocess.run(args, start_new_session=True)
    return {"kind": "construction_maintenance", "exit_code": result.returncode,
            "operation_lease": lease["directory"], "command": list(command),
            "wait_seconds": wait_seconds, "timeout_seconds": timeout_seconds}


def _verify(root, registration):
    return [name for name, digest in registration["files"].items()
            if not (root / name).is_file() or _digest(root / name) != digest]


def _budget_exhausted(registration):
    budget = registration.get("run_budget")
    return bool(budget and (budget["boot_id"] != boot_id() or time.monotonic_ns() >= budget["deadline_ns"]))


def serve_gateway(plan_path, *, interval=1.0, stop_event=None):
    """Serve the fixed origin until SIGTERM/SIGINT, STOP, or integrity/health failure.

    Writes private/gateway-heartbeat.jsonl and gateway-health.json. No source reset,
    website probe, browser action or model call is performed by this service.
    """
    interval = float(interval)
    if not 0.05 <= interval <= 60:
        raise ValueError("heartbeat interval must be between 0.05 and 60 seconds")
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text())
    root, private = Path(plan["run_dir"]), Path(plan["private"])
    registration = json.loads((private / "input-registration.json").read_text())
    changed = _verify(root, registration)
    if changed:
        raise ValueError("registered construction inputs changed: " + ", ".join(changed))
    stopped = stop_event or threading.Event()
    reason = "stop_event"
    previous = {}
    def stop(signum, frame):
        nonlocal reason
        reason = "signal:" + signal.Signals(signum).name
        stopped.set()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, stop)
    started = time.monotonic()
    latest = private / "gateway-health.json"
    def heartbeat(state, **extra):
        value = {"state": state, "pid": os.getpid(), "time_ns": time.time_ns(),
                 "elapsed_seconds": time.monotonic() - started, "model_calls": 0,
                 "source_reset": False, "isolation_limited": True, **extra}
        with (private / "gateway-heartbeat.jsonl").open("a") as stream:
            stream.write(json.dumps(value) + "\n")
            stream.flush()
        temporary = latest.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2))
        temporary.replace(latest)
        return value
    try:
        if any(Path(p).exists() for p in registration["stop_paths"]):
            return heartbeat("stopped", reason="STOP_present_before_start")
        if _budget_exhausted(registration):
            return heartbeat("stopped", reason="construction_total_wall_deadline")
        with transport.OriginGateway(plan) as gateway:
            heartbeat("ready", socket_exists=Path(plan["socket"]).exists())
            print(json.dumps({"state": "ready", "plan": str(plan_path)}), flush=True)
            while not stopped.wait(interval):
                if _budget_exhausted(registration):
                    reason = "construction_total_wall_deadline"
                    break
                if any(Path(p).exists() for p in registration["stop_paths"]):
                    reason = "STOP"
                    break
                changed = _verify(root, registration)
                if changed:
                    reason = "registered_inputs_changed"
                    heartbeat("failed", reason=reason, changed=changed)
                    break
                alive = gateway.thread.is_alive() and Path(plan["socket"]).exists()
                heartbeat("healthy" if alive else "failed", gateway_alive=alive)
                if not alive:
                    reason = "gateway_unhealthy"
                    break
        return heartbeat("stopped", reason=reason)
    except BaseException as error:
        heartbeat("failed", reason=type(error).__name__)
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare", help="Create a new construction workspace; never calls a model")
    command.add_argument("--config", required=True, help="JSON with run_dir, origin, task/task_path and optional public fixture/budgets")
    command = commands.add_parser("serve-gateway", help="Serve fixed-origin browser gateway with heartbeat, STOP and SIGTERM handling")
    command.add_argument("--plan", required=True, help="private/launch-plan.json produced by prepare")
    command.add_argument("--interval", type=float, default=1, help="Heartbeat seconds, 0.05–60 (default 1)")
    command = commands.add_parser("maintenance", help="Run an explicit management command under the run's maintenance lease")
    command.add_argument("--plan", required=True)
    command.add_argument("--wait-seconds", type=float, default=0, help="0 rejects an active call atomically; positive value reserves admission and waits")
    command.add_argument("--timeout-seconds", type=float, default=300)
    command.add_argument("maintenance_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(json.loads(Path(args.config).read_text()))
    elif args.command == "serve-gateway":
        result = serve_gateway(args.plan, interval=args.interval)
    else:
        command = args.maintenance_command[1:] if args.maintenance_command[:1] == ["--"] else args.maintenance_command
        result = maintenance(args.plan, command, wait_seconds=args.wait_seconds, timeout_seconds=args.timeout_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "maintenance":
        return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
