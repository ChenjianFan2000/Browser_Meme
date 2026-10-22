"""Fail-closed reset-safety components plus real delayed-write timeout proof."""
import contextlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from uuid import uuid4
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('safety_evaluator',HERE/'evaluator.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
def main():
    checks=[];start=time.time_ns();barrier={'relay_drained':True,'browser_tree_clean':True,'gateway_log_complete':True}
    def event(phase,status,stamp=start+1):return {'source':'trusted_browser_gateway','method':'POST','path':'/api/me/collection/1','management_request_started_ns':stamp,'event_phase':phase,'status':status}
    pair=[event('dispatch',0),event('response',200)]
    assert e.assess_reset_safety(pair,barrier,start)['safe_to_reset']
    checks.append('unique normal terminal response with all trusted barriers permits next reset')
    for field in barrier:
        bad=dict(barrier);bad[field]=False
        assert not e.assess_reset_safety(pair,bad,start)['safe_to_reset']
    assert not e.assess_reset_safety(pair,barrier,None)['safe_to_reset']
    checks.append('every cleanup/log/time attestation is mandatory, never inferred from wrapper success')
    variants=[[event('dispatch',0)],[event('response',200)],[event('dispatch',0),event('dispatch',0),event('response',200)],[event('dispatch',0),event('response',200),event('response',200)],list(reversed(pair))]
    for rows in variants:assert not e.assess_reset_safety(rows,barrier,start)['safe_to_reset']
    checks.append('missing, duplicate, orphan or reordered events remain unknown')
    for status in [0,100,302,408,429,500,502,503,504]:assert not e.assess_reset_safety([event('dispatch',0),event('response',status)],barrier,start)['safe_to_reset']
    for status in [200,201,204,400,401,403,404,405,422]:assert e.assess_reset_safety([event('dispatch',0),event('response',status)],barrier,start)['safe_to_reset']
    checks.append('registered completed branches are accepted, timeout/proxy/unexpected statuses cannot prove handler completion')
    assert e.assess_reset_safety([],barrier,start)['safe_to_reset']
    assert not e.assess_reset_safety([],{},start)['safe_to_reset']
    assert not e.assess_reset_safety([event('dispatch',0,start-1),event('response',200,start-1)],barrier,start)['safe_to_reset']
    unknown_write={'source':'trusted_browser_gateway','method':'POST','path':'/api/unlisted-mutating-route','management_request_started_ns':start+2,'event_phase':'dispatch','status':0}
    assert not e.assess_reset_safety([*pair,unknown_write],barrier,start)['safe_to_reset']
    assert not e.is_business_write({'method':'POST','path':'/api/auth/login'}) and e.is_business_write({'method':'POST','path':'/api/auth/register'})
    checks.append('unknown API mutations are conservative; old-case times and incomplete logs cannot pass')
    out=ROOT/'.runtime/phase2-eval-worker-a/private/reset-safety-components';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        db=Path(tmp)/'generic-only.db'
        with contextlib.closing(sqlite3.connect(db)) as connection:connection.execute('create table writes(value integer)');connection.commit()
        began=threading.Event();committed=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                began.set();time.sleep(.35)
                with contextlib.closing(sqlite3.connect(db)) as connection:connection.execute('insert into writes values (1)');connection.commit()
                committed.set()
                try:self.send_response(200);self.end_headers();self.wfile.write(b'ok')
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        request_started=time.time_ns();events=[event('dispatch',0,request_started)]
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=.05)
        timed_out=False
        try:client.request('POST','/generic-managed-write');client.getresponse()
        except TimeoutError:timed_out=True
        finally:client.close()
        assert timed_out and began.is_set()
        assert not e.assess_reset_safety(events,barrier,request_started-1)['safe_to_reset']
        assert committed.wait(2)
        with contextlib.closing(sqlite3.connect(db)) as connection:assert connection.execute('select count(*) from writes').fetchone()[0]==1
        assert not e.assess_reset_safety(events,barrier,request_started-1)['safe_to_reset']
        server.shutdown();server.server_close();thread.join(2)
        # Even after the generic server is stopped, an immutable earlier record
        # is not silently promoted. Recovery must be a separate management run.
        assert not e.assess_reset_safety(events,barrier,request_started-1)['safe_to_reset']
        checks.append('real client timeout followed by late backend DB commit stays unsafe before/after commit and server shutdown')
    report={'kind':'independent_reset_safety_components','passed':len(checks),'checks':checks,'real_generic_http_timeout':True,'active_worker_or_pilot_db_touched':False,'site_services_started_or_stopped':False,'benchmark_cases_executed':0}
    epath=out/('result-'+uuid4().hex+'.json')
    with epath.open('x',encoding='utf8') as output:json.dump(report,output,indent=2)
    print(json.dumps(report))
if __name__=='__main__':main()
