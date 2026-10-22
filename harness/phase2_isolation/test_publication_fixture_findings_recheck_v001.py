import json
import pytest
from harness.phase2_isolation import publication_fixture_findings_recheck_v001 as check
from harness.phase2_isolation import publication_export_audit_v002 as audit


def fixture():return {'kind':'public_fixture','is_real_credential':False,'role':'ordinary','account':{'username':'synthetic-local','password':'synthetic-fixture-password'},'source':'generic-fixture'}


def entry(tmp_path,value,name='job.json'):
 p=tmp_path/name;p.write_text(json.dumps(value),encoding='utf-8');h=audit.digest(p)
 return {'source_path':name,'original_source_path':name,'archive_path':name,'original_sha256':h,'export_sha256':h,'original_size':p.stat().st_size,'export_size':p.stat().st_size,'treatment':'unchanged'}


def finding(path='job.json',category='sensitive_credential_field'):return {'path':path,'category':category,'blocking':True}


def test_exact_frozen_fixture_object_resolves_only_that_field(tmp_path):
 f=fixture();row=entry(tmp_path,{'fixture':f})
 result=check.recheck_entry(row,[finding()],tmp_path,tmp_path,[f])
 assert result['status']=='exact_frozen_synthetic_fixture_field_only' and result['scope_counts']['exact_frozen_fixture_objects']==1


def test_same_password_outside_fixture_cannot_share_exception(tmp_path):
 f=fixture();row=entry(tmp_path,{'fixture':f,'other':{'password':f['account']['password']}})
 result=check.recheck_entry(row,[finding()],tmp_path,tmp_path,[f])
 assert result['status']=='unresolved_blocking' and result['scope_counts']['unscoped_equal_password_fields']==1


def test_other_password_and_any_token_remain_blocking(tmp_path):
 f=fixture();row=entry(tmp_path,{'fixture':f,'other':{'password':'different-canary'}})
 assert check.recheck_entry(row,[finding()],tmp_path,tmp_path,[f])['status']=='unresolved_blocking'
 row=entry(tmp_path,{'fixture':f,'accessToken':f['account']['password']})
 assert check.recheck_entry(row,[finding()],tmp_path,tmp_path,[f])['status']=='unresolved_blocking'
 assert check.recheck_entry(row,[finding(category='jwt')],tmp_path,tmp_path,[f])['status']=='unresolved_blocking'


def test_unmarked_account_and_other_filename_need_review(tmp_path):
 f=fixture();row=entry(tmp_path,{'account':f['account']})
 assert check.recheck_entry(row,[finding()],tmp_path,tmp_path,[f])['status']=='unresolved_blocking'
 row=entry(tmp_path,{'fixture':f},'objects.json')
 assert check.recheck_entry(row,[finding('objects.json')],tmp_path,tmp_path,[f])['status']=='unresolved_blocking'


def test_hash_drift_still_rejected(tmp_path):
 f=fixture();row=entry(tmp_path,{'fixture':f});row['export_sha256']='0'*64
 with pytest.raises(ValueError,match='export_hash_or_size'):check.recheck_entry(row,[finding()],tmp_path,tmp_path,[f])
