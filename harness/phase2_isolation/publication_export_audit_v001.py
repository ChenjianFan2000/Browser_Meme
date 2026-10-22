"""Independent staged-publication inventory/hash/credential audit. No approval mutation."""
from pathlib import Path, PurePosixPath
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import argparse
import base64
import hashlib
import io
import json
import re
import tempfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[2]
AUTH_NAMES={'auth.json','credentials.json','research.env','id_rsa','id_ed25519','cookies','login data'}
PLACEHOLDERS={'[REDACTED_AUTH]','[REDACTED]','<redacted>','REDACTED_AUTH',''}
RX={
 'jwt':re.compile(rb'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}'),
 'openai_key':re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
 'github_legacy_token':re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}'),
 'github_pat':re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{30,}'),
 'google_api_key':re.compile(rb'\bAIza[A-Za-z0-9_-]{30,}'),
 'aws_access_key':re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'private_key_material':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
}
PREFIX={'jwt':b'eyJ','openai_key':b'sk-','github_pat':b'github_pat_','google_api_key':b'AIza','private_key_material':b'PRIVATE KEY'}
SENSITIVE_HEADERS={'authorization','proxy-authorization','cookie','set-cookie','x-api-key','x-auth-token','x-csrf-token','x-xsrf-token'}
SENSITIVE_FIELDS={'password','passwd','access_token','refresh_token','client_secret','api_key'}


def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()


def safe_relative(value):
 p=PurePosixPath(value)
 if p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value or not p.parts:raise ValueError('unsafe_relative_path')
 return p


def inspect_stream(stream,label,*,synthetic_passwords=frozenset(),structured=True):
 hits=set();carry=b'';capture=bytearray();linecarry=b'';capture_limit=16*1024*1024;large=False
 def secret(value):return isinstance(value,str) and value not in PLACEHOLDERS
 def patterns(b):
  for key,rx in RX.items():
   prefix=PREFIX.get(key)
   if prefix is not None and prefix not in b:continue
   if key=='github_legacy_token' and not any(x in b for x in [b'ghp_',b'gho_',b'ghu_',b'ghs_',b'ghr_']):continue
   if key=='aws_access_key' and b'AKIA' not in b and b'ASIA' not in b:continue
   if rx.search(b):hits.add(key)
 def walk(v,depth=0):
  if depth>128:
   hits.add('structured_recursion_limit');return
  if isinstance(v,dict):
   if str(v.get('encoding','')).lower()=='base64':
    for field in ('text','data','body'):
     encoded=v.get(field)
     if isinstance(encoded,str):
      try:
       decoded=base64.b64decode(encoded,validate=True);patterns(decoded)
       try:inner=json.loads(decoded)
       except (ValueError,UnicodeDecodeError):continue
       walk(inner,depth+1)
      except (ValueError,TypeError):hits.add('unparsed_base64_encoded_content')
   name=v.get('name');value=v.get('value')
   if isinstance(name,str) and name.lower() in SENSITIVE_HEADERS and secret(value):hits.add('sensitive_header_value')
   for key,child in v.items():
    low=key.lower()
    if low in SENSITIVE_HEADERS and secret(child):hits.add('sensitive_header_value')
    if low in SENSITIVE_FIELDS and secret(child) and child not in synthetic_passwords:hits.add('sensitive_credential_field')
    if low=='cookies' and isinstance(child,list):
     for cookie in child:
      if isinstance(cookie,dict) and secret(cookie.get('value')):hits.add('cookie_storage_value')
    walk(child,depth+1)
  elif isinstance(v,list):
   for child in v:walk(child,depth+1)
  elif isinstance(v,str) and v[:1] in '{[':
   try:inner=json.loads(v)
   except (ValueError,RecursionError):return
   if inner!=v:walk(inner,depth+1)
 def try_json(b):
  try:walk(json.loads(b))
  except (ValueError,UnicodeDecodeError,RecursionError):pass
 while chunk:=stream.read(1024*1024):
  b=carry+chunk
  patterns(b)
  carry=b[-16384:]
  if structured:
   if len(capture)+len(chunk)<=capture_limit and not large:capture.extend(chunk)
   else:large=True;capture.clear()
   lines=(linecarry+chunk).split(b'\n');linecarry=lines.pop()
   for line in lines:
    if line[:1] in (b'{',b'['):try_json(line)
   if len(linecarry)>capture_limit:linecarry=b''
 if structured:
  if not large:try_json(bytes(capture))
  elif linecarry:try_json(linecarry)
 return [{'path':label,'category':key,'blocking':True} for key in sorted(hits)]


def scan_zip(archive,label,tmpdir,synthetic_passwords,depth=0):
 if depth>8:raise ValueError('nested_zip_depth_exceeded')
 findings=[];members=0
 with zipfile.ZipFile(archive) as z:
  for member in z.infolist():
   if member.is_dir():continue
   safe_relative(member.filename);name=PurePosixPath(member.filename).name.lower();where=label+'!'+member.filename
   if name in AUTH_NAMES or name.endswith('.env'):
    findings.append({'path':where,'category':'authentication_storage_member_exclude_without_reading','blocking':True});continue
   members+=1
   with z.open(member) as f:
    prefix=f.read(4);f.seek(0)
    if prefix in (b'PK\x03\x04',b'PK\x05\x06'):
     with tempfile.SpooledTemporaryFile(max_size=8*1024*1024,dir=tmpdir) as nested:
      while chunk:=f.read(1024*1024):nested.write(chunk)
      nested.seek(0);extra,n=scan_zip(nested,where,tmpdir,synthetic_passwords,depth+1);findings.extend(extra);members+=n
    else:findings.extend(inspect_stream(f,where,synthetic_passwords=synthetic_passwords,structured=True))
 return findings,members


def audit_entry(row,root,tmpdir,synthetic_passwords):
 rel=safe_relative(row['source_path']);archive=safe_relative(row['archive_path']);path=root.joinpath(*rel.parts)
 if path.name.lower() in AUTH_NAMES or path.suffix.lower()=='.env':raise ValueError('authentication_storage_no_read_no_hash')
 if not path.resolve(strict=True).is_relative_to(root.resolve()) or any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('symlink_or_uncontained_source')
 if path.stat().st_size!=row['export_size'] or digest(path)!=row['export_sha256']:raise ValueError('export_hash_or_size_mismatch')
 if row['treatment'] not in {'unchanged','redacted'}:raise ValueError('unknown_treatment')
 if row['treatment']=='unchanged' and (row['original_sha256']!=row['export_sha256'] or row['original_size']!=row['export_size']):raise ValueError('unchanged_mapping_differs')
 if row['treatment']=='redacted' and (row['source_path']==row['original_source_path'] or row['original_sha256']==row['export_sha256'] or not (any(row.get('redaction_counts',{}).values()) or row.get('archive_exclusions'))):raise ValueError('redaction_mapping_not_independent_or_unaccounted')
 original=root.joinpath(*safe_relative(row['original_source_path']).parts)
 if original.name.lower() in AUTH_NAMES or original.suffix.lower()=='.env':raise ValueError('authentication_original_no_read_no_hash')
 if not original.resolve(strict=True).is_relative_to(root.resolve()) or any(p.is_symlink() for p in [original,*original.parents]):raise ValueError('uncontained_original')
 if original.stat().st_size!=row['original_size'] or digest(original)!=row['original_sha256']:raise ValueError('original_mapping_hash_or_size_mismatch')
 with path.open('rb') as f:prefix=f.read(4)
 if prefix in (b'PK\x03\x04',b'PK\x05\x06'):
  findings,members=scan_zip(path,row['archive_path'],tmpdir,synthetic_passwords)
 else:
  code=path.suffix.lower() in {'.py','.js','.cjs','.ts','.tsx','.toml','.md'}
  with path.open('rb') as f:findings=inspect_stream(f,row['archive_path'],synthetic_passwords=synthetic_passwords,structured=not code)
  members=0
 return findings,members


def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--output',required=True);p.add_argument('--root',default=str(ROOT));p.add_argument('--workers',type=int,default=4);args=p.parse_args()
 root=Path(args.root).resolve();manifest=Path(args.manifest);data=json.loads(manifest.read_text(encoding='utf-8'));assert data['schema_version']==1 and data['status']=='exported_pending_independent_approval' and not data.get('failures')
 rows=data['entries'];archives=[r['archive_path'] for r in rows];assert len(archives)==len(set(archives))
 # Only independently classified, explicitly synthetic public fixtures supply this whitelist.
 synthetic=set()
 for fixture in (root/'harness/experiments/phase2-discogs-20261021-01/runs').glob('*/workspace/public-fixture.json'):
  v=json.loads(fixture.read_text(encoding='utf-8'))
  if v.get('is_real_credential') is False and isinstance(v.get('password'),str):synthetic.add(v['password'])
 tmpdir=root/'.runtime/publication-phase2-20261022/audit-tmp';tmpdir.mkdir(parents=True,exist_ok=True)
 findings=[];errors=[];counts=Counter();iterator=iter(rows);last_progress=time.monotonic();last_count=0
 with ThreadPoolExecutor(max_workers=args.workers) as pool:
  active={}
  while True:
   while len(active)<args.workers*2:
    try:row=next(iterator)
    except StopIteration:break
    active[pool.submit(audit_entry,row,root,tmpdir,frozenset(synthetic))]=row
   if not active:break
   done,_=wait(active,timeout=15,return_when=FIRST_COMPLETED)
   for future in done:
    row=active.pop(future)
    try:
     found,members=future.result();findings.extend(found);counts['zip_members_scanned']+=members;counts['entries_verified']+=1
    except Exception as error:errors.append({'path':row['archive_path'],'error_type':type(error).__name__,'category':str(error) if type(error) is ValueError else 'entry_audit_failed'})
   if time.monotonic()-last_progress>=15 or counts['entries_verified']-last_count>=1000:
    print(json.dumps({'entries_verified':counts['entries_verified'],'active':len(active),'findings':len(findings),'errors':len(errors)}),flush=True)
    last_progress=time.monotonic();last_count=counts['entries_verified']
 output={'kind':'independent_actual_export_stage_audit','status':'checks_passed_pending_explicit_approval' if not findings and not errors else 'blocked','observed_at_utc':datetime.now(timezone.utc).isoformat(),'pending_manifest_sha256':digest(manifest),'generator_sha256':digest(Path(__file__)),'entry_count':len(rows),'counts':dict(counts),'category_counts':dict(Counter(x['category'] for x in findings)),'findings':findings,'errors':errors,'exclusions':data.get('exclusions',[]),'auth_storage_read':False,'matched_values_emitted':False,'manifest_approval_mutated':False,'limitations':['Byte-pattern/structured credential scanning is not OCR.','Source regex definitions and split test-string expressions are not executed.','Any matched token remains blocking until independently classified; no values are printed.']}
 with Path(args.output).open('x',encoding='utf-8') as f:json.dump(output,f,indent=2)
 print(json.dumps({'output':args.output,'status':output['status'],'entries':len(rows),'findings':len(findings),'errors':len(errors)}),flush=True)


if __name__=='__main__':main()
