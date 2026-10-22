"""WSL-side frozen-evaluation protocol probe using only generic canaries."""
import hashlib
import json
import os
import pathlib
import select
import socket
import socketserver
import subprocess
import sys
import threading
import time

BASE = pathlib.Path('/opt/browser-meme/tmp/phase2-isolation-audit')
ROOT = BASE / 'evaluation-generic-012'
RUNTIME = ROOT / 'runtime'
WORK = ROOT / 'workspace'
FROZEN = ROOT / 'frozen'
for folder in [WORK, FROZEN]:
    folder.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(RUNTIME))
from permissions import CODEX, overrides

control_path = ROOT / 'control.sock'
site_path = ROOT / 'site.sock'
records = []
expected_case, expected_before = 'GENERIC-CASE-012', 'a' * 64
accepted = False


class Control(socketserver.StreamRequestHandler):
    def handle(self):
        global accepted
        value = json.loads(self.rfile.readline(65537))
        if value.get('case_id') != expected_case or value.get('before_sha256') != expected_before:
            response = {'status': 'rejected', 'reason': 'case_or_before_mismatch'}
        elif accepted:
            response = {'status': 'rejected', 'reason': 'already_declared'}
        else:
            accepted = True
            response = {'status': 'frozen', 'case_id': expected_case, 'before_sha256': expected_before, 'declared_at_ns': time.time_ns()}
        records.append({'request': value, 'response': response})
        self.wfile.write(json.dumps(response).encode() + b'\n')


control = socketserver.ThreadingUnixStreamServer(str(control_path), Control)
threading.Thread(target=control.serve_forever, daemon=True).start()
site = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
site.bind(str(site_path)); site.listen(10)
model = FROZEN / 'behavior_model.py'
source = '''import socket
def predict(observation,intent):
    try:
        with open(__file__,'a') as output: output.write('UNEXPECTED_WRITE')
        frozen_write='ALLOWED'
    except OSError as error: frozen_write=type(error).__name__; frozen_errno=error.errno
    try:
        client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); client.connect(CONTROL)
        control_access='CONNECTED'; client.close()
    except OSError as error: control_access=type(error).__name__
    return {'disposition':'accepted','effects':{'persistent_state_changed':None,'affected_record_count':None,'generic':True},'ui_claims':[],'unknowns':[],'audit':{'frozen_write':frozen_write,'frozen_errno':frozen_errno,'control_access':control_access,'observation':observation,'intent':intent}}
'''.replace('CONTROL', repr(str(control_path)))
model.write_text(source)
digest = hashlib.sha256(model.read_bytes()).hexdigest()
fixture = ROOT / 'fixture.json'; fixture.write_text('{}')
base_config = dict(workspace=str(WORK), runtime=str(RUNTIME), origin='http://generic.invalid', socket=str(site_path),
                   fixture_path=str(fixture), action_limit=10, script_call_limit=8, time_limit_seconds=300,
                   frozen_root=str(FROZEN), frozen_model=str(model), frozen_files={'behavior_model.py': digest},
                   control_socket=str(control_path), case_id=expected_case, before_sha256=expected_before)
transcript = []


def start(condition):
    private = ROOT / ('private-' + condition); private.mkdir()
    config = {**base_config, 'condition': condition, 'private': str(private)}
    path = private / 'config.json'; path.write_text(json.dumps(config))
    error = (private / 'broker.stderr.txt').open('x')
    child = subprocess.Popen(['/usr/bin/python3', str(RUNTIME / 'evaluation_broker.py'), '--config', str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error)
    return child, error


def call(child, method, parameters):
    request = {'jsonrpc': '2.0', 'id': len(transcript) + 1, 'method': method, 'params': parameters}
    child.stdin.write(json.dumps(request).encode() + b'\n'); child.stdin.flush()
    if not select.select([child.stdout], [], [], 40)[0]:
        raise TimeoutError('generic broker response timeout')
    result = json.loads(child.stdout.readline())
    transcript.append({'request': request, 'response': result})
    return result['result']


def value(response):
    return json.loads(response['content'][0]['text'])


def invoke(child, name, arguments):
    return call(child, 'tools/call', {'name': name, 'arguments': arguments})


children = []
try:
    a, err_a = start('A'); children.append((a, err_a))
    tools_a = call(a, 'tools/list', {})['tools']
    premature = invoke(a, 'declare_task_prediction', {'prediction': {'disposition': 'accepted'}, 'basis': 'generic-before-model'})
    assert premature.get('isError')
    prediction_record = value(invoke(a, 'model_predict', {'observation': {'generic': 'visible'}, 'intent': {'generic': 'intent'}}))
    prediction = prediction_record['prediction']
    assert prediction['audit']['frozen_write'] in ['PermissionError', 'OSError']
    assert prediction['audit']['frozen_errno'] in [1, 13, 30]
    assert prediction['audit']['control_access'] in ['PermissionError', 'FileNotFoundError']
    mismatch = invoke(a, 'declare_task_prediction', {'prediction': {'disposition': 'rejected'}, 'basis': 'generic-mismatch'})
    assert mismatch.get('isError')
    assert records == []
    declaration = value(invoke(a, 'declare_task_prediction', {'prediction': prediction, 'basis': 'exact generic frozen output'}))
    assert declaration['status'] == 'frozen'
    duplicate = invoke(a, 'declare_task_prediction', {'prediction': prediction, 'basis': 'generic-duplicate'})
    assert duplicate.get('isError') and len(records) == 1
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(control_path)); client.sendall(json.dumps({'command': 'declare_prediction', 'case_id': 'WRONG-GENERIC-CASE', 'before_sha256': expected_before, 'prediction': prediction}).encode() + b'\n')
        cross_case = json.loads(client.makefile('rb').readline())
    assert cross_case['status'] == 'rejected'
    b, err_b = start('B'); children.append((b, err_b))
    tools_b = call(b, 'tools/list', {})['tools']
    assert 'model_predict' in {row['name'] for row in tools_a}
    assert 'model_predict' not in {row['name'] for row in tools_b}
    forced_b = invoke(b, 'model_predict', {'observation': {}, 'intent': {}})
    assert forced_b.get('isError')
    probe = WORK / 'namespace_probe.py'
    probe.write_text('''import pathlib,socket,json
out={}
try:
 pathlib.Path(MODEL).write_text('UNEXPECTED_WRITE');out['frozen_write']='ALLOWED'
except OSError as e:out['frozen_write']=type(e).__name__;out['frozen_errno']=e.errno
for label,path in [('control',CONTROL),('site',SITE)]:
 try:
  client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);client.connect(path);client.close();out[label]='CONNECTED'
 except OSError as e:out[label]=type(e).__name__
print(json.dumps(out))
'''.replace('MODEL', repr(str(model))).replace('CONTROL', repr(str(control_path))).replace('SITE', repr(str(site_path))))
    boundaries = []
    for name, options in [('learner', overrides(extra_paths={str(FROZEN): 'read'})), ('browser-worker', overrides(runtime=RUNTIME, socket=site_path, extra_paths={str(FROZEN): 'read'}))]:
        args = [CODEX, 'sandbox', '-P', 'p2', '-C', str(WORK)] + options + ['/usr/bin/python3', str(probe)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        actual = json.loads(result.stdout)
        assert actual['frozen_write'] in ['PermissionError', 'OSError'] and actual['frozen_errno'] in [1, 13, 30]
        assert actual['control'] in ['PermissionError', 'FileNotFoundError']
        assert actual['site'] == ('CONNECTED' if name == 'browser-worker' else 'PermissionError')
        boundaries.append({'namespace': name, 'command': args, 'result': actual})
    assert hashlib.sha256(model.read_bytes()).hexdigest() == digest
    result = dict(status='passed', scope='Linux generic evaluation extension with stub control-clock, not Windows time ordering',
                  declaration=declaration, cross_case_stub_result=cross_case, prediction=prediction_record,
                  tools_a=[row['name'] for row in tools_a], tools_b=[row['name'] for row in tools_b],
                  transcript=transcript, control_stub_records=records, namespace_boundaries=boundaries,
                  runtime_files_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in RUNTIME.glob('*.py')})
    (ROOT / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
finally:
    (ROOT / 'transcript.json').write_text(json.dumps({'transcript': transcript, 'control_stub_records': records}, indent=2))
    for child, error in children:
        child.stdin.close(); child.wait(timeout=10); error.close()
    site.close(); site_path.unlink(missing_ok=True)
    control.shutdown(); control.server_close(); control_path.unlink(missing_ok=True)
