"""Component checks only: no browser/site run and no benchmark scores."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('private_eval',Path(__file__).with_name('evaluator.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
def main():
    checks=[]
    event=e.ingest_http('POST','http://127.0.0.1:12042/api/me/listings',422,{'release_id':7,'quantity':0,'password':'excluded','token':'excluded'},{'sensitive':'excluded'},'application/json')
    assert event=={'method':'POST','path':'/api/me/listings','status':422,'source':'trusted_browser_gateway','safe_request':{'release_id':7,'quantity':0}}
    assert e.ingest_http('POST','http://127.0.0.1:12042/api/auth/login',200,{'password':'excluded'}) is None
    assert e.ingest_http('GET','http://127.0.0.1:12138/api/me/listings',200) is None
    assert e.ingest_http('POST','http://untrusted.example/api/me/listings',422) is None
    checks.append('gateway hook matches safe event shape and drops credentials, response bodies, auth and non-frontend origins')
    folder=e.RUNTIME/'private/component_checks';folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as temp:
        e.DB=Path(temp)/'test.db'
        first=e.reset_learning(1);second=e.reset_learning(2)
        assert first['snapshot']==second['snapshot']==e.snapshot(e.RUNTIME/'data/baseline.db')
        checks.append('learning reset uses identical original baseline for distinct scheduling seeds, not case initial states')
        for case in e.cases():
            e.reset(case)
            assert e.snapshot()['table_hashes']==e.snapshot(ROOT/case['initial_db'])['table_hashes']
        checks.append('30 management resets reproduce each locked initial state')
        case=e.fixed('P01');e.reset(case);before=e.snapshot();digest=e.digest(e.DB);after=e.observe()
        assert before==after and e.digest(e.DB)==digest
        checks.append('read-only snapshots preserve database bytes')
        with e.connect(e.DB) as db:
            try: db.execute('delete from cart_items')
            except sqlite3.OperationalError: pass
            else: raise AssertionError('readonly write succeeded')
        checks.append('readonly connection rejects write')
        result=e.evaluate(case,before,after,{'events':[]})
        assert result['outcome']=='failed'
        checks.append('untouched positive case fails independently of prediction')
        initial_get=e.evaluate(case,before,after,{'events':[{'method':'GET','path':'/api/me/collection/1','status':200}]})
        assert initial_get['business_disposition']=='unknown'
        blocked=e.evaluate(case,before,after,{'events':[{'method':'POST','path':'/api/me/collection/1','status':404}]})
        assert blocked['business_disposition']=='unknown' and blocked['transport_disposition']=='rejected' and blocked['environment_limited']
        checks.append('initial GET cannot imply business acceptance; evidenced routing 404 remains domain unknown')
        case=e.fixed('B01');e.reset(case);before=e.snapshot()
        result=e.evaluate(case,before,e.snapshot(),{'events':[]})
        assert result['outcome']=='unable_to_confirm'
        assert set(result['prediction_grading'].values())=={'unknown'}
        checks.append('unchanged idempotent state without UI proof is unable_to_confirm; absent predictions unknown')
        shot=Path(temp)/'component-only.txt';shot.write_text('synthetic component evidence, not screenshot')
        case=e.fixed('B06');e.reset(case);before=e.snapshot()
        events=[{'path':'/api/me/listings','method':'POST','status':422,'safe_request':{'release_id':case['release_id'],'quantity':case['quantity']}}]
        result=e.evaluate(case,before,e.snapshot(),{'events':events,'screenshot_path':str(shot),'prediction':{'disposition':'rejected','effects':{'persistent_state_changed':False,'affected_record_count':0}}})
        assert result['outcome']=='passed' and set(result['prediction_grading'].values())=={'correct'}
        events[0]['safe_request']['quantity']=999999
        assert e.evaluate(case,before,e.snapshot(),{'events':events,'screenshot_path':str(shot)})['outcome']!='passed'
        checks.append('synthetic rejection proves strict target parameter checks and independent prediction grading; not UI validation')
    report={'kind':'component_only','checks':checks,'passed':len(checks),'ui_cases_executed':0,'services_started':False,'inventory_sha256':e.digest(e.INVENTORY)}
    path=folder/'result.json'
    if path.exists():
        from uuid import uuid4
        path=folder/('result-'+uuid4().hex[:8]+'.json')
    with path.open('x',encoding='utf8') as out:json.dump(report,out,indent=2)
    print(json.dumps(report))
if __name__=='__main__':main()
