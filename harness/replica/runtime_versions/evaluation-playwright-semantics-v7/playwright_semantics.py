"""Versioned Playwright DOM-derived semantic capture, separate from native AX.

Captures are sequential, not atomic. The independent lane's bounded sampling and
final checkpoint compare the full DOM/AX plus this auxiliary record together.
No opposite-lane state, target business rules, or application source is read.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

SCHEMA = "playwright-script-semantics/v1"
POLICY = {
    "id": "playwright-dom-derived-default/v1",
    "playwright_version": "1.62.0",
    "core_bundle_sha256": "3258d1cf334c6afc95f22aa9c292436cb976b391e0437f1359c83b84f0cb9d66",
    "mode": "default", "depth": None, "boxes": False, "refs": "none",
    "root": "body", "frame_scope": "all attached same-origin frames; complete raw-capture topology",
    "snapshot_timeout_ms": 2000,
    "comparison": "exact complete rendered strings after declared URL-field-only normalization",
    "url_normalization": "only renderer /url scalar fields and explicit frame.url; unsafe syntax or data URL rejected",
    "security_projection": "only explicit /url scalar with lstrip and case-insensitive javascript: scheme becomes javascript:[REDACTED_EXECUTABLE_URL]; business names/text remain exact; private raw auxiliary keeps executable URL, secrets separately redacted",
    "long_name_guard": "all fixed valid roles queried with the same Playwright accessible-name algorithm; any normalized name longer than 900 UTF-16 units is unsupported",
    "capture_order": "one full DOM/Chromium AX capture then frame semantics; sequential, not atomic; combined consecutive stability and final recheck",
    "losses": ["DOM-derived, not native Chromium AX or complete assistive-technology equivalence",
               "whitespace normalization and nameless roleless containers may be folded",
               "focus and selection omitted here; full DOM/live properties remain mandatory",
               "partial role states; false and missing markers can coincide",
               "description and complete relation/identity graph omitted; full DOM and action identity remain mandatory",
               "native AX frame-owner paths retained conservatively; no arbitrary topology normalization"],
}
SEMANTICS_POLICY = POLICY
_URL_LINE = re.compile(r"^( *)- /url: (.*)$")
_LONG_NAME = re.compile(r"^[\s\S]{901,}$")


def _url(value, roots):
    for origin, replacement in sorted(roots.items(), key=lambda pair: -len(pair[0])):
        origin = origin.rstrip("/")
        if value == origin or value.startswith(origin) and value[len(origin):len(origin)+1] in ("/", "?", "#"):
            return replacement.rstrip("/") + value[len(origin):]
    return value


def normalize_snapshot_urls(snapshot, roots):
    """Normalize only unambiguous official-renderer /url property scalars.

    Names and text are never searched/replaced. Unrecognized quoted/escape forms
    are rejected rather than interpreted permissively or compared as equal.
    """
    if not isinstance(snapshot, str):
        raise ValueError("snapshot must be a complete string")
    result = []
    for line in snapshot.split("\n"):
        match = _URL_LINE.fullmatch(line)
        if not match:
            result.append(line)
            continue
        indent, scalar = match.groups()
        if len(indent) % 2 or not scalar:
            raise ValueError("unsupported URL scalar layout")
        if scalar.startswith('"'):
            try:
                value = json.loads(scalar)
            except (ValueError, TypeError) as error:
                raise ValueError("unsupported URL scalar escaping") from error
            if not isinstance(value, str):
                raise ValueError("URL scalar is not a string")
        else:
            if scalar[0] in "'&*],?!>|@#%[{`" or scalar != scalar.strip() or re.search(r":\s|\s#|[\x00-\x1f]", scalar):
                raise ValueError("unsupported plain URL scalar")
            value = scalar
        if value.lstrip().lower().startswith("data:"):
            raise ValueError("data URL may be truncated by Playwright")
        if value.lstrip().lower().startswith("javascript:"):
            value = "javascript:[REDACTED_EXECUTABLE_URL]"
        result.append(indent + "- /url: " + json.dumps(_url(value, roots), ensure_ascii=False))
    return "\n".join(result)


def canonical_semantics(record, roots=None):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("policy") != POLICY:
        raise ValueError("unregistered semantic schema/policy")
    if record.get("status") not in {"confirmed", "unconfirmed"} or not isinstance(record.get("unsupported"), list):
        raise ValueError("invalid semantic capture status")
    if record["status"] == "confirmed" and record["unsupported"]:
        raise ValueError("unsupported capture cannot be confirmed")
    frames, seen = [], set()
    if not isinstance(record.get("frames"), list):
        raise ValueError("missing frame coverage")
    for frame in record["frames"]:
        required = {"key", "parent", "owner", "url", "name", "root", "snapshot"}
        if set(frame) != required or frame["key"] in seen or frame["root"] != "body":
            raise ValueError("unregistered or duplicate semantic frame")
        if frame["parent"] is not None and frame["parent"] not in seen:
            raise ValueError("semantic parent topology is incomplete")
        seen.add(frame["key"])
        frames.append({**frame, "url": _url(frame["url"], roots or {}),
                       "snapshot": normalize_snapshot_urls(frame["snapshot"], roots or {})})
    if record["status"] == "confirmed" and (not frames or frames[0]["key"] != "f0" or frames[0]["parent"] is not None):
        raise ValueError("confirmed capture needs complete root frame")
    return {"schema": SCHEMA, "policy": deepcopy(POLICY), "status": record["status"],
            "frames": frames, "unsupported": deepcopy(record["unsupported"])}


@lru_cache(maxsize=1)
def _verify_dependency():
    import playwright
    if importlib.metadata.version("playwright") != POLICY["playwright_version"]:
        raise RuntimeError("unregistered Playwright version")
    bundle = Path(playwright.__file__).parent / "driver/package/lib/coreBundle.js"
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != POLICY["core_bundle_sha256"]:
        raise RuntimeError("unregistered Playwright injected implementation")
    roles = json.loads((Path(__file__).with_name("SEMANTICS_ROLES.json")).read_text())
    if not roles or len(set(roles)) != len(roles):
        raise RuntimeError("invalid frozen supported-role inventory")
    return roles


def _frames(page):
    result = []
    def visit(frame):
        result.append(frame)
        for child in frame.child_frames:
            visit(child)
    visit(page.main_frame)
    return result


def _origin(url):
    value = urlsplit(url)
    return value.scheme, value.hostname, value.port or (443 if value.scheme == "https" else 80)


def capture_semantics(page, raw, *, origin, aria_snapshot=None):
    record = {"schema": SCHEMA, "policy": deepcopy(POLICY), "status": "unconfirmed",
              "frames": [], "unsupported": [], "timing": {"long_name_guard_seconds": 0.0}}
    started = time.monotonic()
    try:
        roles = _verify_dependency()
        frames = _frames(page)
        originals = raw["frames"]
        if len(frames) != len(originals):
            raise RuntimeError("frame topology changed during sequential acquisition")
        for index, (frame, original) in enumerate(zip(frames, originals)):
            key = "f" + str(index)
            if original["key"] != key or frame.url != original["url"] or frame.name != original.get("name", ""):
                raise RuntimeError("frame identity changed during sequential acquisition")
            if _origin(frame.url) != _origin(origin):
                record["unsupported"].append({"kind": "unsupported_frame_origin", "frame": key})
                continue
            root = frame.locator("body")
            if root.count() != 1:
                record["unsupported"].append({"kind": "missing_or_multiple_body", "frame": key})
                continue
            guard_started = time.monotonic()
            long_names = None
            for role in roles:
                locator = frame.get_by_role(role, name=_LONG_NAME, include_hidden=False)
                long_names = locator if long_names is None else long_names.or_(locator)
            count = long_names.count()
            record["timing"]["long_name_guard_seconds"] += time.monotonic() - guard_started
            if count:
                record["unsupported"].append({"kind": "accessible_name_exceeds_900", "frame": key, "count": count})
                continue
            snapshot_method = aria_snapshot or type(root).aria_snapshot
            snapshot = snapshot_method(root, mode="default", depth=None, boxes=False,
                                       timeout=POLICY["snapshot_timeout_ms"])
            normalize_snapshot_urls(snapshot, {})  # Fail closed before accepting ambiguous URL syntax.
            record["frames"].append({"key": key, "parent": original["parent"], "owner": original["owner"],
                                      "url": original["url"], "name": original.get("name", ""),
                                      "root": "body", "snapshot": snapshot})
        if [id(frame) for frame in _frames(page)] != [id(frame) for frame in frames]:
            record["unsupported"].append({"kind": "frame_topology_changed_after_acquisition"})
        for original in raw.get("unsupported", []):
            record["unsupported"].append({"kind": "dom_ax_capture_unsupported", "detail": original})
        if not record["unsupported"] and len(record["frames"]) == len(originals):
            record["status"] = "confirmed"
    except Exception as error:
        record["unsupported"].append({"kind": "semantic_capture_error", "error_type": type(error).__name__})
    record["timing"]["elapsed_seconds"] = time.monotonic() - started
    return record


def capture_checkpoint(page, *, origin, aria_snapshot=None):
    from trees import capture
    start = time.monotonic()
    snapshot = capture(page)
    elapsed = time.monotonic() - start
    snapshot["semantics"] = capture_semantics(page, snapshot["raw"], origin=origin, aria_snapshot=aria_snapshot)
    for issue in snapshot["canonical"].get("unsupported", []):
        item = {"kind": "dom_ax_capture_unsupported", "detail": issue}
        if item not in snapshot["semantics"]["unsupported"]:
            snapshot["semantics"]["unsupported"].append(item)
    if snapshot["semantics"]["unsupported"]:
        snapshot["semantics"]["status"] = "unconfirmed"
    snapshot["semantics"]["timing"]["full_dom_ax_seconds"] = elapsed
    return snapshot


def signature_payload(snapshot):
    from trees import canonicalize
    semantic = canonical_semantics(snapshot["semantics"], {})
    dom_ax = canonicalize(snapshot["raw"])
    return {"dom_ax": dom_ax, "playwright_semantics": semantic,
            "unsupported": dom_ax.get("unsupported", []) + semantic["unsupported"]}


def sanitize_record(record, secrets):
    """Redact raw and JSON/YAML-escaped forms before private persistence."""
    from observation import redact
    variants = set(secrets)
    for secret in secrets:
        if secret:
            variants.add(json.dumps(secret, ensure_ascii=False)[1:-1])
            variants.add(json.dumps(secret, ensure_ascii=True)[1:-1])
    return redact(record, secrets=sorted(variants, key=len, reverse=True))
