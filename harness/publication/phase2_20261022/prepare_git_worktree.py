"""Copy a reviewable Git subset of approved export bytes into a clean worktree."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from urllib.parse import unquote


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def within(root, relative):
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(p in {"", ".", ".."} or ":" in p for p in rel.parts):
        raise ValueError("invalid relative path")
    result = root.joinpath(*rel.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("uncontained path")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    source_root = Path(args.source_root).resolve(strict=True)
    target = Path(args.worktree).resolve(strict=True)
    receipt = Path(args.receipt)
    if receipt.exists():
        raise ValueError("receipt already exists")
    manifest = Path(args.manifest)
    if sha(manifest) != args.manifest_sha256:
        raise ValueError("manifest digest mismatch")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data["status"] != "approved_for_publication" or data.get("failures"):
        raise ValueError("manifest is not approved")
    if not target.is_relative_to(source_root / ".runtime" / "publication-phase2-20261022"):
        raise ValueError("unexpected publication worktree")
    if not (target / ".git").is_file():
        raise ValueError("linked worktree required")
    status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                            cwd=target, capture_output=True, text=True, check=True)
    if status.stdout.strip():
        raise ValueError("publication worktree must be clean")
    exp = "harness/experiments/phase2-discogs-20261021-01"
    prefixes = ("harness/phase2/", "harness/phase2_isolation/",
                "harness/sites/discogs/phase2_private/", "harness/publication/phase2_20261022/")
    section_prefixes = tuple(exp + "/" + p + "/" for p in
                             ("reports", "reviews", "handoff", "isolation", "batches", "private/audit"))
    rows = {row["archive_path"]: row for row in data["entries"]}
    if len(rows) != len(data["entries"]):
        raise ValueError("duplicate archive paths")
    selected = set()
    for name in rows:
        parts = PurePosixPath(name).parts
        if (name in {"README.md", "harness/sites/discogs/loop_deploy.py"}
            or name.startswith(prefixes)
            or (name.startswith("harness/tests/test_phase2_") and name.endswith(".py"))
            or name.startswith(section_prefixes)
            or (name.startswith(exp + "/") and len(parts) == 4)
            or name.startswith(exp + "/evaluations/a-seed-1729/case-01/")):
            selected.add(name)
        if name.startswith(exp + "/runs/"):
            tail = PurePosixPath(name[len(exp) + 1:]).parts
            if len(tail) == 3 or (len(tail) == 4 and tail[2] == "workspace") or "workspace/revisions/" in name:
                selected.add(name)
    # Follow only actual local links of the chosen, already approved example.
    example = rows[exp + "/reports/evidence-example-001.md"]
    markdown = within(source_root, example["source_path"]).read_text(encoding="utf-8")
    example_parent = source_root / exp / "reports"
    for url in re.findall(r"\[[^\]]*\]\(([^\)]+)\)", markdown):
        url = unquote(url.strip("<>").split("#", 1)[0])
        if not url or "://" in url:
            continue
        path = (example_parent / url).resolve()
        if path.is_relative_to(source_root):
            relative = path.relative_to(source_root).as_posix()
            if relative in rows:
                selected.add(relative)
    chosen = [rows[name] for name in sorted(selected)]
    for row in chosen:
        original = within(source_root, row["source_path"])
        if sha(original) != row["export_sha256"] or original.stat().st_size != row["export_size"]:
            raise ValueError("approved export changed")
        output = within(target, row["archive_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, output)
        if sha(output) != row["export_sha256"]:
            raise ValueError("copied file digest mismatch")
    result = {"schema_version": 1, "status": "approved_bytes_copied_not_committed",
              "manifest_sha256": args.manifest_sha256, "worktree": str(target),
              "files": len(chosen), "bytes": sum(x["export_size"] for x in chosen),
              "entries": [{k: row[k] for k in ("archive_path", "export_sha256", "export_size", "treatment")}
                          for row in chosen], "frozen_originals_modified": False}
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"receipt": str(receipt), "files": result["files"], "bytes": result["bytes"]}))


if __name__ == "__main__":
    main()
