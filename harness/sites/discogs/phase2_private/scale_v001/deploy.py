"""Extra d..l independent copies, using the original trusted supervisor functions."""
import argparse
import json
import os
import subprocess
from pathlib import Path
import sys
from uuid import uuid4
from management import HERE, PRIVATE, WORKERS, EXTRA, PARENT, load_file, sha
sys.path.insert(0, str(PRIVATE))
legacy = load_file('scale_original_worker_deploy', PRIVATE / 'worker_deploy.py')
legacy.HERE = HERE  # only the external Node deployment preload path changes

def dependencies(worker):
    manifest = json.loads((PARENT / 'dependency-copy-manifest.json').read_text(encoding='utf-8'))
    folder = worker['runtime'] / 'source/frontend/node_modules'
    for name, expected in manifest['hashes'].items():
        if sha(folder / name) != expected:
            raise ValueError('Dependency copy differs')
    return len(manifest['hashes'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'start', 'serve', 'status', 'verify'])
    parser.add_argument('--worker', choices=EXTRA, required=True)
    args = parser.parse_args(); worker = EXTRA[args.worker]
    if args.action == 'prepare':
        legacy.prepare(worker)
        count = dependencies(worker)
        legacy.write(worker['runtime'] / 'scale-admission.json', {'adapter_version': 'scale-v001',
            'dependency_files_verified': count, 'frozen_driver_sha256': sha(PRIVATE / 'driver.py'),
            'frozen_evaluator_sha256': sha(PRIVATE / 'evaluator.py'),
            'management_adapter_sha256': sha(HERE / 'management.py'),
            'transport_parent_sha256': sha(PRIVATE / 'worker_transport.cjs'),
            'transport_sha256': sha(HERE / 'worker_transport.cjs'),
            'business_semantics_changed': False, 'state_copy': 'independent full copies; no links'})
    elif args.action == 'start':
        runtime=worker['runtime']
        if not (runtime/'scale-admission.json').is_file():raise RuntimeError('Preparation verification incomplete')
        legacy.require_memory()
        token=uuid4().hex
        marker=runtime/('stop-scale001-'+token)
        env=os.environ.copy();env['HARNESS_STOP_FILE']=str(marker)
        with (runtime/'logs'/('supervisor-'+token+'.log')).open('xb') as log:
            process=subprocess.Popen([sys.executable,str(HERE/'deploy.py'),'serve','--worker',worker['id']],
                env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        record={'worker_id':worker['id'],'launcher_pid':process.pid,'stop_marker':str(marker),'token':token}
        legacy.write(runtime/('scale-launch-'+token+'.json'),record)
        print(json.dumps(record),flush=True)
    elif args.action == 'serve': legacy.serve(worker)
    elif args.action == 'verify':
        print(json.dumps({**legacy.verify(worker), 'dependency_files': dependencies(worker)}))
    else:
        print(json.dumps({'worker_id': worker['id'], 'free_ram_bytes': legacy.free_memory(),
              'ports': {str(worker[k]): legacy.listener(worker[k]) for k in ['frontend_port','backend_port']}}))

if __name__ == '__main__': main()
