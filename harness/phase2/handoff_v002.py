"""Strict versioned management handoff; never reads learner code or task semantics."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from .report_v002 import read, checked_manifest, schedule_runs, build_report
from .records import sha256, write_new_json, validate_browser_exports, validate_rules
from .run_learning import EXPERIMENT, management_barrier_passed

RUN_CHECKS = {"manifest_integrity", "browser_exports_match_originals", "evidence_references_valid",
              "condition_artifact_contract", "observation_boundary_compliance", "frozen_version_lineage",
              "budgets_and_stopping_accounted", "rule_claims_audited", "novelty_and_coverage_claims_audited",
              "limitations_and_unknowns_preserved"}
TOP_CHECKS = {"six_identity_bindings", "formal_schedule_binding", "candidate_freeze_binding",
              "learning_review_report_binding", "complete_180_evaluation_report_binding",
              "fixed_denominator_accounting", "unresolved_effects_and_recovery_accounted"}
TEMPLATE = "private/phase3/candidate-templates-v001.private.json"
TEMPLATE_FREEZE = "private/phase3/template-freeze-v001.json"


def contained(experiment, relative):
    path = (experiment / relative).resolve(strict=True)
    path.relative_to(experiment.resolve())
    if not path.is_file():
        raise ValueError("reference must be a file")
    return path


def rows_by_identity(rows, expected):
    mapping = {}
    for row in rows:
        key = (row["run_id"], row["condition"], row["seed"])
        if key in mapping:
            raise ValueError("duplicate review identity")
        mapping[key] = row
    if set(mapping) != set(expected):
        raise ValueError("review must bind all six registered identities")
    return mapping


def validate_checks(checks, required, experiment, issue_ids):
    found = {}
    for check in checks:
        if check["id"] in found:
            raise ValueError("duplicate independent check")
        if check.get("status") not in {"passed", "failed", "unknown"}:
            raise ValueError("invalid independent check status")
        if not isinstance(check.get("issue_ids"), list) or any(key not in issue_ids for key in check["issue_ids"]):
            raise ValueError("check issue accounting is incomplete")
        found[check["id"]] = check
    if not required.issubset(found):
        raise ValueError("required independent checks are missing")
    for name in required:
        check = found[name]
        if check.get("status") != "passed" or not check.get("evidence_refs"):
            raise ValueError("required independent check lacks passed evidence: " + name)
        for reference in check["evidence_refs"]:
            if sha256(contained(experiment, reference["path"])) != reference["sha256"]:
                raise ValueError("independent check evidence hash mismatch")


def public_evidence_hashes(root, revision, manifest_files):
    workspace = root / "workspace"
    private_browser = root / "private/browser"
    rules = read(revision / "rules.json")
    validate_rules(rules, workspace)
    validation = validate_browser_exports(workspace, private_browser, rules)
    allowed = {}
    for path in (workspace / "evidence").rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace).as_posix()
        package_relative = path.relative_to(root).as_posix()
        digest = sha256(path)
        if manifest_files.get(package_relative) != digest:
            raise ValueError("public browser evidence is not covered by the learning manifest")
        # The public export validator binds these files to private management
        # originals. Keep the frozen originals and their export manifest covered
        # as well, so newly-added files cannot extend an old package's allowance.
        exported = path.relative_to(workspace / "evidence")
        original = private_browser / exported.parts[0] / "evidence" / Path(*exported.parts[1:])
        export_manifest = private_browser / exported.parts[0] / "public-evidence-hashes.json"
        if (manifest_files.get(original.relative_to(root).as_posix()) != digest
                or manifest_files.get(export_manifest.relative_to(root).as_posix()) != sha256(export_manifest)):
            raise ValueError("public evidence original/export manifest is not frozen")
        parts = {part.lower() for part in Path(relative).parts}
        tokens = set(re.split(r"[-_.]", path.name.lower()))
        if (parts & {"private", "rawtrace", "trace", "state", "auth", "cookies", "credentials"}
                or tokens & {"private", "rawtrace", "trace", "state", "auth", "cookies", "credentials"}
                or path.suffix.lower() in {".zip", ".har"}):
            raise ValueError("private trace, state or authentication material cannot be handed off")
        allowed[relative] = digest
    for rule in rules:
        for reference in rule.get("evidence_refs", []):
            relative = Path(reference["path"]).as_posix()
            if relative.startswith("evidence/") and allowed.get(relative) != reference["sha256"]:
                raise ValueError("rule browser evidence reference is missing from the public allowance")
    return allowed, validation


def build_handoff(learning_review, evaluation_report, independent_review, *, experiment=EXPERIMENT):
    schedule_path = experiment / "FORMAL_SCHEDULE.json"
    schedule = read(schedule_path)
    pairs = schedule_runs(schedule)
    expected = {(condition.lower()+"-seed-"+str(worker["seed"]), condition, worker["seed"]) for worker, condition in pairs}
    paths = {"learning_review": contained(experiment, learning_review),
             "evaluation_report": contained(experiment, evaluation_report),
             "independent_review": contained(experiment, independent_review)}
    learning, report, independent = (read(paths[name]) for name in ("learning_review", "evaluation_report", "independent_review"))
    current_report = build_report(experiment)
    if report.get("schema_version") != 2 or report.get("status") != "complete":
        raise ValueError("complete v002 evaluation report is required")
    for key in ("runs", "conditions", "overall", "schedule_sha256"):
        if report.get(key) != current_report[key]:
            raise ValueError("evaluation report no longer matches immutable case records: " + key)
    if report["overall"]["case_denominator"] != 180 or report["overall"]["prediction_field_denominator"] != 540:
        raise ValueError("fixed evaluation denominator differs")
    if (learning.get("schema_version") != 2 or learning.get("kind") != "frozen_learning_structure_and_original_evidence_review"
            or learning.get("denominator") != 6 or learning.get("status") != "review_complete"
            or learning.get("admission_checks_passed") is not True):
        raise ValueError("complete structural review admission is required")
    if learning.get("formal_schedule_sha256") != sha256(schedule_path):
        raise ValueError("structural review schedule mismatch")
    source_rows = rows_by_identity(learning["runs"], expected)
    if (independent.get("schema_version") != 2 or independent.get("kind") != "independent_learning_review"
            or independent.get("phase") != "post_freeze_independent_review"
            or independent.get("status") != "review_complete" or independent.get("admission_checks_passed") is not True):
        raise ValueError("final independent review admission is required")
    bindings = {"formal_schedule_sha256": sha256(schedule_path),
                "source_report_sha256": sha256(paths["learning_review"]),
                "evaluation_report_sha256": sha256(paths["evaluation_report"]),
                "candidate_template_freeze_sha256": sha256(contained(experiment, TEMPLATE_FREEZE)),
                "candidate_templates_sha256": sha256(contained(experiment, TEMPLATE))}
    if any(independent.get(key) != value for key, value in bindings.items()):
        raise ValueError("independent review report/freeze binding mismatch")
    if (not isinstance(independent.get("private_evaluation_started_at_review"), bool)
            or not independent.get("review_started_at_utc") or not independent.get("review_completed_at_utc")
            or independent.get("reviewer_role") != "independent_evaluator_not_learner"):
        raise ValueError("independent review provenance is incomplete")
    try:
        started = datetime.fromisoformat(independent["review_started_at_utc"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(independent["review_completed_at_utc"].replace("Z", "+00:00"))
        if started.utcoffset() != timezone.utc.utcoffset(started) or completed.utcoffset() != timezone.utc.utcoffset(completed) or completed < started:
            raise ValueError("review timestamps must be ordered UTC times")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("independent review timing is invalid") from error
    issues = independent.get("issues")
    if not isinstance(issues, list) or not isinstance(independent.get("limitations"), list):
        raise ValueError("independent issue accounting is required")
    issue_ids = {issue["id"] for issue in issues}
    if len(issue_ids) != len(issues) or any(issue.get("severity") == "blocking" and issue.get("status") != "resolved" for issue in issues):
        raise ValueError("unresolved blocking independent issue")
    for issue in issues:
        if issue.get("severity") not in {"blocking", "limitation"} or issue.get("status") not in {"open", "resolved"}:
            raise ValueError("invalid independent issue state")
        if not isinstance(issue.get("evidence_refs"), list) or not issue["evidence_refs"]:
            raise ValueError("issue evidence missing")
        for reference in issue["evidence_refs"]:
            if sha256(contained(experiment, reference["path"])) != reference["sha256"]:
                raise ValueError("independent issue evidence hash mismatch")
    if any(issue_id not in issue_ids for issue_id in independent.get("unresolved_issues", [])):
        raise ValueError("unknown unresolved issue reference")
    validate_checks(independent.get("checks", []), TOP_CHECKS, experiment, issue_ids)
    independent_rows = rows_by_identity(independent["runs"], expected)
    packages = []
    for run_id, condition, seed in sorted(expected):
        root = experiment / "runs" / run_id
        files, manifest_digest = checked_manifest(root, "learning-manifest.json", {
            "registration.json", "learning-summary.json", "workspace/READY.json"})
        registration, summary, ready = (read(root/name) for name in ("registration.json", "learning-summary.json", "workspace/READY.json"))
        if any(registration.get(key) != value for key, value in {"run_id":run_id,"condition":condition,"seed":seed,"kind":"formal_learning"}.items()):
            raise ValueError("frozen package identity mismatch")
        if summary.get("status") != "learning_finished" or not management_barrier_passed(summary.get("management_barrier")):
            raise ValueError("frozen package completion/barrier missing")
        workspace = root / "workspace"
        revision = (workspace / ready["revision_directory"]).resolve(strict=True)
        revision.relative_to(workspace.resolve())
        model = revision / "behavior_model.py"
        if condition == "A" and not model.is_file():
            raise ValueError("A predictor missing")
        if condition == "B" and list(workspace.rglob("behavior_model.py")):
            raise ValueError("B predictor forbidden")
        hashes = {"registration_sha256":sha256(root/"registration.json"),
                  "learning_manifest_sha256":manifest_digest,"learning_summary_sha256":sha256(root/"learning-summary.json"),
                  "ready_sha256":sha256(workspace/"READY.json"),"frozen_revision":ready["revision_directory"]}
        source, audited = source_rows[(run_id,condition,seed)], independent_rows[(run_id,condition,seed)]
        for row in (source, audited):
            if row.get("status") != "review_complete" or row.get("admission_checks_passed") is not True or any(row.get(key)!=value for key,value in hashes.items()):
                raise ValueError("review package binding/admission mismatch")
        if source.get("artifact_integrity_passed") is not True or source.get("formal_learning") is not True:
            raise ValueError("source structural review lacks formal package integrity")
        if (not isinstance(source.get("action_evidence_complete"), bool)
                or audited.get("action_evidence_complete") is not source["action_evidence_complete"]):
            raise ValueError("independent action evidence disclosure mismatch")
        if not isinstance(audited.get("unresolved_issue_ids"), list) or any(key not in issue_ids for key in audited["unresolved_issue_ids"]):
            raise ValueError("run issue accounting incomplete")
        validate_checks(audited.get("checks", []), RUN_CHECKS, experiment, issue_ids)
        artifact_hashes = {}
        for path in revision.rglob("*"):
            if path.is_symlink():
                raise ValueError("frozen revision symlink forbidden")
            if path.is_file():
                relative = path.relative_to(workspace).as_posix()
                package_relative = path.relative_to(root).as_posix()
                if package_relative not in files:
                    raise ValueError("unmanifested frozen artifact")
                artifact_hashes[relative] = sha256(path)
        artifact_hashes["READY.json"] = hashes["ready_sha256"]
        public_hashes, public_validation = public_evidence_hashes(root, revision, files)
        artifact_hashes.update(public_hashes)
        packages.append({"run_id":run_id,"condition":condition,"seed":seed,**hashes,
                         "workspace":workspace.relative_to(experiment).as_posix(),
                         "revision":ready["revision_directory"],"allowed_frozen_artifact_hashes":artifact_hashes,
                         "has_executable_predictor":condition=="A","action_evidence_complete":source.get("action_evidence_complete"),
                         "public_evidence_files":len(public_hashes),"public_evidence_validation":public_validation})
    references = {key:{"path":path.relative_to(experiment).as_posix(),"sha256":sha256(path),"visibility":"management_only_for_first_frozen_combinations"} for key,path in paths.items()}
    return {"schema_version":2,"status":"admitted","kind":"phase_three_handoff_without_phase_three_execution",
            "phase_two_protocol":schedule["protocol"],"packages":packages,"management_reviews":references,
            "independent_review_phase":independent["phase"],"fixed_case_denominator":180,"prediction_field_denominator":540,
            "candidate_freeze_binding":bindings,"third_stage_started":False,"official_benchmark":False,
            "first_frozen_combination_rules":[
                "Register a separate phase-three protocol, workflow split, account scope and budgets before execution.",
                "Provide only allowed_frozen_artifact_hashes to task contexts; management review and test answers remain private.",
                "Use native Playwright and independent verification; preserve predictions, refusals, unknowns and timeouts.",
                "Keep first frozen attempts separate from parent-linked online repairs and adaptation scores.",
                "Independently audit combination novelty against actual exploration evidence; this index does not prove novelty."
            ],
            "semantic_perfection_required":False,"combination_novelty_established":False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff-id", required=True)
    parser.add_argument("--learning-review", required=True)
    parser.add_argument("--evaluation-report", required=True)
    parser.add_argument("--independent-review", required=True)
    args = parser.parse_args()
    result = build_handoff(args.learning_review,args.evaluation_report,args.independent_review)
    destination = EXPERIMENT / "handoff" / (args.handoff_id+".json")
    write_new_json(destination,result)
    print(json.dumps({"handoff":str(destination),"packages":len(result['packages']),"third_stage_started":False}))


if __name__ == "__main__":
    main()
