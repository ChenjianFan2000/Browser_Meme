"""Freeze independent worker acceptance and restore only worker learning states."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import urllib.request
from worker_registry import ROOT,PARENT,WORKERS
from worker_deploy import require_memory,verify,sha,write
HERE=Path(__file__).resolve().parent
def main():
    require_memory();summaries=[]
    for key,worker in WORKERS.items():
        runtime=worker['runtime'];verify(worker);os.environ['BM_DISCOGS_PHASE2_RUNTIME']=str(runtime)
        spec=importlib.util.spec_from_file_location('final_worker_eval_'+key,HERE/'evaluator.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
        report=json.loads((runtime/'private/ui-readiness-001/report.private.json').read_text(encoding='utf8'))
        if report['executed']!=30:raise RuntimeError('Fixed denominator incomplete')
        evaluations=[]
        for case in e.cases():
            folder=runtime/'private/ui-readiness-001'/case['id'];r=json.loads((folder/'result.json').read_text(encoding='utf8'));before=json.loads((folder/'before.private.json').read_text(encoding='utf8'));after=json.loads((folder/'after.private.json').read_text(encoding='utf8'))
            evaluations.append(e.evaluate(case,before,after,{'events':r['events'],'screenshot_path':str(folder/'after.png'),'ui_error':r['error']}))
        if not all(r['outcome']=='passed' and r['side_effects_ok'] for r in evaluations):raise RuntimeError('Worker UI verification failed')
        connections=[json.loads(line) for line in (runtime/'logs/frontend-connections.jsonl').read_text(encoding='utf8').splitlines() if line]
        allowed=[row for row in connections if row.get('decision')=='allowed']
        if any(row.get('target_port')!=worker['backend_port'] or row.get('target_host')!='127.0.0.1' for row in allowed):raise RuntimeError('Worker escaped own backend')
        final=runtime/'private/final-ui-evaluations.private.json';write(final,{'worker_id':key,'kind':'independent_environment_acceptance_not_learner','denominator':30,'evaluations':evaluations,'evaluator_sha256':sha(HERE/'evaluator.py')})
        baseline=e.reset_learning(0);write(runtime/'private/learning-reset-before-handoff.private.json',baseline)
        pids=json.loads(max(runtime.glob('pids-*.json'),key=lambda p:p.stat().st_mtime_ns).read_text())
        for port,path in [(worker['frontend_port'],'/'),(worker['backend_port'],'/healthz')]:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=10) as response:
                if response.status!=200:raise RuntimeError('Worker health failed')
        summary={'worker_id':key,'status':'ready','site_variant':'phase2-routing-v002','deployment_adapter':'parallel-workers-v001','runtime':str(runtime),'frontend_port':worker['frontend_port'],'backend_port':worker['backend_port'],'learner_visible_origin':'http://127.0.0.1:12042','ui_denominator':30,'ui_verified':30,'ordinary_logins_verified':30,'side_effect_checks_passed':30,'cli_component_groups_passed':11,'source_manifest_sha256':sha(PARENT/'variant-source-manifest.json'),'build_manifest_sha256':sha(PARENT/'variant-build-manifest.json'),'dependency_files_verified':20041,'inventory_sha256':sha(e.INVENTORY),'node_preload_sha256':sha(HERE/'worker_transport.cjs'),'final_ui_evidence_sha256':sha(final),'boundary_evidence_sha256':sha(runtime/'private/boundary-acceptance-001/result.private.json'),'allowed_frontend_connections_all_own_backend':True,'connections_audited':len(allowed),'external_decorative_image_requests_denied':sum(row.get('decision')=='denied' and row.get('requested_host')=='images.unsplash.com' for row in connections),'transport_scope':'Trusted frozen Node process; not an OS sandbox against arbitrary native code','learning_state_reset':True,'baseline_sha256':baseline['baseline_sha256'],'services':pids,'resource_guard':{'available_ram_minimum_bytes':3*1024**3,'poll_seconds':.25,'action':'stop only owned worker on threshold breach'},'prediction_scores_reported':False,'tokens':None,'cost':None,'pilot_service_or_database_accessed':False}
        write(runtime/'readiness.management.json',summary)
        overlay={'kind':'deployment_adapter_overlay','parent_worker_manifest_sha256':sha(runtime/'worker-manifest.json'),'adapter':'parallel-workers-v001','preload_revision':'v002','preload_sha256':sha(HERE/'worker_transport.cjs'),'source_build_unchanged':True,'first_attempt_failure_retained':True}
        write(runtime/'worker-adapter-v001.json',overlay)
        archive=runtime/'private/adapter-source-final';archive.mkdir()
        for path in HERE.iterdir():
            if path.is_file() and path.suffix in {'.py','.cjs','.md'}:shutil.copyfile(path,archive/path.name)
        summaries.append(summary)
    result={'kind':'independent_parallel_deployment_acceptance_not_learner','status':'ready','max_active_workers':3,'worker_count':3,'ui_total':90,'ui_verified':90,'source_variant':'phase2-routing-v002','no_speed_claim':True,'pilot_service_or_database_accessed':False,'workers':summaries,'current_available_ram_bytes':require_memory()}
    write(WORKERS['a']['runtime']/'parallel-readiness.management.json',result);print(json.dumps(result))
if __name__=='__main__':main()
