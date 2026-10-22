"""One real frozen Unix/stdio relay+namespace native UI path, no model call."""
import argparse
import json
import subprocess
import sys
import threading
import time
from management import HERE, ROOT, EXTRA, evaluator, sha
sys.path.insert(0,str(ROOT))
from harness.phase2.management import DISTRO, LINUX_ROOT, put_files, export_tree, wsl_python
from harness.phase2.relay import FixedOriginRelay
from harness.phase2.run_learning import TrustedEvents
from harness.phase2.process_guard import receipt_valid

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=EXTRA,required=True);p.add_argument('--attempt',default='002');args=p.parse_args()
    worker=EXTRA[args.worker];e=evaluator(worker['runtime']);case=e.fixed('P01')
    out=worker['runtime']/('private/scale-relay-ui-'+args.attempt);out.mkdir(exist_ok=False)
    def cli(arguments):
        result=subprocess.run([sys.executable,str(HERE/'management.py'),'--runtime',str(worker['runtime']),*arguments],capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(result.stdout)
    cli(['reset-case','--id',case['id']]);before=cli(['begin','--id',case['id'],'--output',str(out/'before.json')])
    runtime=LINUX_ROOT+'/runtime-05ef37ca7f58';identifier='scale-relay-ui-'+args.worker+'-'+args.attempt;base=LINUX_ROOT+'/'+identifier;socket=base+'.sock'
    button='Add to Collection' if case['table']=='collection_items' else 'Add to Wantlist'
    script='''def run(h):
 p=h.page
 forecast={'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['Independent environment readiness only']}
 h.expect(forecast,'Open login through UI')
 p.goto(h.origin+'/login')
 h.observe('login')
 h.expect(forecast,'Submit ordinary public fixture login')
 p.get_by_role('button',name='Sign in',exact=True).click()
 p.wait_for_timeout(700)
 h.observe('login submission readback')
 h.expect(forecast,'Open private readiness target UI')
 p.goto(h.origin+ENTRY)
 h.observe('before membership')
 h.expect(forecast,'Execute one real visible readiness interaction')
 p.get_by_role('button',name=BUTTON,exact=True).click()
 p.wait_for_timeout(700)
 h.observe('after membership')
'''.replace('ENTRY',repr(case['entry'])).replace('BUTTON',repr(button))
    config={'workspace':base+'/workspace','private':base+'/private/browser','runtime':runtime,
        'origin':'http://127.0.0.1:12042','socket':socket,'fixture_path':base+'/public-fixture.json',
        'action_limit':20,'script_call_limit':1,'time_limit_seconds':180}
    put_files({base+'/broker-config.json':json.dumps(config).encode(),base+'/public-fixture.json':(worker['runtime']/'public-fixture.json').read_bytes(),base+'/workspace/readiness.py':script.encode()})
    class Events(TrustedEvents):
        def __init__(self):
            self.ingest=e.ingest_http;self.destination=out/'trusted-gateway.jsonl';self.file=self.destination.open('x',encoding='utf-8');self.lock=threading.Lock();self.count=0
    events=Events()
    relay=FixedOriginRelay(['wsl','-d',DISTRO,'--','python3',runtime+'/relay.py','linux','--socket',socket,'--origin','http://127.0.0.1:12042'],
        'http://127.0.0.1:12042','127.0.0.1',worker['frontend_port'],out/'relay.stderr.txt',callback=events)
    try:
        if not relay.ready.wait(20):raise RuntimeError('Readiness relay not ready')
        code='import sys,json\nsys.path.insert(0,'+repr(runtime)+')\nfrom browser_broker import Broker\nb=Broker(json.load(open('+repr(base+'/broker-config.json')+')))\nprint(json.dumps(b.execute({"script_path":"readiness.py"})))\n'
        response=wsl_python(code,timeout=240)
        (out/'broker.stdout.json').write_bytes(response.stdout);(out/'broker.stderr.txt').write_bytes(response.stderr)
        if response.returncode:raise RuntimeError('Namespace native UI probe failed; private stderr preserved')
        broker=json.loads(response.stdout)
    finally:
        relay.close();events.close();export_tree(base+'/private',out/'private')
    clean=receipt_valid(out/'private/browser'/broker['cleanup_receipt'],nonce=broker['cleanup_nonce'],supervisor_pid=broker['supervisor_pid'])
    with relay.active_condition:drained=not relay.active and not relay.thread.is_alive() and relay.child.poll() is not None
    barrier={'browser_tree_clean':clean,'relay_drained':drained and not relay.errors,'gateway_log_complete':drained and not relay.errors and events.file.closed}
    shots=sorted((out/'private/browser').glob('call-*/evidence/obs-*.png'))
    ui={'events':[json.loads(line) for line in events.destination.read_text(encoding='utf-8').splitlines()],
        'screenshot_path':str(shots[-1]) if shots else None,'ui_error':broker['result'].get('error'),'management_barrier':barrier}
    with (out/'ui.json').open('x',encoding='utf-8') as f:json.dump(ui,f,indent=2)
    finish=cli(['finish','--id',case['id'],'--before',str(out/'before.json'),'--ui-evidence',str(out/'ui.json'),'--output',str(out/'evaluation.json')])
    value=json.loads((out/'evaluation.json').read_text(encoding='utf-8'));passed=value['safe_to_reset'] is True and value['evaluation']['task_outcome']=='passed'
    result={'worker_id':args.worker,'passed':passed,'physical_formal_relay_exercised':True,'native_browser_in_frozen_namespace':True,
        'browser_cleanup_receipt_valid':clean,'barrier':barrier,'safe_to_reset':value['safe_to_reset'],'before':before,'finish':finish,
        'runtime':runtime,'frontend_port':worker['frontend_port'],'events':events.count,'relay_errors':relay.errors,'model_requests':0,
        'kind':'independent_environment_relay_readiness_not_learner_score'}
    with (out/'result.management.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'passed':passed,'path':str(out/'result.management.json'),'sha256':sha(out/'result.management.json')}))
    if not passed:raise RuntimeError('Full frozen relay integration not ready')
    cli(['reset-learning','--seed','0'])

if __name__=='__main__':main()
