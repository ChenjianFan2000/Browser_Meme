"""Build a human-readable index of one immutable, independently evaluated case."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

from .records import sha256, write_new_json
from .report_v002 import checked_manifest, read
from .report_lineage_v001 import checked_handoff
from .run_learning import EXPERIMENT


def build_index(report_path, handoff_path, destination, *, experiment=EXPERIMENT):
    report = read(report_path)
    handoff, _ = checked_handoff(handoff_path, expected_paths={"evaluation_report": report_path}, experiment=experiment)
    allowed = {row["run_id"] for row in handoff["packages"]
               if row.get("admitted") is True and row.get("phase_three_access_allowed") is True}
    candidates = [(run, case) for run in report["runs"] if run["run_id"] in allowed
                  for case in run["cases"]
                  if case.get("safe_to_reset") is True and case.get("ui_actions", 0) > 0]
    if not candidates:
        raise ValueError("no admitted, safely closed case with actual UI actions exists")
    run, case = min(candidates, key=lambda pair: (pair[0]["condition"] != "A", pair[0]["seed"], pair[1]["case_index"]))
    root = experiment / "evaluations" / run["run_id"] / f"case-{case['case_index']:02d}"
    manifest, manifest_hash = checked_manifest(root, "case-manifest.json", {"case-summary.json", "registration.json"})
    summary = read(root / "case-summary.json")
    destination = Path(destination).resolve()

    def link(path, label):
        path = Path(path).resolve()
        if not path.is_file():
            raise ValueError("missing indexed evidence: " + str(path))
        relative = os.path.relpath(path, destination.parent).replace("\\", "/")
        return f"[{label}]({quote(relative, safe='/.-_')})"

    def evidence_link(path, label):
        path = Path(path).resolve()
        relative = path.relative_to(root.resolve()).as_posix()
        if manifest.get(relative) != sha256(path):
            raise ValueError("unmanifested or changed indexed evidence")
        return link(path, label)

    def cell(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")

    evaluation = summary["independent_evaluation"]
    lines = ["# 单任务完整证据索引", "",
             f"运行：`{run['run_id']}`；登记案例序号：`{case['case_index']}`；案例 ID：`{case['case_id']}`。", "",
             "选取规则：在最终准入包中优先 A 组，再按种子和登记案例序号选取首个有真实 UI 动作且安全结案的案例；不按成绩筛选。", "",
             "这是管理侧只读索引。逐动作日志中的预测和分类保持原样；逐动作预测没有被本索引独立评分。案例级结论来自独立评估，执行无异常不等于预测正确。", "",
             f"独立任务结果：`{evaluation['task_outcome']}`；业务结果：`{evaluation['business_disposition']}`；UI 动作：{summary['ui_actions']}；浏览器执行：{summary['browser_executions']}。", "",
             "案例级三个预测字段的原始评分：", "", "```json",
             json.dumps(evaluation["prediction_grading"], ensure_ascii=False, indent=2), "```", "",
             "原件入口：", "",
             "- " + link(root / "case-manifest.json", "完整冻结清单") + "；SHA256：`" + manifest_hash + "`。",
             "- " + evidence_link(root / "case-summary.json", "独立评分与运行摘要") + "。",
             "- " + evidence_link(root / "registration.json", "当前案例登记、初态绑定与冻结输入") + "。",
             "- " + evidence_link(root / "private/solar/events.jsonl", "完整模型与工具调用记录（含未分派的失败提交）") + "。",
             "- " + evidence_link(root / "trusted-gateway.jsonl", "可信请求派发与响应记录") + "。",
             "- " + evidence_link(root / "management-barrier.json", "浏览器退出与请求排空检查") + "。", ""]
    selected_package = next(row for row in handoff["packages"] if row["run_id"] == run["run_id"])
    rulebook = experiment / selected_package["workspace"] / selected_package["revision"] / "rulebook.md"
    rulebook_key = selected_package["revision"].rstrip("/") + "/rulebook.md"
    if selected_package["allowed_frozen_artifact_hashes"].get(rulebook_key) != sha256(rulebook):
        raise ValueError("rulebook differs from the admitted frozen artifact")
    lines += ["学习规则书：" + link(rulebook, "原始冻结规则书") + "。", ""]
    action_before, action_after, calls = 0, 0, []
    for directory in sorted((root / "private/browser").glob("call-*")):
        if not directory.is_dir():
            continue
        job_path = directory / "job.json"
        actions_path = directory / "evidence/actions.jsonl"
        lines += ["## " + directory.name, "", "- " + evidence_link(job_path, "执行脚本与模块原件") + "。"]
        job = read(job_path)
        script_hash = hashlib.sha256(job["script"].encode("utf-8")).hexdigest()
        calls.append({"call": directory.name, "job_sha256": sha256(job_path), "script_sha256": script_hash})
        lines += [f"- 脚本 SHA256：`{script_hash}`。"]
        if not actions_path.is_file():
            lines += ["- 原始动作日志缺失，不能在本索引中补造。", ""]
            continue
        lines += ["- " + evidence_link(actions_path, "完整观察、逐动作预测、等待耗时和错误记录") + "。", ""]
        rows = [json.loads(line) for line in actions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        observations = {row["dom"]: row for row in rows if row.get("kind") == "observation" and row.get("dom")}
        before = [row for row in rows if row.get("kind") == "action_before"]
        after = {row["action"]: row for row in rows if row.get("kind") == "action_after"}
        action_before += len(before)
        action_after += len(after)

        def observation_refs(row):
            observation = observations.get((row or {}).get("observation"))
            if not observation:
                return "原记录无可用观察引用"
            return " / ".join(evidence_link(directory / "evidence" / observation[field], label)
                              for field, label in (("dom", "DOM"), ("screenshot", "截图"), ("accessibility", "无障碍树"))
                              if observation.get(field))

        for row in before:
            post = after.get(row["action"])
            lines += [f"### 动作 {row['action']}：`{cell(row['method'])}`", "",
                      "动作前预测（原样）：", "", "```json",
                      json.dumps(row["prediction"], ensure_ascii=False, indent=2), "```", "",
                      "- 动作前观察：" + observation_refs(row) + "。",
                      "- 动作后观察：" + observation_refs(post) + "。",
                      "- 原始执行耗时（秒）：`" + str(post.get("elapsed_seconds") if post else None) + "`。",
                      "- 原始执行错误：`" + cell(post.get("error") if post else "action_after_missing") + "`。", ""]
        result_path = directory / "management-result.json"
        if result_path.is_file():
            lines += ["该次执行的管理结果：" + evidence_link(result_path, "原始结果") + "。", ""]
    lines += ["## 核对信息", "", f"原始动作前记录 {action_before} 条，动作后记录 {action_after} 条；摘要登记 {summary['ui_actions']} 个动作。", "",
              "完整结果与准入依据：" + link(report_path, "180 例原始统计") + "；" + link(handoff_path, "逐包准入及隔离索引") + "。", "",
              "私有真值原件的长期归档由最终独立审核绑定，本索引不重新评分、不改写原始声明或学习包。", ""]
    provenance = {"schema_version": 1, "kind": "management_read_only_single_case_evidence_index",
                  "run_id": run["run_id"], "case_index": case["case_index"], "case_id": case["case_id"],
                  "selection_uses_outcome_score": False, "case_manifest_sha256": manifest_hash,
                  "report_sha256": sha256(report_path), "handoff_sha256": sha256(handoff_path),
                  "actions_before": action_before, "actions_after": action_after,
                  "summary_ui_actions": summary["ui_actions"], "calls": calls,
                  "lineage_validator_sha256": sha256(Path(__file__).with_name("report_lineage_v001.py")),
                  "generator_sha256": sha256(Path(__file__)), "third_stage_started": False}
    return "\n".join(lines), provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    sidecar = output.with_suffix(".provenance.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError("evidence index outputs must be new")
    body, provenance = build_index(Path(args.report), Path(args.handoff), output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(body)
    provenance["index_sha256"] = sha256(output)
    write_new_json(sidecar, provenance)
    print(json.dumps({"index": str(output), "run_id": provenance["run_id"], "case_index": provenance["case_index"]}))


if __name__ == "__main__":
    main()
