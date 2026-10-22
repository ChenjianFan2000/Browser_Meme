"""Metadata-only export merge. No content reads, approval, upload or input mutation."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from harness.phase2_isolation.publication_export_audit_parallel_v002 import check_union

PENDING='exported_pending_independent_approval'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def relative(value):
    if not isinstance(value,str):raise ValueError('path_not_string')
    p=PurePosixPath(value)
    if not p.parts or p.is_absolute() or '..' in p.parts or ':' in value or chr(92) in value or str(p)!=value or any(ord(c)<32 for c in value):raise ValueError('unsafe_relative_path')
    return value

def pinned(path,expected):
    path=Path(path).resolve(strict=True)
    if not re.fullmatch('[0-9a-f]{64}',expected) or sha(path)!=expected:raise ValueError('pinned_input_hash_mismatch')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('duplicate_json_key')
            result[k]=v
        return result
    value=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite_json')))
    return value,{'path':str(path),'sha256':expected}

def inventory_map(value):
    archives={};sources={}
    for row in value['entries']:
        a=relative(row['archive_path']);s=relative(row['source_path']);relative(row.get('restore_path',a))
        if a in archives or s in sources:raise ValueError('duplicate_inventory_source_or_archive')
        bound=row.get('expected_original_sha256')
        if bound is not None and not re.fullmatch('[0-9a-f]{64}',str(bound)):raise ValueError('invalid_inventory_hash')
        archives[a]=row;sources[s]=a
    return archives,sources

def success_map(value,inventory):
    rows={};sources=set()
    for row in value.get('entries',[]):
        a=relative(row['archive_path']);original=relative(row['original_source_path']);exported=relative(row['source_path']);restore=relative(row['restore_path'])
        if a in rows or original in sources:raise ValueError('duplicate_success_identity')
        if a not in inventory or original!=inventory[a]['source_path'] or restore!=inventory[a].get('restore_path',a):raise ValueError('success_inventory_mapping_mismatch')
        for name in ['original_sha256','export_sha256']:
            if not re.fullmatch('[0-9a-f]{64}',str(row.get(name,''))):raise ValueError('invalid_success_hash')
        for name in ['original_size','export_size']:
            if type(row.get(name)) is not int or row[name]<0:raise ValueError('invalid_success_size')
        if inventory[a].get('expected_original_sha256',row['original_sha256'])!=row['original_sha256']:raise ValueError('original_hash_inventory_mismatch')
        if row.get('treatment') not in {'redacted','unchanged'}:raise ValueError('invalid_treatment')
        if row['treatment']=='unchanged' and (row['original_sha256']!=row['export_sha256'] or row['original_size']!=row['export_size']):raise ValueError('unchanged_hash_mismatch')
        rows[a]=row;sources.add(original)
    return rows

def candidate_exclusions(value,inventory):
    result={}
    for row in value.get('exclusions',[]):
        relative(row['source_path'])
        if row.get('content_read_or_hashed') is not False:raise ValueError('exclusion_requires_no_read_proof')
        if row.get('archive_path') is None:continue
        a=relative(row['archive_path'])
        if a in result or a not in inventory or row['source_path']!=inventory[a]['source_path']:raise ValueError('exclusion_inventory_mapping_mismatch')
        result[a]=row
    return result

def merge(parent_inventory,parent_manifest,retries,supplements,destination):
    inv,invref=pinned(*parent_inventory);parent,parentref=pinned(*parent_manifest)
    if parent.get('schema_version')!=1 or parent.get('status')!='export_blocked' or parent.get('inventory_sha256')!=invref['sha256'] or parent.get('scheduler_error'):raise ValueError('invalid_bound_parent_blocked_manifest')
    imap,smap=inventory_map(inv);success=success_map(parent,imap);excluded=candidate_exclusions(parent,imap)
    if set(success)&set(excluded):raise ValueError('parent_success_exclusion_overlap')
    failed={}
    for row in parent.get('failures',[]):
        source=relative(row['source_path'])
        if source not in smap or source in failed:raise ValueError('unregistered_or_duplicate_parent_failure')
        failed[source]=smap[source]
    if not failed or (set(success)|set(excluded))&set(failed.values()) or set(success)|set(excluded)|set(failed.values())!=set(imap):raise ValueError('parent_denominator_partition_invalid')
    original_exclusions=copy.deepcopy(parent.get('exclusions',[]));allowed_exclusions={canon(x) for x in original_exclusions}
    input_refs=[invref,parentref];lineage=[];repaired=set();added={};finalrows=dict(success);all_sources=set(smap)
    for kind,groups in [('retry',retries),('supplement',supplements)]:
        for pin in groups:
            child,childref=pinned(pin[0],pin[1]);manifest,mref=pinned(pin[2],pin[3]);input_refs.extend([childref,mref])
            if (manifest.get('schema_version')!=1 or manifest.get('status')!=PENDING or manifest.get('failures') or manifest.get('scheduler_error') or manifest.get('inventory_sha256')!=childref['sha256']):raise ValueError('child_not_complete_bound_pending')
            if child.get('source_root',inv.get('source_root'))!=inv.get('source_root') or manifest.get('source_root',parent.get('source_root'))!=parent.get('source_root'):raise ValueError('source_root_mismatch')
            cm,cs=inventory_map(child);entries=success_map(manifest,cm)
            if set(entries)!=set(cm):raise ValueError('child_inventory_not_all_successful')
            if any(canon(x) not in allowed_exclusions for x in manifest.get('exclusions',[])) or any(canon(x) not in allowed_exclusions for x in child.get('excluded_roots',[])):raise ValueError('new_exclusion_forbidden')
            for a,row in cm.items():
                source=row['source_path']
                if kind=='retry':
                    if source not in failed or failed[source]!=a or source in repaired:raise ValueError('retry_not_exact_unique_parent_failure')
                    expected=imap[a]
                    if row.get('restore_path',a)!=expected.get('restore_path',a):raise ValueError('retry_restore_mapping_mismatch')
                    if expected.get('expected_original_sha256',entries[a]['original_sha256'])!=entries[a]['original_sha256']:raise ValueError('retry_parent_hash_mismatch')
                    repaired.add(source)
                else:
                    if source in all_sources or a in imap or a in added:raise ValueError('supplement_source_or_archive_overlap')
                    all_sources.add(source);added[a]=copy.deepcopy(row)
                if a in finalrows:raise ValueError('merged_archive_overlap')
                finalrows[a]=entries[a]
            lineage.append({'role':kind,'inventory':childref,'pending_manifest':mref,'included_count':len(entries)})
    if repaired!=set(failed):raise ValueError('unrepaired_parent_failures')
    final_inventory_rows=[]
    for a,row in [*imap.items(),*added.items()]:
        item=copy.deepcopy(row)
        if a in finalrows:item['expected_original_sha256']=finalrows[a]['original_sha256']
        final_inventory_rows.append(item)
    # Restore identities must also remain unique across parent and supplemental sources.
    restores=[r.get('restore_path',r['archive_path']) for r in final_inventory_rows]
    if len(restores)!=len(set(restores)):raise ValueError('merged_restore_overlap')
    now=datetime.now(timezone.utc).isoformat();generator=sha(Path(__file__))
    merged_inv={**copy.deepcopy(inv),'schema_version':1,'status':'inventory_only_not_publication_approval','created_at_utc':now,'entries':final_inventory_rows,
        'merge_lineage':{'parent_inventory':invref,'parent_blocked_manifest':parentref,'children':lineage,'generator_sha256':generator,'parent_candidate_denominator':len(imap),'repaired_parent_failures':len(repaired),'supplemental_candidates':len(added),'parent_exclusions_unchanged':True,'union_validator_sha256':sha(ROOT/'harness/phase2_isolation/publication_export_audit_parallel_v002.py')}}
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('new_output_directory_required')
    if any(destination==Path(x['path']) or destination in Path(x['path']).parents for x in input_refs):raise ValueError('output_cannot_contain_inputs')
    # Check input bytes still pinned before writing anything.
    if any(sha(x['path'])!=x['sha256'] for x in input_refs):raise ValueError('input_changed_during_merge')
    destination.mkdir(parents=True,exist_ok=False)
    def write(name,value):
        with (destination/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    write('inventory.merged.json',merged_inv);inventory_sha=sha(destination/'inventory.merged.json')
    entries=list(finalrows.values())
    pending={'schema_version':1,'status':PENDING,'created_at_utc':now,'inventory_sha256':inventory_sha,'generator_sha256':generator,'source_root':parent.get('source_root'),
        'entries':entries,'exclusions':original_exclusions,'failures':[],'counts':{'included':len(entries),'excluded':len(original_exclusions),'redacted':sum(r['treatment']=='redacted' for r in entries)},
        'coverage':{'parent_candidates':len(imap),'parent_successes_preserved':len(success),'parent_failures_repaired':len(repaired),'supplemental_candidates':len(added),'merged_candidates':len(final_inventory_rows)},
        'merge_lineage':merged_inv['merge_lineage'],'originals_modified':False,'secret_values_in_logs':False,'not_yet_approved_for_publication':True,'merge_reads_file_contents':False}
    shards=[]
    for i in range(8):
        selected=entries[i::8];exclusions=[r for j,r in enumerate(original_exclusions) if j%8==i]
        shard={**pending,'entries':selected,'exclusions':exclusions,'audit_shard':i+1,'audit_shards':8,'counts':{'included':len(selected),'excluded':len(exclusions),'redacted':sum(r['treatment']=='redacted' for r in selected)}}
        shards.append(shard)
    coverage=check_union(pending,shards,merged_inv,inventory_sha)
    if canon(pending['exclusions'])!=canon(parent.get('exclusions',[])):raise ValueError('internal_exclusions_changed')
    for key,row in success.items():
        if canon(finalrows[key])!=canon(row):raise ValueError('internal_parent_success_changed')
    write('export-manifest.pending.json',pending)
    for i,shard in enumerate(shards,1):write('audit-shard-'+format(i,'02d')+'.pending.json',shard)
    if any(sha(x['path'])!=x['sha256'] for x in input_refs):raise ValueError('input_changed_during_output')
    result={'schema_version':1,'kind':'metadata_only_export_merge','status':'merged_pending_independent_audit_not_approved','coverage':coverage,'input_pins':input_refs,'generator_sha256':generator,
        'outputs':[{'path':str(p),'sha256':sha(p)} for p in sorted(destination.glob('*.json'))],'all_parent_success_dicts_preserved':True,'parent_exclusions_unchanged':True,'approved_written':False,'originals_modified':False,'source_content_read':False}
    write('merge-summary.json',result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--parent-inventory',nargs=2,required=True);p.add_argument('--parent-manifest',nargs=2,required=True)
    p.add_argument('--retry',nargs=4,action='append',default=[]);p.add_argument('--supplement',nargs=4,action='append',default=[]);p.add_argument('--output-directory',required=True);a=p.parse_args()
    try:
        value=merge(a.parent_inventory,a.parent_manifest,a.retry,a.supplement,a.output_directory)
        print(json.dumps({'status':value['status'],'coverage':value['coverage'],'summary':str(Path(a.output_directory).resolve()/'merge-summary.json')}))
    except Exception as error:
        print(json.dumps({'status':'blocked','error_type':type(error).__name__,'reason':str(error) if isinstance(error,ValueError) else 'merge_io_or_schema_failure','approved_written':False}));raise SystemExit(1)
if __name__=='__main__':main()
