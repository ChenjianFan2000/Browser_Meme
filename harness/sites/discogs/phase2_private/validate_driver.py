"""CLI component tests on a disposable DB, never touch active business state."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
spec=importlib.util.spec_from_file_location('driver',Path(__file__).with_name('driver.py'));d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
def main():
    folder=d.RUNTIME/'private/driver-components';folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        tmp=Path(tmp);d.e.DB=tmp/'isolated.db';checks=[]
        def run(argv):
            with contextlib.redirect_stdout(io.StringIO()):d.main(argv)
        reset=tmp/'reset.json';run(['reset-learning','--seed','7','--output',str(reset)])
        assert d.read(reset)['snapshot']==d.e.snapshot(d.RUNTIME/'data/baseline.db')
        checks.append('reset-learning original baseline on disposable DB')
        original=d.e.digest(d.e.DB)
        try:run(['reset-learning','--seed','8','--output',str(reset)])
        except FileExistsError:pass
        else:raise AssertionError('Existing output overwritten')
        assert original==d.e.digest(d.e.DB)
        checks.append('exclusive existing output rejected before management mutation')
        inventory=tmp/'inventory.json';run(['inventory-public','--output',str(inventory)])
        assert len(d.read(inventory))==30 and all(set(c)=={'id','goal','parameters'} for c in d.read(inventory))
        checks.append('public inventory exact three-field projection retains 30')
        case=tmp/'resetcase.json';run(['reset-case','--id','P01','--output',str(case)])
        prediction=tmp/'prediction.json';prediction.write_text(json.dumps({'disposition':'unknown','effects':{'persistent_state_changed':False,'affected_record_count':0}}))
        before=tmp/'before.json';run(['begin','--id','P01','--prediction-file',str(prediction),'--output',str(before)])
        prediction.write_text(json.dumps({'disposition':'accepted','effects':{'persistent_state_changed':True}}))
        evidence=tmp/'ui.json';evidence.write_text(json.dumps({'events':[]}));result=tmp/'result.json'
        run(['finish','--id','P01','--before',str(before),'--ui-evidence',str(evidence),'--output',str(result)])
        r=d.read(result)['evaluation'];assert r['outcome']=='failed' and r['prediction_grading']['persistent_state_changed']=='correct'
        checks.append('finish evaluates real disposable state and begin-frozen prediction, never later source change')
        evidence.write_text(json.dumps({'events':[{'method':'POST','path':'/api/me/collection/1','status':200}]}))
        try:run(['finish','--id','P01','--before',str(before),'--ui-evidence',str(evidence),'--output',str(tmp/'untrusted.json')])
        except ValueError:pass
        else:raise AssertionError('Untrusted event accepted')
        checks.append('missing trusted gateway event provenance rejected')
        text=tmp/'learning.txt';text.write_text('No confirmed website references in this component fixture.')
        audit=tmp/'audit.json';run(['novelty-audit','--learning-evidence',str(text),'--output',str(audit)])
        assert all(not c['novelty_claim_permitted'] for c in d.read(audit)['cases'])
        checks.append('absence of lexical exposure does not establish novelty')
        stamp=d.read(before)['captured_at_ns'];before_hash=d.e.digest(before)
        broker=tmp/'broker.json'
        declaration={'source':'trusted_browser_broker','case_id':'P01','before_sha256':before_hash,'declared_at_ns':stamp+100,'prediction':{'disposition':'accepted','effects':{'persistent_state_changed':False,'affected_record_count':0}},'declaration_count':1}
        gateway=[{'source':'trusted_browser_gateway','method':'POST','path':'/api/auth/login','status':200,'management_request_started_ns':stamp+50},{'source':'trusted_browser_gateway','method':'GET','path':'/api/me/collection','status':200},{'source':'trusted_browser_gateway','method':'POST','path':'/api/me/collection/1','status':200,'management_request_started_ns':stamp+200}]
        broker.write_text(json.dumps(declaration));evidence.write_text(json.dumps({'events':gateway}))
        fresh=tmp/'broker-result.json';run(['finish','--id','P01','--before',str(before),'--ui-evidence',str(evidence),'--prediction-record',str(broker),'--output',str(fresh)])
        result=d.read(fresh);assert result['prediction_provenance']['status']=='valid' and result['evaluation']['prediction_grading']['disposition']=='correct'
        assert d.e.digest(before)==before_hash
        checks.append('broker prediction bound to unchanged before is accepted before business write; earlier auth/query excluded')
        declaration['declared_at_ns']=stamp+200;broker.write_text(json.dumps(declaration))
        late=tmp/'late.json';run(['finish','--id','P01','--before',str(before),'--ui-evidence',str(evidence),'--prediction-record',str(broker),'--output',str(late)])
        late_result=d.read(late);assert late_result['prediction_provenance']['status']=='invalid' and set(late_result['evaluation']['prediction_grading'].values())=={'unknown'}
        assert late_result['evaluation']['task_outcome']==result['evaluation']['task_outcome']
        checks.append('equal/late declaration cannot score predictions or rewrite task outcome')
        declaration['declared_at_ns']=stamp+100;broker.write_text(json.dumps(declaration))
        prior_wrong=gateway+[{'source':'trusted_browser_gateway','method':'POST','path':'/api/cart/items','status':201,'management_request_started_ns':stamp+90}]
        assert d.broker_prediction(broker,before,d.read(before),'P01',prior_wrong)[1]['status']=='invalid'
        checks.append('earlier wrong-action business write also prevents retroactive prediction')
        missing=[dict(gateway[-1])];missing[0].pop('management_request_started_ns')
        assert d.broker_prediction(broker,before,d.read(before),'P01',missing)[1]['reason']=='business_request_timestamp_missing'
        assert d.broker_prediction(broker,before,d.read(before),'P01',[])[1]['reason']=='no_business_write_observed'
        assert d.broker_prediction(tmp/'missing.json',before,d.read(before),'P01',gateway)[1]['reason']=='record_missing_or_unreadable'
        checks.append('missing declaration/request timing or write observation remains invalid/unknown')
        declaration['before_sha256']='wrong';broker.write_text(json.dumps(declaration))
        assert d.broker_prediction(broker,before,d.read(before),'P01',gateway)[1]['reason']=='case_or_before_binding_mismatch'
        declaration['before_sha256']=before_hash;declaration['source']='learner';broker.write_text(json.dumps(declaration))
        assert d.broker_prediction(broker,before,d.read(before),'P01',gateway)[1]['reason']=='untrusted_source'
        checks.append('replayed before binding and learner-declared source rejected')
        declaration['source']='trusted_browser_broker';broker.write_text(json.dumps(declaration))
        business=dict(gateway[-1]);business['event_phase']='response'
        dispatch=dict(business);dispatch.update(status=0,event_phase='dispatch')
        complete={'events':[dispatch,business],'management_barrier':{'relay_drained':True,'browser_tree_clean':True,'gateway_log_complete':True}}
        evidence.write_text(json.dumps(complete));safe_result=tmp/'safe-result.json'
        run(['finish','--id','P01','--before',str(before),'--ui-evidence',str(evidence),'--prediction-record',str(broker),'--output',str(safe_result)])
        verified=d.read(safe_result)
        assert verified['safe_to_reset'] is True and verified['reset_safety']==verified['evaluation']['management_safety']
        assert verified['evaluation']['task_outcome']=='failed'
        incomplete={'events':[dispatch],'management_barrier':complete['management_barrier']}
        evidence.write_text(json.dumps(incomplete));unsafe_result=tmp/'unsafe-result.json'
        run(['finish','--id','P01','--before',str(before),'--ui-evidence',str(evidence),'--prediction-record',str(broker),'--output',str(unsafe_result)])
        unconfirmed=d.read(unsafe_result)
        assert unconfirmed['safe_to_reset'] is False and unconfirmed['reset_safety']['status']=='unknown'
        assert d.e.digest(before)==before_hash
        checks.append('private CLI/evaluator wire identical top/nested safety flags; failed task can safely reset, incomplete write cannot')


    report={'kind':'isolated_cli_component_checks','passed':len(checks),'checks':checks,'active_runtime_db_touched':False,'ui_runs':0}
    target=folder/('result-'+d.uuid4().hex+'.json');d.write(target,report);print(json.dumps(report))
if __name__=='__main__':main()
