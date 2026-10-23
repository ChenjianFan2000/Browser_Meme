"""Frozen v2 validator extension over an isolated instance of the stable v1 runner."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import types
import uuid

from harness.replica.contracts_v1 import runner as stable


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def completion_deadline(started, wall_seconds, cleanup_seconds, *, now=None):
    return min(started + wall_seconds, (time.monotonic() if now is None else now) + cleanup_seconds)


def normalize_bundle(bundle):
    schema = bundle.get("schema")
    if schema not in {"component-contract-bundle/v1", "component-contract-bundle/v2"}:
        raise ValueError("v2 controller supports frozen component-contract-bundle/v1 or v2")
    return {**bundle, "schema": "component-contract-bundle/v1"}, schema.rsplit("/", 1)[1]


def _load(name, path, *, package=False):
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[str(Path(path).parent)] if package else None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_source(source_plan, script_path, out, contracts_path, **kwargs):
    """Freeze extension bytes before import; never mutate the v1 module or artifacts."""
    started = time.monotonic()
    out = Path(out).resolve()
    extension = out.parent / (out.name + "-contract-extension-" + uuid.uuid4().hex[:10])
    extension.mkdir(parents=True, exist_ok=False)
    directory = Path(__file__).parent
    for name in ("__init__.py", "schema.py", "validator.py", "runner.py", "README.schema.md"):
        shutil.copyfile(directory / name, extension / name)
    base_source = Path(stable.__file__).read_text()
    old_cleanup = "deadline = time.monotonic() + 12"
    new_cleanup = "deadline = completion_deadline(started, policy[\"wall_seconds\"], policy.get(\"completion_cleanup_seconds\", 45))"
    old_copy = "shutil.copytree(Path(__file__).parent, frozen / \"contracts_v1\""
    new_copy = "shutil.copytree(Path(BASE_SOURCE_DIRECTORY), frozen / \"contracts_v1\""
    if base_source.count(old_cleanup) != 1 or base_source.count(old_copy) != 1:
        raise ValueError("stable controller changed; bounded cleanup patch requires explicit review")
    patched_source = base_source.replace(old_cleanup, new_cleanup).replace(old_copy, new_copy)
    (extension / "base_runner_v2.py").write_text(patched_source)
    bundle = json.loads(Path(contracts_path).read_text())
    normalized, contract_version = normalize_bundle(bundle)
    if contract_version == "v1":
        legacy = extension / "legacy"
        legacy.mkdir()
        for name in ("__init__.py", "schema.py", "validator.py"):
            shutil.copyfile(Path(stable.__file__).parent / name, legacy / name)
    (extension / "original-contracts.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
    (extension / "worker-controller-bundle.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    manifest = {"schema": "component-contract-extension/v2", "execution": "validator imported from this frozen directory before browser launch",
                "v1_runner_sha256": _sha(stable.__file__), "bundle_original_sha256": _sha(contracts_path),
                "normalization": "Only outer bundle schema v2 becomes v1 for unchanged base loading; every v2 contract remains unchanged.",
                "base_controller_changes": {"cleanup": "bounded remaining wall budget and completion_cleanup_seconds, default 45", "source_copy": "explicit stable v1 source directory"},
                "contract_version": contract_version,
                "file_sha256": {str(p.relative_to(extension)): _sha(p) for p in sorted(extension.rglob("*")) if p.is_file()}}
    (extension / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    name = "_component_contract_extension_" + uuid.uuid4().hex
    _load(name, extension / "__init__.py", package=True)
    if contract_version == "v1":
        _load(name + ".legacy", extension / "legacy/__init__.py", package=True)
        frozen_validator = _load(name + ".legacy.validator", extension / "legacy/validator.py")
    else:
        frozen_validator = _load(name + ".validator", extension / "validator.py")
    frozen_helpers = _load(name + ".runner", extension / "runner.py")
    # This private module has its own globals, so the running v1 controller and
    # existing frozen runs are untouched. Its relative imports retain v1 helpers.
    base_name = "harness.replica.contracts_v1._v2_controller_" + uuid.uuid4().hex
    base = _load(base_name, extension / "base_runner_v2.py")
    base.RUNTIME = stable.RUNTIME
    base.BASE_SOURCE_DIRECTORY = str(Path(stable.__file__).parent)
    base.completion_deadline = frozen_helpers.completion_deadline
    base.validate = frozen_validator.validate
    base.SCHEMA = "component-contract-run/v2"
    original_shared = base.shared
    shared = types.SimpleNamespace(**vars(original_shared))
    original_write = shared._write

    def write(path, value):
        if Path(path) == out / "registration.json":
            value = {**value, "contract_extension": {"directory": str(extension), "manifest_sha256": _sha(extension / "manifest.json"),
                                                     "contract_schema": "component-contract/" + contract_version}}
        original_write(path, value)

    shared._write = write
    base.shared = shared
    policy = {"wall_seconds": 600, "completion_cleanup_seconds": 45, **kwargs.pop("policy", {})}
    if not 0 < policy["completion_cleanup_seconds"] < float("inf"):
        raise ValueError("completion_cleanup_seconds must be finite and positive")
    policy["wall_seconds"] -= time.monotonic() - started
    result = base.run_source(source_plan, script_path, out, extension / "worker-controller-bundle.json", policy=policy, **kwargs)
    result["contract_extension"] = {"directory": str(extension), "manifest_sha256": _sha(extension / "manifest.json")}
    original_shared._atomic(out / "result.json", result)
    return result
