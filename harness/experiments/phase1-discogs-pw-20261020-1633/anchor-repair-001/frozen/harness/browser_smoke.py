"""Live generic browser transport check; never a target-site experiment score."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import traceback
from uuid import uuid4

from .browser import Browser


HTML = b"""<!doctype html><html><head><title>Harness transport fixture</title></head>
<body><h1>Harness transport fixture</h1><label>Name <input id="name"></label>
<button id="save" onclick="document.getElementById('result').textContent='Saved: '+document.getElementById('name').value;document.cookie='fixture=1'">Save</button>
<p id="result">Empty</p><button class="duplicate">One</button><button class="duplicate">Two</button>
<div style="height:1600px"></div><button id="bottom" onclick="document.getElementById('result').textContent='Scrolled and clicked'">Bottom action</button>
</body></html>"""


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cdp")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    events = []
    checks = []
    site = {"base_url": f"http://127.0.0.1:{server.server_port}", "allowed_hosts": ["127.0.0.1"]}
    browser = Browser(site, f"smoke-{uuid4().hex[:12]}", cdp_url=args.cdp, event_sink=events.append)
    result = {"kind": "generic_browser_transport_only", "target_site_score": False,
              "started_at": datetime.now(timezone.utc).isoformat(), "checks": checks}
    try:
        browser.start()
        browser.act({"kind": "open", "url": "/"})
        browser.wait({"kind": "selector", "value": "#name"})
        browser.act({"kind": "fill", "selector": "#name", "value": "Solar fixture"})
        browser.wait({"kind": "selector", "value": "#save"})
        browser.act({"kind": "click", "selector": "button:has-text('Save')"})
        browser.wait({"kind": "text", "value": "Saved: Solar fixture"})
        observation = browser.observe({"result": {"kind": "text", "selector": "#result"}})
        checks.append({"id": "real_keyboard_and_click", "passed": observation["fields"]["result"] == "Saved: Solar fixture"})
        try:
            browser.act({"kind": "click", "selector": ".duplicate"})
            checks.append({"id": "ambiguous_locator_rejected", "passed": False})
        except RuntimeError as exc:
            checks.append({"id": "ambiguous_locator_rejected", "passed": str(exc).startswith("locator:")})
        browser.act({"kind": "click", "selector": "#bottom"})
        browser.wait({"kind": "text", "value": "Scrolled and clicked"})
        checks.append({"id": "offscreen_scroll_and_click", "passed": True})
        browser.screenshot(output / "fixture.png")
        checks.append({"id": "screenshot", "passed": (output / "fixture.png").stat().st_size > 100})
        # Check actual cookie state in a distinct context on the same Chrome.
        other = Browser(site, f"smoke-{uuid4().hex[:12]}", cdp_url=browser.cdp_url, event_sink=events.append)
        try:
            other.start()
            other.act({"kind": "open", "url": "/"})
            other.wait({"kind": "selector", "value": "#name"})
            cookies = other.call("Network.getCookies", {"urls": [site["base_url"]]})["cookies"]
            checks.append({"id": "fresh_case_cookie_isolation", "passed": not any(c["name"] == "fixture" for c in cookies)})
        finally:
            other.close()
        result["status"] = "passed" if all(c["passed"] for c in checks) else "failed"
    except Exception as exc:
        result.update(status="blocked_or_failed", error=str(exc), traceback=traceback.format_exc())
    finally:
        browser.close()
        server.shutdown()
        server.server_close()
        result["ended_at"] = datetime.now(timezone.utc).isoformat()
        (output / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
