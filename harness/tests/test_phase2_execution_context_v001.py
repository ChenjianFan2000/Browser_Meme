import pytest
from harness.phase2.execution_context_v001 import process_peak, report_keys, service_error_counts


def event(kind, worker, index, moment):
    return {"event": kind, "worker": worker, "time_ns": moment, "run_id": "generic",
            "case_index": index, "label": f"generic-case-{index:02d}"}


def test_observed_overlap_is_distinct_from_number_of_workers():
    rows = [event("case_process_started", "a", 1, 1),
            event("case_process_started", "b", 2, 2),
            event("case_process_finished", "a", 1, 3),
            event("case_process_started", "c", 3, 4),
            event("case_process_finished", "b", 2, 5),
            event("case_process_finished", "c", 3, 6)]
    assert process_peak(list(reversed(rows))) == 2


def test_overlapping_cases_on_one_site_are_rejected():
    with pytest.raises(ValueError, match="overlapping"):
        process_peak([event("case_process_started", "a", 1, 1),
                      event("case_process_started", "a", 2, 2)])


def test_unfinished_and_misattributed_case_processes_are_rejected():
    with pytest.raises(ValueError, match="active"):
        process_peak([event("case_process_started", "a", 1, 1)])
    with pytest.raises(ValueError, match="ownership"):
        process_peak([event("case_process_started", "a", 1, 1),
                      event("case_process_finished", "a", 2, 2)])


def test_fixed_report_keys_reject_repeated_runs_or_indices_even_with_180_rows():
    schedule = {"workers": [{"seed": seed, "conditions": ["A", "B"]} for seed in (1729, 2718, 3141)]}
    report = {"runs": [{"run_id": f"{condition}-seed-{seed}",
                         "cases": [{"case_index": index} for index in range(1, 31)]}
                        for seed in (1729, 2718, 3141) for condition in ("a", "b")]}
    assert len(report_keys(report, schedule)) == 180
    report["runs"][0]["cases"][0]["case_index"] = 2
    with pytest.raises(ValueError, match="distinct indices"):
        report_keys(report, schedule)
    report["runs"][0]["cases"][0]["case_index"] = 1
    report["runs"][0]["run_id"] = report["runs"][1]["run_id"]
    with pytest.raises(ValueError, match="six learning identities"):
        report_keys(report, schedule)


def test_corrupt_or_absent_service_logs_are_not_reported_as_zero_errors(tmp_path):
    assert service_error_counts(tmp_path) == {"events_archive_missing": 1}
    path = tmp_path / "private/solar/events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"type":"error","message":"Selected model is at capacity"}\nnull\n{"type":', encoding="utf-8")
    assert service_error_counts(tmp_path) == {"model_service_connection_or_availability": 1, "malformed_json_records": 2}
