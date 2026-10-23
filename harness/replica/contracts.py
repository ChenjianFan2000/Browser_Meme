"""Reviewable artifact contracts and immutable registrations for replica runs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return path


def within(root, relative, *, file=True):
    root = Path(root).resolve()
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts or not part.parts:
        raise ValueError("artifact path must be workspace-relative")
    candidate = (root / part).resolve()
    candidate.relative_to(root)
    if file and not candidate.is_file():
        raise ValueError(f"missing artifact: {relative}")
    return candidate


def load_package(workspace, ready="READY.json"):
    """Validate structure, never certify the author's business claims."""
    root = Path(workspace).resolve()
    value = json.loads(within(root, ready).read_text())
    if value.get("schema_version") != 1:
        raise ValueError("READY schema_version must be 1")
    revision = value.get("revision", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", revision):
        raise ValueError("revision must be a stable plain identifier")
    for key in ("rulebook", "components", "representation", "scripts", "replica"):
        if key not in value:
            raise ValueError("missing package field: " + key)
    files = {"READY.json": digest(root / ready)}
    for key in ("rulebook", "components", "representation"):
        path = within(root, value[key])
        files[str(path.relative_to(root))] = digest(path)
    for key, default in (("coverage", "coverage.json"), ("exploration", "exploration.jsonl"),
                         ("state_export", "state-export.json")):
        name = value.get(key, default)
        if key in value or (root / name).exists():
            path = within(root, name)
            files[str(path.relative_to(root))] = digest(path)
    if not isinstance(value["scripts"], list) or not value["scripts"]:
        raise ValueError("at least one independently executable cross-page script required")
    for script in value["scripts"]:
        if not isinstance(script, dict) or not {"id", "path", "purpose"} <= script.keys():
            raise ValueError("scripts require id, path and purpose")
        path = within(root, script["path"])
        files[str(path.relative_to(root))] = digest(path)
        for module in script.get("modules", []):
            path = within(root, module)
            files[str(path.relative_to(root))] = digest(path)
    components = json.loads(within(root, value["components"]).read_text())
    rows = components.get("components", []) if isinstance(components, dict) else components
    if not isinstance(rows, list) or not rows:
        raise ValueError("component inventory must be a nonempty list")
    ids = set()
    for row in rows:
        required = {"id", "purpose", "locator", "ready_when", "read_when"}
        if not isinstance(row, dict) or not required <= row.keys():
            raise ValueError("component needs identity, purpose, locator, continuation and reading conditions")
        if row["id"] in ids:
            raise ValueError("duplicate component id")
        ids.add(row["id"])
    replica = value["replica"]
    if replica.get("kind") != "static_browser_app":
        raise ValueError("pilot v1 supports an isolated static browser app; another kind needs a versioned adapter")
    candidates = value.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    candidate_ids = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("id") or candidate["id"] in candidate_ids:
            raise ValueError("candidate ids must be present and unique")
        candidate_ids.add(candidate["id"])
    for bundle in [replica, *candidates]:
        directory = within(root, bundle["directory"], file=False)
        if not directory.is_dir():
            raise ValueError("replica directory absent")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("replica bundle may not contain symlinks")
            if path.is_file():
                files[str(path.relative_to(root))] = digest(path)
        entry = within(directory, bundle.get("entry", "index.html"))
        if entry.suffix != ".html":
            raise ValueError("replica entry must be HTML")
        if bundle.get("init_script"):
            path = within(root, bundle["init_script"])
            files[str(path.relative_to(root))] = digest(path)
    return value, files


def freeze_package(workspace, output, *, parent=None, phase="development"):
    package, hashes = load_package(workspace)
    return write_new(output, {"schema_version": 1, "phase": phase,
        "revision": package["revision"], "parent": parent,
        "workspace": str(Path(workspace).resolve()), "files": hashes,
        "bundle_directories": sorted({bundle["directory"] for bundle in
            [package["replica"], *package.get("candidates", [])]}),
        "meaning": "byte registration and contract validation, not a semantic or isolation verdict"})


def verify_registration(registration):
    record = json.loads(Path(registration).read_text())
    root = Path(record["workspace"])
    changed = [name for name, sha in record["files"].items()
               if not (root / name).is_file() or digest(root / name) != sha]
    for directory in record.get("bundle_directories", []):
        for path in (root / directory).rglob("*"):
            name = str(path.relative_to(root))
            if path.is_symlink() or path.is_file() and name not in record["files"]:
                changed.append(name)
    changed = sorted(set(changed))
    return {"passed": not changed, "changed": changed}


def snapshot_package(workspace, output_directory, *, parent=None, phase="development_revision"):
    """Copy only registered artifacts, rejecting edits during the snapshot.

    Evidence may keep growing outside the bundles. A failed copy retains its
    partial directory and error receipt but never gains a registration.
    """
    source = Path(workspace).resolve()
    out = Path(output_directory).resolve()
    if out == source or source in out.parents:
        raise ValueError("snapshot output must be outside author workspace")
    package, hashes = load_package(source)
    out.mkdir(parents=True, exist_ok=False)
    destination = out / "package"
    destination.mkdir()
    try:
        for name, expected in hashes.items():
            path = within(source, name)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            if digest(path) != expected or digest(target) != expected:
                raise ValueError("artifact changed during snapshot: " + name)
        final_package, final_hashes = load_package(source)
        copied_package, copied_hashes = load_package(destination)
        if final_package != package or final_hashes != hashes:
            raise ValueError("author manifest or bundle changed during snapshot")
        if copied_package != package or copied_hashes != hashes:
            raise ValueError("snapshot does not match registered source artifacts")
        registration = freeze_package(destination, out / "registration.json", parent=parent, phase=phase)
        write_new(out / "snapshot.json", {"source_workspace": str(source),
            "revision": package["revision"], "file_count": len(hashes),
            "time_ns": time.time_ns(), "source_and_copy_hashes_equal": True,
            "meaning": "artifact snapshot only; no semantic success claim"})
        return {"registration": str(registration), "package": str(destination),
                "revision": package["revision"], "file_count": len(hashes)}
    except Exception as error:
        write_new(out / "snapshot-failure.json", {"type": type(error).__name__,
            "message": str(error), "time_ns": time.time_ns(), "registered": False})
        raise


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="Copy registered author artifacts to a new frozen package")
    snapshot.add_argument("--workspace", required=True)
    snapshot.add_argument("--out", required=True)
    snapshot.add_argument("--parent")
    snapshot.add_argument("--phase", default="development_revision")
    verify = commands.add_parser("verify", help="Check a frozen registration and complete bundle membership")
    verify.add_argument("--registration", required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot_package(args.workspace, args.out, parent=args.parent, phase=args.phase)
    else:
        result = verify_registration(args.registration)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
