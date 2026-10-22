"""Fast privileged CLI. Never expose this module or its snapshots to learner."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import time
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[4]
bootstrap=argparse.ArgumentParser(add_help=False);bootstrap.add_argument('--runtime')
requested_runtime=bootstrap.parse_known_args()[0].runtime
RUNTIME=Path(requested_runtime or os.environ.get('BM_DISCOGS_PHASE2_RUNTIME',str(ROOT/'.runtime/phase2-routing-v002'))).resolve()
ALLOWED_RUNTIMES={(ROOT/'.runtime/phase2-routing-v002').resolve(),*((ROOT/('.runtime/phase2-eval-worker-'+key)).resolve() for key in 'abc')}
if RUNTIME not in ALLOWED_RUNTIMES:raise RuntimeError('Unregistered driver runtime')
os.environ['BM_DISCOGS_PHASE2_RUNTIME']=str(RUNTIME)
spec=importlib.util.spec_from_file_location('discogs_private_evaluator',Path(__file__).with_name('evaluator.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def output_path(value,kind):
    path=Path(value).resolve() if value else RUNTIME/'private/driver'/f'{kind}-{uuid4().hex}.json'
    if not path.is_relative_to(RUNTIME):raise ValueError('All outputs must stay inside registered runtime')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError('Exclusive output already exists')
    return path
def write(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def before_record(case_id,prediction_file):
    prediction=None;metadata=None
    if prediction_file:
        source=Path(prediction_file).resolve();raw=source.read_bytes();prediction=json.loads(raw.decode('utf-8-sig'))
        if not isinstance(prediction,dict):raise ValueError('Frozen prediction must be a JSON object')
        metadata={'source_path':str(source),'source_sha256':sha(raw),'frozen_at':now()}
    snapshot=e.observe()
    return {'kind':'management_before','version':2,'captured_at_ns':time.time_ns(),'runtime':str(RUNTIME),'case_id':case_id,'inventory_sha256':e.digest(e.INVENTORY),'captured_at':now(),'snapshot':snapshot,'frozen_prediction':prediction,'prediction_provenance':metadata}
def is_business_write(event):
    return e.is_business_write(event)

def broker_prediction(path,before_path,before,case_id,events):
    provenance={'mode':'trusted_broker_record','status':'invalid','reason':None,'record_path':str(Path(path).resolve()),'record_sha256':None}
    def invalid(reason):
        provenance['reason']=reason
        return {},provenance
    record_path=Path(path).resolve()
    if not record_path.is_relative_to(RUNTIME):return invalid('record_outside_management_runtime')
    try:
        raw=record_path.read_bytes();provenance['record_sha256']=sha(raw);record=json.loads(raw.decode('utf-8-sig'))
    except (OSError,ValueError,UnicodeError):return invalid('record_missing_or_unreadable')
    if not isinstance(record,dict):return invalid('record_not_object')
    if record.get('source')!='trusted_browser_broker':return invalid('untrusted_source')
    if record.get('case_id')!=case_id or record.get('before_sha256')!=e.digest(before_path):return invalid('case_or_before_binding_mismatch')
    if record.get('declaration_count',1)!=1:return invalid('not_single_declaration')
    declared=record.get('declared_at_ns');started=before.get('captured_at_ns')
    if type(declared) is not int or type(started) is not int:return invalid('missing_trusted_declaration_or_begin_timestamp')
    provenance['declared_at_ns']=declared
    if declared<started:return invalid('declaration_precedes_begin')
    if declared>time.time_ns():return invalid('declaration_in_future')
    writes=[event for event in events if is_business_write(event)]
    if not writes:return invalid('no_business_write_observed')
    times=[event.get('management_request_started_ns') for event in writes]
    if any(type(value) is not int for value in times):return invalid('business_request_timestamp_missing')
    first=min(times);provenance['first_business_write_started_ns']=first
    if first<started:return invalid('business_write_precedes_begin')
    if first>time.time_ns():return invalid('business_write_timestamp_in_future')
    if declared>=first:return invalid('declaration_not_strictly_before_first_business_write')
    prediction=record.get('prediction')
    if not isinstance(prediction,dict):return invalid('prediction_not_object')
    provenance.update(status='valid',reason=None,source='trusted_browser_broker')
    return prediction,provenance

def novelty_audit(path):
    """Conservative exposure audit. A lexical absence never proves novelty."""
    source=Path(path).resolve()
    if source.is_dir():files=[p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in {'.json','.jsonl','.txt','.md','.html','.py'}]
    elif source.is_file():files=[source]
    else:raise FileNotFoundError(source)
    inventory=[];texts=[]
    for file in files:
        raw=file.read_bytes();inventory.append({'path':str(file),'sha256':sha(raw)})
        texts.append(raw.decode('utf8',errors='replace'))
    combined='\n'.join(texts)
    overlaps=[]
    for case in e.cases():
        candidates=[case.get('title','')]
        if 'release_id' in case:candidates.append('/release/'+str(case['release_id']))
        if 'listing_id' in case:candidates.append('/cart?add='+str(case['listing_id']))
        hit=any(token and token in combined for token in candidates)
        overlaps.append({'case_id':case['id'],'status':'possible_exposure_requires_review' if hit else 'not_established','novelty_claim_permitted':False})
    return {'kind':'conservative_novelty_audit','inventory_sha256':e.digest(e.INVENTORY),'learning_evidence_files':inventory,'cases':overlaps,'status':'manual_trace_review_required','limits':['Exact visible-object/title matches flag possible exposure, not a demonstrated workflow.','No lexical match does not establish unseen parameters, state, or composition.','Review action trace and frozen model before making novelty claims.'],'denominator':30}
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--runtime');sub=p.add_subparsers(dest='command',required=True)
    for name in ['reset-learning','inventory-public','reset-case','begin','finish','novelty-audit']:
        item=sub.add_parser(name);item.add_argument('--output')
        if name=='reset-learning':item.add_argument('--seed',type=int,required=True)
        if name in {'reset-case','finish'}:item.add_argument('--id',required=True)
        if name=='begin':item.add_argument('--id');item.add_argument('--prediction-file')
        if name=='finish':item.add_argument('--before',required=True);item.add_argument('--ui-evidence',required=True);item.add_argument('--prediction-record')
        if name=='novelty-audit':item.add_argument('--learning-evidence',required=True)
    args=p.parse_args(argv)
    if args.runtime and Path(args.runtime).resolve()!=RUNTIME:raise ValueError('Runtime selection must occur at process startup')
    path=output_path(args.output,args.command)
    if args.command=='reset-learning':result=e.reset_learning(args.seed)
    elif args.command=='inventory-public':result=[e.public_case(c) for c in e.cases()]
    elif args.command=='reset-case':result=e.reset(args.id)
    elif args.command=='begin':
        if args.id:e.fixed(args.id)
        result=before_record(args.id,args.prediction_file)
    elif args.command=='novelty-audit':result=novelty_audit(args.learning_evidence)
    else:
        before_path=Path(args.before).resolve();record=read(before_path)
        if not before_path.is_relative_to(RUNTIME) or record.get('runtime')!=str(RUNTIME) or record.get('kind')!='management_before':raise ValueError('Untrusted before record location or runtime')
        if record.get('case_id') not in {None,args.id} or record.get('inventory_sha256')!=e.digest(e.INVENTORY):raise ValueError('Before record binding mismatch')
        evidence_path=Path(args.ui_evidence).resolve();evidence=read(evidence_path)
        if 'prediction' in evidence:raise ValueError('Post-action inline prediction is forbidden; freeze at begin')
        events=evidence.get('events',[])
        if not isinstance(events,list) or any(event.get('source')!='trusted_browser_gateway' for event in events):raise ValueError('Only trusted gateway events are accepted')
        prediction_provenance=record.get('prediction_provenance')
        if args.prediction_record:
            evidence['prediction'],prediction_provenance=broker_prediction(args.prediction_record,before_path,record,args.id,events)
        else:evidence['prediction']=record.get('frozen_prediction') or {}
        evidence['before_captured_at_ns']=record.get('captured_at_ns')
        after=e.observe();evaluation=e.evaluate(args.id,record['snapshot'],after,evidence)
        safety=evaluation['management_safety']
        result={'kind':'independent_case_evaluation','case_id':args.id,'evaluated_at':now(),'runtime':str(RUNTIME),'before_file_sha256':e.digest(before_path),'ui_evidence_sha256':e.digest(evidence_path),'prediction_provenance':prediction_provenance,'safe_to_reset':safety['safe_to_reset'],'reset_safety':safety,'evaluation':evaluation,'after_snapshot':after,'denominator_retained':True}
    write(path,result)
    print(json.dumps({'command':args.command,'output':str(path),'sha256':e.digest(path),'status':'written'}))
if __name__=='__main__':main()
