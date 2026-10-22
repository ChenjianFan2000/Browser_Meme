"""Synthetic-only tests; all token shapes are assembled fictitious canaries."""
import hashlib
import base64
import io
import json
import tempfile
import zipfile
import pytest
from harness.phase2_isolation import publication_export_audit_v001 as audit


def categories(data,**kwargs):return {x['category'] for x in audit.inspect_stream(io.BytesIO(data),'generic',**kwargs)}


def test_token_families_are_detected_without_emitting_values():
    values={
      'jwt':b'eyJ'+b'A'*30+b'.'+b'B'*30+b'.'+b'C'*30,
      'openai_key':b'sk-'+b'A'*40,
      'github_legacy_token':b'ghp_'+b'A'*36,
      'github_pat':b'github_' + b'pat_'+b'A'*50,
      'google_api_key':b'AI' + b'za'+b'A'*35,
      'aws_access_key':b'AK' + b'IA'+b'A'*16,
      'private_key_material':b'-----BEGIN '+b'PRIVATE KEY-----\n'+b'A'*80+b'\n-----END '+b'PRIVATE KEY-----',
    }
    for kind,value in values.items():
      findings=audit.inspect_stream(io.BytesIO(value),'generic',structured=False)
      assert kind in {x['category'] for x in findings}
      assert value.decode() not in json.dumps(findings)


def test_placeholders_and_synthetic_fixture_password_are_not_live_auth():
    obj={'headers':[{'name':'Cookie','value':'[REDACTED_AUTH]'}],
         'cookies':[{'name':'local','value':'[REDACTED_AUTH]'}],
         'password':'synthetic-local-fixture'}
    assert categories(json.dumps(obj).encode(),synthetic_passwords={'synthetic-local-fixture'})==set()


def test_structured_headers_cookies_and_embedded_json():
    obj={'nested':json.dumps({'headers':[{'name':'Authorization','value':'Bearer local-canary'}]}),
         'cookies':[{'name':'local','value':'local-canary'}]}
    assert categories(json.dumps(obj).encode())=={'sensitive_header_value','cookie_storage_value'}


def test_base64_har_body_is_decoded_before_scanning():
    encoded=base64.b64encode(json.dumps({'access_token':('ghp_'+'A'*36)}).encode()).decode()
    found=categories(json.dumps({'encoding':'base64','text':encoded}).encode())
    assert {'github_legacy_token','sensitive_credential_field'}<=found


def test_split_source_expressions_and_regex_are_not_executed():
    data=b"pattern = r'ghp_[A-Za-z0-9]{36}'\ncanary='ghp_' + 'A' * 36\n"
    assert categories(data,structured=False)==set()


def test_cross_chunk_token_is_detected():
    data=b' '*((1024*1024)-5)+b'sk-'+b'A'*40
    assert 'openai_key' in categories(data,structured=False)


def test_nested_zip_all_members_including_opaque_resource(tmp_path):
    inner=io.BytesIO()
    with zipfile.ZipFile(inner,'w') as z:z.writestr('resources/opaque',b'sk-'+b'A'*40)
    outer=tmp_path/'outer.zip'
    with zipfile.ZipFile(outer,'w') as z:z.writestr('nested.zip',inner.getvalue())
    findings,members=audit.scan_zip(outer,'generic',tmp_path,set())
    assert members==2 and any(x['category']=='openai_key' and '!nested.zip!resources/opaque' in x['path'] for x in findings)


def test_auth_storage_member_blocked_without_opening_payload(tmp_path):
    outer=tmp_path/'outer.zip'
    with zipfile.ZipFile(outer,'w') as z:z.writestr('auth.json',b'not-read')
    findings,members=audit.scan_zip(outer,'generic',tmp_path,set())
    assert members==0 and findings[0]['category']=='authentication_storage_member_exclude_without_reading'


def test_manifest_hash_size_and_original_redaction_mapping(tmp_path):
    source=tmp_path/'original.txt';source.write_bytes(b'synthetic-public-data')
    row={'source_path':'original.txt','original_source_path':'original.txt','archive_path':'results/original.txt',
         'original_sha256':audit.digest(source),'export_sha256':audit.digest(source),
         'original_size':source.stat().st_size,'export_size':source.stat().st_size,'treatment':'unchanged'}
    assert audit.audit_entry(row,tmp_path,tmp_path,set())==([],0)
    row['export_size']+=1
    with pytest.raises(ValueError,match='export_hash_or_size'):audit.audit_entry(row,tmp_path,tmp_path,set())
    row['export_size']-=1;row['treatment']='redacted'
    with pytest.raises(ValueError,match='redaction_mapping'):audit.audit_entry(row,tmp_path,tmp_path,set())


def test_traversal_archive_path_is_rejected():
    with pytest.raises(ValueError):audit.safe_relative('../private')


def test_named_auth_file_never_hashed(tmp_path,monkeypatch):
    row={'source_path':'auth.json','archive_path':'auth.json'}
    monkeypatch.setattr(audit,'digest',lambda _:pytest.fail('must not hash auth store'))
    with pytest.raises(ValueError,match='authentication_storage'):audit.audit_entry(row,tmp_path,tmp_path,set())
