"""Synthetic tests only; no experiment files, accounts, or authentication stores."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package as tool


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="phase2-publication-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.data = {
            "harness/experiments/synthetic/evidence/page.html": b"<p>example</p>" * 500,
            "harness/experiments/synthetic/evidence/image.png": b"synthetic PNG data" * 200,
            "harness/experiments/synthetic/evidence/trace.zip": b"synthetic ZIP bytes" * 200,
            "harness/experiments/synthetic/rules.json": b'{"fixture_only":true}\n',
            "harness/experiments/synthetic/unicode-\u4e2d\u6587.txt": "\u4e2d\u6587 evidence\n".encode(),
            ".runtime/synthetic-managed/evidence.txt": b"explicit approved runtime evidence\n",
            "harness/experiments/synthetic/redacted.json": b'{"synthetic_token":"[REDACTED]"}\n',
            "harness/experiments/synthetic/empty.txt": b"",
            "harness/experiments/synthetic/public-fixture.json": b'{"is_real_credential":false,"password":"synthetic-example-only"}',
        }
        entries = []
        for archive_path, data in self.data.items():
            redacted = archive_path.endswith("redacted.json")
            source_path = ".runtime/publication/exports/redacted.json" if redacted else archive_path
            source = self.root / source_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(data)
            entries.append({"source_path":source_path, "archive_path":archive_path,
                            "original_sha256":sha(b"synthetic original differs") if redacted else sha(data),
                            "export_sha256":sha(data), "treatment":"redacted" if redacted else "unchanged"})
        self.manifest = {"schema_version":1, "status":"approved_for_publication", "entries":entries,
                         "exclusions":[{"path":"auth.json", "reason":"never read or export"}]}
        self.manifest_path = self.base / "approved-export.json"
        self.save_manifest()

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.manifest_sha = sha(self.manifest_path.read_bytes())

    def pack(self, name="packed", workers=4):
        output = self.base / name
        with contextlib.redirect_stdout(io.StringIO()):
            index = tool.pack(self.manifest_path, self.manifest_sha, self.root, output, 4096, workers)
        return output, index

    def save_index(self, output, index):
        (output / "volume-index.json").write_text(json.dumps(index), encoding="utf-8")

    def test_roundtrip_every_byte_redaction_and_compression(self):
        output, index = self.pack()
        self.assertGreater(len(index["volumes"]), 1)
        tool.verify(output / "volume-index.json")
        restored = self.base / "restored"
        tool.restore(output / "volume-index.json", restored)
        observed = {p.relative_to(restored).as_posix():p.read_bytes() for p in restored.rglob("*") if p.is_file()}
        self.assertEqual(observed, self.data)
        self.assertEqual(index["redacted_file_count"], 1)
        entry = next(e for e in index["entries"] if e["treatment"] == "redacted")
        self.assertNotEqual(entry["original_sha256"], entry["export_sha256"])
        self.assertFalse(index["originals_modified"])
        for volume in index["volumes"]:
            with zipfile.ZipFile(output / volume["name"]) as archive:
                for info in archive.infolist():
                    expected = zipfile.ZIP_STORED if Path(info.filename).suffix in {".png", ".zip"} else zipfile.ZIP_DEFLATED
                    self.assertEqual(info.compress_type, expected)
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))

    def test_deterministic_across_workers_and_input_order(self):
        first, a = self.pack("first", workers=1)
        self.manifest["entries"].reverse()
        self.save_manifest()
        second, b = self.pack("second", workers=4)
        self.assertEqual(a["volumes"], b["volumes"])
        for v in a["volumes"]:
            self.assertEqual((first/v["name"]).read_bytes(), (second/v["name"]).read_bytes())

    def test_unapproved_or_wrong_manifest_hash_refused(self):
        with self.assertRaises(tool.PublicationError):
            tool.pack(self.manifest_path, "0"*64, self.root, self.base/"bad")
        self.manifest["status"] = "pending_review"
        self.save_manifest()
        with self.assertRaises(tool.PublicationError): self.pack()
        self.assertFalse((self.base/"packed").exists())

    def test_export_hash_bad_refused_before_output(self):
        self.manifest["entries"][0]["export_sha256"] = "0"*64
        self.manifest["entries"][0]["original_sha256"] = "0"*64
        self.save_manifest()
        with self.assertRaises(tool.PublicationError): self.pack()
        self.assertFalse((self.base/"packed").exists())

    def test_unchanged_original_hash_difference_refused(self):
        self.manifest["entries"][0]["original_sha256"] = "0"*64
        self.save_manifest()
        with self.assertRaises(tool.PublicationError): self.pack()

    def test_unsafe_manifest_paths_refused(self):
        for name in ["../escape", "/absolute", "C:/drive", "a\\windows", "a/../b", "a/./b", "a//b", "a/NUL.txt", "a/trailing.", "a/file:stream"]:
            with self.subTest(name=name):
                manifest = copy.deepcopy(self.manifest)
                manifest["entries"][0]["archive_path"] = name
                with self.assertRaises(tool.PublicationError): tool.validated_entries(manifest, self.root)
                manifest = copy.deepcopy(self.manifest)
                manifest["entries"][0]["source_path"] = name
                with self.assertRaises(tool.PublicationError): tool.validated_entries(manifest, self.root)

    def test_duplicate_casefold_and_file_ancestor_refused(self):
        for path in [self.manifest["entries"][0]["archive_path"], self.manifest["entries"][0]["archive_path"].upper(), "harness"]:
            with self.subTest(path=path):
                manifest = copy.deepcopy(self.manifest)
                manifest["entries"][1]["archive_path"] = path
                with self.assertRaises(tool.PublicationError): tool.validated_entries(manifest, self.root)

    def test_credentials_and_caches_refused_without_content_read(self):
        for name in ["auth.json", "sub/secrets/synthetic.txt", "sub/codex-home/data.json", "sub/cache/item.txt", "__pycache__/module.pyc", ".env", "sub/.env.local"]:
            with self.subTest(name=name):
                manifest = copy.deepcopy(self.manifest)
                manifest["entries"][0]["source_path"] = name
                with patch.object(tool, "safe_open", side_effect=AssertionError("must not open excluded content")):
                    with self.assertRaises(tool.PublicationError): tool.validated_entries(manifest, self.root)

    def test_symlink_or_junction_escape_refused(self):
        external = self.base/"outside"
        external.mkdir()
        (external/"file.txt").write_bytes(b"outside synthetic data")
        link = self.root/"escape-link"
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError:
            if os.name != "nt": raise
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)], capture_output=True)
            self.assertEqual(result.returncode, 0, "Synthetic junction setup failed")
        manifest = copy.deepcopy(self.manifest)
        manifest["entries"][0]["source_path"] = "escape-link/file.txt"
        with self.assertRaises(tool.PublicationError): tool.validated_entries(manifest, self.root)

    def test_corrupt_volume_and_wrong_index_pin_refused(self):
        output, index = self.pack()
        with self.assertRaises(tool.PublicationError): tool.verify(output/"volume-index.json", "0"*64)
        path = output/index["volumes"][0]["name"]
        data = bytearray(path.read_bytes()); data[0] ^= 1; path.write_bytes(data)
        with self.assertRaises(tool.PublicationError): tool.restore(output/"volume-index.json", self.base/"restored")
        self.assertFalse((self.base/"restored").exists())

    def test_malicious_member_paths_and_duplicate_members_refused(self):
        for extra in ["../escape", "harness/experiments/synthetic/evidence/page.html"]:
            with self.subTest(extra=extra):
                output, index = self.pack("packed-"+str(len(extra)))
                volume = index["volumes"][0]
                # Pick the volume containing page.html so the second case is a duplicate.
                page = next(e for e in index["entries"] if e["archive_path"].endswith("page.html"))
                volume = next(v for v in index["volumes"] if v["name"] == page["volume"])
                path = output/volume["name"]
                with zipfile.ZipFile(path, "a") as archive:
                    if extra.endswith("page.html"):
                        with self.assertWarns(UserWarning): archive.writestr(extra, b"malicious synthetic data")
                    else:
                        archive.writestr(extra, b"malicious synthetic data")
                volume["sha256"] = sha(path.read_bytes()); volume["size_bytes"] = path.stat().st_size
                self.save_index(output, index)
                with self.assertRaises(tool.PublicationError): tool.restore(output/"volume-index.json", self.base/"restored")
                self.assertFalse((self.base/"restored").exists())

    def test_member_hash_mismatch_even_when_whole_zip_hash_matches(self):
        output, index = self.pack()
        volume = index["volumes"][0]
        path = output/volume["name"]
        with zipfile.ZipFile(path) as archive:
            payload = [(i, archive.read(i)) for i in archive.infolist()]
        with zipfile.ZipFile(path, "w") as archive:
            for info, data in payload:
                archive.writestr(info, (b"X"+data[1:]) if data else data)
        volume["sha256"] = sha(path.read_bytes()); volume["size_bytes"] = path.stat().st_size
        self.save_index(output,index)
        with self.assertRaises(tool.PublicationError): tool.verify(output/"volume-index.json")

    def test_symlink_zip_member_refused(self):
        output,index = self.pack()
        volume = index["volumes"][0]
        path = output/volume["name"]
        with zipfile.ZipFile(path) as archive: payload = [(i,archive.read(i)) for i in archive.infolist()]
        with zipfile.ZipFile(path,"w") as archive:
            for info,data in payload:
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info,data)
        volume["sha256"] = sha(path.read_bytes()); volume["size_bytes"] = path.stat().st_size
        self.save_index(output,index)
        with self.assertRaises(tool.PublicationError): tool.verify(output/"volume-index.json")

    def test_restore_and_pack_never_overwrite(self):
        output,index = self.pack()
        with self.assertRaises(tool.PublicationError): self.pack()
        target = self.base/"restore-existing"; target.mkdir(); (target/"keep").write_bytes(b"unchanged")
        with self.assertRaises(tool.PublicationError): tool.restore(output/"volume-index.json", target)
        self.assertEqual((target/"keep").read_bytes(),b"unchanged")

    def test_asset_index_offline_rest_urls(self):
        output,index = self.pack()
        release = {"html_url":"https://github.com/example/research/releases/tag/synthetic", "assets":[]}
        for n,v in enumerate(index["volumes"],1):
            release["assets"].append({"id":n,"name":v["name"],"size":v["size_bytes"],
                "url":f"https://api.github.com/repos/example/research/releases/assets/{n}",
                "browser_download_url":f"https://github.com/example/research/releases/download/synthetic/{v['name']}"})
        rest = self.base/"release.json"; rest.write_text(json.dumps(release),encoding="utf-8")
        result = tool.asset_index(output/"volume-index.json",rest,self.base/"asset-urls.json")
        self.assertEqual(len(result["assets"]),len(index["volumes"]))
        self.assertEqual(result["volume_index_sha256"],sha((output/"volume-index.json").read_bytes()))

    def test_asset_size_bound_is_strict_and_targets_bounded(self):
        with patch.object(tool, "ASSET_LIMIT", 8000):
            with self.assertRaises(tool.PublicationError): tool.validated_entries(self.manifest,self.root)
        for target in [0,1023,tool.ASSET_LIMIT]:
            with self.subTest(target=target):
                with self.assertRaises(tool.PublicationError): tool.volume_plan([],target)
        for workers in [0,5]:
            with self.assertRaises(tool.PublicationError):
                tool.pack(self.manifest_path,self.manifest_sha,self.root,self.base/"bad-workers",4096,workers)

    def test_source_change_during_pack_retains_failed_run_without_index(self):
        original = tool.make_volume
        mutated = False
        def changing(output,root,name,entries):
            nonlocal mutated
            if not mutated:
                source = tool.source_for(root,entries[0])
                source.write_bytes(b"source changed after complete preflight")
                mutated = True
            return original(output,root,name,entries)
        with patch.object(tool,"make_volume",side_effect=changing):
            with self.assertRaises(tool.PublicationError): self.pack(workers=1)
        output=self.base/"packed"
        self.assertTrue((output/"PACK_FAILED.json").exists())
        self.assertFalse((output/"volume-index.json").exists())
        self.assertFalse(json.loads((output/"PACK_FAILED.json").read_text())["publishable"])

    def test_index_traversal_or_duplicate_refused_before_restore(self):
        output,index=self.pack()
        for mode in ["traversal","duplicate"]:
            bad=copy.deepcopy(index)
            bad["entries"][0]["archive_path"]="../escape" if mode=="traversal" else bad["entries"][1]["archive_path"]
            self.save_index(output,bad)
            with self.assertRaises(tool.PublicationError): tool.restore(output/"volume-index.json",self.base/"restored")
            self.assertFalse((self.base/"restored").exists())

    def test_cli_pack_verify_restore(self):
        output=self.base/"cli-packed"
        commands=[
            ["pack","--manifest",str(self.manifest_path),"--approved-manifest-sha256",self.manifest_sha,
             "--source-root",str(self.root),"--output",str(output),"--target-mib","1","--workers","4"],
            ["verify","--index",str(output/"volume-index.json"),"--workers","4"],
            ["restore","--index",str(output/"volume-index.json"),"--output",str(self.base/"cli-restored"),"--workers","4"],
        ]
        for command in commands:
            result=subprocess.run([sys.executable,str(Path(tool.__file__).resolve()),*command],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1])["status"],"passed")
        self.assertEqual((self.base/"cli-restored"/next(iter(self.data))).read_bytes(),next(iter(self.data.values())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
