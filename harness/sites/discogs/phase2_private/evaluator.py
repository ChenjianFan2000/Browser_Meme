"""Privileged independent evaluator. No learner/model input supplies truth.

Reset is management-only. Observe/score open SQLite mode=ro and query_only.
UI evidence must be collected by the trusted browser host using attach_ui().
"""
from __future__ import annotations
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[4]
RUNTIME=Path(os.environ.get('BM_DISCOGS_PHASE2_RUNTIME',str(ROOT/'.runtime/phase2-discogs-20261021-01'))).resolve()
if RUNTIME not in {(ROOT/'.runtime/phase2-discogs-20261021-01').resolve(),(ROOT/'.runtime/phase2-routing-v001').resolve(),(ROOT/'.runtime/phase2-routing-v002').resolve(),*((ROOT/('.runtime/phase2-eval-worker-'+key)).resolve() for key in 'abc')}:
    raise RuntimeError('Unregistered phase2 runtime')
INVENTORY=ROOT/'harness/experiments/phase2-discogs-20261021-01/private/cases.private.json'
DB=RUNTIME/'data/discogs.db'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def cases(): return json.loads(INVENTORY.read_text(encoding='utf8'))['cases']
def fixed(case_id): return next(c for c in cases() if c['id']==case_id)
@contextmanager
def connect(path):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    try:
        yield db
    finally:
        db.close()
def canonical(rows): return sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))
def snapshot(path=None):
    path=DB if path is None else path
    with connect(path) as db:
        db.execute('BEGIN')
        names=[r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        hashes={}; rows={}
        for name in names:
            data=canonical([dict(r) for r in db.execute('select * from "'+name.replace('"','""')+'"')])
            hashes[name]=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if name in {'collection_items','wantlist_items','cart_items','marketplace_listings'}: rows[name]=data
        demo=db.execute("select id from users where username='demo'").fetchone()[0]
    return {'table_hashes':hashes,'rows':rows,'account_id':demo}
def reset(case_id):
    case_id=case_id['id'] if isinstance(case_id,dict) else case_id
    case=fixed(case_id); source=ROOT/case['initial_db']
    if digest(source)!=case['initial_sha256']: raise RuntimeError('Frozen initial DB changed')
    # Caller must hold the management lease and stop all case browser contexts.
    with connect(source) as src,closing(sqlite3.connect(DB,timeout=15)) as dst: src.backup(dst)
    return {'case_id':case_id,'initial_sha256':case['initial_sha256'],'table_hashes':snapshot()['table_hashes']}
def ingest_http(method,url,status,request_body=None,response_body=None,content_type=None):
    """Trusted management gateway hook, never exposed as a learner tool.

    Payloads/tokens/headers are discarded except fixed non-sensitive task keys.
    Caller attests the traffic comes from its isolated browser transport.
    """
    parsed=urlparse(url)
    if parsed.scheme not in {'http','https'} or parsed.hostname not in {'127.0.0.1','localhost'} or parsed.port!=12042:
        return None
    path=parsed.path
    if not path.startswith('/api/') or '/auth/' in path or method.upper() not in {'GET','POST','DELETE','PATCH','PUT'}:
        return None
    item={'method':method.upper(),'path':path,'status':int(status),'source':'trusted_browser_gateway'}
    if path=='/api/me/listings' and item['method']=='POST':
        try:
            body=request_body if isinstance(request_body,dict) else json.loads(request_body.decode('utf8') if isinstance(request_body,bytes) else request_body)
            item['safe_request']={key:body.get(key) if type(body.get(key)) is int else None for key in ['release_id','quantity']}
        except (ValueError,TypeError,AttributeError,UnicodeError):
            item['safe_request']=None
    return item

def attach_ui(page):
    events=[]
    def response_seen(response):
        try:body=response.request.post_data_json if response.request.method=='POST' and urlparse(response.url).path=='/api/me/listings' else None
        except Exception:body=None
        url=response.url
        worker_ports={'phase2-eval-worker-a':13042,'phase2-eval-worker-b':14042,'phase2-eval-worker-c':15042}
        parsed=urlparse(url)
        if parsed.hostname in {'127.0.0.1','localhost'} and parsed.port==worker_ports.get(RUNTIME.name):
            url=parsed._replace(netloc='127.0.0.1:12042').geturl()
        item=ingest_http(response.request.method,url,response.status,body)
        if item is not None:
            item['source']='trusted_playwright_page'
            events.append(item)
    page.on('response',response_seen)
    return events

def score(case_id, events, *, screenshot_path=None, ui_error=None, _before=None, _after=None):
    case=fixed(case_id); initial=ROOT/case['initial_db']
    if digest(initial)!=case['initial_sha256']: raise RuntimeError('Frozen initial DB changed')
    before=_before if _before is not None else snapshot(initial);after=_after if _after is not None else snapshot(); uid=before['account_id']; kind=case['kind']
    table=case.get('table','cart_items' if kind.startswith('cart_') else 'marketplace_listings')
    unchanged=[t for t,h in before['table_hashes'].items() if t!=table and after['table_hashes'].get(t)!=h]
    b=before['rows'][table];a=after['rows'][table]
    checks={'unrelated_tables_unchanged':not unchanged}; endpoint=''; method='POST'; statuses={200,201}
    if kind.startswith('membership_'):
        target=lambda r:r['user_id']==uid and r['release_id']==case['release_id']
        checks['exactly_one_membership']=len([r for r in a if target(r)])==1
        checks['unrelated_rows_unchanged']=[r for r in a if not target(r)]==[r for r in b if not target(r)]
        checks['correct_transition']=len([r for r in b if target(r)])==(1 if kind.endswith('idempotent') else 0)
        if kind.endswith('idempotent'): checks['all_state_unchanged']=after['table_hashes']==before['table_hashes']
        endpoint='/api/me/'+('collection' if table=='collection_items' else 'wantlist')+'/'+str(case['release_id'])
    elif kind.startswith('cart_'):
        target=lambda r:r['user_id']==uid and r['listing_id']==case['listing_id']
        old=[r for r in b if target(r)]; new=[r for r in a if target(r)]
        checks['unrelated_rows_unchanged']=[r for r in a if not target(r)]==[r for r in b if not target(r)]
        if kind=='cart_remove':
            checks['removed']=not new
            endpoint='/api/cart/items/'+str(old[0]['id']);method='DELETE'
        else:
            checks['incremented_once']=len(new)==1 and new[0]['quantity']==old[0]['quantity']+1
            checks['identity_preserved']=len(new)==1 and {k:v for k,v in new[0].items() if k!='quantity'}=={k:v for k,v in old[0].items() if k!='quantity'}
            endpoint='/api/cart/items'
    else:
        checks['all_state_unchanged']=before['table_hashes']==after['table_hashes']
        endpoint='/api/me/listings';statuses={422}
    checks['trusted_ui_response']=any(e.get('path')==endpoint and e.get('method')==method and e.get('status') in statuses for e in events)
    if kind=='listing_reject':
        checks['requested_boundary_observed']=any(e.get('path')==endpoint and e.get('status')==422 and e.get('safe_request')=={'release_id':case['release_id'],'quantity':case['quantity']} for e in events)
    shot=Path(screenshot_path).resolve() if screenshot_path else None
    checks['screenshot_exists']=bool(shot and shot.is_file() and shot.is_relative_to(RUNTIME))
    checks['no_ui_error']=not ui_error
    state_ok=all(v for k,v in checks.items() if k not in {'trusted_ui_response','requested_boundary_observed','screenshot_exists','no_ui_error'})
    outcome='passed' if all(checks.values()) else ('unable_to_confirm' if state_ok else 'failed')
    return {'case_id':case_id,'outcome':outcome,'checks':checks,'ui_error':ui_error,'source_truth':'independent read-only SQLite plus trusted UI response and screenshot','inventory_sha256':digest(INVENTORY),'initial_sha256':case['initial_sha256'],'denominator_retained':True}


def is_business_write(event):
    method=event.get('method','').upper();path=event.get('path','')
    if method not in {'POST','PUT','PATCH','DELETE'} or not path.startswith('/api/'):
        return False
    # Only known read-only authentication actions are excluded. Unknown API
    # mutations remain conservative business writes, never silently safe.
    return not (method=='POST' and path in {'/api/auth/login','/api/auth/logout'})

def assess_reset_safety(events,barrier=None,not_before_ns=None):
    """A fail-closed management assertion, separate from target correctness.

    This proves observed-request completion only under trusted log completeness,
    browser cleanup and ingress-drain attestations. It cannot cancel a server
    handler or infer completion from current DB contents.
    """
    barrier=barrier if isinstance(barrier,dict) else {}
    reasons=[];details=[];groups={};write_events=0
    required=('relay_drained','browser_tree_clean','gateway_log_complete')
    for key in required:
        if barrier.get(key) is not True:reasons.append('management_barrier_not_confirmed:'+key)
    if type(not_before_ns) is not int:reasons.append('case_time_boundary_missing')
    if not isinstance(events,list):
        events=[];reasons.append('event_log_not_array')
    for event in events:
        if not isinstance(event,dict):reasons.append('event_not_object');continue
        if not is_business_write(event):continue
        write_events+=1
        if event.get('source') not in {'trusted_browser_gateway','trusted_playwright_page'}:
            reasons.append('business_event_untrusted_source');continue
        started=event.get('management_request_started_ns')
        if type(started) is not int:
            reasons.append('business_request_time_missing');continue
        if type(not_before_ns) is int and started<not_before_ns:
            reasons.append('business_request_precedes_case_boundary')
        key=(event.get('method','').upper(),event.get('path'),started)
        groups.setdefault(key,[]).append(event)
    # These statuses are explicitly supported by the unchanged local UI/backend
    # contract. Proxy/server errors and unexpected statuses never certify that a
    # possibly upstream handler is no longer executing.
    terminal={200,201,204,400,401,403,404,405,422}
    for key,rows in groups.items():
        dispatches=[row for row in rows if row.get('event_phase')=='dispatch' and type(row.get('status')) is int and row['status']==0]
        responses=[row for row in rows if row.get('event_phase')=='response']
        request_reasons=[]
        if len(dispatches)!=1:request_reasons.append('business_dispatch_missing_or_ambiguous')
        if len(responses)!=1:request_reasons.append('business_terminal_response_missing_or_ambiguous')
        elif type(responses[0].get('status')) is not int or responses[0]['status'] not in terminal:
            request_reasons.append('business_response_does_not_prove_handler_completion')
        if len(rows)!=len(dispatches)+len(responses):request_reasons.append('business_event_phase_invalid')
        if len(dispatches)==1 and len(responses)==1 and rows.index(dispatches[0])>=rows.index(responses[0]):request_reasons.append('business_response_precedes_dispatch')
        if request_reasons:
            reasons.extend(request_reasons)
            details.append({'request_ref_sha256':hashlib.sha256(json.dumps(key).encode()).hexdigest(),'reasons':request_reasons})
    reasons=sorted(set(reasons));safe=not reasons
    return {'version':1,'safe_to_reset':safe,'status':'confirmed' if safe else 'unknown','case_result_final':safe,'business_request_groups':len(groups),'business_events':write_events,'unconfirmed_request_groups':len(details),'reasons':reasons,'request_diagnostics':details,'recovery_policy':'Do not reset or retry writes on unknown. Preserve this case and stop/reap the affected frontend/backend worker trees before an independently recorded recovery; never infer safety from a state snapshot alone.','assumptions':['management-owned complete dispatch/response log','all browser descendants closed','gateway ingress closed and requests drained','trusted frozen deployment; responses in registered normal contract complete after backend handler returns']}

def observe():
    """Management-only snapshot; never include in learner prompts."""
    return snapshot()

def public_case(case):
    item=fixed(case['id'] if isinstance(case,dict) else case)
    return {'id':item['id'],'goal':item['goal'],'parameters':{}}

def evaluate(case,before,after,ui_evidence):
    """Host owns snapshots/evidence; learner supplies only optional prediction."""
    case_id=case['id'] if isinstance(case,dict) else case
    item=fixed(case_id)
    events=ui_evidence.get('events',[])
    result=score(case_id,events,screenshot_path=ui_evidence.get('screenshot_path'),ui_error=ui_evidence.get('ui_error'),_before=before,_after=after)
    kind=item['kind']
    endpoint=('/api/me/'+('collection' if item.get('table')=='collection_items' else 'wantlist')+'/'+str(item['release_id'])) if kind.startswith('membership_') else '/api/me/listings' if kind=='listing_reject' else '/api/cart/items'
    relevant=[e for e in events if e.get('method')==('DELETE' if kind=='cart_remove' else 'POST') and (e.get('path')==endpoint or kind=='cart_remove' and e.get('path','').startswith(endpoint+'/'))]
    status=relevant[-1]['status'] if relevant else None
    transport_disposition='accepted' if status and 200<=status<300 else 'rejected' if status and 400<=status<500 else 'unknown'
    # Every locked case references an existing source-verified object. On this
    # unchanged build, UI 404 is the independently evidenced routing blocker,
    # not a demonstrated domain-level rejection. Preserve it as an unknown.
    disposition='unknown' if status==404 else transport_disposition
    changed=before['table_hashes']!=after['table_hashes']
    unknown_tables=[t for t in before['table_hashes'] if t not in before['rows'] and before['table_hashes'][t]!=after['table_hashes'].get(t)]
    count=0
    for table,old in before['rows'].items():
        oldset={json.dumps(r,sort_keys=True) for r in old};newset={json.dumps(r,sort_keys=True) for r in after['rows'][table]}
        count+=max(len(oldset-newset),len(newset-oldset))
    truth={'disposition':disposition,'persistent_state_changed':changed,'affected_record_count':None if unknown_tables else count}
    prediction=ui_evidence.get('prediction',{})
    claims={'disposition':prediction.get('disposition'),**prediction.get('effects',{})}
    grading={}
    for field,actual in truth.items():
        claimed=claims.get(field)
        grading[field]='unknown' if claimed is None or claimed=='unknown' else 'unscorable' if actual is None or actual=='unknown' else 'correct' if type(claimed) is type(actual) and claimed==actual else 'incorrect'
    result.update(task_outcome=result['outcome'],transport_disposition=transport_disposition,environment_limited=status==404,business_disposition=disposition,side_effects_ok=result['checks']['unrelated_tables_unchanged'] and result['checks'].get('unrelated_rows_unchanged',True) and result['checks'].get('all_state_unchanged',True),prediction_grading=grading,ui_claims_grading=[{'claim':c,'grade':'unscorable'} for c in prediction.get('ui_claims',[])])
    result['management_safety']=assess_reset_safety(events,ui_evidence.get('management_barrier'),ui_evidence.get('before_captured_at_ns'))
    return result


def reset_learning(seed):
    """Reset only from the original frozen baseline, never a private case state.

    Seed is scheduling metadata. Caller holds the exclusive management lease
    and disposes previous browser contexts before invoking this function.
    """
    if type(seed) is not int or not 0<=seed<2**31:
        raise ValueError('Scheduling seed must be an unsigned 31-bit integer')
    baseline=RUNTIME/'data/baseline.db'
    expected=(RUNTIME/'baseline.sha256').read_text(encoding='ascii').strip()
    original=ROOT/'.runtime/phase1-discogs-pw-20261020-1633/data/baseline.db'
    if digest(baseline)!=expected or digest(original)!=expected:
        raise RuntimeError('Original learning baseline hash mismatch')
    with connect(baseline) as source,closing(sqlite3.connect(DB,timeout=15)) as destination:
        source.backup(destination)
    state=observe()
    return {'kind':'learning_initialization','seed':seed,'seed_semantics':'scheduling only; identical original baseline','baseline_sha256':expected,'snapshot':state}
