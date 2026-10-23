"""Public canonical DOM + AX observation, without control-plane state.

The public-dom-v2 projection is frozen byte-for-byte from runner.py and guarded
by parity tests. Security redaction is independent of that projection and never
weakens the comparator. This module accepts canonical observations only.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json

try:
    from .observation import redact
except ImportError:
    from observation import redact

PROJECTION_POLICY = {"id": "public-dom-v2", "remove": ["SCRIPT elements", "on* attributes", "srcdoc", "javascript: active attributes"],
                     "javascript_url_attributes": ["href","src","action","formaction","xlink:href","data"],
                     "retain": ["style and CSS nodes", "head metadata except declared removals", "resource nodes except SCRIPT", "dynamic business text", "control values and states", "hierarchy", "frame relationships"]}


def _public_projection(canonical):
    """Apply the frozen public policy to actual canonical fields and references."""
    value = deepcopy(canonical)
    paths = {}
    def strip(node, old, new):
        if not isinstance(node, dict):
            return node
        if str(node.get("nodeName", "")).upper() == "SCRIPT":
            paths[old] = "@removed-execution-content"
            return None
        paths[old] = new
        node = deepcopy(node)
        if "attributes" in node:
            node["attributes"] = {k:v for k,v in node["attributes"].items() if not k.lower().startswith("on") and k.lower() != "srcdoc" and not (k.lower() in PROJECTION_POLICY["javascript_url_attributes"] and isinstance(v,str) and v.lstrip().lower().startswith("javascript:"))}
        if "urls" in node:
            node["urls"] = {k:v for k,v in node["urls"].items() if not (isinstance(v,str) and v.lstrip().lower().startswith("javascript:"))}
        children = []
        for index, child in enumerate(node.get("children", [])):
            retained = strip(child, f"{old}/children/{index}", f"{new}/children/{len(children)}")
            if retained is not None:
                children.append(retained)
        node["children"] = children
        for key in ("shadowRoot", "templateContent"):
            if key in node:
                node[key] = strip(node[key], old + "/" + key, new + "/" + key)
        return node
    for frame in value.get("frames", []):
        root = frame["key"] + "/document"
        frame["document"] = strip(frame.get("document"), root, root)
    def remap(path):
        if not isinstance(path, str):
            return path
        for old in sorted(paths, key=len, reverse=True):
            if path == old or path.startswith(old + "/"):
                return paths[old] + path[len(old):]
        return path
    def refs(item):
        if isinstance(item, dict):
            return {k:remap(v) if k == "backendDOMNodeId" else refs(v) for k,v in item.items()}
        if isinstance(item, list):
            return [refs(v) for v in item]
        return item
    for frame in value.get("frames", []):
        frame["owner"] = remap(frame.get("owner"))
        if frame.get("activeElementPath"):
            full = remap(frame["key"] + "/" + frame["activeElementPath"])
            frame["activeElementPath"] = full.removeprefix(frame["key"] + "/")
        frame["ax"] = refs(frame.get("ax", []))
    return value


SCHEMA = "public-browser-tree/v1"
EXECUTION_URL_POLICY = {
    "id": "public-ax-execution-url-redaction/v1",
    "remove": "javascript: code bodies in CDP AX properties named url",
    "replacement": "[EXECUTION URL REMOVED]",
    "retain": "all fields, node relationships, ordering, and non-executable values",
    "comparison_scope": "additional public-observation security layer; not part of the existing v2 AX comparator",
}


def public_execution_projection(value):
    """Remove executable URL bodies from public AX and canonical observations.

    CDP Accessibility exposes javascript: link targets as URL property values.
    Removing the DOM href alone does not remove this independent code channel.
    Raw private capture and registered comparisons are deliberately unaffected.
    """
    if isinstance(value, dict):
        result = {key: public_execution_projection(item) for key, item in value.items()}
        if value.get("name") == "url" and isinstance(value.get("value"), dict):
            url = value["value"].get("value")
            if isinstance(url, str) and url.lstrip().lower().startswith("javascript:"):
                result["value"]["value"] = EXECUTION_URL_POLICY["replacement"]
        return result
    if isinstance(value, list):
        return [public_execution_projection(item) for item in value]
    return value


def security_projection_metadata():
    digest = hashlib.sha256((inspect.getsource(public_execution_projection) +
                            json.dumps(EXECUTION_URL_POLICY, sort_keys=True)).encode()).hexdigest()
    return {**EXECUTION_URL_POLICY, "sha256": digest}


def projection_metadata():
    """Same digest construction as the independent comparison registration."""
    digest = hashlib.sha256((inspect.getsource(_public_projection) +
                            json.dumps(PROJECTION_POLICY, sort_keys=True)).encode()).hexdigest()
    return {**PROJECTION_POLICY, "sha256": digest}


def _secret_values(canonical):
    """Defense in depth: discover secret control values within captured DOM.

    Values remain private to this function. Length/selection/empty-state are
    visible control properties under the current protocol; actual values are not.
    """
    result = set()
    def visit(node):
        if not isinstance(node, dict):
            return
        attributes = {key.lower(): value for key, value in node.get("attributes", {}).items()}
        kind = " ".join(str(attributes.get(key, "")) for key in ("type", "name", "autocomplete")).lower()
        secret = node.get("nodeName", "").upper() in {"INPUT", "TEXTAREA"} and any(
            word in kind for word in ("password", "token", "secret"))
        if secret:
            for value in (attributes.get("value"), node.get("live", {}).get("value")):
                if isinstance(value, str) and value:
                    result.add(value)
        for child in node.get("children", []):
            visit(child)
        for key in ("shadowRoot", "templateContent"):
            visit(node.get(key))
    for frame in canonical.get("frames", []):
        visit(frame.get("document"))
    return result


def export_snapshot(canonical, *, secrets=()):
    """Expose only the canonical public tree, with a matching projection digest.

    The caller passes the same capture used for its private canonical record.
    This function neither captures again nor reads Storage/network/oracle data.
    It never changes the private capture or a registered comparison result.
    """
    if not isinstance(canonical, dict) or "frames" not in canonical or "raw" in canonical:
        raise ValueError("public snapshot requires a canonical tree")
    if any("dom" in frame or "cdp_dom" in frame or "document" not in frame
           for frame in canonical["frames"]):
        raise ValueError("raw frame data must not be exported as canonical")
    allowed = {name: canonical[name] for name in
               ("schema", "policy", "environment", "frames", "unsupported") if name in canonical}
    # Canonical frames have a fixed contract; reject accidental control-plane
    # attachments instead of silently copying them into the learner workspace.
    frame_fields = {"key", "parent", "owner", "url", "name", "document", "activeElementPath", "ax"}
    if any(set(frame) - frame_fields for frame in allowed["frames"]):
        raise ValueError("public snapshot contains unregistered frame fields")
    secret_values = set(secrets) | _secret_values(allowed)
    tree = public_execution_projection(_public_projection(redact(allowed, secrets=secret_values)))
    return {"schema": SCHEMA, "projection": projection_metadata(),
            "security_projection": security_projection_metadata(),
            "security": {"secret_control_values": "redacted", "control_selection": "retained",
                         "network_and_storage": "not_exported"}, "tree": tree}
