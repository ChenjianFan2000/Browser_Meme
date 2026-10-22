"""Metadata-only final approval joining completed independent full scans.

Does not replace scans, edit pending records or silently waive any finding.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import argparse
import json
from harness.phase2_isolation import publication_export_audit_v002 as scanner
from harness.phase2_isolation import publication_findings_recheck_v002 as classification
from harness.phase2_isolation.publication_export_audit_parallel_v002 import unique_rows,canonical


SCANNER_SHA='29b5a88f087bcce759f2b626e9119170944d7fe2d78528771cfb28d7e0a076e4'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def ref(p):return {'path':str(Path(p).resolve()),'sha256':scanner.digest(p)}
def write_new(p,v):
 with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2);f.write('\n')


def verify_part(manifest_path,audit_path,recheck=None):
 manifest=read(manifest_path);digest=scanner.digest(manifest_path);rows=unique_rows(manifest['entries']);report=read(audit_path);findings=[];verified=0;refs=[ref(manifest_path),ref(audit_path)]
 if manifest.get('status')!='exported_pending_independent_approval' or manifest.get('failures'):raise ValueError('part_export_not_complete')
 if report.get('kind')=='actual_parallel_independent_export_stage_audit':
  if report['input_manifests_sha256'].get(str(Path(manifest_path).resolve()))!=digest or not report['input_manifests_stable_after_scan']:raise ValueError('part_parallel_binding_or_stability')
  union={}
  for item in report['shard_audits']:
   ap=Path(item['audit_path']);mp=Path(item['manifest_path'])
   if scanner.digest(ap)!=item['audit_sha256'] or scanner.digest(mp)!=item['manifest_sha256'] or item['exit_code']!=0:raise ValueError('part_shard_binding_or_exit')
   child=read(ap);part=read(mp);refs.extend([ref(ap),ref(mp)])
   if child['generator_sha256']!=SCANNER_SHA or child['pending_manifest_sha256']!=item['manifest_sha256'] or child.get('errors') or child['counts']['entries_verified']!=len(part['entries']):raise ValueError('part_shard_incomplete')
   for key,row in unique_rows(part['entries']).items():
    if key in union:raise ValueError('part_duplicate_scan_entry')
    union[key]=row
   findings.extend(child['findings']);verified+=child['counts']['entries_verified']
  if union!=rows:raise ValueError('part_full_entry_scan_union_differs')
 else:
  if report.get('kind')!='independent_actual_export_stage_audit' or report['pending_manifest_sha256']!=digest or report['generator_sha256']!=SCANNER_SHA or report.get('errors'):raise ValueError('part_single_binding_or_errors')
  findings=report['findings'];verified=report['counts']['entries_verified']
 if verified!=len(rows):raise ValueError('part_entry_scan_count_differs')
 if findings:
  if recheck is None:raise ValueError('unresolved_part_findings')
  c=read(recheck);refs.append(ref(recheck))
  if (c['generator_sha256']!=scanner.digest(Path(classification.__file__)) or c['status']!='partial_findings_resolved_not_publication_approval' or c['manifest']['sha256']!=digest or c['primary_summary']['sha256']!=scanner.digest(audit_path) or c['unresolved_entry_count']!=0 or not c['inputs_stable_after_recheck'] or c['entries_primary_full_scan_verified']!=verified):raise ValueError('classification_not_exact_completed_part')
  accounted=[];seen=set()
  for result in c['results']:
   key=result['archive_path']
   if key in seen or key not in rows:raise ValueError('classification_identity')
   seen.add(key);row=rows[key]
   if result['original_sha256']!=row['original_sha256'] or result['export_sha256']!=row['export_sha256']:raise ValueError('classification_entry_hash')
   if result['status'] not in {'exact_frozen_synthetic_fixture_field_only','exact_empty_historical_diagnostic_only'}:raise ValueError('classification_unresolved')
   accounted.extend(result['primary_findings'])
  if Counter(map(canonical,accounted))!=Counter(map(canonical,findings)):raise ValueError('classification_findings_coverage')
  for fixture in c['fixtures']:
   if scanner.digest(Path(fixture['path']))!=fixture['sha256']:raise ValueError('classification_fixture_drift')
  refs.extend(c['primary_audits'])
 return rows,refs,{'manifest_sha256':digest,'entry_count':verified,'primary_findings':len(findings),'findings_exactly_classified':bool(findings)}


def verify_final_coverage(final,inventory,original_inventory,original_export,parts):
 if final.get('status')!='exported_pending_independent_approval' or final.get('failures'):raise ValueError('final_export_incomplete')
 target=unique_rows(final['entries']);expected=unique_rows(inventory['entries']);baseline=unique_rows(original_inventory['entries']);union={}
 for part in parts:
  for key,row in part.items():
   if key in union:raise ValueError('cross_part_duplicate')
   union[key]=row
 if union!=target:raise ValueError('final_part_union_has_gap_extra_or_modified_dictionary')
 if set(target)!=set(expected):raise ValueError('final_inventory_coverage')
 for key,row in target.items():
  inv=expected[key]
  if row['original_source_path']!=inv['source_path'] or row['original_sha256']!=inv.get('expected_original_sha256'):raise ValueError('final_inventory_original_binding')
 for key,row in baseline.items():
  if key not in expected or any(expected[key].get(k)!=v for k,v in row.items()):raise ValueError('original_inventory_metadata_changed_or_missing')
 for key,row in unique_rows(original_export['entries']).items():
  if target.get(key)!=row:raise ValueError('original_success_dictionary_changed')
 sources={}
 for key,row in baseline.items():sources.setdefault(row['source_path'],[]).append(key)
 failed=[]
 for failure in original_export['failures']:
  keys=sources.get(failure['source_path'],[])
  if len(keys)!=1:raise ValueError('ambiguous_original_failure_identity')
  failed.extend(keys)
 original_success=set(unique_rows(original_export['entries']))
 if original_success&set(failed) or original_success|set(failed)!=set(baseline):raise ValueError('original_full_candidate_partition')
 if Counter(map(canonical,final.get('exclusions',[])))!=Counter(map(canonical,original_export.get('exclusions',[]))):raise ValueError('original_exclusions_changed_or_extended')
 return {'final_included':len(target),'original_candidates':len(baseline),'original_successes_unchanged':len(original_success),'original_failed_candidates_now_audited':len(failed),'supplemental_candidates_audited':len(target)-len(baseline),'parts':len(parts)}


def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--inventory',required=True);p.add_argument('--original-inventory',required=True);p.add_argument('--original-export',required=True);p.add_argument('--part-manifest',action='append',required=True);p.add_argument('--part-audit',action='append',required=True);p.add_argument('--findings-recheck');p.add_argument('--additional-audit',action='append',default=[]);p.add_argument('--output',required=True);p.add_argument('--approved-output',required=True);args=p.parse_args()
 if len(args.part_manifest)!=len(args.part_audit):raise ValueError('part_argument_count')
 if Path(args.output).exists() or Path(args.approved_output).exists():raise FileExistsError('exclusive_approval_outputs_required')
 if scanner.digest(Path(scanner.__file__))!=SCANNER_SHA:raise ValueError('fixed_scanner_changed')
 paths=[args.manifest,args.inventory,args.original_inventory,args.original_export,*args.part_manifest,*args.part_audit,*args.additional_audit]+([args.findings_recheck] if args.findings_recheck else []);snapshots={str(Path(p).resolve()):scanner.digest(p) for p in paths}
 final=read(args.manifest);inventory=read(args.inventory)
 if final['inventory_sha256']!=scanner.digest(args.inventory):raise ValueError('final_inventory_hash_binding')
 parts=[];evidence=[];summaries=[]
 for manifest_path,audit_path in zip(args.part_manifest,args.part_audit):
  candidate=read(args.findings_recheck) if args.findings_recheck else None
  match=args.findings_recheck if candidate and candidate['manifest']['sha256']==scanner.digest(manifest_path) else None
  rows,refs,summary=verify_part(manifest_path,audit_path,match);parts.append(rows);evidence+=refs;summaries.append(summary)
 coverage=verify_final_coverage(final,inventory,read(args.original_inventory),read(args.original_export),parts)
 final_rows=unique_rows(final['entries'])
 for path in args.additional_audit:
  extra=read(path)
  if extra.get('status')!='passed' or extra.get('scanner_sha256')!=SCANNER_SHA:raise ValueError('additional_audit_not_passed_or_fixed_scanner')
  for row in extra.get('entries',[]):
   if row['archive_path'] not in final_rows or row['export_sha256']!=final_rows[row['archive_path']]['export_sha256'] or row.get('findings'):raise ValueError('additional_audit_entry_differs_or_blocked')
  evidence.append(ref(path))
 if any(scanner.digest(Path(path))!=digest for path,digest in snapshots.items()):raise ValueError('metadata_input_drift')
 for item in evidence:
  if scanner.digest(Path(item['path']))!=item['sha256']:raise ValueError('audit_evidence_drift')
 approval={'kind':'actual_incremental_publication_approval','status':'passed','approved_at_utc':datetime.now(timezone.utc).isoformat(),'generator_sha256':scanner.digest(Path(__file__)),'scanner_sha256':SCANNER_SHA,'classification_sha256':scanner.digest(Path(classification.__file__)),'inputs':snapshots,'coverage':coverage,'parts':summaries,'evidence':evidence,'original_blocked_reports_preserved':True,'originals_modified':False,'all_payload_entries_independently_scanned':True,'scope':'Complete candidate inventory plus additions; pre-inventory excluded browser profiles/auth stores/cache remain explicitly recorded. Packager must revalidate every current export hash against this approved manifest.'}
 approved={**final,'status':'approved_for_publication','not_yet_approved_for_publication':False,'independent_approval':approval}
 write_new(args.approved_output,approved);approval['approved_manifest']={'path':str(Path(args.approved_output).resolve()),'sha256':scanner.digest(args.approved_output)};write_new(args.output,approval)
 print(json.dumps({'status':'passed','coverage':coverage,'approved':approval['approved_manifest'],'audit_sha256':scanner.digest(args.output)}),flush=True)


if __name__=='__main__':main()
