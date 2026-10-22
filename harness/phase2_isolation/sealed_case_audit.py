"""Read-only management-chain audit of explicitly selected sealed evaluation cases.
No model, browser, driver, process, reset or business-truth computation is invoked.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from harness.phase2.records import sha256, verify_manifest
from harness.phase2.process_guard import receipt_valid
from harness.phase2.run_learning import EXPERIMENT, LINUX_ROOT, management_barrier_passed


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":"))


def json_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def successful_mcp(rows, name):
    values=[]
    for index,row in enumerate(rows):
        item=row.get("item",{})
        if row.get("type")!="item.completed" or item.get("type")!="mcp_tool_call" or item.get("tool")!=name:
            continue
        if item.get("status")!="completed":
            continue
        for block in (item.get("result")or{}).get("content",[]):
            if block.get("type")=="text":
                try:value=json.loads(block["text"])
                except ValueError:continue
                values.append((index,item,value))
    return values


def audit_case(directory):
    directory=Path(directory)
    manifest_path=directory/"case-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("active or unsealed case must not be read")
    manifest_digest=sha256(manifest_path)
    manifest=read(manifest_path)["files"]
    required={"registration.json","case-summary.json","management-barrier.json","trusted-gateway.jsonl","private/solar/events.jsonl","private/solar/launch-result.json","private/browser/prediction-ack.json"}
    if not required.issubset(manifest) or verify_manifest(directory,manifest):
        raise ValueError("case is missing required sealed records or hashes differ")
    registration=read(directory/"registration.json")
    summary=read(directory/"case-summary.json")
    run_id,index,condition=registration["learning_run"],registration["index"],registration["condition"]
    checks={}
    checks["summary_registration_identity"]=(summary["learning_run"]==run_id and summary["case_index"]==index and summary["condition"]==condition and summary["case_id"]==registration["case_id"])
    learning=EXPERIMENT/"runs"/run_id
    learning_manifest_path=learning/"learning-manifest.json"
    learning_manifest_digest=sha256(learning_manifest_path)
    learning_manifest=read(learning_manifest_path)["files"]
    ready=read(learning/"workspace/READY.json")
    revision=(learning/"workspace"/ready["revision_directory"]).resolve()
    revision.relative_to((learning/"workspace").resolve())
    expected={path.relative_to(learning/"workspace").as_posix():sha256(path) for path in revision.rglob("*") if path.is_file()}
    expected["READY.json"]=sha256(learning/"workspace/READY.json")
    checks["frozen_input_exact_final_revision_and_ready"]=(expected==registration["frozen_files"])
    checks["frozen_inputs_covered_by_learning_manifest"]=all(learning_manifest.get("workspace/"+relative)==digest for relative,digest in expected.items())
    frozen_linux=LINUX_ROOT+"/"+run_id+"/workspace"
    checks["frozen_namespace_readonly_path_binding"]=(registration["plan"]["readonly_paths"]==[frozen_linux])
    gate=Path(registration["gate"]["path"])
    checks["gate_sha_binding"]=(sha256(gate)==registration["gate"]["sha256"])
    launch_path=directory/"private/solar/launch-result.json"
    launch=read(launch_path)
    command=launch["command"]
    checks["exact_requested_model"]=(launch["model"]=="gpt-6.1-sol" and command[command.index("-m")+1]=="gpt-6.1-sol")
    checks["fresh_context_configuration"]=(launch["fresh_context"] is True and "--ephemeral" in command and "--ignore-user-config" in command and "--ignore-rules" in command)
    checks["cli_exit_timeout_summary_matches_original"]=(summary["model_cli_exit_code"]==launch["exit_code"] and summary["model_cli_timeout"] is launch["timeout"])
    cli=json_rows(directory/"private/solar/events.jsonl")
    actual_usage=[row["usage"] for row in cli if "usage" in row]
    checks["cli_usage_exact_not_recomputed"]=(actual_usage==launch["usage_events"]==summary["usage_events"])
    cleanup=directory/"private/solar"/launch["cleanup_receipt"]
    checks["outer_cleanup_receipt_valid"]=(launch["process_tree_clean"] is True and receipt_valid(cleanup,nonce=launch["cleanup_nonce"],supervisor_pid=launch["supervisor_pid"]))
    call_results=[]
    for path in sorted((directory/"private/browser").glob("call-*/management-result.json")):
        outer=read(path)
        receipt=directory/"private/browser"/outer["cleanup_receipt"]
        call_results.append(outer)
        if not (outer.get("process_tree_clean") is True and receipt_valid(receipt,nonce=outer["cleanup_nonce"],supervisor_pid=outer["supervisor_pid"])):
            raise ValueError("browser cleanup receipt not valid")
    checks["all_browser_cleanup_receipts_valid"]=bool(call_results)
    checks["browser_call_action_counts_match_management"]=(len(call_results)==summary["browser_executions"] and sum(row["result"]["actions"] for row in call_results)==summary["ui_actions"])
    case_private=Path(registration["runtime"])/"private/frozen-evaluation"/f"eval-{run_id}-{index:02d}"
    before_path=Path(registration["before"]["output"])
    finish_path=Path(summary["evaluation_record"]["output"])
    checks["sealed_case_snapshot_paths_bound"]=(before_path.parent.resolve()==case_private.resolve() and finish_path.parent.resolve()==case_private.resolve())
    if not checks["sealed_case_snapshot_paths_bound"]:
        raise ValueError("private snapshot path does not bind selected sealed case")
    before_hash=sha256(before_path)
    checks["capture_before_hash_unchanged"]=(before_hash==registration["before"]["sha256"])
    checks["finish_output_hash_unchanged"]=(sha256(finish_path)==summary["evaluation_record"]["sha256"])
    # Snapshot and evaluation objects are opaque except the explicitly audited
    # identity, provenance, timing and cleanup interface fields below.
    before=read(before_path)
    finish=read(finish_path)
    prediction_path=case_private/"prediction.json"
    ui_path=case_private/"ui-evidence.json"
    prediction=read(prediction_path)
    ui=read(ui_path)
    ack=read(directory/"private/browser/prediction-ack.json")
    declaration=successful_mcp(cli,"declare_task_prediction")
    checks["one_actual_declaration_acknowledged"]=(len(declaration)==1 and ack["acknowledgement"]["status"]=="frozen" and prediction["declaration_count"]==1)
    checks["declaration_case_and_before_binding"]=(prediction["case_id"]==registration["case_id"]==before["case_id"]==ack["request"]["case_id"]==ack["acknowledgement"]["case_id"] and prediction["before_sha256"]==ack["request"]["before_sha256"]==before_hash)
    checks["declaration_record_digest_acknowledged"]=(sha256(prediction_path)==ack["acknowledgement"]["record_sha256"])
    checks["declaration_values_match_cli_and_broker_request"]=(len(declaration)==1 and canonical(declaration[0][1]["arguments"]["prediction"])==canonical(ack["request"]["prediction"])==canonical(prediction["prediction"]))
    model_calls=successful_mcp(cli,"model_predict")
    if condition=="A":
        provenance=prediction["model_provenance"]
        matching=[]
        for path in (directory/"private/browser").glob("prediction-*/model-result.json"):
            record=read(path)
            if all(record.get(key)==provenance.get(key) for key in ("model_sha256","input_sha256")):
                matching.append((path,record))
        checks["A_actual_model_output_provenance_found"]=(len(matching)==1 and bool(model_calls))
        if len(matching)!=1:
            raise ValueError("actual frozen predictor result not uniquely bound")
        path,record=matching[0]
        matching_cli=[row for row in model_calls if row[2].get("directory")==record["directory"]]
        checks["A_actual_output_exactly_declared"]=(canonical(read(path.parent/"prediction.json"))==canonical(record["prediction"])==canonical(prediction["prediction"]) and len(matching_cli)==1 and canonical(matching_cli[0][2]["prediction"])==canonical(record["prediction"]))
        checks["A_exact_immutable_model_and_input_hash"]=(record["model_sha256"]==expected[Path(ready["revision_directory"],"behavior_model.py").as_posix()] and record["input_sha256"]==sha256(path.parent/"job.json") and ack["request"]["model_provenance"]==provenance)
        checks["A_model_call_precedes_declaration"]=(len(matching_cli)==1 and len(declaration)==1 and matching_cli[0][0]<declaration[0][0])
    else:
        checks["B_no_executable_model_tool_call_or_provenance"]=(not model_calls and not prediction.get("model_provenance") and not list((directory/"private/browser").glob("prediction-*/model-result.json")))
    gateway=json_rows(directory/"trusted-gateway.jsonl")
    provenance=finish["prediction_provenance"]
    declared=prediction["declared_at_ns"]
    first_write=provenance.get("first_business_write_started_ns")
    checks["capture_before_precedes_declaration"]=(isinstance(before.get("captured_at_ns"),int) and before["captured_at_ns"]<declared)
    checks["same_clock_declaration_ack_and_provenance"]=(declared==ack["acknowledgement"]["declared_at_ns"]==provenance.get("declared_at_ns") and provenance.get("record_sha256")==sha256(prediction_path))
    checks["declaration_precedes_independently_identified_write"]=(provenance.get("status")=="valid" and isinstance(first_write,int) and declared<first_write)
    checks["identified_write_dispatch_exists_in_original_gateway"]=(isinstance(first_write,int) and any(row.get("event_phase")=="dispatch" and row.get("management_request_started_ns")==first_write for row in gateway))
    dispatches={}
    responses={}
    for row in gateway:
        key=(row.get("method"),row.get("path"),row.get("management_request_started_ns"))
        collection=dispatches if row.get("event_phase")=="dispatch" else responses
        collection.setdefault(key,[]).append(row)
    checks["original_gateway_dispatch_response_uniquely_paired"]=(set(dispatches)==set(responses) and all(len(value)==1 for value in dispatches.values()) and all(len(value)==1 for value in responses.values()))
    barrier=read(directory/"management-barrier.json")
    checks["barrier_original_ui_summary_agree"]=(barrier==ui["management_barrier"]==summary["management_barrier"] and management_barrier_passed(barrier))
    checks["gateway_log_export_and_driver_input_match"]=(ui["events"]==gateway and sha256(ui_path)==finish["ui_evidence_sha256"])
    checks["safe_to_reset_outputs_consistent"]=(summary["safe_to_reset"] is True and finish["safe_to_reset"] is True and summary["reset_safety"]==finish["reset_safety"] and finish["reset_safety"]["safe_to_reset"] is True and finish["evaluation"]["management_safety"]==finish["reset_safety"])
    checks["capture_before_digest_matches_driver_finish"]=(finish["before_file_sha256"]==before_hash)
    checks["case_manifest_still_same_after_read"]=(sha256(manifest_path)==manifest_digest and not verify_manifest(directory,manifest))
    checks["frozen_learning_manifest_still_same_after_read"]=(sha256(learning_manifest_path)==learning_manifest_digest and all(sha256(learning/"workspace"/relative)==digest for relative,digest in expected.items()))
    return {"run_id":run_id,"case_index":index,"condition":condition,"status":"passed" if all(checks.values()) else "issues_found",
        "checks":checks,"model":"gpt-6.1-sol","model_cli_exit_code":launch["exit_code"],"model_cli_timeout":launch["timeout"],
        "actual_usage_events":actual_usage,"actual_model_predict_calls":len(model_calls),"actual_declaration_acks":len(declaration),
        "browser_executions":len(call_results),"declared_at_ns":declared,"first_business_write_started_ns":first_write,
        "write_identification_basis":"independent driver provenance timestamp matched to original dispatch; no auditor endpoint/business classification",
        "evidence":{"case_manifest_sha256":manifest_digest,"case_summary_sha256":sha256(directory/"case-summary.json"),
            "registration_sha256":sha256(directory/"registration.json"),"launch_result_sha256":sha256(launch_path),
            "cli_events_sha256":sha256(directory/"private/solar/events.jsonl"),"prediction_record_sha256":sha256(prediction_path),
            "before_sha256":before_hash,"driver_finish_sha256":sha256(finish_path),"ui_evidence_sha256":sha256(ui_path),
            "gateway_sha256":sha256(directory/"trusted-gateway.jsonl"),"learning_manifest_sha256":learning_manifest_digest},
        "qualification":"generic chain audit only; not business-oracle correctness, learning compliance rehabilitation or new isolation proof"}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",action="append",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    rows=[]
    for relative in args.case:
        directory=(EXPERIMENT/relative).resolve(strict=True)
        directory.relative_to((EXPERIMENT/"evaluations").resolve())
        rows.append(audit_case(directory))
    value={"kind":"incremental_sealed_case_management_chain_audit","observed_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"passed" if all(row["status"]=="passed" for row in rows) else "issues_found", "audited_case_denominator":len(rows),
        "registered_total_case_denominator":180,"full_180_audit_completed":False,
        "selection":"explicit sealed cases only; active cases and worker state never read",
        "evaluation_stop_contract_note":"Evaluation prompt permits temporary execution-script fixes and same-task supervision; learning AST stop adjudications are not mechanically applied here.",
        "cases":rows,"business_truth_recomputed":False,"code_or_feedback_changed":False,
        "auditor_source_sha256":sha256(Path(__file__))}
    output=Path(args.output)
    with output.open("x",encoding="utf-8") as out:json.dump(value,out,ensure_ascii=False,indent=2)
    print(json.dumps({"status":value["status"],"audited_cases":len(rows),"failed_checks":{row["run_id"]+":"+str(row["case_index"]):[name for name,passed in row["checks"].items() if not passed] for row in rows if row["status"]!="passed"},"output":str(output)}))


if __name__=="__main__":
    main()
