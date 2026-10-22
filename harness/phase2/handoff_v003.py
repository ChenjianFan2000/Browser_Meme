"""Completed review may admit compliant packages while retaining quarantined failures."""
from __future__ import annotations
import argparse
import json
from .validity_report_v001 import review_context, validity_from_context, DEVIATIONS
from .handoff_v002 import contained, public_evidence_hashes
from .report_v002 import read
from .records import sha256, write_new_json
from .run_learning import EXPERIMENT


def build_handoff(learning_review,evaluation_report,independent_review,validity_report,*,deviations=DEVIATIONS,experiment=EXPERIMENT):
    context=review_context(learning_review,evaluation_report,independent_review,deviations=deviations,experiment=experiment)
    validity_path=contained(experiment,validity_report)
    validity=read(validity_path)
    if validity!=validity_from_context(context):
        raise ValueError("validity report differs from final compliance ledger/raw records")
    allowed,quarantine=[],[]
    for package in context["packages"]:
        public_fields={key:package[key] for key in ("run_id","condition","seed","registration_sha256",
            "learning_manifest_sha256","learning_summary_sha256","ready_sha256","frozen_revision",
            "admitted","reasons","open_blocking_issue_ids","action_evidence_complete","required_check_statuses")}
        if not package["admitted"]:
            quarantine.append({**public_fields,"diagnostic_case_count":30,"raw_scores_retained":True,
                "phase_three_access_allowed":False,"allowed_frozen_artifact_hashes":{}})
            continue
        workspace,revision,root=package["workspace"],package["revision"],package["directory"]
        artifacts={}
        for path in revision.rglob("*"):
            if path.is_symlink():
                raise ValueError("frozen revision symlink forbidden")
            if path.is_file():
                relative=path.relative_to(workspace).as_posix()
                digest=sha256(path)
                if package["manifest_files"].get(path.relative_to(root).as_posix())!=digest:
                    raise ValueError("unmanifested frozen revision artifact")
                artifacts[relative]=digest
        artifacts["READY.json"]=package["ready_sha256"]
        evidence,validation=public_evidence_hashes(root,revision,package["manifest_files"])
        artifacts.update(evidence)
        allowed.append({**public_fields,"workspace":workspace.relative_to(experiment).as_posix(),
            "revision":package["frozen_revision"],"allowed_frozen_artifact_hashes":artifacts,
            "has_executable_predictor":package["condition"]=="A","public_evidence_files":len(evidence),
            "public_evidence_validation":validation,"phase_three_access_allowed":True})
    refs={name:{"path":path.relative_to(experiment).as_posix(),"sha256":sha256(path),
        "visibility":"management_only_for_first_frozen_combinations"} for name,path in context["paths"].items()}
    refs["validity_report"]={"path":validity_path.relative_to(experiment).as_posix(),"sha256":sha256(validity_path),
        "visibility":"management_only_for_first_frozen_combinations"}
    return {"schema_version":3,"kind":"qualified_phase_three_handoff_without_execution","status":"review_complete",
        "all_registered_packages_admitted":not quarantine,"registered_package_count":6,"allowed_package_count":len(allowed),
        "quarantined_package_count":len(quarantine),"packages":allowed,"quarantined_packages":quarantine,
        "registered_case_denominator":180,"registered_prediction_field_denominator":540,
        "phase_two_protocol":context["schedule"]["protocol"],"management_reviews":refs,
        "bindings":context["bindings"],"independent_overall_admission_checks_passed":context["independent"]["admission_checks_passed"],
        "historical_blocking_issues_relabelled_resolved":False,"original_scores_rewritten":False,
        "third_stage_started":False,"semantic_perfection_required":False,"combination_novelty_established":False,
        "first_frozen_combination_rules":[
            "Register a separate phase-three protocol and use only admitted packages; never substitute quarantined package knowledge.",
            "Give task contexts only allowed_frozen_artifact_hashes; validity, reviews, task answers and private state remain management-only.",
            "Report the raw 180-case cohort and the ledger-selected paired sensitivity separately; never replace the registered denominator.",
            "Preserve first frozen attempts, failures and unknowns; online repairs require parent-linked new versions and separate scores.",
            "This completed review/index does not start phase three or prove combination novelty."
        ]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--handoff-id",required=True)
    parser.add_argument("--learning-review",required=True)
    parser.add_argument("--evaluation-report",required=True)
    parser.add_argument("--independent-review",required=True)
    parser.add_argument("--validity-report",required=True)
    parser.add_argument("--deviations",default=DEVIATIONS)
    args=parser.parse_args()
    value=build_handoff(args.learning_review,args.evaluation_report,args.independent_review,args.validity_report,deviations=args.deviations)
    destination=EXPERIMENT/"handoff"/(args.handoff_id+".json")
    write_new_json(destination,value)
    print(json.dumps({"handoff":str(destination),"allowed_packages":value["allowed_package_count"],"quarantined_packages":value["quarantined_package_count"],"third_stage_started":False}))


if __name__=="__main__":
    main()
