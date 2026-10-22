import json

from harness.phase2.call_records import browser_call_records


def test_interrupted_last_call_is_counted_and_not_masked(tmp_path):
    for index in (1, 2):
        evidence = tmp_path / f"call-{index:03d}-fixture" / "evidence"
        evidence.mkdir(parents=True)
        (evidence / "actions.jsonl").write_text(json.dumps({"kind": "action_before"}) + "\n", encoding="utf-8")
    first = tmp_path / "call-001-fixture"
    (first / "management-result.json").write_text(json.dumps({"result": {"status": "ok", "actions": 1, "error": None}}), encoding="utf-8")
    (tmp_path / "broker.jsonl").write_text("\n".join(json.dumps({"event": "dispatch", "call": f"call-{index:03d}-fixture"}) for index in (1, 2)), encoding="utf-8")
    calls = browser_call_records(tmp_path)
    assert len(calls) == 2
    assert sum(call["actions"] for call in calls) == 2
    assert calls[-1]["result"]["error"] == "execution_completion_missing"
    assert calls[-1]["management_completed"] is False


def test_management_timeout_result_and_partial_journal_are_preserved(tmp_path):
    directory = tmp_path / "call-001-fixture"
    (directory / "evidence").mkdir(parents=True)
    (directory / "evidence/actions.jsonl").write_text('{"kind":"action_before"}\n{"kind":', encoding="utf-8")
    (directory / "management-result.json").write_text(json.dumps({"result": {"status": "error", "actions": 1, "error": "executor_timeout"}}), encoding="utf-8")
    call = browser_call_records(tmp_path)[0]
    assert call["actions"] == 1
    assert call["result"]["error"] == "executor_timeout"
    assert call["malformed_action_lines"] == 1
