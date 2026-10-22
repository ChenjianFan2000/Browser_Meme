"""Narrow new export version: .log is mixed UTF-8 text, not forced JSONL.

The pinned parent exporter and all strict JSON/JSONL policies stay unchanged.
Use only for separately inventoried retry items; do not overwrite old runs.
"""
from contextlib import contextmanager
from pathlib import Path

import export_evidence as base


PARENT_SHA256 = "fbbaea885afae45876d8f67e7b5aea298908e1b510d2a75c24d063857e001ec5"
ORIGINAL_TRANSFORM = base.transform_stream
ORIGINAL_WRITE = base.write_new


def transform_log_text(source,target,filename,counts,*,depth=0,archive_exclusions=None,logical_path=None):
    if Path(filename).suffix.casefold() != ".log":
        return ORIGINAL_TRANSFORM(source,target,filename,counts,depth=depth,archive_exclusions=archive_exclusions,logical_path=logical_path)
    if depth > base.MAX_DEPTH:
        raise ValueError("nested archive limit")
    head=source.read(4096); source.seek(0)
    # File extensions cannot turn binary/archives into text or bypass their
    # inspection. Known binaries remain unchanged or fail on credential bytes.
    if head.startswith((b"PK\x03\x04",b"PK\x05\x06")) or base._binary_kind(head):
        return ORIGINAL_TRANSFORM(source,target,filename,counts,depth=depth,archive_exclusions=archive_exclusions,logical_path=logical_path)
    data=source.read(base.MAX_TEXT+1)
    if len(data)<=base.MAX_TEXT:
        clean=base._redact_text(data,counts,strict=False)
        target.write(clean)
        return clean!=data
    # Preserve the parent's bounded-memory fallback for large ordinary text.
    source.seek(0); changed=False
    while line:=source.readline(base.MAX_LINE+1):
        if len(line)>base.MAX_LINE:
            raise ValueError("oversized text log record requires explicit review")
        clean=base._redact_text(line,counts,strict=False)
        target.write(clean); changed=changed or clean!=line
    return changed


def write_with_lineage(path,value):
    if Path(path).name=="export-manifest.pending.json":
        value=dict(value)
        value["parent_generator_sha256"]=value["generator_sha256"]
        value["generator_sha256"]=base.file_hash(Path(__file__))
        value["generator_version"]="ordinary_log_text_v002"
        value["format_policy"]={"changed_suffixes":[".log"],"ordinary_log":"mixed UTF-8 text with parsed JSON fragments and unchanged credential checks",
                                "strict_structured_formats":"parent .json/.jsonl/.trace/.network unchanged"}
    ORIGINAL_WRITE(path,value)


@contextmanager
def log_text_policy():
    if base.file_hash(Path(base.__file__))!=PARENT_SHA256:
        raise ValueError("pinned parent exporter SHA256 mismatch")
    old_transform,old_write=base.transform_stream,base.write_new
    base.transform_stream,base.write_new=transform_log_text,write_with_lineage
    try:
        yield
    finally:
        base.transform_stream,base.write_new=old_transform,old_write


def main():
    with log_text_policy():
        base.main()


if __name__=="__main__": main()
