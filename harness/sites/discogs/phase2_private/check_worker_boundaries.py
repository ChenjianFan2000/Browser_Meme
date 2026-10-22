"""Independent network boundary and cross-worker state acceptance; no pilot access."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from uuid import uuid4
from worker_registry import ROOT,PARENT,WORKERS
from worker_deploy import require_memory,sha,write
HERE=Path(__file__).resolve().parent
def evaluator(worker):
    os.environ['BM_DISCOGS_PHASE2_RUNTIME']=str(worker['runtime'])
    spec=importlib.util.spec_from_file_location('worker_eval_'+worker['id'],HERE/'evaluator.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e);return e
def main():
    minimum=require_memory();evaluators={key:evaluator(worker) for key,worker in WORKERS.items()}
    for key,e in evaluators.items():e.reset('P01')
    results=[]
    for key,worker in WORKERS.items():
        minimum=min(minimum,require_memory());runtime=worker['runtime'];folder=runtime/'private/boundary-acceptance-001';folder.mkdir(exist_ok=False)
        before={k:e.observe() for k,e in evaluators.items()};env=os.environ.copy();env.update(BM_ALLOWED_BACKEND_PORT=str(worker['backend_port']),BM_FOREIGN_BACKEND_PORTS=','.join(str(w['backend_port']) for k,w in WORKERS.items() if k!=key),BM_CONNECTION_LOG=str(folder/'probe-connections.jsonl'),BM_FIXTURE_FILE=str(runtime/'public-fixture.json'),BM_PROBE_OUTPUT=str(folder/'transport-result.json'))
        process=subprocess.run(['node','--require',str(HERE/'worker_transport.cjs'),str(HERE/'probe_worker_transport.cjs')],env=env,capture_output=True,text=True,timeout=60)
        if process.returncode:raise RuntimeError('Transport boundary probe failed: '+process.stdout+process.stderr)
        after={k:e.observe() for k,e in evaluators.items()}
        own_changed=before[key]['table_hashes']!=after[key]['table_hashes'];others_unchanged=all(before[k]==after[k] for k in WORKERS if k!=key)
        if not own_changed or not others_unchanged:raise RuntimeError('Own/cross-worker state isolation failed')
        # Unmatched frontend routes exercise the actual frozen rewrite fallback.
        states={k:e.observe() for k,e in evaluators.items()};paths=[]
        for method in ['GET','POST']:
            suffix='worker-isolation-'+uuid4().hex;url=f"http://127.0.0.1:{worker['frontend_port']}/api/{suffix}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url,method=method,data=b'{}' if method=='POST' else None),timeout=15) as response:status=response.status
            except urllib.error.HTTPError as error:status=error.code
            paths.append({'method':method,'status':status,'suffix':suffix})
            if status!=404:raise RuntimeError('Unexpected frozen fallback response')
        if any(states[k]!=e.observe() for k,e in evaluators.items()):raise RuntimeError('Unmatched route mutated worker state')
        connections=[json.loads(line) for line in (runtime/'logs/frontend-connections.jsonl').read_text(encoding='utf8').splitlines() if line]
        allowed=[r for r in connections if r.get('decision')=='allowed']
        if not allowed or any(r.get('target_port')!=worker['backend_port'] or r.get('target_host')!='127.0.0.1' for r in allowed):raise RuntimeError('Actual frontend connection escaped worker')
        mapped=[r for r in allowed if r.get('mapped')]
        if not mapped:raise RuntimeError('Frozen fixed-target fallback did not exercise mapper')
        record={'worker_id':key,'status':'passed','own_business_write_verified':own_changed,'other_worker_databases_unchanged':others_unchanged,'unmatched_routes':paths,'actual_frontend_all_connections_stayed_own_backend':True,'fixed_fallback_mapping_exercised':True,'transport_probe':json.loads((folder/'transport-result.json').read_text()),'minimum_available_ram_bytes':minimum,'pilot_accessed':False}
        write(folder/'result.private.json',record);results.append(record)
    for key,e in evaluators.items():e.reset_learning(0)
    summary={'kind':'independent_deployment_boundary_acceptance_not_learner','workers':[{k:v for k,v in r.items() if k not in {'unmatched_routes','transport_probe'}} for r in results],'minimum_available_ram_bytes':minimum,'pilot_accessed':False}
    write(WORKERS['a']['runtime']/'private/boundary-summary.management.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
