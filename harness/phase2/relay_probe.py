"""Verify cross-platform relay using a generic fixture, with no target knowledge."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

from .management import provision_runtime, wsl_python, DISTRO, LINUX_ROOT, ROOT
from .relay import FixedOriginRelay


def main():
    runtime, digest = provision_runtime()
    identifier = "relay-canary-" + str(time.time_ns())
    private = ROOT / "harness/experiments/phase2-discogs-20261021-01/isolation" / identifier
    private.mkdir()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<title>Relay fixture</title><button>Generic control</button>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"length": len(body), "path": self.path}).encode())
        def log_message(self, *args):
            pass
    events = []
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as fixture:
        threading.Thread(target=fixture.serve_forever, daemon=True).start()
        socket = LINUX_ROOT + "/" + identifier + ".sock"
        command = ["wsl", "-d", DISTRO, "--", "python3", runtime + "/relay.py", "linux",
                   "--socket", socket, "--origin", "http://127.0.0.1:12042"]
        relay = FixedOriginRelay(command, "http://127.0.0.1:12042", "127.0.0.1", fixture.server_port,
                                 private / "stderr.txt", callback=events.append)
        try:
            if not relay.ready.wait(20):
                raise RuntimeError("relay failed to become ready")
            code = """import sys,urllib.request,json
sys.path.insert(0,RUNTIME)
from unix_bridge import playwright_proxy
with playwright_proxy(SOCKET) as proxy:
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy['server']}))
 import os
 os.environ['NO_PROXY']='';os.environ['no_proxy']=''
 get=opener.open('http://127.0.0.1:12042/',timeout=10)
 result={'get_status':get.status,'body':get.read().decode()}
 post=opener.open(urllib.request.Request('http://127.0.0.1:12042/echo?a=1',data=b'abc',method='POST'),timeout=10)
 result['post_status']=post.status;result['post']=json.load(post)
 try:
  opener.open('http://127.0.0.1:12043/',timeout=10)
  result['wrong_port']='allowed'
 except Exception as error: result['wrong_port']=str(error)
 print(json.dumps(result))
""".replace("RUNTIME", repr(runtime)).replace("SOCKET", repr(socket))
            result = wsl_python(code)
            record = {"runtime_sha256": digest, "exit_code": result.returncode,
                      "stdout": result.stdout.decode(), "stderr": result.stderr.decode(),
                      "trusted_event_count": len(events), "relay_errors": relay.errors}
            (private / "result.json").write_text(json.dumps(record, indent=2))
            if result.returncode:
                raise RuntimeError(record)
            parsed = json.loads(record["stdout"])
            assert parsed["get_status"] == 200 and parsed["post_status"] == 201
            assert parsed["post"] == {"length": 3, "path": "/echo?a=1"}
            assert "403" in parsed["wrong_port"] and len(events) == 4 and not relay.errors
            assert [event["event_phase"] for event in events] == ["dispatch", "response", "dispatch", "response"]
            print(json.dumps({"status": "passed", "evidence": str(private), "checks": 5}))
        finally:
            relay.close()
            fixture.shutdown()


if __name__ == "__main__":
    main()
