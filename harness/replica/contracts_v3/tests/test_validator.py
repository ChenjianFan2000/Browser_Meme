"""Generic representation controls; no website source, locators or browser."""
from copy import deepcopy

import pytest

from harness.replica.contracts_v3.schema import commit_prediction
from harness.replica.contracts_v3.validator import render, validate


def fixture(count=2):
    contract = {"schema": "component-contract/v3", "parameters": {"$type": "object"}, "slots": {},
        "coverage": ["container", "dom_rows", "ax_rows", "representations"], "branches": {"ready": {"required": [
            {"id": "container", "select": {"source": "dom", "tag": "UL"}},
            {"id": "dom_rows", "scope": "container", "select": {"source": "dom", "tag": "LI"}, "count": {"min": 0},
             "each": {"slots": {"title": {"type": "string"}}, "required": [
                 {"id": "title", "select": {"source": "dom", "tag": "A"}, "bind": {"slot": "title", "field": "text"}},
                 {"id": "toggle", "select": {"source": "dom", "tag": "BUTTON", "properties": {"pressed": False}}}]}},
            {"id": "ax_rows", "select": {"source": "ax", "role": "listitem"}, "count": {"min": 0}}],
            "relations": [{"id": "representations", "kind": "same_dom_set", "left": "dom_rows", "right": "ax_rows"}]}}}
    prediction = {"disposition": "accepted", "contract_ref": "fixture", "branch": "ready", "parameters": {}, "unknown_slots": ["dom_rows.*.title"]}
    nodes = [{"id": "dom-root", "parent": None, "source": "dom", "tag": "UL"},
             {"id": "ax-root", "parent": None, "source": "ax", "role": "list", "name": "Results", "backend_dom_id": "dom-root"}]
    for index in range(count):
        nodes += [{"id": f"dom-{index}", "parent": "dom-root", "source": "dom", "tag": "LI"},
                  {"id": f"title-{index}", "parent": f"dom-{index}", "source": "dom", "tag": "A", "text": f"External {index}"},
                  {"id": f"button-{index}", "parent": f"dom-{index}", "source": "dom", "tag": "BUTTON", "properties": {"pressed": False}},
                  {"id": f"ax-{index}", "parent": "ax-root", "source": "ax", "role": "listitem", "name": f"External {index}", "backend_dom_id": f"dom-{index}"}]
    observation = {"schema": "component-observation/v1", "complete": True, "evidence_refs": ["independent-generic-capture.json"], "nodes": nodes}
    return contract, prediction, observation


def assess(count=2, mutate=None):
    contract, prediction, observation = fixture(count)
    if mutate:
        mutate(contract, prediction, observation)
    return validate(contract, prediction, observation, commitment=commit_prediction(prediction))


@pytest.mark.parametrize("count", [0, 1, 4])
def test_same_frozen_shape_accepts_zero_one_many(count):
    result = assess(count)
    assert result["schema"] == "component-contract-assessment/v3"
    assert result["verdict"] == "pass"
    assert result["evaluation_instances"]["dom_rows"]["evaluated_instances"] == count
    assert len(result["bindings"]["dom_rows.each"]) == count
    assert result["evaluation_instances"]["dom_rows"]["child_passes"] == count * 3


def test_zero_children_are_not_applicable_not_passed():
    result = assess(0)
    assert result["evaluation_instances"]["dom_rows"] == {"evaluated_instances": 0, "child_passes": 0,
        "child_failures": 0, "child_unknown": 0, "children_status": "not_applicable"}
    assert not any(row["id"].startswith("dom_rows[") for row in result["checks"])
    na = next(row for row in result["checks"] if row["id"] == "dom_rows/each")
    assert na["verdict"] == "not_applicable" and na["child_passes"] == 0
    assert result["observation_binding_score"]["passed"] == 0
    relation = next(row for row in result["checks"] if row["id"] == "representations")
    assert relation["verdict"] == "pass" and relation["evaluated_instances"] == 0


def test_zero_parents_still_require_action_prior_unknown_slot_declaration():
    result = assess(0, lambda c, p, o: p.update(unknown_slots=[]))
    assert result["verdict"] == "unknown"
    assert any(row["reason"] == "required_local_unknown_not_declared_before_action" for row in result["checks"])
    assert result["evaluation_instances"]["dom_rows"]["child_passes"] == 0


@pytest.mark.parametrize("change", [
    lambda c: c["branches"]["ready"]["required"][1].pop("scope"),
    lambda c: c["branches"]["ready"]["required"][0].update(count={"min": 0}),
    lambda c: c["branches"]["ready"]["required"][0]["select"].update(tag={"$slot": "late"}),
])
def test_zero_each_without_independent_positive_container_is_unknown(change):
    assert assess(0, lambda c, p, o: change(c))["verdict"] == "unknown"


def test_missing_positive_container_does_not_make_empty_success():
    assert assess(0, lambda c, p, o: o.update(nodes=[n for n in o["nodes"] if n["id"] != "dom-root"]))["verdict"] == "fail"


def test_known_nonempty_minimum_still_fails_on_zero():
    assert assess(0, lambda c, p, o: c["branches"]["ready"]["required"][1].update(count={"min": 1}))["verdict"] == "fail"


def test_missing_ax_rows_is_identity_set_failure():
    result = assess(2, lambda c, p, o: o.update(nodes=[n for n in o["nodes"] if n["source"] != "ax"]))
    assert result["verdict"] == "fail"
    assert next(r for r in result["checks"] if r["id"] == "representations")["reason"] == "DOM_identity_set_contradiction"


def test_wrong_resolved_bridge_is_fail_not_positional_match():
    def change(c, p, o):
        next(n for n in o["nodes"] if n["id"] == "ax-0")["backend_dom_id"] = "dom-root"
    assert assess(2, change)["verdict"] == "fail"


def test_permuted_ax_order_uses_identity_sets():
    def change(c, p, o):
        o["nodes"] = list(reversed(o["nodes"]))
    assert assess(3, change)["verdict"] == "pass"


@pytest.mark.parametrize("identity", [None, 10, "/frame/dom-unresolved/7", "@removed-execution-content", "unmapped-dom-path"])
def test_unresolved_identity_is_unknown(identity):
    def change(c, p, o):
        next(n for n in o["nodes"] if n["id"] == "ax-0")["backend_dom_id"] = identity
    assert assess(1, change)["verdict"] == "unknown"


def test_single_dom_node_identity_relation():
    def change(c, p, o):
        c["branches"]["ready"]["relations"][0]["kind"] = "same_dom_node"
    assert assess(1, change)["verdict"] == "pass"
    assert assess(2, change)["verdict"] == "unknown"


def test_wrong_child_state_and_parent_still_fail():
    assert assess(1, lambda c, p, o: next(n for n in o["nodes"] if n["id"] == "button-0")["properties"].update(pressed=True))["verdict"] == "fail"
    assert assess(2, lambda c, p, o: next(n for n in o["nodes"] if n["id"] == "button-0").update(parent="dom-1"))["verdict"] == "fail"


def test_external_titles_can_change_without_prediction_rewrite():
    c, p, o = fixture(3)
    prior = deepcopy(p)
    for node in o["nodes"]:
        if node.get("tag") == "A":
            node["text"] = "New input " + node["id"]
    assert validate(c, p, o, commitment=commit_prediction(p))["verdict"] == "pass"
    assert p == prior


def test_slot_dependent_relation_gets_only_postbinding_credit():
    c, p, o = fixture(1)
    c["slots"] = {"wanted": {"type": "string"}}
    c["branches"]["ready"]["required"][0]["bind"] = {"slot": "wanted", "field": "id"}
    p["unknown_slots"].append("wanted")
    c["branches"]["ready"]["required"].append({"id": "bound_container", "select": {"source": "dom", "tag": "UL", "id": {"$slot": "wanted"}}})
    c["branches"]["ready"]["relations"].append({"id": "postbound", "kind": "same_dom_node", "left": "container", "right": "bound_container"})
    result = validate(c, p, o)
    assert result["verdict"] == "pass"
    assert next(r for r in result["checks"] if r["id"] == "postbound")["stage"] == "observation_binding"


def test_render_exports_full_namespaced_unknown_declarations():
    contract, _, _ = fixture(0)
    rendered = render(contract, {}, branch="ready")
    assert rendered["schema"] == "symbolic-component-tree/v3"
    assert rendered["unknown_slots"] == ["dom_rows.*.title"]
    assert rendered["prediction_contract"] == contract


def test_duplicate_ax_to_one_dom_identity_is_unknown():
    def change(c, p, o):
        duplicate = deepcopy(next(n for n in o["nodes"] if n["id"] == "ax-0"))
        duplicate["id"] = "ax-duplicate"
        o["nodes"].append(duplicate)
    result = assess(1, change)
    assert result["verdict"] == "unknown"
    relation = next(row for row in result["checks"] if row["id"] == "representations")
    assert relation["reason"] == "ambiguous_duplicate_DOM_identity"
