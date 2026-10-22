"""Management validity views preserve raw results and quarantine protocol deviations."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from .report_v002 import read, checked_manifest, schedule_runs, build_report, aggregate
from .handoff_v002 import contained, rows_by_identity, TOP_CHECKS, RUN_CHECKS, TEMPLATE, TEMPLATE_FREEZE
from .records import sha256, write_new_json
from .run_learning import EXPERIMENT, management_barrier_passed

DEVIATIONS = "DEVIATIONS-001.md"


def check_records(rows, required, experiment, issue_ids):
    checks = {}
    for row in rows:
        name = row["id"]
        if not isinstance(name, str) or not name or name in checks:
            raise ValueError("invalid or duplicate independent check")
        if row.get("status") not in {"passed", "failed", "unknown"}:
            raise ValueError("invalid independent check status")
        if not isinstance(row.get("issue_ids"), list) or any(key not in issue_ids for key in row["issue_ids"]):
            raise ValueError("check issue references are incomplete")
        refs = row.get("evidence_refs")
        if not isinstance(refs, list) or (row["status"] == "passed" and not refs):
            raise ValueError("passed check requires evidence")
        for ref in refs:
            if sha256(contained(experiment, ref["path"])) != ref["sha256"]:
                raise ValueError("independent check evidence hash mismatch")
        checks[name] = row
    if not required.issubset(checks):
        raise ValueError("required independent check missing")
    return checks


def review_context(learning_review, evaluation_report, independent_review, *, deviations=DEVIATIONS, experiment=EXPERIMENT):
    paths = {name:contained(experiment,path) for name,path in {
        "learning_review":learning_review,"evaluation_report":evaluation_report,
        "independent_review":independent_review,"deviations":deviations}.items()}
    schedule_path = experiment / "FORMAL_SCHEDULE.json"
    schedule = read(schedule_path)
    pairs = schedule_runs(schedule)
    expected = {(condition.lower()+"-seed-"+str(worker["seed"]),condition,worker["seed"]) for worker,condition in pairs}
    run_ids = {key[0] for key in expected}
    source, raw, independent = (read(paths[name]) for name in ("learning_review","evaluation_report","independent_review"))
    current = build_report(experiment)
    if raw.get("schema_version") != 2 or raw.get("status") != "complete" or current["status"] != "complete":
        raise ValueError("complete 180-case raw archive is required")
    for key in ("runs","conditions","overall","schedule_sha256"):
        if raw.get(key) != current[key]:
            raise ValueError("raw report differs from immutable cases: "+key)
    if raw["overall"]["case_denominator"] != 180 or raw["overall"]["prediction_field_denominator"] != 540:
        raise ValueError("registered denominator is not 180/540")
    if (source.get("schema_version") != 2 or source.get("kind") != "frozen_learning_structure_and_original_evidence_review"
            or source.get("status") != "review_complete" or source.get("denominator") != 6
            or not isinstance(source.get("admission_checks_passed"),bool)
            or source.get("formal_schedule_sha256") != sha256(schedule_path)):
        raise ValueError("complete bound structural review is required")
    if (independent.get("schema_version") != 2 or independent.get("kind") != "independent_learning_review"
            or independent.get("phase") != "post_freeze_independent_review"
            or independent.get("status") != "review_complete"
            or not isinstance(independent.get("admission_checks_passed"),bool)):
        raise ValueError("completed final independent review is required, not universal admission")
    bindings = {"formal_schedule_sha256":sha256(schedule_path),"source_report_sha256":sha256(paths["learning_review"]),
        "evaluation_report_sha256":sha256(paths["evaluation_report"]),"deviations_sha256":sha256(paths["deviations"]),
        "candidate_template_freeze_sha256":sha256(contained(experiment,TEMPLATE_FREEZE)),
        "candidate_templates_sha256":sha256(contained(experiment,TEMPLATE))}
    if any(independent.get(key)!=value for key,value in bindings.items()):
        raise ValueError("independent review binding mismatch")
    if (independent.get("reviewer_role") != "independent_evaluator_not_learner"
            or not isinstance(independent.get("private_evaluation_started_at_review"),bool)):
        raise ValueError("independent review provenance is incomplete")
    try:
        start=datetime.fromisoformat(independent["review_started_at_utc"].replace("Z","+00:00"))
        end=datetime.fromisoformat(independent["review_completed_at_utc"].replace("Z","+00:00"))
        if start.utcoffset()!=timezone.utc.utcoffset(start) or end.utcoffset()!=timezone.utc.utcoffset(end) or end<start:
            raise ValueError("review times must be ordered UTC")
    except (ValueError,TypeError,AttributeError,KeyError) as error:
        raise ValueError("invalid final review times") from error
    issues=independent.get("issues")
    if not isinstance(issues,list) or not isinstance(independent.get("limitations"),list):
        raise ValueError("issue and limitation accounting is required")
    issue_map={}
    for issue in issues:
        name=issue["id"]
        if not isinstance(name,str) or not name or name in issue_map:
            raise ValueError("invalid or duplicate issue ID")
        if issue.get("severity") not in {"blocking","limitation"} or issue.get("status") not in {"open","resolved"}:
            raise ValueError("invalid issue state")
        if issue["severity"]=="blocking":
            if issue.get("scope")=="global":
                affected=set(run_ids)
            elif issue.get("scope")=="package":
                ids=issue.get("affected_run_ids")
                if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or not set(ids).issubset(run_ids):
                    raise ValueError("package blocking issue must bind registered runs")
                affected=set(ids)
            else:
                raise ValueError("blocking issue scope must be explicit")
        else:
            affected=set(issue.get("affected_run_ids",[]))
            if not affected.issubset(run_ids):
                raise ValueError("limitation refers to unknown run")
        if not isinstance(issue.get("evidence_refs"),list) or not issue["evidence_refs"]:
            raise ValueError("issue evidence missing")
        for ref in issue["evidence_refs"]:
            if sha256(contained(experiment,ref["path"]))!=ref["sha256"]:
                raise ValueError("issue evidence hash mismatch")
        issue_map[name]={"record":issue,"affected":affected}
    if any(key not in issue_map for key in independent.get("unresolved_issues",[])):
        raise ValueError("unknown unresolved issue")
    top=check_records(independent.get("checks",[]),TOP_CHECKS,experiment,set(issue_map))
    source_rows=rows_by_identity(source["runs"],expected)
    audited_rows=rows_by_identity(independent["runs"],expected)
    packages=[]
    global_reasons=["top_check_"+top[name]["status"]+":"+name for name in sorted(TOP_CHECKS) if top[name]["status"]!="passed"]
    for run_id,condition,seed in sorted(expected):
        directory=experiment/"runs"/run_id
        manifest,digest=checked_manifest(directory,"learning-manifest.json",{"registration.json","learning-summary.json","workspace/READY.json"})
        registration,summary,ready=(read(directory/name) for name in ("registration.json","learning-summary.json","workspace/READY.json"))
        if any(registration.get(key)!=value for key,value in {"run_id":run_id,"condition":condition,"seed":seed,"kind":"formal_learning"}.items()):
            raise ValueError("frozen package identity mismatch")
        workspace=directory/"workspace"
        revision=(workspace/ready["revision_directory"]).resolve(strict=True)
        revision.relative_to(workspace.resolve())
        hashes={"registration_sha256":sha256(directory/"registration.json"),"learning_manifest_sha256":digest,
            "learning_summary_sha256":sha256(directory/"learning-summary.json"),"ready_sha256":sha256(workspace/"READY.json"),
            "frozen_revision":ready["revision_directory"]}
        structure,audited=source_rows[(run_id,condition,seed)],audited_rows[(run_id,condition,seed)]
        for row in (structure,audited):
            if (row.get("status")!="review_complete" or not isinstance(row.get("admission_checks_passed"),bool)
                    or any(row.get(key)!=value for key,value in hashes.items())):
                raise ValueError("final review package binding/completion mismatch")
        if (not isinstance(structure.get("action_evidence_complete"),bool)
                or audited.get("action_evidence_complete") is not structure["action_evidence_complete"]):
            raise ValueError("action evidence disclosure mismatch")
        if not isinstance(audited.get("unresolved_issue_ids"),list) or any(key not in issue_map for key in audited["unresolved_issue_ids"]):
            raise ValueError("run issue accounting incomplete")
        checks=check_records(audited.get("checks",[]),RUN_CHECKS,experiment,set(issue_map))
        reasons=list(global_reasons)
        reasons += ["required_check_"+checks[name]["status"]+":"+name for name in sorted(RUN_CHECKS) if checks[name]["status"]!="passed"]
        if structure["admission_checks_passed"] is not True:reasons.append("structural_package_admission_false")
        if audited["admission_checks_passed"] is not True:reasons.append("independent_package_admission_false")
        if structure.get("artifact_integrity_passed") is not True or structure.get("formal_learning") is not True:
            reasons.append("source_structural_integrity_not_confirmed")
        if summary.get("status")!="learning_finished" or not management_barrier_passed(summary.get("management_barrier")):
            reasons.append("package_completion_or_cleanup_barrier_missing")
        if condition=="A" and not (revision/"behavior_model.py").is_file():reasons.append("A_predictor_missing")
        if condition=="B" and list(workspace.rglob("behavior_model.py")):reasons.append("B_predictor_forbidden")
        blockers=[name for name,item in issue_map.items() if item["record"]["severity"]=="blocking" and item["record"]["status"]=="open" and run_id in item["affected"]]
        reasons += ["open_blocking_issue:"+name for name in sorted(blockers)]
        packages.append({"run_id":run_id,"condition":condition,"seed":seed,**hashes,
            "admitted":not reasons,"reasons":reasons,"open_blocking_issue_ids":sorted(blockers),
            "action_evidence_complete":structure["action_evidence_complete"],"manifest_files":manifest,
            "directory":directory,"revision":revision,"workspace":workspace,
            "required_check_statuses":{name:checks[name]["status"] for name in sorted(RUN_CHECKS)}})
    if independent["admission_checks_passed"] is True and not all(row["admitted"] for row in packages):
        raise ValueError("overall admission true contradicts package blockers")
    if independent["admission_checks_passed"] is False and all(row["admitted"] for row in packages):
        for row in packages:
            row["admitted"]=False;row["reasons"].append("overall_admission_not_granted_without_scoped_exception")
    return {"experiment":experiment,"paths":paths,"schedule":schedule,"raw":raw,
            "independent":independent,"bindings":bindings,"packages":packages}


def validity_from_context(context):
    raw=context["raw"]
    ledger=[{key:row[key] for key in ("run_id","condition","seed","admitted","reasons","open_blocking_issue_ids","required_check_statuses")} for row in context["packages"]]
    eligible={row["run_id"] for row in ledger if row["admitted"]}
    seeds=sorted({row["seed"] for row in ledger})
    paired=[seed for seed in seeds if {"a-seed-"+str(seed),"b-seed-"+str(seed)}.issubset(eligible)]
    selected=[run for run in raw["runs"] if run["seed"] in paired]
    if selected:
        sensitivity={"status":"available","overall":aggregate([row for run in selected for row in run["cases"]]),
            "conditions":{condition:aggregate([row for run in selected if run["condition"]==condition for row in run["cases"]]) for condition in ("A","B")}}
    else:
        sensitivity={"status":"no_compliant_pairs","overall":{"case_denominator":0,"prediction_field_denominator":0},"conditions":{}}
    sensitivity.update({"paired_seeds":paired,"included_run_ids":[run["run_id"] for run in selected],
        "excluded_seed_reasons":{str(seed):{row["run_id"]:row["reasons"] for row in ledger if row["seed"]==seed and not row["admitted"]} for seed in seeds if seed not in paired},
        "selection_basis":"final independent compliance ledger, never outcomes or scores","replaces_registered_denominator":False})
    excluded=[row["run_id"] for row in ledger if not row["admitted"]]
    return {"schema_version":1,"kind":"registered_raw_and_compliance_paired_validity_report","status":"review_complete",
        "registered_case_denominator":180,"registered_prediction_field_denominator":540,
        "review_complete_means_all_admitted":False,"all_registered_runs_compliant":not excluded,
        "compliant_run_count":len(eligible),"diagnostic_only_run_ids":excluded,"diagnostic_only_case_count":30*len(excluded),
        "raw_registered_statistics":{"interpretation":"raw registered results include protocol-noncompliant trials; not six compliant method repeats",
            "overall":raw["overall"],"conditions":raw["conditions"],
            "condition_noncompliance_annotations":{condition:[row["run_id"] for row in ledger if row["condition"]==condition and not row["admitted"]] for condition in ("A","B")}},
        "compliance_ledger":ledger,"compliant_paired_sensitivity":sensitivity,
        "bindings":context["bindings"],"references":{name:{"path":path.relative_to(context["experiment"]).as_posix(),"sha256":sha256(path)} for name,path in context["paths"].items()},
        "original_scores_rewritten":False,"third_stage_started":False}


def build_validity_report(learning_review,evaluation_report,independent_review,*,deviations=DEVIATIONS,experiment=EXPERIMENT):
    return validity_from_context(review_context(learning_review,evaluation_report,independent_review,deviations=deviations,experiment=experiment))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--report-id",required=True)
    parser.add_argument("--learning-review",required=True)
    parser.add_argument("--evaluation-report",required=True)
    parser.add_argument("--independent-review",required=True)
    parser.add_argument("--deviations",default=DEVIATIONS)
    args=parser.parse_args()
    value=build_validity_report(args.learning_review,args.evaluation_report,args.independent_review,deviations=args.deviations)
    destination=EXPERIMENT/"reports"/(args.report_id+".json")
    write_new_json(destination,value)
    print(json.dumps({"validity_report":str(destination),"registered_cases":180,"diagnostic_only_runs":value["diagnostic_only_run_ids"]}))


if __name__=="__main__":
    main()
