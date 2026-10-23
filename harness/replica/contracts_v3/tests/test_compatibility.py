from copy import deepcopy
import importlib

import pytest

from harness.replica.contracts_v3.runner import normalize_bundle


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_original_contract_and_prediction_keep_their_version(version):
    validator = importlib.import_module("harness.replica.contracts_" + version + ".validator")
    contract = {"schema": "component-contract/" + version, "parameters": {"$type": "object"}, "slots": {},
                "coverage": ["anchor"], "branches": {"ready": {"required": [{"id": "anchor", "select": {"role": "heading", "name": "Example"}}]}}}
    bundle = {"schema": "component-contract-bundle/" + version, "contracts": {"example": contract}}
    before = deepcopy(bundle)
    prediction = {"disposition": "accepted", "contract_ref": "example", "branch": "ready", "parameters": {}, "unknown_slots": []}
    digest = validator.commit_prediction(prediction)
    adapted, selected_version = normalize_bundle(bundle)
    assert selected_version == version and adapted["contracts"] == before["contracts"] and bundle == before
    result = validator.validate(adapted["contracts"]["example"], prediction, {"schema": "component-observation/v1", "complete": True,
        "nodes": [{"id": "n", "parent": None, "source": "ax", "role": "heading", "name": "Example"}], "evidence_refs": ["fixture"]}, commitment=digest)
    assert result["verdict"] == "pass" and validator.commit_prediction(prediction) == digest
