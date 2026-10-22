"""Scan only the independently frozen runtime publication inventory."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import zipfile
from harness.phase2_isolation.publication_scan_v001 import ROOT, EXP, PATTERNS, PROHIBITED


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()


def main():
    inventory=ROOT/'harness/publication/phase2_20261022/runtime-evidence-inventory-002.json'
    assert digest(inventory)=='7183e27476162638689448a018efce2569d2ddb3f997ce75825d97c4d2ea73a3'
    data=json.loads(inventory.read_text(encoding='utf-8'));findings=[];errors=[];counts=Counter()
    def scan(stream,label):
        carry=b'';hits=set()
        while chunk:=stream.read(1024*1024):
            b=carry+chunk;hits.update(k for k,p in PATTERNS.items() if p.search(b));carry=b[-8192:]
        for k in hits:findings.append({'path':label,'category':k,'publication_blocked_pending_export_review':True})
    for entry in data['entries']:
        path=Path(entry['source_path']);label=entry['source_repo_relative_path']
        if path.name.lower() in PROHIBITED or path.suffix.lower()=='.env':
            findings.append({'path':label,'category':'authentication_storage_exclude_without_reading','publication_blocked_pending_export_review':True});continue
        try:
            assert path.resolve().is_relative_to(ROOT.resolve()) and not path.is_symlink()
            assert path.stat().st_size==entry['bytes'] and digest(path)==entry['sha256']
            counts['inventory_hashes_verified']+=1
            if path.suffix.lower()=='.zip':
                counts['zip_files']+=1
                with zipfile.ZipFile(path) as z:
                    for m in z.infolist():
                        if m.is_dir():continue
                        if Path(m.filename).name.lower() in PROHIBITED:
                            findings.append({'path':label+'!'+m.filename,'category':'authentication_storage_exclude_without_reading','publication_blocked_pending_export_review':True});continue
                        with z.open(m) as f:scan(f,label+'!'+m.filename)
                        counts['zip_members_scanned']+=1
            else:
                with path.open('rb') as f:scan(f,label)
                counts['nonzip_files_scanned']+=1
        except (OSError,ValueError,RuntimeError,AssertionError,zipfile.BadZipFile) as error:errors.append({'path':label,'error_type':type(error).__name__})
        if counts['inventory_hashes_verified']%500==0:print(json.dumps({'runtime_files_verified':counts['inventory_hashes_verified'],'findings':len(findings)}),flush=True)
    result={'kind':'frozen_runtime_inventory_credential_scan','created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'pending_redacted_export_review','inventory_sha256':digest(inventory),'counts':dict(counts),'category_counts':dict(Counter(x['category'] for x in findings)),'findings':findings,'errors':errors,'real_authentication_storage_read':False,'matched_values_emitted':False,'originals_modified':False}
    out=EXP/'isolation/publication-runtime-credential-scan-001.json'
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'output':str(out),'counts':dict(counts),'category_counts':result['category_counts'],'errors':len(errors)}),flush=True)


if __name__=='__main__':main()
