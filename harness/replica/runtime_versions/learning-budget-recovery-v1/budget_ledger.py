"""Recover coordinator-owned execution budgets without reading script contents.

Dispatches and job directories reserve calls. Per-call action evidence is joined,
never added twice. An incomplete/corrupt execution is a persistent refusal, not a
way to acquire a fresh budget. This is sequential restart recovery, not a claim
of transactional admission across concurrently running broker processes.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time

from process_guard import receipt_valid

CALL = re.compile(r"call-(\d{3,})-[0-9a-f]{8}\Z")


def write_new(path, value):
    import os
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def rows(path):
    """Return complete known records as well as any integrity uncertainty."""
    path = Path(path)
    if path.is_symlink():
        return [], ["symlink_journal"]
    if not path.exists():
        return [], []
    records, errors = [], []
    for index, line in enumerate(path.read_bytes().splitlines(keepends=True), 1):
        if not line.endswith(b"\n"):
            errors.append(f"unterminated_line:{index}")
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            records.append(record)
        except (ValueError, UnicodeDecodeError):
            errors.append(f"invalid_json_line:{index}")
    return records, errors


def document(path, errors, label):
    path = Path(path)
    if path.is_symlink():
        errors.append("symlink_document:" + label)
        return None
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("document must be an object")
        return value
    except (ValueError, UnicodeDecodeError):
        errors.append("invalid_document:" + label)
        return None


def action_evidence(path):
    records, errors = rows(path)
    identifiers = []
    refusal = None
    for record in records:
        if record.get("kind") == "action_before":
            number = record.get("action")
            if not nonnegative_int(number) or number == 0:
                errors.append("invalid_action_identifier")
            else:
                identifiers.append(number)
        if record.get("kind") in {"policy_rejection", "runtime_terminated"} and not refusal:
            reason = record.get("stop_reason") or record.get("reason")
            if reason:
                prefix = "policy_rejection:" if record["kind"] == "policy_rejection" else "runtime_terminated:"
                refusal = str(reason) if str(reason).startswith(prefix) else prefix + str(reason)
    count = max(len(identifiers), max(identifiers, default=0))
    if len(set(identifiers)) != len(identifiers) or any(value != index for index,value in enumerate(sorted(identifiers), 1)):
        errors.append("nonconsecutive_or_duplicate_action_identifiers")
    return count, errors, refusal


def recover(private, config):
    private = Path(private)
    errors = []
    records, journal_errors = rows(private / "broker.jsonl")
    errors.extend("broker:" + value for value in journal_errors)
    attempts = {}
    refusal = None

    def attempt(key):
        if not isinstance(key, str) or not CALL.fullmatch(key):
            errors.append("invalid_call_identifier")
            return None
        return attempts.setdefault(key, {"dispatch":False, "results":[]})

    for record in records:
        if record.get("stop_reason") and not refusal:
            refusal = str(record["stop_reason"])
        if record.get("event") in {"dispatch", "result"}:
            item = attempt(record.get("call"))
            if item is not None:
                if record["event"] == "dispatch":
                    item["dispatch"] = True
                else:
                    item["results"].append(record)
    for directory in private.glob("call-*"):
        item = attempt(directory.name)
        if directory.is_symlink() or not directory.is_dir():
            errors.append("invalid_job_directory")
            if item is not None:
                item["unsafe_directory"] = True
        elif item is not None:
            item["directory"] = directory

    actions = 0
    recovered_calls = []
    for key, item in sorted(attempts.items()):
        call_errors = []
        counts = []
        reported = []
        if item.get("unsafe_directory"):
            known = max([row["actions"] for row in item["results"] if nonnegative_int(row.get("actions"))],default=0)
            actions += known
            recovered_calls.append({"call":key,"actions":known,"result_recorded":bool(item["results"]),"action_journal_count":0})
            continue
        directory = item.get("directory", private / key)
        count, action_errors, action_refusal = action_evidence(directory / "evidence" / "actions.jsonl")
        counts.append(count)
        call_errors.extend(action_errors)
        if action_refusal and not refusal:
            refusal = action_refusal
        for result in item["results"]:
            if nonnegative_int(result.get("actions")):
                counts.append(result["actions"])
                reported.append(result["actions"])
            else:
                call_errors.append("invalid_result_action_count")
        worker = document(directory / "evidence" / "result.json", call_errors, "worker_result")
        management = document(directory / "management-result.json", call_errors, "management_result")
        for result in (worker, management.get("result") if management else None):
            if result is not None:
                if not isinstance(result, dict) or not nonnegative_int(result.get("actions")):
                    call_errors.append("invalid_artifact_action_count")
                    continue
                counts.append(result["actions"])
                reported.append(result["actions"])
                category = result.get("failure_category")
                if not refusal and category in {"boundary", "runtime_terminated"}:
                    prefix = "policy_rejection:" if category == "boundary" else "runtime_terminated:"
                    refusal = prefix + str(result.get("terminal_reason") or result.get("error", category))
        if management:
            stop = management.get("budget", {}).get("stop_reason")
            if stop and not refusal:
                refusal = str(stop)
        if not item["results"]:
            # Only an already-written management completion with its bound
            # process receipt can establish that no old worker is still active.
            completion_confirmed = False
            if management and management.get("call") == key and management.get("process_tree_clean") is True:
                try:
                    receipt = (private / management["cleanup_receipt"]).resolve()
                    receipt.relative_to((private / "cleanup").resolve())
                    completion_confirmed = receipt_valid(receipt, nonce=management["cleanup_nonce"],
                                                        supervisor_pid=management["supervisor_pid"])
                except (KeyError, TypeError, ValueError, OSError):
                    pass
            if not completion_confirmed:
                call_errors.append("execution_completion_unconfirmed")
        charged = max(counts)
        if len(set(reported)) > 1 or (reported and count > max(reported)):
            call_errors.append("conflicting_reported_action_counts")
        actions += charged
        errors.extend(key + ":" + value for value in call_errors)
        recovered_calls.append({"call":key, "actions":charged, "result_recorded":bool(item["results"]),
                                "action_journal_count":count})

    calls = len(attempts)
    next_number = max([calls, *[int(CALL.fullmatch(key).group(1)) for key in attempts]], default=0) + 1
    bounds = {"action_limit":config["action_limit"], "script_call_limit":config.get("script_call_limit", 40),
              "time_limit_seconds":config["time_limit_seconds"]}
    origin_path = private / "budget-origin.json"
    origin = document(origin_path, errors, "budget_origin")
    now_wall, now_monotonic = time.time_ns(), time.monotonic_ns()
    if origin is None and not origin_path.exists():
        legacy = bool(records or attempts or journal_errors)
        origin = {"schema":1, "wall_ns":now_wall, "monotonic_ns":now_monotonic,
                  "bounds":bounds, "legacy_origin_unknown":legacy}
        write_new(origin_path, origin)
    elapsed = float(bounds["time_limit_seconds"])
    if origin:
        if origin.get("schema") != 1:
            errors.append("unsupported_budget_origin_schema")
        valid_clock = all(isinstance(origin.get(field), int) and not isinstance(origin[field], bool) and origin[field] > 0
                          for field in ("wall_ns", "monotonic_ns"))
        if origin.get("bounds") != bounds:
            errors.append("registered_budget_changed")
        if origin.get("legacy_origin_unknown"):
            errors.append("legacy_time_origin_unknown")
        if not valid_clock or now_wall < origin.get("wall_ns", now_wall) or now_monotonic < origin.get("monotonic_ns", now_monotonic):
            errors.append("invalid_or_reset_budget_clock")
        else:
            elapsed = max((now_wall-origin["wall_ns"])/1e9, (now_monotonic-origin["monotonic_ns"])/1e9)
    denial_path = private / "budget-recovery-denial.json"
    denial = document(denial_path, errors, "budget_recovery_denial")
    if denial and denial.get("stop_reason"):
        refusal = str(denial["stop_reason"])
    if errors and not refusal:
        refusal = "budget_recovery_unconfirmed:" + errors[0]
    if not refusal and (actions >= bounds["action_limit"] or calls >= bounds["script_call_limit"]):
        refusal = "budget_exhausted"
    if not refusal and elapsed >= bounds["time_limit_seconds"]:
        refusal = "time_budget_exhausted"
    if refusal and not denial_path.exists():
        write_new(denial_path, {"schema":1, "stop_reason":refusal, "errors":errors,
                               "known_actions":actions, "known_calls":calls, "time_ns":now_wall})
    return {"actions":actions, "calls":calls, "next_call_number":next_number,
            "closed_reason":refusal, "elapsed_seconds":elapsed, "errors":errors,
            "calls_recovered":recovered_calls, "counts_complete":not bool(errors)}
