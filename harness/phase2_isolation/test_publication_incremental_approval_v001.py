import copy
import pytest
from harness.phase2_isolation import publication_incremental_approval_v001 as final


def corpus():
 base=[{'source_path':'source/one','archive_path':'one','restore_path':'source/one'},
       {'source_path':'source/two','archive_path':'two','restore_path':'source/two'}]
 a={'source_path':'exports/one','archive_path':'one','original_source_path':'source/one','original_sha256':'a'*64,'export_sha256':'b'*64,'treatment':'redacted'}
 b={'source_path':'exports/two','archive_path':'two','original_source_path':'source/two','original_sha256':'c'*64,'export_sha256':'d'*64,'treatment':'redacted'}
 c={'source_path':'new','archive_path':'new','original_source_path':'new','original_sha256':'e'*64,'export_sha256':'e'*64,'treatment':'unchanged'}
 baseline={'entries':base};original={'entries':[a],'failures':[{'source_path':'source/two'}],'exclusions':[{'source_path':'excluded/profile','reason':'temporary profile'}]}
 inventory={'entries':[{**base[0],'expected_original_sha256':a['original_sha256']},{**base[1],'expected_original_sha256':b['original_sha256']},{'source_path':'new','archive_path':'new','expected_original_sha256':c['original_sha256']}]}
 merged={'status':'exported_pending_independent_approval','entries':[a,b,c],'failures':[],'exclusions':copy.deepcopy(original['exclusions'])}
 parts=[{'one':a},{'two':b},{'new':c}]
 return merged,inventory,baseline,original,parts


def test_complete_original_partition_retry_and_additions():
 values=corpus();out=final.verify_final_coverage(*values)
 assert out=={'final_included':3,'original_candidates':2,'original_successes_unchanged':1,'original_failed_candidates_now_audited':1,'supplemental_candidates_audited':1,'parts':3}


def test_no_missing_original_failure_or_modified_success():
 merged,inv,base,orig,parts=corpus();parts.pop(1)
 with pytest.raises(ValueError,match='part_union'):final.verify_final_coverage(merged,inv,base,orig,parts)
 merged,inv,base,orig,parts=corpus();orig['entries'][0]=dict(orig['entries'][0],export_sha256='0'*64)
 with pytest.raises(ValueError,match='success_dictionary'):final.verify_final_coverage(merged,inv,base,orig,parts)


def test_cross_part_duplicate_and_inventory_hash_cannot_be_weakened():
 merged,inv,base,orig,parts=corpus();parts.append(parts[0])
 with pytest.raises(ValueError,match='cross_part_duplicate'):final.verify_final_coverage(merged,inv,base,orig,parts)
 merged,inv,base,orig,parts=corpus();inv['entries'][0]['expected_original_sha256']='0'*64
 with pytest.raises(ValueError,match='original_binding'):final.verify_final_coverage(merged,inv,base,orig,parts)


def test_original_exclusions_and_metadata_must_stay_exact():
 merged,inv,base,orig,parts=corpus();merged['exclusions'].append({'source_path':'another'})
 with pytest.raises(ValueError,match='exclusions_changed'):final.verify_final_coverage(merged,inv,base,orig,parts)
 merged,inv,base,orig,parts=corpus();inv['entries'][0]['restore_path']='modified'
 with pytest.raises(ValueError,match='metadata_changed'):final.verify_final_coverage(merged,inv,base,orig,parts)


def test_unscanned_single_part_is_rejected(tmp_path):
 from harness.phase2_isolation.publication_export_audit_parallel_v002 import write_new,sha
 manifest=tmp_path/'pending.json';audit=tmp_path/'audit.json';write_new(manifest,{'status':'exported_pending_independent_approval','entries':[],'failures':[]})
 write_new(audit,{'kind':'independent_actual_export_stage_audit','pending_manifest_sha256':sha(manifest),'generator_sha256':final.SCANNER_SHA,'errors':[],'findings':[],'counts':{'entries_verified':1}})
 with pytest.raises(ValueError,match='scan_count'):final.verify_part(manifest,audit)
