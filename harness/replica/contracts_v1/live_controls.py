"""Small site-independent browser controls; intentionally no target application."""
from __future__ import annotations

import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.request import urlopen

from .runner import run_source

HTML = b'''<!doctype html><html><head><title>Contract fixture</title></head><body>
<h1>Contract fixture</h1><button aria-pressed="false" onclick="fetch('/enable').then(()=>this.setAttribute('aria-pressed','true'))">Enable</button>
<button onclick="fetch('/finish')">Finish</button><ul aria-label="External"><li>changing value 73</li></ul>
</body></html>'''


class FixtureServer(ThreadingHTTPServer):
    def __init__(self):
        self.facts = {"enable": 0, "finish": 0}
        super().__init__(("127.0.0.1", 0), FixtureHandler)


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/reset":
            self.server.facts = {"enable": 0, "finish": 0}
        if self.path in ("/enable", "/finish"):
            self.server.facts[self.path[1:]] += 1
        body = HTML if self.path == "/" else json.dumps(self.server.facts).encode() if self.path == "/facts" else b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if self.path == "/" else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class FixtureOracle:
    """Independent server-side effects; never consults predicted contract values."""
    def __init__(self, server, evidence):
        self.server = server
        self.evidence = evidence

    def describe(self):
        return {"independent": True, "scope": "generic fixture server counters independent of browser prediction"}

    def prepare(self, lane, case_ref):
        with urlopen("http://127.0.0.1:" + str(self.server.server_port) + "/reset", timeout=3) as response:
            response.read()
        return {"initial_equivalence": "pass", "reset_receipt": "generic fixture counters reset"}

    def capture(self, lane, case_ref, checkpoint):
        with urlopen("http://127.0.0.1:" + str(self.server.server_port) + "/facts", timeout=3) as response:
            facts = json.load(response)
        path = self.evidence / (str(checkpoint["kind"]) + "-" + str(checkpoint["action"]) + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(facts))
        return {"status": "confirmed", "facts": facts, "logical_object_identities": ["fixture"],
                "coverage": {"server_counters": True}, "evidence_refs": [str(path)]}

    def assess(self, case_ref, checkpoint, previous, current, action):
        count = checkpoint["action"]
        expected = {"enable": int(count >= 1), "finish": int(count >= 2)}
        passed = current["facts"] == expected
        return {"verdict": "pass" if passed else "fail", "checks": [{"id": "server_effects", "pass": passed}],
                "evidence_refs": current["evidence_refs"]}


def contract(required, slots=None):
    return {"schema": "component-contract/v1", "parameters": {"$type": "object"},
            "slots": slots or {}, "coverage": [row["id"] for row in required],
            "branches": {"ready": {"required": required, "forbidden": [], "relations": []}}}


def prediction(ref, unknown=None):
    return {"disposition": "accepted", "contract_ref": ref, "branch": "ready", "parameters": {}, "unknown_slots": unknown or []}


def run_controls(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    server = FixtureServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    rows = []
    try:
        for variant in ("normal", "wrong_state", "unbound_slot"):
            directory = out / variant
            directory.mkdir()
            heading = {"id": "heading", "select": {"role": "heading", "name": "Contract fixture"}}
            required = [heading, {"id": "enabled", "select": {"role": "button", "name": "Enable", "properties": {"pressed": "false" if variant == "wrong_state" else "true"}}}]
            slots = {"external": {"type": "string", "required": True}} if variant == "unbound_slot" else {}
            bundle = {"schema": "component-contract-bundle/v1", "contracts": {"initial": contract([heading]), "enabled": contract(required, slots), "final": contract([heading])}}
            bundle_path = directory / "contracts.json"
            bundle_path.write_text(json.dumps(bundle))
            pred = prediction("enabled", ["external"] if slots else [])
            script = "def run(h):\n    h.expect(" + repr(pred) + ")\n    h.page.get_by_role('button', name='Enable', exact=True).click()\n    h.expect(" + repr(prediction("final")) + ")\n    h.page.get_by_role('button', name='Finish', exact=True).click()\n    return {'done': True}\n"
            script_path = directory / "script.py"
            script_path.write_text(script)
            result = run_source({"origin": "http://fixture.invalid", "upstream_host": "127.0.0.1", "upstream_port": server.server_port,
                                 "public_fixture": {}}, script_path, directory / "run", bundle_path,
                                oracle=FixtureOracle(server, directory / "truth"), case_ref=variant,
                                state0_prediction=prediction("initial"), final_prediction=prediction("final"),
                                policy={"wall_seconds": 120, "progress_seconds": 40, "action_limit": 4,
                                        "lease_directory": str(out / "operation-lease")})
            row = {"variant": variant, "primary_pass": result["primary_pass"], "reason": result["reason"],
                   "checked_actions": result["checked_actions"], "facts": deepcopy(server.facts),
                   "cleanup": result["source"]["process_tree_clean"], "result": str(directory / "run/result.json")}
            row["control_pass"] = (row["primary_pass"] and row["facts"] == {"enable": 1, "finish": 1}) if variant == "normal" else (
                not row["primary_pass"] and row["checked_actions"] == 1 and row["facts"] == {"enable": 1, "finish": 0})
            rows.append(row)
            print(json.dumps(row), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    summary = {"schema": "generic-contract-live-controls/v1", "pass": all(row["control_pass"] and row["cleanup"] for row in rows), "runs": rows}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    arguments = parser.parse_args()
    raise SystemExit(0 if run_controls(arguments.out)["pass"] else 1)
