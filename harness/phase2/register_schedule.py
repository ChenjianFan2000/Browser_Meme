"""Freeze management inputs before the first formal learner is started."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .management import ROOT, provision_runtime
from .records import sha256, write_new_json
from .run_learning import EXPERIMENT


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checked_gate(path):
    path = Path(path).resolve(strict=True)
    gate = read_json(path)
    if gate.get("status") != "passed" or not gate.get("runtime_files_sha256"):
        raise ValueError("passed isolation gate with code hashes is required")
    for name, expected in gate["runtime_files_sha256"].items():
        if sha256(ROOT / "harness/phase2" / name) != expected:
            raise ValueError("isolation code changed since acceptance: " + name)
    for name, expected in gate.get("coordinator_files_sha256", {}).items():
        if sha256(ROOT / "harness/phase2" / name) != expected:
            raise ValueError("management code changed since acceptance: " + name)
    for name, expected in gate.get("support_files_sha256", {}).items():
        if sha256(ROOT / name) != expected:
            raise ValueError("isolation support code changed since acceptance: " + name)
    for reference in gate.get("evidence", []):
        if sha256(ROOT / reference["path"]) != reference["sha256"]:
            raise ValueError("isolation evidence changed since acceptance")
    return str(path), sha256(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning-gate", required=True)
    parser.add_argument("--evaluation-gate", required=True)
    args = parser.parse_args()
    if (EXPERIMENT / "FORMAL_SCHEDULE.json").exists():
        raise ValueError("formal schedule is already frozen")
    learning_gate, learning_hash = checked_gate(args.learning_gate)
    evaluation_gate, evaluation_hash = checked_gate(args.evaluation_gate)
    pilot = EXPERIMENT / "pilot-review-001.json"
    if read_json(pilot).get("status") != "passed":
        raise ValueError("pilot review must pass before formal registration")
    workers, readiness_files = [], []
    for identifier, seed, port, conditions in (
        ("a", 1729, 13042, ["A", "B"]),
        ("b", 2718, 14042, ["B", "A"]),
        ("c", 3141, 15042, ["A", "B"]),
    ):
        runtime = ROOT / (".runtime/phase2-eval-worker-" + identifier)
        readiness_path = runtime / "readiness.management.json"
        readiness = read_json(readiness_path)
        if readiness.get("status") != "ready" or any(readiness.get(key) != 30 for key in (
            "ui_denominator", "ui_verified", "side_effect_checks_passed"
        )):
            raise ValueError("worker acceptance incomplete: " + identifier)
        if readiness["frontend_port"] != port or not readiness["learning_state_reset"]:
            raise ValueError("worker registration differs from the accepted deployment")
        for condition in conditions:
            run_id = condition.lower() + "-seed-" + str(seed)
            if (EXPERIMENT / "runs" / run_id).exists():
                raise ValueError("formal learning began before schedule freezing: " + run_id)
        workers.append({"id": identifier, "runtime": str(runtime), "frontend_port": port,
                        "seed": seed, "conditions": conditions,
                        "readiness_path": str(readiness_path), "readiness_sha256": sha256(readiness_path),
                        "accepted_environment": readiness})
        readiness_files.append(readiness_path)
    for key in ("source_manifest_sha256", "build_manifest_sha256", "inventory_sha256", "baseline_sha256"):
        if len({worker["accepted_environment"][key] for worker in workers}) != 1:
            raise ValueError("worker initial environment mismatch: " + key)
    # Provision once here so parallel controller startups cannot race to create it.
    runtime, runtime_hash = provision_runtime()
    files = [*EXPERIMENT.glob("PROTOCOL*.md"), *EXPERIMENT.glob("environment-check-*.json"),
             pilot, Path(learning_gate), Path(evaluation_gate), *readiness_files]
    for directory in (ROOT / "harness/phase2", ROOT / "harness/phase2_isolation", ROOT / "harness/sites/discogs/phase2_private"):
        files.extend(path for path in directory.rglob("*") if path.is_file() and path.suffix in {".py", ".md", ".json"} and "__pycache__" not in path.parts)
    input_hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in sorted(set(files))}
    snapshot = EXPERIMENT / "formal-inputs-001.json"
    write_new_json(snapshot, {"kind": "pre_formal_management_input_hashes", "registered_ns": time.time_ns(), "files": input_hashes,
                              "private_materials_are_hashed_only_and_not_learner_inputs": True})
    schedule = {"protocol": "phase2-discogs-20261021-01", "registered_ns": time.time_ns(),
                "learning_acceptance": learning_gate, "learning_acceptance_sha256": learning_hash,
                "evaluation_acceptance": evaluation_gate, "evaluation_acceptance_sha256": evaluation_hash,
                "input_manifest": str(snapshot), "input_manifest_sha256": sha256(snapshot),
                "runtime": runtime, "runtime_sha256": runtime_hash,
                "model": "gpt-6.1-sol", "reasoning_effort": "high", "model_sampling_seed": None,
                "learning_runs": 6, "cases_per_learning_run": 30, "case_denominator": 180,
                "learning_limits": {"ui_actions": 300, "browser_executions": 40, "seconds": 7200},
                "evaluation_limits": {"ui_actions": 60, "browser_executions": 20, "seconds": 900},
                "all_learning_frozen_before_private_testing": True, "max_active_workers": 3,
                "external_decorative_images": "uncached_external_requests_denied_equally_in_both_conditions",
                "workers": workers}
    destination = EXPERIMENT / "FORMAL_SCHEDULE.json"
    write_new_json(destination, schedule)
    print(json.dumps({"status": "registered", "schedule": str(destination), "sha256": sha256(destination),
                      "input_files": len(input_hashes), "runtime": runtime}))


if __name__ == "__main__":
    main()
