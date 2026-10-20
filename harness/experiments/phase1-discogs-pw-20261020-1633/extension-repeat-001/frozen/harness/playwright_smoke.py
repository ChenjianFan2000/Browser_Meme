"""Real native Playwright transport acceptance; contains no website tasks."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time

from .artifacts import Recorder, write_json
from .playwright_run import ScriptHarness, sanitize_trace

HTML = b"""<!doctype html><html><meta charset="utf-8"><title>Harness fixture</title>
<label>Name <input id="name"></label><button class="duplicate">X</button>
<button class="duplicate">X</button><div style="height:1700px"></div>
<button id="save" onclick="document.querySelector('#result').textContent=document.querySelector('#name').value;
document.cookie='fixture=present;path=/'">Save</button><output id="result"></output></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *_):
        pass


class ReadOnlyFixture:
    def observe(self):
        return {"fixture": "unchanged"}


def execute(out):
    from playwright.sync_api import sync_playwright
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(out / "events.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks = []
    result = {"status": "failed", "checks": checks, "started_at": time.time()}
    case = {"id": "generic", "goal": "native transport only", "parameters": {}, "steps": [
        {"id": "navigate", "rule_ids": ["fixture"], "action": "navigate",
         "expect": [{"id": "rendered", "checks": [{"path": "after.ui.title", "op": "eq", "value": "Harness fixture"}]}]},
        {"id": "fill", "rule_ids": ["fixture"], "action": "fill",
         "expect": [{"id": "filled", "checks": [{"path": "after.ui.fields.name", "op": "eq", "value": "native"}]}]},
        {"id": "save", "rule_ids": ["fixture"], "action": "click",
         "expect": [{"id": "saved", "checks": [{"path": "after.ui.text", "op": "contains", "value": "native"}]}]},
    ]}
    try:
        with sync_playwright() as pw:
            options = {"headless": True, "chromium_sandbox": True}
            executable = os.environ.get("HARNESS_CHROME")
            options.update({"executable_path": executable} if executable else {"channel": "chrome"})
            browser = pw.chromium.launch(**options)
            result["browser_version"] = browser.version
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.set_default_timeout(10000)
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            h = ScriptHarness(page, case, {"readouts": {"name": {"selector": "#name", "kind": "value"}}},
                              ReadOnlyFixture(), out, recorder, [], base)
            with h.step("navigate"):
                page.goto(base)
            with h.step("fill"):
                h.confirm(page.get_by_label("Name")).fill("native")
            with h.step("save"):
                try:
                    h.confirm(page.locator(".duplicate"))
                except RuntimeError as exc:
                    checks.append({"id": "ambiguous_target_rejected", "passed": "exactly one" in str(exc)})
                h.confirm(page.get_by_role("button", name="Save", exact=True)).click()
                page.locator("#result").filter(has_text="native").wait_for()
            checks.append({"id": "all_native_steps_matched", "passed": all(s["status"] == "matched" for s in h.results)})
            checks.append({"id": "actually_scrolled", "passed": page.evaluate("scrollY") > 0
                           and page.locator("#save").is_visible()})
            other = browser.new_context()
            other_page = other.new_page()
            other_page.goto(base)
            checks.append({"id": "context_cookie_isolation", "passed": other.cookies() == [] and bool(context.cookies())})
            other.close()
            raw = out / ".raw-trace.zip"
            context.tracing.stop(path=str(raw))
            sanitize_trace(raw, out / "trace.zip")
            raw.unlink()
            context.close()
            browser.close()
            checks.append({"id": "raw_dom_preserved", "passed": any('id="name"' in frame["html"]
                           for frame in json.loads((out / "01.dom.json").read_text()))})
            events = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
            sequence = [e["kind"] for e in events]
            checks.append({"id": "prediction_precedes_dispatch", "passed": all(
                sequence[i - 1] == "prediction" for i, kind in enumerate(sequence) if kind == "action_dispatch")})
            result["status"] = "passed" if all(c["passed"] for c in checks) else "failed"
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        recorder.close()
        server.shutdown()
        server.server_close()
        result["ended_at"] = time.time()
        write_json(out / "result.json", result)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raise SystemExit(0 if execute(args.out)["status"] == "passed" else 1)
