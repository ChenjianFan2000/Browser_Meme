"""Versioned management-only reporting; immutable experiment inputs are untouched."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
from . import report as previous
from .records import sha256, verify_manifest, write_new_json
from .run_learning import EXPERIMENT

read = previous.read
PREDICTION_FIELDS = previous.PREDICTION_FIELDS


def checked_manifest(directory, filename, required):
    path = directory / filename
    value = read(path)
    files = value.get("files")
    if not isinstance(files, dict) or not files or not set(required).issubset(files):
        raise ValueError("nonempty manifest must cover required records: " + str(path))
    if verify_manifest(directory, files):
        raise ValueError("frozen manifest mismatch: " + str(path))
    return files, sha256(path)


def schedule_runs(schedule):
    workers = schedule["workers"]
    if len(workers) != 3 or len({worker["seed"] for worker in workers}) != 3:
        raise ValueError("fixed design requires three distinct seeds")
    if any(len(worker["conditions"]) != 2 or set(worker["conditions"]) != {"A", "B"} for worker in workers):
        raise ValueError("each seed requires exactly A and B")
    return [(worker, condition) for worker in workers for condition in worker["conditions"]]


def case_row(index, summary=None, *, partial=False):
    row = previous.case_row(index, summary, partial=partial)
    row["evaluation_recorded"] = summary is not None
    row["browser_actions_observed"] = row["ui_actions"] > 0
    return row


def aggregate(rows):
    result = previous.aggregate(rows)
    archived = [row for row in rows if row.get("evaluation_recorded")]
    actions = result["ui_actions"]
    result.update({"archived_evaluation_count": len(archived),
                   "archived_zero_ui_action_count": sum(row["ui_actions"] == 0 for row in archived),
                   "browser_actions_measured": actions > 0,
                   "measurement_status": ("measured" if actions else "evaluation_recorded_no_ui_actions") if archived else "not_started",
                   "model_cli_exit_counts": dict(Counter(str(row.get("model_cli_exit_code")) for row in archived)),
                   "model_cli_timeout_counts": {"true": sum(row.get("model_cli_timeout") is True for row in archived),
                                                "false": sum(row.get("model_cli_timeout") is False for row in archived),
                                                "unknown": sum(row.get("model_cli_timeout") is not True and row.get("model_cli_timeout") is not False for row in archived)}})
    if archived:
        result["task_pass_rate_fixed_denominator"] = result["task_counts"]["passed"] / len(rows)
        result["prediction_correct_rate_fixed_denominator"] = result["prediction_counts"]["correct"] / result["prediction_field_denominator"]
        known = result["prediction_counts"]["correct"] + result["prediction_counts"]["incorrect"]
        result["prediction_coverage"] = known / result["prediction_field_denominator"]
    return result


def collect_run(worker, condition, *, experiment=EXPERIMENT):
    run_id = condition.lower() + "-seed-" + str(worker["seed"])
    rows, summaries, manifests = [], {}, {}
    for index in range(1, 31):
        directory = experiment / "evaluations" / run_id / f"case-{index:02d}"
        if not (directory / "case-manifest.json").exists():
            rows.append(case_row(index, partial=directory.exists()))
            continue
        _, digest = checked_manifest(directory, "case-manifest.json", {"case-summary.json", "registration.json"})
        value, registration = read(directory / "case-summary.json"), read(directory / "registration.json")
        expected = {"learning_run": run_id, "condition": condition, "case_index": index}
        if any(value.get(key) != wanted for key, wanted in expected.items()):
            raise ValueError("case summary identity mismatch")
        if any(registration.get(key) != wanted for key, wanted in {
                "learning_run": run_id, "condition": condition, "index": index, "case_id": value["case_id"]}.items()):
            raise ValueError("case registration identity mismatch")
        summaries[(directory / "case-summary.json").relative_to(experiment).as_posix()] = sha256(directory / "case-summary.json")
        manifests[(directory / "case-manifest.json").relative_to(experiment).as_posix()] = digest
        rows.append(case_row(index, value))
    ids = [row["case_id"] for row in rows if row.get("case_id")]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case identity in fixed denominator")
    return {"run_id": run_id, "condition": condition, "seed": worker["seed"],
            "summary": aggregate(rows), "cases": rows, "case_summary_hashes": summaries,
            "case_manifest_hashes": manifests}


def build_report(experiment=EXPERIMENT):
    schedule_path = experiment / "FORMAL_SCHEDULE.json"
    schedule = read(schedule_path)
    runs = [collect_run(worker, condition, experiment=experiment) for worker, condition in schedule_runs(schedule)]
    overall = aggregate([row for run in runs for row in run["cases"]])
    assert overall["case_denominator"] == 180 and overall["prediction_field_denominator"] == 540
    return {"schema_version": 2, "status": "complete" if overall["archived_evaluation_count"] == 180 else "incomplete",
            "protocol": schedule["protocol"], "kind": "fixed_frozen_evaluation_aggregation",
            "runs": runs, "conditions": {condition: aggregate([row for run in runs if run["condition"] == condition for row in run["cases"]]) for condition in ("A", "B")},
            "overall": overall, "schedule_sha256": sha256(schedule_path),
            "coverage_and_novelty": "require_separate_independent_review", "official_benchmark": False,
            "strict_speed_comparison": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-id", required=True)
    args = parser.parse_args()
    result = build_report()
    destination = EXPERIMENT / "reports" / (args.report_id + ".json")
    write_new_json(destination, result)
    print(json.dumps({"report": str(destination), "overall": result["overall"]}))


if __name__ == "__main__":
    main()
