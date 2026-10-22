"""WSL-side generic broker audit; file transfer is supplied by trusted launcher."""
import hashlib
import json
import pathlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = pathlib.Path('/opt/browser-meme/tmp/phase2-isolation-audit')
ROOT = BASE / 'mcp-audit-006'
RUNTIME = ROOT / 'runtime'
WORK = ROOT / 'workspace'
PRIVATE = ROOT / 'private'
for path in [RUNTIME, WORK, PRIVATE]:
    path.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(BASE))
from unix_gateway import make_gateway
from permissions import CODEX


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'''<html><title>Generic broker audit</title><h1>Generic fixture</h1>
<button onclick="this.textContent='Clicked'">Generic Canary</button>
<label>API credential<input name="token" value="TOKEN_CANARY_006"></label>
<script>const JS_SOURCE_CANARY_006='not-an-observation';</script></html>''')

    def log_message(self, *args):
        pass


http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=http.serve_forever, daemon=True).start()
origin = f'http://127.0.0.1:{http.server_port}'
socket = ROOT / 'site.sock'
socket.unlink(missing_ok=True)
gateway = make_gateway(socket, origin, '127.0.0.1', http.server_port)
threading.Thread(target=gateway.serve_forever, daemon=True).start()
fixture = PRIVATE / 'fixture.json'
fixture.write_text(json.dumps({'kind': 'generic-audit'}))
state = {'cookies': [{'name': 'audit_cookie', 'value': 'COOKIE_CANARY_006', 'domain': '127.0.0.1', 'path': '/', 'expires': -1, 'httpOnly': True, 'secure': False, 'sameSite': 'Lax'}], 'origins': []}
(PRIVATE / 'browser-state.json').write_text(json.dumps(state))
config = dict(workspace=str(WORK), private=str(PRIVATE), runtime=str(RUNTIME), origin=origin, socket=str(socket), fixture_path=str(fixture), action_limit=10, script_call_limit=8, time_limit_seconds=300)
config_path = PRIVATE / 'broker-config.json'
config_path.write_text(json.dumps(config))
script = '''def run(h):
    h.expect({'disposition':'unknown'},'Generic fixture navigation')
    h.page.goto(h.origin)
    h.expect({'disposition':'accepted'},'Generic button should change text')
    h.page.get_by_role('button',name='Generic Canary').click()
    h.note('{0.context._impl_obj._options}'.format(h))
    return h.observe('generic-final')
'''
(WORK / 'generic_positive.py').write_text(script)
args_path = PRIVATE / 'execute-args.json'
args_path.write_text(json.dumps({'script_path': 'generic_positive.py'}))
args = ['/usr/bin/python3', str(RUNTIME / 'browser_broker.py'), '--config', str(config_path), '--execute-file', str(args_path)]
try:
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    evidence = dict(command=args, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr, runtime_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RUNTIME.glob('*.py')})
    (ROOT / 'deterministic-result.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))
finally:
    gateway.shutdown(); gateway.server_close(); socket.unlink(missing_ok=True)
    http.shutdown(); http.server_close()
