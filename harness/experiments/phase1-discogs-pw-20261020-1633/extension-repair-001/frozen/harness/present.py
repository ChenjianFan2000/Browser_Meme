"""Render actual per-task evidence without adding website-specific conclusions."""
import argparse
import html
import json
from pathlib import Path

from .contract import read_json


def escaped(value):
    return html.escape(str(value))


def details(label, value):
    return f"<details><summary>{escaped(label)}</summary><pre>{escaped(json.dumps(value, ensure_ascii=False, indent=2))}</pre></details>"


def render_case(out, index, case, result, rules):
    prefix = f"cases/{index + 1:02d}-{case['id']}"
    checks = result.get("independent_checks", [])
    actual_steps = {s["id"]: s for s in result["steps"]}
    body = f"<h1>{escaped(case['id'])}</h1><p>{escaped(case['goal'])}</p>"
    body += f"<p>最终状态：<strong>{escaped(result['status'])}</strong>；独立通过：{result['passed']}。</p>"
    body += "<p><a href='report.html'>返回运行报告</a> · <a href='inputs/model/rulebook.md'>冻结规则书</a> · "
    body += "<a href='inputs/scripts.py'>完整原生 Playwright 脚本</a> · "
    body += f"<a href='{prefix}/events.jsonl'>逐事件原始记录</a> · <a href='{prefix}/trace.zip'>脱敏 Playwright 轨迹</a></p>"
    body += "<p>本页按固定计划列出全部步骤；失败、拒绝、无法确认与未执行步骤均保留。"
    body += "每一步预测先落盘，再执行脚本；界面截图、网络与后台状态为不同证据渠道。</p>"
    body += details("固定任务参数", case["parameters"])
    body += details("独立终点评价", checks)
    body += details("任务监督结果", result)
    for step_index, step in enumerate(case["steps"]):
        actual = actual_steps[step["id"]]
        name = f"{step_index + 1:02d}"
        body += f"<section><h2>{step_index + 1}. {escaped(step['id'])}</h2>"
        body += f"<p>动作：{escaped(step['action'])}</p><p>判断：<strong>{escaped(actual['status'])}</strong>；"
        body += f"匹配分支：{escaped(', '.join(actual.get('matched_branches', [])) or '无')}</p>"
        body += details("动作前规则与预测", {"rules": [rules[r] for r in step["rule_ids"]],
                                        "expect": step["expect"], "invariants": step.get("invariants", [])})
        body += details("实际检查结果", actual)
        evidence = out / prefix / f"{name}.json"
        if evidence.is_file():
            data = read_json(evidence)
            network = data.get("after", {}).get("ui", {}).get("step_network", [])
            body += details("本步骤浏览器网络反馈", network)
            before = data.get("before", {}).get("backend", {}).get("table_hashes", {})
            after = data.get("after", {}).get("backend", {}).get("table_hashes", {})
            body += details("独立后台表指纹变化", {"changed_tables": [key for key in before if before[key] != after.get(key)],
                                                    "unchanged_tables": [key for key in before if before[key] == after.get(key)]})
            body += f"<p><a href='{prefix}/{name}.json'>完整前后观察 JSON</a> · "
            body += f"<a href='{prefix}/{name}.dom.json'>原始 DOM</a></p>"
        if (out / prefix / f"{name}.png").is_file():
            body += f"<a href='{prefix}/{name}.png'><img loading='lazy' src='{prefix}/{name}.png' alt='步骤 {step_index + 1} 回读截图'></a>"
        body += "</section>"
    document = """<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>任务完整运行证据</title>
<style>body{font:16px/1.65 system-ui;max-width:1100px;margin:36px auto;padding:0 20px;color:#16232e}
h1{font-size:30px}h2{font-size:22px}section{border-top:2px solid #dbe5ef;margin:30px 0;padding:12px 0}
pre{overflow:auto;white-space:pre-wrap;max-height:650px;background:#f3f6f9;padding:16px;font:13px/1.5 monospace}
details{margin:12px 0}summary{cursor:pointer;font-weight:600}img{width:100%;height:auto;border:1px solid #ccd6e0}
a{color:#1761a0}strong{background:#edf2f7;padding:3px 8px}</style>"""
    (out / f"task-{case['id']}.html").write_text(document + body + "</html>", encoding="utf-8")


def render(out):
    out = Path(out).resolve()
    plan = read_json(out / "inputs/plan.json")
    summary = read_json(out / "summary.json")
    rules = {rule["id"]: rule for rule in read_json(out / "inputs/rules.json")}
    for index, (case, result) in enumerate(zip(plan["cases"], summary["cases"])):
        render_case(out, index, case, result, rules)
    return len(summary["cases"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    print(json.dumps({"task_pages": render(args.run)}))
