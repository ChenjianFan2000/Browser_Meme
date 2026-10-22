"""Synthetic mixed logs only; credential-shaped values are runtime fixtures."""
from collections import Counter
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import export_evidence as base
import export_evidence_logtext_v002 as wrapper


class LogTextTests(unittest.TestCase):
    def clean(self,raw,name='mixed.log'):
        with wrapper.log_text_policy(): return base.redact_bytes(raw,name)[0]

    def test_json_records_followed_by_ordinary_tail(self):
        first=json.dumps({'access_'+'token':'synthetic-value','keep':'cafe'},indent=None).encode()+b'\r\n'
        raw=first+b'Traceback (synthetic example):\r\n[stopped] ordinary text\n'
        self.assertEqual(self.clean(raw),raw.replace(b'synthetic-value',base.SENTINEL.encode()))
        with self.assertRaises(ValueError): base.redact_bytes(raw,'mixed.log')

    def test_bracket_prefix_with_json_fragment_headers_and_tokens(self):
        credential=b'AKIA'+b'A'*16
        fragment=json.dumps({'cookies':[{'name':'sid','value':'synthetic-cookie'}]}).encode()
        raw=b'[synthetic info] process stopped\r\n'+fragment+b'\nCookie: sid=synthetic-header\r\nkey='+credential+b'\n'
        expected=raw.replace(b'synthetic-cookie',base.SENTINEL.encode()).replace(b'sid=synthetic-header',base.SENTINEL.encode()).replace(credential,base.SENTINEL.encode())
        self.assertEqual(self.clean(raw),expected)

    def test_structured_extensions_remain_strict(self):
        raw=json.dumps({'keep':True}).encode()+b'\nordinary text tail\n'
        for name in ['file.json','file.jsonl','file.trace','file.network']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError): self.clean(raw,name)

    def test_whole_json_log_preserves_nonsensitive_bytes(self):
        record={'response':json.dumps({'token':'synthetic-token','keep':'caf\\u00e9'},indent=2),'keep':'unchanged'}
        raw=json.dumps(record,indent=2).encode()+b'\r\n'
        self.assertEqual(self.clean(raw),raw.replace(b'synthetic-token',base.SENTINEL.encode()))
        safe=b'ordinary [not JSON] text\r\nno change\n'
        self.assertEqual(self.clean(safe),safe)

    def test_binary_log_and_large_text_bounds_preserved(self):
        with self.assertRaises(ValueError): self.clean(b'\xff\x00unknown')
        with self.assertRaises(ValueError): self.clean(b'%PDF-1.7\n'+b'AKIA'+b'A'*16)
        raw=b'[ordinary prefix]\n'+json.dumps({'token':'synthetic'}).encode()+b'\r\n'
        with patch.object(base,'MAX_TEXT',8):
            self.assertEqual(self.clean(raw),raw.replace(b'synthetic',base.SENTINEL.encode()))

    def test_nested_zip_log_uses_narrow_policy(self):
        rawlog=json.dumps({'token':'synthetic'}).encode()+b'\nordinary tail\n'
        source=io.BytesIO()
        with zipfile.ZipFile(source,'w') as archive: archive.writestr('mixed.log',rawlog)
        clean=self.clean(source.getvalue(),'archive.zip')
        with zipfile.ZipFile(io.BytesIO(clean)) as archive:
            self.assertEqual(archive.read('mixed.log'),rawlog.replace(b'synthetic',base.SENTINEL.encode()))

    def test_retry_manifest_lineage_and_original_bytes_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='phase2-log-retry-synthetic-') as temporary:
            root=Path(temporary); raw=json.dumps({'token':'synthetic'}).encode()+b'\nordinary tail\r\n'
            original=root/'original.log'; original.write_bytes(raw)
            inv=root/'retry-inventory.json'
            inv.write_text(json.dumps({'schema_version':1,'status':'inventory_only_not_publication_approval','entries':[{'source_path':'original.log','archive_path':'original.log','expected_original_sha256':hashlib.sha256(raw).hexdigest()}]}),encoding='utf-8')
            output=root/'retry-001'
            result=subprocess.run([sys.executable,str(Path(wrapper.__file__).resolve()),'export','--source-root',str(root),'--inventory',str(inv),'--output-dir',str(output),'--workers','1'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads((output/'export-manifest.pending.json').read_text('utf-8'))
            self.assertEqual(value['status'],'exported_pending_independent_approval')
            self.assertEqual(value['parent_generator_sha256'],wrapper.PARENT_SHA256)
            self.assertEqual(value['generator_sha256'],hashlib.sha256(Path(wrapper.__file__).read_bytes()).hexdigest())
            self.assertTrue(value['not_yet_approved_for_publication'])
            self.assertEqual(original.read_bytes(),raw)
            self.assertEqual((root/value['entries'][0]['source_path']).read_bytes(),raw.replace(b'synthetic',base.SENTINEL.encode()))


if __name__=='__main__': unittest.main(verbosity=2)
