"""Eight-process orchestration around the fixed independent export auditor."""
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import sys
from harness.phase2_isolation.publication_export_audit_v001 import safe_relative


ROOT=Path(__file__).resolve().parents[2]
SCANNER=ROOT/'harness/phase2_isolation/publication_export_audit_v001.py'
SCANNER_SHA='4ad0a508ac07284d920d8666739dce40c300b473d96799b7ba9eda963c94a7e3'


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def write_new(p,v):
 with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2);f.write('\n')


def unique_rows(rows):
 mapping={}
 for row in rows:
  key=safe_relative(row['archive_path']).as_posix()
  if key in mapping:raise ValueError('duplicate_archive_identity')
  mapping[key]=row
 return mapping


def check_union(final,shards,inventory,inventory_sha):
 if final.get('schema_version')!=1 or final.get('status')!='exported_pending_independent_approval' or final.get('failures'):raise ValueError('invalid_final_pending_manifest')
 if final.get('inventory_sha256')!=inventory_sha:raise ValueError('original_inventory_hash_binding')
 merged=unique_rows(final['entries']);union={}
 for shard in shards:
  if shard.get('status')!='exported_pending_independent_approval' or shard.get('failures'):raise ValueError('invalid_shard_manifest')
  for key,row in unique_rows(shard['entries']).items():
   if key in union:raise ValueError('cross_shard_duplicate')
   union[key]=row
 if canonical(union)!=canonical(merged):raise ValueError('shard_union_differs_from_final_entries')
 expected=unique_rows(inventory['entries']);excluded={}
 for row in final.get('exclusions',[]):
  key=row.get('archive_path')
  if key is None:continue  # Explicit pre-inventory pruned roots are not candidate entries.
  key=safe_relative(key).as_posix()
  if key in excluded:raise ValueError('duplicate_exclusion_identity')
  excluded[key]=row
 if set(merged)&set(excluded):raise ValueError('included_and_excluded_overlap')
 if set(merged)|set(excluded)!=set(expected):raise ValueError('original_inventory_coverage_gap_or_extra')
 for key,row in merged.items():
  if row['original_source_path']!=expected[key]['source_path']:raise ValueError('original_source_mapping_differs_from_inventory')
  bound=expected[key].get('expected_original_sha256')
  if bound is not None and row['original_sha256']!=bound:raise ValueError('inventory_original_hash_differs')
 for key,row in excluded.items():
  if row.get('source_path')!=expected[key]['source_path'] or row.get('content_read_or_hashed') is not False:raise ValueError('exclusion_mapping_or_no_read_proof_differs')
 shard_exclusions=[row for shard in shards for row in shard.get('exclusions',[]) if row.get('archive_path')]
 if sorted(map(canonical,shard_exclusions))!=sorted(map(canonical,[r for r in final.get('exclusions',[]) if r.get('archive_path')])):raise ValueError('shard_exclusion_union_differs')
 return {'included_entries':len(merged),'candidate_exclusions':len(excluded),'inventory_candidates':len(expected),'shards':len(shards)}


def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--inventory',required=True);p.add_argument('--shard',action='append',required=True);p.add_argument('--output-directory',required=True);p.add_argument('--root',default=str(ROOT));p.add_argument('--processes',type=int,default=8);p.add_argument('--approved-output');args=p.parse_args()
 if not 1<=args.processes<=8 or not 1<=len(args.shard)<=8:raise ValueError('maximum_eight_processes_and_shards')
 root=Path(args.root).resolve();manifest=Path(args.manifest).resolve();inventory_path=Path(args.inventory).resolve();shard_paths=[Path(x).resolve() for x in args.shard]
 if len(shard_paths)!=len(set(shard_paths)):raise ValueError('duplicate_shard_path')
 if sha(SCANNER)!=SCANNER_SHA:raise ValueError('fixed_auditor_source_changed')
 snapshots={str(p):sha(p) for p in [manifest,inventory_path,*shard_paths]};final=read(manifest);shards=[read(p) for p in shard_paths];inventory=read(inventory_path)
 coverage=check_union(final,shards,inventory,snapshots[str(inventory_path)])
 destination=Path(args.output_directory).resolve();destination.mkdir(parents=True,exist_ok=False)
 def one(index,path):
  audit=destination/f'shard-{index:02d}.audit.json';stdout=destination/f'shard-{index:02d}.stdout.jsonl';stderr=destination/f'shard-{index:02d}.stderr.txt'
  command=[sys.executable,'-u','-m','harness.phase2_isolation.publication_export_audit_v001','--manifest',str(path),'--output',str(audit),'--root',str(root),'--workers','1']
  with stdout.open('xb') as out,stderr.open('xb') as err:
   child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=0x08000000 if sys.platform=='win32' else 0)
   print(json.dumps({'event':'independent_audit_process_started','shard':index,'pid':child.pid}),flush=True);code=child.wait()
  value=read(audit) if audit.is_file() else None
  okay=(code==0 and value is not None and value.get('status')=='checks_passed_pending_explicit_approval' and value.get('pending_manifest_sha256')==snapshots[str(path)] and value.get('generator_sha256')==SCANNER_SHA and value.get('counts',{}).get('entries_verified')==len(shards[index-1]['entries']) and not value.get('findings') and not value.get('errors'))
  print(json.dumps({'event':'independent_audit_process_finished','shard':index,'exit_code':code,'passed':okay}),flush=True)
  return {'shard':index,'manifest_path':str(path),'manifest_sha256':snapshots[str(path)],'audit_path':str(audit),'audit_sha256':sha(audit) if audit.is_file() else None,'exit_code':code,'passed':okay}
 results=[]
 with ThreadPoolExecutor(max_workers=args.processes) as pool:
  futures=[pool.submit(one,i,p) for i,p in enumerate(shard_paths,1)]
  for f in as_completed(futures):results.append(f.result())
 stable=all(sha(Path(p))==digest for p,digest in snapshots.items())
 passed=stable and all(r['passed'] for r in results) and len(results)==len(shard_paths)
 output={'kind':'actual_parallel_independent_export_stage_audit','status':'passed' if passed else 'blocked','completed_at_utc':datetime.now(timezone.utc).isoformat(),'coverage':coverage,'fixed_auditor_sha256':SCANNER_SHA,'input_manifests_sha256':snapshots,'input_manifests_stable_after_scan':stable,'shard_audits':sorted(results,key=lambda r:r['shard']),'processes_limit':args.processes,'each_scanner_workers':1,'scan_reduction':False,'approved_manifest_written':False,'matched_values_emitted':False}
 if args.approved_output:
  if not passed:raise ValueError('cannot_approve_incomplete_or_blocked_audit')
  approved={**final,'status':'approved_for_publication','not_yet_approved_for_publication':False,'independent_approval':{'auditor_source_sha256':sha(Path(__file__)),'scanner_source_sha256':SCANNER_SHA,'pending_manifest_sha256':snapshots[str(manifest)],'inventory_sha256':snapshots[str(inventory_path)],'shard_audits':[{'path':r['audit_path'],'sha256':r['audit_sha256']} for r in results],'approved_at_utc':datetime.now(timezone.utc).isoformat()}}
  write_new(args.approved_output,approved);output['approved_manifest_written']=True;output['approved_manifest']={'path':str(Path(args.approved_output).resolve()),'sha256':sha(args.approved_output)}
 write_new(destination/'audit-summary.json',output)
 print(json.dumps({'status':output['status'],'summary':str(destination/'audit-summary.json'),'sha256':sha(destination/'audit-summary.json'),'approved_manifest':output.get('approved_manifest')}),flush=True)


if __name__=='__main__':main()
