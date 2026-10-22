"""Supplement text scan with opaque ZIP resources; emit no payload values."""
from pathlib import Path
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from harness.phase2_isolation.publication_scan_v001 import ROOT, EXP, TEXT, PROHIBITED, PATTERNS


def main():
    findings, errors, counts = [], [], Counter()
    for base in [EXP,ROOT/'harness/phase2',ROOT/'harness/phase2_isolation',ROOT/'harness/sites/discogs/phase2_private']:
        for path in base.rglob('*.zip'):
            counts['zip_files'] += 1
            try:
                with zipfile.ZipFile(path) as z:
                    for member in z.infolist():
                        p=Path(member.filename)
                        if member.is_dir() or p.name.lower() in PROHIBITED or p.suffix.lower() in TEXT or p.name in {'trace.trace','trace.network'}: continue
                        counts['additional_members_scanned'] += 1
                        hits=set();carry=b''
                        with z.open(member) as stream:
                            while chunk:=stream.read(1024*1024):
                                data=carry+chunk
                                hits.update(k for k,pattern in PATTERNS.items() if pattern.search(data))
                                carry=data[-8192:]
                        for category in hits:findings.append({'path':path.relative_to(ROOT).as_posix()+'!'+member.filename,'category':category,'publication_blocked_pending_classification_or_export_redaction':True})
            except (OSError,ValueError,RuntimeError,zipfile.BadZipFile) as error:errors.append({'path':path.relative_to(ROOT).as_posix(),'error_type':type(error).__name__})
            if counts['zip_files']%100==0:print(json.dumps({'zip_progress':counts['zip_files'],'additional_findings':len(findings)}),flush=True)
    out={'kind':'opaque_zip_resource_credential_pattern_supplement','created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'pending_export_review','counts':dict(counts),'category_counts':dict(Counter(x['category'] for x in findings)),'findings':findings,'errors':errors,'matched_values_emitted':False,'auth_storage_read':False,'originals_modified':False}
    p=EXP/'isolation/publication-zip-resources-scan-001.json'
    with p.open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'output':str(p),'counts':dict(counts),'category_counts':out['category_counts'],'errors':len(errors)}),flush=True)


if __name__=='__main__':main()
