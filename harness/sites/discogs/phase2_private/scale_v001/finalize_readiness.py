"""Seal each completed extra worker independently; never reads abc state."""
import argparse
import json
from pathlib import Path
import urllib.request
import psutil
from management import HERE, PRIVATE, ROOT, PARENT, EXTRA, evaluator, sha

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',required=True);args=p.parse_args()
    for key in args.workers:
        worker=EXTRA[key];runtime=worker['runtime'];report=runtime/'private/scale-ui-acceptance-002/report.private.json'
        ui=read(report);boundary=runtime/'private/scale-boundary-001/result.private.json'
        cli=runtime/'private/scale-cli-ui-001/result.management.json'
        if ui['status']!='ready' or ui['executed']!=30 or ui['classification_counts']!={'expected_business_result_verified':30}:raise RuntimeError('UI not ready')
        if read(boundary)['status']!='passed' or not read(cli)['passed'] or read(cli)['safe_to_reset'] is not True:raise RuntimeError('Boundary/CLI not ready')
        admission=read(runtime/'scale-admission.json')
        if admission['management_adapter_sha256']!=sha(HERE/'management.py') or admission['transport_sha256']!=sha(HERE/'worker_transport.cjs'):raise RuntimeError('Adapter changed')
        e=evaluator(runtime)
        # reset_learning uses SQLite backup, so page/header bytes need not match;
        # compare the original frozen evaluator's full canonical snapshots.
        if e.snapshot()!=e.snapshot(runtime/'data/baseline.db'):raise RuntimeError('Post-acceptance logical state is not original baseline')
        stat=(runtime/'data/discogs.db').stat()
        if stat.st_nlink!=1:raise RuntimeError('DB is linked')
        launches=[read(path) for path in runtime.glob('scale-launch-*.json')]
        active=[row for row in launches if psutil.pid_exists(row['launcher_pid']) and not Path(row['stop_marker']).exists()]
        if len(active)!=1:raise RuntimeError('Expected exactly one active owned launcher')
        launch=active[0];services=read(runtime/('pids-'+str(launch['launcher_pid'])+'.json'))
        if Path(launch['stop_marker']).exists() or any(not psutil.pid_exists(services[name]) for name in ['launcher','backend','frontend']):raise RuntimeError('Owned process missing/stopped')
        for port,path in [(worker['frontend_port'],'/'),(worker['backend_port'],'/healthz')]:
            with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=15) as response:
                if response.status!=200:raise RuntimeError('Health failed')
        rows=[];guard_triggered_history=False
        for path in (runtime/'logs').glob('supervisor-*.log'):
            if 'Host available RAM below required 3 GiB' in path.read_text(encoding='utf-8'):guard_triggered_history=True
            for line in path.read_text(encoding='utf-8').splitlines():
                try:row=json.loads(line)
                except ValueError:continue
                if 'available_ram_bytes' in row:rows.append(row)
        minimum=min(row['available_ram_bytes'] for row in rows)
        if minimum<3*1024**3:raise RuntimeError('Host3GiB threshold violated')
        evidence=[runtime/'worker-manifest.json',runtime/'scale-admission.json',report,boundary,cli]
        result={'schema_version':1,'kind':'expanded_site_worker_readiness_not_learner','status':'ready','worker_id':key,
                'runtime':str(runtime),'frontend_port':worker['frontend_port'],'backend_port':worker['backend_port'],
                'site_variant':'phase2-routing-v002','source_manifest_sha256':sha(PARENT/'variant-source-manifest.json'),
                'build_manifest_sha256':sha(PARENT/'variant-build-manifest.json'),'dependency_manifest_sha256':sha(PARENT/'dependency-copy-manifest.json'),
                'dependency_files_verified':admission['dependency_files_verified'],'baseline_sha256':(runtime/'baseline.sha256').read_text().strip(),
                'inventory_sha256':ui['inventory_sha256'],'management_entry':str(HERE/'management.py'),
                'management_entry_sha256':sha(HERE/'management.py'),'node_preload_sha256':sha(HERE/'worker_transport.cjs'),
                'frozen_driver_sha256':sha(PRIVATE/'driver.py'),'frozen_evaluator_sha256':sha(PRIVATE/'evaluator.py'),
                'services':services,'stop_marker':launch['stop_marker'],'ui_cases_passed':30,'ui_fixed_denominator':30,
                'db_file_identity':{'device':stat.st_dev,'inode':stat.st_ino,'links':stat.st_nlink},
                'post_acceptance_original_baseline':True,'minimum_supervisor_host_available_bytes':minimum,
                'memory_guard_triggered_history':guard_triggered_history,
                'evidence_refs':[{'path':str(path),'sha256':sha(path)} for path in evidence],
                'limitations':['Deployment/UI readiness does not establish sustainable12Solar capacity.',
                    'First9-native-browser acceptance had missing admin-port alias and performance pressure; preserved001, corrected002 run in3-worker cohorts.',
                    'CLI integration used trusted native UI and canonical events, not physical formal relay; generic formal namespace/relay gate is separate.',
                    'Originalabc business state not accessed/reset.','Model tokens/cost unavailable.'],
                'model_tokens':None,'model_cost':None}
        output=runtime/'readiness.scale-v001.management.json'
        with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
        print(json.dumps({'worker_id':key,'readiness_path':str(output),'sha256':sha(output),'frontend_port':worker['frontend_port'],'backend_port':worker['backend_port'],'stop_marker':launch['stop_marker']}),flush=True)

if __name__=='__main__':main()
