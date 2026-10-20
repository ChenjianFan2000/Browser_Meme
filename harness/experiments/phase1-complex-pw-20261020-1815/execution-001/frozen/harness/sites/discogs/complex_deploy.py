"""Reuse frozen original build/dependencies with a new DB and append-only logs.

Only the root Harness invokes prepare/serve. No original site source is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path(os.environ.get("BM_DISCOGS_RUNTIME", ROOT / ".runtime/phase1-complex-pw-20261020-1815")).resolve()
REFERENCE = Path(os.environ.get("BM_DISCOGS_REFERENCE_RUNTIME", ROOT / ".runtime/phase1-discogs-pw-20261020-1633")).resolve()
if RUNTIME == REFERENCE or RUNTIME.is_relative_to(REFERENCE):
    raise RuntimeError("Complex runtime must be separate from the archived reference")
SOURCE = REFERENCE / "source"
PYTHON = REFERENCE / "venv/Scripts/python.exe"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect():
    frozen = json.loads((REFERENCE / "source_manifest.json").read_text(encoding="utf-8"))
    upstream = ROOT / "veri_env/external/VeriEnv-main/websites/discogs"
    for relative, expected in frozen.items():
        if digest(SOURCE / relative) != expected or digest(upstream / relative) != expected:
            raise RuntimeError(f"Original source hash mismatch: {relative}")
    expected_freeze = (REFERENCE / "python.freeze.txt").read_text(encoding="utf-8")
    actual = subprocess.check_output([str(PYTHON), "-m", "pip", "freeze", "--all"], text=True, timeout=30)
    if set(actual.splitlines()) != set(expected_freeze.splitlines()):
        raise RuntimeError("Shared dependency versions differ from the frozen inventory")
    expected_baseline = (REFERENCE / "baseline.sha256").read_text(encoding="ascii").strip()
    if digest(REFERENCE / "data/baseline.db") != expected_baseline:
        raise RuntimeError("Reference baseline hash mismatch")
    assets = {}
    for folder in [SOURCE / "frontend/.next/server", SOURCE / "frontend/.next/static"]:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                assets[path.relative_to(SOURCE).as_posix()] = digest(path)
    for name in ["BUILD_ID", "routes-manifest.json", "required-server-files.json"]:
        path = SOURCE / "frontend/.next" / name
        assets[path.relative_to(SOURCE).as_posix()] = digest(path)
    return {
        "runtime": str(RUNTIME), "reference_runtime": str(REFERENCE),
        "source": str(SOURCE), "python": str(PYTHON),
        "source_file_hashes": frozen, "production_asset_hashes": assets,
        "python_freeze_sha256": hashlib.sha256(expected_freeze.encode()).hexdigest(),
        "baseline_sha256": expected_baseline,
        "shared_resources": "Original build, node_modules, venv and decorative-image cache; not a strict speed control",
        "services_started_by_prepare": False,
    }


def prepare():
    record = inspect()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    data = RUNTIME / "data"
    data.mkdir(exist_ok=True)
    for name in ["baseline.db", "discogs.db"]:
        destination = data / name
        if not destination.exists():
            # Exclusive creation prevents accidental replacement of live state.
            with destination.open("xb") as output:
                output.write((REFERENCE / "data/baseline.db").read_bytes())
    if digest(data / "baseline.db") != record["baseline_sha256"]:
        raise RuntimeError("New runtime baseline differs from the frozen reference")
    marker = RUNTIME / "baseline.sha256"
    if marker.exists():
        if marker.read_text(encoding="ascii").strip() != record["baseline_sha256"]:
            raise RuntimeError("New runtime baseline marker mismatch")
    else:
        marker.write_text(record["baseline_sha256"], encoding="ascii")
    manifest = RUNTIME / "setup-manifest.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        if previous != record:
            raise RuntimeError("Prepared runtime inputs changed; use a new runtime/version")
    else:
        with manifest.open("x", encoding="utf-8") as output:
            json.dump(record, output, indent=2)
    print(json.dumps({"prepared": True, "runtime": str(RUNTIME), "source_files": len(record["source_file_hashes"]),
                      "baseline_sha256": record["baseline_sha256"]}), flush=True)


def launcher():
    os.environ["BM_DISCOGS_RUNTIME"] = str(RUNTIME)
    spec = importlib.util.spec_from_file_location("discogs_reference_launcher", Path(__file__).parent / "deploy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SOURCE = SOURCE
    module.PYTHON = PYTHON
    return module


def serve():
    if not (RUNTIME / "setup-manifest.json").is_file():
        raise RuntimeError("Root Harness must invoke complex_deploy.py prepare first")
    current = inspect()
    if current != json.loads((RUNTIME / "setup-manifest.json").read_text(encoding="utf-8")):
        raise RuntimeError("Prepared source/build/dependencies changed")
    module = launcher()
    if module.healthy("http://127.0.0.1:12138/healthz") or module.healthy("http://127.0.0.1:12042"):
        raise RuntimeError("Port already serves a site. Root Harness must stop the prior owned services; cross-runtime reuse is forbidden")
    module.serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inspect", "prepare", "serve", "status"])
    action = parser.parse_args().action
    if action == "inspect":
        result = inspect()
        print(json.dumps({"source_files": len(result["source_file_hashes"]), "production_assets": len(result["production_asset_hashes"]),
                          "runtime": str(RUNTIME), "reference": str(REFERENCE), "baseline_sha256": result["baseline_sha256"]}))
    elif action == "prepare":
        prepare()
    elif action == "serve":
        serve()
    else:
        module = launcher()
        print(json.dumps({"prepared": (RUNTIME / "setup-manifest.json").exists(),
                          "backend": module.healthy("http://127.0.0.1:12138/healthz"),
                          "frontend": module.healthy("http://127.0.0.1:12042")}))
