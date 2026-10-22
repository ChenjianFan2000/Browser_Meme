"""Root-authorized six-worker recovery; no reset, DB writes or old-ready edit."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import urllib.request
import psutil
from management import PRIVATE, ROOT, WORKERS, sha

def now():return time.time_ns()
def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
def db_files(runtime):
    return {'sampled_at_ns':now(),'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}
            for p in (runtime/'data').glob('discogs.db*') if p.is_file()}}
def owned(pid,key):
    try:
        p=psutil.Process(pid);cmd=p.cmdline()
        return '--worker' in cmd and cmd[cmd.index('--worker')+1]==key and any('deploy.py' in x for x in cmd)
    except (psutil.NoSuchProcess,psutil.AccessDenied,ValueError,IndexError):return False
def alive_same(pid,created):
    try:return psutil.Process(pid).create_time()==created
    except psutil.NoSuchProcess:return False

def main():
    token=uuid4().hex;records=[]
    for key in 'ghijkl':
        runtime=WORKERS[key]['runtime'];launches=[]
        for path in runtime.glob('scale-launch-*.json'):
            row=json.loads(path.read_text());
            if owned(row['launcher_pid'],key):launches.append(row)
        if len(launches)>1:raise RuntimeError('Multiple owned extra launchers')
        record={'worker_id':key,'action':'pause_idle_owned_service','at_ns':now(),'active_formal_case':False,'old_records_preserved':True}
        if launches:
            launch=launches[0];pids=json.loads((runtime/('pids-'+str(launch['launcher_pid'])+'.json')).read_text())
            processes=[(pid,psutil.Process(pid).create_time()) for name,pid in pids.items() if name in {'launcher','frontend','backend'} and psutil.pid_exists(pid)]
            marker=Path(launch['stop_marker']).resolve()
            if not marker.is_relative_to(runtime.resolve()):raise RuntimeError('Stop marker escape')
            if not marker.exists():
                with marker.open('x',encoding='ascii') as f:f.write('root-authorized-idle-scale-pause\n')
            deadline=time.monotonic()+30
            while any(alive_same(pid,created) for pid,created in processes) and time.monotonic()<deadline:time.sleep(.2)
            if any(alive_same(pid,created) for pid,created in processes):raise RuntimeError('Owned idle worker did not stop')
            record.update(stop_marker=str(marker),owned_pids=pids,all_owned_processes_exited=True)
        else:record['already_stopped']=True
        records.append(record)
    for key in 'abc':
        worker=WORKERS[key];runtime=worker['runtime']
        before=db_files(runtime)
        marker=runtime/('stop-recovery-six-'+token)
        env=os.environ.copy();env['HARNESS_STOP_FILE']=str(marker)
        log_path=runtime/'logs'/('recovery-six-'+token+'.log')
        with log_path.open('xb') as log:
            child=subprocess.Popen([sys.executable,str(PRIVATE/'worker_deploy.py'),'serve','--worker',key],env=env,
                stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+120;healthy=False
        while time.monotonic()<deadline:
            try:
                for port,path in [(worker['frontend_port'],'/'),(worker['backend_port'],'/healthz')]:
                    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=3) as response:
                        if response.status!=200:raise ValueError('Unhealthy')
                healthy=True;break
            except Exception:
                if child.poll() is not None:break
                time.sleep(.5)
        after=db_files(runtime)
        pids=runtime/('pids-'+str(child.pid)+'.json')
        record={'worker_id':key,'action':'recover_original_frozen_service','launcher_pid':child.pid,'stop_marker':str(marker),
            'log_path':str(log_path),'healthy':healthy,'services':json.loads(pids.read_text()) if pids.exists() else None,
            'before_db_files':before,'after_db_files':after,'main_db_bytes_unchanged':before['files'].get('discogs.db')==after['files'].get('discogs.db'),
            'raw_file_set_unchanged':before['files']==after['files'],'reset_called':False,'db_opened_by_manager':False,
            'old_readiness_rewritten':False,'frozen_worker_deploy_sha256':sha(PRIVATE/'worker_deploy.py')}
        write(runtime/('recovery-six-'+token+'.management.json'),record);records.append(record)
        if not healthy or not record['main_db_bytes_unchanged']:raise RuntimeError('Recovery health/DB-byte preservation failed')
    output=ROOT/'harness/experiments/phase2-discogs-20261021-01/private'/('recovery-six-'+token+'.json')
    write(output,{'kind':'management_owned_service_recovery_not_score','token':token,'scope':'abc+def only; pausedghijkl',
        'records':records,'db_read_scope':'hash-only file bytes, no SQL or evaluator snapshots',
        'temporal_limit':'Before/after endpoint samples do not prove no writes throughout the interval.',
        'formal_cases_modified':False,'frozen_management_sha256':sha(Path(__file__).with_name('management.py'))})
    print(json.dumps({'output':str(output),'sha256':sha(output),'abc_healthy':True,'ghijkl_paused':True}),flush=True)

if __name__=='__main__':main()
