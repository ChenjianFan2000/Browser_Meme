"""Windows generic relay callback and strict reset admission regression."""
import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from harness.phase2.relay import FixedOriginRelay
from harness.phase2.run_learning import management_barrier, management_barrier_passed

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'generic')
    def log_message(self, *args): pass

checks = {}
fixture = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=fixture.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for failure in (False, True):
            private = root / str(failure); solar = private / 'solar'; solar.mkdir(parents=True)
            (solar/'cleanup.json').write_text(json.dumps(dict(status='cleaned',owned_processes_remaining=0,nonce='canary',supervisor_pid=1)),encoding='utf-8')
            (solar/'launch-result.json').write_text(json.dumps(dict(cleanup_receipt='cleanup.json',cleanup_nonce='canary',supervisor_pid=1)),encoding='utf-8')
            events=SimpleNamespace(file=(private/'gateway.jsonl').open('x',encoding='utf-8'))
            def callback(request):
                if failure and request['event_phase']=='response':
                    raise RuntimeError('generic_callback_failure')
                events.file.write(json.dumps({'event_phase':request['event_phase']})+'\n');events.file.flush()
            child = "import sys,json;print(json.dumps({'event':'ready'}),flush=True);sys.stdin.read();print(json.dumps({'id':1,'method':'GET','path':'/','headers':[],'body':''}),flush=True)"
            relay=FixedOriginRelay([sys.executable,'-u','-c',child],'http://generic.invalid','127.0.0.1',fixture.server_port,private/'stderr.txt',callback=callback)
            assert relay.ready.wait(5)
            relay.close();events.file.close()
            barrier=management_barrier(private,relay,events)
            assert barrier['relay_drained'] and barrier['browser_tree_clean']
            assert barrier['gateway_log_complete'] is (not failure)
            checks['real_callback_error_blocks_gateway_barrier' if failure else 'real_reader_and_active_request_drained']=True
        good=dict(relay_drained=True,browser_tree_clean=True,gateway_log_complete=True)
        assert management_barrier_passed(good)
        assert not management_barrier_passed({})
        assert not management_barrier_passed({**good,'browser_tree_clean':1})
        tree=ast.parse(Path('harness/phase2/run_evaluation.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case')
        assignment=next(n for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='summary' for t in n.targets))
        expr=next(v for k,v in zip(assignment.value.keys,assignment.value.values) if isinstance(k,ast.Constant) and k.value=='safe_to_reset')
        code=compile(ast.Expression(expr),'reset-expression','eval')
        for value,want in [(True,True),(False,False),(1,False),('true',False),(None,False)]:
            assert eval(code,{'value':{'safe_to_reset':value},'barrier':good,'management_barrier_passed':management_barrier_passed}) is want
        assert eval(code,{'value':{'safe_to_reset':True},'barrier':{**good,'relay_drained':False},'management_barrier_passed':management_barrier_passed}) is False
        checks['driver_boolean_must_be_exact_true_and_local_barrier_passed']=True
        freeze_index=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='freeze_manifest')
        safety_index=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.If) and 'safe_to_reset' in ast.unparse(n.test))
        assert freeze_index<safety_index
        checks['unsafe_case_frozen_before_stop']=True
finally:
    fixture.shutdown();fixture.server_close()
result={'status':'passed','checks':checks}
Path('harness/experiments/phase2-discogs-20261021-01/isolation/management-barrier-034.result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
