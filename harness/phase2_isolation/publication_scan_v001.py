"""Read-only publication credential triage. Never emit matched values."""
from pathlib import Path
from collections import Counter
import json
import re
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / 'harness/experiments/phase2-discogs-20261021-01'
PATTERNS = {
    'authorization_header_value': re.compile(rb'(?i)(?:"name"\s*:\s*"authorization"\s*,\s*"value"\s*:\s*"[^"\s]+|"authorization"\s*:\s*"(?:bearer|basic)\s+[^"\s]+)'),
    'cookie_header_value': re.compile(rb'(?i)"name"\s*:\s*"(?:cookie|set-cookie)"\s*,\s*"value"\s*:\s*"[^"\s]+'),
    'cookie_storage_entries': re.compile(rb'(?i)"cookies"\s*:\s*\[\s*\{'),
    'provider_key_shape': re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
    'jwt_shape': re.compile(rb'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
    'literal_password_or_secret_field': re.compile(rb'(?i)"(?:password|passwd|client_secret|access_token|refresh_token|api_key)"\s*:\s*"[^"\s]{3,}"'),
}
TEXT = {'.json', '.jsonl', '.network', '.trace', '.html', '.htm', '.md', '.txt', '.log', '.py', '.js', '.cjs', '.toml', '.yaml', '.yml', '.env', '.config'}
PROHIBITED = {'auth.json', 'credentials.json', 'research.env', 'id_rsa', 'id_ed25519', 'login data', 'cookies'}


def main():
    findings, errors, counts = [], [], Counter()
    def scan_stream(stream, label):
        hits = Counter()
        carry = b''
        while chunk := stream.read(1024 * 1024):
            data = carry + chunk
            for category, pattern in PATTERNS.items():
                if pattern.search(data): hits[category] += 1
            carry = data[-8192:]
        for category, n in hits.items():
            findings.append({'path': label, 'category': category, 'matched_chunks': n,
                             'publication_blocked_pending_classification_or_export_redaction': True})
    roots = [EXP, ROOT/'harness/phase2', ROOT/'harness/phase2_isolation', ROOT/'harness/sites/discogs/phase2_private']
    seen = set()
    for base in roots:
        for path in base.rglob('*'):
            if not path.is_file(): continue
            resolved = path.resolve()
            if resolved in seen: continue
            seen.add(resolved); counts['files_enumerated'] += 1
            label = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                findings.append({'path': label, 'category': 'symlink_export_requires_review', 'publication_blocked_pending_classification_or_export_redaction': True}); continue
            if path.name.lower() in PROHIBITED or path.suffix.lower() == '.env':
                findings.append({'path': label, 'category': 'authentication_storage_exclude_without_reading', 'publication_blocked_pending_classification_or_export_redaction': True}); counts['auth_stores_not_read'] += 1; continue
            try:
                if path.suffix.lower() == '.zip':
                    counts['zip_files'] += 1
                    with zipfile.ZipFile(path) as archive:
                        for entry in archive.infolist():
                            if entry.is_dir(): continue
                            counts['zip_members'] += 1
                            member = Path(entry.filename)
                            if member.name.lower() in PROHIBITED:
                                findings.append({'path': label+'!'+entry.filename, 'category': 'authentication_storage_exclude_without_reading', 'publication_blocked_pending_classification_or_export_redaction': True}); continue
                            if member.suffix.lower() in TEXT or member.name in {'trace.trace','trace.network'}:
                                with archive.open(entry) as stream: scan_stream(stream, label+'!'+entry.filename)
                                counts['zip_text_members_scanned'] += 1
                elif path.suffix.lower() in TEXT or (not path.suffix and path.stat().st_size < 2*1024*1024):
                    with path.open('rb') as stream: scan_stream(stream,label)
                    counts['text_files_scanned'] += 1
                else: counts['nontext_files_not_content_scanned'] += 1
            except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
                errors.append({'path':label,'error_type':type(error).__name__})
            if counts['files_enumerated'] % 10000 == 0: print(json.dumps({'progress_files':counts['files_enumerated'],'findings':len(findings)}),flush=True)
    output = EXP/'isolation/publication-credential-scan-001.json'
    result = {'kind':'read_only_publication_credential_triage','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'publication_blocked_pending_export_review' if findings or errors else 'no_pattern_findings',
        'scope_roots':[p.relative_to(ROOT).as_posix() for p in roots], 'counts':dict(counts),
        'category_counts':dict(Counter(x['category'] for x in findings)), 'findings':findings,'errors':errors,
        'matched_values_emitted':False,'real_authentication_stores_read':False,'originals_modified':False,
        'limitations':['Pattern triage is not proof all secrets absent. Binary image/PDF/cache contents require separate export treatment.','Runtime referenced evidence outside these roots not included; inventory and supplementary scan required.','Local synthetic site cookies still count as authentication material until classification; original frozen evidence is never edited.']}
    with output.open('x',encoding='utf-8') as stream: json.dump(result,stream,indent=2)
    print(json.dumps({'output':str(output),'counts':dict(counts),'category_counts':result['category_counts'],'errors':len(errors)}),flush=True)


if __name__ == '__main__': main()
