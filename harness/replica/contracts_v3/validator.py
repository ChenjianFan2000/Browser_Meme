"""Independent, fail-closed matching of frozen component contracts to observations."""
from __future__ import annotations

from copy import deepcopy

from .schema import (OBSERVATION_SCHEMA, SchemaError, UnknownValue, commit_prediction,
                     get_path, has_slot, literal_equal, local_contract, matches, resolve, slot_paths, slot_pattern, validate_contract)

NODE_FIELDS = {"id", "parent", "source", "role", "name", "properties", "attributes", "tag",
               "text", "visible", "identity", "ignored", "description", "value", "backend_dom_id", "url"}


def _score(checks, stage):
    rows = [row for row in checks if row["stage"] == stage]
    return {"passed": sum(row["verdict"] == "pass" for row in rows), "failed": sum(row["verdict"] == "fail" for row in rows),
            "unknown": sum(row["verdict"] == "unknown" for row in rows),
            "not_applicable": sum(row["verdict"] == "not_applicable" for row in rows), "total": len(rows)}


def validate(contract, prediction, observation, *, commitment=None):
    """Never mutate prior predictions; observed bindings are a separate result channel.

    A controller must persist commitment before action execution. This function
    checks the digest, not wall-clock provenance, which belongs to that controller.
    """
    checks, bindings, selected, selected_stages, evaluation_instances = [], {}, {}, {}, {}

    def add(identifier, verdict, reason, *, stage="prediction", **extra):
        checks.append({"id": identifier, "verdict": verdict, "reason": reason, "stage": stage, **extra})

    def result():
        verdicts = [row["verdict"] for row in checks]
        verdict = "fail" if "fail" in verdicts else "unknown" if "unknown" in verdicts or not checks else "pass"
        covered = [row["id"] for row in checks if row["id"] in contract.get("coverage", [])]
        return {"schema": "component-contract-assessment/v3", "verdict": verdict, "checks": checks,
                "bindings": bindings, "coverage": {"declared": contract.get("coverage", []), "evaluated": covered,
                "nonempty": bool(covered)}, "prediction_score": _score(checks, "prediction"),
                "observation_binding_score": _score(checks, "observation_binding"),
                "evaluation_instances": evaluation_instances,
                "prediction_sha256": commit_prediction(prediction), "commitment_verified": commitment is not None and commitment == commit_prediction(prediction)}

    if not isinstance(contract, dict) or not isinstance(prediction, dict):
        return {"schema": "component-contract-assessment/v3", "verdict": "unknown", "checks": [{"id": "schema", "verdict": "unknown", "reason": "contract_and_prediction_must_be_objects", "stage": "prediction"}], "bindings": {}}
    try:
        validate_contract(contract)
    except (SchemaError, TypeError, KeyError, ValueError) as error:
        add("schema", "unknown", str(error))
        return result()
    if commitment is not None and commitment != commit_prediction(prediction):
        add("prediction_integrity", "fail", "prediction_rewritten")
        return result()
    if prediction.get("disposition") not in {"accepted", "rejected"}:
        add("disposition", "unknown", "unknown_or_missing_predicted_disposition")
        return result()
    if not isinstance(prediction.get("contract_ref"), str) or not prediction["contract_ref"]:
        add("contract_ref", "unknown", "missing_contract_ref")
    parameters = prediction.get("parameters")
    if not isinstance(parameters, dict):
        add("parameters", "unknown", "missing_parameters_object")
        return result()
    try:
        pattern = resolve(contract.get("parameters", {"$type": "object"}), parameters, {})
        if not matches(parameters, pattern):
            add("parameters", "unknown", "parameters_do_not_satisfy_declared_shape")
            return result()
    except UnknownValue as error:
        add("parameters", "unknown", str(error))
        return result()
    branch_name = prediction.get("branch")
    if branch_name not in contract["branches"]:
        add("branch", "unknown", "missing_or_unknown_branch")
        return result()
    branch = contract["branches"][branch_name]
    if "when" in branch:
        try:
            if not matches(parameters, resolve(branch["when"], parameters, {})):
                add("branch", "fail", "branch_parameter_precondition_contradiction")
                return result()
        except UnknownValue as error:
            add("branch", "unknown", str(error))
            return result()
    unknown_slots = prediction.get("unknown_slots")
    slots = contract.get("slots", {})
    if not isinstance(unknown_slots, list) or not all(isinstance(item, str) for item in unknown_slots) or len(set(unknown_slots)) != len(unknown_slots):
        add("unknown_slots", "unknown", "unknown_slots_must_be_unique_names")
        return result()
    if set(unknown_slots) - slot_paths(contract, branch_name):
        add("unknown_slots", "unknown", "undeclared_unknown_slot")
    for name, spec in slots.items():
        if spec.get("required", True) and name not in unknown_slots:
            add("slot:" + name, "unknown", "required_unknown_not_declared_before_action", stage="observation_binding")
    for claim in branch.get("required", []):
        for local_name, spec in claim.get("each", {}).get("slots", {}).items():
            name = claim["id"] + ".*." + local_name
            if spec.get("required", True) and name not in unknown_slots:
                add("slot:" + name, "unknown", "required_local_unknown_not_declared_before_action", stage="observation_binding")
    if not isinstance(observation, dict) or observation.get("schema") != OBSERVATION_SCHEMA or observation.get("complete") is not True or not observation.get("evidence_refs"):
        add("acquisition", "unknown", "incomplete_or_unsupported_observation")
        return result()
    nodes = observation.get("nodes")
    if not isinstance(nodes, list) or any(not isinstance(node, dict) or not isinstance(node.get("id"), str) or "parent" not in node or not isinstance(node.get("source"), str) for node in nodes):
        add("acquisition", "unknown", "malformed_node_graph")
        return result()
    by_id = {node["id"]: node for node in nodes}
    if len(by_id) != len(nodes) or any(node["parent"] is not None and node["parent"] not in by_id for node in nodes):
        add("acquisition", "unknown", "duplicate_identity_or_missing_parent")
        return result()

    def ancestor(child, parent):
        visited = set()
        current = child.get("parent")
        while current is not None:
            if current in visited:
                raise UnknownValue("cyclic_observation_graph")
            visited.add(current)
            if current == parent["id"]:
                return True
            current = by_id[current].get("parent")
        return False

    try:
        for node in nodes:
            ancestor(node, {"id": "@cycle-detection-sentinel"})
    except UnknownValue as error:
        add("acquisition", "unknown", str(error))
        return result()

    for kind in ("required", "forbidden"):
        for claim in branch.get(kind, []):
            identifier = claim["id"]
            stage = "observation_binding" if has_slot(claim["select"]) or has_slot(claim.get("has", [])) or selected_stages.get(claim.get("scope")) == "observation_binding" else "prediction"
            selected_stages[identifier] = stage
            error_identifier, error_stage = identifier, stage
            try:
                selector = resolve(claim["select"], parameters, bindings)
                if set(selector) - NODE_FIELDS:
                    raise UnknownValue("unsupported_selector_fields:" + ",".join(sorted(set(selector) - NODE_FIELDS)))
                if "role" in selector and "source" not in selector:
                    selector = {**selector, "source": "ax"}
                candidates = nodes
                scope = claim.get("scope")
                if scope is not None:
                    parents = selected.get(scope)
                    if parents is None or len(parents) != 1:
                        raise UnknownValue("scope_missing_or_ambiguous:" + str(scope))
                    candidates = [node for node in candidates if ancestor(node, parents[0])]
                hits = [node for node in candidates if matches(node, selector)]
                for predicate in claim.get("has", []):
                    descendant_selector = resolve(predicate["select"], parameters, bindings)
                    if set(descendant_selector) - NODE_FIELDS:
                        raise UnknownValue("unsupported_has_selector_fields")
                    if "role" in descendant_selector and "source" not in descendant_selector:
                        descendant_selector = {**descendant_selector, "source": "ax"}
                    limits = predicate.get("count", {"min": 1})
                    filtered = []
                    for parent in hits:
                        descendant_count = sum(node.get("source") == parent.get("source") and ancestor(node, parent) and matches(node, descendant_selector) for node in nodes)
                        if descendant_count >= limits.get("min", 0 if "max" in limits else 1) and ("max" not in limits or descendant_count <= limits["max"]):
                            filtered.append(parent)
                    hits = filtered
                selected[identifier] = hits
                count = claim.get("count", {"min": 1, "max": 1})
                passed = not hits if kind == "forbidden" else len(hits) >= count.get("min", 1) and ("max" not in count or len(hits) <= count["max"])
                add(identifier, "pass" if passed else "fail", "structure_matched" if passed else "forbidden_present" if kind == "forbidden" else "required_count_or_state_mismatch", stage=stage,
                    matched_ids=[node["id"] for node in hits], matched_count=len(hits))
                bind = claim.get("bind")
                if bind is not None and passed:
                    name = bind["slot"]
                    error_identifier, error_stage = "bind:" + name, "observation_binding"
                    if name not in unknown_slots:
                        raise UnknownValue("binding_not_declared_before_action:" + name)
                    if bind.get("many", False):
                        value = [deepcopy(get_path(node, bind["field"])) for node in hits]
                    else:
                        if len(hits) != 1:
                            raise UnknownValue("binding_ambiguous:" + name)
                        value = deepcopy(get_path(hits[0], bind["field"]))
                    if not matches(value, slot_pattern(slots[name])):
                        add("bind:" + name, "fail", "observed_slot_type_mismatch", stage="observation_binding")
                    elif name in bindings and not literal_equal(bindings[name], value):
                        add("bind:" + name, "fail", "observed_slot_identity_conflict", stage="observation_binding")
                    else:
                        bindings[name] = value
                        add("bind:" + name, "pass", "external_value_bound_after_observation", stage="observation_binding")
                if "each" in claim and passed:
                    each_rows = []
                    local_check_start = len(checks)
                    local = local_contract(claim["each"], contract.get("parameters", {"$type": "object"}))
                    local_unknowns = [name[len(identifier) + 3:] for name in unknown_slots if name.startswith(identifier + ".*.")]
                    for parent in hits:
                        current = deepcopy(local)
                        current["branches"]["local"]["required"][0]["select"] = {"id": parent["id"]}
                        local_nodes = [deepcopy(node) for node in nodes if node["id"] == parent["id"] or node.get("source") == parent.get("source") and ancestor(node, parent)]
                        for node in local_nodes:
                            if node["id"] == parent["id"]:
                                node["parent"] = None
                        local_prediction = {"disposition": prediction["disposition"], "contract_ref": prediction["contract_ref"] + ":" + identifier,
                            "branch": "local", "parameters": deepcopy(parameters), "unknown_slots": local_unknowns}
                        checked = validate(current, local_prediction, {**observation, "nodes": local_nodes}, commitment=commit_prediction(local_prediction))
                        for row in checked["checks"]:
                            if row["id"] == "$parent":
                                continue
                            row = deepcopy(row)
                            row["id"] = identifier + "[" + parent["id"] + "]/" + row["id"]
                            if stage == "observation_binding":
                                row["stage"] = stage
                            checks.append(row)
                        each_rows.append({"parent_id": parent["id"], "bindings": checked["bindings"], "verdict": checked["verdict"]})
                    bindings[identifier + ".each"] = each_rows
                    child_checks = checks[local_check_start:]
                    evaluation_instances[identifier] = {"evaluated_instances": len(hits),
                        "child_passes": sum(row["verdict"] == "pass" for row in child_checks),
                        "child_failures": sum(row["verdict"] == "fail" for row in child_checks),
                        "child_unknown": sum(row["verdict"] == "unknown" for row in child_checks),
                        "children_status": "evaluated" if hits else "not_applicable"}
                    if not hits:
                        add(identifier + "/each", "not_applicable", "zero_parent_instances_no_child_checks", stage=stage,
                            evaluated_instances=0, child_passes=0)
            except UnknownValue as error:
                add(error_identifier, "unknown", str(error), stage=error_stage)
    for relation in branch.get("relations", []):
        left, right = selected.get(relation.get("left")), selected.get(relation.get("right"))
        stage = "observation_binding" if any(selected_stages.get(relation.get(side)) == "observation_binding" for side in ("left", "right")) else "prediction"
        if relation["kind"] in {"same_dom_set", "same_dom_node"}:
            if left is None or right is None:
                add(relation["id"], "unknown", "DOM_relation_endpoints_not_evaluated", stage=stage)
                continue
            if relation["kind"] == "same_dom_node" and (len(left) != 1 or len(right) != 1):
                add(relation["id"], "unknown", "DOM_singleton_identity_ambiguous", stage=stage)
                continue
            try:
                def dom_identity(node):
                    identity = node.get("id") if node.get("source") == "dom" else node.get("backend_dom_id") if node.get("source") == "ax" else None
                    if not isinstance(identity, str) or not identity or any(marker in identity for marker in ("/dom-unresolved/", "@removed-execution-content", "unresolved", "@missing")):
                        raise UnknownValue("unresolved_DOM_identity")
                    target = by_id.get(identity)
                    if target is None or target.get("source") != "dom":
                        raise UnknownValue("DOM_identity_not_in_captured_canonical_map")
                    return identity
                left_values = [dom_identity(node) for node in left]
                right_values = [dom_identity(node) for node in right]
                left_ids, right_ids = set(left_values), set(right_values)
                if len(left_ids) != len(left_values) or len(right_ids) != len(right_values):
                    raise UnknownValue("ambiguous_duplicate_DOM_identity")
                passed = left_ids == right_ids
                add(relation["id"], "pass" if passed else "fail", "DOM_identity_sets_match" if passed else "DOM_identity_set_contradiction", stage=stage,
                    evaluated_instances=len(left_ids | right_ids), left_dom_ids=sorted(left_ids), right_dom_ids=sorted(right_ids))
            except UnknownValue as error:
                add(relation["id"], "unknown", str(error), stage=stage)
            continue
        if not left or not right or relation.get("quantifier", "one") == "one" and (len(left) != 1 or len(right) != 1):
            add(relation["id"], "unknown", "relation_endpoints_missing_or_ambiguous", stage=stage)
            continue
        def related(a, b):
            return {"parent": lambda: a["parent"] == b["id"], "ancestor": lambda: ancestor(a, b),
                    "same": lambda: a["id"] == b["id"], "different": lambda: a["id"] != b["id"]}[relation["kind"]]()
        if relation.get("quantifier") == "each":
            passed = all(any(related(a, b) for b in right) for a in left)
        else:
            passed = all(related(a, b) for a in left for b in right)
        add(relation["id"], "pass" if passed else "fail", "relation_matched" if passed else "relation_contradiction", stage=stage)
    for name, spec in slots.items():
        if spec.get("required", True) and name not in bindings:
            add("slot:" + name, "unknown", "required_slot_unbound", stage="observation_binding")
    if not any(row["id"] in contract["coverage"] for row in checks):
        add("coverage", "unknown", "declared_coverage_not_evaluated_in_selected_branch")
    return result()


def render(contract, inputs, *, branch=None):
    """Export a symbolic component tree; this does not construct a browser replica."""
    validate_contract(contract)
    if branch is None:
        if len(contract["branches"]) != 1:
            raise SchemaError("branch is required for a multibranch render")
        branch = next(iter(contract["branches"]))
    if branch not in contract["branches"]:
        raise SchemaError("unknown branch")
    slots = contract.get("slots", {})
    missing_parameters = []
    try:
        inputs_valid = isinstance(inputs, dict) and matches(inputs, resolve(contract.get("parameters", {"$type": "object"}), inputs, {}))
    except UnknownValue:
        inputs_valid = False

    def symbolic(value):
        if isinstance(value, dict):
            if "$slot" in value:
                name = value["$slot"]
                return {"$unknown": {"slot": name, "type": slots.get(name.split(".")[0], {}).get("type", "undeclared")}}
            if "$param" in value:
                try:
                    return deepcopy(get_path(inputs, value["$param"]))
                except UnknownValue:
                    missing_parameters.append(value["$param"])
                    return {"$unknown": {"parameter": value["$param"]}}
            return {key: symbolic(item) for key, item in value.items()}
        if isinstance(value, list):
            return [symbolic(item) for item in value]
        return deepcopy(value)

    tree = symbolic(contract["branches"][branch].get("tree", {}))
    return {"schema": "symbolic-component-tree/v3", "branch": branch, "parameters": deepcopy(inputs),
            "status": "ready" if inputs_valid and not missing_parameters else "unknown",
            "input_validation": {"verdict": "pass" if inputs_valid else "unknown", "reason": "parameters_satisfy_declared_shape" if inputs_valid else "parameters_do_not_satisfy_declared_shape"},
            "unknown_parameters": sorted(set(missing_parameters)), "tree": tree,
            "prediction_contract": deepcopy(contract), "unknown_slots": sorted(slot_paths(contract, branch)),
            "scope": "parameterized component structure; not a complete website replica"}
