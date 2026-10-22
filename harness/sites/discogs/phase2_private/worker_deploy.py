"""Copy frozen v002 assets and supervise isolated management workers."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from worker_registry import ROOT,PARENT,WORKERS
HERE=Path(__file__).resolve().parent
MIN_FREE=3*1024**3
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('available',ctypes.c_ulonglong),('page_total',ctypes.c_ulonglong),('page_available',ctypes.c_ulonglong),('virtual_total',ctypes.c_ulonglong),('virtual_available',ctypes.c_ulonglong),('extended',ctypes.c_ulonglong)]
def free_memory():
    record=Memory();record.length=ctypes.sizeof(record)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(record)):raise OSError('Memory measurement failed')
    return record.available
def require_memory():
    available=free_memory()
    if available<MIN_FREE:raise RuntimeError('Host available RAM below required 3 GiB; stop owned worker')
    return available
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2)
def listener(port):
    with socket.socket() as probe:probe.settimeout(.3);return probe.connect_ex(('127.0.0.1',port))==0
def verify(worker):
    runtime=worker['runtime'];source=runtime/'source'
    source_manifest=json.loads((PARENT/'variant-source-manifest.json').read_text())
    build=json.loads((PARENT/'variant-build-manifest.json').read_text())
    for name,h in source_manifest['source_hashes'].items():
        if sha(source/name)!=h:raise RuntimeError('Worker source hash mismatch')
    for name,h in build['artifact_hashes'].items():
        if sha(source/'frontend'/name)!=h:raise RuntimeError('Worker build hash mismatch')
    if sha(runtime/'data/baseline.db')!=(PARENT/'baseline.sha256').read_text().strip():raise RuntimeError('Baseline mismatch')
    return {'source_manifest_sha256':sha(PARENT/'variant-source-manifest.json'),'build_manifest_sha256':sha(PARENT/'variant-build-manifest.json'),'source_files':len(source_manifest['source_hashes']),'build_files':len(build['artifact_hashes'])}
def prepare(worker):
    require_memory();runtime=worker['runtime']
    if runtime.exists():raise RuntimeError('Refuse overwrite worker runtime')
    runtime.mkdir(parents=True)
    source=runtime/'source'
    # All files are copied, including dependencies, compiled assets and caches.
    # No hardlink/junction or shared writable state is introduced.
    status=subprocess.run(['robocopy',str(PARENT/'source'),str(source),'/E','/NFL','/NDL','/NJH','/NJS','/NP','/MT:8'],stdout=subprocess.DEVNULL).returncode
    if status>7:raise RuntimeError('Worker file copy failed')
    (runtime/'data').mkdir();(runtime/'private').mkdir();(runtime/'logs').mkdir()
    for name in ['baseline.db','discogs.db']:shutil.copyfile(PARENT/'data/baseline.db',runtime/'data'/name)
    for name in ['baseline.sha256','public-fixture.json','variant-source-manifest.json','variant-build-manifest.json','dependency-copy-manifest.json']:shutil.copyfile(PARENT/name,runtime/name)
    record={'worker_id':worker['id'],'runtime':str(runtime),'site_variant':'phase2-routing-v002','frontend_port':worker['frontend_port'],'backend_port':worker['backend_port'],'parent_runtime':str(PARENT),'node_preload_sha256':sha(HERE/'worker_transport.cjs'),'state_copy':'independent files; no links','memory_minimum_bytes':MIN_FREE,**verify(worker)}
    write(runtime/'worker-manifest.json',record);print(json.dumps({'prepared':True,'worker_id':worker['id'],'runtime':str(runtime)}),flush=True)
def serve(worker):
    runtime=worker['runtime'];require_memory();verify(worker)
    if any(listener(worker[key]) for key in ['frontend_port','backend_port']):raise RuntimeError('Worker ports occupied')
    marker=Path(os.environ.get('HARNESS_STOP_FILE','')).resolve()
    if not marker.is_relative_to(runtime.resolve()) or marker.exists():raise RuntimeError('Unique worker stop marker required')
    os.environ['BM_DISCOGS_RUNTIME']=str(runtime)
    spec=importlib.util.spec_from_file_location('worker_process_owner',ROOT/'harness/sites/discogs/deploy.py');owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    env=owner.env();backend=worker['backend_port'];front=worker['frontend_port']
    env.update(DATABASE_URL='sqlite+pysqlite:///'+(runtime/'data/discogs.db').as_posix(),PYTHONPATH=str(runtime/'source/backend'),API_INTERNAL_URL=f'http://127.0.0.1:{backend}',NEXT_PUBLIC_API_URL=f'http://127.0.0.1:{backend}',NEXT_PUBLIC_WEB_URL='http://127.0.0.1:12042',CORS_ORIGINS=f'http://127.0.0.1:12042,http://127.0.0.1:{front}',BM_ALLOWED_BACKEND_PORT=str(backend),BM_CONNECTION_LOG=str(runtime/'logs/frontend-connections.jsonl'))
    definitions=[('backend',[str(ROOT/'.runtime/phase1-discogs-pw-20261020-1633/venv/Scripts/python.exe'),'-m','uvicorn','app.main:app','--app-dir',str(runtime/'source/backend'),'--host','127.0.0.1','--port',str(backend)],runtime/'source',f'http://127.0.0.1:{backend}/healthz'),('frontend',[shutil.which('node'),'--require',str(HERE/'worker_transport.cjs'),str(runtime/'source/frontend/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',str(front)],runtime/'source/frontend',f'http://127.0.0.1:{front}')]
    children=[];pids={}
    try:
        for name,args,cwd,health in definitions:
            require_memory()
            with (runtime/'logs'/f'{name}.log').open('ab') as log:
                child=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            children.append(child);pids[name]=child.pid
        record={'launcher':os.getpid(),**pids,'stop_marker':str(marker)}
        write(runtime/('pids-'+str(os.getpid())+'.json'),record)
        if not (runtime/'pids.json').exists():write(runtime/'pids.json',record)
        started=time.monotonic();ready=False;last=0
        while not marker.exists():
            available=require_memory()
            if any(p.poll() is not None for p in children):raise RuntimeError('Owned worker process exited')
            if time.monotonic()-last>=10:
                healthy=all(owner.healthy(d[3]) for d in definitions);last=time.monotonic()
                if healthy:ready=True
                if not ready and time.monotonic()-started>120:raise RuntimeError('Worker readiness timeout')
                print(json.dumps({'worker_id':worker['id'],'ready':healthy,'available_ram_bytes':available,'owned_pids':pids}),flush=True)
            time.sleep(.25)
    finally:owner.stop_owned(children)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','serve','status']);parser.add_argument('--worker',choices=WORKERS,required=True);args=parser.parse_args();worker=WORKERS[args.worker]
    if args.action=='prepare':prepare(worker)
    elif args.action=='serve':serve(worker)
    else:print(json.dumps({'worker_id':worker['id'],'free_ram_bytes':free_memory(),'ports':{str(worker[k]):listener(worker[k]) for k in ['frontend_port','backend_port']}}))
if __name__=='__main__':main()
