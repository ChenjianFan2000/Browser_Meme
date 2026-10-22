"""Fixed-denominator management reporting; no target-site truth is inferred here."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .records import sha256, verify_manifest, write_new_json
from .run_learning import EXPERIMENT

PREDICTION_FIELDS = ("disposition", "persistent_state_changed", "affected_record_count")
GRADES = ("correct", "incorrect", "unknown", "unscorable")
TASK_STATES = ("passed", "failed", "unable_to_confirm", "not_run", "infrastructure_error", "unsafe_reset")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def case_row(index, summary=None, *, partial=False):
    row = {"case_index": index, "task_status": "infrastructure_error" if partial else "not_run",
           "prediction_grades": {key: "unknown" for key in PREDICTION_FIELDS},
           "business_disposition": "unknown", "transport_disposition": "unknown",
           "side_effects_ok": None, "prediction_provenance": "not_declared", "ui_actions": 0,
           "browser_executions": 0, "elapsed_seconds": None, "usage_events": None}
    if summary is None:
        return row
    evaluation = summary["independent_evaluation"]
    outcome = evaluation["task_outcome"]
    if outcome not in {"passed", "failed", "unable_to_confirm"}:
        raise ValueError("unexpected independent task outcome")
    grades = evaluation["prediction_grading"]
    if set(grades) != set(PREDICTION_FIELDS) or any(value not in GRADES for value in grades.values()):
        raise ValueError("independent predictor grading must have the registered three fields")
    safe = summary.get("safe_to_reset") is True
    row.update({"case_id": summary["case_id"], "task_status": outcome if safe else "unsafe_reset",
                "prediction_grades": grades if safe else {key: "unknown" if grades[key] == "unknown" else "unscorable" for key in PREDICTION_FIELDS},
                "business_disposition": evaluation["business_disposition"] if safe else "unknown",
                "transport_disposition": evaluation["transport_disposition"],
                "side_effects_ok": evaluation["side_effects_ok"] if safe else None,
                "prediction_provenance": (summary.get("prediction_provenance") or {}).get("status", "not_declared"),
                "ui_actions": summary["ui_actions"], "browser_executions": summary["browser_executions"],
                "elapsed_seconds": summary["elapsed_seconds"], "usage_events": summary.get("usage_events"),
                "model_cli_exit_code": summary.get("model_cli_exit_code"),
                "model_cli_timeout": summary.get("model_cli_timeout"), "safe_to_reset": safe,
                "ui_claims_unscorable": len(evaluation.get("ui_claims_grading", []))})
    if not safe:
        row["provisional_independent_outcome"] = outcome
        row["provisional_prediction_grades"] = grades
    return row


def aggregate(rows):
    if not rows:
        raise ValueError("fixed case denominator cannot be empty")
    tasks = Counter({key: 0 for key in TASK_STATES})
    grades = Counter({key: 0 for key in GRADES})
    by_field = {key: Counter({grade: 0 for grade in GRADES}) for key in PREDICTION_FIELDS}
    usage, usage_records = Counter(), 0
    for row in rows:
        tasks[row["task_status"]] += 1
        for field, grade in row["prediction_grades"].items():
            grades[grade] += 1
            by_field[field][grade] += 1
        for event in row.get("usage_events") or []:
            usage_records += 1
            for key, value in event.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    usage[key] += value
    actions = sum(row["ui_actions"] for row in rows)
    known = grades["correct"] + grades["incorrect"]
    denominator = len(rows) * len(PREDICTION_FIELDS)
    return {"case_denominator": len(rows), "prediction_field_denominator": denominator,
            "task_counts": dict(tasks), "prediction_counts": dict(grades),
            "prediction_counts_by_field": {key: dict(value) for key, value in by_field.items()},
            "task_pass_rate_fixed_denominator": tasks["passed"] / len(rows) if actions else None,
            "prediction_correct_rate_fixed_denominator": grades["correct"] / denominator if actions else None,
            "prediction_coverage": known / denominator if actions else None,
            "prediction_accuracy_on_scorable_fields": grades["correct"] / known if known else None,
            "measurement_status": "measured" if actions else "not_started",
            "business_disposition_counts": dict(Counter(row["business_disposition"] for row in rows)),
            "transport_disposition_counts": dict(Counter(row["transport_disposition"] for row in rows)),
            "side_effect_counts": {"passed": sum(row["side_effects_ok"] is True for row in rows),
                                   "failed": sum(row["side_effects_ok"] is False for row in rows),
                                   "unknown": sum(row["side_effects_ok"] is None for row in rows)},
            "prediction_provenance_counts": dict(Counter(row["prediction_provenance"] for row in rows)),
            "ui_actions": actions, "browser_executions": sum(row["browser_executions"] for row in rows),
            "sum_case_elapsed_seconds": sum(row["elapsed_seconds"] or 0 for row in rows),
            "actual_cli_usage": dict(usage) if usage_records else None, "usage_records": usage_records,
            "model_calls": None, "cost": None}


def collect_run(worker, condition):
    run_id = condition.lower() + "-seed-" + str(worker["seed"])
    rows, case_files = [], {}
    for index in range(1, 31):
        directory = EXPERIMENT / "evaluations" / run_id / f"case-{index:02d}"
        manifest = directory / "case-manifest.json"
        summary = directory / "case-summary.json"
        if not manifest.exists():
            rows.append(case_row(index, partial=directory.exists()))
            continue
        if verify_manifest(directory, read(manifest)["files"]):
            raise ValueError("case manifest mismatch: " + str(directory))
        value = read(summary)
        if value["learning_run"] != run_id or value["condition"] != condition or value["case_index"] != index:
            raise ValueError("case identity mismatch")
        case_files[str(summary.relative_to(EXPERIMENT)).replace("\\", "/")] = sha256(summary)
        rows.append(case_row(index, value))
    ids = [row["case_id"] for row in rows if row.get("case_id")]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case identity in fixed denominator")
    return {"run_id": run_id, "condition": condition, "seed": worker["seed"],
            "summary": aggregate(rows), "cases": rows, "case_summary_hashes": case_files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-id", required=True)
    args = parser.parse_args()
    schedule = read(EXPERIMENT / "FORMAL_SCHEDULE.json")
    runs = [collect_run(worker, condition) for worker in schedule["workers"] for condition in worker["conditions"]]
    groups = {condition: aggregate([row for run in runs if run["condition"] == condition for row in run["cases"]]) for condition in ("A", "B")}
    result = {"protocol": schedule["protocol"], "kind": "fixed_frozen_evaluation_aggregation",
              "runs": runs, "conditions": groups,
              "overall": aggregate([row for run in runs for row in run["cases"]]),
              "schedule_sha256": sha256(EXPERIMENT / "FORMAL_SCHEDULE.json"),
              "coverage_and_novelty": "require_separate_independent_review",
              "official_benchmark": False, "strict_speed_comparison": False}
    destination = EXPERIMENT / "reports" / (args.report_id + ".json")
    write_new_json(destination, result)
    print(json.dumps({"report": str(destination), "overall": result["overall"]}))


if __name__ == "__main__":
    main()
