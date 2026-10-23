from copy import deepcopy

import pytest

from harness.replica.contracts_v1.schema import SchemaError, commit_prediction, matches, validate_contract
from harness.replica.contracts_v1.validator import render, validate


def fixture():
    contract = {
        "schema": "component-contract/v1",
        "parameters": {"$type": "object", "$required": ["title"], "$properties": {"title": {"$type": "string"}}, "$additional": False},
        "slots": {"labels": {"type": "array", "items": {"$type": "string"}, "required": True}},
        "coverage": ["list", "items", "no-alert", "owner"],
        "branches": {"ready": {
            "required": [
                {"id": "list", "select": {"role": "list", "name": {"$param": "title"}}, "count": {"min": 1, "max": 1}},
                {"id": "items", "scope": "list", "select": {"role": "listitem", "properties": {"selected": False}}, "count": {"min": 1},
                 "bind": {"slot": "labels", "field": "name", "many": True}},
            ],
            "forbidden": [{"id": "no-alert", "select": {"role": "alert"}}],
            "relations": [{"id": "owner", "kind": "parent", "left": "items", "right": "list", "quantifier": "each"}],
            "tree": {"role": "list", "name": {"$param": "title"}, "children": {"$slot": "labels"}},
        }},
    }
    prediction = {"disposition": "accepted", "contract_ref": "example", "branch": "ready", "parameters": {"title": "Results"}, "unknown_slots": ["labels"]}
    observation = {"schema": "component-observation/v1", "complete": True, "evidence_refs": ["independent-capture.json"], "nodes": [
        {"id": "root", "parent": None, "source": "ax", "role": "document", "name": ""},
        {"id": "list", "parent": "root", "source": "ax", "role": "list", "name": "Results"},
        {"id": "a", "parent": "list", "source": "ax", "role": "listitem", "name": "External A", "properties": {"selected": False}},
        {"id": "b", "parent": "list", "source": "ax", "role": "listitem", "name": "External B", "properties": {"selected": False}},
    ]}
    return contract, prediction, observation


def assess(change=None):
    contract, prediction, observation = fixture()
    commitment = commit_prediction(prediction)
    if change:
        change(contract, prediction, observation)
    return validate(contract, prediction, observation, commitment=commitment)


def test_normal_has_nonempty_prior_and_separate_binding_coverage():
    result = assess()
    assert result["verdict"] == "pass"
    assert result["coverage"]["nonempty"]
    assert result["prediction_score"] == {"passed": 4, "failed": 0, "unknown": 0, "total": 4}
    assert result["observation_binding_score"]["passed"] == 1
    assert result["bindings"] == {"labels": ["External A", "External B"]}


def test_missing_required_node_blocks():
    result = assess(lambda c, p, o: o.update(nodes=o["nodes"][:2]))
    assert result["verdict"] == "fail"
    assert any(row["id"] == "items" and row["verdict"] == "fail" for row in result["checks"])


def test_wrong_parent_blocks():
    def change(c, p, o):
        o["nodes"][2]["parent"] = "root"
        o["nodes"][3]["parent"] = "root"
    assert assess(change)["verdict"] == "fail"


def test_wrong_state_blocks():
    def change(c, p, o):
        for node in o["nodes"][2:]:
            node["properties"]["selected"] = True
    assert assess(change)["verdict"] == "fail"


def test_variable_external_list_data_is_permitted_without_rewriting_prior():
    contract, prediction, observation = fixture()
    original = deepcopy(prediction)
    observation["nodes"][2]["name"] = "New external value"
    observation["nodes"].append({"id": "c", "parent": "list", "source": "ax", "role": "listitem", "name": "Third external value", "properties": {"selected": False}})
    result = validate(contract, prediction, observation, commitment=commit_prediction(prediction))
    assert result["verdict"] == "pass"
    assert len(result["bindings"]["labels"]) == 3
    assert prediction == original


def test_missing_binding_is_unknown():
    result = assess(lambda c, p, o: c["branches"]["ready"]["required"][1].pop("bind"))
    assert result["verdict"] == "unknown"
    assert any(row["reason"] == "required_slot_unbound" for row in result["checks"])


def test_ambiguous_scope_is_unknown():
    def change(c, p, o):
        c["branches"]["ready"]["required"][0]["count"] = {"min": 1}
        o["nodes"].append({"id": "list2", "parent": "root", "source": "ax", "role": "list", "name": "Results"})
    assert assess(change)["verdict"] == "unknown"


def test_postobservation_prediction_rewriting_is_rejected():
    result = assess(lambda c, p, o: p["parameters"].update(title="Changed after action"))
    assert result["verdict"] == "fail"
    assert result["checks"][0]["reason"] == "prediction_rewritten"


@pytest.mark.parametrize("change", [
    lambda c, p, o: o.update(complete=False),
    lambda c, p, o: o.update(evidence_refs=[]),
    lambda c, p, o: o["nodes"].append(deepcopy(o["nodes"][1])),
    lambda c, p, o: o["nodes"][2].update(parent="missing"),
    lambda c, p, o: o["nodes"][0].update(parent="a"),
])
def test_incomplete_or_invalid_collection_is_unknown(change):
    assert assess(change)["verdict"] == "unknown"


def test_forbidden_node_blocks():
    result = assess(lambda c, p, o: o["nodes"].append({"id": "alert", "parent": "root", "source": "ax", "role": "alert", "name": "Problem"}))
    assert result["verdict"] == "fail"


def test_missing_field_in_binding_does_not_become_wildcard():
    result = assess(lambda c, p, o: o["nodes"][2].pop("name"))
    assert result["verdict"] == "unknown"


def test_unknown_selector_semantics_is_unknown():
    result = assess(lambda c, p, o: c["branches"]["ready"]["required"][1]["select"].update(guessed_business_state="ready"))
    assert result["verdict"] == "unknown"


def test_prior_unknown_slot_declaration_required():
    contract, prediction, observation = fixture()
    prediction["unknown_slots"] = []
    result = validate(contract, prediction, observation, commitment=commit_prediction(prediction))
    assert result["verdict"] == "unknown"


def test_postbinding_relation_checks_do_not_add_prior_prediction_credit():
    contract, prediction, observation = fixture()
    contract["branches"]["ready"]["required"].append({"id": "bound-first", "select": {"role": "listitem", "name": {"$slot": "labels.0"}}})
    result = validate(contract, prediction, observation, commitment=commit_prediction(prediction))
    assert result["verdict"] == "pass"
    assert result["prediction_score"]["total"] == 4
    assert result["observation_binding_score"]["total"] == 2


@pytest.mark.parametrize("selector", [{}, {"source": "ax"}, {"role": {"$type": "string"}}])
def test_vacuous_coverage_is_rejected(selector):
    contract, _, _ = fixture()
    contract["branches"]["ready"]["required"][0]["select"] = selector
    with pytest.raises(SchemaError):
        validate_contract(contract)


def test_object_array_typed_required_and_forbidden_patterns():
    pattern = {"$type": "object", "$required": ["rows"], "$forbidden": ["error"], "$additional": False,
               "$properties": {"rows": {"$type": "array", "$minItems": 1, "$items": {"$type": "object", "$required": ["id"], "$properties": {"id": {"$type": "integer"}}}}}}
    assert matches({"rows": [{"id": 7}, {"id": 8}]}, pattern)
    assert not matches({"rows": [{"id": True}]}, pattern)
    assert not matches({"rows": [{"id": 7}], "error": None}, pattern)
    assert not matches({"rows": []}, pattern)


def test_branch_precondition_and_render():
    contract, prediction, observation = fixture()
    contract["branches"]["ready"]["when"] = {"title": "Results"}
    rendered = render(contract, {"title": "Different"}, branch="ready")
    assert rendered["tree"]["name"] == "Different"
    assert rendered["tree"]["children"] == {"$unknown": {"slot": "labels", "type": "array"}}
    prediction["parameters"]["title"] = "Different"
    assert validate(contract, prediction, observation)["verdict"] == "fail"


def test_wrong_parent_relation_blocks_even_if_both_nodes_exist():
    contract, prediction, observation = fixture()
    contract["branches"]["ready"]["required"][1].pop("scope")
    observation["nodes"][2]["parent"] = "root"
    result = validate(contract, prediction, observation)
    assert result["verdict"] == "fail"
    assert any(row["id"] == "owner" and row["reason"] == "relation_contradiction" for row in result["checks"])


def test_unknown_predicted_disposition_blocks():
    contract, prediction, observation = fixture()
    prediction["disposition"] = "unknown"
    result = validate(contract, prediction, observation, commitment=commit_prediction(prediction))
    assert result["verdict"] == "unknown"
    assert result["checks"][0]["reason"] == "unknown_or_missing_predicted_disposition"


def test_render_unresolved_or_mistyped_parameters_remain_unknown():
    contract, _, _ = fixture()
    rendered = render(contract, {})
    assert rendered["status"] == "unknown"
    assert rendered["unknown_parameters"] == ["title"]
    assert rendered["tree"]["name"] == {"$unknown": {"parameter": "title"}}
    assert render(contract, {"title": 1})["input_validation"]["verdict"] == "unknown"


def test_nested_constants_distinguish_boolean_from_integer():
    assert not matches({"state": False}, {"$const": {"state": 0}})


def test_parameter_data_cannot_inject_pattern_operators():
    contract = {"schema": "component-contract/v1", "parameters": {"$type": "object"}, "slots": {}, "coverage": ["anchor"],
                "branches": {"ready": {"required": [{"id": "anchor", "select": {"source": "ax", "name": {"$param": "wild"}}}]}}}
    prediction = {"disposition": "accepted", "contract_ref": "example", "branch": "ready", "parameters": {"wild": {"$type": "string"}}, "unknown_slots": []}
    observation = {"schema": "component-observation/v1", "complete": True, "evidence_refs": ["fixture.json"],
                   "nodes": [{"id": "one", "parent": None, "source": "ax", "name": "Unpredicted arbitrary name"}]}
    assert validate(contract, prediction, observation)["verdict"] == "fail"


def test_slot_data_cannot_inject_pattern_operators():
    contract, prediction, observation = fixture()
    contract["slots"]["payload"] = {"type": "object", "required": True}
    prediction["unknown_slots"].append("payload")
    observation["nodes"][1]["properties"] = {"payload": {"$type": "string"}}
    contract["branches"]["ready"]["required"][0]["bind"] = {"slot": "payload", "field": "properties.payload"}
    contract["branches"]["ready"]["required"].append({"id": "postbound", "select": {"role": "list", "name": {"$slot": "payload"}}})
    result = validate(contract, prediction, observation)
    assert result["verdict"] == "fail"
    assert any(row["id"] == "postbound" and row["verdict"] == "fail" and row["stage"] == "observation_binding" for row in result["checks"])
