"""Versioned management entry for the unchanged frozen-case browser protocol."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from . import run_evaluation as frozen
from .management import ROOT
from .records import sha256
from .report_v002 import schedule_runs


def events_type(ingest, expected_runtime):
    class ExpandedTrustedEvents(frozen.TrustedEvents):
        def __init__(self, destination, runtime):
            if Path(runtime).resolve() != expected_runtime:
                raise ValueError("event ingest runtime differs from worker assignment")
            self.ingest = ingest
            self.destination = Path(destination)
            self.file = self.destination.open("x", encoding="utf-8")
            self.lock = threading.Lock()
            self.count = 0
    return ExpandedTrustedEvents


def verify_registration(path):
    path = Path(path).resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("kind") != "expanded_frozen_evaluation_dispatch" or value.get("schema_version") != 1:
        raise ValueError("unrecognized expansion registration")
    required = {"harness/phase2/run_expanded_case_v001.py", "harness/phase2/run_parallel_v001.py",
                value["driver_entry"], value["protocol_path"]}
    paths = [item["path"] for item in value["management_inputs"]]
    if len(paths) != len(set(paths)) or not required.issubset(paths):
        raise ValueError("actual management entry points must be uniquely hash-bound")
    for item in value["management_inputs"]:
        target = (ROOT / item["path"]).resolve(strict=True)
        target.relative_to(ROOT.resolve())
        if sha256(target) != item["sha256"]:
            raise ValueError("expansion management input changed: " + item["path"])
    for item in value["admission_records"]:
        target = (ROOT / item["path"]).resolve(strict=True)
        target.relative_to(ROOT.resolve())
        if sha256(target) != item["sha256"]:
            raise ValueError("expansion admission evidence changed")
        record = json.loads(target.read_text(encoding="utf-8"))
        if record.get("status") not in {"passed", "ready"}:
            raise ValueError("expansion admission has not passed")
    if not value["admission_records"]:
        raise ValueError("independent expansion admission is required")
    if (type(value.get("max_active_workers")) is not int
            or not 1 <= value["max_active_workers"] <= min(12, len(value["workers"]))
            or value.get("case_denominator") != 180):
        raise ValueError("registered expansion ceiling/denominator differs")
    if value.get("model") != "gpt-6.1-sol" or value.get("reasoning_effort") != "high":
        raise ValueError("frozen model configuration differs")
    schedule_path = frozen.EXPERIMENT / "FORMAL_SCHEDULE.json"
    if sha256(schedule_path) != value["formal_schedule_sha256"]:
        raise ValueError("formal schedule differs from expansion parent")
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    expected = {condition.lower() + "-seed-" + str(worker["seed"])
                for worker, condition in schedule_runs(schedule)}
    if len(value["learning_run_ids"]) != 6 or set(value["learning_run_ids"]) != expected:
        raise ValueError("expansion learning identities differ from the fixed six")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expansion-registration", required=True)
    parser.add_argument("--learning-run", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--case-index", required=True, type=int)
    args = parser.parse_args()
    registration = verify_registration(args.expansion_registration)
    worker = next(row for row in registration["workers"] if row["id"] == args.worker)
    entry = (ROOT / registration["driver_entry"]).resolve(strict=True)
    runtime = Path(worker["runtime"]).resolve(strict=True)
    if args.learning_run not in registration["learning_run_ids"] or not 1 <= args.case_index <= 30:
        raise ValueError("case is outside the registered 180")

    def expanded_driver(target_runtime, arguments):
        if Path(target_runtime).resolve() != runtime:
            raise ValueError("driver runtime differs from worker assignment")
        env = os.environ.copy()
        env["BM_DISCOGS_PHASE2_RUNTIME"] = str(runtime)
        result = subprocess.run([sys.executable, str(entry), "--runtime", str(runtime), *arguments],
                                env=env, capture_output=True, text=True, encoding="utf-8",
                                timeout=120, creationflags=0x08000000)
        if result.returncode:
            raise RuntimeError(result.stderr[-5000:])
        return json.loads(result.stdout)

    print(json.dumps({"event": "expanded_management_entry", "worker": args.worker,
                      "learning_run": args.learning_run, "case_index": args.case_index,
                      "expansion_registration_sha256": sha256(Path(args.expansion_registration)),
                      "runner_sha256": sha256(Path(__file__)), "driver_entry_sha256": sha256(entry)}), flush=True)
    from harness.sites.discogs.phase2_private.scale_v001 import management as expanded_management
    if Path(expanded_management.__file__).resolve() != entry:
        raise ValueError("event loader differs from registered management entry")
    evaluator = expanded_management.evaluator(runtime)
    frozen.driver = expanded_driver
    frozen.TrustedEvents = events_type(evaluator.ingest_http, runtime)
    sys.argv = [str(Path(__file__)), "--learning-run", args.learning_run,
                "--runtime", str(runtime), "--frontend-port", str(worker["frontend_port"]),
                "--evaluation-acceptance", str(ROOT / registration["evaluation_acceptance"]),
                "--case-index", str(args.case_index)]
    frozen.main()


if __name__ == "__main__":
    main()
