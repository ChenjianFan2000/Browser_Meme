"""Controller contract checks without browser processes or website knowledge."""
from copy import deepcopy
import json

import pytest

from harness.replica.contracts_v1 import runner
from harness.replica.contracts_v1.tests.test_validator import fixture


class IndependentFixtureOracle:
    def __init__(self, *, verdict="pass", checks=None):
        self.verdict = verdict
        self.checks = [{"id": "generic-state", "pass": True}] if checks is None else checks

    def capture(self, lane, case_ref, checkpoint):
        return {"status": "confirmed", "facts": {"fixture_state": "ready"},
                "logical_object_identities": ["fixture-object"], "coverage": {"generic-state": True},
                "evidence_refs": ["independent-fixture-capture.json"]}

    def assess(self, case_ref, checkpoint, previous, current, action):
        return {"verdict": self.verdict, "checks": self.checks, "evidence_refs": ["independent-fixture-checks.json"]}


def action_record(tmp_path, prediction, *, before=None, after=None):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    before = deepcopy(prediction) if before is None else before
    after = deepcopy(prediction) if after is None else after
    rows = [{"kind": "action_before", "action": 1, "prediction": before},
            {"kind": "action_after", "action": 1, "prediction": after}]
    (evidence / "actions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return {"checkpoint": "after_action", "action": 1, "prediction": deepcopy(prediction), "evidence_directory": str(evidence),
            "method": "click", "action_arguments": {"args": [], "kwargs": {}},
            "action_identity": {"owner": "Locator", "method": "click", "element": {"id": "fixture-object"}},
            "observation": {}, "error": None, "status": "observed"}


def check(tmp_path, monkeypatch, *, mutate=None, oracle="default"):
    contract, prediction, observation = fixture()
    if mutate:
        mutate(contract, prediction, observation)
    record = action_record(tmp_path, prediction)
    monkeypatch.setattr(runner, "load_checkpoint", lambda record: deepcopy(observation))
    result, current = runner.check_checkpoint(record, {"contracts": {"example": contract}}, None,
        oracle=IndependentFixtureOracle() if oracle == "default" else oracle, case_ref="generic-fixture",
        previous=None, preparation={"initial_equivalence": "pass", "reset_receipt": "fixture-reset"},
        destination=tmp_path / "checked")
    return result, current, prediction


def test_prior_prediction_uses_serialized_before_not_mutable_late_object(tmp_path):
    _, prediction, _ = fixture()
    record = action_record(tmp_path, prediction)
    prior, error = runner.prior_prediction(record)
    assert error is None
    prediction["parameters"]["title"] = "Mutated unrelated author object"
    assert prior["parameters"]["title"] == "Results"


def test_action_after_rewriting_is_rejected(tmp_path):
    _, prediction, _ = fixture()
    before = deepcopy(prediction)
    before["parameters"]["title"] = "Original prior"
    record = action_record(tmp_path, prediction, before=before)
    prior, error = runner.prior_prediction(record)
    assert error == "prediction_rewritten"
    assert prior == before


def test_boolean_to_number_prior_rewriting_is_rejected(tmp_path):
    _, prediction, _ = fixture()
    prediction["parameters"]["flag"] = 0
    before = deepcopy(prediction)
    before["parameters"]["flag"] = False
    record = action_record(tmp_path, prediction, before=before)
    assert runner.prior_prediction(record)[1] == "prediction_rewritten"


def test_missing_or_reordered_action_before_is_not_a_prediction(tmp_path):
    _, prediction, _ = fixture()
    record = action_record(tmp_path, prediction)
    path = tmp_path / "evidence/actions.jsonl"
    rows = path.read_text().splitlines()
    path.write_text("\n".join(reversed(rows)))
    assert runner.prior_prediction(record)[1] == "missing_or_ambiguous_prior_prediction"


def test_normal_gate_releases_and_observed_bindings_do_not_rewrite_prior(tmp_path, monkeypatch):
    result, current, prediction = check(tmp_path, monkeypatch)
    assert result["primary_pass"] is True
    assert result["release_decision"] == "continue"
    assert current["facts"] == {"fixture_state": "ready"}
    prior = json.loads((tmp_path / "checked/prior-prediction.json").read_text())
    update = json.loads((tmp_path / "checked/observation-update.json").read_text())
    assert prior["prediction"] == prediction
    assert "bindings" not in prior["prediction"]
    assert update["bindings"] == {"labels": ["External A", "External B"]}
    assert update["rewrites_prior_prediction"] is False
    assert update["prior_prediction_sha256"] == prior["sha256"]
    assert update["prediction_score"]["passed"] == 4
    assert update["observation_binding_score"]["passed"] == 1


def test_structural_contradiction_stops_gate(tmp_path, monkeypatch):
    result, _, _ = check(tmp_path, monkeypatch, mutate=lambda c, p, o: o.update(nodes=o["nodes"][:2]))
    assert result["release_decision"] == "stop"
    assert result["contract_validation"]["verdict"] == "fail"


def test_unknown_binding_stops_gate(tmp_path, monkeypatch):
    result, _, _ = check(tmp_path, monkeypatch, mutate=lambda c, p, o: c["branches"]["ready"]["required"][1].pop("bind"))
    assert result["release_decision"] == "stop"
    assert result["contract_validation"]["verdict"] == "unknown"


def test_unknown_semantic_disposition_stops_gate(tmp_path, monkeypatch):
    result, _, _ = check(tmp_path, monkeypatch, mutate=lambda c, p, o: p.update(disposition="unknown"))
    assert result["release_decision"] == "stop"
    assert result["contract_validation"]["verdict"] == "unknown"


def test_missing_independent_oracle_stops_even_matching_contract(tmp_path, monkeypatch):
    result, _, _ = check(tmp_path, monkeypatch, oracle=None)
    assert result["release_decision"] == "stop"
    assert result["contract_validation"]["verdict"] == "pass"
    assert result["layers"]["independent_truth"] is False


def test_independent_truth_contradiction_stops_matching_contract(tmp_path, monkeypatch):
    result, _, _ = check(tmp_path, monkeypatch, oracle=IndependentFixtureOracle(verdict="fail"))
    assert result["release_decision"] == "stop"
    assert result["contract_validation"]["verdict"] == "pass"
    assert result["business"]["verdict"] == "fail"


@pytest.mark.parametrize("checks", [{"pass": 0}, {}, ["fail"], ["unknown"], [{}], {"pass": True, "side_effect_safe": False}])
def test_incomplete_or_nonboolean_oracle_checks_never_pass(checks):
    result, _ = runner.business_checkpoint(IndependentFixtureOracle(checks=checks), "fixture", {"checkpoint": "state0"}, {}, None,
                                          {"initial_equivalence": "pass", "reset_receipt": "fixture-reset"})
    assert result["verdict"] == "unconfirmed"


@pytest.mark.parametrize("checks", [[{"id": "x", "pass": True}], {"x": True}])
def test_explicit_positive_oracle_checks_can_pass(checks):
    result, _ = runner.business_checkpoint(IndependentFixtureOracle(checks=checks), "fixture", {"checkpoint": "state0"}, {}, None,
                                          {"initial_equivalence": "pass", "reset_receipt": "fixture-reset"})
    assert result["verdict"] == "pass"
