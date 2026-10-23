"""Project the existing frozen runtime's captured trees; no browser or site logic."""
from __future__ import annotations

import json
from pathlib import Path

from ..runner_playwright import _public_projection


def _value(value):
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def project(canonical, *, evidence_refs, url=None):
    public = _public_projection(canonical)
    nodes = []

    def dom(node, node_id, parent):
        if not isinstance(node, dict):
            return
        item = {"id": node_id, "identity": node_id, "parent": parent,
                "source": "dom", "tag": node.get("nodeName"),
                "attributes": node.get("attributes", {}), "properties": node.get("live", {})}
        if "text" in node:
            item["text"] = node["text"]
        if "urls" in node:
            item["urls"] = node["urls"]
        nodes.append(item)
        for index, child in enumerate(node.get("children", [])):
            dom(child, f"{node_id}/children/{index}", node_id)
        for field in ("shadowRoot", "templateContent"):
            if field in node:
                dom(node[field], node_id + "/" + field, node_id)

    for frame in public.get("frames", []):
        dom(frame.get("document"), frame["key"] + "/document", None)
        for node in frame.get("ax", []):
            item = {"id": node["nodeId"], "parent": node.get("parentId"), "source": "ax",
                    "identity": node.get("backendDOMNodeId", node["nodeId"]),
                    "properties": {p["name"]: _value(p.get("value")) for p in node.get("properties", [])}}
            for field in ("role", "name", "description", "value", "ignored"):
                if field in node:
                    item[field] = _value(node[field])
            if "backendDOMNodeId" in node:
                item["backend_dom_id"] = node["backendDOMNodeId"]
            nodes.append(item)
    return {"schema": "component-observation/v1", "complete": bool(public.get("frames")) and not public.get("unsupported"),
            "nodes": nodes, "evidence_refs": list(evidence_refs), "url": url,
            "unsupported": public.get("unsupported", []),
            "scope": "Existing captured Chromium DOM and AX nodes; no inferred component roles or business facts."}


def load_checkpoint(record):
    observed = record.get("observation", {})
    result = {"schema": "component-observation/v1", "complete": False, "nodes": [], "evidence_refs": []}
    try:
        stem = Path(observed["dom"]).stem
        directory = Path(record["private_trees_directory"]) / stem
        canonical_path = directory / "canonical.json"
        canonical = json.loads(canonical_path.read_text())
        semantics_path = directory / "playwright-semantics.json"
        semantics = json.loads(semantics_path.read_text())
        result = project(canonical, evidence_refs=[str(canonical_path), str(semantics_path)], url=observed.get("url"))
        stability = record.get("stability", {})
        result["complete"] = bool(result["complete"] and semantics.get("status") == "confirmed"
                                  and stability.get("enabled") is True and stability.get("status") == "stable"
                                  and not observed.get("error") and record.get("status") not in {"unconfirmed", "terminated"})
        result["collection"] = {"semantics_status": semantics.get("status"), "stability": stability}
    except (KeyError, OSError, ValueError, TypeError) as error:
        result["collection_error"] = type(error).__name__ + ": " + str(error)
    return result
