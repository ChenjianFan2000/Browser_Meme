"""Independent frozen-case Solar supervision with management-owned evaluation.

No website selectors, rules, reference answers or task scripts are authored here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import random
import subprocess
import sys
import time

from .management import ROOT, DISTRO, LINUX_ROOT, provision_runtime, put_files, export_tree, wsl_python
from .run_learning import EXPERIMENT, SITE_RUNTIME, TrustedEvents, management_barrier, management_barrier_passed
from .relay import FixedOriginRelay
from .prediction_record import PredictionRecorder
from .records import write_new_json, freeze_manifest, verify_manifest


def driver(runtime, arguments):
    env = os.environ.copy()
    env["BM_DISCOGS_PHASE2_RUNTIME"] = str(runtime)
    result = subprocess.run([sys.executable, str(ROOT / "harness/sites/discogs/phase2_private/driver.py"), *arguments],
                            env=env, capture_output=True, text=True, timeout=120, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return json.loads(result.stdout)


def evaluation_prompt(condition, frozen, revision):
    return f"""You are an independent exact gpt-6.1-sol frozen-evaluation executor for condition {condition}.
This fresh context receives ONE current task in current-task.json and an immutable learning package at {frozen}.
Read its READY.json and revision {revision}, plus your local RUNTIME_GUIDE.md. This package was learned in a separate browser-only experiment. No website source, oracle, hidden state or earlier test feedback is available.
Complete this current task on the real website through the phase2 native Playwright MCP tools. Write your own task scripts in your current workspace; use native locators and the learned evidence. Frozen rules/model are read-only: DO NOT modify them or create a replacement behavior predictor. Temporary execution-script fixes and current-task LLM supervision are allowed.
Before any target business write, inspect the relevant initial state through read-only UI navigation/authentication. Then freeze exactly ONE whole-task prediction via declare_task_prediction. It must use disposition accepted/rejected/unknown, effects persistent_state_changed bool/null and affected_record_count int/null, ui_claims list, unknowns list.
{'Call the model_predict tool with current allowed observations and task intent. Inspect the frozen predict() function to supply its expected input schema. Declare its exact returned output; you cannot substitute your own revised forecast. If evidence is insufficient, preserve its unknowns.' if condition == 'A' else 'Reason from the frozen natural-language rules and current browser evidence to write the task prediction. There is no executable behavior model in this condition; do not implement one.'}
After the declaration, execute the task with native Playwright and read back actual UI results. Use h.expect before EVERY native action for per-action predictions. Whole-task and per-action predictions are separate. Do not use raw API business requests, client code, DOM mutation, hidden state or guessed write retries.
Classify locator/timing/implementation errors separately from business counterexamples. If a non-idempotent write might already have happened, first inspect its effect and stop if unconfirmed. Do not revise frozen knowledge with this task's feedback. Refusals and unknowns are valid findings; your claimed outcome is never the independent truth.
Each browser script starts a new page but preserves cookies/local storage and this case's business state. Navigate explicitly. Total case limits: 60 UI actions, 20 browser script executions, 900 seconds, single script 300 seconds, native operations 30 seconds. Every actual retry/wait counts. Do not start further work when a budget stops execution.
Use the public fixture JSON without printing its account values. The only origin is http://127.0.0.1:12042. Your command tools can only access your own workspace and the read-only frozen package, with no network; browser access is exclusively through MCP.
Finish with CASE_DONE.json containing current task id, claimed_ui_outcome, evidence_refs with actual hashes, remaining uncertainty and any failures. This is a current-task record, not a new learned version. End after completing or honestly stopping this task; no other evaluation task may be requested.
"""


def create_case_session(identifier, runtime, case, condition, frozen_linux, frozen_files, revision,
                        before_hash, socket, control_socket, fixture):
    base = LINUX_ROOT + "/" + identifier
    work, private, home = base + "/workspace", base + "/private", base + "/codex-home"
    broker = {"workspace": work, "private": private + "/browser", "runtime": runtime,
              "origin": "http://127.0.0.1:12042", "socket": socket, "control_socket": control_socket,
              "fixture_path": base + "/public-fixture.json", "action_limit": 60,
              "script_call_limit": 20, "time_limit_seconds": 900,
              "case_id": case["id"], "before_sha256": before_hash, "condition": condition,
              "frozen_root": frozen_linux, "frozen_files": frozen_files,
              "frozen_model": frozen_linux + "/" + revision + "/behavior_model.py"}
    plan = {"private": private + "/solar", "workspace": work, "runtime": runtime,
            "broker_config": base + "/broker-config.json", "broker_file": "evaluation_broker.py",
            "codex_home": home, "prompt_path": work + "/PROMPT.md", "time_limit_seconds": 900,
            "condition": condition, "model_sampling_seed": None, "reasoning_effort": "high",
            "readonly_paths": [frozen_linux]}
    prompt = evaluation_prompt(condition, frozen_linux, revision)
    files = {base + "/broker-config.json": json.dumps(broker).encode(),
             base + "/launch-plan.json": json.dumps(plan).encode(), base + "/public-fixture.json": fixture,
             work + "/public-fixture.json": fixture, work + "/current-task.json": json.dumps(case, ensure_ascii=False).encode(),
             work + "/RUNTIME_GUIDE.md": (ROOT / "harness/phase2/RUNTIME_GUIDE.md").read_bytes(),
             work + "/PROMPT.md": prompt.encode(), home + "/auth.json": (Path.home() / ".codex/auth.json").read_bytes()}
    put_files(files, private=True)
    wsl_python("import os; os.chmod(" + repr(home) + ",0o700)")
    return base, plan, prompt


def frozen_inputs(learning):
    manifest = json.loads((learning / "learning-manifest.json").read_text(encoding="utf-8"))["files"]
    if verify_manifest(learning, manifest):
        raise ValueError("learning artifact integrity check failed")
    summary = json.loads((learning / "learning-summary.json").read_text(encoding="utf-8"))
    if summary["status"] != "learning_finished" or not management_barrier_passed(summary.get("management_barrier")):
        raise ValueError("learning package is not complete")
    registration = json.loads((learning / "registration.json").read_text(encoding="utf-8"))
    if registration["kind"] != "formal_learning":
        raise ValueError("pilot packages cannot enter the formal denominator")
    ready = json.loads((learning / "workspace/READY.json").read_text(encoding="utf-8"))
    revision = ready["revision_directory"].replace("\\", "/").strip("/")
    files = {}
    for path in (learning / "workspace" / revision).rglob("*"):
        if path.is_file():
            files[path.relative_to(learning / "workspace").as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    files["READY.json"] = hashlib.sha256((learning / "workspace/READY.json").read_bytes()).hexdigest()
    return registration, revision, files


def collect_browser_results(private):
    results = []
    for call in sorted(Path(private).glob("call-*")):
        management = call / "management-result.json"
        evidence = call / "evidence/result.json"
        if management.exists():
            result = json.loads(management.read_text(encoding="utf-8"))["result"]
        elif evidence.exists():
            result = json.loads(evidence.read_text(encoding="utf-8"))
        else:
            actions = call / "evidence/actions.jsonl"
            count = 0
            if actions.exists():
                for line in actions.read_text(encoding="utf-8").splitlines():
                    try:
                        count += json.loads(line).get("kind") == "action_before"
                    except ValueError:
                        pass
            result = {"status": "error", "actions": count, "error": "browser_call_incomplete"}
        results.append(result)
    return results


def run_case(learning, case, index, runtime_dir, frontend_port, gate, runtime, runtime_hash):
    registration, revision, frozen_files = frozen_inputs(learning)
    condition = registration["condition"]
    run_id = registration["run_id"]
    identifier = f"eval-{run_id}-{index:02d}"
    out = EXPERIMENT / "evaluations" / run_id / f"case-{index:02d}"
    out.mkdir(parents=True, exist_ok=False)
    case_private = runtime_dir / "private" / "frozen-evaluation" / identifier
    case_private.mkdir(parents=True, exist_ok=False)
    reset = driver(runtime_dir, ["reset-case", "--id", case["id"]])
    before = driver(runtime_dir, ["begin", "--id", case["id"], "--output", str(case_private / "before.json")])
    before_path = Path(before["output"])
    recorder = PredictionRecorder(case["id"], before_path, case_private / "prediction.json")
    socket, control = LINUX_ROOT + "/" + identifier + ".sock", LINUX_ROOT + "/" + identifier + "-control.sock"
    frozen_linux = LINUX_ROOT + "/" + run_id + "/workspace"
    fixture_path = runtime_dir / "public-fixture.json"
    if not fixture_path.exists():
        fixture_path = SITE_RUNTIME / "public-fixture.json"
    base, plan, prompt = create_case_session(identifier, runtime, case, condition, frozen_linux, frozen_files,
                                             revision, before["sha256"], socket, control, fixture_path.read_bytes())
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    write_new_json(out / "registration.json", {"case_id": case["id"], "index": index, "learning_run": run_id,
                                                "condition": condition, "runtime": str(runtime_dir), "frontend_port": frontend_port,
                                                "reset": reset, "before": before, "runtime_sha256": runtime_hash,
                                                "frozen_files": frozen_files, "plan": plan, "gate": gate,
                                                "exposure": "current_case_only_fresh_context", "time_started_ns": time.time_ns()})
    events = TrustedEvents(out / "trusted-gateway.jsonl", runtime=runtime_dir)
    command = ["wsl", "-d", DISTRO, "--", "python3", runtime + "/relay.py", "linux", "--socket", socket,
               "--origin", "http://127.0.0.1:12042", "--control-socket", control]
    relay = FixedOriginRelay(command, "http://127.0.0.1:12042", "127.0.0.1", frontend_port,
                             out / "relay.stderr.txt", callback=events, control_callback=recorder)
    started = time.monotonic()
    code = None
    try:
        if not relay.ready.wait(20):
            raise RuntimeError("case relay unavailable")
        args = ["wsl", "-d", DISTRO, "--", "python3", runtime + "/launch_solar.py", "--plan", base + "/launch-plan.json"]
        with (out / "launcher.stdout.txt").open("xb") as stdout, (out / "launcher.stderr.txt").open("xb") as stderr:
            child = subprocess.Popen(args, stdout=stdout, stderr=stderr, creationflags=0x08000000)
            print(json.dumps({"event": "case_started", "learning_run": run_id, "case_index": index, "case_id": case["id"]}), flush=True)
            last_notice = time.monotonic()
            while child.poll() is None:
                time.sleep(5)
                if time.monotonic() - last_notice >= 60:
                    print(json.dumps({"event": "case_progress", "learning_run": run_id, "case_index": index,
                                      "elapsed_seconds": round(time.monotonic() - started), "http_events": events.count,
                                      "prediction_declared": recorder.destination.exists()}), flush=True)
                    last_notice = time.monotonic()
            code = child.returncode
    finally:
        relay.close()
        events.close()
        export_tree(base + "/workspace", out / "workspace")
        export_tree(base + "/private", out / "private")
    barrier = management_barrier(out / "private", relay, events)
    write_new_json(out / "management-barrier.json", barrier)
    screenshots = sorted((out / "private/browser").glob("call-*/evidence/obs-*.png"))
    screenshot = None
    if screenshots:
        screenshot = case_private / "final-screenshot.png"
        shutil.copyfile(screenshots[-1], screenshot)
    result_files = sorted((out / "private/browser").glob("call-*/evidence/result.json"))
    browser_records = collect_browser_results(out / "private/browser")
    last_result = browser_records[-1] if browser_records else {"error": "no_browser_execution"}
    ui = {"events": [json.loads(line) for line in events.destination.read_text(encoding="utf-8").splitlines()],
          "screenshot_path": str(screenshot) if screenshot else None, "ui_error": last_result.get("error"),
          "management_barrier": barrier}
    write_new_json(case_private / "ui-evidence.json", ui)
    arguments = ["finish", "--id", case["id"], "--before", str(before_path), "--ui-evidence", str(case_private / "ui-evidence.json"),
                 "--output", str(case_private / "evaluation.json")]
    if recorder.destination.exists():
        arguments += ["--prediction-record", str(recorder.destination)]
    finish = driver(runtime_dir, arguments)
    value = json.loads(Path(finish["output"]).read_text(encoding="utf-8"))
    launch_path = out / "private/solar/launch-result.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8")) if launch_path.exists() else {}
    summary = {"case_id": case["id"], "case_index": index, "learning_run": run_id, "condition": condition,
               "launcher_exit_code": code, "model_cli_exit_code": launch.get("exit_code"),
               "model_cli_timeout": launch.get("timeout"), "elapsed_seconds": time.monotonic() - started,
               "ui_actions": sum(item.get("actions", 0) for item in browser_records),
               "browser_executions": len(browser_records), "declared_prediction": recorder.destination.exists(),
               "independent_evaluation": value["evaluation"], "prediction_provenance": value.get("prediction_provenance"),
               "evaluation_record": finish, "usage_events": launch.get("usage_events"), "model_calls": None,
               "cost": None, "relay_errors": relay.errors, "management_barrier": barrier,
               "safe_to_reset": value.get("safe_to_reset") is True and management_barrier_passed(barrier),
               "reset_safety": value.get("reset_safety"),
               "case_denominator_retained": True}
    write_new_json(out / "case-summary.json", summary)
    freeze_manifest(out, [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()], out / "case-manifest.json")
    print(json.dumps({"event": "case_finished", "learning_run": run_id, "case_index": index,
                      "ui_actions": summary["ui_actions"], "elapsed_seconds": round(summary["elapsed_seconds"])}), flush=True)
    if not summary["safe_to_reset"]:
        raise RuntimeError("case retained but reset safety is unconfirmed; no next reset is allowed")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning-run", required=True)
    parser.add_argument("--runtime", default=str(SITE_RUNTIME))
    parser.add_argument("--frontend-port", type=int, default=12042)
    parser.add_argument("--evaluation-acceptance", required=True)
    parser.add_argument("--case-index", type=int)
    args = parser.parse_args()
    if args.case_index is not None and not 1 <= args.case_index <= 30:
        parser.error("--case-index must be within 1..30")
    gate_path = Path(args.evaluation_acceptance)
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate["status"] != "passed":
        raise ValueError("frozen-evaluation isolation gate not passed")
    for name, expected in gate.get("runtime_files_sha256", {}).items():
        if hashlib.sha256((ROOT / "harness/phase2" / name).read_bytes()).hexdigest() != expected:
            raise ValueError("evaluation code changed after acceptance: " + name)
    runtime_dir = Path(args.runtime).resolve()
    learning = EXPERIMENT / "runs" / args.learning_run
    learning_registration, _, _ = frozen_inputs(learning)
    public = driver(runtime_dir, ["inventory-public"])
    inventory = json.loads(Path(public["output"]).read_text(encoding="utf-8"))
    if not isinstance(inventory, list):
        inventory = inventory.get("cases", inventory.get("public_cases"))
    if not isinstance(inventory, list) or len(inventory) != 30:
        raise ValueError("fixed 30-case public projection not found")
    runtime, digest = provision_runtime()
    ordered = list(enumerate(inventory, 1))
    random.Random(learning_registration["seed"]).shuffle(ordered)
    for index, case in ordered:
        if args.case_index is not None and index != args.case_index:
            continue
        existing = EXPERIMENT / "evaluations" / args.learning_run / f"case-{index:02d}"
        if (existing / "case-manifest.json").exists():
            manifest = json.loads((existing / "case-manifest.json").read_text(encoding="utf-8"))["files"]
            if verify_manifest(existing, manifest):
                raise ValueError("existing completed case integrity failed")
            previous_summary = json.loads((existing / "case-summary.json").read_text(encoding="utf-8"))
            if previous_summary.get("safe_to_reset") is not True:
                raise ValueError("completed case does not authorize a subsequent reset")
            previous = json.loads((existing / "registration.json").read_text(encoding="utf-8"))
            if any(previous.get(key) != value for key, value in {
                    "case_id": case["id"], "index": index, "learning_run": args.learning_run,
                    "condition": learning_registration["condition"]}.items()):
                raise ValueError("completed case identity differs from current frozen inventory")
            print(json.dumps({"event": "preserved_completed_case", "index": index}), flush=True)
            continue
        if existing.exists():
            raise ValueError("partial case exists; explicit recovery record is required")
        run_case(learning, case, index, runtime_dir, args.frontend_port,
                 {"path": str(gate_path), "sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest()}, runtime, digest)


if __name__ == "__main__":
    main()
