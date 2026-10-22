import json
import random
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from harness.phase2 import run_parallel_v001 as dispatch
from harness.phase2 import run_expanded_case_v001 as expanded
from harness.phase2.records import sha256


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def schedule():
    return {"workers": [{"seed": seed, "conditions": conditions} for seed, conditions in
                        [(1729, ["A", "B"]), (2718, ["B", "A"]), (3141, ["A", "B"])]]}


def test_twelve_consumers_claim_each_case_once_and_stop_preserves_unclaimed():
    queue = dispatch.DispatchQueue(list(range(180)))

    def consume():
        values = []
        while (value := queue.take()) is not None:
            values.append(value)
        return values

    with ThreadPoolExecutor(max_workers=12) as pool:
        values = [value for batch in pool.map(lambda _: consume(), range(12)) for value in batch]
    assert sorted(values) == list(range(180))
    queue = dispatch.DispatchQueue(list(range(180)))
    active = [queue.take() for _ in range(12)]
    queue.stop()
    assert active == list(range(12))
    assert queue.take() is None and queue.queue.qsize() == 168


def test_pending_cases_keep_fixed_denominator_and_seed_relative_order(tmp_path):
    pending, preserved = dispatch.pending_cases(schedule(), experiment=tmp_path)
    assert len(pending) == 180 and preserved == []
    assert len({(row["run_id"], row["case_index"]) for row in pending}) == 180
    for seed in (1729, 2718, 3141):
        expected = list(range(1, 31))
        random.Random(seed).shuffle(expected)
        for condition in ("a", "b"):
            assert [row["case_index"] for row in pending if row["run_id"] == f"{condition}-seed-{seed}"] == expected
    assert len({row["run_id"] for row in pending[:6]}) == 6


def sealed_case(tmp_path, *, safe=True, identity="a-seed-1729"):
    directory = tmp_path / "evaluations/a-seed-1729/case-01"
    write(directory / "case-summary.json", {"learning_run": identity, "case_index": 1,
          "condition": "A", "safe_to_reset": safe, "case_id": "synthetic-1"})
    write(directory / "registration.json", {"learning_run": "a-seed-1729", "index": 1,
          "condition": "A", "case_id": "synthetic-1"})
    write(directory / "case-manifest.json", {"files": {name: sha256(directory / name)
          for name in ("case-summary.json", "registration.json")}})
    return directory


def test_sealed_case_skipped_only_with_identity_integrity_and_reset_safety(tmp_path):
    directory = sealed_case(tmp_path)
    pending, preserved = dispatch.pending_cases(schedule(), experiment=tmp_path)
    assert len(pending) == 179 and len(preserved) == 1
    assert preserved[0]["case_manifest_sha256"] == sha256(directory / "case-manifest.json")
    write(directory / "registration.json", {})
    with pytest.raises(ValueError):
        dispatch.pending_cases(schedule(), experiment=tmp_path)


@pytest.mark.parametrize("safe,identity", [(False, "a-seed-1729"), (True, "b-seed-1729")])
def test_unsafe_or_wrong_identity_blocks_resume(tmp_path, safe, identity):
    sealed_case(tmp_path, safe=safe, identity=identity)
    with pytest.raises(ValueError):
        dispatch.pending_cases(schedule(), experiment=tmp_path)


def test_real_partial_case_is_never_retried(tmp_path):
    (tmp_path / "evaluations/a-seed-1729/case-01").mkdir(parents=True)
    with pytest.raises(ValueError, match="partial case"):
        dispatch.pending_cases(schedule(), experiment=tmp_path)


@pytest.mark.parametrize("event", [
    {"type": "error", "message": "workspace routing discovery timed out"},
    {"type": "turn.failed", "error": {"message": "429 rate limit"}},
    {"type": "error", "message": "Selected model is at capacity"},
])
def test_provider_failure_stops_even_if_overall_case_also_timed_out(tmp_path, event):
    path = tmp_path / "private/solar/events.jsonl"
    write(path, event)
    assert dispatch.provider_failure(tmp_path, {"model_cli_exit_code": 1,
           "model_cli_timeout": True, "ui_actions": 3}) == "model_provider_connection_or_availability_failure"
    write(path, {"type": "error", "message": "locator timing error"})
    assert dispatch.provider_failure(tmp_path, {"model_cli_exit_code": 1,
           "model_cli_timeout": True, "ui_actions": 3}) is None


def test_expanded_events_reuse_original_recording_and_check_worker(tmp_path):
    from harness.phase2.run_learning import TrustedEvents
    cls = expanded.events_type(lambda **kwargs: {"generic_event": kwargs["status"]}, tmp_path.resolve())
    assert cls.__call__ is TrustedEvents.__call__ and cls.close is TrustedEvents.close
    events = cls(tmp_path / "events.jsonl", tmp_path)
    events({"method": "GET", "url": "http://example.invalid/", "status": 200,
            "request_body": None, "response_body": "", "content_type": "text/plain",
            "management_request_started_ns": 1, "event_phase": "response"})
    events.close()
    row = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8"))
    assert row["generic_event"] == 200 and row["management_request_started_ns"] == 1
    assert events.count == 1 and events.file.closed
    with pytest.raises(ValueError, match="worker assignment"):
        cls(tmp_path / "wrong.jsonl", tmp_path / "other")


def test_memory_gate_checks_both_hosts_and_caches_one_shared_sample(monkeypatch):
    seen, calls = [], []
    monkeypatch.setattr(dispatch, "available_memory_bytes", lambda: 8 * 1024 ** 3)
    def measure(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=str(1 * 1024 ** 3))
    monkeypatch.setattr(dispatch.subprocess, "run", measure)
    gate = dispatch.MemoryGate(seen.append)
    assert gate.available() is False and gate.available() is False
    assert len(calls) == 1 and seen[0]["wsl_available_bytes"] == 1024 ** 3
    gate.sampled = 0
    monkeypatch.setattr(dispatch.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match="measurement failed"):
        gate.available()


def test_registration_requires_actual_entries_exact_six_identities_and_valid_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(expanded, "ROOT", tmp_path)
    experiment = tmp_path / "experiment"
    monkeypatch.setattr(expanded.frozen, "EXPERIMENT", experiment)
    write(experiment / "FORMAL_SCHEDULE.json", schedule())
    paths = ["harness/phase2/run_expanded_case_v001.py", "harness/phase2/run_parallel_v001.py",
             "driver.py", "protocol.md"]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic management input", encoding="utf-8")
    write(tmp_path / "gate.json", {"status": "passed"})
    value = {"schema_version": 1, "kind": "expanded_frozen_evaluation_dispatch",
             "driver_entry": "driver.py", "protocol_path": "protocol.md",
             "management_inputs": [{"path": name, "sha256": sha256(tmp_path / name)} for name in paths],
             "admission_records": [{"path": "gate.json", "sha256": sha256(tmp_path / "gate.json")}],
             "max_active_workers": 3, "workers": [{"id": value} for value in "abc"], "case_denominator": 180,
             "model": "gpt-6.1-sol", "reasoning_effort": "high",
             "formal_schedule_sha256": sha256(experiment / "FORMAL_SCHEDULE.json"),
             "learning_run_ids": [f"{condition}-seed-{seed}" for seed in (1729, 2718, 3141) for condition in ("a", "b")]}
    registration = tmp_path / "registration.json"
    write(registration, value)
    assert expanded.verify_registration(registration)["case_denominator"] == 180
    removed = value["management_inputs"].pop(0)
    write(registration, value)
    with pytest.raises(ValueError, match="hash-bound"):
        expanded.verify_registration(registration)
    value["management_inputs"].insert(0, removed)
    value["learning_run_ids"][0] = value["learning_run_ids"][1]
    write(registration, value)
    with pytest.raises(ValueError, match="fixed six"):
        expanded.verify_registration(registration)
    value["learning_run_ids"][0] = "a-seed-1729"
    write(registration, value)
    (tmp_path / "driver.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="input changed"):
        expanded.verify_registration(registration)
