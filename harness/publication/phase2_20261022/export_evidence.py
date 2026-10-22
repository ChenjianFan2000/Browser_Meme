"""Bounded, fail-closed export copies; originals and approval remain separate.

No website rules are implemented here. Only an independent auditor can promote
the pending manifest into the packer's approved manifest.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import zipfile

import package as common


SENTINEL = "[REDACTED_AUTH]"
CHUNK = 1024 * 1024
SPOOL_MEMORY = 8 * CHUNK
MAX_TEXT = 32 * CHUNK
MAX_LINE = 16 * CHUNK
MAX_MEMBER = 512 * CHUNK
MAX_DEPTH = 5
PROHIBITED_NAMES = common.DENIED_NAMES | {"cookies.sqlite", "storage.sqlite"}
PROHIBITED_PARTS = common.DENIED_PARTS | {"venv", ".next"}
CACHE_PARTS = {"cache", "caches", ".cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SENSITIVE_KEYS = {"authorization", "proxyauthorization", "cookie", "setcookie", "xapikey", "xauthtoken",
                  "password", "passwd", "pwd", "clientsecret", "accesstoken", "refreshtoken", "idtoken",
                  "apikey", "secretaccesskey", "sessiontoken", "csrftoken", "token", "privatekey",
                  "awssecretaccesskey", "awsaccesskeyid", "accesskeyid"}
HEADERS = {"authorization", "proxyauthorization", "cookie", "setcookie", "xapikey", "xauthtoken"}
PATTERNS = {
    "jwt": re.compile(rb"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}"),
    "provider_key": re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "google_api_key": re.compile(rb"\bAIza[A-Za-z0-9_-]{30,}"),
    "slack_token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----", re.S),
    "bearer_value": re.compile(rb"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/-]{12,}=*"),
}
TEXT_PATTERNS = {k: re.compile(p.pattern.decode("ascii"), p.flags) for k,p in PATTERNS.items()}
PRIVATE_START = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")
TEXT_SUFFIXES = {".html", ".htm", ".txt", ".log", ".md", ".py", ".js", ".cjs", ".mjs", ".css",
                 ".toml", ".yaml", ".yml", ".config", ".csv", ".svg", ".xml", ".sh", ".ps1", ".sql", ".htc", ".tag"}
LINE_SUFFIXES = {".jsonl", ".trace", ".network"}
HEADER_LINE = re.compile(r"(?im)^[ \t]*(?:Authorization|Proxy-Authorization|Cookie|Set-Cookie|X-Api-Key|X-Auth-Token)[ \t]*:[ \t]*([^\r\n]+)")
DECODER = json.JSONDecoder(parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON constant")))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return common.digest_file(path)


def write_new(path, value):
    common.no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def relative_path(value):
    return PurePosixPath(common.relative_name(value, protected=False))


def contained(root, relative):
    root = common.no_links(root)
    p = root.joinpath(*relative_path(relative).parts)
    common.no_links(p)
    q = p.resolve(strict=True)
    if not q.is_relative_to(root.resolve()) or not q.is_file():
        raise ValueError("source containment or regular-file check failed")
    return q


def excluded(relative):
    p = relative_path(relative)
    names = {x.casefold() for x in p.parts}
    name = p.name.casefold()
    if names & CACHE_PARTS or p.suffix.casefold() in {".pyc", ".pyo", ".cache-9"}:
        return "reconstructible_cache_not_experiment_result"
    if names & PROHIBITED_PARTS or name in PROHIBITED_NAMES or name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".key")):
        return "authentication_or_installation_store_not_read"
    return None


def norm(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _ws(text, pos):
    while pos < len(text) and text[pos] in " \t\r\n":
        pos += 1
    return pos


class Node:
    def __init__(self, kind, start, end, value=None, children=None):
        self.kind, self.start, self.end = kind, start, end
        self.value, self.children = value, children or []


def _parse(text, pos=0, depth=0):
    if depth > 90:
        raise ValueError("JSON nesting limit")
    pos = _ws(text, pos)
    start = pos
    if pos >= len(text):
        raise ValueError("incomplete JSON")
    token = text[pos]
    if token == "{":
        pos = _ws(text, pos + 1)
        children = []
        if pos < len(text) and text[pos] == "}": return Node("object", start, pos + 1),pos+1
        while True:
            key, pos = _parse(text, pos, depth+1)
            if key.kind != "string": raise ValueError("JSON object key must be string")
            pos = _ws(text, pos)
            if pos >= len(text) or text[pos] != ":": raise ValueError("JSON object colon missing")
            child, pos = _parse(text, pos+1, depth+1)
            children.append((key.value,child))
            pos = _ws(text,pos)
            if pos >= len(text): raise ValueError("incomplete JSON object")
            if text[pos] == "}": return Node("object",start,pos+1,children=children),pos+1
            if text[pos] != ",": raise ValueError("JSON object separator missing")
            pos = _ws(text,pos+1)
    if token == "[":
        pos = _ws(text,pos+1)
        children=[]
        if pos < len(text) and text[pos] == "]": return Node("array",start,pos+1),pos+1
        while True:
            child,pos = _parse(text,pos,depth+1)
            children.append(child)
            pos = _ws(text,pos)
            if pos >= len(text): raise ValueError("incomplete JSON array")
            if text[pos] == "]": return Node("array",start,pos+1,children=children),pos+1
            if text[pos] != ",": raise ValueError("JSON array separator missing")
            pos = _ws(text,pos+1)
    try:
        value,end=DECODER.raw_decode(text,pos)
    except (ValueError,RecursionError):
        raise ValueError("invalid JSON value") from None
    return Node("string" if isinstance(value,str) else "scalar",start,end,value=value),end


def _string_boundaries(text,node):
    # Map decoded-character boundaries back into the original JSON literal.
    # This keeps unrelated escape spelling and whitespace byte-for-byte.
    positions=[node.start+1]
    pos=node.start+1
    while pos < node.end-1:
        if text[pos] != "\\":
            pos+=1
        elif text[pos+1] != "u":
            pos+=2
        else:
            code=int(text[pos+2:pos+6],16)
            pos+=6
            if 0xD800 <= code <= 0xDBFF and text[pos:pos+2] == "\\u":
                low=int(text[pos+2:pos+6],16)
                if 0xDC00 <= low <= 0xDFFF: pos+=6
        positions.append(pos)
    if len(positions) != len(node.value)+1:
        raise ValueError("unsupported JSON string character mapping")
    return positions


def _replaceable(node):
    if node.kind in {"object","array"}: return bool(node.children)
    return node.value is not None and node.value != "" and node.value != SENTINEL


def _walk(text,node,counts,spans,*,cookies=False,synthetic=False,depth=0):
    if depth > 10: raise ValueError("embedded JSON nesting limit")
    if node.kind == "object":
        base64_flag=any((norm(k)=="encoding" and isinstance(c.value,str) and c.value.casefold()=="base64")
                        or (norm(k)=="base64encoded" and c.value is True)
                        or (norm(k)=="type" and c.value=="base64") for k,c in node.children)
        handled=set()
        if base64_flag:
            payloads=[c for k,c in node.children if norm(k) in {"text","body","data"}]
            if not payloads: raise ValueError("base64 record without supported payload requires explicit review")
            for child in payloads:
                if child.kind!="string": raise ValueError("non-string base64 payload requires explicit review")
                handled.add(id(child))
                if not child.value: continue
                try: decoded=base64.b64decode("".join(child.value.split()),validate=True)
                except (ValueError,binascii.Error): raise ValueError("invalid base64 payload requires explicit review") from None
                if len(decoded)>MAX_TEXT: raise ValueError("oversized base64 payload requires explicit review")
                if decoded.startswith((b"PK\x03\x04",b"PK\x05\x06")):
                    raise ValueError("base64-encoded archive requires explicit review")
                if _binary_kind(decoded[:4096]):
                    with io.BytesIO(decoded) as source: _binary_copy(source,None)
                    clean=decoded
                else:
                    structured=decoded.lstrip(b" \t\r\n\xef\xbb\xbf").startswith((b"{",b"["))
                    try: clean=_redact_text(decoded,counts,strict=structured,depth=depth+1)
                    except ValueError:
                        if not structured: raise
                        cleaned=[]
                        for line in decoded.splitlines(keepends=True):
                            if len(line)>MAX_LINE: raise ValueError("oversized base64 JSONL record")
                            cleaned.append(_redact_text(line,counts,strict=True,depth=depth+1) if line.strip() else line)
                        clean=b"".join(cleaned)
                if clean!=decoded:
                    spans.append((child.start,child.end,json.dumps(base64.b64encode(clean).decode("ascii"))))
                    counts["base64_payload"]+=1
        synthetic = synthetic or any(k == "is_real_credential" and c.value is False for k,c in node.children)
        header = any(norm(k) in {"name","key"} and isinstance(c.value,str) and norm(c.value) in HEADERS|SENSITIVE_KEYS for k,c in node.children)
        cookie_value_form = any(norm(k) == "value" for k,_ in node.children)
        for key,child in node.children:
            if id(child) in handled: continue
            keynorm=norm(key)
            sensitive=keynorm in SENSITIVE_KEYS or keynorm == "value" and (cookies or header)
            if cookies and not cookie_value_form: sensitive=True
            if keynorm == "cookies" and child.kind not in {"object","array"}: sensitive=True
            if keynorm in {"password","passwd","pwd"} and synthetic: sensitive=False
            if sensitive and _replaceable(child):
                spans.append((child.start,child.end,json.dumps(SENTINEL)))
                counts["structured_auth_value"]+=1
            else:
                _walk(text,child,counts,spans,cookies=keynorm == "cookies",synthetic=synthetic,depth=depth)
    elif node.kind == "array":
        for child in node.children: _walk(text,child,counts,spans,cookies=cookies,synthetic=synthetic,depth=depth)
    elif node.kind == "string":
        inner=_text_spans(node.value,counts,strict=False,depth=depth+1)
        if inner:
            bounds=_string_boundaries(text,node)
            for a,b,replacement in inner:
                spans.append((bounds[a],bounds[b],json.dumps(replacement,ensure_ascii=True)[1:-1]))


def _clean_spans(spans):
    result=[]
    for a,b,value in sorted(spans,key=lambda x:(x[0],-x[1])):
        if result and a < result[-1][1]:
            if b <= result[-1][1]: continue
            raise ValueError("overlapping credential spans require review")
        result.append((a,b,value))
    return result


def _text_spans(text,counts,*,strict=False,depth=0):
    spans=[]
    if strict:
        start=1 if text.startswith("\ufeff") else 0
        node,end=_parse(text,start)
        if _ws(text,end) != len(text): raise ValueError("trailing or malformed JSON record")
        _walk(text,node,counts,spans,depth=depth)
    else:
        pos=0
        while pos < len(text):
            found=re.compile(r"[\[{]").search(text,pos)
            if not found: break
            start=found.start()
            try:
                node,end=_parse(text,start)
            except ValueError:
                pos=start+1
                continue
            _walk(text,node,counts,spans,depth=depth)
            pos=end
    for name,pattern in TEXT_PATTERNS.items():
        for match in pattern.finditer(text):
            spans.append((match.start(),match.end(),SENTINEL))
            counts[name]+=1
    for match in re.finditer(PRIVATE_START.pattern.decode("ascii"),text):
        if not any(a<=match.start() and match.end()<=b for a,b,_ in spans):
            raise ValueError("incomplete private key block requires explicit review")
    for match in HEADER_LINE.finditer(text):
        if match.group(1) != SENTINEL:
            spans.append((match.start(1),match.end(1),SENTINEL))
            counts["raw_auth_header"]+=1
    return _clean_spans(spans)


def _redact_text(data,counts,*,strict=False,depth=0):
    try: text=data.decode("utf-8")
    except UnicodeDecodeError: raise ValueError("text format is not UTF-8; explicit review required") from None
    if any(c in data for c in (b"\x00",b"\x01",b"\x02",b"\x03",b"\x04",b"\x05",b"\x06",b"\x07",b"\x08")):
        raise ValueError("binary control bytes in presumed text require explicit review")
    spans=_text_spans(text,counts,strict=strict,depth=depth)
    if not spans: return data
    pieces=[]; pos=0
    for a,b,replacement in spans:
        pieces.extend([text[pos:a],replacement]); pos=b
    pieces.append(text[pos:])
    return "".join(pieces).encode("utf-8")


def _binary_kind(head):
    return (head.startswith((b"\x89PNG\r\n\x1a\n",b"\xff\xd8\xff",b"GIF87a",b"GIF89a",b"%PDF-",b"wOFF",b"wOF2",b"OTTO",b"\x00\x01\x00\x00"))
            or head[:4] == b"RIFF" and head[8:12] == b"WEBP"
            or len(head)>12 and head[4:8] == b"ftyp")


def _binary_copy(source,target):
    carry=b""
    while chunk:=source.read(CHUNK):
        scan=carry+chunk
        if PRIVATE_START.search(scan) or any(p.search(scan) for p in PATTERNS.values()):
            raise ValueError("credential-like bytes in binary require explicit review; binary not modified")
        if target is not None: target.write(chunk)
        carry=scan[-8192:]


def transform_stream(source,target,filename,counts,*,depth=0,archive_exclusions=None,logical_path=None):
    if depth > MAX_DEPTH: raise ValueError("nested archive limit")
    archive_exclusions=[] if archive_exclusions is None else archive_exclusions
    logical_path=filename if logical_path is None else logical_path
    head=source.read(4096); source.seek(0)
    suffix=Path(filename).suffix.casefold()
    if suffix == ".zip" or head.startswith((b"PK\x03\x04",b"PK\x05\x06")):
        return _zip_stream(source,target,counts,depth,archive_exclusions,logical_path)
    if _binary_kind(head):
        _binary_copy(source,target)
        return False
    stripped=head.lstrip(b" \t\r\n\xef\xbb\xbf")
    is_json=suffix == ".json" or stripped.startswith((b"{",b"["))
    is_lines=suffix in LINE_SUFFIXES
    is_text=suffix in TEXT_SUFFIXES or stripped.lower().startswith((b"<!doctype html",b"<html",b"<?xml",b"<svg"))
    # Unknown suffixes and extensionless resources can be ordinary UTF-8 text.
    # They undergo the same full text checks; undecodable/control-rich bytes
    # fail closed rather than being scrubbed as arbitrary binary.
    if is_lines:
        changed=False
        while line:=source.readline(MAX_LINE+1):
            if len(line)>MAX_LINE: raise ValueError("oversized JSONL record requires explicit review")
            clean=_redact_text(line,counts,strict=True) if line.strip() else line
            target.write(clean); changed=changed or clean!=line
        return changed
    data=source.read(MAX_TEXT+1)
    if len(data)>MAX_TEXT:
        # Large JSON/opaque JSON may be JSONL, but only complete valid records
        # are accepted. Arbitrary oversized text cannot bypass this boundary.
        if is_json:
            source.seek(0)
            return transform_stream(source,target,"stream.jsonl",counts,depth=depth,archive_exclusions=archive_exclusions,logical_path=logical_path)
        source.seek(0); changed=False
        while line:=source.readline(MAX_LINE+1):
            if len(line)>MAX_LINE: raise ValueError("oversized text record requires explicit review")
            clean=_redact_text(line,counts)
            target.write(clean); changed=changed or clean!=line
        return changed
    if is_json:
        try:
            clean=_redact_text(data,counts,strict=True)
        except ValueError:
            # Support mislabeled JSONL, while rejecting every malformed line.
            source.seek(0)
            return transform_stream(source,target,"stream.jsonl",counts,depth=depth,archive_exclusions=archive_exclusions,logical_path=logical_path)
    else:
        clean=_redact_text(data,counts)
    target.write(clean)
    return clean!=data


def _zip_stream(source,target,counts,depth,exclusions,logical_path):
    changed=False
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as output:
        seen=set(); files=[]
        comment=_redact_text(archive.comment,counts) if archive.comment else b""
        output.comment=comment; changed=comment!=archive.comment
        for member in archive.infolist():
            rawname=member.orig_filename
            if rawname != member.filename: raise ValueError("ZIP filename terminator rejected")
            canonical=rawname[:-1] if rawname.endswith("/") else rawname
            relative_path(canonical)
            if canonical.casefold() in seen: raise ValueError("duplicate or case-colliding ZIP member")
            seen.add(canonical.casefold())
            mode=member.external_attr>>16
            if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0,stat.S_IFREG,stat.S_IFDIR}:
                raise ValueError("ZIP member link or special file rejected")
            reason=excluded(canonical)
            if reason:
                counts["excluded_archive_"+reason]+=1; changed=True
                exclusions.append({"path":logical_path+"!"+canonical,"reason":reason,"content_read_or_hashed":False})
                continue
            if member.is_dir():
                output.writestr(copy.copy(member),b"")
                continue
            files.append(canonical)
            if member.flag_bits&1 or member.compress_type not in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED}:
                raise ValueError("encrypted or unsupported ZIP member")
            if member.file_size>MAX_MEMBER: raise ValueError("oversized ZIP member requires explicit review")
            if PRIVATE_START.search(member.extra) or any(p.search(member.extra) for p in PATTERNS.values()):
                raise ValueError("credential-like binary ZIP metadata requires explicit review")
            with tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY) as raw, tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY) as clean:
                with archive.open(member) as stream: shutil.copyfileobj(stream,raw,CHUNK)
                raw.seek(0)
                member_changed=transform_stream(raw,clean,canonical,counts,depth=depth+1,archive_exclusions=exclusions,logical_path=logical_path+"!"+canonical)
                info=copy.copy(member)
                if info.comment:
                    info.comment=_redact_text(info.comment,counts)
                changed=changed or member_changed or info.comment!=member.comment
                info._compresslevel=1
                selected=clean if member_changed else raw
                selected.seek(0,2); info.file_size=selected.tell(); selected.seek(0)
                with output.open(info,"w",force_zip64=True) as stream: shutil.copyfileobj(selected,stream,CHUNK)
        common.check_unique(files)
    return changed


def redact_bytes(data,filename,*,depth=0):
    """Small synthetic-test helper; actual exports use streaming file handles."""
    if excluded(filename): raise ValueError("excluded authentication/cache input must not be inspected")
    counts=Counter()
    with io.BytesIO(data) as source, tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY) as target:
        changed=transform_stream(source,target,filename,counts,depth=depth)
        target.seek(0)
        return (target.read() if changed else data),counts


def inventory(args):
    root=common.no_links(args.source_root).resolve(strict=True)
    candidates={}; excluded_roots=[]
    def add(source,archive=None,**extra):
        source=relative_path(source).as_posix(); archive=relative_path(archive or source).as_posix()
        row={"source_path":source,"archive_path":archive}|extra
        if source in candidates and candidates[source]["archive_path"] != archive:
            raise ValueError("source has conflicting restoration mappings")
        candidates[source]=row
    for name in args.root:
        rel=relative_path(name).as_posix(); folder=root/rel
        common.no_links(folder)
        if not folder.is_dir(): raise ValueError("explicit inventory root is not a directory")
        reason=excluded(rel)
        if reason:
            excluded_roots.append({"source_path":rel,"reason":reason,"content_read_or_hashed":False})
            continue
        def walk_error(_): raise ValueError("inventory traversal failed; no silent omissions")
        for current,dirs,names in os.walk(folder,followlinks=False,onerror=walk_error):
            kept=[]
            for name in sorted(dirs):
                child=Path(current)/name
                common.no_links(child)  # Explicit refusal, including Windows junctions.
                child_rel=child.relative_to(root).as_posix(); reason=excluded(child_rel)
                if reason: excluded_roots.append({"source_path":child_rel,"reason":reason,"content_read_or_hashed":False})
                else: kept.append(name)
            dirs[:]=kept
            for filename in sorted(names):
                p=Path(current)/filename; common.no_links(p)
                add(p.relative_to(root).as_posix())
    for name in args.file:
        rel=relative_path(name).as_posix()
        common.no_links(root/rel)
        if not excluded(rel): contained(root,rel)
        add(rel)
    external_refs=[]
    for name in args.runtime_inventory:
        path=common.no_links(name).resolve(strict=True)
        value=common.load_json(path)
        external_refs.append({"path":str(path),"sha256":file_hash(path)})
        for entry in value["entries"]:
            source=Path(entry["source_path"])
            if not source.is_absolute(): source=root/source
            common.no_links(source)
            source=Path(os.path.abspath(source)).relative_to(root).as_posix()
            archive=relative_path(entry["archive_path"]).as_posix()
            restore=relative_path(entry["restore_path"]).as_posix()
            common.checked_sha(entry["sha256"])
            add(source,archive,restore_path=restore,expected_original_sha256=entry["sha256"])
    entries=sorted(candidates.values(),key=lambda x:x["archive_path"])
    common.check_unique(x["archive_path"] for x in entries)
    value={"schema_version":1,"status":"inventory_only_not_publication_approval",
           "created_at_utc":datetime.now(timezone.utc).isoformat(),"entries":entries,
           "excluded_roots":excluded_roots,"runtime_inventories":external_refs,"source_root":str(root)}
    write_new(Path(args.output),value)
    print(json.dumps({"output":args.output,"entries":len(entries),"excluded_roots":len(excluded_roots)}))


def export(args):
    if not 1<=args.workers<=4: raise ValueError("export workers must be between 1 and 4")
    root=common.no_links(args.source_root).resolve(strict=True)
    inventory_path=common.no_links(args.inventory).resolve(strict=True)
    inventory_data=common.load_json(inventory_path)
    if inventory_data.get("status") != "inventory_only_not_publication_approval": raise ValueError("unsupported or blocked inventory")
    rows=inventory_data["entries"]
    common.check_unique(relative_path(row["archive_path"]).as_posix() for row in rows)
    destination=common.no_links(args.output_dir)
    if not destination.is_relative_to(root): raise ValueError("export destination must be inside explicit source root")
    if any(root.joinpath(*relative_path(row["source_path"]).parts).is_relative_to(destination) for row in rows):
        raise ValueError("export destination overlaps inventoried inputs")
    destination.mkdir(parents=True,exist_ok=False)
    entries=[]; exclusions=list(inventory_data.get("excluded_roots",[])); failures=[]
    def process(row):
        source=relative_path(row["source_path"]).as_posix()
        archive=relative_path(row["archive_path"]).as_posix()
        reason=excluded(source) or excluded(archive)
        if reason:
            return "excluded",{"source_path":source,"archive_path":archive,"reason":reason,"content_read_or_hashed":False}
        path=contained(root,source)
        original_hash=file_hash(path); original_size=path.stat().st_size
        if row.get("expected_original_sha256",original_hash)!=original_hash: raise ValueError("inventory original hash changed")
        counts=Counter(); archive_exclusions=[]
        with common.safe_open(path) as raw, tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY) as cleaned:
            changed=transform_stream(raw,cleaned,path.name,counts,archive_exclusions=archive_exclusions,logical_path=archive)
            if file_hash(path)!=original_hash: raise ValueError("source changed during export")
            if changed:
                output=destination/"files"/archive
                common.no_links(output); output.parent.mkdir(parents=True,exist_ok=True)
                cleaned.seek(0); h=hashlib.sha256(); export_size=0
                with output.open("xb") as stream:
                    while chunk:=cleaned.read(CHUNK): h.update(chunk); export_size+=len(chunk); stream.write(chunk)
                export_hash=h.hexdigest(); output_source=output.relative_to(root).as_posix(); treatment="redacted"
            else:
                export_hash=original_hash; export_size=original_size; output_source=source; treatment="unchanged"
        return "entry",{"source_path":output_source,"original_source_path":source,"archive_path":archive,
                        "restore_path":row.get("restore_path",archive),"original_sha256":original_hash,
                        "export_sha256":export_hash,"original_size":original_size,"export_size":export_size,
                        "treatment":treatment,"redaction_counts":dict(counts),"archive_exclusions":archive_exclusions}
    # At most 2*workers futures, not one future for each of ~100k files.
    iterator=iter(rows); processed=0; started=time.monotonic(); last_progress=started
    print(json.dumps({"export_started":True,"inventory_entries":len(rows),"workers":args.workers}),flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending={}
        def fill():
            while len(pending)<2*args.workers:
                row=next(iterator,None)
                if row is None: break
                pending[pool.submit(process,row)]=row
        fill()
        while pending:
            done,_=wait(pending,timeout=15,return_when=FIRST_COMPLETED)
            for future in done:
                row=pending.pop(future)
                try:
                    kind,value=future.result(); (entries if kind=="entry" else exclusions).append(value)
                except Exception as error:
                    failures.append({"source_path":row["source_path"],"error_type":type(error).__name__,
                                     "reason":str(error) if isinstance(error,ValueError) else "processing_error"})
                processed+=1
            now=time.monotonic()
            if now-last_progress>=15 or processed and processed%5000==0:
                print(json.dumps({"processed":processed,"pending":len(pending),"redacted":sum(x["treatment"]=="redacted" for x in entries),"failures":len(failures),"elapsed_seconds":round(now-started,1)}),flush=True)
                last_progress=now
            fill()
    value={"schema_version":1,"status":"export_blocked" if failures else "exported_pending_independent_approval",
           "created_at_utc":datetime.now(timezone.utc).isoformat(),"inventory_sha256":file_hash(inventory_path),
           "generator_sha256":file_hash(Path(__file__)),"source_root":str(root),"entries":sorted(entries,key=lambda x:x["archive_path"]),
           "exclusions":sorted(exclusions,key=lambda x:x["source_path"]),"failures":sorted(failures,key=lambda x:x["source_path"]),
           "counts":{"included":len(entries),"excluded":len(exclusions),"redacted":sum(x["treatment"]=="redacted" for x in entries)},
           "originals_modified":False,"secret_values_in_logs":False,"not_yet_approved_for_publication":True,
           "memory_bounds":{"workers":args.workers,"pending_futures_max":2*args.workers,"spool_memory_bytes":SPOOL_MEMORY,
                            "single_text_bytes":MAX_TEXT,"jsonl_record_bytes":MAX_LINE,"archive_member_bytes":MAX_MEMBER},
           "limitations":["Pattern and format checks do not prove all arbitrary secrets absent; independent export-content audit is required.",
                          "Known binary formats remain byte-identical; recognized credential bytes in them block export.",
                          "Unknown binary formats, malformed structured records, unsupported encodings and oversized records block export; unknown UTF-8 text is still fully scanned.",
                          "Changed ZIP containers may be recompressed; unchanged member payloads remain byte-identical."]}
    write_new(destination/"export-manifest.pending.json",value)
    print(json.dumps({"manifest":str(destination/"export-manifest.pending.json"),"counts":value["counts"],"failures":len(failures)}))
    if failures: raise SystemExit(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    inv=sub.add_parser("inventory")
    inv.add_argument("--source-root",required=True)
    inv.add_argument("--root",action="append",default=[])
    inv.add_argument("--file",action="append",default=[])
    inv.add_argument("--runtime-inventory",action="append",default=[])
    inv.add_argument("--output",required=True)
    exp=sub.add_parser("export")
    exp.add_argument("--source-root",required=True)
    exp.add_argument("--inventory",required=True)
    exp.add_argument("--output-dir",required=True)
    exp.add_argument("--workers",type=int,choices=range(1,5),default=4)
    args=parser.parse_args()
    (inventory if args.command=="inventory" else export)(args)


if __name__=="__main__": main()
