"""Trusted Windows/WSL stdio relay for one website origin.

No Windows listener is opened. The Linux end exposes only a filesystem Unix
socket. The native Playwright browser uses the sandbox-local HTTP/Unix bridge.
The model process never gets a route to host TCP ports or this process's files.
"""
from __future__ import annotations

import argparse
import base64
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import socketserver
import threading
import time
from urllib.parse import urlsplit
import uuid

HOP_HEADERS = {"connection", "proxy-connection", "proxy-authorization", "proxy-authenticate",
               "keep-alive", "te", "trailer", "transfer-encoding", "upgrade", "content-length"}
MAX_BODY = 32 * 1024 * 1024


class RPCClient:
    def __init__(self):
        self.write_lock = threading.Lock()
        self.pending = {}
        self.pending_lock = threading.Lock()
        self.closed = threading.Event()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            for line in sys.stdin.buffer:
                response = json.loads(line)
                with self.pending_lock:
                    item = self.pending.get(response["id"])
                if item:
                    item[1].update(response)
                    item[0].set()
        finally:
            self.closed.set()

    def call(self, request):
        key = uuid.uuid4().hex
        event, response = threading.Event(), {}
        with self.pending_lock:
            self.pending[key] = (event, response)
        try:
            data = json.dumps({"id": key, **request}, separators=(",", ":")).encode() + b"\n"
            with self.write_lock:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            if not event.wait(40):
                raise TimeoutError("fixed-origin relay timed out")
            return response
        finally:
            with self.pending_lock:
                self.pending.pop(key, None)


def linux_serve(socket_path: str, origin: str, control_socket: str | None = None):
    from unix_gateway import make_gateway

    rpc = RPCClient()

    class Control(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline(65537)
            if len(line) > 65536:
                return
            try:
                message = json.loads(line)
                if message.get("command") != "declare_prediction":
                    raise ValueError("unknown control operation")
                response = rpc.call({"control": message})
                self.wfile.write(json.dumps(response.get("control_result", {"error": "unavailable"})).encode() + b"\n")
            except Exception as error:
                self.wfile.write(json.dumps({"error": type(error).__name__}).encode() + b"\n")

    control = None
    if control_socket:
        import os
        control = socketserver.ThreadingUnixStreamServer(control_socket, Control)
        os.chmod(control_socket, 0o600)
        threading.Thread(target=control.serve_forever, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def forward(self):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= MAX_BODY:
                self.send_error(413)
                return
            request_body = self.rfile.read(length)
            try:
                response = rpc.call({"method": self.command, "path": self.path,
                                     "headers": list(self.headers.items()),
                                     "body": base64.b64encode(request_body).decode()})
                body = base64.b64decode(response["body"], validate=True)
                self.send_response(response["status"])
                for key, value in response["headers"]:
                    if key.lower() not in HOP_HEADERS:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            except (OSError, ValueError, KeyError, TimeoutError):
                self.close_connection = True

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = forward

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as local:
        worker = threading.Thread(target=local.serve_forever, daemon=True)
        worker.start()
        gateway = make_gateway(socket_path, origin, "127.0.0.1", local.server_port, MAX_BODY)
        try:
            threading.Thread(target=gateway.serve_forever, daemon=True).start()
            with rpc.write_lock:
                sys.stdout.buffer.write(json.dumps({"event": "ready", "socket": socket_path}).encode() + b"\n")
                sys.stdout.buffer.flush()
            rpc.closed.wait()
        finally:
            gateway.shutdown()
            gateway.server_close()
            local.shutdown()
            Path(socket_path).unlink(missing_ok=True)
            if control:
                control.shutdown()
                control.server_close()
                Path(control_socket).unlink(missing_ok=True)


class FixedOriginRelay:
    """Management-side owner; callbacks receive actual HTTP bytes, never predictions."""

    def __init__(self, command: list[str], origin: str, upstream_host: str, upstream_port: int,
                 stderr_path: Path, callback=None, control_callback=None):
        expected = urlsplit(origin)
        if expected.scheme != "http" or not expected.hostname or expected.username or expected.password:
            raise ValueError("one HTTP origin is required")
        self.origin = origin.rstrip("/")
        self.authority = expected.netloc
        self.host, self.port = upstream_host, upstream_port
        self.callback = callback
        self.control_callback = control_callback
        self.errors = []
        self.active = set()
        self.active_condition = threading.Condition()
        self.ready = threading.Event()
        self.write_lock = threading.Lock()
        self.stderr = stderr_path.open("xb")
        self.child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=self.stderr, creationflags=0x08000000 if sys.platform == "win32" else 0)
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        try:
            for line in self.child.stdout:
                item = json.loads(line)
                if item.get("event") == "ready":
                    self.ready.set()
                else:
                    worker = threading.Thread(target=self.forward, args=(item,), daemon=True)
                    with self.active_condition:
                        self.active.add(worker)
                    worker.start()
        except Exception as error:
            self.errors.append(type(error).__name__)

    def forward(self, item):
        response = {"id": item["id"], "status": 502, "headers": [], "body": ""}
        connection = None
        started = time.monotonic()
        request_started_ns = time.time_ns()
        try:
            if "control" in item:
                if not self.control_callback:
                    raise ValueError("control channel is disabled")
                response["control_result"] = self.control_callback(item["control"])
                return
            path = item["path"]
            if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
                raise ValueError("relay accepts only an origin-relative path")
            if any(ord(char) < 32 for char in path):
                raise ValueError("control character in path")
            if item["method"] not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
                raise ValueError("method denied")
            body = base64.b64decode(item["body"], validate=True)
            if len(body) > MAX_BODY:
                raise ValueError("request too large")
            headers = {key: value for key, value in item["headers"] if key.lower() not in HOP_HEADERS}
            headers["Host"] = self.authority
            if self.callback:
                self.callback({"method": item["method"], "url": self.origin + path,
                               "status": 0, "request_body": body, "response_body": b"",
                               "content_type": "", "elapsed_seconds": 0,
                               "management_request_started_ns": request_started_ns,
                               "event_phase": "dispatch", "source": "trusted_fixed_origin_gateway"})
            connection = http.client.HTTPConnection(self.host, self.port, timeout=30)
            connection.request(item["method"], path, body=body, headers=headers)
            actual = connection.getresponse()
            actual_body = actual.read(MAX_BODY + 1)
            if len(actual_body) > MAX_BODY:
                raise ValueError("response too large")
            actual_headers = actual.getheaders()
            response.update(status=actual.status, headers=actual_headers,
                            body=base64.b64encode(actual_body).decode())
            if self.callback:
                self.callback({"method": item["method"], "url": self.origin + path,
                               "status": actual.status, "request_body": body,
                               "response_body": actual_body,
                               "content_type": actual.getheader("Content-Type", ""),
                               "elapsed_seconds": time.monotonic() - started,
                               "management_request_started_ns": request_started_ns,
                               "event_phase": "response",
                               "source": "trusted_fixed_origin_gateway"})
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            if connection:
                connection.close()
            try:
                with self.write_lock:
                    self.child.stdin.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")
                    self.child.stdin.flush()
            except (OSError, ValueError):
                pass
            with self.active_condition:
                self.active.discard(threading.current_thread())
                self.active_condition.notify_all()

    def close(self):
        deadline = time.monotonic() + 40
        # Stop the Linux ingress before draining. Its final stdout records may
        # still dispatch work, so the reader must finish before the active set
        # can be considered complete.
        if self.child.stdin and not self.child.stdin.closed:
            self.child.stdin.close()
        try:
            self.child.wait(timeout=min(10, max(0.1, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            self.child.terminate()
            try:
                self.child.wait(timeout=min(5, max(0.1, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                self.child.kill()
                try:
                    self.child.wait(timeout=min(5, max(0.1, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    self.errors.append("unsettled_requests_at_close")
        self.thread.join(timeout=max(0, deadline - time.monotonic()))
        with self.active_condition:
            while self.active and time.monotonic() < deadline:
                self.active_condition.wait(timeout=min(1, deadline - time.monotonic()))
            if (self.active or self.thread.is_alive()) and "unsettled_requests_at_close" not in self.errors:
                self.errors.append("unsettled_requests_at_close")
        self.stderr.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["linux"])
    parser.add_argument("--socket", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--control-socket")
    args = parser.parse_args()
    linux_serve(args.socket, args.origin, args.control_socket)


if __name__ == "__main__":
    main()
