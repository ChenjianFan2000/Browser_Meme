"""Run an independent browser-only learner; site-specific truth stays external."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from .management import ROOT, DISTRO, LINUX_ROOT, provision_runtime, fresh_session, export_tree, wsl_python
from .relay import FixedOriginRelay
from .process_guard import receipt_valid
from .records import write_new_json, freeze_manifest, validate_rules, validate_browser_exports


EXPERIMENT = ROOT / "harness/experiments/phase2-discogs-20261021-01"
SITE_RUNTIME = ROOT / ".runtime/phase2-routing-v002"


def driver(command, runtime=SITE_RUNTIME):
    env = os.environ.copy()
    env["BM_DISCOGS_PHASE2_RUNTIME"] = str(runtime)
    result = subprocess.run([sys.executable, str(ROOT / "harness/sites/discogs/phase2_private/driver.py"), *command],
                            env=env, capture_output=True, text=True, timeout=120, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return json.loads(result.stdout)


class TrustedEvents:
    def __init__(self, destination, runtime=SITE_RUNTIME):
        os.environ["BM_DISCOGS_PHASE2_RUNTIME"] = str(runtime)
        from harness.sites.discogs.phase2_private.evaluator import ingest_http
        self.ingest = ingest_http
        self.destination = Path(destination)
        self.file = self.destination.open("x", encoding="utf-8")
        self.lock = threading.Lock()
        self.count = 0

    def __call__(self, request):
        event = self.ingest(**{key: request[key] for key in ("method", "url", "status", "request_body", "response_body", "content_type")})
        if event is not None:
            with self.lock:
                event["management_received_ns"] = time.time_ns()
                event["management_request_started_ns"] = request["management_request_started_ns"]
                event["event_phase"] = request["event_phase"]
                self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
                self.file.flush()
                self.count += 1

    def close(self):
        with self.lock:
            self.file.close()


def management_barrier_passed(value):
    keys = {"relay_drained", "browser_tree_clean", "gateway_log_complete"}
    return isinstance(value, dict) and set(value) == keys and all(value[key] is True for key in keys)


def management_barrier(private, relay, events):
    solar = Path(private) / "solar"
    launch_path = solar / "launch-result.json"
    clean = False
    if launch_path.is_file():
        try:
            launch = json.loads(launch_path.read_text(encoding="utf-8"))
            name = launch.get("cleanup_receipt", "")
            if name and Path(name).name == name:
                clean = receipt_valid(solar / name, nonce=launch.get("cleanup_nonce"),
                                      supervisor_pid=launch.get("supervisor_pid"))
        except (OSError, ValueError, TypeError):
            pass
    with relay.active_condition:
        drained = not relay.active and not relay.thread.is_alive() and relay.child.poll() is not None
    return {"relay_drained": drained and "unsettled_requests_at_close" not in relay.errors,
            "browser_tree_clean": clean,
            "gateway_log_complete": drained and not relay.errors and events.file.closed}


def learner_prompt(condition, seed, pilot):
    return f"""You are the independent experimental learner, exact gpt-6.1-sol, condition {condition}, scheduling seed {seed}.
This is {'a protocol pilot (not a formal score)' if pilot else 'a formal independent browser-only learning run'}.
Read LEARNER_CONTRACT.md and RUNTIME_GUIDE.md in your current workspace, then actively perform the experiment. Do not merely propose a plan.
Your only target website information initially is the public origin http://127.0.0.1:12042 and public-fixture.json. Inspect fixture keys without printing credential values. No site source, private answers, historical rules, selectors, or tasks are supplied.
Find your actual phase2 MCP tool in the available tool list. Write your own native Playwright scripts in this workspace and execute them through that tool. Command tools are for offline work only; they cannot reach the site.
Your interaction limit is {100 if pilot else 300} actual UI actions, 40 browser script submissions, and {3600 if pilot else 7200} seconds inclusive. One script timeout is 300 seconds. Use small discriminating experiments so failures are diagnosable. Inspect resulting DOM/network/screenshots as needed. Missing controls are not evidence of missing backend behavior.
Discover pages and objects, then test competing hypotheses, successful changes, rejection/boundaries, repeats and short combinations. Follow each action with readback, classify evidence, and keep unknowns. Preserve failed versions. Do not perform blind retries after an unconfirmed non-idempotent write. Do not fetch APIs directly, read client script bodies or use JavaScript evaluation.
Condition A requires a separate executable behavior_model.py with predict(observation,intent). Condition B MUST NOT produce executable behavior prediction; use prose knowledge plus native UI scripts. Both receive the same budget, evidence access, ongoing LLM supervision and memory.
Publish complete versioned artifacts required by the contract, citing exported browser evidence by actual relative path and sha256. Paths in evidence_refs are relative to the workspace root. Verified rules must refer to observed, limited conditions; mark all broader inferences as hypotheses. Do not use source_refs.
Write READY.json only when your best budget-bounded revision is complete, with revision_directory, stop_reason, and limitations. A valid final package with honest unknowns is required even if coverage is limited. Leave your own reusable scripts for later task execution, but no private tasks are available during learning. End after publishing READY.json.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--condition", choices=["A", "B"], required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--isolation-acceptance", required=True)
    parser.add_argument("--site-runtime", default=str(SITE_RUNTIME))
    parser.add_argument("--frontend-port", type=int, default=12042)
    args = parser.parse_args()
    site_runtime = Path(args.site_runtime).resolve()
    acceptance = Path(args.isolation_acceptance)
    gate = json.loads(acceptance.read_text(encoding="utf-8"))
    if gate.get("status") != "passed":
        raise ValueError("final browser MCP isolation acceptance is required")
    out = EXPERIMENT / "runs" / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    runtime, digest = provision_runtime()
    if gate.get("runtime_files_sha256"):
        for name, expected in gate["runtime_files_sha256"].items():
            actual = hashlib.sha256((ROOT / "harness/phase2" / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("isolation-relevant file changed after acceptance: " + name)
    readiness = json.loads((site_runtime / "readiness.management.json").read_text(encoding="utf-8"))
    if "ui_denominator" in readiness or "ui_verified" in readiness:
        counts = (readiness.get("ui_denominator"), readiness.get("ui_verified"))
    else:
        counts = (readiness.get("denominator"), readiness.get("checked_cases"),
                  readiness.get("verified_expected_endpoints"))
    if readiness.get("status") != "ready" or any(value != 30 for value in counts):
        raise ValueError("registered website acceptance not complete")
    reset = driver(["reset-learning", "--seed", str(args.seed)], runtime=site_runtime)
    write_new_json(out / "baseline-reset.json", reset)
    socket = LINUX_ROOT + "/" + args.run_id + ".sock"
    prompt = learner_prompt(args.condition, args.seed, args.pilot)
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    base, plan = fresh_session(args.run_id, runtime, condition=args.condition, seed=args.seed,
                               prompt=prompt, fixture_path=site_runtime / "public-fixture.json", socket=socket,
                               action_limit=100 if args.pilot else 300, time_limit=3600 if args.pilot else 7200)
    registration = {"run_id": args.run_id, "condition": args.condition, "seed": args.seed,
                    "kind": "pilot" if args.pilot else "formal_learning", "model": "gpt-6.1-sol",
                    "model_reasoning_effort": "high", "model_sampling_seed": None,
                    "runtime_sha256": digest, "runtime": runtime, "isolation_acceptance": str(acceptance),
                    "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "isolation_acceptance_sha256": hashlib.sha256(acceptance.read_bytes()).hexdigest(),
                    "site": readiness, "site_runtime": str(site_runtime), "frontend_port": args.frontend_port,
                    "time_started_ns": time.time_ns(), "plan": plan,
                    "model_handoffs": 1, "model_calls": None, "cost": None}
    write_new_json(out / "registration.json", registration)
    events = TrustedEvents(out / "trusted-gateway.jsonl", runtime=site_runtime)
    command = ["wsl", "-d", DISTRO, "--", "python3", runtime + "/relay.py", "linux",
               "--socket", socket, "--origin", "http://127.0.0.1:12042"]
    relay = FixedOriginRelay(command, "http://127.0.0.1:12042", "127.0.0.1", args.frontend_port,
                             out / "relay.stderr.txt", callback=events)
    started = time.monotonic()
    exit_code = None
    try:
        if not relay.ready.wait(20):
            raise RuntimeError("website relay unavailable")
        child_args = ["wsl", "-d", DISTRO, "--", "python3", runtime + "/launch_solar.py", "--plan", base + "/launch-plan.json"]
        with (out / "launcher.stdout.txt").open("xb") as stdout, (out / "launcher.stderr.txt").open("xb") as stderr:
            child = subprocess.Popen(child_args, stdout=stdout, stderr=stderr, creationflags=0x08000000)
            print(json.dumps({"event": "learning_started", "run_id": args.run_id, "pid": child.pid}), flush=True)
            while child.poll() is None:
                time.sleep(15)
                print(json.dumps({"event": "progress", "run_id": args.run_id, "elapsed_seconds": round(time.monotonic() - started),
                                  "trusted_http_events": events.count}), flush=True)
            exit_code = child.returncode
    finally:
        relay.close()
        events.close()
        export_tree(base + "/workspace", out / "workspace")
        export_tree(base + "/private", out / "private")
    barrier = management_barrier(out / "private", relay, events)
    write_new_json(out / "management-barrier.json", barrier)
    workspace = out / "workspace"
    checks = {"ready_file": (workspace / "READY.json").is_file(), "rules_valid": False,
              "required_files": False, "browser_exports_match_originals": False,
              "launcher_success": exit_code == 0, "relay_settled_without_errors": not relay.errors,
              "management_barrier": management_barrier_passed(barrier)}
    errors = []
    if checks["ready_file"]:
        try:
            ready = json.loads((workspace / "READY.json").read_text(encoding="utf-8"))
            revision = (workspace / ready["revision_directory"]).resolve()
            revision.relative_to(workspace.resolve())
            required = {"revision.json", "rulebook.md", "rules.json", "objects.json", "coverage.json", "scripts.py", "exploration.jsonl"}
            if args.condition == "A":
                required.add("behavior_model.py")
            checks["required_files"] = all((revision / name).is_file() for name in required)
            checks["condition_no_predictor"] = args.condition == "A" or not list(workspace.rglob("behavior_model.py"))
            rules = json.loads((revision / "rules.json").read_text(encoding="utf-8"))
            validate_rules(rules, workspace)
            checks["rules_valid"] = True
            evidence_check = validate_browser_exports(workspace, out / "private/browser", rules)
            checks["browser_exports_match_originals"] = True
            write_new_json(out / "browser-evidence-integrity.json", evidence_check)
        except Exception as error:
            errors.append(type(error).__name__ + ": " + str(error))
    summary = {"run_id": args.run_id, "exit_code": exit_code, "elapsed_seconds": time.monotonic() - started,
               "checks": checks, "management_barrier": barrier, "validation_errors": errors, "trusted_http_events": events.count,
               "relay_errors": relay.errors, "status": "learning_finished" if all(checks.values()) and not errors else "needs_artifact_review"}
    write_new_json(out / "learning-summary.json", summary)
    freeze_manifest(out, [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()], out / "learning-manifest.json")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
