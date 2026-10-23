from copy import deepcopy

import pytest

from harness.replica.contracts_v2.schema import commit_prediction
from harness.replica.contracts_v2.validator import validate


def fixture(count=2):
    contract = {"schema": "component-contract/v2", "parameters": {"$type": "object"}, "slots": {}, "coverage": ["root", "rows"],
        "branches": {"ready": {"required": [
            {"id": "root", "select": {"role": "document"}},
            {"id": "rows", "scope": "root", "select": {"role": "row"}, "count": {"min": 1},
             "each": {"slots": {"title": {"type": "string", "required": True}}, "required": [
                 {"id": "title", "select": {"role": "link"}, "bind": {"slot": "title", "field": "name"}},
                 {"id": "toggle", "select": {"role": "button", "name": "Toggle", "properties": {"pressed": False}}}],
                 "forbidden": [{"id": "no-alert", "select": {"role": "alert"}}],
                 "relations": [{"id": "owner", "kind": "parent", "left": "toggle", "right": "$parent"}]}}]}}}
    prediction = {"disposition": "accepted", "contract_ref": "fixture", "branch": "ready", "parameters": {}, "unknown_slots": ["rows.*.title"]}
    nodes = [{"id": "root", "parent": None, "source": "ax", "role": "document", "name": "Fixture"}]
    for i in range(count):
        nodes += [{"id": f"row-{i}", "parent": "root", "source": "ax", "role": "row", "name": ""},
                  {"id": f"link-{i}", "parent": f"row-{i}", "source": "ax", "role": "link", "name": f"External {i}"},
                  {"id": f"toggle-{i}", "parent": f"row-{i}", "source": "ax", "role": "button", "name": "Toggle", "properties": {"pressed": False}}]
    return contract, prediction, {"schema": "component-observation/v1", "complete": True, "evidence_refs": ["fixture.json"], "nodes": nodes}


def assess(count=2, mutate=None):
    c, p, o = fixture(count)
    if mutate:
        mutate(c, p, o)
    return validate(c, p, o, commitment=commit_prediction(p))


@pytest.mark.parametrize("count", [1, 4])
def test_each_one_many_external_rows_pass(count):
    result = assess(count)
    assert result["verdict"] == "pass"
    assert len(result["bindings"]["rows.each"]) == count
    assert result["observation_binding_score"]["passed"] == count
    assert result["prediction_score"]["passed"] == 2 + count * 4


def test_zero_results_require_independent_empty_branch():
    c, p, o = fixture(0)
    c["branches"]["empty"] = {"required": [{"id": "root", "select": {"role": "document"}}],
                                "forbidden": [{"id": "rows", "select": {"role": "row"}}]}
    p.update(branch="empty", unknown_slots=[])
    assert validate(c, p, o)["verdict"] == "pass"
    assert assess(0)["verdict"] == "fail"


def test_each_zero_minimum_is_unknown_not_vacuous_success():
    result = assess(mutate=lambda c, p, o: c["branches"]["ready"]["required"][1].update(count={"min": 0}))
    assert result["verdict"] == "unknown"


@pytest.mark.parametrize("each", [{}, {"slots": {"title": {"type": "string"}}}, {"relations": [{"id": "tautology", "kind": "same", "left": "$parent", "right": "$parent"}]}])
def test_synthetic_parent_cannot_make_empty_each_pass(each):
    result = assess(mutate=lambda c, p, o: c["branches"]["ready"]["required"][1].update(each=each))
    assert result["verdict"] == "unknown"


def test_missing_child_fails_its_parent_not_hidden_by_other_parent():
    result = assess(mutate=lambda c, p, o: o.update(nodes=[n for n in o["nodes"] if n["id"] != "toggle-0"]))
    assert result["verdict"] == "fail"
    assert any(r["id"] == "rows[row-0]/toggle" and r["verdict"] == "fail" for r in result["checks"])


def test_wrong_parent_fails_even_when_global_child_count_is_unchanged():
    result = assess(mutate=lambda c, p, o: next(n for n in o["nodes"] if n["id"] == "toggle-0").update(parent="row-1"))
    assert result["verdict"] == "fail"


def test_wrong_single_row_state_fails():
    result = assess(mutate=lambda c, p, o: next(n for n in o["nodes"] if n["id"] == "toggle-1")["properties"].update(pressed=True))
    assert result["verdict"] == "fail"


def test_dynamic_titles_remain_typed_postobservation_bindings():
    def change(c, p, o):
        for node in o["nodes"]:
            if node["role"] == "link":
                node["name"] = "Unseen value " + node["id"]
    result = assess(3, change)
    assert result["verdict"] == "pass"
    assert result["bindings"]["rows.each"][0]["bindings"]["title"] == "Unseen value link-0"


def test_missing_action_prior_local_unknown_declaration_blocks():
    assert assess(mutate=lambda c, p, o: p.update(unknown_slots=[]))["verdict"] == "unknown"


def test_incomplete_capture_unknown():
    assert assess(mutate=lambda c, p, o: o.update(complete=False))["verdict"] == "unknown"


def test_ambiguous_local_scope_unknown():
    def change(c, p, o):
        each = c["branches"]["ready"]["required"][1]["each"]
        each["required"] += [{"id": "groups", "select": {"role": "group"}, "count": {"min": 1}},
                             {"id": "scoped", "scope": "groups", "select": {"role": "button"}}]
        o["nodes"] += [{"id": f"group-{i}", "parent": "row-0", "source": "ax", "role": "group"} for i in range(2)]
    assert assess(1, change)["verdict"] == "unknown"


def test_has_filters_each_parent_by_literal_parameter_descendants():
    c, p, o = fixture(2)
    row = c["branches"]["ready"]["required"][1]
    row["count"] = {"min": 1, "max": 1}
    row["has"] = [{"select": {"role": "cell", "name": {"$param": "category"}}, "count": {"min": 1, "max": 1}}]
    p["parameters"] = {"category": "Chosen"}
    o["nodes"] += [{"id": "cell-0", "parent": "row-0", "source": "ax", "role": "cell", "name": "Chosen"},
                   {"id": "cell-1", "parent": "row-1", "source": "ax", "role": "cell", "name": "Other"}]
    next(n for n in o["nodes"] if n["id"] == "toggle-1")["properties"]["pressed"] = True
    result = validate(c, p, o, commitment=commit_prediction(p))
    assert result["verdict"] == "pass"
    assert [r["parent_id"] for r in result["bindings"]["rows.each"]] == ["row-0"]


def test_has_count_zero_allows_absence():
    def change(c, p, o):
        c["branches"]["ready"]["required"][1]["has"] = [{"select": {"role": "alert"}, "count": {"min": 0, "max": 0}}]
    assert assess(mutate=change)["verdict"] == "pass"


def test_has_does_not_bridge_source_trees():
    def change(c, p, o):
        row = c["branches"]["ready"]["required"][1]
        row["count"] = {"min": 1}
        row["has"] = [{"select": {"source": "dom", "tag": "INPUT"}}]
        o["nodes"].append({"id": "dom", "parent": "row-0", "source": "dom", "tag": "INPUT"})
    assert assess(1, change)["verdict"] == "fail"


def test_nested_each_is_explicitly_unknown():
    def change(c, p, o):
        c["branches"]["ready"]["required"][1]["each"]["required"][0]["each"] = {"required": []}
    assert assess(mutate=change)["verdict"] == "unknown"


def test_postobservation_prediction_mutation_still_rejected():
    c, p, o = fixture()
    commitment = commit_prediction(p)
    p["parameters"]["late"] = "observed"
    assert validate(c, p, o, commitment=commitment)["verdict"] == "fail"
