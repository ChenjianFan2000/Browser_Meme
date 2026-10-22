"""Review frozen learner structures and original evidence, without website semantics."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .call_records import browser_call_records
from .records import (sha256, validate_rules, validate_prediction,
                      validate_browser_exports, verify_manifest, write_new_json)
from .run_learning import EXPERIMENT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def review_run(run_id):
    root = EXPERIMENT / "runs" / run_id
    registration = read(root / "registration.json")
    manifest_path = root / "learning-manifest.json"
    if verify_manifest(root, read(manifest_path)["files"]):
        raise ValueError("frozen learning hash mismatch: " + run_id)
    workspace = root / "workspace"
    ready = read(workspace / "READY.json")
    revision = (workspace / ready["revision_directory"]).resolve()
    revision.relative_to(workspace.resolve())
    rules = read(revision / "rules.json")
    validate_rules(rules, workspace)
    exports = validate_browser_exports(workspace, root / "private/browser", rules)
    before, after = 0, 0
    for path in sorted((root / "private/browser").glob("call-*/evidence/actions.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["kind"] == "action_before":
                validate_prediction(event["prediction"])
                before += 1
            elif event["kind"] == "action_after":
                after += 1
    syntax_files = ["scripts.py"]
    if registration["condition"] == "A":
        syntax_files.append("behavior_model.py")
    for name in syntax_files:
        compile((revision / name).read_text(encoding="utf-8"), name, "exec")
    launch = read(root / "private/solar/launch-result.json")
    calls = browser_call_records(root / "private/browser")
    return {"run_id": run_id, "condition": registration["condition"], "seed": registration["seed"],
            "learning_manifest_sha256": sha256(manifest_path),
            "formal_learning": registration["kind"] == "formal_learning",
            "artifact_integrity_passed": True, "trusted_evidence": exports,
            "model_exit_code": launch["exit_code"], "model_timeout": launch["timeout"],
            "model_elapsed_seconds": launch["elapsed_seconds"], "usage_events": launch.get("usage_events"),
            "actions_with_valid_pre_action_prediction": before, "action_after_records": after,
            "ui_actions_reported_by_executor": sum(value["actions"] for value in calls),
            "browser_executions": len(calls), "action_evidence_complete": before == after,
            "browser_failures": sum(bool(value["result"].get("error")) for value in calls),
            "incomplete_management_calls": sum(not value["management_completed"] for value in calls),
            "learner_declared_rule_status_counts": dict(Counter(rule["status"] for rule in rules)),
            "rule_count": len(rules), "frozen_revision": ready["revision_directory"],
            "stop_reason": ready["stop_reason"], "limitations": ready.get("limitations", []),
            "syntax_checked": syntax_files, "semantic_correctness": "not_established_by_this_structural_review",
            "model_calls": None, "cost": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-id", required=True)
    args = parser.parse_args()
    schedule = read(EXPERIMENT / "FORMAL_SCHEDULE.json")
    rows = [review_run(condition.lower() + "-seed-" + str(worker["seed"]))
            for worker in schedule["workers"] for condition in worker["conditions"]]
    value = {"kind": "frozen_learning_structure_and_original_evidence_review", "runs": rows,
             "semantic_correctness": "requires_independent_evaluation", "denominator": 6}
    destination = EXPERIMENT / "reviews" / (args.review_id + ".json")
    write_new_json(destination, value)
    print(json.dumps({"review": str(destination), "runs": len(rows), "ui_actions": sum(row["actions_with_valid_pre_action_prediction"] for row in rows)}))


if __name__ == "__main__":
    main()
