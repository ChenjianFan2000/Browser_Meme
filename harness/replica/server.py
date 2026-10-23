"""Serve only a generated offline replica bundle, with explicit route fallback."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


class ReplicaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, entry="index.html", **kwargs):
        self.bundle = Path(directory).resolve()
        self.entry = entry
        super().__init__(*args, directory=str(self.bundle), **kwargs)

    def log_message(self, format, *args):
        # No auth data, query strings or model HTML in management logs.
        print(json.dumps({"event": "replica_http", "method": self.command,
                          "path": urlsplit(self.path).path, "status": str(args[1]) if len(args)>1 else None}), flush=True)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self' data:; connect-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; form-action 'self'")
        super().end_headers()

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/__replica_health__":
            body = b'{"status":"ready","kind":"static_browser_app"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if any(p in {"..", ".git", "private", "codex-home"} for p in path.split("/")):
            self.send_error(403)
            return
        requested = (self.bundle / path.lstrip("/")).resolve()
        try:
            requested.relative_to(self.bundle)
        except ValueError:
            self.send_error(403)
            return
        if requested.exists() and (requested.is_symlink() or requested.is_dir()):
            if path != "/":
                self.send_error(403)
                return
        if not requested.is_file():
            # Route fallback only for document-like URLs, never missing assets/API.
            if requested.suffix or path.startswith(("/api/", "/private/")):
                self.send_error(404)
                return
            self.path = "/" + self.entry
        super().do_GET()


def make_server(directory, port, *, entry="index.html", host="127.0.0.1"):
    directory = Path(directory).resolve()
    if not (directory / entry).is_file():
        raise ValueError("replica entry is missing")
    return ThreadingHTTPServer((host, port), partial(ReplicaHandler, directory=directory, entry=entry))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--entry", default="index.html")
    args = parser.parse_args()
    with make_server(args.directory, args.port, entry=args.entry) as server:
        print(json.dumps({"event": "replica_server_ready", "port": args.port}), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
