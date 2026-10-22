"""Immutable manifests, evidence references, and honest fixed-denominator reporting."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def contained_file(root: Path, relative: str) -> Path:
    """Resolve a reference without permitting absolute paths or symlink escape."""
    root = root.resolve(strict=True)
    entry = Path(relative)
    if entry.is_absolute() or entry.drive or ".." in entry.parts:
        raise ValueError("evidence reference must be a contained relative path")
    candidate = (root / entry).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("evidence reference escapes its root or is not a file")
    return candidate


def freeze_manifest(root: Path, files: list[str], destination: Path) -> dict:
    if len(files) != len(set(files)) or not files:
        raise ValueError("manifest paths must be nonempty and unique")
    manifest = {name: sha256(contained_file(root, name)) for name in sorted(files)}
    write_new_json(destination, {"schema_version": 1, "files": manifest})
    return manifest


def verify_manifest(root: Path, manifest: dict[str, str]) -> list[dict]:
    failures = []
    for relative, expected in manifest.items():
        try:
            actual = sha256(contained_file(root, relative))
            if actual != expected:
                failures.append({"path": relative, "reason": "hash_mismatch"})
        except (OSError, ValueError) as error:
            failures.append({"path": relative, "reason": type(error).__name__})
    return failures


def summarize_cases(case_ids: list[str], results: list[dict]) -> dict:
    """Keep unrun cases and prevent a blocked environment from implying a model score."""
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError("case denominator must be nonempty and unique")
    by_id = {}
    for row in results:
        key = row["id"]
        if key not in case_ids or key in by_id:
            raise ValueError("unknown or duplicate case result")
        by_id[key] = row
    rows = []
    for key in case_ids:
        row = by_id.get(key, {"id": key, "status": "not_run", "passed": None,
                              "ui_actions_dispatched": 0})
        if row.get("passed") not in (True, False, None) or (
            row.get("passed") is not None and not isinstance(row["passed"], bool)
        ):
            raise ValueError("passed must be a boolean or null")
        rows.append(row)
    dispatched = sum(row.get("ui_actions_dispatched", 0) for row in rows)
    passed = sum(row.get("passed") is True for row in rows)
    statuses: dict[str, int] = {}
    for row in rows:
        name = row.get("status", "unknown")
        statuses[name] = statuses.get(name, 0) + 1
    return {"case_denominator": len(case_ids), "passed_cases": passed,
            "ui_actions_dispatched": dispatched, "status_counts": statuses,
            "case_success_rate": passed / len(case_ids) if dispatched else None,
            "measurement_status": "measured" if dispatched else "not_started",
            "cases": rows}


def validate_prediction(value: dict) -> None:
    """Validate the public structure without supplying any website semantics."""
    if value.get("disposition") not in {"accepted", "rejected", "unknown"}:
        raise ValueError("invalid disposition")
    effects = value.get("effects")
    if not isinstance(effects, dict):
        raise ValueError("effects must be present")
    changed = effects.get("persistent_state_changed")
    if changed is not None and not isinstance(changed, bool):
        raise ValueError("persistent_state_changed must be boolean or null")
    count = effects.get("affected_record_count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        raise ValueError("affected_record_count must be a nonnegative integer or null")
    if not isinstance(value.get("unknowns"), list) or not all(
        isinstance(item, str) for item in value["unknowns"]
    ):
        raise ValueError("unknowns must be an array of strings")
    if not isinstance(value.get("ui_claims"), list):
        raise ValueError("ui_claims must be an array")


def validate_rules(rules: list[dict], evidence_root: Path) -> None:
    if not rules or len({rule.get("id") for rule in rules}) != len(rules):
        raise ValueError("rules must be nonempty with unique ids")
    for rule in rules:
        if not isinstance(rule.get("id"), str) or not rule["id"]:
            raise ValueError("rule id required")
        if rule.get("source_refs"):
            raise ValueError("source references are forbidden in browser-only learning")
        if rule.get("status") not in {"verified", "hypothesis", "unknown", "refuted"}:
            raise ValueError("invalid rule evidence status")
        if not isinstance(rule.get("statement"), str) or not rule["statement"].strip():
            raise ValueError("rule statement required")
        references = rule.get("evidence_refs", [])
        if not isinstance(references, list):
            raise ValueError("evidence_refs must be an array")
        if rule["status"] in {"verified", "refuted"} and not references:
            raise ValueError("verified or refuted rules require browser evidence")
        for reference in references:
            expected = reference.get("sha256")
            actual = sha256(contained_file(evidence_root, reference["path"]))
            if not isinstance(expected, str) or actual != expected:
                raise ValueError("rule evidence hash mismatch")


def validate_browser_exports(workspace: Path, private_browser: Path, rules: list[dict]) -> dict:
    """Match learner-visible evidence to originals the learner could not edit."""
    originals = {}
    for manifest in private_browser.glob("call-*/public-evidence-hashes.json"):
        hashes = json.loads(manifest.read_text(encoding="utf-8"))
        for name, expected in hashes.items():
            relative = "evidence/" + manifest.parent.name + "/" + name
            original = manifest.parent / "evidence" / name
            if sha256(original) != expected or sha256(contained_file(workspace, relative)) != expected:
                raise ValueError("browser evidence differs from its management original: " + relative)
            originals[relative] = expected
    if not originals:
        raise ValueError("no independently retained browser evidence")
    evidence = workspace / "evidence"
    if evidence.is_symlink():
        raise ValueError("browser evidence directory cannot be a symlink")
    for path in evidence.rglob("*"):
        if path.is_symlink():
            raise ValueError("browser evidence cannot contain symlinks")
        if path.is_file() and path.relative_to(workspace).as_posix() not in originals:
            raise ValueError("learner-authored file appears inside original browser evidence")
    grounded = 0
    for rule in rules:
        if rule["status"] in {"verified", "refuted"}:
            references = rule.get("evidence_refs", [])
            if not any(originals.get(ref["path"]) == ref["sha256"] for ref in references):
                raise ValueError("verified/refuted rule lacks an original browser evidence reference")
            grounded += 1
    return {"original_public_files": len(originals), "rules_with_original_evidence": grounded,
            "semantic_rule_correctness": "requires_independent_website_evaluation"}
