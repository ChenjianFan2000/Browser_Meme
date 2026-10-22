"""Synthetic validated ICO containers; no real trace or account inputs."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib

import export_evidence as base
import export_evidence_ico_v003 as wrapper


def png_chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)


def image_png():
    return wrapper.PNG_MAGIC+png_chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+png_chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00\xff'))+png_chunk(b'IEND',b'')


def icon(*,png=False,extra=b''):
    if png: payload=image_png()
    else:
        pixels=b'\x00\x00\x00\xff'+b'\x00'*4+extra
        payload=struct.pack('<IiiHHIIiiII',40,1,2,1,32,0,len(pixels),0,0,0,0)+pixels
    return struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',1,1,0,0,1,32,len(payload),22)+payload


def zip_blob(items):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        for name,data in items: archive.writestr(name,data)
    return buffer.getvalue()


class IconTests(unittest.TestCase):
    def clean(self,raw,name='image.ico'):
        with wrapper.ico_policy(): return base.redact_bytes(raw,name)[0]

    def test_real_dib_and_png_icon_bytes_unchanged(self):
        for png in [False,True]:
            raw=icon(png=png)
            self.assertEqual(self.clean(raw),raw)
            self.assertEqual(self.clean(raw,'opaque-resource'),raw)
        with self.assertRaises(ValueError): base.redact_bytes(icon(),'image.ico')

    def test_nested_trace_still_redacts_every_text_and_cookie(self):
        ico=icon(png=True)
        record=json.dumps({'cookies':[{'name':'sid','value':'synthetic-cookie'}]}).encode()
        nested=zip_blob([('resources/favicon.ico',ico),('trace.network',record+b'\n')])
        raw=zip_blob([('nested.zip',nested),('note.txt',b'ordinary unchanged text')])
        clean=self.clean(raw,'trace.zip')
        with zipfile.ZipFile(io.BytesIO(clean)) as outer:
            self.assertEqual(outer.read('note.txt'),b'ordinary unchanged text')
            with zipfile.ZipFile(io.BytesIO(outer.read('nested.zip'))) as inner:
                self.assertEqual(inner.read('resources/favicon.ico'),ico)
                self.assertEqual(json.loads(inner.read('trace.network'))['cookies'][0]['value'],base.SENTINEL)

    def test_binary_credentials_blocked_not_replaced(self):
        token=b'AKIA'+b'A'*16
        raw=icon(extra=token)
        with self.assertRaises(ValueError): self.clean(raw)
        self.assertIn(token,raw)

    def test_fake_truncated_overlap_and_bad_png_rejected(self):
        for raw in [wrapper.ICO_MAGIC+b'not an icon',icon()[:-1],icon()+b'trailing']:
            with self.assertRaises(ValueError): self.clean(raw)
        bad=bytearray(icon()); struct.pack_into('<I',bad,18,0)
        with self.assertRaises(ValueError): self.clean(bytes(bad))
        bad=bytearray(icon(png=True)); bad[-1]^=1
        with self.assertRaises(ValueError): self.clean(bytes(bad))

    def test_narrow_suffix_and_strict_json_policies(self):
        for name in ['wrong.json','wrong.jsonl','wrong.trace']:
            with self.assertRaises(ValueError): self.clean(icon(),name)
        raw=json.dumps({'token':'synthetic'}).encode()+b'\nordinary stopped tail\r\n'
        self.assertEqual(self.clean(raw,'mixed.log'),raw.replace(b'synthetic',base.SENTINEL.encode()))
        with self.assertRaises(ValueError): self.clean(raw,'strict.jsonl')
        with self.assertRaises(ValueError): self.clean(b'\xff\x00unknown','unknown-resource')

    def test_unchanged_archive_stays_byte_identical(self):
        raw=zip_blob([('resources/favicon.ico',icon()),('safe.json',json.dumps({'keep':True}).encode())])
        self.assertEqual(self.clean(raw,'trace.zip'),raw)

    def test_cli_manifest_new_and_parent_sha_lineage(self):
        with tempfile.TemporaryDirectory(prefix='phase2-ico-retry-synthetic-') as temporary:
            root=Path(temporary); raw=icon(); original=root/'original.ico'; original.write_bytes(raw)
            inventory=root/'inventory.json'; inventory.write_text(json.dumps({'schema_version':1,'status':'inventory_only_not_publication_approval',
                'entries':[{'source_path':'original.ico','archive_path':'original.ico','expected_original_sha256':hashlib.sha256(raw).hexdigest()}]}),encoding='utf-8')
            output=root/'new-output'
            result=subprocess.run([sys.executable,str(Path(wrapper.__file__).resolve()),'export','--source-root',str(root),'--inventory',str(inventory),'--output-dir',str(output),'--workers','1'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads((output/'export-manifest.pending.json').read_text('utf-8'))
            self.assertEqual(value['status'],'exported_pending_independent_approval')
            self.assertEqual(value['generator_sha256'],hashlib.sha256(Path(wrapper.__file__).read_bytes()).hexdigest())
            self.assertEqual(value['parent_generator_sha256'],wrapper.PARENT_SHA256)
            self.assertEqual(value['format_wrapper_parent_sha256'],wrapper.LOG_WRAPPER_SHA256)
            self.assertEqual(value['entries'][0]['export_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(original.read_bytes(),raw)

    def test_two_process_failed_only_cli_preserves_wrapper_and_parent_chain(self):
        with tempfile.TemporaryDirectory(prefix='phase2-ico-shards-synthetic-') as temporary:
            root=Path(temporary)
            items={'sample.ico':icon(png=True),'sample.log':json.dumps({'token':'synthetic'}).encode()+b'\nordinary tail\n'}
            rows=[]
            for name,data in items.items():
                (root/name).write_bytes(data)
                rows.append({'source_path':name,'archive_path':name,'expected_original_sha256':hashlib.sha256(data).hexdigest()})
            inventory=root/'inventory.json'; inventory.write_text(json.dumps({'schema_version':1,'status':'inventory_only_not_publication_approval',
                'source_root':str(root),'entries':rows,'excluded_roots':[]}),encoding='utf-8')
            output=root/'sharded-output'
            result=subprocess.run([sys.executable,str(Path(wrapper.__file__).resolve()),'sharded-export','--source-root',str(root),
                '--inventory',str(inventory),'--inventory-sha256',hashlib.sha256(inventory.read_bytes()).hexdigest(),
                '--output-dir',str(output),'--shards','2','--jobs','2'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            merged=json.loads((output/'export-manifest.pending.json').read_text('utf-8'))
            self.assertEqual(merged['status'],'exported_pending_independent_approval')
            self.assertEqual(merged['counts'],{'included':2,'excluded':0,'redacted':1})
            self.assertEqual(merged['generator_sha256'],hashlib.sha256(Path(wrapper.__file__).read_bytes()).hexdigest())
            for shard in merged['shards']:
                child=json.loads((root/shard['manifest_path']).read_text('utf-8'))
                self.assertEqual(child['parent_generator_sha256'],wrapper.PARENT_SHA256)
                self.assertEqual(child['format_wrapper_parent_sha256'],wrapper.LOG_WRAPPER_SHA256)
                self.assertEqual(child['generator_sha256'],merged['generator_sha256'])
            for name,data in items.items(): self.assertEqual((root/name).read_bytes(),data)


if __name__=='__main__': unittest.main(verbosity=2)
