"""Read every management-dispatched browser execution, including interrupted ones."""
from __future__ import annotations

import json
from pathlib import Path


def json_lines(path):
    rows, invalid = [], 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                invalid += 1
    return rows, invalid


def browser_call_records(private_browser: Path) -> list[dict]:
    private_browser = Path(private_browser)
    journal, malformed_journal = json_lines(private_browser / "broker.jsonl")
    dispatches = {row["call"]: row for row in journal if row.get("event") == "dispatch"}
    names = set(dispatches) | {path.name for path in private_browser.glob("call-*") if path.is_dir()}
    records = []
    for name in sorted(names):
        directory = private_browser / name
        management = directory / "management-result.json"
        executor = directory / "evidence/result.json"
        actions, malformed_actions = json_lines(directory / "evidence/actions.jsonl")
        before = sum(row.get("kind") == "action_before" for row in actions)
        after = sum(row.get("kind") == "action_after" for row in actions)
        if management.exists():
            outer = json.loads(management.read_text(encoding="utf-8"))
            result = dict(outer["result"])
            source = "management-result"
        elif executor.exists():
            result = dict(json.loads(executor.read_text(encoding="utf-8")))
            source = "executor-result-without-management-completion"
        else:
            result = {"status": "error", "actions": before, "error": "execution_completion_missing"}
            source = "action-journal-fallback"
        if not management.exists():
            result["error"] = result.get("error") or "management_completion_missing"
        reported = result.get("actions")
        if isinstance(reported, bool) or not isinstance(reported, int) or reported < 0:
            reported = before
            result["error"] = result.get("error") or "invalid_action_counter"
        # Keep the two counters separately: a missing action record is evidence loss.
        records.append({"call": name, "dispatched": name in dispatches,
                        "dispatch_ns": dispatches.get(name, {}).get("time_ns"),
                        "result_source": source, "result": result, "actions": reported,
                        "actions_before": before, "actions_after": after,
                        "management_completed": management.exists(),
                        "malformed_action_lines": malformed_actions,
                        "malformed_broker_lines": malformed_journal})
    return records
