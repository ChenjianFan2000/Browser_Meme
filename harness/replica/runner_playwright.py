"""Preregistered v3 script continuity; full Chromium AX/raw remain diagnostic.

Independent lanes run the identical native script. Mandatory gates are full
public DOM, exact Playwright-derived semantics, independent business facts,
action identity and bounded local acquisition. No V2 result is reinterpreted.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import uuid
import inspect
import importlib.metadata
import importlib.util
import sys

SCHEMA = "replica-script-continuity/v3"
MODE = "playwright_script_continuity"
SEMANTICS_SCHEMA = "playwright-script-semantics/v1"
STABILITY_VERSION = "single-lane-dom-ax-playwright/v2"
PLAYWRIGHT_VERSION = "1.62.0"
PLAYWRIGHT_BUNDLE_SHA256 = "3258d1cf334c6afc95f22aa9c292436cb976b391e0437f1359c83b84f0cb9d66"
ARIA_LIMITS = {"origin":"DOM/ARIA/CSS-derived Playwright snapshot; not native Chromium AX or an assistive-technology full tree",
    "snapshot":"Playwright 1.62.0 default mode, unlimited depth, no refs/boxes; exact complete rendered string",
    "whitespace":"Playwright normalizes whitespace; exact comparison is of the declared derived snapshot",
    "names":"Playwright omits names longer than 900 UTF-16 code units; detected name omission/truncation is unsupported and cannot pass",
    "focus_and_live_properties":"not fully represented by snapshot; full public DOM separately retains focus, input values, selections and captured live properties",
    "relations":"not a complete relation/ID/description graph; original ARIA attributes remain in full public DOM and actions retain resolved identities",
    "frames":"each supported frame separately captured with topology retained; raw owner paths compared conservatively",
    "urls":"only explicitly parsed URL fields use registered origin mappings and the frozen executable-URL security projection; names and business text never rewritten"}
PROJECTION_POLICY = {"id": "public-dom-v2", "remove": ["SCRIPT elements", "on* attributes", "srcdoc", "javascript: active attributes"],
                     "javascript_url_attributes": ["href","src","action","formaction","xlink:href","data"],
                     "retain": ["style and CSS nodes", "head metadata except declared removals", "resource nodes except SCRIPT", "dynamic business text", "control values and states", "hierarchy", "frame relationships"]}
ACTION_SCHEMA = {"required": ["method", "action_arguments", "action_identity"], "arguments": ["args", "kwargs"], "identity": "runtime resolved element identity plus owner/method/target; independent oracle checks logical objects"}

try:
    from . import monitor, transport, trees, resource_guard
except ImportError:
    import monitor
    import transport
    import trees
    import resource_guard


def _sha(value):
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _atomic(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def _file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _freeze_dependencies(frozen, semantics_module):
    """Freeze own code and fingerprint the actual SDK/engine dependency bytes."""
    directory = frozen / "controller-dependencies"
    directory.mkdir()
    own = {}
    for module in (transport, monitor, resource_guard, trees):
        source = Path(module.__file__).resolve()
        shutil.copyfile(source, directory / source.name)
        own[source.name] = _file_sha(source)
    version = importlib.metadata.version("playwright")
    package = Path(importlib.util.find_spec("playwright").origin).resolve().parent
    bundle = package / "driver/package/lib/coreBundle.js"
    if version != PLAYWRIGHT_VERSION or _file_sha(bundle) != PLAYWRIGHT_BUNDLE_SHA256:
        raise ValueError("v3 requires the preregistered Playwright 1.62.0/coreBundle bytes")
    sdk = {str(path.relative_to(package)):_file_sha(path) for path in sorted(package.rglob("*"))
           if path.is_file() and "__pycache__" not in path.relative_to(package).parts}
    binaries = {name:{"path":str(Path(path).resolve()),"sha256":_file_sha(path)} for name,path in (
        ("controller_python",sys.executable),("worker_python",transport.PYTHON),("chromium","/usr/lib/chromium/chromium"))}
    result = {"schema":"script-continuity-dependencies/v1","controller_dependencies":own,
        "semantics_policy":semantics_module.POLICY,"semantics_collector_sha256":_file_sha(semantics_module.__file__),
        "playwright":{"version":version,"package_path":str(package),"file_sha256":sdk,
                      "package_manifest_sha256":_sha(json.dumps(sdk,sort_keys=True,separators=(",",":")))},
        "binaries":binaries,"python_version":sys.version,
        "scope":"All selected runtime files, own controller/dependency source and complete Playwright Python/driver payload are hashed; executable hashes supplement the externally configured OS/browser resources. This is not a hermetic OS image."}
    _write(frozen / "dependency-manifest.json",result)
    return result


@contextmanager
def _origin_gateway(plan, gateway_module):
    """Use the selected, hashed runtime gateway rather than a development default."""
    server = gateway_module.make_gateway(plan["socket"],plan["origin"],plan["upstream_host"],plan["upstream_port"])
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        Path(plan["socket"]).unlink(missing_ok=True)


def _fixture(plan):
    if "public_fixture" in plan:
        value = plan["public_fixture"]
        return _json(value) if isinstance(value, (str, Path)) else deepcopy(value)
    return _json(Path(plan["private"]) / "public-fixture.json")


def _validate_common_script(source, modules, origins, *, runtime_source=None):
    """Reject privileged interface access and obvious lane-origin branching."""
    script_policy = transport._module("script_policy", runtime_source=runtime_source)
    script_policy.validate_script(source, module_names=modules)
    for code in [source, *modules.values()]:
        parsed = ast.parse(code)
        script_policy.validate_script(code, module_names=modules)
        for node in ast.walk(parsed):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(origin in node.value for origin in origins):
                    raise ValueError("script/modules must not hardcode either registered origin")
        tainted = set()
        changed = True
        def origin_dependent(node):
            return any((isinstance(n, ast.Attribute) and n.attr == "origin") or
                       (isinstance(n, ast.Name) and n.id in tainted) for n in ast.walk(node))
        while changed:
            before = set(tainted)
            for node in ast.walk(parsed):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value and origin_dependent(node.value):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    tainted.update(n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name))
            changed = before != tainted
        for node in ast.walk(parsed):
            condition = node.test if isinstance(node, (ast.If, ast.IfExp, ast.While)) else node if isinstance(node, ast.Compare) else None
            if condition is not None and origin_dependent(condition):
                raise ValueError("origin-dependent script branching is excluded")


def _freeze_runtime(destination, *, runtime_source=None):
    source = transport.resolve_runtime_source(runtime_source)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
    if not (destination / "trees.py").exists():
        shutil.copyfile(Path(trees.__file__), destination / "trees.py")
    if (destination / "trees.py").read_bytes() != Path(trees.__file__).read_bytes():
        raise ValueError("selected runtime normalizer must match the coordinator normalizer")
    return {str(p.relative_to(destination)): _sha(p.read_bytes()) for p in sorted(destination.rglob("*")) if p.is_file()}


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


def _normalize_action(value, roots, field=None):
    if isinstance(value, dict):
        return {k:_normalize_action(v, roots, k) for k,v in value.items()}
    if isinstance(value, list):
        return [_normalize_action(v, roots) for v in value]
    if isinstance(value, str):
        if field == "target":
            # Native Playwright diagnostic repr embeds frame URLs inside quotes.
            # Only this diagnostic field gets embedded-origin substitution.
            for root,alias in sorted(roots.items(), key=lambda pair:-len(pair[0])):
                value = value.replace(root + "/", alias + "/").replace(root + "'", alias + "'").replace(root + '"', alias + '"')
            return value
        return trees._url(value, roots)
    return value


def _business_checkpoint(oracle, case_ref, checkpoint, records, previous, preparations):
    result = {"verdict": "unconfirmed", "facts_match": None, "identity_match": None, "lanes": {}}
    if oracle is None:
        result["reason"] = "independent_business_oracle_not_configured"
        return result
    snapshots = {}
    def incomplete(value):
        if value is False or value is None:
            return True
        if isinstance(value, dict):
            return any(incomplete(item) for item in value.values())
        if isinstance(value, list):
            return any(incomplete(item) for item in value)
        return value in ("unconfirmed", "unsupported", "fail", "missing") if isinstance(value, str) else False
    def incomplete_checks(value):
        if isinstance(value, dict):
            return any(incomplete(item) if key in {"pass","passed","complete","status","verdict"} else incomplete_checks(item) for key,item in value.items())
        if isinstance(value, list):
            return any(incomplete_checks(item) for item in value)
        return False
    try:
        for lane in ("source", "replica"):
            current = oracle.capture(lane, case_ref, checkpoint)
            snapshots[lane] = current
            action = {key: records[lane].get(key) for key in ACTION_SCHEMA["required"]}
            assessment = oracle.assess(case_ref, {**checkpoint, "lane": lane}, previous.get(lane, current), current, action)
            evidence = bool(current.get("evidence_refs")) and bool(assessment.get("evidence_refs"))
            captured = current.get("status") in ("pass", "confirmed") and ("facts" in current or "canonical_facts" in current)
            complete = captured and "logical_object_identities" in current and bool(current.get("coverage")) and not incomplete(current.get("coverage")) and evidence and bool(assessment.get("checks"))
            verdict = assessment.get("verdict", "unconfirmed")
            if incomplete_checks(assessment.get("checks")) and verdict == "pass":
                verdict = "unconfirmed"
            if verdict == "pass" and not complete:
                verdict = "unconfirmed"
            preparation = preparations.get(lane, {})
            if preparation.get("initial_equivalence") == "fail":
                verdict = "fail"
            elif preparation.get("initial_equivalence") not in ("pass", True) or not preparation.get("reset_receipt"):
                verdict = "unconfirmed"
            result["lanes"][lane] = {"capture": current, "assessment": assessment, "verdict": verdict, "required_evidence_present": complete}
        facts = lambda row: row.get("facts", row.get("canonical_facts"))
        result["facts_match"] = facts(snapshots["source"]) == facts(snapshots["replica"])
        result["identity_match"] = snapshots["source"].get("logical_object_identities") == snapshots["replica"].get("logical_object_identities")
        verdicts = [row["verdict"] for row in result["lanes"].values()]
        if "fail" in verdicts or not result["facts_match"] or not result["identity_match"]:
            result["verdict"] = "fail"
        elif all(v == "pass" for v in verdicts):
            result["verdict"] = "pass"
        previous.update(snapshots)
    except Exception as error:
        result["reason"] = "oracle_error"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    return result


def _semantics_comparison(records, roots, destination, semantics_module, raw_captures):
    payloads, errors = [], []
    for lane, record in records.items():
        try:
            aux = record["observation"]["auxiliary"]["playwright_semantics"]
            if aux.get("schema") != SEMANTICS_SCHEMA or aux.get("file") != "playwright-semantics.json":
                raise ValueError("unexpected semantics reference")
            stem = Path(record["observation"]["dom"]).stem
            value = _json(Path(record["private_trees_directory"]) / stem / "playwright-semantics.json")
            if value.get("schema") != SEMANTICS_SCHEMA or value.get("status") != aux.get("status"):
                raise ValueError("semantics schema/status mismatch")
            if value.get("policy") != semantics_module.POLICY:
                raise ValueError("semantics policy differs from the frozen collector")
            if not isinstance(value.get("frames"),list) or not isinstance(value.get("unsupported"),list):
                raise ValueError("semantics frame/unsupported structure missing")
            canonical = semantics_module.canonical_semantics(value, roots)
            if canonical.get("schema") != SEMANTICS_SCHEMA or canonical.get("status") != "confirmed" or canonical.get("unsupported"):
                errors.append({"lane":lane,"kind":"semantics_unconfirmed_or_unsupported",
                               "unsupported":canonical.get("unsupported")})
                payloads.append(canonical)
                continue
            if not value["frames"]:
                raise ValueError("confirmed semantics must cover a root frame")
            fields = ("key","parent","owner","url","name")
            identity = lambda frame: tuple(frame.get(field,"" if field == "name" else None) for field in fields)
            if [identity(frame) for frame in value["frames"]] != [identity(frame) for frame in raw_captures[lane]["frames"]]:
                raise ValueError("semantics frame topology does not cover the full capture")
            if any(frame.get("root") != "body" or not isinstance(frame.get("snapshot"),str) for frame in value["frames"]):
                raise ValueError("semantics root or complete snapshot string unavailable")
            payloads.append(canonical)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append({"lane":lane,"kind":"semantics_capture_unavailable","error_type":type(error).__name__})
            payloads.append({"schema":SEMANTICS_SCHEMA,"status":"unconfirmed","frames":[],
                             "unsupported":[{"kind":"semantics_capture_unavailable"}]})
    difference = trees._first_difference(*payloads)
    supported = not errors
    result = {"schema":"playwright-semantics-comparison/v1","exact":supported and difference is None,
              "supported":supported,"first_difference":difference,"errors":errors,
              "comparison":"exact complete canonical payload; ordered snapshots, topology and explicit URL fields retained",
              "aria_snapshot_limits":ARIA_LIMITS}
    destination = Path(destination)
    _write(destination / "expected.json", payloads[0])
    _write(destination / "actual.json", payloads[1])
    _write(destination / "comparison.json", result)
    return result


def _compare_step(left, right, destination, roots, *, mode, oracle=None, case_ref=None, previous=None, preparations=None, semantics_module=None):
    if mode != MODE or semantics_module is None:
        raise ValueError("v3 mode and frozen semantics collector are required")
    destination = Path(destination)
    records = {"source": left, "replica": right}
    terminated = any(record.get("status") == "terminated" or record.get("observation", {}).get("failure_category") == "runtime_terminated" for record in (left, right))
    missing_capture = any(not record.get("observation", {}).get("dom") for record in (left, right))
    if terminated or missing_capture:
        layer = "runtime_terminated" if terminated else "capture_unavailable"
        unavailable = {"exact":False, "first_difference":None, "reason":layer}
        result = {"schema":SCHEMA, "mode":mode, "checkpoint":left.get("checkpoint", "after_action"), "action":left.get("action"),
                  "primary_pass":False, "script_continuity_pass":False,"raw_strict_exact":False,"public_dom_match":False,"ax_match":False,
                  "full_ax_match":False,"playwright_semantics_match":False,
                  "business_verdict":"unconfirmed", "action_identity_match":False, "needs_reading":False,
                  "runtime_terminated":terminated, "capture_unconfirmed":not terminated,
                  "stability_requested":any(row.get("stability", {}).get("enabled", False) for row in (left, right)),
                  "stability_gate_pass":False, "stability":{lane:row.get("stability") for lane,row in records.items()},
                  "first_failure_layer":layer, "raw_strict":unavailable, "public_dom":unavailable, "ax":unavailable,
                  "business":{"verdict":"unconfirmed", "reason":layer},
                  "action_data":[{key:row.get(key) for key in ACTION_SCHEMA["required"]} for row in (left,right)],
                  "prediction_equal":left.get("prediction") == right.get("prediction")}
        _write(destination / "step-result.json", result)
        return result
    raw = [_json(Path(record["private_trees_directory"]) / Path(record["observation"]["dom"]).stem / "raw.json") for record in (left,right)]
    strict = trees.compare(*[{"raw": value} for value in raw], url_roots=roots, output_dir=destination / "raw-strict")
    projected = [_public_projection(trees.canonicalize(value, roots)) for value in raw]
    comparisons = {}
    for kind in ("public_dom", "ax"):
        values = deepcopy(projected)
        for value in values:
            for frame in value.get("frames", []):
                frame.pop("ax" if kind == "public_dom" else "document", None)
        comparisons[kind] = trees.compare(*values, output_dir=destination / kind)
    semantics = _semantics_comparison(records, roots, destination / "playwright-semantics", semantics_module,
                                      dict(zip(("source","replica"),raw)))
    checkpoint_kind = left.get("checkpoint", "after_action")
    is_action = checkpoint_kind == "after_action"
    action_data = [{key: record.get(key) for key in ACTION_SCHEMA["required"]} for record in (left,right)]
    action_present = all(all(record.get(key) is not None for key in ACTION_SCHEMA["required"]) for record in (left,right))
    if any('"non_json_type"' in json.dumps(item,sort_keys=True) for item in action_data):
        action_present = False
    identity = action_present and _normalize_action(action_data[0], roots) == _normalize_action(action_data[1], roots)
    if not is_action:
        identity = left.get("checkpoint") == right.get("checkpoint") and left.get("action") == right.get("action")
    checkpoint = {"kind": checkpoint_kind, "action": left.get("action", 0), "case_ref": case_ref,
                  "observations": {lane:row.get("observation") for lane,row in records.items()},
                  "evidence_directories": {lane:row.get("evidence_directory") for lane,row in records.items()},
                  "private_trees_directories": {lane:row.get("private_trees_directory") for lane,row in records.items()}}
    business = _business_checkpoint(oracle, case_ref, checkpoint, records, previous if previous is not None else {}, preparations or {})
    action_error = any(record.get("error") or record.get("observation", {}).get("error") for record in (left,right))
    stability_requested = any(record.get("stability",{}).get("enabled",False) for record in (left,right))
    stability_gate_pass = all(record.get("stability",{}).get("enabled") is True and record["stability"].get("status")=="stable" for record in (left,right))
    capture_unconfirmed = any(record.get("status")=="unconfirmed" for record in (left,right)) or not stability_gate_pass
    readpoint = any(record.get("reading_request") or record.get("status") == "needs_reading" for record in (left,right))
    layers = {"public_dom":comparisons["public_dom"]["exact"], "playwright_semantics":semantics["exact"],
              "business":business["verdict"] == "pass", "action_identity":identity,
              "action_error_free":not action_error,"stability":stability_gate_pass}
    primary = all(layers.values())
    if readpoint or capture_unconfirmed:
        primary = False
    failed = [key for key,value in layers.items() if not value]
    result = {"schema": SCHEMA, "mode": mode, "checkpoint": checkpoint_kind, "action": left.get("action"),
              "primary_pass":primary,"script_continuity_pass":primary,"raw_strict_exact":strict["exact"],
              "public_dom_match":layers["public_dom"],"ax_match":comparisons["ax"]["exact"],
              "full_ax_match":comparisons["ax"]["exact"],"playwright_semantics_match":semantics["exact"],
              "semantics_unconfirmed":not semantics["supported"],
              "business_verdict": business["verdict"], "action_identity_match": identity, "needs_reading": readpoint,
              "capture_unconfirmed":capture_unconfirmed, "stability_requested":stability_requested,
              "stability_gate_pass":stability_gate_pass, "stability":{lane:record.get("stability") for lane,record in records.items()},
              "first_failure_layer":"capture_stability_unconfirmed" if capture_unconfirmed else "needs_reading" if readpoint else "playwright_semantics_unconfirmed" if not semantics["supported"] else (failed[0] if not primary and failed else None),
              "raw_strict": strict, "public_dom": comparisons["public_dom"], "ax": comparisons["ax"], "business": business,
              "playwright_semantics":semantics,"aria_snapshot_limits":ARIA_LIMITS,
              "full_ax_role":"diagnostic; original full Chromium AX comparison retained",
              "action_data": action_data, "prediction_equal": left.get("prediction") == right.get("prediction")}
    _write(destination / "step-result.json", result)
    return result


def _release(lane, checkpoint, decision, reason):
    name = f"step-{checkpoint:04d}" if isinstance(checkpoint, int) else checkpoint
    path = lane["barrier"] / (name + ".release.json")
    if not path.exists():
        pending = path.with_name(path.name + ".pending")
        _write(pending, {"decision": decision, "reason": reason})
        pending.replace(path)


def _terminate(child):
    if child.poll() is not None:
        return
    os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)


def run_pair(source_plan, replica_plan, script_path, out, modules=(), policy=None, *, oracle=None, case_ref=None, runtime_source=None):
    """Preregister and execute independent lanes with state0/action/final gates.

    ``policy.mode`` is mandatory. No oracle means business=unconfirmed, so
    script-continuity cannot pass. Raw-strict remains a separate tree metric.
    The private oracle and case reference are never sent to either browser worker.
    """
    if not policy or policy.get("mode") != MODE:
        raise ValueError("preregister policy.mode='playwright_script_continuity' for the separate v3 controller")
    policy = {"wall_seconds":600,"progress_seconds":90,"barrier_wait_seconds":55,"action_limit":120,"resource_limits":None,
              "min_memory_bytes":512*1024**2,"min_disk_bytes":256*1024**2, **policy,
              "primary_layers":["public_dom","playwright_semantics","business","action_identity","action_error_free","stability"],
              "raw_strict_is_separate":True,"compare_state0":True,"compare_final":True,"stop_on_first_primary_failure":True}
    limits = policy["resource_limits"]
    limit_fields = {"cpu_seconds", "rss_bytes", "disk_growth_bytes"}
    if limits is not None and (not isinstance(limits, dict) or set(limits) != limit_fields or
            any(isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float("inf") for value in limits.values())):
        raise ValueError("resource_limits requires finite positive cpu_seconds/rss_bytes/disk_growth_bytes or None")
    resource_policy = {"enabled":limits is not None, "limits":limits, "sample_interval_seconds":1,
        "enforcement":"polling soft limits; stop and clean on observed exceedance; overshoot possible; not a cgroup quota",
        "process_scope":"both worker supervisors and observed descendants, retained by PID and kernel starttime",
        "cpu_measurement":"sampled identity self CPU cumulative lower bound; processes born/reaped between polls are unobserved",
        "rss_measurement":"sum of sampled process RSS; shared pages can be counted in multiple processes",
        "disk_scope":"run-directory regular-file logical growth from monitoring initialization; excludes tmpfs/browser cache outside directory"}
    runtime_source = transport.resolve_runtime_source(runtime_source)
    stability_module = transport._module("settle", runtime_source=runtime_source)
    policy["stability"] = stability_module.normalize_policy(policy.get("stability"))
    if not policy["stability"]["enabled"] or policy["stability"]["version"] != STABILITY_VERSION:
        raise ValueError("v3 requires bounded full DOM/AX plus Playwright semantics local stability")
    semantics_module = transport._module("playwright_semantics", runtime_source=runtime_source)
    gateway_module = transport._module("unix_gateway", runtime_source=runtime_source)
    sandbox_module = transport._module("worker_sandbox", runtime_source=runtime_source)
    guard_module = transport._module("process_guard", runtime_source=runtime_source)
    if policy.get("semantics_policy_id") != semantics_module.POLICY["id"]:
        raise ValueError("v3 requires explicit semantics_policy_id matching the selected collector")
    preregistered_source_hashes = {str(path.relative_to(runtime_source)):_file_sha(path)
        for path in sorted(runtime_source.rglob("*")) if path.is_file() and "__pycache__" not in path.relative_to(runtime_source).parts}
    runtime_manifest_sha256 = _sha(json.dumps(preregistered_source_hashes,sort_keys=True,separators=(",",":")))
    if policy.get("runtime_manifest_sha256") != runtime_manifest_sha256:
        raise ValueError("v3 requires explicit runtime_manifest_sha256 matching all selected runtime bytes")
    stability_sha256 = stability_module.policy_hash(policy["stability"])
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(script_path).read_text(encoding="utf-8")
    module_sources = {}
    for item in modules:
        path = Path(item)
        if not path.stem.isidentifier() or path.suffix != ".py" or path.stem in module_sources:
            raise ValueError("modules require unique plain Python module names")
        module_sources[path.stem] = path.read_text(encoding="utf-8")
    origins = [source_plan["origin"], replica_plan["origin"]]
    if origins[0] == origins[1] or source_plan["socket"] == replica_plan["socket"]:
        raise ValueError("lanes need distinct origins and independent gateway sockets")
    _validate_common_script(source,module_sources,origins,runtime_source=runtime_source)
    fixtures = [_fixture(source_plan),_fixture(replica_plan)]
    if fixtures[0] != fixtures[1]:
        raise ValueError("same-program comparison requires identical public fixtures")
    frozen = out / "frozen"
    frozen.mkdir()
    (frozen / "script.py").write_text(source, encoding="utf-8")
    for name,code in module_sources.items():
        (frozen / (name + ".py")).write_text(code, encoding="utf-8")
    hashes = _freeze_runtime(frozen / "runtime", runtime_source=runtime_source)
    source_hashes = {str(p.relative_to(runtime_source)):_sha(p.read_bytes())
                     for p in sorted(runtime_source.rglob("*")) if p.is_file() and "__pycache__" not in p.relative_to(runtime_source).parts}
    if source_hashes != preregistered_source_hashes or hashes != source_hashes:
        raise ValueError("selected runtime bytes changed during freeze")
    shutil.copyfile(__file__,frozen / "runner_playwright.py")
    shutil.copyfile(resource_guard.__file__,frozen / "resource_guard.py")
    dependencies = _freeze_dependencies(frozen,semantics_module)
    roots = {origin:"http://registered-origin.invalid" for origin in origins}
    description = oracle.describe() if oracle else None
    if oracle and description.get("independent") is not True:
        raise ValueError("oracle.describe() must explicitly attest independent=True")
    adapter_file = inspect.getsourcefile(type(oracle)) if oracle else None
    if adapter_file:
        shutil.copyfile(adapter_file,frozen / "oracle-adapter.py")
    registration = {"schema":SCHEMA,"run_id":policy.get("run_id",out.name+"-"+uuid.uuid4().hex[:12]),"research_scope":policy.get("research_scope","isolation_limited_construction_pilot"),
        "policy":policy,"aria_snapshot_limits":ARIA_LIMITS,"full_ax_role":"diagnostic only; ax_match retains the original full Chromium AX metric",
        "dependency_manifest":"frozen/dependency-manifest.json","dependency_manifest_sha256":_file_sha(frozen / "dependency-manifest.json"),
        "semantics_collector_sha256":dependencies["semantics_collector_sha256"],"semantics_policy":semantics_module.POLICY,
        "security_projection":semantics_module.POLICY.get("security_projection"),
        "projection":{**PROJECTION_POLICY,"sha256":_sha(inspect.getsource(_public_projection)+json.dumps(PROJECTION_POLICY,sort_keys=True))},
        "action_schema_sha256":_sha(json.dumps(ACTION_SCHEMA,sort_keys=True)),
        "oracle_adapter_sha256":_sha(Path(adapter_file).read_bytes()) if adapter_file else None,
        "oracle_description":description,"oracle_fact_schema_sha256":_sha(json.dumps(description,sort_keys=True)) if description else None,
        "script_sha256":_sha(source),"module_sha256":{k:_sha(v) for k,v in module_sources.items()},
        "public_fixture":fixtures[0],"public_fixture_sha256":_sha(json.dumps(fixtures[0],sort_keys=True)),
        "runtime_sha256":hashes,"runtime_source":str(runtime_source),"runtime_source_sha256":source_hashes,
        "runtime_manifest_sha256":runtime_manifest_sha256,
        "runtime_selection":"explicit_parameter" if runtime_source != transport.RUNTIME.resolve() else "default_development_runtime",
        "resource_monitoring":resource_policy,"resource_guard_sha256":_sha((frozen / "resource_guard.py").read_bytes()),
        "runner_sha256":_sha(Path(__file__).read_bytes()),"normalizer_sha256":hashes["trees.py"],
        "normalizer_policy":trees.POLICY,"url_roots":roots,"teacher_forcing":False,
        "capture_policy":{"initial_navigation":"trusted same-origin root before state0; not a business action","post_action_wait_ms":250,"snapshot":"sequential non-atomic Chromium DOM+AX","stability":policy["stability"],"stability_policy_sha256":stability_sha256,
            "stability_signature_scope":"entire same-lane canonical DOM+AX plus Playwright-derived semantics; protocol IDs normalized, business fields retained; no counterpart data",
            "stability_timeout":"unconfirmed; stop suffix; no website action retry; independent worker watchdog bounds blocked acquisition",
            "security_redaction":"observed secret values redacted before public observations, raw/canonical tree persistence and action recording; authentication effects require independent oracle",
            "private_control_state":"opt-in raw Storage evidence in control plane only; never learner observation"},
        "lane_source_branching":"same frozen source; hardcoded origins and origin-dependent branches rejected",
        "init_script_sha256":{name:_sha(plan.get("init_script") or "") for name,plan in zip(("source","replica"),(source_plan,replica_plan))}}
    _write(out / "registration.json",registration)
    preparations = {}
    if oracle:
        for name in ("source","replica"):
            try:
                preparations[name] = oracle.prepare(name,case_ref)
            except Exception as error:
                preparations[name] = {"initial_equivalence":"unconfirmed","error":str(error)}
        _write(out / "oracle-preparations.json",preparations)
    lanes, comparisons, previous = [], [], {}
    started = last_progress = time.monotonic()
    reason = first_failure = None
    checkpoint = "state0"
    next_step = 1
    final_seen = False
    pending_since = None
    last_resource_check = 0
    with ExitStack() as stack:
        for name,original_plan,fixture in zip(("source","replica"),(source_plan,replica_plan),fixtures):
            directory = out / name
            directory.mkdir()
            jobdir,barrier = directory / "job", directory / "barrier"
            jobdir.mkdir();barrier.mkdir()
            plan = {**original_plan,"runtime":str(frozen / "runtime"),"socket":str(transport.make_socket_path())}
            job = {"origin":plan["origin"],"socket":plan["socket"],"fixture":fixture,"script":source,"modules":module_sources,
                "action_limit":policy["action_limit"],"state_path":str(jobdir / "state.json"),"step_barrier_dir":str(barrier),
                "state_barriers":True,"initial_url":plan["origin"] + "/",
                "collect_private_control_state":bool(policy.get("collect_private_control_state",False)),
                "settle_policy":policy["stability"],
                "step_barrier_timeout_seconds":min(60,policy["barrier_wait_seconds"]+4),"init_script":plan.get("init_script")}
            _write(jobdir / "job.json",job)
            nonce = uuid.uuid4().hex
            receipt = directory / "cleanup.json"
            command = [transport.PYTHON,str(frozen / "runtime" / "process_guard.py"),"--receipt",str(receipt),"--nonce",nonce,"--",
                *sandbox_module.command(plan["runtime"],jobdir / "job.json",plan["socket"],step_barrier_dir=barrier)]
            stack.enter_context(_origin_gateway(plan,gateway_module))
            stdout = stack.enter_context((directory / "stdout.log").open("xb"))
            stderr = stack.enter_context((directory / "stderr.log").open("xb"))
            child = subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True,env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8"})
            stack.callback(_terminate,child)
            lanes.append({"name":name,"job":jobdir,"barrier":barrier,"child":child,"receipt":receipt,"nonce":nonce,"command":command,"last_checkpoint":None})
        workload_guard = resource_guard.ResourceGuard([lane["child"].pid for lane in lanes if lane["child"].poll() is None],out,limits=limits) if limits is not None else None
        last_workload_sample = None
        events = stack.enter_context((out / "progress.jsonl").open("x",encoding="utf-8"))
        try:
            while True:
                now = time.monotonic()
                if checkpoint != "state0" and not final_seen:
                    step_paths = [lane["barrier"] / f"step-{next_step:04d}.json" for lane in lanes]
                    final_paths = [lane["barrier"] / "final.json" for lane in lanes]
                    if any(path.exists() for path in final_paths):
                        final_records = [_json(path) for path in final_paths if path.exists()]
                        if any(row.get("status") == "terminated" for row in final_records):
                            reason = "runtime_terminated"
                        elif all(path.exists() for path in final_paths):
                            checkpoint = "final"
                        elif any(row.get("reading_request") or row.get("status") == "needs_reading" for row in final_records):
                            reason = "needs_reading"
                        elif any(step.exists() for step in step_paths):
                            reason = "runtime_terminated" if any(row.get("status") == "terminated" for row in final_records) else "needs_reading" if any(row.get("reading_request") or row.get("status") == "needs_reading" for row in final_records) else "action_sequence_length_mismatch"
                name = f"step-{next_step:04d}" if checkpoint == "after_action" else checkpoint
                paths = [lane["barrier"] / (name + ".json") for lane in lanes]
                present = [path.exists() for path in paths]
                if now-last_resource_check >= 1:
                    resource = monitor.resources(out)
                    if workload_guard is not None:
                        last_workload_sample = workload_guard.sample()
                    heartbeat = {"elapsed_seconds":now-started,"idle_seconds":now-last_progress,"checkpoint":name,"barrier_present":present,
                        "resources":resource,"workload_resources":last_workload_sample,"processes":[monitor.process_sample(lane["child"].pid) for lane in lanes],"progress_basis":"paired checkpoint advancement only; stdout/evidence growth is liveness only"}
                    events.write(json.dumps(heartbeat)+"\n");events.flush()
                    _atomic(out / "status.json",heartbeat)
                    last_resource_check = now
                    if last_workload_sample is not None and last_workload_sample["stop_required"]:
                        reason = "resource_limit_exceeded"
                        first_failure = first_failure or {"checkpoint":name,"layer":"resource_limit","resource_sample":last_workload_sample}
                    elif resource["available_memory_bytes"] < policy["min_memory_bytes"]:
                        reason = "memory_guard"
                    elif resource["available_disk_bytes"] < policy["min_disk_bytes"]:
                        reason = "disk_guard"
                for lane in lanes:
                    settle_path=lane["job"] / "settle-status.json"
                    if settle_path.exists():
                        state=_json(settle_path)
                        if state.get("status")=="running" and now>state["watchdog_deadline_monotonic"]:
                            reason="capture_stability_timeout"
                            first_failure={"checkpoint":name,"layer":"capture_stability_unconfirmed","lane":lane["name"],"stability":state, "watchdog_detected_monotonic":now,
                                           "watchdog_observed_elapsed_seconds":now-state["started_monotonic"]}
                            lane["last_checkpoint"] = {**(lane["last_checkpoint"] or {}), "checkpoint":"capture_timeout", "action":state.get("action"), "source_location":state.get("source_location"), "stability":state}
                            _terminate(lane["child"])
                if (out / "STOP").exists(): reason = "coordinator_stop"
                elif now-started > policy["wall_seconds"]: reason = "wall_time_exhausted"
                elif now-last_progress > policy["progress_seconds"]: reason = "no_checkpoint_progress"
                if all(present) and not reason:
                    records = [_json(path) for path in paths]
                    for lane,record in zip(lanes,records): lane["last_checkpoint"] = record
                    destination = out / "comparisons" / name
                    compared = _compare_step(*records,destination,roots,mode=policy["mode"],oracle=oracle,case_ref=case_ref,previous=previous,preparations=preparations,semantics_module=semantics_module)
                    comparisons.append({key:compared[key] for key in ("checkpoint","action","primary_pass","script_continuity_pass","raw_strict_exact","public_dom_match","ax_match","full_ax_match","playwright_semantics_match","business_verdict","action_identity_match","needs_reading","capture_unconfirmed","stability_requested","stability_gate_pass","first_failure_layer")}|{"directory":"comparisons/"+name,"method":records[0].get("method")})
                    if not compared["primary_pass"]:
                        reason = "runtime_terminated" if compared.get("runtime_terminated") else "capture_stability_unconfirmed" if compared["capture_unconfirmed"] else "needs_reading" if compared["needs_reading"] else "playwright_semantics_unconfirmed" if compared.get("semantics_unconfirmed") else "first_primary_failure"
                        first_failure = {"checkpoint":name,"layer":compared["first_failure_layer"],"comparison":"comparisons/"+name,
                            "raw_strict_first_difference":compared["raw_strict"]["first_difference"],
                            "playwright_semantics_first_difference":compared.get("playwright_semantics",{}).get("first_difference")}
                    for lane in lanes: _release(lane,next_step if checkpoint == "after_action" else checkpoint,"stop" if reason else "continue",reason or "paired_primary_pass")
                    if checkpoint == "final": final_seen = True
                    elif checkpoint == "after_action": next_step += 1
                    checkpoint = "after_action" if not final_seen else "final-released"
                    pending_since = None
                    last_progress = time.monotonic()
                elif any(present):
                    pending_since = pending_since or now
                    if now-pending_since > policy["barrier_wait_seconds"]: reason = "paired_barrier_timeout"
                    if any(not exists and lane["child"].poll() is not None for lane,exists in zip(lanes,present)):
                        reason = "action_sequence_length_mismatch"
                if reason:
                    for lane in lanes:
                        for path in lane["barrier"].glob("*.json"):
                            if ".release." not in path.name:
                                _release(lane,path.stem,"stop",reason)
                    break
                if all(lane["child"].poll() is not None for lane in lanes):
                    reason = "workers_completed" if final_seen else "missing_required_checkpoint"
                    break
                time.sleep(.05)
        except Exception as error:
            reason = "controller_error"
            _write(out / "controller-error.json",{"type":type(error).__name__,"error":str(error)})
        finally:
            # Release all pending waits before bounded cleanup, including final
            # entered by a runtime after a stopped action or read point.
            deadline = time.monotonic()+8
            while any(lane["child"].poll() is None for lane in lanes) and time.monotonic()<deadline:
                for lane in lanes:
                    for path in lane["barrier"].glob("*.json"):
                        if ".release." not in path.name:
                            _release(lane,path.stem,"stop",reason or "cleanup")
                time.sleep(.05)
            for lane in lanes: _terminate(lane["child"])
        lane_results = {}
        for lane in lanes:
            path = lane["job"] / "evidence" / "result.json"
            clean = guard_module.receipt_valid(lane["receipt"],nonce=lane["nonce"],supervisor_pid=lane["child"].pid)
            row = _json(path) if path.exists() else None
            lane_results[lane["name"]] = {"exit_code":lane["child"].returncode,"process_tree_clean":clean,"result":row,"command":lane["command"]}
            if reason != "workers_completed":
                record = lane["last_checkpoint"] or {}
                line = (record.get("source_location") or {}).get("line")
                suffix = "".join(source.splitlines(keepends=True)[line:]) if line else source
                (out/lane["name"]/"unexecuted-source-suffix.py").write_text(suffix)
                _write(out/lane["name"]/"continuation.json",{"stopped_after_action":record.get("action"),"source_location":record.get("source_location"),
                    "suffix_file":"unexecuted-source-suffix.py","meaning":"lexical suffix; frozen full source retained; no continuation was executed by the coordinator"})
        statuses = [row["result"].get("status") if row["result"] else None for row in lane_results.values()]
        if reason != "resource_limit_exceeded":
            if "terminated" in statuses: reason = "runtime_terminated"
            elif "unconfirmed" in statuses: reason = "capture_stability_unconfirmed"
            elif "needs_reading" in statuses: reason = "needs_reading"
        if workload_guard is not None:
            last_workload_sample = workload_guard.sample()
            if last_workload_sample["stop_required"] and reason == "workers_completed":
                reason = "resource_limit_exceeded"
                first_failure = first_failure or {"checkpoint":"post_cleanup","layer":"resource_limit","resource_sample":last_workload_sample}
        if reason == "workers_completed" and any(status != "completed" for status in statuses): reason = "worker_runtime_failure"
        business_actions = sum(row["checkpoint"] == "after_action" and row["method"] not in {"goto","reload","go_back","go_forward"} for row in comparisons)
        completed = reason == "workers_completed" and final_seen and business_actions > 0
        clean = all(row["process_tree_clean"] and row["exit_code"] == 0 for row in lane_results.values())
        success = bool(completed and clean and comparisons and all(row["primary_pass"] for row in comparisons))
        if not success and first_failure is None:
            first_failure = {"checkpoint":"post_cleanup" if completed else name,
                             "layer":"cleanup_failure" if completed and not clean else reason or "incomplete_execution",
                             "comparison":None}
        business_verdicts = [row["business_verdict"] for row in comparisons]
        business_verdict = "fail" if "fail" in business_verdicts else "pass" if business_verdicts and all(v == "pass" for v in business_verdicts) else "unconfirmed"
        result = {"schema":SCHEMA,"mode":policy["mode"],"research_scope":registration["research_scope"],"primary_pass":success,"script_continuity_pass":success,
            "aria_snapshot_limits":ARIA_LIMITS,"semantics_policy":semantics_module.POLICY,
            "security_projection":semantics_module.POLICY.get("security_projection"),
            "full_ax_role":"diagnostic; not a v2 pass claim",
            "raw_strict_exact":bool(comparisons and all(row["raw_strict_exact"] for row in comparisons)),
            "public_dom_match":bool(comparisons and all(row["public_dom_match"] for row in comparisons)),
            "ax_match":bool(comparisons and all(row["ax_match"] for row in comparisons)),
            "full_ax_match":bool(comparisons and all(row["full_ax_match"] for row in comparisons)),
            "playwright_semantics_match":bool(comparisons and all(row["playwright_semantics_match"] for row in comparisons)),"business_verdict":business_verdict,
            "action_identity_match":bool(comparisons and all(row["action_identity_match"] for row in comparisons)),
            "completion_status":"completed" if completed else "terminated" if reason == "runtime_terminated" else "unconfirmed" if reason.startswith("capture_stability") or reason == "playwright_semantics_unconfirmed" else "needs_reading" if reason == "needs_reading" else "stopped",
            "reason":reason,"first_failure":first_failure,"compared_actions":sum(row["checkpoint"] == "after_action" for row in comparisons),
            "state0_compared":any(row["checkpoint"] == "state0" for row in comparisons),"final_compared":any(row["checkpoint"] == "final" for row in comparisons),
            "steps":comparisons,"lanes":lane_results,"elapsed_seconds":time.monotonic()-started,"teacher_forcing":False,"model_calls":0,
            "resource_monitoring":{"policy":resource_policy,"last_sample":last_workload_sample,
                "peaks":dict(workload_guard.peaks) if workload_guard is not None else None,
                "baseline_disk":workload_guard.baseline_disk if workload_guard is not None else None},
            "registration":"registration.json","normalizer_sha256":hashes["trees.py"],"raw_strict_is_separate":True}
        result["raw_strict_scope"] = "compared checkpoints only; consult state0_compared/final_compared/completion_status for full-run coverage"
        if reason == "workers_completed" and not completed:
            result["completion_status"] = "unconfirmed_no_business_actions"
        _write(out / "result.json",result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan",required=True)
    parser.add_argument("--replica-plan",required=True)
    parser.add_argument("--script",required=True)
    parser.add_argument("--out",required=True)
    parser.add_argument("--module",action="append",default=[])
    parser.add_argument("--policy",required=True)
    parser.add_argument("--runtime-source",help="trusted generic runtime_versions directory; frozen and hashed before dispatch")
    args = parser.parse_args()
    result = run_pair(_json(args.source_plan),_json(args.replica_plan),args.script,args.out,args.module,_json(args.policy),runtime_source=args.runtime_source)
    print(json.dumps({key:result[key] for key in ("schema","mode","script_continuity_pass","primary_pass","playwright_semantics_match","full_ax_match","raw_strict_exact","reason","compared_actions","first_failure")},ensure_ascii=False))
    return 0 if result["primary_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


