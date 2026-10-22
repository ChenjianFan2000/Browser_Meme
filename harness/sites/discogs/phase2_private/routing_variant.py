"""Private framework-only variant. Original handlers/business code stay byte-identical."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
ROOT=Path(__file__).resolve().parents[4]
VARIANT=os.environ.get('BM_ROUTING_VARIANT','phase2-routing-v001')
if VARIANT not in {'phase2-routing-v001','phase2-routing-v002'}:raise RuntimeError('Unregistered routing variant')
RUNTIME=ROOT/'.runtime'/VARIANT
REFERENCE=ROOT/'.runtime/phase1-discogs-pw-20261020-1633'
SOURCE=RUNTIME/'source'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def ports():
    result={}
    for port in [12042,12138]:
        with socket.socket() as s:s.settimeout(.5);result[str(port)]=s.connect_ex(('127.0.0.1',port))==0
    return result

def prepare():
    os.environ['BM_DISCOGS_RUNTIME']=str(RUNTIME)
    os.environ['BM_DISCOGS_REFERENCE_RUNTIME']=str(REFERENCE)
    parent=load('routing_parent',ROOT/'harness/sites/discogs/complex_deploy.py');record=parent.inspect()
    if SOURCE.exists():raise RuntimeError('Variant source already exists; refuse rebuild')
    SOURCE.mkdir(parents=True)
    for name in record['source_file_hashes']:
        dest=SOURCE/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REFERENCE/'source'/name,dest)
    config=SOURCE/'frontend/next.config.ts';original=config.read_text(encoding='utf8')
    patched=original.replace('return [','return { fallback: [',1).replace('    ];','    ] };',1)
    if original==patched:raise RuntimeError('Patch did not apply')
    config.write_text(patched,encoding='utf8',newline='')
    diff=''.join(difflib.unified_diff(original.splitlines(True),patched.splitlines(True),fromfile='parent/frontend/next.config.ts',tofile=VARIANT+'/frontend/next.config.ts'))
    if VARIANT=='phase2-routing-v002':
        proxy=SOURCE/'frontend/src/app/api/backend/[...path]/route.ts'
        parent_proxy=proxy.read_text(encoding='utf8')
        proxy_patch=parent_proxy.replace('const url = backendUrl("/" + path.join("/"));','const url = backendUrl("/" + path.join("/")) + new URL(req.url).search;')
        if proxy_patch==parent_proxy:raise RuntimeError('Proxy patch did not apply')
        proxy.write_text(proxy_patch,encoding='utf8',newline='')
        diff+=''.join(difflib.unified_diff(parent_proxy.splitlines(True),proxy_patch.splitlines(True),fromfile='parent/frontend/src/app/api/backend/[...path]/route.ts',tofile=VARIANT+'/frontend/src/app/api/backend/[...path]/route.ts'))
    (RUNTIME/'routing-compatibility.patch').write_text(diff,encoding='utf8')
    # Identical frozen packages copied locally for Turbopack root compatibility.
    shutil.copytree(REFERENCE/'source/frontend/node_modules',SOURCE/'frontend/node_modules')
    data=RUNTIME/'data';data.mkdir()
    for name in ['baseline.db','discogs.db']:shutil.copyfile(REFERENCE/'data/baseline.db',data/name)
    (RUNTIME/'baseline.sha256').write_text(record['baseline_sha256'],encoding='ascii')
    fixture={'kind':'public_fixture','is_real_credential':False,'role':'ordinary_test_account','account':{'username':'demo','password':'password123'},'source':'public login page supplied by unchanged site fixture'}
    (RUNTIME/'public-fixture.json').write_text(json.dumps(fixture,indent=2),encoding='utf8')
    manifest={'variant':VARIANT,'parent':record,'patch_file':'routing-compatibility.patch','patch_sha256':sha(RUNTIME/'routing-compatibility.patch'),'source_hashes':{name:sha(SOURCE/name) for name in record['source_file_hashes']},'changed_files':[name for name,h in record['source_file_hashes'].items() if sha(SOURCE/name)!=h],'scope':'Next.js fallback rewrite priority; v002 additionally preserves generic proxy query string. All domain handlers, backend, auth, validation, business and data bytes unchanged. Rewrite destination unchanged.','shared_dependencies':'Exact frozen node_modules copied locally, frozen shared Python venv; no install/upgrade.'}
    if set(manifest['changed_files'])!=({'frontend/next.config.ts','frontend/src/app/api/backend/[...path]/route.ts'} if VARIANT=='phase2-routing-v002' else {'frontend/next.config.ts'}):raise RuntimeError('Unexpected source change')
    (RUNTIME/'variant-source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(json.dumps({'prepared':True,'runtime':str(RUNTIME),'changed_files':len(manifest['changed_files'])}))

def launcher():
    os.environ['BM_DISCOGS_RUNTIME']=str(RUNTIME)
    m=load('routing_launcher',ROOT/'harness/sites/discogs/deploy.py');m.SOURCE=SOURCE;m.PYTHON=REFERENCE/'venv/Scripts/python.exe';return m

def build():
    if (RUNTIME/'variant-build-manifest.json').exists():raise RuntimeError('Refuse overwrite frozen variant build')
    m=launcher();logs=RUNTIME/'logs';logs.mkdir(exist_ok=True)
    log=logs/'build.log'
    if log.exists():
        from uuid import uuid4
        log=logs/('build-'+uuid4().hex[:8]+'.log')
    with log.open('xb') as f:
        result=subprocess.run([shutil.which('node'),str(SOURCE/'frontend/node_modules/next/dist/bin/next'),'build'],cwd=SOURCE/'frontend',env=m.env(),stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Variant build failed; inspect private build log')
    files={p.relative_to(SOURCE/'frontend').as_posix():sha(p) for p in (SOURCE/'frontend/.next').rglob('*') if p.is_file() and 'cache' not in p.parts}
    (RUNTIME/'variant-build-manifest.json').write_text(json.dumps({'variant':VARIANT,'build_id':(SOURCE/'frontend/.next/BUILD_ID').read_text(),'artifact_hashes':files,'source_manifest_sha256':sha(RUNTIME/'variant-source-manifest.json'),'dependency_strategy':'copied byte-identical frozen node_modules; shared frozen Python venv','build_log':str(log.relative_to(RUNTIME))},indent=2),encoding='utf8')
    print(json.dumps({'built':True,'artifacts':len(files)}))

def serve():
    if any(ports().values()):raise RuntimeError('Refuse existing listener')
    marker=Path(os.environ.get('HARNESS_STOP_FILE','')).resolve()
    if not marker.is_relative_to(RUNTIME) or marker.exists():raise RuntimeError('Unique variant stop marker required')
    if not (RUNTIME/'variant-build-manifest.json').is_file():raise RuntimeError('Build first')
    manifest=json.loads((RUNTIME/'variant-source-manifest.json').read_text())
    if any(sha(SOURCE/name)!=h for name,h in manifest['source_hashes'].items()):raise RuntimeError('Variant source changed')
    build_manifest=json.loads((RUNTIME/'variant-build-manifest.json').read_text())
    if any(sha(SOURCE/'frontend'/name)!=h for name,h in build_manifest['artifact_hashes'].items()):raise RuntimeError('Variant build changed')
    launcher().serve()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','build','serve','status']);action=p.parse_args().action
    if action=='prepare':prepare()
    elif action=='build':build()
    elif action=='serve':serve()
    else:print(json.dumps({'variant':VARIANT,'ports_occupied':ports()}))
