import json
from pathlib import Path

import pytest

from harness.phase2.records import (
    contained_file, freeze_manifest, sha256, summarize_cases,
    validate_prediction, validate_rules, verify_manifest, write_new_json,
)


def test_frozen_manifest_detects_modification_and_cannot_be_overwritten(tmp_path):
    (tmp_path / "observation.json").write_text('{"visible":true}', encoding="utf-8")
    manifest_path = tmp_path / "frozen.json"
    manifest = freeze_manifest(tmp_path, ["observation.json"], manifest_path)
    assert verify_manifest(tmp_path, manifest) == []
    (tmp_path / "observation.json").write_text('{"visible":false}', encoding="utf-8")
    assert verify_manifest(tmp_path, manifest)[0]["reason"] == "hash_mismatch"
    with pytest.raises(FileExistsError):
        write_new_json(manifest_path, {})


def test_evidence_cannot_escape_root(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    private = tmp_path / "private.json"
    private.write_text("private", encoding="utf-8")
    for reference in ("../private.json", str(private.resolve())):
        with pytest.raises(ValueError):
            contained_file(root, reference)


def test_unrun_and_unknown_cases_remain_in_denominator():
    rows = [{"id": "one", "status": "completed", "passed": True, "ui_actions_dispatched": 2},
            {"id": "two", "status": "unknown", "passed": None, "ui_actions_dispatched": 1}]
    summary = summarize_cases(["one", "two", "three"], rows)
    assert summary["case_denominator"] == 3
    assert summary["case_success_rate"] == 1 / 3
    assert summary["status_counts"] == {"completed": 1, "unknown": 1, "not_run": 1}
    assert summarize_cases(["one"], [])["case_success_rate"] is None
    with pytest.raises(ValueError):
        summarize_cases(["one"], rows)
    with pytest.raises(ValueError):
        summarize_cases(["one"], [rows[0], rows[0]])


def test_rule_claims_require_real_browser_evidence(tmp_path):
    evidence = tmp_path / "observed.json"
    evidence.write_text("{}", encoding="utf-8")
    rule = {"id": "r1", "statement": "A bounded claim", "status": "verified", "evidence_refs": []}
    with pytest.raises(ValueError):
        validate_rules([rule], tmp_path)
    rule["evidence_refs"] = [{"path": evidence.name, "sha256": sha256(evidence)}]
    validate_rules([rule], tmp_path)
    evidence.write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(ValueError):
        validate_rules([rule], tmp_path)
    rule["status"] = "hypothesis"
    rule["evidence_refs"] = []
    rule["source_refs"] = ["old source"]
    with pytest.raises(ValueError):
        validate_rules([rule], tmp_path)


def test_unknown_prediction_is_valid_but_numeric_truthiness_is_not():
    prediction = {"disposition": "unknown", "effects": {
        "persistent_state_changed": None, "affected_record_count": None},
        "ui_claims": [], "unknowns": ["Not observed"]}
    validate_prediction(prediction)
    prediction["effects"]["affected_record_count"] = True
    with pytest.raises(ValueError):
        validate_prediction(prediction)
    prediction["effects"]["affected_record_count"] = 0
    prediction["effects"]["persistent_state_changed"] = 1
    with pytest.raises(ValueError):
        validate_prediction(prediction)
