"""Credential-shaped strings here are generated synthetic fixtures, never accounts."""
from collections import Counter
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import export_evidence as tool


def blob_zip(entries):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in entries:
            if "\\" in name:
                info=zipfile.ZipInfo("placeholder")
                info.filename=name; info.orig_filename=name
                z.writestr(info,data)
            else:
                z.writestr(name,data)
    return stream.getvalue()


def run_bytes(data,name="file.json"):
    return tool.redact_bytes(data,name)[0]


class ExportRedactionTests(unittest.TestCase):
    def test_header_pairs_all_key_orders_and_cases(self):
        for key in ["Cookie","Set-Cookie","Authorization","X-Api-Key","X-Auth-Token"]:
            for reverse in [False,True]:
                with self.subTest(key=key,reverse=reverse):
                    pairs=[("name",key),("value","synthetic-session=example"),("keep","unchanged")]
                    if reverse: pairs.reverse()
                    raw=json.dumps(dict(pairs),indent=2).encode()
                    expected=raw.replace(b'"synthetic-session=example"',json.dumps(tool.SENTINEL).encode())
                    self.assertEqual(run_bytes(raw),expected)
        self.assertNotIn(b"example",run_bytes(b'\x7b"VaLuE":"example","NaMe":"cOoKiE"}'))

    def test_cookie_storage_keeps_metadata_and_redacts_values(self):
        raw=b'\x7b "cookies": [ \x7b "value": "session-example", "name": "sid", "domain": "local.example", "httpOnly": true } ], "origins": [] }\r\n'
        self.assertEqual(run_bytes(raw),raw.replace(b'"session-example"',json.dumps(tool.SENTINEL).encode()))
        self.assertEqual(run_bytes(b'\x7b"cookies":[]}'),b'\x7b"cookies":[]}')
        self.assertNotIn(b"example",run_bytes(b'\x7b"cookies":\x7b"sid":"example"}}'))

    def test_synthetic_marker_exempts_only_password(self):
        raw=b'\x7b"is_real_credential":false,"password":"example-pw","token":"example-token","cookies":[\x7b"name":"sid","value":"example-cookie"}]}'
        cleaned=json.loads(run_bytes(raw))
        self.assertEqual(cleaned["password"],"example-pw")
        self.assertEqual(cleaned["token"],tool.SENTINEL)
        self.assertEqual(cleaned["cookies"][0]["value"],tool.SENTINEL)
        self.assertEqual(json.loads(run_bytes(b'\x7b"is_real_credential":true,"password":"example-pw"}'))["password"],tool.SENTINEL)

    def test_numeric_secret_and_duplicate_header_name(self):
        clean=json.loads(run_bytes(b'\x7b"csrf_token":123456,"headers":[\x7b"name":"Cookie","name":"Other","value":"example"}]}'))
        self.assertEqual(clean["csrf_token"],tool.SENTINEL)
        self.assertEqual(clean["headers"][0]["value"],tool.SENTINEL)

    def test_embedded_login_response_preserves_all_other_escape_bytes(self):
        body='before\n\x7b "access_token" : "example-token", "keep": "caf\\u00e9", "path":"a\\/b" }\nafter'
        raw=json.dumps({"body":body,"keep":"unchanged"},ensure_ascii=True,indent=2).encode()+b"\r\n"
        self.assertEqual(run_bytes(raw),raw.replace(b"example-token",tool.SENTINEL.encode()))
        self.assertEqual(json.loads(run_bytes(raw))["keep"],"unchanged")

    def test_json_escape_obfuscated_keys_and_values(self):
        raw=b'\x7b"\\u0074oken":"example", "note":"\\ud83d\\ude00 \\u00e9 \x7b\\"token\\":\\"second\\"}"}'
        cleaned=run_bytes(raw)
        self.assertNotIn(b'"example"',cleaned)
        self.assertNotIn(b"second",cleaned)
        self.assertIn(b"\\ud83d\\ude00 \\u00e9",cleaned)

    def test_jsonl_trace_preserves_line_endings_and_safe_records(self):
        first=b'\x7b "type" : "event", "cookie": "example" }\r\n'
        second=b'\x7b"keep": "byte identical"}\n'
        raw=first+second
        for name in ["events.jsonl","trace.trace","trace.network","opaque-resource"]:
            with self.subTest(name=name):
                self.assertEqual(run_bytes(raw,name),first.replace(b'"example"',json.dumps(tool.SENTINEL).encode())+second)

    def test_malformed_json_or_jsonl_and_unknown_formats_fail_closed(self):
        self.assertEqual(run_bytes(b"ordinary UTF-8 text","opaque-resource"),b"ordinary UTF-8 text")
        for data,name in [(b'\x7b"token":"example"',"x.json"),(b'\x7b}\nmalformed\n',"x.jsonl"),(b"\xff\x00unknown","resource.dat"),(b'\xff\xfe\x7b\x00}',"x.json")]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError): run_bytes(data,name)

    def test_opaque_zip_resources_and_nested_archive(self):
        plain=b'\x7b "keep": "byte identical" }\r\n'
        nested=blob_zip([("resources/no-extension",b'\x7b"access_token":"example-token","keep":true}'),("safe.json",plain)])
        raw=blob_zip([("nested.zip",nested),("safe.json",plain),("image.png",b"\x89PNG\r\n\x1a\nsynthetic-image")])
        clean=run_bytes(raw,"private-trace.zip")
        with zipfile.ZipFile(io.BytesIO(clean)) as outer:
            self.assertEqual(outer.read("safe.json"),plain)
            self.assertEqual(outer.read("image.png"),b"\x89PNG\r\n\x1a\nsynthetic-image")
            with zipfile.ZipFile(io.BytesIO(outer.read("nested.zip"))) as inner:
                self.assertEqual(inner.read("safe.json"),plain)
                self.assertEqual(json.loads(inner.read("resources/no-extension"))["access_token"],tool.SENTINEL)

    def test_unchanged_zip_bytes_are_identical(self):
        raw=blob_zip([("safe.json",b'\x7b "keep" : true }\n')])
        self.assertEqual(run_bytes(raw,"private-trace.zip"),raw)

    def test_large_jsonl_and_text_streaming_paths(self):
        lines=b'\x7b"keep":true}\r\n'+b'\x7b"token":"example"}\n'
        with patch.object(tool,"MAX_TEXT",8):
            clean=run_bytes(lines,"opaque-resource")
            self.assertEqual(clean,lines.replace(b'"example"',json.dumps(tool.SENTINEL).encode()))
            self.assertEqual(run_bytes(b"ordinary safe text\r\nsecond line\n","opaque-resource"),b"ordinary safe text\r\nsecond line\n")

    def test_local_storage_sensitive_name_value_and_self_source_unmodified(self):
        record={"localStorage":[{"name":"access_"+"token","value":"synthetic-local-value"}]}
        clean=json.loads(run_bytes(json.dumps(record).encode()))
        self.assertEqual(clean["localStorage"][0]["value"],tool.SENTINEL)
        for name in ["export_evidence.py","test_export_evidence.py","package.py","test_package.py","README.md"]:
            path=Path(__file__).parent/name
            raw=path.read_bytes()
            self.assertEqual(run_bytes(raw,path.name),raw,name)

    def test_har_and_cdp_base64_json_response_redaction(self):
        body=json.dumps({'access_'+'token':'synthetic-secret','keep':'byte identical'},indent=2).encode()
        for flag,payload in [('encoding','text'),('base64Encoded','body')]:
            record={flag:'base64' if flag=='encoding' else True,payload:base64.b64encode(body).decode(),'keep':'untouched'}
            clean=json.loads(run_bytes(json.dumps(record).encode()))
            decoded=base64.b64decode(clean[payload])
            self.assertEqual(decoded,body.replace(b'synthetic-secret',tool.SENTINEL.encode()))
            self.assertEqual(clean['keep'],'untouched')

    def test_base64_binary_preserved_or_blocked_and_invalid_encoding_blocked(self):
        png=b'\x89PNG\r\n\x1a\nsynthetic-safe-image'
        record={'encoding':'base64','text':base64.b64encode(png).decode()}
        raw=json.dumps(record).encode()
        self.assertEqual(run_bytes(raw),raw)
        for payload in [b'\xff\x00unknown',b'%PDF-1.7\n'+b'AKIA'+b'A'*16]:
            record['text']=base64.b64encode(payload).decode()
            with self.assertRaises(ValueError): run_bytes(json.dumps(record).encode())
        record['text']='invalid!'
        with self.assertRaises(ValueError): run_bytes(json.dumps(record).encode())

    def test_archive_authstore_excluded_without_member_read(self):
        raw=blob_zip([("auth.json",b"must not inspect"),("safe.json",b'\x7b}')])
        original=zipfile.ZipFile.open
        def guarded(archive,member,*args,**kwargs):
            name=member.filename if isinstance(member,zipfile.ZipInfo) else member
            if name=="auth.json" and (not args or args[0]=="r"): raise AssertionError("authentication member read")
            return original(archive,member,*args,**kwargs)
        with patch.object(zipfile.ZipFile,"open",new=guarded): clean=run_bytes(raw,"archive.zip")
        with zipfile.ZipFile(io.BytesIO(clean)) as archive: self.assertEqual(archive.namelist(),["safe.json"])

    def test_binary_tokens_are_blocked_and_binary_safe_bytes_unchanged(self):
        jwt=b"eyJ"+b"A"*25+b"."+b"B"*20+b"."+b"C"*20
        raw=b"\x89PNG\r\n\x1a\n"+b"\x00\xff"+jwt
        with self.assertRaises(ValueError): run_bytes(raw,"image.png")
        # ASCII-decodable bytes with binary magic must not be blindly scrubbed.
        with self.assertRaises(ValueError): run_bytes(b"%PDF-1.7\n"+jwt,"resource")
        safe=b"\x89PNG\r\n\x1a\nsynthetic safe pixels\x00\xff"
        self.assertEqual(run_bytes(safe,"resource"),safe)

    def test_provider_shapes_aws_and_pem(self):
        keys=["ghp_"+"a"*36,"github_pat_"+"b"*40,"AIza"+"c"*35,"AKIA"+"D"*16,"ASIA"+"E"*16,"sk-"+"f"*30]
        for key in keys:
            with self.subTest(prefix=key[:4]): self.assertNotIn(key.encode(),run_bytes(("example "+key+" suffix").encode(),"note.txt"))
        begin=b"-----BEGIN "+b"PRIVATE KEY-----"
        end=b"-----END "+b"PRIVATE KEY-----"
        pem=begin+b"\nsynthetic\n"+end
        self.assertNotIn(b"synthetic",run_bytes(pem,"note.txt"))
        with self.assertRaises(ValueError): run_bytes(begin+b"\ntruncated","note.txt")

    def test_raw_header_lines(self):
        raw=b"keep\r\nCookie: sid=example\r\nSet-Cookie: sid=second; HttpOnly\nother\n"
        self.assertEqual(run_bytes(raw,"http.log"),b"keep\r\nCookie: "+tool.SENTINEL.encode()+b"\r\nSet-Cookie: "+tool.SENTINEL.encode()+b"\nother\n")

    def test_archive_paths_duplicates_links_and_depth_rejected(self):
        for name in ["../escape.json","/absolute.json","a\\b.json"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError): run_bytes(blob_zip([(name,b'\x7b}')]),"x.zip")
        raw=blob_zip([("A.json",b'\x7b}'),("a.json",b'\x7b}')])
        with self.assertRaises(ValueError): run_bytes(raw,"x.zip")
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as archive:
            info=zipfile.ZipInfo("link.json"); info.create_system=3; info.external_attr=(stat.S_IFLNK|0o777)<<16
            archive.writestr(info,b"target")
        with self.assertRaises(ValueError): run_bytes(stream.getvalue(),"x.zip")
        raw=b'\x7b}'
        for n in range(tool.MAX_DEPTH+2): raw=blob_zip([("nested.zip" if n else "safe.json",raw)])
        with self.assertRaises(ValueError): run_bytes(raw,"x.zip")


class ExportFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="phase2-export-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"source"; self.root.mkdir()
        self.scope=self.root/"scope"; self.scope.mkdir()
        self.inventory_path=self.root/"inventory.json"
        self.destination=self.root/"exports-001"

    def inventory(self):
        with contextlib.redirect_stdout(io.StringIO()):
            tool.inventory(SimpleNamespace(source_root=str(self.root),root=["scope"],file=[],runtime_inventory=[],output=str(self.inventory_path)))

    def export(self):
        with contextlib.redirect_stdout(io.StringIO()):
            tool.export(SimpleNamespace(source_root=str(self.root),inventory=str(self.inventory_path),output_dir=str(self.destination),workers=4))
        return json.loads((self.destination/"export-manifest.pending.json").read_text("utf-8"))

    def test_export_preserves_originals_nonsecret_bytes_and_pending_approval(self):
        raw=b'\x7b "response" : \x7b "token": "example" }, "keep" : "unchanged" }\r\n'
        files={"sensitive.json":raw,"safe.md":b"plain safe bytes\r\n","public-fixture.json":b'\x7b"is_real_credential":false,"password":"synthetic-example"}'}
        for name,data in files.items(): (self.scope/name).write_bytes(data)
        self.inventory(); value=self.export()
        self.assertEqual(value["status"],"exported_pending_independent_approval")
        self.assertTrue(value["not_yet_approved_for_publication"])
        for name,data in files.items(): self.assertEqual((self.scope/name).read_bytes(),data)
        changed=next(e for e in value["entries"] if e["treatment"]=="redacted")
        self.assertEqual((self.root/changed["source_path"]).read_bytes(),raw.replace(b'"example"',json.dumps(tool.SENTINEL).encode()))
        self.assertEqual(changed["original_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(value["counts"]["redacted"],1)

    def test_direct_authstore_never_read_or_hashed(self):
        (self.scope/"auth.json").write_bytes(b"synthetic blocked store")
        (self.scope/"safe.json").write_bytes(b'\x7b}')
        self.inventory()
        original=tool.common.safe_open
        def guard(path):
            if Path(path).name=="auth.json": raise AssertionError("blocked store opened")
            return original(path)
        with patch.object(tool.common,"safe_open",side_effect=guard): value=self.export()
        self.assertEqual(value["counts"]["excluded"],1)
        self.assertFalse(value["exclusions"][0]["content_read_or_hashed"])

    def test_unknown_format_blocks_manifest_without_modifying_source(self):
        raw=b"\xff\x00unknown binary"; path=self.scope/"opaque.bin"; path.write_bytes(raw)
        self.inventory()
        with self.assertRaises(SystemExit) as error: self.export()
        self.assertEqual(error.exception.code,2)
        value=json.loads((self.destination/"export-manifest.pending.json").read_text("utf-8"))
        self.assertEqual(value["status"],"export_blocked")
        self.assertEqual(len(value["failures"]),1)
        self.assertEqual(path.read_bytes(),raw)

    def test_inventory_symlink_or_junction_directory_explicitly_rejected(self):
        outside=Path(self.temp.name)/"outside"; outside.mkdir()
        link=self.scope/"linked"
        try: link.symlink_to(outside,target_is_directory=True)
        except OSError:
            if os.name!="nt": raise
            result=subprocess.run(["cmd","/c","mklink","/J",str(link),str(outside)],capture_output=True)
            self.assertEqual(result.returncode,0)
        with self.assertRaises(ValueError): self.inventory()
        self.assertFalse(self.inventory_path.exists())

    def test_escaping_inventory_entry_and_bad_original_hash_blocked(self):
        (self.scope/"safe.json").write_bytes(b'\x7b}'); self.inventory()
        value=json.loads(self.inventory_path.read_text())
        value["entries"][0]["expected_original_sha256"]="0"*64
        self.inventory_path.write_text(json.dumps(value))
        with self.assertRaises(SystemExit): self.export()
        blocked=json.loads((self.destination/"export-manifest.pending.json").read_text())
        self.assertEqual(blocked["entries"],[])
        with self.assertRaises(ValueError): tool.contained(self.root,"../outside")


if __name__=="__main__": unittest.main(verbosity=2)
