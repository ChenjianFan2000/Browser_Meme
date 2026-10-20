"""Content-addressed input freezing and durable append-only event records."""
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

from .contract import local_path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_manifest(site, root):
    files = set()
    for item in [site['adapter'], *site['source_roots']]:
        path = local_path(root, item)
        files.update([path] if path.is_file() else (p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts))
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(files)}


def freeze(site_path, bundle_path, site, cases, out, root):
    inputs = out / 'inputs'
    inputs.mkdir()
    shutil.copyfile(site_path, inputs / 'site.json')
    shutil.copyfile(bundle_path, inputs / 'bundle.json')
    write_json(inputs / 'cases.json', cases)
    manifest = {'algorithm': 'sha256', 'sources': source_manifest(site, root),
                'inputs': {p.name: digest(p) for p in inputs.iterdir()},
                'harness': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')},
                'runtime': {'python': sys.version, 'platform': platform.platform()},
                'argv': sys.argv, 'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write_json(out / 'manifest.json', manifest)
    return manifest


def verify_frozen(out, root, site):
    from .contract import read_json
    out = Path(out)
    manifest = read_json(out / 'manifest.json')
    errors = []
    for name, expected in manifest['inputs'].items():
        if digest(out / 'inputs' / name) != expected:
            errors.append(f'input changed: {name}')
    current = source_manifest(site, root)
    if current != manifest['sources']:
        errors.append('source/adapter content changed')
    for name, expected in manifest['harness'].items():
        path = Path(__file__).parent / name
        if not path.exists() or digest(path) != expected:
            errors.append(f'harness changed: {name}')
    return errors


class Recorder:
    def __init__(self, path):
        self.handle = Path(path).open('x', encoding='utf-8')
        self.sequence = 0

    def emit(self, kind, **data):
        self.sequence += 1
        event = {'seq': self.sequence, 'time_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns(),
                 'kind': kind, **data}
        self.handle.write(json.dumps(event, ensure_ascii=False) + '\n')
        self.handle.flush()
        os.fsync(self.handle.fileno())
        return event

    def close(self):
        self.handle.close()
