"""Small declarative JSON patterns for independently observed component contracts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

CONTRACT_SCHEMA = "component-contract/v1"
OBSERVATION_SCHEMA = "component-observation/v1"
TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
OPERATORS = {"$type", "$const", "$enum", "$properties", "$required", "$forbidden",
             "$additional", "$items", "$minItems", "$maxItems", "$min", "$max", "$anyOf"}


class SchemaError(ValueError):
    pass


class UnknownValue(ValueError):
    pass


def commit_prediction(prediction):
    """Hash JSON bytes, not a mutable object reference held until after execution."""
    value = json.dumps(prediction, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_path(value, path):
    if path in ("", None):
        return value
    for key in str(path).split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            raise UnknownValue("missing path: " + str(path))
    return value


def resolve(value, parameters, bindings):
    """Resolve pattern references as exact data, never as injected operators."""
    if isinstance(value, dict):
        if "$param" in value or "$slot" in value:
            if len(value) != 1:
                raise SchemaError("reference must be the only object key")
            key = "$param" if "$param" in value else "$slot"
            return {"$const": deepcopy(get_path(parameters if key == "$param" else bindings, value[key]))}
        return {key: deepcopy(item) if key in {"$const", "$enum"} else resolve(item, parameters, bindings) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, parameters, bindings) for item in value]
    return value


def has_slot(value):
    if isinstance(value, dict):
        return "$slot" in value or any(has_slot(item) for item in value.values())
    return isinstance(value, list) and any(has_slot(item) for item in value)


def is_type(value, kind):
    return {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
            "string": lambda: isinstance(value, str), "number": lambda: isinstance(value, (float, int)) and not isinstance(value, bool),
            "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
            "boolean": lambda: isinstance(value, bool), "null": lambda: value is None}[kind]()


def validate_pattern(pattern):
    if isinstance(pattern, list):
        for item in pattern:
            validate_pattern(item)
    elif isinstance(pattern, dict):
        refs = set(pattern) & {"$param", "$slot"}
        if refs:
            if len(pattern) != 1 or not isinstance(pattern[next(iter(refs))], str):
                raise SchemaError("reference must contain one string path")
            return
        operators = {key for key in pattern if key.startswith("$")}
        if operators - OPERATORS:
            raise SchemaError("unknown pattern operators: " + str(sorted(operators - OPERATORS)))
        if operators and set(pattern) - OPERATORS:
            raise SchemaError("use $properties for fields in an operator pattern")
        if "$type" in pattern and pattern["$type"] not in TYPES:
            raise SchemaError("unsupported JSON type")
        for key in ("$required", "$forbidden"):
            if key in pattern and (not isinstance(pattern[key], list) or not all(isinstance(x, str) for x in pattern[key])):
                raise SchemaError(key + " must be a list of property names")
        if "$additional" in pattern and not isinstance(pattern["$additional"], bool):
            raise SchemaError("$additional must be boolean")
        if "$properties" in pattern:
            if not isinstance(pattern["$properties"], dict):
                raise SchemaError("$properties must be an object")
            for item in pattern["$properties"].values():
                validate_pattern(item)
        if "$items" in pattern:
            validate_pattern(pattern["$items"])
        if "$anyOf" in pattern:
            if not isinstance(pattern["$anyOf"], list) or not pattern["$anyOf"]:
                raise SchemaError("$anyOf must be nonempty")
            for item in pattern["$anyOf"]:
                validate_pattern(item)
        if "$enum" in pattern and (not isinstance(pattern["$enum"], list) or not pattern["$enum"]):
            raise SchemaError("$enum must be nonempty")
        for key in ("$minItems", "$maxItems"):
            if key in pattern and (not isinstance(pattern[key], int) or isinstance(pattern[key], bool) or pattern[key] < 0):
                raise SchemaError(key + " must be a nonnegative integer")
        for key in ("$min", "$max"):
            if key in pattern and not is_type(pattern[key], "number"):
                raise SchemaError(key + " must be numeric")
        if not operators:
            for item in pattern.values():
                validate_pattern(item)


def matches(value, pattern):
    """Exact literals and partial objects; $additional:false opts into exact keys."""
    if isinstance(pattern, dict):
        if not any(key.startswith("$") for key in pattern):
            return isinstance(value, dict) and all(key in value and matches(value[key], item) for key, item in pattern.items())
        if "$type" in pattern and not is_type(value, pattern["$type"]):
            return False
        if "$const" in pattern and not literal_equal(value, pattern["$const"]):
            return False
        if "$enum" in pattern and not any(literal_equal(value, item) for item in pattern["$enum"]):
            return False
        if "$anyOf" in pattern and not any(matches(value, item) for item in pattern["$anyOf"]):
            return False
        if any(key in pattern for key in ("$properties", "$required", "$forbidden", "$additional")):
            if not isinstance(value, dict):
                return False
            if any(key not in value for key in pattern.get("$required", [])) or any(key in value for key in pattern.get("$forbidden", [])):
                return False
            properties = pattern.get("$properties", {})
            if any(key in value and not matches(value[key], item) for key, item in properties.items()):
                return False
            if pattern.get("$additional") is False and set(value) - set(properties):
                return False
        if any(key in pattern for key in ("$items", "$minItems", "$maxItems")):
            if not isinstance(value, list):
                return False
            if len(value) < pattern.get("$minItems", 0) or ("$maxItems" in pattern and len(value) > pattern["$maxItems"]):
                return False
            if "$items" in pattern and not all(matches(item, pattern["$items"]) for item in value):
                return False
        if any(key in pattern for key in ("$min", "$max")):
            if not is_type(value, "number"):
                return False
            if ("$min" in pattern and value < pattern["$min"]) or ("$max" in pattern and value > pattern["$max"]):
                return False
        return True
    if isinstance(pattern, list):
        return isinstance(value, list) and len(value) == len(pattern) and all(matches(a, b) for a, b in zip(value, pattern))
    return literal_equal(value, pattern)


def literal_equal(left, right):
    # Python otherwise equates True, 1 and 1.0; JSON state booleans stay distinct.
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, dict) or isinstance(right, dict):
        return isinstance(left, dict) and isinstance(right, dict) and set(left) == set(right) and all(literal_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) or isinstance(right, list):
        return isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and all(literal_equal(a, b) for a, b in zip(left, right))
    return left == right


def meaningful(value):
    """Reject wildcard-only anchors. Unknown slot references never establish prior coverage."""
    if isinstance(value, dict):
        if "$slot" in value:
            return False
        if "$param" in value or "$const" in value:
            return True
        if "$enum" in value:
            return bool(value["$enum"])
        return any(meaningful(item) for key, item in value.items() if not key.startswith("$") and key != "source")
    if isinstance(value, list):
        return bool(value) and any(meaningful(item) for item in value)
    return value is not None


def slot_pattern(spec):
    value = {"$type": spec["type"]}
    for key, target in (("items", "$items"), ("properties", "$properties"), ("required_properties", "$required")):
        if key in spec:
            value[target] = spec[key]
    return value


def validate_contract(contract):
    if not isinstance(contract, dict) or contract.get("schema") != CONTRACT_SCHEMA:
        raise SchemaError("unsupported component contract schema")
    allowed_contract = {"schema", "parameters", "slots", "branches", "coverage", "description", "source_refs", "version", "id"}
    if set(contract) - allowed_contract:
        raise SchemaError("unsupported contract fields: " + str(sorted(set(contract) - allowed_contract)))
    validate_pattern(contract.get("parameters", {"$type": "object"}))
    slots = contract.get("slots", {})
    if not isinstance(slots, dict):
        raise SchemaError("slots must be an object")
    for name, spec in slots.items():
        if not isinstance(name, str) or not isinstance(spec, dict) or spec.get("type") not in TYPES:
            raise SchemaError("slots need names and supported types")
        if set(spec) - {"type", "items", "properties", "required_properties", "required", "description", "source"}:
            raise SchemaError("unsupported slot semantics")
        if "required" in spec and not isinstance(spec["required"], bool):
            raise SchemaError("slot required must be boolean")
        if "source" in spec and spec["source"] != "observation":
            raise SchemaError("slots must derive from independent observation")
        validate_pattern(slot_pattern(spec))
    branches = contract.get("branches")
    if not isinstance(branches, dict) or not branches:
        raise SchemaError("branches must be nonempty")
    all_ids = set()
    for branch in branches.values():
        if not isinstance(branch, dict):
            raise SchemaError("branch must be an object")
        if set(branch) - {"required", "forbidden", "relations", "tree", "when", "description", "source_refs"}:
            raise SchemaError("unsupported branch fields")
        if "when" in branch:
            validate_pattern(branch["when"])
        ids = set()
        anchors = 0
        for kind in ("required", "forbidden"):
            if not isinstance(branch.get(kind, []), list):
                raise SchemaError("claims must be arrays")
            for claim in branch.get(kind, []):
                if not isinstance(claim, dict) or not isinstance(claim.get("id"), str) or claim["id"] in ids:
                    raise SchemaError("claim ids must be unique strings per branch")
                ids.add(claim["id"])
                if set(claim) - {"id", "select", "scope", "count", "bind", "description", "source_refs"}:
                    raise SchemaError("unsupported structural claim semantics")
                selector = claim.get("select")
                if not isinstance(selector, dict) or not selector or not meaningful(selector):
                    raise SchemaError("vacuous wildcard selector is prohibited")
                validate_pattern(selector)
                count = claim.get("count", {"min": 1, "max": 1})
                if not isinstance(count, dict) or set(count) - {"min", "max"}:
                    raise SchemaError("invalid count")
                if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in count.values()):
                    raise SchemaError("count bounds must be nonnegative integers")
                if "max" in count and count["max"] < count.get("min", 0):
                    raise SchemaError("inverted count bounds")
                anchors += kind == "required" and count.get("min", 1) > 0 and not has_slot(selector)
                bind = claim.get("bind")
                if bind is not None and (kind != "required" or not isinstance(bind, dict) or bind.get("slot") not in slots or not isinstance(bind.get("field"), str)):
                    raise SchemaError("bind must name a declared slot and node field")
                if bind is not None and (set(bind) - {"slot", "field", "many"} or "many" in bind and not isinstance(bind["many"], bool)):
                    raise SchemaError("unsupported binding semantics")
        if not isinstance(branch.get("relations", []), list):
            raise SchemaError("relations must be an array")
        for relation in branch.get("relations", []):
            if not isinstance(relation, dict) or set(relation) - {"id", "kind", "left", "right", "quantifier", "description", "source_refs"}:
                raise SchemaError("unsupported relation semantics")
            if relation.get("id") in ids or not isinstance(relation.get("id"), str):
                raise SchemaError("relation id must be unique")
            if relation.get("kind") not in {"parent", "ancestor", "same", "different"}:
                raise SchemaError("unknown relation semantics")
            if relation.get("quantifier", "one") not in {"one", "each", "all"}:
                raise SchemaError("unknown relation quantifier")
            ids.add(relation["id"])
        if not anchors:
            raise SchemaError("each branch requires positive predictive structural coverage")
        all_ids.update(ids)
    coverage = contract.get("coverage")
    if not isinstance(coverage, list) or not coverage or not all(isinstance(x, str) for x in coverage) or set(coverage) - all_ids:
        raise SchemaError("coverage must name a nonempty set of existing checks")
    return contract
