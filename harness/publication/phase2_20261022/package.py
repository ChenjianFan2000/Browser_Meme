"""Manifest-bound, independent ZIP volumes. Python 3.11+, standard library only.

This tool never decides what is public. An independent review must supply the
approved export manifest and its SHA256 before pack reads any listed input.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import zipfile


SCHEMA = 1
MIB = 1024 * 1024
ASSET_LIMIT = 2 * 1024**3  # Strictly less than this value.
CHUNK = MIB
DENIED_PARTS = {
    ".git", ".codex", "codex-home", "secrets", "node_modules", "__pycache__",
    ".cache", "cache", "caches", ".pytest_cache", ".mypy_cache", ".venv",
}
DENIED_NAMES = {
    "auth.json", "credentials.json", "research.env", "id_rsa", "id_ed25519",
    "login data", "cookies", "cookies.sqlite", "credentials",
}
STORED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".zip", ".gz",
    ".bz2", ".xz", ".7z", ".rar", ".mp4", ".webm", ".mp3", ".woff2",
    ".pdf", ".parquet",
}


class PublicationError(ValueError):
    pass


def fail(message):
    raise PublicationError(message)


def digest_file(path):
    h = hashlib.sha256()
    with safe_open(path) as stream:
        while chunk := stream.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def checked_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        fail("SHA256 must be 64 lowercase hexadecimal characters")
    return value


def relative_name(value, *, protected=True):
    if not isinstance(value, str) or not value or "\\" in value:
        fail("Paths must be nonempty relative POSIX paths")
    parts = value.split("/")
    for part in parts:
        if part in {"", ".", ".."} or part.endswith((".", " ")):
            fail("Unsafe path component")
        if any(ord(c) < 32 or c in '<>:"|?*' for c in part):
            fail("Nonportable or absolute path")
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part):
            fail("Windows reserved path component")
        low = part.casefold()
        if protected and (low in DENIED_PARTS or low in DENIED_NAMES
                          or low == ".env" or low.startswith(".env.")
                          or low.endswith((".pyc", ".pyo", ".pem", ".key"))):
            fail("Credential, cache, or environment path is excluded")
    return value


def no_links(path):
    """Reject symlinks and Windows junction/reparse points in every ancestor."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            s = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            fail("Symlink or reparse point is not allowed")
    return path


def safe_open(path):
    path = Path(os.path.abspath(path))
    for part in path.parts:
        if part != path.anchor:
            relative_name(part)
    path = no_links(path)
    s = path.stat()
    if not stat.S_ISREG(s.st_mode):
        fail("Input must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    opened = os.fstat(fd)
    if (opened.st_dev, opened.st_ino) != (s.st_dev, s.st_ino):
        os.close(fd)
        fail("Input changed during open")
    return os.fdopen(fd, "rb")


def load_json(path):
    with safe_open(path) as stream:
        return json.load(stream)


def load_bound_json(path, expected_sha=None):
    with safe_open(path) as stream:
        data = stream.read()
    if expected_sha is not None and hashlib.sha256(data).hexdigest() != checked_sha(expected_sha):
        fail("JSON file differs from pinned SHA256")
    return json.loads(data)


def write_json_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def check_unique(names):
    seen = set()
    all_names = set()
    for name in names:
        key = name.casefold()
        if key in seen:
            fail("Duplicate or case-colliding archive path")
        seen.add(key)
        all_names.add(key)
    for name in all_names:
        parts = name.split("/")
        if any("/".join(parts[:n]) in all_names for n in range(1, len(parts))):
            fail("A file path is also an ancestor of another file")


def validated_entries(manifest, source_root):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA or manifest.get("status") != "approved_for_publication":
        fail("An approved_for_publication schema_version=1 manifest is required")
    raw = manifest.get("entries")
    if not isinstance(raw, list) or not raw:
        fail("Manifest entries must be a nonempty list")
    root = no_links(source_root)
    if not root.is_dir():
        fail("Source root must exist")
    result = []
    for entry in raw:
        if not isinstance(entry, dict):
            fail("Each approved entry must be an object")
        source = relative_name(entry.get("source_path"))
        archive = relative_name(entry.get("archive_path"))
        original = checked_sha(entry.get("original_sha256"))
        export = checked_sha(entry.get("export_sha256"))
        treatment = entry.get("treatment")
        if treatment not in {"unchanged", "redacted"}:
            fail("Treatment must be unchanged or redacted")
        if treatment == "unchanged" and original != export:
            fail("Unchanged entry has different original and export SHA256")
        source_file = root.joinpath(*source.split("/"))
        no_links(source_file)
        if not source_file.resolve().is_relative_to(root.resolve()):
            fail("Source escapes its explicit root")
        size = source_file.stat().st_size
        if size < 0 or size + 1024 + 2 * len(archive.encode("utf-8")) >= ASSET_LIMIT:
            fail("Single file cannot fit in a less-than-2GiB independent volume")
        result.append({"source_path": source, "archive_path": archive,
                       "original_sha256": original, "export_sha256": export,
                       "treatment": treatment, "size_bytes": size})
    check_unique(e["archive_path"] for e in result)
    return sorted(result, key=lambda e: e["archive_path"])


def source_for(root, entry):
    return Path(root).joinpath(*entry["source_path"].split("/"))


def volume_plan(entries, target_bytes):
    if not 1024 <= target_bytes < ASSET_LIMIT:
        fail("Target size must be at least 1024 bytes and less than 2GiB")
    groups, group, used = [], [], 22
    for entry in entries:
        # Conservative deflate bound plus ZIP64/header overhead; partitioning is
        # stable by archive_path and independent of compression scheduling.
        size = entry["size_bytes"]
        estimate = size + math.ceil(size / 16384) * 5 + 1024 + 2 * len(entry["archive_path"].encode("utf-8"))
        if group and used + estimate > target_bytes:
            groups.append(group)
            group, used = [], 22
        group.append(entry)
        used += estimate
    if group:
        groups.append(group)
    return [(f"volume-{n:05d}.zip", group) for n, group in enumerate(groups, 1)]


def check_source(root, entry):
    source = source_for(root, entry)
    if source.stat().st_size != entry["size_bytes"] or digest_file(source) != entry["export_sha256"]:
        fail("Approved export input SHA256 or size mismatch: " + entry["archive_path"])


def make_volume(output, root, name, entries):
    partial = output / (name + ".partial")
    with zipfile.ZipFile(partial, "x", allowZip64=True, compresslevel=1) as archive:
        for entry in entries:
            info = zipfile.ZipInfo(entry["archive_path"], date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED if Path(entry["archive_path"]).suffix.casefold() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
            info._compresslevel = 1  # ZipInfo's supported internal equivalent on Python 3.11.
            info.file_size = entry["size_bytes"]
            h, size = hashlib.sha256(), 0
            with safe_open(source_for(root, entry)) as source, archive.open(info, "w", force_zip64=True) as target:
                while chunk := source.read(CHUNK):
                    h.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
            if size != entry["size_bytes"] or h.hexdigest() != entry["export_sha256"]:
                fail("Source changed while writing ZIP: " + entry["archive_path"])
    size = partial.stat().st_size
    if size >= ASSET_LIMIT:
        fail("Actual ZIP size is not less than 2GiB")
    final = output / name
    partial.rename(final)
    result = {"name": name, "size_bytes": size, "sha256": digest_file(final),
              "file_count": len(entries), "uncompressed_bytes": sum(e["size_bytes"] for e in entries)}
    verify_volume(output, result, entries)
    print(json.dumps({"verified_volume": name, "size_bytes": size, "file_count": len(entries)}), flush=True)
    return result


def stream_member(archive, info, entry, target=None):
    h, size = hashlib.sha256(), 0
    with archive.open(info) as stream:
        while chunk := stream.read(CHUNK):
            size += len(chunk)
            if size > entry["size_bytes"]:
                fail("ZIP member exceeds approved size")
            h.update(chunk)
            if target is not None:
                target.write(chunk)
    if size != entry["size_bytes"] or h.hexdigest() != entry["export_sha256"]:
        fail("ZIP member SHA256 or size mismatch: " + entry["archive_path"])


def verify_volume(base, volume, entries):
    path = base / volume["name"]
    if path.stat().st_size != volume["size_bytes"] or digest_file(path) != volume["sha256"]:
        fail("Volume SHA256 or size mismatch: " + volume["name"])
    expected = {e["archive_path"]: e for e in entries}
    with safe_open(path) as stream, zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        names = [relative_name(i.orig_filename) for i in infos]
        if any(i.orig_filename != i.filename for i in infos):
            fail("ZIP filenames contain hidden terminators")
        check_unique(names)
        if set(names) != set(expected) or len(infos) != volume["file_count"]:
            fail("Volume member set does not match index")
        for info in infos:
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG}):
                fail("Only regular ZIP members are allowed")
            if info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                fail("Encrypted or unsupported ZIP member")
            entry = expected[info.filename]
            if info.file_size != entry["size_bytes"]:
                fail("ZIP member header size does not match index")
            stream_member(archive, info, entry)


def pack(manifest_path, approved_sha, source_root, output, target_bytes=512*MIB, workers=4):
    checked_sha(approved_sha)
    # Credential paths are refused before opening even the approval manifest.
    relative_name(Path(manifest_path).name)
    manifest = load_bound_json(manifest_path, approved_sha)
    entries = validated_entries(manifest, source_root)
    if not 1 <= workers <= 4:
        fail("Worker count must be between 1 and 4")
    plans = volume_plan(entries, target_bytes)
    output = no_links(output)
    if output.exists():
        fail("Output directory must be new and exclusive")
    # Complete preflight before any output is created.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda e: check_source(source_root, e), entries))
    output.mkdir(parents=True, exist_ok=False)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(make_volume, output, source_root, name, group) for name, group in plans]
            volumes = [f.result() for f in futures]
        exported = []
        for name, group in plans:
            exported.extend({k:v for k,v in entry.items() if k != "source_path"} | {"volume": name} for entry in group)
        index = {"schema_version": SCHEMA, "status": "verified", "kind": "independent_zip_volumes",
                 "tool_version": "phase2-publication-v001",
                 "approved_export_manifest_sha256": approved_sha, "tool_sha256": digest_file(__file__),
                 "compression": {"deflate_level": 1, "stored_suffixes": sorted(STORED_SUFFIXES),
                                 "timestamp": "1980-01-01T00:00:00", "stable_entry_order": "archive_path"},
                 "target_volume_bytes": target_bytes, "strict_asset_limit_bytes": ASSET_LIMIT,
                 "file_count": len(entries), "uncompressed_bytes": sum(e["size_bytes"] for e in entries),
                 "redacted_file_count": sum(e["treatment"] == "redacted" for e in entries),
                 "originals_modified": False, "volumes": volumes, "entries": exported,
                 "interpretation": "export_sha256 verifies published bytes; original_sha256 identifies frozen pre-export bytes. Redacted exports do not rewrite academic originals, scores, or internal reference hashes."}
        write_json_new(output / "volume-index.json", index)
        with (output / "SHA256SUMS").open("x", encoding="ascii", newline="\n") as stream:
            for v in volumes:
                stream.write(v["sha256"] + "  " + v["name"] + "\n")
            stream.write(digest_file(output / "volume-index.json") + "  volume-index.json\n")
        return index
    except BaseException as error:
        write_json_new(output / "PACK_FAILED.json", {"status": "failed", "error_type": type(error).__name__,
                       "publishable": False, "instruction": "Preserve this failed run; rerun into a new output directory."})
        raise


def load_index(index_path, expected_sha=None):
    index = load_bound_json(index_path, expected_sha)
    if not isinstance(index, dict) or index.get("schema_version") != SCHEMA or index.get("status") != "verified" or index.get("kind") != "independent_zip_volumes":
        fail("Unsupported or incomplete volume index")
    volumes, entries = index.get("volumes"), index.get("entries")
    if not isinstance(volumes, list) or not isinstance(entries, list) or not volumes or not entries:
        fail("Index volumes and entries are required")
    names = []
    for volume in volumes:
        if not isinstance(volume, dict):
            fail("Each volume must be an object")
        name = relative_name(volume.get("name"))
        if not re.fullmatch(r"volume-[0-9]{5,}\.zip", name):
            fail("Invalid independent volume filename")
        checked_sha(volume.get("sha256"))
        if type(volume.get("size_bytes")) is not int or not 0 < volume["size_bytes"] < ASSET_LIMIT:
            fail("Invalid volume size")
        if type(volume.get("file_count")) is not int or volume["file_count"] < 1:
            fail("Invalid volume file count")
        names.append(name)
    check_unique(names)
    for entry in entries:
        if not isinstance(entry, dict):
            fail("Each export entry must be an object")
        relative_name(entry.get("archive_path"))
        checked_sha(entry.get("original_sha256")); checked_sha(entry.get("export_sha256"))
        if entry.get("volume") not in names or type(entry.get("size_bytes")) is not int or entry["size_bytes"] < 0:
            fail("Invalid entry volume or size")
        if entry.get("treatment") not in {"unchanged", "redacted"}:
            fail("Invalid entry treatment")
        if entry["treatment"] == "unchanged" and entry["original_sha256"] != entry["export_sha256"]:
            fail("Unchanged entry has different hashes")
    check_unique(e["archive_path"] for e in entries)
    if index.get("file_count") != len(entries):
        fail("Index total file count mismatch")
    if index.get("uncompressed_bytes") != sum(e["size_bytes"] for e in entries):
        fail("Index total byte count mismatch")
    for v in volumes:
        group = [e for e in entries if e["volume"] == v["name"]]
        if len(group) != v["file_count"] or sum(e["size_bytes"] for e in group) != v["uncompressed_bytes"]:
            fail("Volume declared totals mismatch")
    return index


def verify(index_path, expected_sha=None, workers=4):
    if not 1 <= workers <= 4:
        fail("Worker count must be between 1 and 4")
    index = load_index(index_path, expected_sha)
    base = no_links(Path(index_path).parent)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(verify_volume, base, v, [e for e in index["entries"] if e["volume"] == v["name"]]) for v in index["volumes"]]
        for future in futures:
            future.result()
    return index


def restore(index_path, output, expected_sha=None, workers=4):
    # Validate every byte and member before creating any restored output.
    index = verify(index_path, expected_sha, workers)
    output = no_links(output)
    if output.exists():
        fail("Restore directory must be new and exclusive")
    output.mkdir(parents=True, exist_ok=False)
    base = Path(index_path).parent
    for volume in index["volumes"]:
        expected = {e["archive_path"]:e for e in index["entries"] if e["volume"] == volume["name"]}
        with safe_open(base / volume["name"]) as stream, zipfile.ZipFile(stream) as archive:
            for name, entry in expected.items():
                target = output.joinpath(*name.split("/"))
                no_links(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as restored:
                    stream_member(archive, archive.getinfo(name), entry, restored)
    return index


def asset_index(index_path, release_json, output, expected_sha=None):
    index = load_index(index_path, expected_sha)
    release = load_json(release_json)
    assets = release.get("assets") if isinstance(release, dict) else None
    if not isinstance(assets, list):
        fail("GitHub release REST response assets list is required")
    byname = {}
    for asset in assets:
        if not isinstance(asset, dict):
            fail("Each release asset must be an object")
        name = asset.get("name")
        if name in byname:
            fail("Duplicate release asset name")
        byname[name] = asset
    result = {"schema_version": 1, "volume_index_sha256": digest_file(index_path),
              "release_html_url": release.get("html_url"), "assets": []}
    for volume in index["volumes"]:
        asset = byname.get(volume["name"])
        if not asset or asset.get("size") != volume["size_bytes"]:
            fail("Release asset missing or size differs from verified volume")
        rest_url = asset.get("url", "")
        download_url = asset.get("browser_download_url", "")
        if not rest_url.startswith("https://api.github.com/") or not download_url.startswith("https://github.com/"):
            fail("Expected official GitHub asset URLs")
        result["assets"].append(volume | {"asset_id":asset.get("id"), "rest_asset_url":rest_url,
                                        "browser_download_url":download_url})
    write_json_new(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--approved-manifest-sha256", required=True)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--target-mib", type=int, default=512)
    p.add_argument("--workers", type=int, default=4)
    for command in ["verify", "restore", "asset-index"]:
        p = sub.add_parser(command)
        p.add_argument("--index", type=Path, required=True)
        p.add_argument("--index-sha256")
        if command != "asset-index": p.add_argument("--workers", type=int, default=4)
        if command != "verify": p.add_argument("--output", type=Path, required=True)
        if command == "asset-index": p.add_argument("--release-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = pack(args.manifest, args.approved_manifest_sha256, args.source_root, args.output, args.target_mib*MIB, args.workers)
        elif args.command == "verify":
            result = verify(args.index, args.index_sha256, args.workers)
        elif args.command == "restore":
            result = restore(args.index, args.output, args.index_sha256, args.workers)
        else:
            result = asset_index(args.index, args.release_json, args.output, args.index_sha256)
        print(json.dumps({"command":args.command, "status":"passed", "file_count":result.get("file_count"), "volume_count":len(result.get("volumes", result.get("assets", [])))}))
        return 0
    except (PublicationError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as error:
        print(json.dumps({"command":args.command, "status":"failed", "error_type":type(error).__name__, "message":str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
