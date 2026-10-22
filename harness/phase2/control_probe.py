"""Windows↔WSL control/HTTP clock and immutable declaration integration check."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

from .management import provision_runtime, wsl_python, DISTRO, LINUX_ROOT, ROOT
from .relay import FixedOriginRelay
from .prediction_record import PredictionRecorder
from .records import write_new_json


def main():
    runtime, digest = provision_runtime()
    identifier = "control-canary-" + str(time.time_ns())
    private = ROOT / "harness/experiments/phase2-discogs-20261021-01/isolation" / identifier
    private.mkdir()
    before = private / "before.json"
    write_new_json(before, {"generic": "before", "captured_at_ns": time.time_ns()})
    recorder = PredictionRecorder("generic-case", before, private / "prediction.json")
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *args):
            pass
    events = []
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as fixture:
        threading.Thread(target=fixture.serve_forever, daemon=True).start()
        socket = LINUX_ROOT + "/" + identifier + ".sock"
        control = LINUX_ROOT + "/" + identifier + "-private-control.sock"
        command = ["wsl", "-d", DISTRO, "--", "python3", runtime + "/relay.py", "linux",
                   "--socket", socket, "--origin", "http://127.0.0.1:12042", "--control-socket", control]
        relay = FixedOriginRelay(command, "http://127.0.0.1:12042", "127.0.0.1", fixture.server_port,
                                 private / "stderr.txt", callback=events.append, control_callback=recorder)
        try:
            if not relay.ready.wait(20):
                raise RuntimeError("relay unavailable")
            code = """import sys,socket,json,urllib.request,os
sys.path.insert(0,RUNTIME)
from unix_bridge import playwright_proxy
def declare(case,before):
 message={'command':'declare_prediction','case_id':case,'before_sha256':before,
 'prediction':{'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['generic fixture']}}
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
  client.connect(CONTROL);client.sendall(json.dumps(message).encode()+b'\\n')
  return json.loads(client.makefile('rb').readline())
out={'wrong_case':declare('different-case',BEFORE),'wrong_digest':declare('generic-case','0'*64),
     'first':declare('generic-case',BEFORE),'repeated':declare('generic-case',BEFORE)}
os.environ['NO_PROXY']='';os.environ['no_proxy']=''
with playwright_proxy(SOCKET) as proxy:
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy['server']}))
 response=opener.open(urllib.request.Request('http://127.0.0.1:12042/generic-write',data=b'abc',method='POST'),timeout=10)
 out['http_status']=response.status;response.read()
print(json.dumps(out))
""".replace("RUNTIME", repr(runtime)).replace("CONTROL", repr(control)).replace("SOCKET", repr(socket)).replace("BEFORE", repr(recorder.before_sha256))
            process = wsl_python(code)
            if process.returncode:
                raise RuntimeError(process.stderr.decode())
            result = json.loads(process.stdout)
            prediction = json.loads((private / "prediction.json").read_text())
            checks = {"wrong_case_denied": result["wrong_case"]["status"] == "denied",
                      "wrong_digest_denied": result["wrong_digest"]["status"] == "denied",
                      "first_frozen": result["first"]["status"] == "frozen",
                      "repeat_denied": result["repeated"]["status"] == "denied",
                      "http_success": result["http_status"] == 200,
                      "dispatch_saved": len(events) == 2 and events[0]["event_phase"] == "dispatch",
                      "same_clock_order": prediction["declared_at_ns"] < events[0]["management_request_started_ns"],
                      "no_relay_error": not relay.errors}
            write_new_json(private / "result.json", {"status": "passed" if all(checks.values()) else "failed",
                                                       "checks": checks, "runtime_sha256": digest, "actual_result": result,
                                                       "declaration_ns": prediction["declared_at_ns"],
                                                       "request_start_ns": events[0]["management_request_started_ns"]})
            assert all(checks.values()), checks
            print(json.dumps({"status": "passed", "checks": len(checks), "evidence": str(private)}))
        finally:
            relay.close()
            fixture.shutdown()


if __name__ == "__main__":
    main()
