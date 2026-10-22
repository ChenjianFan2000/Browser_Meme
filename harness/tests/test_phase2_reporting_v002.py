import copy
import json
from pathlib import Path
import pytest
from harness.phase2.records import sha256
from harness.phase2.report_v002 import aggregate, case_row, collect_run, build_report, checked_manifest
from harness.phase2.review_learning_v002 import audit_actions, review_run
from harness.phase2.handoff_v002 import build_handoff, public_evidence_hashes, TOP_CHECKS, RUN_CHECKS, TEMPLATE, TEMPLATE_FREEZE


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def freeze(directory, name):
    files = {path.relative_to(directory).as_posix(): sha256(path) for path in directory.rglob("*") if path.is_file() and path.name != name}
    write(directory / name, {"files": files})


def summary(index=1, run_id="a-seed-1729", condition="A", actions=0, safe=True):
    return {"case_id": f"generic-{index}", "case_index": index, "learning_run": run_id, "condition": condition,
            "ui_actions": actions, "browser_executions": 1, "elapsed_seconds": 1, "safe_to_reset": safe,
            "model_cli_exit_code": 0, "model_cli_timeout": False,
            "usage_events": [{"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 5}],
            "independent_evaluation": {"task_outcome": "failed", "business_disposition": "rejected",
                "transport_disposition": "accepted", "side_effects_ok": True,
                "prediction_grading": {"disposition": "incorrect", "persistent_state_changed": "unknown", "affected_record_count": "unscorable"}}}


def test_zero_action_archived_case_is_recorded_with_fixed_rates_and_separate_usage():
    row = case_row(1, summary())
    result = aggregate([row] + [case_row(i) for i in range(2,31)])
    assert result["measurement_status"] == "evaluation_recorded_no_ui_actions"
    assert result["browser_actions_measured"] is False
    assert result["case_denominator"] == 30 and result["prediction_field_denominator"] == 90
    assert result["task_counts"]["failed"] == 1 and result["task_pass_rate_fixed_denominator"] == 0
    assert result["actual_cli_usage"] == {"input_tokens":100,"cached_input_tokens":80,"output_tokens":5}
    assert result["archived_zero_ui_action_count"] == 1
    assert result["model_cli_exit_counts"] == {"0":1}
    assert result["model_cli_timeout_counts"] == {"true":0,"false":1,"unknown":0}
    absent = aggregate([case_row(1, partial=True)])
    assert absent["measurement_status"] == "not_started" and absent["task_pass_rate_fixed_denominator"] is None


def test_unsafe_unknowns_and_business_rejection_stay_separate():
    value = summary(actions=1, safe=False)
    row = case_row(1, value)
    assert row["task_status"] == "unsafe_reset" and row["provisional_independent_outcome"] == "failed"
    assert row["prediction_grades"] == {"disposition":"unscorable","persistent_state_changed":"unknown","affected_record_count":"unscorable"}
    value["safe_to_reset"] = True
    value["independent_evaluation"]["task_outcome"] = "passed"
    row = case_row(1,value)
    assert row["task_status"] == "passed" and row["business_disposition"] == "rejected"


def test_case_manifest_must_cover_summary_and_registration_and_retains_its_hash(tmp_path):
    worker = {"seed":1729}
    directory = tmp_path / "evaluations/a-seed-1729/case-01"
    write(directory/"case-summary.json",summary())
    write(directory/"registration.json",dict(case_id="generic-1",learning_run="a-seed-1729",condition="A",index=1))
    for files in ({}, {"registration.json":sha256(directory/"registration.json")}, {"case-summary.json":sha256(directory/"case-summary.json")}):
        write(directory/"case-manifest.json",{"files":files})
        with pytest.raises(ValueError):collect_run(worker,"A",experiment=tmp_path)
    freeze(directory,"case-manifest.json")
    run = collect_run(worker,"A",experiment=tmp_path)
    assert run["case_manifest_hashes"]["evaluations/a-seed-1729/case-01/case-manifest.json"] == sha256(directory/"case-manifest.json")
    write(directory/"case-summary.json",summary(actions=2))
    with pytest.raises(ValueError):collect_run(worker,"A",experiment=tmp_path)


def test_action_audit_retains_partial_json_and_marks_missing_counter_records(tmp_path):
    call=tmp_path/"call-001-canary"
    write(call/"management-result.json",{"result":{"actions":2,"error":"executor_timeout"}})
    (call/"evidence").mkdir()
    prediction={"disposition":"unknown","effects":{"persistent_state_changed":None,"affected_record_count":None},"ui_claims":[],"unknowns":[]}
    action={"kind":"action_before","prediction":prediction}
    (call/"evidence/actions.jsonl").write_text(json.dumps(action)+'\n{"kind":',encoding="utf-8")
    (tmp_path/"broker.jsonl").write_text(json.dumps({"event":"dispatch","call":call.name})+'\nnull\n',encoding="utf-8")
    result=audit_actions(tmp_path);row=result["calls"][0]
    assert result["action_evidence_complete"] is False
    assert result["malformed_broker_lines"]==1 and row["malformed_action_lines"]==1
    assert row["actions"]==2 and row["valid_predictions"]==1 and row["actions_before"]==1
    assert row["missing_before_records"]==1 and row["missing_after_records"]==2


def test_zero_equals_zero_does_not_hide_missing_log_or_unreported_actions(tmp_path):
    call=tmp_path/"call-001-canary"
    write(call/"management-result.json",{"result":{"actions":2,"error":None}})
    (tmp_path/"broker.jsonl").write_text(json.dumps({"event":"dispatch","call":call.name}),encoding="utf-8")
    row=audit_actions(tmp_path)["calls"][0]
    assert row["missing_action_log"] and row["missing_before_records"]==2 and not row["evidence_complete"]
    write(call/"management-result.json",{"result":{"actions":0,"error":None}})
    assert audit_actions(tmp_path)["action_evidence_complete"] is False
    (call/"evidence").mkdir()
    (call/"evidence/actions.jsonl").write_bytes(b'{"kind":"action_after"}\n\xff')
    audit = audit_actions(tmp_path)
    assert audit["calls"][0]["malformed_action_lines"] == 1
    assert audit["calls"][0]["actions_after"] == 1 and not audit["action_evidence_complete"]


@pytest.fixture
def complete_archive(tmp_path):
    root=tmp_path
    workers=[{"seed":seed,"conditions":["A","B"]} for seed in (1729,2718,3141)]
    write(root/"FORMAL_SCHEDULE.json",{"workers":workers,"protocol":"generic-reporting-test"})
    barrier=dict(relay_drained=True,browser_tree_clean=True,gateway_log_complete=True)
    source_rows=[]
    for worker in workers:
        for condition in worker["conditions"]:
            run_id=condition.lower()+"-seed-"+str(worker["seed"])
            package=root/"runs"/run_id
            write(package/"registration.json",dict(run_id=run_id,condition=condition,seed=worker["seed"],kind="formal_learning"))
            write(package/"learning-summary.json",dict(status="learning_finished",management_barrier=barrier))
            write(package/"workspace/READY.json",dict(revision_directory="v1",stop_reason="generic-budget"))
            revision=package/"workspace/v1";revision.mkdir(parents=True)
            (revision/"rulebook.md").write_text('Generic fixture limitations',encoding="utf-8")
            if condition=="A":(revision/"behavior_model.py").write_text('# generic frozen canary',encoding="utf-8")
            public=package/"workspace/evidence/call-001-generic/obs-0001.html"
            public.parent.mkdir(parents=True);public.write_text('<p>Generic public observation</p>',encoding="utf-8")
            original=package/"private/browser/call-001-generic/evidence/obs-0001.html"
            original.parent.mkdir(parents=True);original.write_bytes(public.read_bytes())
            write(original.parent.parent/"public-evidence-hashes.json",{"obs-0001.html":sha256(public)})
            write(revision/"rules.json",[dict(id="generic",statement="Generic fixture-only rule",status="verified",
                evidence_refs=[dict(path="evidence/call-001-generic/obs-0001.html",sha256=sha256(public))])])
            (original.parent.parent/"private-trace.zip").write_bytes(b'PRIVATE_GENERIC_TRACE')
            write(package/"private/browser/state/browser-state.json",{"generic":"PRIVATE_GENERIC_STATE"})
            write(package/"private/solar/auth.json",{"generic":"PRIVATE_GENERIC_AUTH"})
            freeze(package,"learning-manifest.json")
            source_rows.append(dict(run_id=run_id,condition=condition,seed=worker["seed"],status="review_complete",admission_checks_passed=True,
                registration_sha256=sha256(package/"registration.json"),learning_manifest_sha256=sha256(package/"learning-manifest.json"),
                learning_summary_sha256=sha256(package/"learning-summary.json"),ready_sha256=sha256(package/"workspace/READY.json"),
                frozen_revision="v1",action_evidence_complete=False,artifact_integrity_passed=True,formal_learning=True))
            for index in range(1,31):
                directory=root/"evaluations"/run_id/f"case-{index:02d}"
                value=summary(index,run_id,condition)
                write(directory/"case-summary.json",value)
                write(directory/"registration.json",dict(case_id=value["case_id"],index=index,learning_run=run_id,condition=condition))
                freeze(directory,"case-manifest.json")
    write(root/"reviews/structure.json",dict(schema_version=2,kind="frozen_learning_structure_and_original_evidence_review",denominator=6,status="review_complete",admission_checks_passed=True,
        formal_schedule_sha256=sha256(root/"FORMAL_SCHEDULE.json"),runs=source_rows))
    report=build_report(root);assert report["overall"]["case_denominator"]==180 and report["overall"]["prediction_field_denominator"]==540
    write(root/"reports/full.json",report)
    write(root/TEMPLATE,{"generic":"frozen before any learner evidence"});write(root/TEMPLATE_FREEZE,{"template_sha256":sha256(root/TEMPLATE)})
    write(root/"private/audit/evidence.json",{"generic":"management-only evidence"})
    ref={"path":"private/audit/evidence.json","sha256":sha256(root/"private/audit/evidence.json")}
    def checks(ids):return [dict(id=name,status="passed",evidence_refs=[ref],issue_ids=[]) for name in sorted(ids)]
    independent=dict(schema_version=2,kind="independent_learning_review",phase="post_freeze_independent_review",status="review_complete",admission_checks_passed=True,
        formal_schedule_sha256=sha256(root/"FORMAL_SCHEDULE.json"),source_report_sha256=sha256(root/"reviews/structure.json"),
        evaluation_report_sha256=sha256(root/"reports/full.json"),candidate_template_freeze_sha256=sha256(root/TEMPLATE_FREEZE),candidate_templates_sha256=sha256(root/TEMPLATE),
        private_evaluation_started_at_review=True,review_started_at_utc="2026-10-21T01:00:00Z",review_completed_at_utc="2026-10-21T02:00:00Z",reviewer_role="independent_evaluator_not_learner",
        checks=checks(TOP_CHECKS),runs=[{**row,"checks":checks(RUN_CHECKS),"unresolved_issue_ids":[]} for row in source_rows],
        issues=[dict(id="limited-coverage",severity="limitation",status="open",evidence_refs=[ref])],limitations=["Unknowns and generic failed outcomes remain disclosed"])
    write(root/"reviews/independent.json",independent)
    return root,independent


def test_handoff_admits_complete_low_score_archive_and_disclosed_limitations(complete_archive):
    root,_=complete_archive
    result=build_handoff("reviews/structure.json","reports/full.json","reviews/independent.json",experiment=root)
    assert result["status"]=="admitted" and len(result["packages"])==6
    assert result["semantic_perfection_required"] is False and result["third_stage_started"] is False
    assert result["fixed_case_denominator"]==180 and result["prediction_field_denominator"]==540
    assert all(row["action_evidence_complete"] is False for row in result["packages"])
    for package in result["packages"]:
        workspace=root/package["workspace"]
        allowed=package["allowed_frozen_artifact_hashes"]
        rules=json.loads((workspace/package["revision"]/"rules.json").read_text(encoding="utf-8"))
        for rule in rules:
            for ref in rule["evidence_refs"]:
                assert allowed[ref["path"]]==ref["sha256"]==sha256(workspace/ref["path"])
        assert package["public_evidence_files"]==1
        assert not any("private" in path or "trace" in path or "auth" in path or "state" in path for path in allowed)
        assert not any(path.startswith('reviews/') or path.startswith('reports/') for path in allowed)


def test_handoff_rejects_incomplete_unbound_unknown_or_blocking_review(complete_archive):
    root,original=complete_archive
    def check(mutator):
        value=copy.deepcopy(original);mutator(value);write(root/"reviews/independent.json",value)
        with pytest.raises(ValueError):build_handoff("reviews/structure.json","reports/full.json","reviews/independent.json",experiment=root)
    check(lambda x:x.update(status="incomplete"))
    check(lambda x:x.update(admission_checks_passed=False))
    check(lambda x:x.update(evaluation_report_sha256="0"*64))
    check(lambda x:x["checks"][0].update(status="unknown"))
    check(lambda x:x["runs"][0].update(ready_sha256="0"*64))
    check(lambda x:x["runs"].append(copy.deepcopy(x["runs"][0])))
    check(lambda x:x["issues"][0].update(severity="blocking"))
    check(lambda x:x["checks"][0]["evidence_refs"][0].update(sha256="0"*64))
    write(root/"reviews/independent.json",original)
    report=json.loads((root/"reports/full.json").read_text(encoding="utf-8"));report["status"]="incomplete";write(root/"reports/full.json",report)
    with pytest.raises(ValueError):build_handoff("reviews/structure.json","reports/full.json","reviews/independent.json",experiment=root)


def test_structure_review_completes_with_disclosed_partial_action_evidence(tmp_path):
    root=tmp_path/"runs/a-seed-1729"
    workspace=root/"workspace"
    private=root/"private/browser"
    call=private/"call-001-canary"
    revision=workspace/"v1"
    write(root/"registration.json",dict(run_id="a-seed-1729",condition="A",seed=1729,kind="formal_learning"))
    write(root/"learning-summary.json",dict(status="learning_finished",management_barrier=dict(relay_drained=True,browser_tree_clean=True,gateway_log_complete=True)))
    write(workspace/"READY.json",dict(revision_directory="v1",stop_reason="generic-budget"))
    write(revision/"rules.json",[dict(id="generic",statement="Generic hypothesis with unknown scope",status="hypothesis",evidence_refs=[])])
    (revision/"scripts.py").write_text('# generic syntax-only script',encoding="utf-8")
    (revision/"behavior_model.py").write_text('# generic syntax-only model',encoding="utf-8")
    write(root/"private/solar/launch-result.json",dict(exit_code=0,timeout=False,elapsed_seconds=1,usage_events=[]))
    write(call/"management-result.json",dict(result=dict(actions=2,error="executor_timeout")))
    (call/"evidence").mkdir()
    action_path=call/"evidence/actions.jsonl"
    action_path.write_bytes(b'{"kind":"action_after"}\n{')
    export=workspace/"evidence"/call.name/"actions.jsonl"
    export.parent.mkdir(parents=True);export.write_bytes(action_path.read_bytes())
    write(call/"public-evidence-hashes.json",{"actions.jsonl":sha256(action_path)})
    (private/"broker.jsonl").write_text(json.dumps(dict(event="dispatch",call=call.name)),encoding="utf-8")
    freeze(root,"learning-manifest.json")
    value=review_run("a-seed-1729",experiment=tmp_path)
    assert value["status"]=="review_complete" and value["admission_checks_passed"] is True
    assert value["action_evidence_complete"] is False and value["malformed_action_lines"]==1
    assert value["action_after_records"]==1 and value["missing_action_before_records"]==2
    assert value["browser_failures"]==1 and value["semantic_correctness"]=="not_established_by_this_structural_review"


def test_empty_archive_keeps_all_180_cases_without_claiming_measurements(tmp_path):
    write(tmp_path/"FORMAL_SCHEDULE.json",dict(protocol="generic",workers=[dict(seed=seed,conditions=["A","B"]) for seed in (1729,2718,3141)]))
    value=build_report(tmp_path)
    assert value["status"]=="incomplete"
    assert value["overall"]["case_denominator"]==180 and value["overall"]["prediction_field_denominator"]==540
    assert value["overall"]["measurement_status"]=="not_started"
    assert value["overall"]["task_counts"]["not_run"]==180
    assert all(group["case_denominator"]==90 for group in value["conditions"].values())


def test_public_evidence_must_be_frozen_and_match_management_original(complete_archive):
    root,_=complete_archive
    package=root/"runs/a-seed-1729"
    files=json.loads((package/"learning-manifest.json").read_text(encoding="utf-8"))["files"]
    public=package/"workspace/evidence/call-001-generic/obs-0001.html"
    omitted=dict(files);omitted.pop(public.relative_to(package).as_posix())
    with pytest.raises(ValueError,match="learning manifest"):
        public_evidence_hashes(package,package/"workspace/v1",omitted)
    public.write_text('Changed public observation',encoding="utf-8")
    with pytest.raises(ValueError):
        public_evidence_hashes(package,package/"workspace/v1",files)


def test_public_allowance_rejects_unfrozen_original_and_private_trace_export(tmp_path):
    package=tmp_path
    revision=package/"workspace/v1"
    public=package/"workspace/evidence/call-001-generic/obs-0001.html"
    original=package/"private/browser/call-001-generic/evidence/obs-0001.html"
    public.parent.mkdir(parents=True);public.write_text('<p>generic public</p>',encoding="utf-8")
    original.parent.mkdir(parents=True);original.write_bytes(public.read_bytes())
    exports=original.parent.parent/"public-evidence-hashes.json"
    write(exports,{"obs-0001.html":sha256(public)})
    write(revision/"rules.json",[dict(id="generic",statement="Generic evidence reference",status="verified",evidence_refs=[dict(path="evidence/call-001-generic/obs-0001.html",sha256=sha256(public))])])
    freeze(package,"learning-manifest.json")
    files=json.loads((package/"learning-manifest.json").read_text(encoding="utf-8"))["files"]
    allowed,_=public_evidence_hashes(package,revision,files)
    assert allowed=={"evidence/call-001-generic/obs-0001.html":sha256(public)}
    missing=dict(files);missing.pop(original.relative_to(package).as_posix())
    with pytest.raises(ValueError,match="original/export manifest"):
        public_evidence_hashes(package,revision,missing)
    trace=public.parent/"private-trace.zip";trace.write_bytes(b'PRIVATE_GENERIC_TRACE')
    raw=original.parent/trace.name;raw.write_bytes(trace.read_bytes())
    write(exports,{"obs-0001.html":sha256(public),trace.name:sha256(trace)})
    freeze(package,"learning-manifest.json")
    files=json.loads((package/"learning-manifest.json").read_text(encoding="utf-8"))["files"]
    with pytest.raises(ValueError,match="cannot be handed off"):
        public_evidence_hashes(package,revision,files)
