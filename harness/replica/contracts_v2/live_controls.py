"""Two generic live controls for repeated descendants and bounded completion."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import threading

from harness.replica.contracts_v1 import live_controls as fixture
from .runner import run_source


def contract(rows, fail=False):
    required = [{"id": "heading", "select": {"role": "heading", "name": "Contract fixture"}}]
    if rows:
        required.append({"id": "rows", "select": {"source": "dom", "tag": "SECTION", "attributes": {"class": "entry"}},
            "count": {"min": 2, "max": 2}, "has": [{"select": {"source": "dom", "tag": "H2"}, "count": {"min": 1, "max": 1}}],
            "each": {"required": [{"id": "title", "select": {"source": "dom", "tag": "H2"}},
                                    {"id": "control", "select": {"source": "dom", "tag": "BUTTON", "attributes": {"class": "required"}}, "count": {"min": 1, "max": 1}}],
                     "forbidden": [], "relations": [{"id": "ownership", "kind": "parent", "left": "control", "right": "$parent"}]}})
    return {"schema": "component-contract/v2", "parameters": {"$type": "object"}, "slots": {},
            "coverage": [row["id"] for row in required], "branches": {"ready": {"required": required, "forbidden": [], "relations": []}}}


def run_controls(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for variant in ("normal", "missing_child"):
        server = fixture.FixtureServer()
        button = "<button class='required'>Local action</button>" if variant == "normal" else ""
        cards = "<section class='entry'><h2>First</h2><button class='required'>Local action</button></section><section class='entry'><h2>Second</h2>" + button + "</section>"
        fixture.HTML = ("<!doctype html><html><body><h1>Contract fixture</h1><button onclick=\"fetch('/enable').then(()=>document.getElementById('rows').innerHTML=" + json.dumps(cards).replace('"', '&quot;') + ")\">Enable</button><button onclick=\"fetch('/finish')\">Finish</button><div id='rows'></div></body></html>").encode()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        directory = out / variant
        directory.mkdir()
        try:
            bundle = {"schema": "component-contract-bundle/v2", "contracts": {"initial": contract(False), "rows": contract(True), "final": contract(True)}}
            bundle_path = directory / "contracts.json"
            bundle_path.write_text(json.dumps(bundle))
            script_path = directory / "script.py"
            script_path.write_text("def run(h):\n    h.expect(" + repr(fixture.prediction("rows")) + ")\n    h.page.get_by_role('button', name='Enable', exact=True).click()\n    h.expect(" + repr(fixture.prediction("final")) + ")\n    h.page.get_by_role('button', name='Finish', exact=True).click()\n")
            result = run_source({"origin": "http://fixture.invalid", "upstream_host": "127.0.0.1", "upstream_port": server.server_port, "public_fixture": {}},
                script_path, directory / "run", bundle_path, oracle=fixture.FixtureOracle(server, directory / "truth"), case_ref=variant,
                state0_prediction=fixture.prediction("initial"), final_prediction=fixture.prediction("final"),
                policy={"wall_seconds": 90, "progress_seconds": 35, "action_limit": 3, "completion_cleanup_seconds": 20, "lease_directory": str(out / "operation-lease")})
            row = {"variant": variant, "primary_pass": result["primary_pass"], "reason": result["reason"], "checked_actions": result["checked_actions"],
                   "facts": deepcopy(server.facts), "browser_cleanup": result["source"].get("process_tree_clean"), "oracle_cleanup": result.get("oracle_process_tree_clean")}
            row["control_pass"] = (row["primary_pass"] and row["facts"] == {"enable": 1, "finish": 1}) if variant == "normal" else (not row["primary_pass"] and row["checked_actions"] == 1 and row["facts"] == {"enable": 1, "finish": 0})
            rows.append(row)
            print(json.dumps(row), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    summary = {"schema": "generic-contract-live-controls/v2", "pass": all(row["control_pass"] and row["browser_cleanup"] and row["oracle_cleanup"] for row in rows), "runs": rows}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run_controls(args.out)["pass"] else 1)
