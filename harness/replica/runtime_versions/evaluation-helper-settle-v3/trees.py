"""Site-independent, loss-conscious Chromium DOM/AX snapshot comparison.

Policy: retain every observable node, child order, text (including whitespace and
script/style text), attribute and captured live property. Only explicitly supplied
URL roots and protocol-generated identifiers are canonicalized. HTML ``id`` and
ARIA IDREF attributes are business data and are never rewritten. Attribute order
is immaterial; child order is material. Open shadow roots, template contents and
all Playwright frames are captured. Closed shadow roots and acquisition errors
make a snapshot unsupported, never an exact pass. Canvas pixels, CSS layout and
browser-native internals are outside this tree metric (use screenshots separately).

Use the same Chromium build, viewport, locale/timezone and settled application
state for both captures. Capture is sequential, not an atomic browser transaction;
the caller must quiesce animations/network and record its waiting policy.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "replica-trees/v1"
POLICY = {
    "attributes": "all; unordered attribute map; no ignore list",
    "text": "exact, including whitespace/comments/script/style",
    "children": "ordered; open shadow and template content retained",
    "ids": "protocol IDs mapped bijectively; HTML IDs unchanged",
    "urls": "explicit root mappings in frame URL, scalar URL attributes/resolved DOM properties and AX url properties; text, scripts, CSS and URL lists remain exact",
    "unsupported": "closed shadow, inaccessible frame or failed acquisition prevents exact pass",
    "scope": "DOM and Chromium AX; excludes rendered pixels, CSS layout and native internals",
}

_DOM_SCRIPT = r"""() => {
  function path(node) {
    if (node === document) return 'document';
    if (node instanceof ShadowRoot) return path(node.host) + '/shadowRoot';
    const parent = node.parentNode;
    if (!parent) return null;
    return path(parent) + '/children/' + Array.prototype.indexOf.call(parent.childNodes, node);
  }
  function walk(node) {
    const out = {nodeType: node.nodeType, nodeName: node.nodeName};
    if (node.nodeType === Node.DOCUMENT_TYPE_NODE) {
      out.publicId = node.publicId; out.systemId = node.systemId;
    }
    if (node.nodeValue !== null) out.text = node.nodeValue;
    if (node.nodeType === Node.ELEMENT_NODE) {
      out.namespaceURI = node.namespaceURI;
      out.attributes = Object.fromEntries(Array.from(node.attributes, a => [a.name, a.value]));
      out.live = {focused: node === node.getRootNode().activeElement};
      for (const prop of ['value', 'checked', 'selected', 'disabled', 'indeterminate',
                          'readOnly', 'multiple', 'selectedIndex', 'selectionStart',
                          'selectionEnd', 'selectionDirection', 'open', 'hidden']) {
        if (prop in node) {
          try { const value = node[prop];
            if (value === null || ['string', 'boolean', 'number'].includes(typeof value)) out.live[prop] = value;
          } catch (error) { out.live[prop] = {error: error.name}; }
        }
      }
      out.urls = {};
      for (const prop of ['href', 'src', 'action', 'formAction', 'poster', 'data', 'cite']) {
        if (prop in node && typeof node[prop] === 'string') out.urls[prop] = node[prop];
      }
      if (node.shadowRoot) {
        out.shadowRoot = walk(node.shadowRoot);
        out.shadowRoot.mode = node.shadowRoot.mode;
        out.shadowRoot.delegatesFocus = node.shadowRoot.delegatesFocus;
      }
      if (node instanceof HTMLTemplateElement) out.templateContent = walk(node.content);
    }
    out.children = Array.from(node.childNodes, walk);
    return out;
  }
  return {document: walk(document), url: location.href,
    environment: {user_agent: navigator.userAgent, locale: navigator.language,
      languages: Array.from(navigator.languages), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      viewport: {width: innerWidth, height: innerHeight}, device_pixel_ratio: devicePixelRatio},
    activeElementPath: path(document.activeElement)};
}"""

_OWNER_SCRIPT = r"""node => {
  function path(n) {
    if (n === document) return 'document';
    if (n instanceof ShadowRoot) return path(n.host) + '/shadowRoot';
    if (!n.parentNode) return null;
    return path(n.parentNode) + '/children/' + Array.prototype.indexOf.call(n.parentNode.childNodes, n);
  }
  return path(node);
}"""


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _url(value: str, roots: Mapping[str, str]) -> str:
    """Map a URL prefix only at a path/query/fragment boundary, longest first."""
    for root, alias in sorted(roots.items(), key=lambda item: -len(item[0])):
        root = root.rstrip("/")
        if value == root or (value.startswith(root) and value[len(root):len(root) + 1] in ("/", "?", "#")):
            return alias.rstrip("/") + value[len(root):]
    return value


_URL_ATTRS = {"href", "src", "action", "formaction", "poster", "data", "cite", "longdesc", "background", "manifest", "xlink:href"}


def _dom_canonical(node: dict, roots: Mapping[str, str]) -> dict:
    out = deepcopy(node)
    for name, value in out.get("attributes", {}).items():
        if name.lower() in _URL_ATTRS:
            # Relative URL spelling remains exact; resolved values are captured too.
            out["attributes"][name] = _url(value, roots)
    out["urls"] = {key: _url(value, roots) for key, value in out.get("urls", {}).items()} if "urls" in out else out.get("urls")
    if out.get("urls") is None:
        out.pop("urls", None)
    out["children"] = [_dom_canonical(child, roots) for child in out.get("children", [])]
    for key in ("shadowRoot", "templateContent"):
        if key in out:
            out[key] = _dom_canonical(out[key], roots)
    return out


def _cdp_paths(document: dict, frame_key: str, frame_ids: Mapping[str, str], backend: dict, owners: dict, unsupported: list) -> None:
    def walk(node: dict, path: str, current: str) -> None:
        if "backendNodeId" in node:
            backend[str(node["backendNodeId"])] = f"{current}/{path}"
        if node.get("frameId") and node.get("nodeName") != "#document":
            owners[f"{current}/{path}"] = node["frameId"]
        for index, child in enumerate(node.get("children", [])):
            walk(child, f"{path}/children/{index}", current)
        for index, shadow in enumerate(node.get("shadowRoots", [])):
            kind = shadow.get("shadowRootType")
            if kind == "closed":
                unsupported.append({"kind": "closed_shadow_root", "path": f"{current}/{path}"})
            # Chromium's user-agent shadow roots are browser-native internals,
            # outside the declared DOM scope. Their AX nodes are still retained.
            shadow_path = f"{path}/shadowRoot" if kind == "open" else f"{path}/{kind}Shadow/{index}"
            walk(shadow, shadow_path, current)
        if node.get("templateContent"):
            walk(node["templateContent"], f"{path}/templateContent", current)
        if node.get("contentDocument"):
            child_key = frame_ids.get(node.get("frameId"))
            if child_key:
                walk(node["contentDocument"], "document", child_key)
    walk(document, "document", frame_key)


def _ax_canonical(nodes: list[dict], frame_key: str, frame_ids: Mapping[str, str], backend: Mapping[str, str], roots: Mapping[str, str]) -> list[dict]:
    by_id = {str(node["nodeId"]): node for node in nodes}
    ids: dict[str, str] = {}

    def visit(node_id: str) -> None:
        node_id = str(node_id)
        if node_id in ids:
            return
        ids[node_id] = f"{frame_key}/ax/{len(ids)}"
        for child_id in by_id.get(node_id, {}).get("childIds", []):
            visit(str(child_id))

    for node in nodes:
        if str(node.get("parentId", "")) not in by_id:
            visit(str(node["nodeId"]))
    for node in nodes:
        visit(str(node["nodeId"]))
    unknown_backend: dict[str, str] = {}

    def rewrite(value: Any, key: str = "") -> Any:
        if key in ("nodeId", "parentId"):
            raw_id = str(value)
            if raw_id not in ids:
                ids[raw_id] = f"{frame_key}/ax/external/{len(ids)}"
            return ids[raw_id]
        if key == "childIds":
            return [rewrite(item, "nodeId") for item in value]
        if key == "backendDOMNodeId":
            raw_id = str(value)
            if raw_id in backend:
                return backend[raw_id]
            if raw_id not in unknown_backend:
                unknown_backend[raw_id] = f"{frame_key}/dom-unresolved/{len(unknown_backend)}"
            return unknown_backend[raw_id]
        if key == "frameId":
            return frame_ids.get(str(value), f"unresolved-frame:{value}")
        if isinstance(value, dict):
            result = {name: rewrite(item, name) for name, item in value.items()}
            return result
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        return value

    ranks = {node_id: index for index, node_id in enumerate(ids)}
    ordered = sorted(nodes, key=lambda node: ranks[str(node["nodeId"])])
    result = [rewrite(node) for node in ordered]
    # AX URL is normally a property named url, not the accessible name.
    for node in result:
        for prop in node.get("properties", []):
            if prop.get("name") == "url" and isinstance(prop.get("value", {}).get("value"), str):
                prop["value"]["value"] = _url(prop["value"]["value"], roots)
    return result


def canonicalize(raw: dict, url_roots: Mapping[str, str] | None = None) -> dict:
    """Canonicalize raw capture without mutating it; useful for audited replay."""
    roots = dict(url_roots or {})
    frame_ids = {frame["cdp_frame_id"]: frame["key"] for frame in raw["frames"] if frame.get("cdp_frame_id")}
    # BackendNodeIds are renderer scoped: OOP frames can allocate the same integer
    # as the main renderer. Never merge these maps across CDP frame captures.
    backend_by_frame: dict[str, dict[str, str]] = {}
    unsupported = deepcopy(raw.get("unsupported", []))
    for frame in raw["frames"]:
        backend: dict[str, str] = {}
        if frame.get("cdp_dom"):
            _cdp_paths(frame["cdp_dom"], frame["key"], frame_ids, backend, {}, unsupported)
        backend_by_frame[frame["key"]] = backend
    frames = []
    for frame in raw["frames"]:
        frames.append({
            "key": frame["key"], "parent": frame["parent"], "owner": frame["owner"],
            "url": _url(frame["url"], roots), "name": frame.get("name", ""),
            "document": _dom_canonical(frame["dom"], roots) if frame.get("dom") else None,
            "activeElementPath": frame.get("activeElementPath"),
            "ax": _ax_canonical(frame.get("ax", []), frame["key"], frame_ids, backend_by_frame[frame["key"]], roots),
        })
    # Duplicate closed-shadow reports may occur when a parent CDP document also
    # includes the child frame document. Collapse identical reports only.
    unsupported = list({json.dumps(item, sort_keys=True): item for item in unsupported}.values())
    return {"schema": SCHEMA, "policy": POLICY, "environment": deepcopy(raw["environment"]), "frames": frames, "unsupported": unsupported}


def capture(page: Any, *, url_roots: Mapping[str, str] | None = None, output_dir: str | Path | None = None) -> dict:
    """Capture a synchronous Playwright Chromium Page; write raw + canonical JSON.

    Requires CDP, hence intentionally Chromium-only. Never silently substitutes
    DOM-derived accessibility for the browser's Accessibility.getFullAXTree.
    """
    raw: dict[str, Any] = {"schema": SCHEMA, "environment": {}, "frames": [], "unsupported": []}
    context = page.context
    session = context.new_cdp_session(page)
    try:
        session.send("DOM.enable", {"includeWhitespace": "all"})
        tree = session.send("Page.getFrameTree")["frameTree"]
        raw["cdp_frame_tree"] = tree
        main_id = tree["frame"]["id"]
        main_dom = session.send("DOM.getDocument", {"depth": -1, "pierce": True})["root"]
        browser = context.browser
        raw["environment"]["browser_version"] = browser.version if browser else None
        raw["environment"].update(page.evaluate(_DOM_SCRIPT)["environment"])
        frame_objects = []

        def collect(frame: Any) -> None:
            frame_objects.append(frame)
            for child in frame.child_frames:
                collect(child)

        collect(page.main_frame)
        frame_keys = {id(frame): f"f{index}" for index, frame in enumerate(frame_objects)}
        known_ids = {main_id: "f0"}
        owner_ids: dict[str, str] = {}
        _cdp_paths(main_dom, "f0", known_ids, {}, owner_ids, [])
        for index, frame in enumerate(frame_objects):
            key = frame_keys[id(frame)]
            parent = frame.parent_frame
            owner = None
            frame_id = main_id if index == 0 else None
            frame_session = session
            record: dict[str, Any] = {"key": key, "parent": frame_keys.get(id(parent)), "owner": owner, "url": frame.url, "name": frame.name}
            try:
                if parent:
                    handle = frame.frame_element()
                    try:
                        owner = f"{frame_keys[id(parent)]}/{handle.evaluate(_OWNER_SCRIPT)}"
                    finally:
                        handle.dispose()
                    frame_id = owner_ids.get(owner)
                    try:
                        frame_session = context.new_cdp_session(frame)
                        frame_session.send("DOM.enable", {"includeWhitespace": "all"})
                    except Exception as error:
                        if "does not have a separate CDP session" not in str(error):
                            raise
                        frame_session = session
                record.update({"owner": owner, "cdp_frame_id": frame_id})
                data = frame.evaluate(_DOM_SCRIPT)
                record.update({"dom": data["document"], "url": data["url"], "activeElementPath": data["activeElementPath"]})
                doc = main_dom if index == 0 else frame_session.send("DOM.getDocument", {"depth": -1, "pierce": True})["root"]
                # A same-process frame CDP session is attached to its page target.
                # Locate its contentDocument rather than mislabelling the main DOM.
                if index:
                    def find_document(node: dict) -> dict | None:
                        if node.get("frameId") == frame_id and node.get("contentDocument"):
                            return node["contentDocument"]
                        for child in node.get("children", []) + node.get("shadowRoots", []):
                            found = find_document(child)
                            if found:
                                return found
                        if node.get("contentDocument"):
                            return find_document(node["contentDocument"])
                        return None
                    own_doc = find_document(doc)
                    if own_doc:
                        doc = own_doc
                    elif doc.get("documentURL") != frame.url:
                        raw["unsupported"].append({"kind": "unresolved_frame_dom", "frame": key})
                record["cdp_dom"] = doc
                if frame_id:
                    known_ids[frame_id] = key
                else:
                    raw["unsupported"].append({"kind": "unresolved_frame_id", "frame": key})
                _cdp_paths(doc, key, known_ids, {}, owner_ids, [])
                parameters = {"frameId": frame_id} if frame_id else {}
                record["ax"] = frame_session.send("Accessibility.getFullAXTree", parameters)["nodes"]
            except Exception as error:
                raw["unsupported"].append({"kind": "capture_error", "frame": key, "error": f"{type(error).__name__}: {error}"})
            finally:
                if frame_session is not session:
                    frame_session.detach()
            raw["frames"].append(record)
    finally:
        session.detach()
    canonical = canonicalize(raw, url_roots)
    snapshot = {"schema": SCHEMA, "raw": raw, "canonical": canonical, "url_roots": dict(url_roots or {})}
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        _write(destination / "raw.json", raw)
        _write(destination / "canonical.json", canonical)
        _write(destination / "normalization.json", {"policy": POLICY, "url_roots": dict(url_roots or {})})
    return snapshot


def _first_difference(expected: Any, actual: Any, path: str = "$") -> dict | None:
    if type(expected) is not type(actual):
        return {"path": path, "kind": "type", "expected": expected, "actual": actual}
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            next_path = f"{path}/{key}"
            if key not in expected or key not in actual:
                return {"path": next_path, "kind": "missing_key", "expected_present": key in expected, "actual_present": key in actual, "expected": expected.get(key), "actual": actual.get(key)}
            difference = _first_difference(expected[key], actual[key], next_path)
            if difference:
                return difference
    elif isinstance(expected, list):
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = _first_difference(left, right, f"{path}/{index}")
            if difference:
                return difference
        if len(expected) != len(actual):
            return {"path": path, "kind": "length", "expected_length": len(expected), "actual_length": len(actual), "expected": expected, "actual": actual}
    elif expected != actual:
        return {"path": path, "kind": "value", "expected": expected, "actual": actual}
    return None


def _subtree(tree: Any, path: str) -> dict:
    """Return the nearest node record enclosing the differing scalar."""
    current = tree
    nearest = tree
    nearest_path = "$"
    traversed = "$"
    for token in path.split("/")[1:]:
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (KeyError, IndexError, TypeError, ValueError):
            break
        traversed += "/" + token
        if isinstance(current, dict) and ("nodeType" in current or "nodeId" in current):
            nearest, nearest_path = current, traversed
    return {"path": nearest_path, "tree": nearest}


def _semantic_features(tree: dict) -> Counter:
    result: Counter = Counter()
    for frame in tree.get("frames", []):
        for node in frame.get("ax", []):
            if not node.get("ignored", False):
                feature = {key: node[key] for key in ("role", "name", "value") if key in node}
                result[json.dumps(feature, sort_keys=True)] += 1
    return result


def compare(expected: dict, actual: dict, *, url_roots: Mapping[str, str] | None = None, output_dir: str | Path | None = None) -> dict:
    """Strict structural comparison, with separately labelled AX semantic overlap.

    Full-tree exact score is binary. Unsupported acquisition cannot pass even when
    two partial captures happen to be equal. Semantic overlap ignores hierarchy
    and is supplemental only; it never changes the exact verdict.
    """
    def canonical(snapshot: dict) -> dict:
        if "raw" in snapshot:
            roots = dict(snapshot.get("url_roots", {}))
            roots.update(url_roots or {})
            return canonicalize(snapshot["raw"], roots)
        if url_roots:
            raise ValueError("URL remapping requires a raw snapshot, not a canonical-only tree")
        return snapshot.get("canonical", snapshot)

    left, right = canonical(expected), canonical(actual)
    difference = _first_difference(left, right)
    unsupported = bool(left.get("unsupported") or right.get("unsupported"))
    exact = difference is None and not unsupported
    a, b = _semantic_features(left), _semantic_features(right)
    total = sum(a.values()) + sum(b.values())
    semantic = 2 * sum((a & b).values()) / total if total else None
    result = {
        "schema": SCHEMA, "exact": exact, "full_tree_exact_score": int(exact),
        "trees_equal": difference is None, "supported": not unsupported,
        "first_difference": difference,
        "difference_subtrees": {"expected": _subtree(left, difference["path"]), "actual": _subtree(right, difference["path"])} if difference else None,
        "supplemental_semantic_score": semantic,
        "semantic_metric": "multiset Dice of non-ignored AX role/name/value records; ignores relationships; not exactness",
        "unsupported": {"expected": left.get("unsupported", []), "actual": right.get("unsupported", [])},
        "normalization": {"policy": POLICY, "expected_url_roots": {**expected.get("url_roots", {}), **dict(url_roots or {})}, "actual_url_roots": {**actual.get("url_roots", {}), **dict(url_roots or {})}},
    }
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        _write(destination / "expected.canonical.json", left)
        _write(destination / "actual.canonical.json", right)
        if "raw" in expected:
            _write(destination / "expected.raw.json", expected["raw"])
        if "raw" in actual:
            _write(destination / "actual.raw.json", actual["raw"])
        _write(destination / "comparison.json", result)
    return result
