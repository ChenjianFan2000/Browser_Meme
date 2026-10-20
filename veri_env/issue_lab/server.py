"""Serve the miniature issue UI on loopback using only Python's standard library.

GET /api/state returns the complete public observation, including all issues
regardless of filtering. POST /api/action accepts a JSON action; see domain.py
for action and observation schemas. POST /admin/reset accepts a JSON object
with optional seed (integer), version (1 or 2), and role (editor or viewer).
Reset is an experiment administration operation, not a learner action.
GET / serves the accessible HTML UI. The rule version is never returned.
Run: python -m issue_lab.server --port 8877 --seed 0 --version 1 --role editor
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

from . import domain as domain_module
from .domain import IssueDomain


class IssueServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], domain: IssueDomain):
        super().__init__(address, IssueHandler)
        self.domain = domain
        self.state_lock = RLock()


class IssueHandler(BaseHTTPRequestHandler):
    server: IssueServer

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "service": "issue_lab"})
        elif path == "/api/state":
            with self.server.state_lock:
                self._json(200, self.server.domain.observe())
        elif path == "/":
            body = Path(__file__).with_name("index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in ("/api/action", "/admin/reset"):
            self._json(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                raise ValueError("JSON body must be 1..65536 bytes")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            with self.server.state_lock:
                if path == "/admin/reset":
                    if set(data) - {"seed", "version", "role"}:
                        raise ValueError("reset accepts seed, version, role only")
                    state = self.server.domain.reset(**data)
                else:
                    state = self.server.domain.step(data)
                self._json(200, state)
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self._json(400, {"error": "invalid_request", "detail": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Action and observation schema:\n" + domain_module.__doc__)
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--role", choices=("editor", "viewer"), default="editor")
    args = parser.parse_args()
    server = IssueServer(("127.0.0.1", args.port),
                         IssueDomain(args.seed, args.version, args.role))
    print(f"Miniature issue workflow: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
