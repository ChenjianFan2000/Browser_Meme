"""Private deployment tests; only d..l databases are observed/reset/written."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from uuid import uuid4
from management import PRIVATE, EXTRA, WORKERS, evaluator, sha
sys.path.insert(0, str(PRIVATE))
from worker_deploy import require_memory, write
HERE=Path(__file__).resolve().parent

def main():
    evaluators={key:evaluator(worker['runtime']) for key,worker in EXTRA.items()}
    minimum=require_memory()
    for e in evaluators.values(): e.reset('P01')
    results=[]
    for key,worker in EXTRA.items():
        minimum=min(minimum,require_memory());runtime=worker['runtime']
        folder=runtime/'private/scale-boundary-001';folder.mkdir(exist_ok=False)
        before={k:e.observe() for k,e in evaluators.items()}
        env=os.environ.copy();env.update(BM_ALLOWED_BACKEND_PORT=str(worker['backend_port']),
            BM_FOREIGN_BACKEND_PORTS=','.join(str(w['backend_port']) for k,w in WORKERS.items() if k!=key),
            BM_CONNECTION_LOG=str(folder/'probe-connections.jsonl'),BM_FIXTURE_FILE=str(runtime/'public-fixture.json'),
            BM_PROBE_OUTPUT=str(folder/'transport-result.json'))
        result=subprocess.run(['node','--require',str(HERE/'worker_transport.cjs'),str(PRIVATE/'probe_worker_transport.cjs')],
            env=env,capture_output=True,text=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode: raise RuntimeError('Transport probe failed for '+key+': '+result.stderr)
        after={k:e.observe() for k,e in evaluators.items()}
        if before[key]['table_hashes']==after[key]['table_hashes'] or any(before[k]!=after[k] for k in EXTRA if k!=key):
            raise RuntimeError('Own-write/other-new-worker isolation failed')
        state={k:e.observe() for k,e in evaluators.items()};routes=[]
        for method in ['GET','POST']:
            url='http://127.0.0.1:'+str(worker['frontend_port'])+'/api/scale-isolation-'+uuid4().hex
            try:
                with urllib.request.urlopen(urllib.request.Request(url,method=method,data=b'{}' if method=='POST' else None),timeout=20) as response: status=response.status
            except urllib.error.HTTPError as error: status=error.code
            if status!=404:raise RuntimeError('Unexpected unmatched fallback response')
            routes.append({'method':method,'status':status})
        if any(state[k]!=e.observe() for k,e in evaluators.items()):raise RuntimeError('Unmatched route changed new-worker state')
        logs=[json.loads(line) for line in (runtime/'logs/frontend-connections.jsonl').read_text(encoding='utf-8').splitlines()]
        allowed=[row for row in logs if row.get('decision')=='allowed']
        if not allowed or any(row.get('target_host')!='127.0.0.1' or row.get('target_port')!=worker['backend_port'] for row in allowed):
            raise RuntimeError('Frontend escaped own backend')
        if not any(row.get('mapped') for row in allowed):raise RuntimeError('Fixed fallback was not exercised')
        record={'worker_id':key,'status':'passed','own_business_write_verified':True,
            'other_eight_new_worker_snapshots_unchanged':True,'original_abc_business_state_accessed':False,
            'original_abc_connection_attempts_denied_before_socket_connect':True,'unmatched_routes':routes,
            'actual_frontend_connections_own_backend_only':True,'minimum_available_ram_bytes':minimum,
            'transport_probe':json.loads((folder/'transport-result.json').read_text(encoding='utf-8')),
            'kind':'deployment_acceptance_not_learner'}
        write(folder/'result.private.json',record);results.append(record)
        print(json.dumps({'worker_id':key,'boundary':'passed','minimum_free':minimum}),flush=True)
    for e in evaluators.values():e.reset_learning(0)
    identities=[(w['runtime']/'data/discogs.db').stat() for w in EXTRA.values()]
    if len({(s.st_dev,s.st_ino) for s in identities})!=9 or any(s.st_nlink!=1 for s in identities):
        raise RuntimeError('New databases share file identity or links')
    write(EXTRA['d']['runtime']/'private/scale-boundary-summary.json',{'workers':9,'passed':9,
        'independent_db_file_ids':True,'db_link_counts_one':True,'minimum_available_ram_bytes':minimum,
        'original_abc_business_state_accessed':False})

if __name__=='__main__':main()
