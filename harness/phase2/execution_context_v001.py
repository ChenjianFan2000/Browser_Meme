"""Describe scheduling and model-service availability without changing raw scores."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .records import sha256, write_new_json
from .report_v002 import case_row, checked_manifest, read, schedule_runs
from .report_lineage_v001 import check_raw_totals
from .run_parallel_v001 import provider_failure
from .run_learning import EXPERIMENT


def process_peak(events):
    active, peak = {}, 0
    for event in sorted(events, key=lambda row: row["time_ns"]):
        if event["event"] == "case_process_started":
            if event["worker"] in active:
                raise ValueError("overlapping cases on the same worker")
            active[event["worker"]] = event["label"]
            peak = max(peak, len(active))
        elif event["event"] == "case_process_finished":
            label = event["run_id"] + f"-case-{event['case_index']:02d}"
            if active.pop(event["worker"], None) != label:
                raise ValueError("case completion differs from active worker ownership")
    if active:
        raise ValueError("batch still has active case processes")
    return peak


def report_keys(report, schedule):
    expected_runs = {condition.lower() + "-seed-" + str(worker["seed"])
                     for worker, condition in schedule_runs(schedule)}
    actual_runs = [run["run_id"] for run in report["runs"]]
    if len(actual_runs) != 6 or set(actual_runs) != expected_runs:
        raise ValueError("report must contain the exact six learning identities")
    keys = set()
    for run in report["runs"]:
        indices = [row["case_index"] for row in run["cases"]]
        if len(indices) != 30 or set(indices) != set(range(1, 31)):
            raise ValueError("each report run must contain exactly the 30 distinct indices")
        keys.update((run["run_id"], index) for index in indices)
    return keys


def service_error_counts(directory):
    path = directory / "private/solar/events.jsonl"
    counts = Counter()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                counts["malformed_json_records"] += 1
                continue
            if not isinstance(row, dict):
                counts["malformed_json_records"] += 1
                continue
            if row.get("type") not in {"error", "turn.failed"}:
                continue
            nested = row.get("error")
            message = (str(row.get("message", "")) + " " +
                       str(nested.get("message", "") if isinstance(nested, dict) else nested or "")).lower()
            if "routing" in message:
                counts["workspace_routing"] += 1
            elif "request timed out" in message or "request timeout" in message:
                counts["model_request_timeout"] += 1
            elif any(value in message for value in ("429", "401", "rate limit", "capacity", "connection", "reconnecting", "service unavailable")):
                counts["model_service_connection_or_availability"] += 1
    else:
        counts["events_archive_missing"] += 1
    return dict(counts)


def build(report_path, experiment=EXPERIMENT):
    report_path = Path(report_path)
    report = read(report_path)
    check_raw_totals(report)
    if (report.get("status") != "complete" or report["overall"]["case_denominator"] != 180
            or report["overall"]["archived_evaluation_count"] != 180):
        raise ValueError("complete fixed-denominator report required")
    schedule_path = experiment / "FORMAL_SCHEDULE.json"
    if report.get("schedule_sha256") != sha256(schedule_path):
        raise ValueError("raw report schedule binding differs")
    expected_keys = report_keys(report, read(schedule_path))
    drain_path = experiment / "batches/drain-001/drain-completed.json"
    drain = read(drain_path)
    legacy = {}
    for row in drain["sealed_cases"]:
        parts = Path(row["path"]).parts
        if len(parts) != 3 or parts[0] != "evaluations" or not parts[2].startswith("case-"):
            raise ValueError("invalid administrative drain case identity")
        key = (parts[1], int(parts[2].removeprefix("case-")))
        if key in legacy:
            raise ValueError("duplicate administrative drain case identity")
        legacy[key] = row["manifest_sha256"]
    claims, batches, all_events = {}, [], []
    for batch in sorted((experiment / "batches").glob("parallel-*")):
        events_path = batch / "dispatch-events.jsonl"
        required = {"dispatch-plan.json", "batch-summary.json"}
        if events_path.exists():
            required.add("dispatch-events.jsonl")
        required.update(path.relative_to(batch).as_posix() for path in (batch / "claims").glob("*.json"))
        _, manifest_hash = checked_manifest(batch, "batch-manifest.json", required)
        plan, summary = read(batch / "dispatch-plan.json"), read(batch / "batch-summary.json")
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()] if events_path.exists() else []
        if not events and list((batch / "claims").glob("*.json")):
            raise ValueError("claimed cases require a frozen dispatch journal")
        all_events.extend(events)
        for path in sorted((batch / "claims").glob("*.json")):
            value = read(path)
            key = (value["run_id"], value["case_index"])
            if key in claims or key in legacy:
                raise ValueError("case was claimed more than once across schedule phases")
            claims[key] = {"batch_id": batch.name, "worker": value["worker"],
                           "runtime": value["runtime"], "claim_sha256": sha256(path)}
        memory = [row for row in events if row["event"] == "memory_admission"]
        batches.append({"batch_id": batch.name, "manifest_sha256": manifest_hash,
                        "registered_max_workers": plan["actual_max_workers"],
                        "observed_case_process_peak": process_peak(events),
                        "started_ns": summary["started_ns"], "finished_ns": summary["finished_ns"],
                        "dispatch_stopped": summary["dispatch_stopped"],
                        "claimed_cases": len(list((batch / "claims").glob("*.json"))),
                        "windows_min_sampled_available_bytes": min((row["windows_available_bytes"] for row in memory), default=None),
                        "wsl_min_sampled_available_bytes": min((row["wsl_available_bytes"] for row in memory), default=None),
                        "memory_observations_are_dispatch_samples_only": True})
    rows = []
    for run in report["runs"]:
        for case in run["cases"]:
            key = (run["run_id"], case["case_index"])
            directory = experiment / "evaluations" / key[0] / f"case-{key[1]:02d}"
            _, digest = checked_manifest(directory, "case-manifest.json", {"registration.json", "case-summary.json"})
            relative = (directory / "case-manifest.json").relative_to(experiment).as_posix()
            if run["case_manifest_hashes"].get(relative) != digest:
                raise ValueError("raw report case hash binding differs")
            summary, registration = read(directory / "case-summary.json"), read(directory / "registration.json")
            if case != case_row(key[1], summary):
                raise ValueError("raw case differs from the original immutable summary")
            if (summary.get("learning_run") != key[0] or summary.get("case_index") != key[1]
                    or summary.get("condition") != run["condition"]
                    or registration.get("learning_run") != key[0] or registration.get("index") != key[1]
                    or registration.get("condition") != run["condition"]
                    or registration.get("case_id") != summary.get("case_id")):
                raise ValueError("case identity differs from raw report")
            if key in legacy:
                if digest != legacy[key]:
                    raise ValueError("pre-expansion case has changed since administrative drain")
                phase, claim = "original_three_workers", None
            elif key in claims:
                phase, claim = claims[key]["batch_id"], claims[key]
                if Path(claim["runtime"]).resolve() != Path(registration["runtime"]).resolve():
                    raise ValueError("case runtime differs from dispatch claim")
            else:
                raise ValueError("case has no scheduling provenance")
            service_counts = service_error_counts(directory)
            rows.append({"run_id": key[0], "case_index": key[1], "condition": run["condition"],
                         "schedule_phase": phase, "claim": claim, "case_manifest_sha256": digest,
                         "model_cli_exit_code": summary["model_cli_exit_code"],
                         "model_cli_timeout": summary["model_cli_timeout"],
                         "ui_actions": summary["ui_actions"],
                         "provider_or_cli_failure_class": provider_failure(directory, summary),
                         "model_service_error_event_counts": service_counts,
                         "model_service_event_archive_complete": not any(service_counts.get(name) for name in ("malformed_json_records", "events_archive_missing")),
                         "raw_task_status": case["task_status"]})
    if (len(rows) != 180 or len(legacy) + len(claims) != 180
            or set(legacy) | set(claims) != expected_keys):
        raise ValueError("execution-context denominator differs")
    return {"schema_version": 1, "status": "complete", "kind": "execution_context_and_service_availability",
            "report_sha256": sha256(report_path), "drain_record_sha256": sha256(drain_path),
            "generator_sha256": sha256(Path(__file__)), "case_denominator": 180,
            "lineage_validator_sha256": sha256(Path(__file__).with_name("report_lineage_v001.py")),
            "phase_counts": dict(Counter(row["schedule_phase"] for row in rows)),
            "failure_class_counts": dict(Counter(row["provider_or_cli_failure_class"] or "no_provider_failure_classified" for row in rows)),
            "cli_success_with_service_error_events": sum(row["model_cli_exit_code"] == 0 and any(
                count for name, count in row["model_service_error_event_counts"].items()
                if name not in {"malformed_json_records", "events_archive_missing"}) for row in rows),
            "incomplete_model_service_event_archive_count": sum(not row["model_service_event_archive_complete"] for row in rows),
            "global_expanded_case_process_peak": process_peak(all_events),
            "batches": batches, "cases": rows,
            "raw_results_rewritten": False, "strict_speed_comparison": False,
            "qualification": "Process concurrency is scheduling overlap, not simultaneous browser actions or a throughput causal comparison. Infrastructure failures remain in the original 180 cases. Unknown causes are not attributed to the model or website."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build(args.report)
    write_new_json(Path(args.output), result)
    print(json.dumps({"output": args.output, "phase_counts": result["phase_counts"],
                      "failure_class_counts": result["failure_class_counts"]}))


if __name__ == "__main__":
    main()
