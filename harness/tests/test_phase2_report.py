from harness.phase2.report import aggregate, case_row


def sample(safe=True):
    return {"case_id": "fixture", "ui_actions": 1, "browser_executions": 1, "elapsed_seconds": 1,
            "safe_to_reset": safe, "independent_evaluation": {"task_outcome": "passed",
              "business_disposition": "accepted", "transport_disposition": "accepted", "side_effects_ok": True,
              "prediction_grading": {"disposition": "correct", "persistent_state_changed": "unknown", "affected_record_count": "unscorable"}}}


def test_unknown_and_missing_cases_remain_in_fixed_denominator():
    value = aggregate([case_row(1, sample()), case_row(2)])
    assert value["case_denominator"] == 2
    assert value["prediction_field_denominator"] == 6
    assert value["prediction_counts"] == {"correct": 1, "incorrect": 0, "unknown": 4, "unscorable": 1}
    assert value["prediction_correct_rate_fixed_denominator"] == 1 / 6
    assert value["prediction_accuracy_on_scorable_fields"] == 1
    assert value["task_pass_rate_fixed_denominator"] == .5


def test_unsafe_write_does_not_become_confirmed_success():
    row = case_row(1, sample(False))
    value = aggregate([row])
    assert row["provisional_independent_outcome"] == "passed"
    assert value["task_counts"]["passed"] == 0
    assert value["task_counts"]["unsafe_reset"] == 1
    assert value["prediction_counts"]["unknown"] == 1
    assert value["prediction_counts"]["unscorable"] == 2


def test_no_execution_is_not_a_zero_model_score():
    value = aggregate([case_row(1, partial=True)])
    assert value["measurement_status"] == "not_started"
    assert value["task_pass_rate_fixed_denominator"] is None
    assert value["prediction_correct_rate_fixed_denominator"] is None
