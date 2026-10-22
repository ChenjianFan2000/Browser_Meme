"""Protocol 4 deployment: new state/logs, unchanged cached original production site.

Prepare does not start services. Serve refuses both occupied ports, even if the
listener is unhealthy, and delegates owned-process cleanup to the existing launcher.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path(os.environ.get("BM_DISCOGS_RUNTIME", ROOT / ".runtime/phase1-closed-loop-20261021")).resolve()
REFERENCE = Path(os.environ.get("BM_DISCOGS_REFERENCE_RUNTIME", ROOT / ".runtime/phase1-discogs-pw-20261020-1633")).resolve()


def _delegate():
    if RUNTIME == REFERENCE or RUNTIME.is_relative_to(REFERENCE):
        raise RuntimeError("Closed-loop state must be separate from archived reference")
    os.environ["BM_DISCOGS_RUNTIME"] = str(RUNTIME)
    os.environ["BM_DISCOGS_REFERENCE_RUNTIME"] = str(REFERENCE)
    spec = importlib.util.spec_from_file_location("discogs_loop_reference_deployment", Path(__file__).with_name("complex_deploy.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ports():
    result = {}
    for port in (12042, 12138):
        with socket.socket() as probe:
            probe.settimeout(0.5)
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) == 0
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "prepare", "serve", "status"))
    action = parser.parse_args().action
    module = _delegate()
    if action == "prepare":
        module.prepare()
    elif action == "serve":
        listeners = ports()
        if any(listeners.values()):
            raise RuntimeError(f"Refusing cross-runtime listener reuse: {listeners}")
        marker = os.environ.get("HARNESS_STOP_FILE")
        if not marker or not Path(marker).resolve().is_relative_to(RUNTIME):
            raise RuntimeError("A unique HARNESS_STOP_FILE inside this runtime is required")
        if Path(marker).exists():
            raise RuntimeError("Stop marker already exists; choose a new launch marker")
        module.serve()
    elif action == "inspect":
        record = module.inspect()
        print(json.dumps({"runtime": str(RUNTIME), "reference": str(REFERENCE),
                          "source_files": len(record["source_file_hashes"]),
                          "production_assets": len(record["production_asset_hashes"]),
                          "baseline_sha256": record["baseline_sha256"],
                          "ports_occupied": ports(), "services_started": False}))
    else:
        print(json.dumps({"runtime": str(RUNTIME), "prepared": (RUNTIME / "setup-manifest.json").is_file(),
                          "ports_occupied": ports(), "services_started": False}))


if __name__ == "__main__":
    main()
