import copy
import json
import pytest
from harness.tests.test_phase2_reporting_v002 import complete_archive, write
from harness.phase2.records import sha256
from harness.phase2.validity_report_v001 import build_validity_report
from harness.phase2.handoff_v003 import build_handoff

ARGS=("reviews/structure.json","reports/full.json","reviews/independent.json")


@pytest.fixture
def qualified_archive(complete_archive):
    root,independent=complete_archive
    write(root/"DEVIATIONS-001.md",{"generic":"Stop-policy deviation registered before private tests; no original score rewrite"})
    independent=copy.deepcopy(independent)
    independent["deviations_sha256"]=sha256(root/"DEVIATIONS-001.md")
    independent["admission_checks_passed"]=False
    issue={"id":"stop-after-policy-denial","severity":"blocking","status":"open","scope":"package",
           "affected_run_ids":["a-seed-2718"],"evidence_refs":copy.deepcopy(independent["checks"][0]["evidence_refs"])}
    independent["issues"].append(issue)
    target=next(row for row in independent["runs"] if row["run_id"]=="a-seed-2718")
    target["admission_checks_passed"]=False
    target["unresolved_issue_ids"].append(issue["id"])
    check=next(row for row in target["checks"] if row["id"]=="observation_boundary_compliance")
    check["status"]="failed";check["issue_ids"]=[issue["id"]]
    write(root/"reviews/independent.json",independent)
    return root,independent


def test_raw_180_and_qualified_pair_sensitivity_do_not_rewrite_scores(qualified_archive):
    root,independent=qualified_archive
    before={path:sha256(root/path) for path in ARGS}
    value=build_validity_report(*ARGS,experiment=root)
    assert value["status"]=="review_complete" and value["review_complete_means_all_admitted"] is False
    assert value["registered_case_denominator"]==180 and value["registered_prediction_field_denominator"]==540
    raw=json.loads((root/"reports/full.json").read_text(encoding="utf-8"))
    assert value["raw_registered_statistics"]["overall"]==raw["overall"]
    assert value["raw_registered_statistics"]["conditions"]==raw["conditions"]
    assert all(group["case_denominator"]==90 for group in value["raw_registered_statistics"]["conditions"].values())
    assert value["diagnostic_only_run_ids"]==["a-seed-2718"] and value["diagnostic_only_case_count"]==30
    assert value["raw_registered_statistics"]["condition_noncompliance_annotations"]["A"]==["a-seed-2718"]
    paired=value["compliant_paired_sensitivity"]
    assert paired["paired_seeds"]==[1729,3141]
    assert paired["overall"]["case_denominator"]==120 and paired["overall"]["prediction_field_denominator"]==360
    assert all(group["case_denominator"]==60 for group in paired["conditions"].values())
    assert "b-seed-2718" not in paired["included_run_ids"] and paired["replaces_registered_denominator"] is False
    assert value["original_scores_rewritten"] is False
    assert before=={path:sha256(root/path) for path in ARGS}
    write(root/"reports/validity.json",value)
    handoff=build_handoff(*ARGS,"reports/validity.json",experiment=root)
    assert handoff["status"]=="review_complete" and handoff["allowed_package_count"]==5
    assert handoff["quarantined_package_count"]==1 and handoff["registered_case_denominator"]==180
    assert "a-seed-2718" not in {row["run_id"] for row in handoff["packages"]}
    assert "b-seed-2718" in {row["run_id"] for row in handoff["packages"]}
    quarantined=handoff["quarantined_packages"][0]
    assert quarantined["run_id"]=="a-seed-2718" and quarantined["allowed_frozen_artifact_hashes"]=={}
    assert quarantined["phase_three_access_allowed"] is False and quarantined["raw_scores_retained"] is True
    assert quarantined["required_check_statuses"]["observation_boundary_compliance"]=="failed"
    assert "open_blocking_issue:stop-after-policy-denial" in quarantined["reasons"]
    assert handoff["historical_blocking_issues_relabelled_resolved"] is False
    assert handoff["third_stage_started"] is False
    assert json.loads((root/"reviews/independent.json").read_text(encoding="utf-8"))["issues"][-1]["status"]=="open"
    assert before=={path:sha256(root/path) for path in ARGS}
    for package in handoff["packages"]:
        assert any(path.startswith("evidence/") for path in package["allowed_frozen_artifact_hashes"])
        assert not any("private" in path or "auth" in path or "trace" in path for path in package["allowed_frozen_artifact_hashes"])


def test_unknown_checks_and_global_blockers_remain_visible_without_admission(qualified_archive):
    root,original=qualified_archive
    value=copy.deepcopy(original)
    target=next(row for row in value["runs"] if row["run_id"]=="b-seed-3141")
    target["admission_checks_passed"]=False;target["checks"][0]["status"]="unknown"
    write(root/"reviews/independent.json",value)
    report=build_validity_report(*ARGS,experiment=root)
    assert report["compliant_run_count"]==4 and report["compliant_paired_sensitivity"]["paired_seeds"]==[1729]
    assert report["compliant_paired_sensitivity"]["overall"]["case_denominator"]==60
    assert next(row for row in report["compliance_ledger"] if row["run_id"]=="b-seed-3141")["required_check_statuses"][target["checks"][0]["id"]]=="unknown"
    value=copy.deepcopy(original);value["issues"][-1]["scope"]="global"
    write(root/"reviews/independent.json",value)
    report=build_validity_report(*ARGS,experiment=root)
    assert report["compliant_run_count"]==0 and report["registered_case_denominator"]==180
    assert report["compliant_paired_sensitivity"]["status"]=="no_compliant_pairs"
    assert report["compliant_paired_sensitivity"]["overall"]["case_denominator"]==0
    write(root/"reports/validity.json",report)
    handoff=build_handoff(*ARGS,"reports/validity.json",experiment=root)
    assert handoff["packages"]==[] and handoff["quarantined_package_count"]==6


def test_incomplete_or_unbound_ledgers_and_stale_validity_are_rejected(qualified_archive):
    root,original=qualified_archive
    report=build_validity_report(*ARGS,experiment=root);write(root/"reports/validity.json",report)
    def rejected(mutator):
        value=copy.deepcopy(original);mutator(value);write(root/"reviews/independent.json",value)
        with pytest.raises(ValueError):build_validity_report(*ARGS,experiment=root)
    rejected(lambda value:value.update(status="incomplete"))
    rejected(lambda value:value.update(deviations_sha256="0"*64))
    rejected(lambda value:value["issues"][-1].pop("scope"))
    rejected(lambda value:value["issues"][-1].update(affected_run_ids=[]))
    rejected(lambda value:value.update(admission_checks_passed=True))
    value=copy.deepcopy(original);value["issues"][-1]["scope"]="global";write(root/"reviews/independent.json",value)
    with pytest.raises(ValueError,match="validity report differs"):
        build_handoff(*ARGS,"reports/validity.json",experiment=root)
    write(root/"reviews/independent.json",original)
    raw=json.loads((root/"reports/full.json").read_text(encoding="utf-8"));raw["status"]="incomplete";write(root/"reports/full.json",raw)
    with pytest.raises(ValueError):build_validity_report(*ARGS,experiment=root)
