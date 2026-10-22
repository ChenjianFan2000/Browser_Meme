"""Recheck the preserved pilot using explicit UTF-8 and trusted originals."""
import json
from pathlib import Path

from .records import validate_rules, validate_prediction, validate_browser_exports, verify_manifest, write_new_json
from .run_learning import EXPERIMENT


def main():
    root = EXPERIMENT / "runs/pilot-001"
    manifest = json.loads((root / "learning-manifest.json").read_text(encoding="utf-8"))["files"]
    assert not verify_manifest(root, manifest)
    workspace = root / "workspace"
    ready = json.loads((workspace / "READY.json").read_text(encoding="utf-8"))
    revision = workspace / ready["revision_directory"]
    rules = json.loads((revision / "rules.json").read_text(encoding="utf-8"))
    validate_rules(rules, workspace)
    exports = validate_browser_exports(workspace, root / "private/browser", rules)
    predictions = []
    after = 0
    for path in (root / "private/browser").glob("call-*/evidence/actions.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["kind"] == "action_before":
                validate_prediction(event["prediction"])
                predictions.append(event["prediction"])
            if event["kind"] == "action_after":
                after += 1
    for name in ("scripts.py", "behavior_model.py"):
        compile((revision / name).read_text(encoding="utf-8"), name, "exec")
    launch = json.loads((root / "private/solar/launch-result.json").read_text(encoding="utf-8"))
    counts = {}
    for rule in rules:
        counts[rule["status"]] = counts.get(rule["status"], 0) + 1
    result = {"status": "passed", "kind": "pilot_artifact_and_evidence_review_not_formal_score",
              "original_summary_preserved": True,
              "original_summary_failure": "Windows controller used GBK to read a UTF-8 model artifact; no artifact was changed",
              "model_exit_code": launch["exit_code"], "model_timeout": launch["timeout"],
              "model_elapsed_seconds": launch["elapsed_seconds"], "model_usage_events": launch["usage_events"],
              "actions_with_valid_pre_action_prediction": len(predictions), "action_after_records": after,
              "browser_executions": len(list((root / "private/browser").glob("call-*"))),
              "rule_count": len(rules), "rule_status_counts": counts, "trusted_evidence": exports,
              "frozen_revision": ready["revision_directory"], "stop_reason": ready["stop_reason"],
              "limitations": ready["limitations"], "final_scripts_syntax_checked": True,
              "final_scripts_real_ui_validation_after_stop": False, "formal_scores_reported": False}
    assert len(predictions) == after == 72
    write_new_json(EXPERIMENT / "pilot-review-001.json", result)
    print(json.dumps({key: result[key] for key in ("status", "actions_with_valid_pre_action_prediction", "browser_executions", "rule_count", "rule_status_counts", "stop_reason")}))


if __name__ == "__main__":
    main()
