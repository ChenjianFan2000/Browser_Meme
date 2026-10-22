"""Explicit deployment admission for extra runtimes; frozen functions stay intact."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PRIVATE = HERE.parent
ROOT = PRIVATE.parents[3]
PARENT = ROOT / '.runtime/phase2-routing-v002'
WORKERS = {chr(97+i): {'id': chr(97+i), 'runtime': ROOT / ('.runtime/phase2-eval-worker-' + chr(97+i)),
           'frontend_port': 13042+i*1000, 'backend_port': 13138+i*1000} for i in range(12)}
EXTRA = {key: value for key, value in WORKERS.items() if key >= 'd'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def identify(runtime):
    runtime = Path(runtime).resolve()
    worker = next((w for w in WORKERS.values() if w['runtime'].resolve() == runtime), None)
    if worker is None:
        raise ValueError('Unregistered scale runtime')
    if worker['id'] in EXTRA:
        manifest = json.loads((runtime / 'worker-manifest.json').read_text(encoding='utf-8'))
        if manifest['worker_id'] != worker['id'] or manifest['frontend_port'] != worker['frontend_port'] or manifest['backend_port'] != worker['backend_port']:
            raise ValueError('Scale worker admission mismatch')
        if manifest['source_manifest_sha256'] != sha(PARENT / 'variant-source-manifest.json') or manifest['build_manifest_sha256'] != sha(PARENT / 'variant-build-manifest.json'):
            raise ValueError('Scale frozen site identity mismatch')
    return worker

def evaluator(runtime):
    worker = identify(runtime)
    previous = os.environ.get('BM_DISCOGS_PHASE2_RUNTIME')
    os.environ['BM_DISCOGS_PHASE2_RUNTIME'] = str(PARENT)
    try:
        module = load_file('scale_evaluator_' + worker['id'], PRIVATE / 'evaluator.py')
    finally:
        if previous is None: os.environ.pop('BM_DISCOGS_PHASE2_RUNTIME', None)
        else: os.environ['BM_DISCOGS_PHASE2_RUNTIME'] = previous
    # Import above only creates functions/constants; no source/runtime DB read.
    module.RUNTIME = worker['runtime'].resolve()
    module.DB = module.RUNTIME / 'data/discogs.db'
    return module

def driver_main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument('--runtime', required=True)
    selected = Path(bootstrap.parse_known_args(arguments)[0].runtime).resolve()
    identify(selected)
    saved_argv, saved_env = sys.argv, os.environ.get('BM_DISCOGS_PHASE2_RUNTIME')
    sys.argv = [str(PRIVATE / 'driver.py')]
    os.environ['BM_DISCOGS_PHASE2_RUNTIME'] = str(PARENT)
    try:
        module = load_file('scale_frozen_driver', PRIVATE / 'driver.py')
    finally:
        sys.argv = saved_argv
        if saved_env is None: os.environ.pop('BM_DISCOGS_PHASE2_RUNTIME', None)
        else: os.environ['BM_DISCOGS_PHASE2_RUNTIME'] = saved_env
    module.RUNTIME = selected
    module.e = evaluator(selected)
    module.ALLOWED_RUNTIMES = {w['runtime'].resolve() for w in WORKERS.values()} | {PARENT.resolve()}
    # main and every scoring/reset/prediction function are the original objects.
    module.main(arguments)

if __name__ == '__main__':
    driver_main()
