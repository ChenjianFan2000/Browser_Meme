"""Restore pinned GitHub MCP source payloads; verify Git blob SHA-1.

No remote code is executed. Payload content is accepted as UTF-8 only when its
Git object hash matches; base64 is tried separately rather than trusting metadata.
"""
from pathlib import Path
import base64, hashlib, json, zipfile, ast, sys, re

ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = ROOT / 'artifacts' / 'source_downloads'
BINARY = re.compile(r'\.(png|jpg|jpeg|gif|webp|pdf|svg|mp4|ico|npy|npz|pkl|pickle|gz|zip|pt|pth|safetensors|woff2?|ttf|otf|apk|jar|keystore|jks|class|so|aab|psd|DS_Store|pyc|bz2|7z|db|sqlite)$', re.I)

def git_hash(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def restore():
    records = []
    for payload in sorted(PAYLOADS.glob('payload-*.json')):
        for item in json.loads(payload.read_text(encoding='utf-8')):
            meta, obj = item['meta'], item['file']
            record = {**meta, 'path': obj['path'], 'blob_sha': obj['sha']}
            repo_root = ROOT / meta.get('local_root', 'external/' + meta['repo'])
            path = repo_root / obj['path']
            if repo_root.resolve() not in path.resolve().parents:
                raise ValueError('Unsafe repository path: ' + obj['path'])
            raw = obj.get('content', '')
            candidates = [raw.encode('utf-8')]
            try:
                candidates.append(base64.b64decode(raw, validate=False))
            except Exception:
                pass
            data = next((x for x in candidates if git_hash(x) == obj['sha']), None)
            if data is None:
                record['status'] = 'hash_mismatch_or_missing_content'
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                record.update(status='downloaded_verified', bytes=len(data), local_path=str(path.relative_to(ROOT)).replace('\\', '/'))
            records.append(record)
    state_path = PAYLOADS / 'repository_inventory.json'
    states = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else []
    submodule_path = PAYLOADS / 'repository_submodules.json'
    if submodule_path.exists():
        states += json.loads(submodule_path.read_text(encoding='utf-8'))
    report = {'acquisition': 'GitHub MCP contents at immutable commit; restored locally with Git blob SHA1 verification', 'repositories': states, 'files': records,
              'user_archive': {'name': 'VeriEnv-main.zip', 'sha256': 'a6a8159d89849bc82b53a437c1d6ed6492ae4dd8ba138ce1358bc58d81950a96', 'unpacked_entries': 1205, 'modified': False}}
    by_key = {(r['repo'], r['path']): r for r in records}
    for state in states:
        license_paths = []
        for item in state.get('files', []):
            restored = by_key.get((state['repo'], item['path']))
            if restored:
                item['status'] = restored['status']
            elif item.get('type') == 'commit':
                expanded = next((s for s in states if s.get('parent') == state['repo'] and s['repo'] == item['path'] and s['commit'] == item['sha']), None)
                item.update(status='expanded_submodule' if expanded else 'excluded_submodule', reason='Pinned gitlink content downloaded separately.' if expanded else 'External git submodule is not embedded in this pinned tree; pin recorded in sha.')
            elif BINARY.search(item['path']):
                item.update(status='excluded_asset', reason='Binary, rendered media, font, archive, checkpoint, or database asset; outside source-only download scope.')
            elif item.get('size', 0) > 1000000:
                item.update(status='excluded_large_data', reason='Blob exceeds 1 MB; dataset/lockfile asset retained in remote inventory.')
            else:
                item.update(status='pending_or_fetch_error', reason='Not yet restored; see acquisition log.')
            if re.search(r'(^|/)(license[^/]*|copying[^/]*)$', item['path'], re.I):
                license_paths.append(item['path'])
        state['license_paths'] = license_paths
        state['counts'] = {status: sum(f['status'] == status for f in state['files']) for status in sorted({f['status'] for f in state['files']})}
        state['source_complete'] = not any(f['status'] == 'pending_or_fetch_error' for f in state['files'])
        if not license_paths:
            state['license_status'] = 'No standalone license file found in pinned tree; inspect README declarations.'
        repo_root = ROOT / state.get('local_root', 'external/' + state['repo'])
        if repo_root.is_dir():
            destination = PAYLOADS / (state['repo'] + '-' + state['commit'][:12] + '-source.zip')
            with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as zf:
                verified_paths = {ROOT / r['local_path'] for r in records if r['status'] == 'downloaded_verified' and repo_root.resolve() in (ROOT / r['local_path']).resolve().parents}
                for path in sorted(verified_paths):
                    zf.write(path, str(path.relative_to(repo_root.parent)))
            state['archive'] = str(destination.relative_to(ROOT)).replace('\\', '/')
            state['archive_sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
    (ROOT / 'SOURCE_MANIFEST.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'downloaded': sum(r['status']=='downloaded_verified' for r in records), 'errors': [r for r in records if r['status']!='downloaded_verified'], 'repositories': len(states), 'pending': sum(s['counts'].get('pending_or_fetch_error', 0) for s in states)}, ensure_ascii=False))

if __name__ == '__main__': restore()
