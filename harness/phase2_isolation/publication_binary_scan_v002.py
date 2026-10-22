"""Nontext credential byte scan with literal prefilters; never OCR or emit values."""
from collections import Counter
from datetime import datetime, timezone
import json
from harness.phase2_isolation.publication_scan_v001 import ROOT, EXP, PATTERNS, TEXT, PROHIBITED


def candidates(data):
    if b'eyJ' in data:yield 'jwt_shape'
    if b'sk-' in data:yield 'provider_key_shape'
    lower=data.lower()
    if b'authorization' in lower:yield 'authorization_header_value'
    if b'cookie' in lower:
        yield 'cookie_header_value'
        yield 'cookie_storage_entries'
    if any(k in lower for k in [b'password',b'passwd',b'client_secret',b'access_token',b'refresh_token',b'api_key']):yield 'literal_password_or_secret_field'


def main():
    counts=Counter();findings=[];errors=[]
    for base in [EXP,ROOT/'harness/phase2',ROOT/'harness/phase2_isolation',ROOT/'harness/sites/discogs/phase2_private']:
        for p in base.rglob('*'):
            if not p.is_file() or p.suffix.lower() in TEXT|{'.zip'} or (not p.suffix and p.stat().st_size<2*1024*1024):continue
            if p.name.lower() in PROHIBITED or p.is_symlink():continue
            label=p.relative_to(ROOT).as_posix();carry=b'';hits=set()
            try:
                with p.open('rb') as f:
                    while chunk:=f.read(1024*1024):
                        b=carry+chunk;counts['bytes_scanned']+=len(chunk);hits.update(k for k in candidates(b) if PATTERNS[k].search(b));carry=b[-8192:]
                counts['files_scanned']+=1
                for k in hits:findings.append({'path':label,'category':k,'publication_blocked_pending_export_review':True})
            except OSError as error:errors.append({'path':label,'error_type':type(error).__name__})
            if counts['files_scanned']%5000==0:print(json.dumps({'binary_files_scanned':counts['files_scanned'],'findings':len(findings)}),flush=True)
    out={'kind':'nontext_binary_credential_byte_pattern_supplement','scanner_version':2,'created_at_utc':datetime.now(timezone.utc).isoformat(),'counts':dict(counts),'findings':findings,'errors':errors,'category_counts':dict(Counter(x['category'] for x in findings)),'scope':'Raw byte patterns only; not OCR or exhaustive visual secret detection. Literal prefilters preserve each regex necessary literal.','originals_modified':False,'real_authentication_storage_read':False}
    p=EXP/'isolation/publication-binary-credential-scan-002.json'
    with p.open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'output':str(p),'counts':dict(counts),'findings':len(findings),'errors':len(errors)}),flush=True)


if __name__=='__main__':main()
