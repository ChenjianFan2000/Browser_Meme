"""Validate dependency pins and local build hashes without network access."""
import hashlib
import json
from pathlib import Path
import re


root = Path(__file__).resolve().parents[2]
report = {}
for profile in ('core', 'agentlab', 'webchore'):
    lock = root / 'environment/requirements' / f'{profile}.lock'
    entries = []
    local_wheels = 0
    for entry in lock.read_text(encoding='utf-8').replace('\\\n', ' ').splitlines():
        entry = entry.strip()
        if not entry or entry.startswith('#'):
            continue
        spec = entry.split(' --hash=', 1)[0].strip()
        hashes = re.findall(r'--hash=sha256:([0-9a-f]{64})(?:\s|$)', entry)
        if not hashes:
            raise RuntimeError(f'Missing SHA256: {profile}: {spec}')
        if re.match(r'(?i)^(nvidia-|triton[= ])', spec):
            raise RuntimeError(f'Unexpected GPU dependency: {spec}')
        if spec.startswith('/mnt/g/Browser_Meme/'):
            wheel = root / spec.removeprefix('/mnt/g/Browser_Meme/')
            with wheel.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest not in hashes:
                raise RuntimeError(f'Local build differs from the dependency lock: {wheel.name}')
            local_wheels += 1
        elif spec.startswith('torch @ '):
            if 'torch-2.8.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl' not in spec:
                raise RuntimeError('Expected the fixed CPU-only Linux Python 3.12 torch wheel.')
        elif not re.match(r'^[A-Za-z0-9_.-]+==[^\s]+$', spec):
            raise RuntimeError(f'Unpinned or unsupported requirement: {spec}')
        entries.append(spec)
    if profile == 'webchore' and local_wheels != 4:
        raise RuntimeError('Expected all four locally built WebChoreArena BrowserGym packages.')
    expected_playwright = '1.50.0' if profile == 'webchore' else '1.44.0'
    if f'playwright=={expected_playwright}' not in entries:
        raise RuntimeError(f'Unexpected Playwright version for {profile}.')
    report[profile] = {'packages': len(entries), 'local_wheels_verified': local_wheels,
                       'lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest()}

report['status'] = 'passed'
report['scope'] = 'Dependency pins and local wheel hashes only; downloads and runtime imports are separate checks.'
destination = root / '.runtime/logs/download-plan-check.json'
destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
