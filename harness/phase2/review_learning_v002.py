"""Review frozen learner structures and original evidence, without website semantics."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .report_v002 import checked_manifest, schedule_runs
from .run_learning import management_barrier_passed
from .records import (sha256, validate_rules, validate_prediction,
                      validate_browser_exports, verify_manifest, write_new_json)
from .run_learning import EXPERIMENT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def parsed_rows(path):
    if not path.exists():
        return [], 0
    rows, malformed = [], 0
    for raw_line in path.read_bytes().splitlines():
        try:
            value = json.loads(raw_line.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("event must be an object")
            rows.append(value)
        except ValueError:
            malformed += 1
    return rows, malformed


def audit_actions(private_browser):
    journal, malformed_broker = parsed_rows(private_browser / "broker.jsonl")
    names = {row["call"] for row in journal if row.get("event") == "dispatch" and isinstance(row.get("call"), str)}
    dispatched = set(names)
    names |= {path.name for path in private_browser.glob("call-*") if path.is_dir()}
    calls = []
    for name in sorted(names):
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("invalid management call name")
        directory = private_browser / name
        action_path = directory / "evidence/actions.jsonl"
        rows, malformed = parsed_rows(action_path)
        before = sum(row.get("kind") == "action_before" for row in rows)
        after = sum(row.get("kind") == "action_after" for row in rows)
        valid, invalid_predictions = 0, 0
        for row in rows:
            if row.get("kind") == "action_before":
                try:
                    if not isinstance(row.get("prediction"), dict):
                        raise ValueError("prediction must be an object")
                    validate_prediction(row["prediction"])
                    valid += 1
                except (ValueError, TypeError, KeyError):
                    invalid_predictions += 1
        result, management_completed, malformed_results = None, False, 0
        for file, managed in [(directory / "management-result.json", True), (directory / "evidence/result.json", False)]:
            if not file.exists():
                continue
            try:
                value = read(file)
                candidate = value["result"] if managed else value
                if not isinstance(candidate, dict):
                    raise ValueError("result must be an object")
                result, management_completed = candidate, managed
                break
            except (ValueError, TypeError, KeyError):
                malformed_results += 1
        result = result or {"error": "execution_completion_missing", "actions": before}
        reported = result.get("actions")
        invalid_counter = isinstance(reported, bool) or not isinstance(reported, int) or reported < 0
        if invalid_counter:
            reported = before
        complete = (name in dispatched and action_path.is_file() and not malformed and not malformed_results and not malformed_broker
                    and not invalid_counter and not invalid_predictions and management_completed
                    and before == after == reported)
        calls.append({"call": name, "dispatched": name in dispatched, "actions": reported, "actions_before": before, "actions_after": after,
                      "valid_predictions": valid, "invalid_predictions": invalid_predictions,
                      "management_completed": management_completed, "result": result,
                      "malformed_action_lines": malformed, "malformed_result_files": malformed_results,
                      "missing_action_log": not action_path.is_file(),
                      "missing_before_records": max(reported - before, 0),
                      "missing_after_records": max(reported - after, 0), "evidence_complete": complete})
    return {"calls": calls, "malformed_broker_lines": malformed_broker,
            "missing_broker_log": not (private_browser / "broker.jsonl").is_file(),
            "action_evidence_complete": bool(calls) and not malformed_broker and all(call["evidence_complete"] for call in calls)}


def review_run(run_id, *, experiment=EXPERIMENT):
    root = experiment / "runs" / run_id
    manifest_path = root / "learning-manifest.json"
    manifest_files, manifest_digest = checked_manifest(root, "learning-manifest.json", {
        "registration.json", "learning-summary.json", "workspace/READY.json", "private/solar/launch-result.json"})
    registration = read(root / "registration.json")
    summary = read(root / "learning-summary.json")
    workspace = root / "workspace"
    ready = read(workspace / "READY.json")
    revision = (workspace / ready["revision_directory"]).resolve()
    revision.relative_to(workspace.resolve())
    for path in revision.rglob("*"):
        if path.is_symlink() or (path.is_file() and path.relative_to(root).as_posix() not in manifest_files):
            raise ValueError("revision artifact missing from frozen manifest")
    rules = read(revision / "rules.json")
    validate_rules(rules, workspace)
    exports = validate_browser_exports(workspace, root / "private/browser", rules)
    audit = audit_actions(root / "private/browser")
    calls = audit["calls"]
    before = sum(call["valid_predictions"] for call in calls)
    after = sum(call["actions_after"] for call in calls)
    syntax_files = ["scripts.py"]
    if registration["condition"] == "A":
        syntax_files.append("behavior_model.py")
    for name in syntax_files:
        compile((revision / name).read_text(encoding="utf-8"), name, "exec")
    launch = read(root / "private/solar/launch-result.json")
    complete = (registration.get("kind") == "formal_learning" and registration.get("run_id") == run_id
                and run_id == str(registration.get("condition", "")).lower() + "-seed-" + str(registration.get("seed"))
                and summary.get("status") == "learning_finished" and management_barrier_passed(summary.get("management_barrier"))
                and launch.get("exit_code") == 0 and launch.get("timeout") is False
                )
    return {"status": "review_complete", "admission_checks_passed": complete, "run_id": run_id, "condition": registration["condition"], "seed": registration["seed"],
            "learning_manifest_sha256": manifest_digest,
            "registration_sha256": sha256(root / "registration.json"),
            "learning_summary_sha256": sha256(root / "learning-summary.json"),
            "ready_sha256": sha256(workspace / "READY.json"),
            "formal_learning": registration["kind"] == "formal_learning",
            "artifact_integrity_passed": True, "trusted_evidence": exports,
            "model_exit_code": launch["exit_code"], "model_timeout": launch["timeout"],
            "model_elapsed_seconds": launch["elapsed_seconds"], "usage_events": launch.get("usage_events"),
            "actions_with_valid_pre_action_prediction": before, "action_after_records": after,
            "ui_actions_reported_by_executor": sum(value["actions"] for value in calls),
            "browser_executions": len(calls), "action_evidence_complete": audit["action_evidence_complete"],
            "action_log_audit": audit,
            "malformed_action_lines": sum(call["malformed_action_lines"] for call in calls),
            "missing_action_before_records": sum(call["missing_before_records"] for call in calls),
            "missing_action_after_records": sum(call["missing_after_records"] for call in calls),
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
    schedule_path = EXPERIMENT / "FORMAL_SCHEDULE.json"
    schedule = read(schedule_path)
    rows = [review_run(condition.lower() + "-seed-" + str(worker["seed"]))
            for worker, condition in schedule_runs(schedule)]
    value = {"schema_version": 2, "status": "review_complete",
             "admission_checks_passed": all(row["admission_checks_passed"] for row in rows),
             "formal_schedule_sha256": sha256(schedule_path), "kind": "frozen_learning_structure_and_original_evidence_review", "runs": rows,
             "semantic_correctness": "requires_independent_evaluation", "denominator": 6}
    destination = EXPERIMENT / "reviews" / (args.review_id + ".json")
    write_new_json(destination, value)
    print(json.dumps({"review": str(destination), "runs": len(rows), "ui_actions": sum(row["actions_with_valid_pre_action_prediction"] for row in rows)}))


if __name__ == "__main__":
    main()
