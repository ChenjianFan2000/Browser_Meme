from copy import deepcopy

from harness.replica.contracts_v1.validator import validate, commit_prediction
from harness.replica.contracts_v2.runner import normalize_bundle


def test_v1_bundle_and_prior_remain_exact_for_cleanup_replay():
    contract = {"schema": "component-contract/v1", "parameters": {"$type": "object"}, "slots": {},
                "coverage": ["heading"], "branches": {"ready": {"required": [{"id": "heading", "select": {"role": "heading", "name": "Example"}}]}}}
    bundle = {"schema": "component-contract-bundle/v1", "contracts": {"example": contract}}
    prior = {"disposition": "accepted", "contract_ref": "example", "branch": "ready", "parameters": {}, "unknown_slots": []}
    before, digest = deepcopy(bundle), commit_prediction(prior)
    replay, version = normalize_bundle(bundle)
    result = validate(replay["contracts"]["example"], prior, {"schema": "component-observation/v1", "complete": True,
                       "nodes": [{"id": "n", "parent": None, "source": "ax", "role": "heading", "name": "Example"}], "evidence_refs": ["fixture"]}, commitment=digest)
    assert version == "v1" and replay == before and bundle == before
    assert commit_prediction(prior) == digest and result["verdict"] == "pass"
