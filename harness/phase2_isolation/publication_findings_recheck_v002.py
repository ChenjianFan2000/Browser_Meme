"""Exact finding rechecks v002: frozen fixture scope and one pinned empty diagnostic capture.

Preserves the primary blocked reports. Does not approve any publication.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import json
import re
from harness.phase2_isolation import publication_export_audit_v002 as audit


ROOT=Path(__file__).resolve().parents[2]
EXPERIMENT='harness/experiments/phase2-discogs-20261021-01'
FIXED_SCANNER_SHA='29b5a88f087bcce759f2b626e9119170944d7fe2d78528771cfb28d7e0a076e4'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def norm(k):return re.sub('[^a-z0-9]','',str(k).casefold())


def load_fixtures(root):
 fixtures=[];evidence=[]
 for condition in 'ab':
  for seed in (1729,2718,3141):
   folder=root/EXPERIMENT/'runs'/f'{condition}-seed-{seed}'
   p=folder/'workspace/public-fixture.json';manifest_path=folder/'learning-manifest.json';manifest=read(manifest_path)['files'];digest=audit.digest(p)
   if manifest.get('workspace/public-fixture.json')!=digest:raise ValueError('fixture_not_bound_to_frozen_learning_manifest')
   value=read(p)
   if value.get('kind')!='public_fixture' or value.get('is_real_credential') is not False or set(value.get('account',{}))!={'username','password'} or not isinstance(value['account']['password'],str):raise ValueError('fixture_classification_schema_mismatch')
   fixtures.append(value);evidence.append({'path':str(p),'sha256':digest,'learning_manifest_sha256':audit.digest(manifest_path)})
 return fixtures,evidence


def password_scope(value,fixtures):
 known={canonical(v) for v in fixtures};passwords={v['account']['password'] for v in fixtures};counts={'exact_frozen_fixture_objects':0,'unscoped_equal_password_fields':0}
 def walk(v):
  if isinstance(v,dict):
   if canonical(v) in known:
    counts['exact_frozen_fixture_objects']+=1;return
   for key,child in v.items():
    if norm(key) in {'password','passwd','pwd'} and isinstance(child,str) and child in passwords:counts['unscoped_equal_password_fields']+=1
    walk(child)
  elif isinstance(v,list):
   for child in v:walk(child)
  elif isinstance(v,str) and v.lstrip()[:1] in ('{','['):
   try:child=json.loads(v)
   except (ValueError,RecursionError):return
   walk(child)
 walk(value);return counts


def recheck_entry(row,findings,root,tmpdir,fixtures):
 result={'archive_path':row['archive_path'],'original_sha256':row['original_sha256'],'export_sha256':row['export_sha256'],'primary_findings':findings,'status':'unresolved_blocking'}
 empty_path=EXPERIMENT+'/isolation/evaluation-generic-012.result.json'
 empty_sha='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
 if row['archive_path']==empty_path and row['original_source_path']==empty_path and row['original_size']==row['export_size']==0 and row['original_sha256']==row['export_sha256']==empty_sha and len(findings)==1 and findings[0]['path']==empty_path and findings[0]['category']=='required_structured_parse_failure':
  current,_=audit.audit_entry(row,root,tmpdir,set())
  if current==findings:
   result['status']='exact_empty_historical_diagnostic_only';result['reason']='Exactly pinned zero-byte historical generic stdout attachment; no content and not valid scoring JSON. Original empty artifact preserved.'
  return result

 if any(f['category']!='sensitive_credential_field' or f['path']!=row['archive_path'] for f in findings):
  result['reason']='not_an_exact_standalone_credential_field_finding';return result
 if Path(row['archive_path']).name not in {'job.json','public-fixture.json'}:
  result['reason']='requires_separate_nonfixture_artifact_review';return result
 passwords={v['account']['password'] for v in fixtures}
 remaining,members=audit.audit_entry(row,root,tmpdir,passwords)
 result['secondary_findings']=remaining
 if remaining:result['reason']='other_password_token_cookie_or_structural_finding_remains';return result
 value=read(root/row['source_path']);scope=password_scope(value,fixtures);result['scope_counts']=scope
 if scope['unscoped_equal_password_fields'] or not scope['exact_frozen_fixture_objects']:
  result['reason']='synthetic_value_outside_exact_frozen_fixture_object';return result
 result['status']='exact_frozen_synthetic_fixture_field_only'
 result['reason']='Primary scanner read nonexistent top-level password; actual schema is account.password. Full entry and original/export hashes independently rechecked; only exact frozen public_fixture object qualifies.'
 return result


def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--audit-directory',required=True);p.add_argument('--output',required=True);p.add_argument('--root',default=str(ROOT));p.add_argument('--workers',type=int,default=4);args=p.parse_args()
 root=Path(args.root).resolve();manifest_path=Path(args.manifest);manifest=read(manifest_path);manifest_sha=audit.digest(manifest_path);entries={r['archive_path']:r for r in manifest['entries']};directory=Path(args.audit_directory)
 if audit.digest(Path(audit.__file__))!=FIXED_SCANNER_SHA:raise ValueError('fixed_primary_scanner_changed')
 summary=read(directory/'audit-summary.json');primary_refs=[];all_findings=[];verified=0
 if summary['input_manifests_sha256'].get(str(manifest_path.resolve()))!=manifest_sha:raise ValueError('primary_summary_does_not_bind_exact_partial_manifest')
 for item in summary['shard_audits']:
  ap=Path(item['audit_path'])
  if audit.digest(ap)!=item['audit_sha256']:raise ValueError('primary_audit_hash_changed')
  value=read(ap)
  if item['exit_code']!=0 or value.get('errors') or value['generator_sha256']!=FIXED_SCANNER_SHA or value['pending_manifest_sha256']!=item['manifest_sha256']:raise ValueError('primary_audit_incomplete_or_not_fixed_scanner')
  primary_refs.append({'path':str(ap),'sha256':audit.digest(ap)});all_findings.extend(value['findings']);verified+=value['counts']['entries_verified']
 if verified!=len(entries) or not summary['input_manifests_stable_after_scan']:raise ValueError('primary_full_entry_scan_not_complete')
 grouped={}
 for f in all_findings:
  key=f['path'].split('!',1)[0]
  if key not in entries:raise ValueError('finding_not_bound_to_manifest_entry')
  grouped.setdefault(key,[]).append(f)
 fixtures,evidence=load_fixtures(root);tmp=root/'.runtime/publication-phase2-20261022/audit-tmp';tmp.mkdir(parents=True,exist_ok=True);results=[]
 with ThreadPoolExecutor(max_workers=args.workers) as pool:
  futures=[pool.submit(recheck_entry,entries[key],findings,root,tmp,fixtures) for key,findings in grouped.items()]
  for f in as_completed(futures):results.append(f.result())
 unresolved=[r for r in results if r['status'] not in {'exact_frozen_synthetic_fixture_field_only','exact_empty_historical_diagnostic_only'}];stable=audit.digest(manifest_path)==manifest_sha and all(audit.digest(Path(r['path']))==r['sha256'] for r in primary_refs)
 output={'kind':'exact_scoped_findings_recheck_v002','generator_sha256':audit.digest(Path(__file__)),'status':'partial_findings_resolved_not_publication_approval' if not unresolved and stable else 'unresolved_blocking','scope':'PARTIAL_NOT_APPROVAL','created_at_utc':datetime.now(timezone.utc).isoformat(),'manifest':{'path':str(manifest_path),'sha256':manifest_sha},'primary_summary':{'path':str(directory/'audit-summary.json'),'sha256':audit.digest(directory/'audit-summary.json')},'primary_audits':primary_refs,'fixed_scanner_sha256':FIXED_SCANNER_SHA,'fixtures':evidence,'entries_primary_full_scan_verified':verified,'primary_finding_count':len(all_findings),'finding_entries_rechecked':len(results),'unresolved_entry_count':len(unresolved),'inputs_stable_after_recheck':stable,'results':sorted(results,key=lambda r:r['archive_path']),'primary_blocked_reports_modified':False,'publication_approved':False,'values_emitted':False,'limitations':['Only exact, hash-bound frozen fixture objects are admitted for this finding classification. Other passwords/tokens/cookies remain blocking. Only the separately pinned zero-byte generic diagnostic attachment receives empty-format classification; no other JSON emptiness is waived.','Final original inventory coverage, failed-export retries, supplemental publication metadata scans and strict complete union still required.']}
 with Path(args.output).open('x',encoding='utf-8') as f:json.dump(output,f,indent=2)
 print(json.dumps({'output':args.output,'status':output['status'],'primary_findings':len(all_findings),'rechecked_entries':len(results),'unresolved_entries':len(unresolved)}),flush=True)


if __name__=='__main__':main()
