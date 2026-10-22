"""Synthetic union/coverage and real child-process tests, no formal publication."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest
from harness.phase2_isolation import publication_export_audit_parallel_v002 as runner


def fixture_rows():
 rows=[{'source_path':f'exports/{i}.json','original_source_path':f'originals/{i}.json','archive_path':f'results/{i}.json','original_sha256':str(i)*64,'export_sha256':str(i+2)*64} for i in (1,2)]
 inventory={'entries':[{'source_path':r['original_source_path'],'archive_path':r['archive_path']} for r in rows]}
 final={'schema_version':1,'status':'exported_pending_independent_approval','inventory_sha256':'bound','entries':rows,'exclusions':[]}
 shards=[{'status':'exported_pending_independent_approval','entries':[r],'exclusions':[]} for r in rows]
 return final,shards,inventory


def test_exact_union_and_original_inventory_coverage():
 final,shards,inventory=fixture_rows()
 assert runner.check_union(final,shards,inventory,'bound')['included_entries']==2


def test_cross_shard_duplicate_fails():
 final,shards,inventory=fixture_rows();shards[1]['entries']=[shards[0]['entries'][0]]
 with pytest.raises(ValueError,match='cross_shard_duplicate'):runner.check_union(final,shards,inventory,'bound')


def test_missing_shard_entry_and_mutated_entry_fail():
 final,shards,inventory=fixture_rows();shards[1]['entries']=[]
 with pytest.raises(ValueError,match='union_differs'):runner.check_union(final,shards,inventory,'bound')
 final,shards,inventory=fixture_rows();shards=copy.deepcopy(shards);shards[0]['entries'][0]['export_sha256']='f'*64
 with pytest.raises(ValueError,match='union_differs'):runner.check_union(final,shards,inventory,'bound')


def test_inventory_gap_and_wrong_original_mapping_fail():
 final,shards,inventory=fixture_rows();inventory['entries'].append({'source_path':'missing','archive_path':'missing'})
 with pytest.raises(ValueError,match='coverage_gap'):runner.check_union(final,shards,inventory,'bound')
 final,shards,inventory=fixture_rows();inventory['entries'][0]['source_path']='another'
 with pytest.raises(ValueError,match='source_mapping'):runner.check_union(final,shards,inventory,'bound')


def test_exclusions_union_and_no_read_proof_required():
 final,shards,inventory=fixture_rows();excluded={'source_path':'originals/auth.json','archive_path':'results/auth.json','content_read_or_hashed':False}
 inventory['entries'].append({'source_path':excluded['source_path'],'archive_path':excluded['archive_path']});final['exclusions']=[excluded];shards[0]['exclusions']=[excluded]
 assert runner.check_union(final,shards,inventory,'bound')['candidate_exclusions']==1
 shards[0]['exclusions']=[]
 with pytest.raises(ValueError,match='exclusion_union'):runner.check_union(final,shards,inventory,'bound')


def test_real_two_process_audit_and_exclusive_approval(tmp_path):
 assert runner.sha(runner.SCANNER)==runner.SCANNER_SHA
 original=tmp_path/'originals';exports=tmp_path/'exports';original.mkdir();exports.mkdir();rows=[]
 for i in range(2):
  src=original/f'{i}.json';dst=exports/f'{i}.json'
  src.write_text(json.dumps({'headers':[{'name':'Cookie','value':'synthetic-local-canary'}]}),encoding='utf-8')
  dst.write_text(json.dumps({'headers':[{'name':'Cookie','value':'[REDACTED_AUTH]'}]}),encoding='utf-8')
  rows.append({'source_path':dst.relative_to(tmp_path).as_posix(),'original_source_path':src.relative_to(tmp_path).as_posix(),'archive_path':f'results/{i}.json','original_sha256':runner.sha(src),'export_sha256':runner.sha(dst),'original_size':src.stat().st_size,'export_size':dst.stat().st_size,'treatment':'redacted','redaction_counts':{'header':1},'archive_exclusions':[]})
 inventory=tmp_path/'inventory.json';runner.write_new(inventory,{'entries':[{'source_path':r['original_source_path'],'archive_path':r['archive_path']} for r in rows]})
 final={'schema_version':1,'status':'exported_pending_independent_approval','inventory_sha256':runner.sha(inventory),'entries':rows,'exclusions':[]};manifest=tmp_path/'pending.json';runner.write_new(manifest,final)
 shard_paths=[]
 for i,row in enumerate(rows):
  p=tmp_path/f'shard{i}.json';runner.write_new(p,{**final,'entries':[row]});shard_paths.append(p)
 approved=tmp_path/'approved.json';out=tmp_path/'audits';cmd=[sys.executable,'-u','-m','harness.phase2_isolation.publication_export_audit_parallel_v002','--manifest',str(manifest),'--inventory',str(inventory),'--output-directory',str(out),'--root',str(tmp_path),'--processes','2','--approved-output',str(approved)]
 for p in shard_paths:cmd+=['--shard',str(p)]
 process=subprocess.run(cmd,cwd=runner.ROOT,capture_output=True,text=True,timeout=90)
 assert process.returncode==0,process.stderr
 summary=runner.read(out/'audit-summary.json');assert summary['status']=='passed' and len(summary['shard_audits'])==2 and all(x['passed'] for x in summary['shard_audits'])
 assert runner.read(approved)['status']=='approved_for_publication'
 assert runner.read(manifest)['status']=='exported_pending_independent_approval'
