"""One-level each-parent and descendant predicates, extending frozen v1."""
from copy import deepcopy

from harness.replica.contracts_v1.schema import *  # Shared literal matching; v1 bytes remain frozen.
from harness.replica.contracts_v1.schema import validate_contract as validate_v1

CONTRACT_SCHEMA = "component-contract/v2"


def local_contract(each, parameters):
    required = deepcopy(each.get("required", []))
    forbidden = deepcopy(each.get("forbidden", []))
    for claim in required + forbidden:
        claim.setdefault("scope", "$parent")
    return {"schema": CONTRACT_SCHEMA, "parameters": deepcopy(parameters), "slots": deepcopy(each.get("slots", {})),
            "coverage": [item["id"] for item in required + forbidden + each.get("relations", [])] or ["$parent"],
            "branches": {"local": {"required": [{"id": "$parent", "select": {"id": "$parent-placeholder"}}, *required],
                "forbidden": forbidden, "relations": deepcopy(each.get("relations", []))}}}


def slot_paths(contract, branch):
    result = set(contract.get("slots", {}))
    for claim in contract["branches"][branch].get("required", []):
        for slot in claim.get("each", {}).get("slots", {}):
            result.add(claim["id"] + ".*." + slot)
    return result


def validate_contract(contract):
    if not isinstance(contract, dict) or contract.get("schema") != CONTRACT_SCHEMA:
        raise SchemaError("unsupported component contract v2 schema")
    stripped = deepcopy(contract)
    stripped["schema"] = "component-contract/v1"
    for branch in stripped.get("branches", {}).values():
        for kind in ("required", "forbidden"):
            for claim in branch.get(kind, []):
                has = claim.pop("has", [])
                if not isinstance(has, list):
                    raise SchemaError("has must be an array")
                for predicate in has:
                    if not isinstance(predicate, dict) or set(predicate) - {"select", "count"}:
                        raise SchemaError("unsupported has semantics")
                    select = predicate.get("select")
                    if not isinstance(select, dict) or not select or not meaningful(select):
                        raise SchemaError("has needs nonvacuous descendant selector")
                    validate_pattern(select)
                    count = predicate.get("count", {"min": 1})
                    if not isinstance(count, dict) or set(count) - {"min", "max"} or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in count.values()):
                        raise SchemaError("invalid has count")
                    if "max" in count and count["max"] < count.get("min", 0):
                        raise SchemaError("inverted has count")
                each = claim.pop("each", None)
                if each is not None:
                    if kind != "required" or not isinstance(each, dict) or set(each) - {"required", "forbidden", "relations", "slots"}:
                        raise SchemaError("each supports required/forbidden/relations/slots on required parents")
                    if not each.get("required") and not each.get("forbidden") and not each.get("relations"):
                        raise SchemaError("empty each is prohibited")
                    if claim.get("count", {"min": 1}).get("min", 1) < 1:
                        raise SchemaError("each requires positive parent minimum; declare an independent empty branch")
                    if not each.get("required") and not each.get("forbidden"):
                        raise SchemaError("each requires a real local structural claim beyond the synthetic parent")
                    for local in each.get("required", []) + each.get("forbidden", []):
                        if local.get("id") == "$parent" or "each" in local:
                            raise SchemaError("nested each and reserved $parent ids are unsupported")
                    validate_contract(local_contract(each, contract.get("parameters", {"$type": "object"})))
    validate_v1(stripped)
    return contract
