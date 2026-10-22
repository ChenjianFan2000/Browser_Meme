"""Three independent worker schedules; learning completes before private testing."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time

from .management import ROOT
from .records import write_new_json, verify_manifest
from .run_learning import EXPERIMENT, management_barrier_passed


def command_run(command, log, *, label):
    with log.open("xb") as stdout, log.with_suffix(".stderr.txt").open("xb") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=ROOT, creationflags=0x08000000)
        print(json.dumps({"event": "schedule_process_started", "label": label, "pid": child.pid}), flush=True)
        code = child.wait()
    result = {"label": label, "exit_code": code, "log": str(log)}
    print(json.dumps({"event": "schedule_process_finished", **result}), flush=True)
    return result


def verify_frozen_learning(worker, condition):
    run_id = condition.lower() + "-seed-" + str(worker["seed"])
    output = EXPERIMENT / "runs" / run_id
    manifest = json.loads((output / "learning-manifest.json").read_text(encoding="utf-8"))
    if verify_manifest(output, manifest["files"]):
        raise ValueError("frozen learning integrity failure: " + run_id)
    summary = json.loads((output / "learning-summary.json").read_text(encoding="utf-8"))
    registration = json.loads((output / "registration.json").read_text(encoding="utf-8"))
    expected = {"run_id": run_id, "condition": condition, "seed": worker["seed"],
                "kind": "formal_learning", "frontend_port": worker["frontend_port"]}
    if (summary.get("status") != "learning_finished"
            or not management_barrier_passed(summary.get("management_barrier")) or any(
            registration.get(key) != value for key, value in expected.items())):
        raise ValueError("frozen learning registration/status mismatch: " + run_id)
    if Path(registration["site_runtime"]).resolve() != Path(worker["runtime"]).resolve():
        raise ValueError("frozen learning worker runtime mismatch: " + run_id)


def learning_worker(worker, schedule, logs):
    outcomes = []
    for condition in worker["conditions"]:
        run_id = condition.lower() + "-seed-" + str(worker["seed"])
        output = EXPERIMENT / "runs" / run_id
        if output.exists():
            manifest = output / "learning-manifest.json"
            summary = output / "learning-summary.json"
            if not manifest.exists() or not summary.exists():
                raise ValueError("partial learning run needs explicit recovery: " + run_id)
            if verify_manifest(output, json.loads(manifest.read_text(encoding="utf-8"))["files"]):
                raise ValueError("frozen learning integrity failure: " + run_id)
            if json.loads(summary.read_text(encoding="utf-8"))["status"] != "learning_finished":
                raise ValueError("learning artifact review required: " + run_id)
            verify_frozen_learning(worker, condition)
            outcomes.append({"label": run_id, "status": "preserved_frozen_run"})
            continue
        command = [sys.executable, "-m", "harness.phase2.run_learning", "--run-id", run_id,
                   "--condition", condition, "--seed", str(worker["seed"]),
                   "--isolation-acceptance", schedule["learning_acceptance"],
                   "--site-runtime", worker["runtime"], "--frontend-port", str(worker["frontend_port"])]
        outcome = command_run(command, logs / (run_id + ".stdout.txt"), label=run_id)
        outcomes.append(outcome)
        summary = output / "learning-summary.json"
        if outcome["exit_code"] or not summary.exists() or json.loads(summary.read_text(encoding="utf-8"))["status"] != "learning_finished":
            raise RuntimeError("learning needs review before continuing: " + run_id)
    return {"worker": worker["id"], "outcomes": outcomes}


def evaluation_worker(worker, schedule, logs):
    outcomes = []
    for condition in worker["conditions"]:
        run_id = condition.lower() + "-seed-" + str(worker["seed"])
        command = [sys.executable, "-m", "harness.phase2.run_evaluation", "--learning-run", run_id,
                   "--runtime", worker["runtime"], "--frontend-port", str(worker["frontend_port"]),
                   "--evaluation-acceptance", schedule["evaluation_acceptance"]]
        outcome = command_run(command, logs / ("evaluation-" + run_id + ".stdout.txt"), label="evaluation-" + run_id)
        outcomes.append(outcome)
        if outcome["exit_code"]:
            raise RuntimeError("case evaluation needs recovery: " + run_id)
    return {"worker": worker["id"], "outcomes": outcomes}


def stage(function, workers, schedule, logs):
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = {pool.submit(function, worker, schedule, logs): worker["id"] for worker in workers}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as error:
                failures.append({"worker": futures[future], "error": type(error).__name__ + ": " + str(error)})
    return {"results": results, "failures": failures}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--stage", choices=["learning", "evaluation", "all"], default="all")
    args = parser.parse_args()
    schedule = json.loads(Path(args.schedule).read_text(encoding="utf-8"))
    workers = schedule["workers"]
    if len(workers) != 3 or len({worker["runtime"] for worker in workers}) != 3:
        raise ValueError("exactly three distinct worker runtimes required")
    if len({Path(worker["runtime"]).resolve() for worker in workers}) != 3:
        raise ValueError("worker runtime paths alias one another")
    if len({worker["frontend_port"] for worker in workers}) != 3 or len({worker["id"] for worker in workers}) != 3:
        raise ValueError("worker IDs and frontend ports must be distinct")
    if {worker["seed"] for worker in workers} != {1729, 2718, 3141}:
        raise ValueError("registered seed set differs")
    if any(set(worker["conditions"]) != {"A", "B"} or len(worker["conditions"]) != 2 for worker in workers):
        raise ValueError("each worker must pair A and B once")
    logs = EXPERIMENT / "batches" / args.batch_id
    logs.mkdir(parents=True, exist_ok=False)
    write_new_json(logs / "schedule.json", schedule)
    summary = {"started_ns": time.time_ns(), "batch_id": args.batch_id}
    if args.stage in {"learning", "all"}:
        summary["learning"] = stage(learning_worker, workers, schedule, logs)
        write_new_json(logs / "learning-stage.json", summary["learning"])
        if summary["learning"]["failures"]:
            write_new_json(logs / "batch-summary.json", summary)
            raise SystemExit("learning review is required; no private evaluations dispatched")
    if args.stage in {"evaluation", "all"}:
        # A global barrier also applies to evaluation-only invocations.
        for worker in workers:
            for condition in worker["conditions"]:
                verify_frozen_learning(worker, condition)
        summary["evaluation"] = stage(evaluation_worker, workers, schedule, logs)
        write_new_json(logs / "evaluation-stage.json", summary["evaluation"])
    summary["finished_ns"] = time.time_ns()
    write_new_json(logs / "batch-summary.json", summary)
    print(json.dumps(summary), flush=True)
    if summary.get("evaluation", {}).get("failures"):
        raise SystemExit("evaluation failures require explicit recovery")


if __name__ == "__main__":
    main()
