"""Deterministic generic integrity checks; run on Linux for real symlinks."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/opt/browser-meme/tmp/phase2-isolation-audit/records-append-018')
checks = {}


def setup(name):
    root = ROOT / name
    public = root / 'workspace/evidence/call-001-neutral/obs.json'
    private = root / 'private/call-001-neutral/evidence/obs.json'
    public.parent.mkdir(parents=True, exist_ok=False)
    private.parent.mkdir(parents=True, exist_ok=False)
    private.write_text('{"generic":true}')
    public.write_bytes(private.read_bytes())
    digest = hashlib.sha256(private.read_bytes()).hexdigest()
    (private.parent.parent / 'public-evidence-hashes.json').write_text(json.dumps({'obs.json': digest}))
    rule = {'id': 'generic', 'status': 'verified', 'evidence_refs': [{'path': 'evidence/call-001-neutral/obs.json', 'sha256': digest}]}
    return root / 'workspace', root / 'private', public, private, rule


def reject(name, mutation):
    workspace, private, public, original, rule = setup(name)
    mutation(workspace, private, public, original, rule)
    try:
        validate_browser_exports(workspace, private, [rule])
    except (ValueError, OSError) as error:
        checks[name] = {'passed': True, 'actual_error': type(error).__name__ + ': ' + str(error)}
    else:
        checks[name] = {'passed': False, 'reason': 'unexpected acceptance'}


workspace, private, public, original, rule = setup('positive')
checks['matching_original'] = {'passed': validate_browser_exports(workspace, private, [rule])['rules_with_original_evidence'] == 1}
reject('public_tamper', lambda w, p, f, o, r: f.write_text('tampered'))
reject('private_original_tamper', lambda w, p, f, o, r: o.write_text('tampered'))
reject('extra_export', lambda w, p, f, o, r: (f.parent / 'author-extra.json').write_text('{}'))
reject('missing_export', lambda w, p, f, o, r: f.unlink())


def author_only(workspace, private, public, original, rule):
    note = workspace / 'author-note.json'
    note.write_text('{}')
    rule['evidence_refs'] = [{'path': 'author-note.json', 'sha256': hashlib.sha256(note.read_bytes()).hexdigest()}]


reject('verified_author_only', author_only)
reject('refuted_author_only', lambda w, p, f, o, r: (author_only(w, p, f, o, r), r.update(status='refuted')))


def file_symlink(w, p, f, o, r):
    target = w / 'ordinary-copy.json'; target.write_bytes(f.read_bytes())
    f.unlink(); f.symlink_to(target)


def child_symlink(w, p, f, o, r):
    (w / 'evidence/linked-directory').symlink_to(p, target_is_directory=True)


def root_symlink(w, p, f, o, r):
    old = w / 'evidence'; moved = w / 'evidence-copy'
    old.rename(moved); old.symlink_to(moved, target_is_directory=True)


reject('file_symlink', file_symlink)
reject('child_directory_symlink', child_symlink)
reject('root_directory_symlink', root_symlink)
workspace, private, public, original, rule = setup('hypothesis')
author_only(workspace, private, public, original, rule)
rule['status'] = 'hypothesis'
checks['hypothesis_without_verified_claim'] = {'passed': validate_browser_exports(workspace, private, [rule])['rules_with_original_evidence'] == 0}
result = {'status': 'passed' if all(row['passed'] for row in checks.values()) else 'failed', 'checks': checks}
print(json.dumps(result))
assert result['status'] == 'passed'
