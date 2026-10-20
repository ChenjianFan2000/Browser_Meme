"""Build the offline Chinese research report from frozen results and editorial notes.

Run from the repository root: python scripts/build_research_report.py
This does not call an LLM, run candidates, or modify experiment artifacts.
"""
from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "RESEARCH_REPORT.html"


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def link(path: str, label: str, external: bool = False) -> str:
    suffix = ' target="_blank" rel="noopener noreferrer"' if external else ""
    return f'<a href="{esc(path)}"{suffix}>{esc(label)}</a>'


CATALOG = {p["id"]: p for p in load("papers/catalog.json")["papers"]}
NOTES = load("papers/report_notes.json")["papers"]
SUMMARY = load("artifacts/results/summary.json")
ROWS = {(r["method"], r["phase"], r["split"]): r for r in SUMMARY["rows"]}
REGISTRY = load("artifacts/method_registry.json")
FROZEN = load("artifacts/frozen_run.json")
SOURCES = load("SOURCE_MANIFEST.json")
AUDIT = load("artifacts/upstream_audit.json")
METHODS = {
    "current": "当前方案：规则注释＋代码",
    "verienv_clone": "VeriEnv 行为克隆",
    "worldcoder": "WorldCoder 提示适配",
    "patchworld": "PatchWorld 提示适配",
    "gif_mcts": "GIF 单候选适配",
    "poe_world": "PoE 属性专家适配",
    "agent2world": "Agent2World code-agent 适配",
    "luna_direct": "Luna Direct",
    "wma": "WMA 提示适配",
    "webdreamer": "WebDreamer 提示适配",
    "webevolver": "WebEvolver 提示适配",
    "webworld": "WebWorld 提示适配",
}
PAPER_BY_METHOD = {p["method"]: p["key"] for p in NOTES if p["method"]}


def row(method: str, phase: str, split: str):
    return ROWS[method, phase, split]


def is_code(method: str) -> bool:
    return REGISTRY[method]["kind"] == "code"


def fraction(method: str, phase: str, split: str, key="exact", percentage=False):
    r = row(method, phase, split)
    numerator = r[key]
    denominator = r["steps"] if key == "step_exact" else r["n"]
    value = f"{numerator}/{denominator}"
    if percentage:
        value += f' <small>({numerator / denominator:.1%})</small>'
    return value


def table(headers, rows, caption="", classes="", raw=False, aria_label=""):
    head = "".join(f'<th scope="col">{esc(c)}</th>' for c in headers)
    body = []
    for cells in rows:
        rendered = []
        for index, cell in enumerate(cells):
            tag = "th" if index == 0 else "td"
            scope = ' scope="row"' if index == 0 else ""
            rendered.append(f'<{tag}{scope}>{cell if raw else esc(cell)}</{tag}>')
        body.append("<tr>" + "".join(rendered) + "</tr>")
    label = f'<caption>{esc(caption)}</caption>' if caption else ""
    return f'<div class="table-scroll" tabindex="0" role="region" aria-label="{esc(aria_label or caption or headers[0])}"><table class="{esc(classes)}">{label}<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def method_label(method):
    dest = f'#paper-{PAPER_BY_METHOD[method]}' if method in PAPER_BY_METHOD else '#current'
    return link(dest, METHODS[method])


def result_tables():
    initial, repaired, adapted = [], [], []
    for method in METHODS:
        initial.append([
            method_label(method), "代码" if is_code(method) else "直接预测",
            fraction(method, "initial", "one_step", percentage=True),
            fraction(method, "initial", "rollout", "all_steps_exact", True),
            fraction(method, "initial", "rollout", "step_exact"),
            f'{sum(row(method, "initial", s)["valid"] for s in ("one_step", "rollout", "drift"))}/48',
        ])
        before = "repaired" if is_code(method) else "initial"
        if is_code(method):
            repaired.append([
                method_label(method),
                fraction(method, "initial", "one_step") + " → " + fraction(method, "repaired", "one_step"),
                fraction(method, "repaired", "rollout", "all_steps_exact", True),
                fraction(method, "repaired", "rollout", "step_exact"),
            ])
        adapted.append([
            method_label(method), "修正后代码" if is_code(method) else "初始直接预测",
            fraction(method, before, "drift"), fraction(method, "adapted", "drift", percentage=True),
            fraction(method, before, "unchanged_v1") + " → " + fraction(method, "adapted", "unchanged_v1"),
        ])
    return (
        table(["Luna 条件", "表示", "一步完整匹配", "多步完整轨迹", "多步正确步数", "结构合法轨迹"], initial, "表 A · 相同初始学习证据；12 个条件", "results", True),
        table(["Luna 代码条件", "一步：初稿 → 修正", "多步完整轨迹", "多步正确步数"], repaired, "表 B · 一次开发反例修正后；7 个代码条件", "results", True),
        table(["Luna 条件", "适应前版本", "变化测试：适应前", "适应后", "未变化旧案例：前 → 后"], adapted, "表 C · 增加 6 条新规则证据后的恢复与保留", "results", True),
    )


def local_paper_table(paper):
    method = paper["method"]
    if not method:
        return '<p class="no-score"><strong>独立预测成绩：未运行／不适用。</strong>没有以 0 分替代缺失结果。</p>'
    cells = [["初稿（相同 36 条证据）", fraction(method, "initial", "one_step"), fraction(method, "initial", "rollout", "all_steps_exact")]]
    if is_code(method):
        cells.append(["一次开发修正后", fraction(method, "repaired", "one_step"), fraction(method, "repaired", "rollout", "all_steps_exact")])
    before = "repaired" if is_code(method) else "initial"
    local = table(["本轮阶段", "一步 /24", "完整组合 /12"], cells, raw=True, aria_label=paper["name"] + " 本地成绩")
    local += f'<p class="local-score">规则变化：<strong>{fraction(method, before, "drift")} → {fraction(method, "adapted", "drift")}</strong>；未变化案例：{fraction(method, before, "unchanged_v1")} → {fraction(method, "adapted", "unchanged_v1")}。</p>'
    local += f'<p class="small">{link(f"artifacts/requests/{method}/initial.json", "原始请求")} · {link(f"artifacts/results/{method}.initial.test.json", "逐例预测与评分")}</p>'
    return local


def source_links(paper):
    cat = CATALOG[paper["catalog_id"]]
    items = [link(cat["paper"], "论文原文", True)]
    if cat.get("repository"):
        items.append(link(cat["repository"], "作者仓库", True))
    if paper.get("source_dir"):
        items.append(link(paper["source_dir"] + "/", "本地源码"))
    if paper.get("download_prefix"):
        matches = list((ROOT / "artifacts/source_downloads").glob(paper["download_prefix"] + "*-source.zip"))
        assert len(matches) == 1, (paper["key"], matches)
        items.append(link(matches[0].relative_to(ROOT).as_posix(), "源码 ZIP"))
    if paper["key"] == "verienv":
        items.append(link("chae26a.pdf", "本地 PDF"))
    if paper["key"] == "memento3":
        items.append(link("../2610.11794v1.pdf", "本地 PDF"))
    return " · ".join(items)


def paper_card(paper, index):
    cat = CATALOG[paper["catalog_id"]]
    original_table = table(paper["result_headers"], paper["result_rows"], aria_label=paper["name"] + " 原论文成绩")
    original_source = link(cat["paper"], paper["source_locator"], True)
    return f'''
    <article class="paper-card" id="paper-{esc(paper['key'])}" data-group="{esc(paper['group'])}">
      <div class="paper-top"><span class="paper-number">{index:02}</span><div><h3>{esc(paper['name'])} <span class="year">{cat['year']}</span></h3><p>{esc(paper['tagline'])}</p></div><span class="pill">{esc(paper['group_label'])}</span></div>
      <p class="paper-title" lang="en">{esc(cat['title'])}</p>
      <details open class="paper-detail">
        <summary>阅读方法、原论文实验、本轮测试与判断</summary>
        <div class="paper-grid">
          <section class="paper-method"><h4>做了什么</h4><p>{esc(paper['mechanism'])}</p><p class="small"><strong>实验设置：</strong>{esc(paper['original_setup'])}</p></section>
          <section class="paper-original"><h4><span class="evidence paper">论文报告</span> 原始数值实验</h4>{original_table}<p class="small">出处：{original_source}。{esc(paper['original_caution'])}</p></section>
          <section class="paper-local"><h4><span class="evidence local">本地实测</span> 我们实际做了什么</h4><p>{esc(paper['local_impl'])}</p>{local_paper_table(paper)}<p class="scope"><strong>执行边界：</strong>{esc(paper['not_run'])}</p></section>
          <section class="paper-takeaway"><h4><span class="evidence inference">综合判断</span> 对当前研究的意义</h4><p>{esc(paper['implication'])}</p></section>
        </div>
      </details>
      <p class="source-links">{source_links(paper)}</p>
    </article>'''


CSS = r'''
:root{--ink:#172c3b;--muted:#526575;--paper:#fff;--canvas:#f4f6f7;--line:#dbe3e8;--teal:#08786e;--teal-soft:#ecf7f4;--blue:#345ca6;--blue-soft:#f0f3fb;--amber:#835119;--amber-soft:#fff6e8;--radius:14px}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{margin:0;background:var(--canvas);color:var(--ink);font-family:Inter,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;font-size:15px;line-height:1.8;-webkit-font-smoothing:antialiased}a{color:#195fa1;text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}a:hover{color:#004c45}button,input,select{font:inherit}button,select{cursor:pointer}button{border:1px solid #aebecb;border-radius:7px;background:white;color:var(--ink);padding:7px 13px}button:hover{background:var(--blue-soft)}:focus-visible{outline:3px solid #b56717;outline-offset:3px}p{margin:10px 0}h1,h2,h3,h4{line-height:1.4;letter-spacing:-.02em}h1{font-size:clamp(28px,3vw,42px);margin:12px 0 20px;max-width:23em}h2{font-size:26px;margin:0 0 12px}h3{font-size:20px;margin:0 0 10px}h4{font-size:16px;margin:0 0 10px}.small,small{font-size:12.5px;color:var(--muted);line-height:1.8}.muted{color:var(--muted)}.eyebrow{font-size:12px;letter-spacing:.14em;font-weight:700;color:var(--teal)}.skip-link{position:fixed;left:20px;top:-70px;z-index:50;background:#fff;padding:12px}.skip-link:focus{top:10px}.rail{position:fixed;inset:0 auto 0 0;width:224px;background:#102a3b;color:#dbe6ec;padding:32px 22px;display:flex;flex-direction:column;gap:24px;overflow-y:auto;z-index:10}.rail-title{color:#fff;font-size:19px;font-weight:700;letter-spacing:.04em}.rail-subtitle{font-size:12px;color:#a9c1cf;line-height:1.65}.rail nav a{display:flex;gap:12px;color:#dbe6ec;text-decoration:none;padding:9px 8px;border-radius:6px;font-size:13px;line-height:1.8}.rail nav a:hover,.rail nav a[aria-current]{color:#fff;background:#294a60}.rail nav a span{color:#98b9cb;font-variant-numeric:tabular-nums}.rail .rail-footer{margin-top:auto;border-top:1px solid #395467;padding-top:16px;font-size:12px;color:#b4cbd7}.rail-footer a{color:#d5e9f3}.rail button{background:#26465a;color:#fff;border-color:#688397;width:100%}.layout{margin-left:224px;padding:36px clamp(22px,3.4vw,58px) 60px}.content{max-width:1210px;margin:0 auto}.hero{background:#fff;border:1px solid var(--line);border-top:5px solid var(--teal);border-radius:var(--radius);padding:36px 40px}.hero .lead{font-size:18px;line-height:1.85;max-width:56em}.meta{display:flex;flex-wrap:wrap;gap:8px 22px;font-size:12px;color:var(--muted);margin-top:20px}.verdict{padding:19px 22px;border-left:4px solid var(--teal);background:var(--teal-soft);margin-top:24px;border-radius:0 8px 8px 0}.verdict p{margin:5px 0}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}.stat{padding:17px 20px;background:#fff;border:1px solid var(--line);border-radius:10px}.stat b{font-size:29px;color:var(--teal);line-height:1.3;display:block;font-variant-numeric:tabular-nums}.stat span{font-size:12px;color:var(--muted)}.block{margin-top:42px;scroll-margin-top:25px}.section-head{display:flex;align-items:baseline;gap:16px;border-bottom:1px solid #cbd7df;margin-bottom:20px;padding-bottom:12px}.section-num{font-weight:700;color:var(--teal);font-size:13px;letter-spacing:.08em}.section-head h2{margin:0}.section-intro{max-width:68em}.panel{background:white;border:1px solid var(--line);border-radius:var(--radius);padding:24px;margin:18px 0}.grid-two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.grid-two>.panel{margin:0}.evidence{display:inline-block;border-radius:4px;font-weight:600;font-size:11px;padding:2px 7px;letter-spacing:.02em;vertical-align:middle;white-space:nowrap}.evidence.paper{color:var(--blue);background:#e8eefb}.evidence.local{color:#00695f;background:#dff2ec}.evidence.inference{color:var(--amber);background:#ffedcf}.legend{display:flex;flex-wrap:wrap;gap:10px 20px;margin:14px 0;font-size:12px;color:var(--muted)}.note{border-left:3px solid #c08a40;background:var(--amber-soft);padding:13px 18px;margin:18px 0;font-size:13px}.table-scroll{max-width:100%;overflow:auto;margin:12px 0;border:1px solid var(--line);border-radius:9px;scrollbar-width:thin}table{width:100%;border-collapse:collapse;background:white;font-size:13px;line-height:1.7}caption{text-align:left;padding:12px 14px;font-weight:600;background:#f4f7f9;color:var(--ink)}th,td{padding:11px 14px;text-align:left;border-bottom:1px solid #e4e9ed;vertical-align:top}thead th{background:#eef3f6;font-size:12px;color:#455c6c;font-weight:650}tbody th{font-weight:600}tbody tr:last-child>*{border-bottom:0}tbody tr:hover>*{background:#f7fbfc}.results{min-width:780px}.results td{font-variant-numeric:tabular-nums;white-space:nowrap}.results tbody tr:has(a[href="#current"]){background:#eff9f5}.results th:first-child{min-width:205px}.results small{display:inline-block;margin-left:3px;font-size:11px}.pill{font-size:11px;color:#3d586b;background:#edf2f6;padding:4px 9px;border-radius:20px;white-space:nowrap}.paper-card{background:white;border:1px solid var(--line);border-radius:var(--radius);padding:25px 28px;margin:20px 0;scroll-margin-top:25px}.paper-top{display:flex;gap:16px;align-items:flex-start}.paper-top h3{font-size:23px;margin:0}.paper-top p{margin:3px 0 0;font-size:14px;color:var(--muted)}.paper-top .pill{margin-left:auto;margin-top:4px}.paper-number{font-size:16px;font-weight:700;color:#7d97a9;border-top:2px solid #b6c9d5;padding-top:5px;line-height:1.7;min-width:25px}.year{font-size:12px;color:var(--muted);letter-spacing:0;margin-left:8px;font-weight:400}.paper-title{color:#607483;font-size:11.5px;line-height:1.6;padding-left:41px}.paper-detail>summary{font-size:12px;color:#426276;cursor:pointer;padding:8px 0}.paper-grid{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:16px;margin-top:12px}.paper-grid>section{min-width:0;padding:19px;border-radius:9px;background:#f8fafb}.paper-grid p{font-size:13px}.paper-grid .paper-original{background:#f3f5fc}.paper-grid .paper-local{background:#edf7f4}.paper-grid .paper-takeaway{background:#fcf7ef}.paper-grid h4{font-size:14px}.paper-grid table{font-size:12px}.paper-grid th,.paper-grid td{padding:8px 10px}.paper-grid .small{font-size:12px}.paper-grid .scope{font-size:12px;color:#425f5a;border-top:1px solid #c4ded4;padding-top:10px}.source-links{font-size:12px;margin:17px 0 0;padding-top:13px;border-top:1px solid #e7edf0}.local-score{font-variant-numeric:tabular-nums}.no-score{padding:12px;background:#fff;border:1px dashed #a7b7be;border-radius:6px}.toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:10px;background:white;border:1px solid var(--line);padding:14px 16px;border-radius:10px;margin:16px 0}.toolbar label{font-size:12px;font-weight:600}.toolbar input{border:1px solid #aebecb;border-radius:6px;padding:8px 10px;min-width:150px;flex:1}.toolbar select,.chart-controls select{padding:8px;border:1px solid #aebecb;border-radius:6px;background:white;color:var(--ink);max-width:100%}.toolbar button{font-size:12px}.toolbar .count{font-size:12px;color:var(--muted);min-width:55px}.paper-index{display:flex;gap:8px;flex-wrap:wrap}.paper-index a{display:inline-block;text-decoration:none;padding:4px 10px;border:1px solid #c3d2dc;border-radius:5px;background:#fff;font-size:12px}.timeline{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:22px 0}.timeline>div{padding:16px 15px;border-radius:8px;background:#fff;border:1px solid var(--line);border-top:3px solid #559d95}.timeline b{display:block;font-size:21px;line-height:1.4;color:var(--teal)}.timeline strong{font-size:13px}.timeline p{font-size:12px;color:var(--muted);margin:6px 0 0}.flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:20px 0}.flow>div{border:1px solid #c9dcd9;background:#f3f9f7;border-radius:9px;padding:16px}.flow .planned{border-style:dashed;border-color:#b6bfc8;background:#f7f8fa}.flow strong{display:block;font-size:14px;margin-bottom:6px}.flow p{font-size:12px;margin:4px 0;color:#4b6570}.phase-title{display:flex;gap:10px;align-items:center;margin-top:28px}.phase-title h3{margin:0}.phase-title>span{background:#dbe9ef;color:#294d61;font-size:12px;font-weight:700;padding:2px 8px;border-radius:4px}.chart-controls{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;margin-bottom:14px}.chart-controls label{font-size:13px;font-weight:600}.chart-axis{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-left:252px;margin-right:84px}.chart-row{display:grid;grid-template-columns:240px 1fr 74px;gap:12px;align-items:center;line-height:1.4;padding:7px 0;font-size:12px}.chart-label{overflow-wrap:anywhere}.chart-track{height:18px;background:repeating-linear-gradient(to right,#edf2f5,#edf2f5 calc(25% - 1px),#dce5eb calc(25% - 1px),#dce5eb 25%);border-radius:3px;overflow:hidden}.chart-bar{height:100%;background:var(--teal);border-radius:3px}.chart-bar.direct{background:var(--blue)}.chart-row.current{font-weight:700;background:#edf7f4;margin:0 -10px;padding:7px 10px;border-radius:5px}.chart-score{text-align:right;font-variant-numeric:tabular-nums}.chart-key{display:inline-flex;gap:7px;align-items:center}.swatch{width:10px;height:10px;background:var(--teal);border-radius:2px;display:inline-block}.swatch.direct{background:var(--blue)}.bar-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.bar-summary>div{padding:15px;background:#fff;border:1px solid var(--line);border-radius:8px}.bar-summary b{font-size:25px;color:var(--teal);display:block;font-variant-numeric:tabular-nums}.bar-summary span{font-size:12px;color:var(--muted)}.mini-track{height:6px;background:#e8eef2;margin-top:8px;border-radius:2px}.mini-track i{height:100%;display:block;background:var(--teal);border-radius:2px}.case-flow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0}.case-flow span{font-size:12px;padding:5px 9px;background:#eaf0f4;border-radius:5px}.case-flow em{font-style:normal;color:#7f94a2}.outcome{padding:12px 14px;border-radius:7px;background:#fff4e8;font-size:13px;margin-top:10px}.claim-table{min-width:740px}.claim-table td:first-of-type{min-width:87px}.priority{display:grid;grid-template-columns:46px minmax(0,1fr);gap:12px;margin:18px 0;padding:21px 23px;background:#fff;border:1px solid var(--line);border-radius:10px}.priority>.rank{font-size:25px;line-height:1.4;color:var(--teal);font-weight:650}.priority h3{margin:0;font-size:18px}.priority p{font-size:13px;margin:8px 0}.priority .test{border-top:1px solid var(--line);padding-top:10px;color:var(--muted)}.codeblock{white-space:pre-wrap;overflow-wrap:anywhere;font-family:Consolas,monospace;font-size:12px;line-height:1.9;color:#1c4057;background:#edf3f7;border-radius:8px;padding:18px}code{font-family:Consolas,monospace;font-size:.9em;background:#edf1f3;padding:1px 4px;border-radius:3px}.archive-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.archive-grid a{padding:14px 17px;background:#fff;border:1px solid var(--line);border-radius:8px;text-decoration:none;font-size:13px}.archive-grid a small{display:block;margin-top:3px;font-size:11px}.source-list{font-size:12px;padding-left:23px}.source-list li{margin:10px 0;overflow-wrap:anywhere}footer{border-top:1px solid #ccd8df;margin-top:40px;padding-top:18px;font-size:12px;color:var(--muted)}[hidden]{display:none!important}.empty{padding:20px;border:1px dashed #a2b4bf;text-align:center}.js-only{display:none}.js .js-only{display:flex}.print-only{display:none}li{margin:5px 0}ul,ol{padding-left:23px}
@media(min-width:1650px){body{font-size:16px}.layout{padding-left:62px;padding-right:62px}}
@media(max-width:1100px){.rail{width:190px;padding:25px 16px}.layout{margin-left:190px;padding:25px 22px}.hero{padding:27px}.paper-grid{grid-template-columns:1fr}.timeline{grid-template-columns:repeat(3,minmax(0,1fr))}.chart-row{grid-template-columns:190px 1fr 70px}.chart-axis{margin-left:202px;margin-right:82px}.paper-grid .paper-original{order:2}.paper-grid .paper-local{order:3}.paper-grid .paper-takeaway{order:4}}
@media(max-width:760px){body{font-size:14px}.rail{position:relative;inset:auto;width:auto;padding:16px 18px;gap:8px}.rail-title{font-size:16px}.rail-subtitle,.rail-footer,.rail>.print-button{display:none!important}.rail nav{display:flex;overflow:auto;gap:4px;white-space:nowrap}.rail nav a{font-size:11px;padding:7px}.rail nav a span{display:none}.layout{margin:0;padding:18px 14px 40px}.hero{padding:24px 20px}.hero .lead{font-size:16px}.hero h1{font-size:28px}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.stat{padding:14px}.stat b{font-size:25px}.section-head{gap:10px}h2{font-size:22px}.grid-two{grid-template-columns:1fr}.timeline{grid-template-columns:repeat(2,minmax(0,1fr))}.flow{grid-template-columns:1fr}.paper-card{padding:19px 16px}.paper-top{gap:10px;flex-wrap:wrap}.paper-top>div{flex:1}.paper-top h3{font-size:21px}.paper-top .pill{margin-left:35px;margin-top:0}.paper-number{min-width:24px}.paper-title{padding-left:35px}.paper-grid>section{padding:15px}.paper-grid th,.paper-grid td{padding:7px}.paper-grid table{font-size:11.5px}.paper-original .table-scroll table{min-width:360px}.toolbar{padding:12px}.toolbar input{min-width:110px;width:100px}.toolbar select{max-width:150px}.chart-row{grid-template-columns:115px minmax(0,1fr) 57px;gap:7px;font-size:10.5px;padding:8px 0}.chart-row.current{padding:8px 6px;margin:0 -6px}.chart-axis{margin-left:122px;margin-right:64px}.chart-track{height:17px}.bar-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.panel{padding:19px 16px}.archive-grid{grid-template-columns:1fr}.priority{padding:17px 15px;grid-template-columns:28px minmax(0,1fr)}.priority>.rank{font-size:20px}.results th:first-child{min-width:180px}.meta{gap:6px 12px;font-size:11px}.block{margin-top:32px}}
.paper-number{color:#536e81}.matrix{min-width:660px}
@media(max-width:760px){.hero h1{font-size:clamp(20px,6.5vw,26px);text-wrap:balance}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{@page{size:A4;margin:15mm 12mm}html{scroll-behavior:auto}body{background:white;color:#142a3a;font-size:10pt;line-height:1.65}.rail,.skip-link,.js-only,.toolbar,.paper-index,.paper-detail>summary,.print-button{display:none!important}.layout{margin:0;padding:0}.content{max-width:none}.hero{border:0;border-top:3px solid var(--teal);padding:16px 0}.hero h1{font-size:25pt}.hero .lead{font-size:12pt}.block{margin-top:24px}.section-head{break-after:avoid}h2{font-size:18pt}h3{font-size:14pt}h4{font-size:11pt}h1,h2,h3,h4{break-after:avoid}.stats{gap:8px}.stat{padding:10px}.stat b{font-size:22pt}.paper-card{break-before:page;border:0;padding:0;margin-top:12px}.paper-detail:not([open])>*:not(summary){display:block!important}.paper-grid{display:block}.paper-grid>section{padding:12px;margin:10px 0;break-inside:avoid}.paper-card[hidden]{display:block!important}.paper-top{gap:12px}.paper-title{padding-left:37px}.table-scroll{overflow:visible;border-radius:0}.table-scroll table{min-width:0!important;table-layout:auto;font-size:8pt}.results th:first-child{min-width:0}.results td{white-space:normal}.results small{display:block;margin:0}.table-scroll th,.table-scroll td{padding:7px 8px;overflow-wrap:anywhere}thead{display:table-header-group}tr{break-inside:avoid}.panel,.priority,.case-flow,.verdict{break-inside:avoid}.grid-two,.flow{display:block}.grid-two>.panel,.flow>div{margin-bottom:12px}.timeline{grid-template-columns:repeat(5,minmax(0,1fr))}.timeline>div{padding:10px}.timeline p{font-size:8pt}.claim-table{min-width:0}.chart-row{grid-template-columns:190px 1fr 70px;font-size:9pt}.chart-axis{margin-left:202px;margin-right:82px}.chart-bar,.mini-track i{print-color-adjust:exact;-webkit-print-color-adjust:exact}.archive-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.source-list{font-size:8pt}.print-only{display:block}.paper-top .pill{font-size:9pt}.paper-grid p,.priority p{font-size:9pt}.small,small,.source-links{font-size:8pt}a{color:#144c78;text-decoration:underline}footer{font-size:8pt}}
@media print{.paper-grid>section{padding:9px 10px;margin:7px 0}.paper-grid p{margin:6px 0;line-height:1.6}.paper-grid h4{margin-bottom:6px}.paper-grid table{font-size:8pt;line-height:1.5}.paper-grid th,.paper-grid td{padding:5px 7px}.source-links{padding-top:6px;margin-top:8px}.paper-title{margin:7px 0;font-size:8pt}.table-scroll{margin:8px 0}.matrix{min-width:0}}
'''


JS = r'''
document.documentElement.classList.add('js');
const allPapers = [...document.querySelectorAll('.paper-card')];
const search = document.getElementById('paper-search');
const category = document.getElementById('paper-category');
function filterPapers(){
  const text = search.value.trim().toLocaleLowerCase();
  let count = 0;
  allPapers.forEach(card => {
    card.hidden = !((category.value === 'all' || category.value === card.dataset.group) && card.textContent.toLocaleLowerCase().includes(text));
    if(!card.hidden) count++;
  });
  document.getElementById('paper-count').textContent = count + ' / 12 篇';
  document.getElementById('paper-empty').hidden = count > 0;
}
search.addEventListener('input',filterPapers);
category.addEventListener('change',filterPapers);
document.getElementById('expand-all').addEventListener('click',()=>allPapers.filter(c=>!c.hidden).forEach(c=>c.querySelector('details').open=true));
document.getElementById('collapse-all').addEventListener('click',()=>allPapers.filter(c=>!c.hidden).forEach(c=>c.querySelector('details').open=false));
function revealHash(){
  if(!location.hash.startsWith('#paper-')) return;
  const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if(!target) return;
  search.value=''; category.value='all'; filterPapers();
  target.querySelector('details').open=true;
  requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
}
window.addEventListener('hashchange',revealHash);
revealHash();
const chartData = JSON.parse(document.getElementById('chart-data').textContent);
const chartChoice = document.getElementById('chart-choice');
function drawChart(){
  const data=chartData[chartChoice.value];
  document.getElementById('chart-title').textContent=data.title;
  document.getElementById('chart-note').textContent=data.note;
  const plot=document.getElementById('comparison-chart');
  plot.replaceChildren();
  data.rows.forEach(r=>{
    const el=document.createElement('div');el.className='chart-row'+(r.id==='current'?' current':'');
    const name=document.createElement('span');name.className='chart-label';name.textContent=r.name;
    const track=document.createElement('div');track.className='chart-track';track.setAttribute('aria-hidden','true');
    const bar=document.createElement('div');bar.className='chart-bar'+(r.kind==='direct'?' direct':'');bar.style.width=(100*r.numerator/r.denominator)+'%';track.append(bar);
    const value=document.createElement('span');value.className='chart-score';value.textContent=r.numerator+'/'+r.denominator;
    value.title=(100*r.numerator/r.denominator).toFixed(1)+'%';
    el.append(name,track,value);plot.append(el);
  });
}
chartChoice.addEventListener('change',drawChart);drawChart();
let printState=[];
let printDetails=[];
window.addEventListener('beforeprint',()=>{
  printState=allPapers.map(c=>({hidden:c.hidden,open:c.querySelector('details').open}));
  printDetails=[...document.querySelectorAll('details')].map(el=>({el,open:el.open}));
  printDetails.forEach(item=>item.el.open=true);
  allPapers.forEach(c=>{c.hidden=false;c.querySelector('details').open=true;});
  document.getElementById('paper-empty').hidden=true;
});
window.addEventListener('afterprint',()=>{
  allPapers.forEach((c,i)=>{if(printState[i]){c.hidden=printState[i].hidden;c.querySelector('details').open=printState[i].open;}});
  printDetails.forEach(item=>item.el.open=item.open);
  filterPapers();
});
document.querySelectorAll('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()));
const sections=[...document.querySelectorAll('main > section[id]')];
if('IntersectionObserver' in window){
  const observer=new IntersectionObserver(entries=>{
    const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);
    if(!visible.length)return;
    document.querySelectorAll('.rail nav a').forEach(a=>{if(a.getAttribute('href')==='#'+visible[0].target.id)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});
  },{rootMargin:'-5% 0px -70% 0px',threshold:0});sections.forEach(s=>observer.observe(s));
}
'''


def chart_payload():
    configs = {
        "initial-rollout": ("初稿 · 开放环完整轨迹", "initial", "rollout", "all_steps_exact", "12 个条件共享 36 条初始证据；12 条轨迹共 45 步。每条全部步骤正确才计入。"),
        "initial-one": ("初稿 · 一步完整匹配", "initial", "one_step", "exact", "相同初始学习证据，不代表相同 token 或运行计算量；直接条件为批量预测。"),
        "repaired-rollout": ("一次开发修正后 · 完整轨迹", "repaired", "rollout", "all_steps_exact", "仅 7 个代码条件接受了开发反例；本图不与没有这轮反馈的直接条件做公平性结论。"),
        "repaired-one": ("一次开发修正后 · 一步完整匹配", "repaired", "one_step", "exact", "7 个条件均达到 24/24；开发与一步测试共享操作模板、使用不同对象种子。"),
        "adapted-drift": ("六条新证据后 · 规则变化预测", "adapted", "drift", "exact", "12 条变化案例。多数条件达到上限；部分组合前提未出现在六条证据中，猜中不能证明充分辨识。"),
    }
    output = {}
    for key, (title, phase, split, metric, note) in configs.items():
        values = []
        for method, name in METHODS.items():
            if (method, phase, split) not in ROWS:
                continue
            r = row(method, phase, split)
            values.append({"id": method, "name": name, "kind": "code" if is_code(method) else "direct", "numerator": r[metric], "denominator": r["n"]})
        output[key] = {"title": title, "note": note, "rows": values}
    return output


def chart_static(data):
    lines = []
    for r in data["rows"]:
        css = "chart-row current" if r["id"] == "current" else "chart-row"
        bar = "chart-bar direct" if r["kind"] == "direct" else "chart-bar"
        lines.append(f'<div class="{css}"><span class="chart-label">{esc(r["name"])}</span><div class="chart-track" aria-hidden="true"><div class="{bar}" style="width:{100*r["numerator"]/r["denominator"]}%"></div></div><span class="chart-score">{r["numerator"]}/{r["denominator"]}</span></div>')
    return "".join(lines)


def main():
    assert len(NOTES) == 12 and len(METHODS) == 12
    assert set(METHODS) == {key for key, value in REGISTRY.items() if value["kind"] in ("code", "direct")}
    assert not SUMMARY["failures"], "Report cannot silently omit replay failures"
    assert len(FROZEN["records"]) == FROZEN["model_calls"] == 31
    assert len(AUDIT["projects"]) == 11
    # Recheck provenance without executing any model or regenerating a split.
    checked = 0
    for record in FROZEN["records"]:
        for key in ("input", "output"):
            path = ROOT / Path(record[key].replace("\\", "/"))
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record[f"{key}_sha256"], path
            checked += 1
    assert {p["catalog_id"] for p in NOTES} == set(CATALOG)
    initial_table, repaired_table, adapted_table = result_tables()
    cards = "".join(paper_card(p, i) for i, p in enumerate(NOTES, 1))
    paper_index = "".join(link(f'#paper-{p["key"]}', p["name"]) for p in NOTES)
    evidence_map = table(
        ["路线", "代表论文", "已有证据", "当前尚未回答"],
        [
            ["可运行环境与可验证奖励", "VeriEnv", "网站和任务可用于策略训练", "agent 是否从交互证据学到了站点规律"],
            ["可执行程序与反例修订", "WorldCoder、GIF-MCTS、PoE、PatchWorld、Memento 3", "在结构化/游戏/文本环境中合成、规划与修补可行", "网页对象发现、部分观察与跨层依赖能否稳定学得"],
            ["网页神经预测与前瞻", "WMA、WebDreamer、WebEvolver、WebWorld", "在各自网页设置中改善动作选择或训练", "可检查的规则、辨识性探索与局部修复是否增加独立收益"],
            ["视觉渲染与研发流程", "Code2World、Agent2World", "图像后果模拟、生成与测试流程有用", "能否连接业务规律、界面读出和在线证伪"],
        ], "路线对照 · 跨论文作机制比较，不作分数排名", "matrix")
    coverage = table(
        ["项目", "本轮真正执行的上游部件", "预测实验范围"],
        [[link(f'#paper-{p["key"]}', p["name"]), esc(p["native"]), esc("Luna 派生条件；完整原法未运行" if p["method"] else ("仅组件检查；无预测成绩" if p["key"] == "code2world" else "无官方代码；无独立成绩"))] for p in NOTES],
        "代码覆盖 · 11 个项目有组件检查，10 篇论文对应本地派生预测条件", "matrix", raw=True)
    claims = table(
        ["问题", "本轮判断", "证据与可推到的范围"],
        [
            ["能否从少量转移生成可运行预测器？", "支持可行性", "7 个代码条件可回放；修正后一步均为 24/24。但只测固定动作与同模板新对象。"],
            ["一步满分是否足够支撑组合？", "否，已有反例", "当前方案一步 24/24，完整组合仅 6/12；业务记录 12/12，界面和反馈各 9/12。"],
            ["当前代码方案是否优于直接 Luna？", "没有证明", "相同初始证据：当前 15/24、6/12；直接 Luna 24/24、6/12。代码增加反馈后为 24/24、6/12。"],
            ["改变规则后能否修复且保留旧能力？", "有限支持", "当前 3/12 → 12/12，未变化子集保持 21/21；直接 Luna 也达到相同结果。"],
            ["是否已真正辨识所有变化规则？", "没有证明", "适应证据未覆盖 blocked 与缺原因同时出现的先后关系，12/12 含未观测条件的推断。"],
            ["是否知道哪个原论文算法最好？", "不能判断", "本轮是单次提示/表示适配，完整搜索、权重和多角色链未保留；预算也非等 token。"],
            ["主动发现控件、真实网页闭环、速度？", "尚未检验", "给定完整 JSON 和动作接口；没有自主对象发现、正式 UI 任务成功率或 UI/API 速度对照。"],
        ], "结论与证据等级", "claim-table")
    scores = row("current", "repaired", "rollout")
    component_bars = "".join(f'<div><b>{scores[k]}/{scores["n"]}</b><span>{label}</span><div class="mini-track" aria-hidden="true"><i style="width:{100*scores[k]/scores["n"]}%"></i></div></div>' for k, label in [("records_exact", "最终业务记录"), ("interface_exact", "最终界面状态"), ("feedback_exact", "最终操作反馈"), ("exact", "最终联合完整状态")])
    timing_rows = []
    for method in METHODS:
        if is_code(method):
            r = row(method, "repaired", "rollout")
            timing_rows.append([METHODS[method], f'{r["prediction_seconds"] * 1000:.3f} ms', f'{r["prediction_seconds"] / r["steps"] * 1e6:.1f} μs'])
    timing = table(["修正后代码条件", "45 步 predict 总时间", "平均每步"], timing_rows, "内存预测计时 · 不含学习、浏览器、网络与判定")
    chart = chart_payload()
    sources_list = "".join(f'<li id="ref-{esc(p["key"])}"><strong>{esc(p["name"])}.</strong> {link(CATALOG[p["catalog_id"]]["paper"], CATALOG[p["catalog_id"]]["title"], True)}（{esc(p["source_locator"])}）。{link(CATALOG[p["catalog_id"]]["repository"], "作者代码", True) if CATALOG[p["catalog_id"]].get("repository") else "未找到可核验官方仓库"}。</li>' for p in NOTES)
    document = TEMPLATE.replace("{{CSS}}", CSS).replace("{{JS}}", JS)
    tokens = {
        "EVIDENCE_MAP": evidence_map, "PAPER_INDEX": paper_index, "PAPER_CARDS": cards,
        "INITIAL_TABLE": initial_table, "REPAIRED_TABLE": repaired_table, "ADAPTED_TABLE": adapted_table,
        "COMPONENT_BARS": component_bars, "CLAIMS": claims, "COVERAGE": coverage,
        "TIMING": timing, "SOURCE_LIST": sources_list,
        "CHART_STATIC": chart_static(chart["initial-rollout"]),
        "CHART_DATA": json.dumps(chart, ensure_ascii=False).replace("<", "\\u003c"),
    }
    for key, value in tokens.items():
        document = document.replace("{{" + key + "}}", value)
    assert "{{" not in document, "Unresolved template token"
    OUTPUT.write_text(document, encoding="utf-8")
    inputs = ["papers/catalog.json", "papers/report_notes.json", "artifacts/results/summary.json", "artifacts/results/failure_examples.json", "artifacts/frozen_run.json", "artifacts/method_registry.json", "artifacts/upstream_audit.json", "SOURCE_MANIFEST.json", "scripts/build_research_report.py"]
    manifest = {
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "report": OUTPUT.name,
        "report_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "report_bytes": OUTPUT.stat().st_size,
        "frozen_experiment_utc": FROZEN["frozen_utc"],
        "verified_frozen_inputs_and_outputs": checked,
        "paper_count": len(NOTES), "scored_conditions": len(METHODS), "model_calls": 31,
        "new_model_calls_for_report": 0,
        "inputs": [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in inputs],
    }
    out = ROOT / "artifacts/report"
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(OUTPUT), "bytes": manifest["report_bytes"], "papers": 12, "conditions": 12, "frozen_files_verified": checked}, ensure_ascii=False))


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><meta name="description" content="12 篇网页与可执行世界模型论文、原始实验及本地 Luna issue 子域实验的证据报告。"><title>可执行网页世界模型：文献、实验与研究判断</title><style>{{CSS}}</style></head>
<body>
<a class="skip-link" href="#main">跳到报告正文</a>
<aside class="rail" aria-label="报告导航"><div><div class="rail-title">网页世界模型</div><div class="rail-subtitle">文献 × 实测 × 研究判断<br>VeriEnv · 本地 issue 子域</div></div>
<nav aria-label="章节目录">
<a href="#overview"><span>01</span> 结论与研究定位</a><a href="#papers"><span>02</span> 12 篇论文逐篇对照</a><a href="#experiment"><span>03</span> 固定实验与全部结果</a><a href="#failures"><span>04</span> 失败案例与已知结论</a><a href="#next"><span>05</span> 是否继续与如何整合</a><a href="#audit"><span>06</span> 代码、证据与复核</a>
</nav><button type="button" class="print-button js-only" data-print>打印 / 保存为 PDF</button><div class="rail-footer">证据截至 2026-10-20<br>正文与图表可离线阅读<br><a href="README.md">工作区说明</a> · <a href="artifacts/results/summary.csv">数值 CSV</a></div></aside>
<div class="layout"><main id="main" class="content">
<header class="hero"><div class="eyebrow">RESEARCH EVIDENCE REPORT · 2026.10</div><h1>从网页交互中学习<br>可执行、可修正的世界模型</h1><p class="lead">12 篇论文分别做到了哪里，我们的本地实验验证了什么，以及这条研究路线下一步还值得做什么。</p><div class="meta"><span>整理日期：2026-10-20</span><span>本地推理：gpt-6-luna / high 子代理</span><span>实验环境：自建 issue 管理微域</span><span>本轮无需 WebArena</span></div><div class="verdict"><strong>判断：值得继续，但需要收窄贡献点。</strong><p>优先研究“主动区分规则假设”和“业务状态—界面读出—反馈的一致性修复”。现有文献已证明让 LLM 生成环境代码可行；<strong>当前实验尚未证明我们的代码方案优于直接 Luna 预测。</strong></p></div></header>
<div class="stats" aria-label="本轮范围"><div class="stat"><b>12</b><span>定向调研论文；非穷尽综述</span></div><div class="stat"><b>11</b><span>有源码并执行组件检查的项目</span></div><div class="stat"><b>12</b><span>本地 Luna 派生预测条件</span></div><div class="stat"><b>31</b><span>实际模型回合；产物已冻结</span></div></div>

<section class="block" id="overview"><div class="section-head"><span class="section-num">01</span><h2>先区分研究对象，再判断已有进展</h2></div><p class="section-intro">原目标关注的是：agent 从交互证据认识网页对象与操作后果，把规律保存成可以预测、组合和持续修正的模型。<a href="chae26a.pdf">chae26a.pdf（VeriEnv）</a>主要提供重建网站与可验证任务，适合作为这项研究的环境与评价基础。两者相关，但主要产物不同。</p>
<div class="legend"><span><span class="evidence paper">论文报告</span> 作者原设置的结果</span><span><span class="evidence local">本地实测</span> 冻结 Luna 产物的评分</span><span><span class="evidence inference">综合判断</span> 从证据推出的研究建议</span></div>
{{EVIDENCE_MAP}}
<div class="grid-two"><div class="panel"><h3>已经建立的实验基础</h3><p>可重置的 issue 站点、统一 JSON 动作与观察、独立真值、原版 VeriEnv 判定 DSL、原始请求/产物哈希，以及 12 个条件的冻结回放。</p><p class="small">本轮实际学的是给定动作接口和完整观察后的行为规律。原目标中的自主控件发现和真实网页闭环尚未进入实验。</p></div><div class="panel"><h3>最关键的实测信号</h3><p>当前方案一次修正后：<strong>一步 24/24，完整组合 6/12</strong>。规则变化后：<strong>3/12 → 12/12</strong>，未变化案例保持 <strong>21/21</strong>。</p><p class="small">直接 Luna 初始即为一步 24/24、组合 6/12，适应后也为 12/12。两者目前没有表现出代码表征的确定优势。</p></div></div>
<div class="note"><strong>阅读口径：</strong>12 篇论文不等于 12 次原论文复现。本地 12 条件 = 10 篇论文的提示/表示派生条件 + 当前方案 + Luna Direct；Memento 3 无独立评分，Code2World 仅检查组件。论文的成功率、Token-F1、游戏得分和可执行率不横向排名。</div>
</section>

<section class="block" id="papers"><div class="section-head"><span class="section-num">02</span><h2>逐篇论文：方法、原实验与我们的测试</h2></div><p>每篇使用同一阅读顺序：做了什么 → 原论文实验 → 本地实际运行 → 对研究的意义。论文数值保留其模型、环境与计分单位；本地数值来自同一冻结结果表。</p><div class="paper-index" aria-label="论文索引">{{PAPER_INDEX}}</div>
<div class="toolbar js-only"><label for="paper-search">检索论文</label><input id="paper-search" type="search" placeholder="名称、方法或指标" autocomplete="off"><label for="paper-category">路线</label><select id="paper-category"><option value="all">全部路线</option><option value="infrastructure">环境与验证</option><option value="code">程序与规则书</option><option value="web">网页预测与训练</option><option value="adjacent">邻接方法</option></select><button id="expand-all" type="button">全部展开</button><button id="collapse-all" type="button">全部收起</button><span id="paper-count" class="count" role="status" aria-live="polite">12 / 12 篇</span></div>
<p id="paper-empty" class="empty" hidden>没有匹配的论文，请修改检索词或路线。</p>
{{PAPER_CARDS}}
</section>

<section class="block" id="experiment"><div class="section-head"><span class="section-num">03</span><h2>固定本地实验：测什么、怎么测、结果如何</h2></div>
<div class="panel"><h3>任务是预测操作后果，而非导航任务完成率</h3><p>自建本地 issue 网页有 6 条记录、8 类动作：筛选、排序、选择、全选、改标签、关闭、重开、评论。输入包含全部记录（包括被筛掉的记录）、当前筛选/排序/选择/角色/反馈/显示顺序。学习器预测动作后的完整 JSON 状态。</p><p>规则变化版本增加“关闭必须给原因”，并改变筛选后的选择保持逻辑；版本号不出现在观察中。评测者掌握独立环境真值，学习器只收到公开转移证据。这里没有真实 GitLab、WebArena 导航或视觉定位。</p><p class="small">完整协议与追加说明：<a href="EXPERIMENT_PROTOCOL.md">EXPERIMENT_PROTOCOL.md</a>。场景与预测器源码分开；读取隔离依赖子代理指令，未建立操作系统级学习器沙箱。</p></div>
<div class="timeline" aria-label="实验阶段"><div><b>36</b><strong>初始学习转移</strong><p>种子 11 / 23 / 37；所有条件相同初始证据。</p></div><div><b>16</b><strong>开发案例</strong><p>种子 41 / 43；代码最多收到 8 条失败反例，修正一次。</p></div><div><b>24 + 12</b><strong>一步与组合</strong><p>种子 101 / 103 / 107；12 条未演示序列，共 45 步。</p></div><div><b>12</b><strong>规则变化测试</strong><p>种子 211 / 223 / 227；先用旧模型预测变化后环境。</p></div><div><b>6</b><strong>新规则适应证据</strong><p>种子 71 / 73；更新后重新测变化，另看 21 条未变化案例。</p></div></div>
<div class="grid-two"><div class="panel"><h3>统一评分与开放环</h3><p>所有预测先提交保存，冻结输入/输出哈希后评分。每一步接收上一步预测，不注入真实中间状态。完整轨迹要求全部步骤完全匹配；本轮它与最终完整状态正确数恰好相等。</p><p class="small">规范化只把 issue 记录、标签和选中 ID 视为集合；保留评论与 visible_ids 顺序、大小写、空白和 JSON 类型。原版 VeriEnv DSL 比较状态指纹；“结构合法”只检查公开字段与类型，不是业务正确率。</p></div><div class="panel"><h3>预算与泛化边界</h3><p>7 个代码条件各 3 回合（初稿、开发修正、适应）；5 个直接条件各 2 回合（初始、适应）。直接预测按 48 / 36 条案例批量提交，没有获得开发反例。</p><p class="small">同初始证据不等于同 token、同调用数或同计算量。每个条件只生成一份产物、测试 3 个对象种子；开发与一步测试共享操作模板。未做显著性检验，也未证明未见任务族泛化。</p></div></div>

<div class="panel"><div class="chart-controls"><h3 id="chart-title">初稿 · 开放环完整轨迹</h3><div class="js-only"><label for="chart-choice">切换指标　</label><select id="chart-choice"><option value="initial-rollout">初稿 · 完整组合</option><option value="initial-one">初稿 · 一步预测</option><option value="repaired-rollout">开发修正 · 完整组合</option><option value="repaired-one">开发修正 · 一步预测</option><option value="adapted-drift">六条新证据 · 变化恢复</option></select></div></div><div class="legend"><span class="chart-key"><i class="swatch" aria-hidden="true"></i>代码派生条件</span><span class="chart-key"><i class="swatch direct" aria-hidden="true"></i>直接预测派生条件</span><span>仅描述本次产物；保持协议顺序，不作算法排名</span></div><div class="chart-axis" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div><div id="comparison-chart" aria-label="本地实验预测正确数">{{CHART_STATIC}}</div><p id="chart-note" class="small">12 个条件共享 36 条初始证据；12 条轨迹共 45 步。每条全部步骤正确才计入。</p></div>

<div class="phase-title"><span>A</span><h3>相同初始证据下的 12 条件</h3></div><p class="small">初始总计 48 条 = 一步 24 + 组合 12 + 变化 12。结构非法、字段遗漏和不正确的预测全部留在分母中。</p>{{INITIAL_TABLE}}
<p class="small">WorldCoder 初稿额外返回 <code>issue_updates</code>，结构合法只有 24/48；WebDreamer 的 6 条组合有非字符串评论列表，结构合法 42/48。它们是本次 Luna 产物与接口适配失败，不能等同原论文模型失败。</p>
<div class="phase-title"><span>B</span><h3>只对代码条件做一次开发修正</h3></div><p>七个代码条件的一步成绩全部达到 24/24，组合成绩仍分化。一次单步反例修正没有自动消除跨动作依赖。</p>{{REPAIRED_TABLE}}
<div class="note">这张表的代码已经额外看过开发反例。直接条件未获得相同反馈，因此不能用它与表 A 的直接预测成绩宣称公平胜出。</div>
<div class="phase-title"><span>C</span><h3>规则变化、六条证据后的恢复与保留</h3></div><p>“适应前”代码使用修正版本，直接条件使用初始预测。保留能力只测语义未变化的 21 条旧案例；旧版筛选或关闭规则与新规则冲突的样本不算遗忘。</p>{{ADAPTED_TABLE}}
<p class="small">WorldCoder / Agent2World 派生条件的 3 条失败来自“缺关闭原因”与 blocked 同时出现时的校验优先级；六条证据未展示该组合。适应后旧版本 rollout 的原始分数仍保存在 JSON，但不作为新版本组合能力评价。</p>
<div class="panel" id="current"><h3>当前方案实际是什么</h3><p>本轮“当前方案”是 Luna 写出的规则注释/模块说明与 Python 预测器，经历一次开发修正、一次新规则适应。尚未实现独立假设集合、主动辨识动作、规则书/代码分诊，以及由 DOM 自主发现控件。</p><p><strong>当前方案：一步 15/24 → 24/24，组合 6/12 → 6/12。</strong>同初始证据的 Luna Direct 为一步 24/24、组合 6/12。现有数据支持继续分析具体失败，不能把它写成已经验证的算法优势。</p></div>
</section>

<section class="block" id="failures"><div class="section-head"><span class="section-num">04</span><h2>失败案例揭示了什么</h2></div><p>最有研究价值的信号是：程序可能正确更新业务记录，却没有正确传播到界面与反馈。以下四项均为当前方案修正后，在同 12 条组合的<strong>最终状态</strong>上分别判定；它们不是互斥类别。</p><div class="bar-summary">{{COMPONENT_BARS}}</div>
<div class="grid-two"><div class="panel"><h3>案例一：关闭之后，列表没有变</h3><div class="case-flow"><span>筛选 open</span><em>→</em><span>选择 issue</span><em>→</em><span>关闭</span></div><p>预测中的 issue 状态已正确变成 closed，但 <code>visible_ids</code> 仍保留关闭前的筛选列表。</p><div class="outcome"><strong>定位：</strong>业务转移正确，界面读出没有按新状态重算。仅检查数据库字段会漏报这个错误。</div></div><div class="panel"><h3>案例二：成功动作保留旧错误</h3><div class="case-flow"><span>关闭被 blocked 拒绝</span><em>→</em><span>成功添加标签</span></div><p>标签更新正确，反馈却仍为上一操作的 <code>blocked</code>。直接 Luna 的部分轨迹也有反馈未复位问题。</p><div class="outcome"><strong>定位：</strong>反馈取决于最近一次动作；它不能作为无条件保留的状态字段。</div></div></div>
<div class="panel"><h3>案例三：没有证据的优先级，模型只能猜</h3><p>新版本中，“没有关闭原因”应先于 blocked 检查。六条适应证据分别展示相关规则，却没有展示两个条件同时成立。WorldCoder 和 Agent2World 派生条件选择了另一顺序，得分为 9/12；其他条件多为 12/12。</p><p><strong>研究问题：</strong>在证据不足时能否保留两种假设，并主动执行一次“两条件同时成立”的关闭操作来区分？这比继续修一份已经猜定的代码更接近可检验的规律发现。</p><p class="small">案例来自 <a href="artifacts/results/failure_examples.json">逐例失败记录</a>，不是新补测。下一轮必须使用新的封存测试，不把本轮答案用于修复后再报告首次泛化。</p></div>
{{CLAIMS}}
<div class="panel"><h3>从所有论文与本轮实验共同得到的认识</h3><p><strong>程序化、前瞻、可修正性都有已有工作支撑，但没有一种表示天然保证准确。</strong>GIF-MCTS 的程序搜索、PoE 的模块组合、PatchWorld 的执行验证、Memento 的规则/实现分诊各自处理不同环节；网页预测论文则展示了前瞻与合成训练的用途。</p><p><strong>现在的缺口是把证据获取、假设辨识和跨层验证连接起来。</strong>本轮的全观察、固定动作微域已经暴露界面读出与条件优先级问题；真实网页还会增加状态抽象、隐藏信息和异步过程。将这些缺口作为研究假设，比把已有组件拼接后直接宣称新世界模型更有说服力。</p></div>
</section>

<section class="block" id="next"><div class="section-head"><span class="section-num">05</span><h2>是否值得继续，以及如何与 VeriEnv 整合</h2></div><div class="verdict"><strong>有条件继续：把目标定为“有限交互下，可证伪且可修复的网页行为模型”。</strong><p>“让 LLM 写一个网页模拟器”已经缺少独立新意。仍值得验证的增量是：更少交互辨识规则、修复业务与读出依赖、以及明确区分假设错误和实现错误。下面是下一轮方案，不是已完成结果。</p></div>
<h3 style="margin-top:26px">建议的整合结构</h3><div class="flow" aria-label="已接通与待实现模块"><div><span class="evidence local">已接通</span><strong>1 · VeriEnv 环境与真值</strong><p>本地站点、重置、HTTP/SDK、私有任务与原 judge DSL；独立保存真实转移。</p></div><div><span class="evidence local">已有基础</span><strong>2 · 代码预测与回放验证</strong><p>统一 predict 接口、冻结产物、严格状态比较；PatchWorld 原生验证钩子。</p></div><div class="planned"><span class="evidence inference">待实现</span><strong>3 · 假设—交互—修复闭环</strong><p>保留未决规则，选最小区分操作，诊断规则/实现/状态估计，再验证补丁。</p></div></div><p class="small">建议的信息流：页面证据 → 假设与预测 → 提交后执行 → 独立差异检查 → 定位与修订 → 回归验证。评测真值始终由环境层持有；不向学习器暴露测试答案。</p>

<div class="priority"><div class="rank">1</div><div><h3>先验证业务转移与界面读出的组合一致性</h3><p>对照单一转移函数、独立读出函数、显式依赖关系与局部重算。保留筛选/排序/批量修改/失败恢复等从未演示的组合模板，分别计业务、界面、反馈与联合正确率。</p><p class="test"><strong>通过条件：</strong>在相同证据与修复预算下，未见组合稳定改善且不损害业务预测。若优势仅来自多给反例，或等预算文本记忆达到相同结果，就不能归因于程序结构。</p></div></div>
<div class="priority"><div class="rank">2</div><div><h3>允许主动选择能区分假设的交互</h3><p>比较随机探索、LLM 不确定性探索、模型分歧驱动的区分试验。受控改变校验优先级、批量原子性、选择保持与评论幂等性，划分未见规则组合。</p><p class="test"><strong>通过条件：</strong>固定查询数下识别更多真规则，或用更少真实交互恢复准确预测；同时检查“不知道”的校准。猜中一次、补丁命中一组案例不构成主动辨识证据。</p></div></div>
<div class="priority"><div class="rank">3</div><div><h3>公平检验代码、文本规则书和二者结合</h3><p>至少四组：直接预测＋历史、文本规则书、可执行代码、规则书＋代码。全部得到相同新增证据和开发反馈；分别记录规则修订与代码修补。建议至少 5 次独立生成、20 个对象种子，按任务族/版本组合统计。</p><p class="test"><strong>通过条件：</strong>改善在多个生成重复和新规则组合上仍存在，且计入调用、token 与维护成本。若等预算直接预测消除优势，调整机制主张。具体规模与阈值在下一轮运行前冻结。</p></div></div>
<div class="priority"><div class="rank">4</div><div><h3>接回完整上游机制，再扩展到真实页面观察</h3><p>优先接 PatchWorld 原诱导/反例选择与 WorldCoder 原约束；GIF 要真正运行树搜索，PoE 要拟合专家组合，Agent2World 要保留研发与测试链。随后隐藏业务 SDK，统一给予 DOM/无障碍树和浏览器动作，增加分页、详情页与延迟保存。</p><p class="test"><strong>通过条件：</strong>先完成浏览器端到端验收，再分别测控件发现覆盖、预测、闭环任务和维护。WMA/WebEvolver/WebWorld 的专用权重实验单列；Code2World 另设视觉渲染评价。</p></div></div>
<div class="note"><strong>什么时候应该缩小或停止这条主张？</strong>若等证据、等反馈、预算受控后，代码/规则书没有稳定收益；主动试验无法更有效区分规则；或只在固定 JSON 接口成立、迁移到页面即失效，就不应继续主张“更通用的网页理解”。可转为范围更清楚的测试生成、行为回归或页面读出一致性工具。</div>
<p>速度实验应单独开展：通用浏览器 agent、模型辅助 agent、手写 UI 脚本、SDK/API 在相同初态与业务终点比较，计入等待、验证、重试、学习和维护成本。当前微秒级代码推演只能说明内存函数便宜，不能换算成网页端到端加速倍数。</p>
</section>

<section class="block" id="audit"><div class="section-head"><span class="section-num">06</span><h2>源码、实际集成与可追溯证据</h2></div><p>在用户已有 VeriEnv 源码包之外，另下载 10 个主仓库与 2 个子模块，共 1,877 个源码/文本文件、12 个 ZIP；逐文件验证 Git blob SHA-1，固定 commit。权重、ROM、媒体与部分大数据文件不包含在源码包中，因此它们不是可直接复现论文的完整运行镜像。</p>{{COVERAGE}}
<div class="grid-two"><div class="panel"><h3>已完成的核验</h3><p>16 项领域/SDK/评分测试通过；31 个冻结模型产物均完成评分，无进程加载失败或超时；两次重放的业务分数一致。报告构建再次校验 31 份请求和 31 份产物的哈希，不重新调用模型。</p><p class="small">PatchWorld 首次回放曾因 UTF-8 BOM 加载失败；只修复适配器解码，模型字节未变。首轮失败与修复后的记录均保留。</p></div><div class="panel"><h3>仍需保留的限制</h3><p>原实验阶段浏览器验收未完成（连接超时及备用工具自动审批拒绝）；已验证 HTTP/SDK。此处的本地成绩来自结构化状态回放，而非完整浏览器任务运行。</p><p class="small">没有可核验 token/费用账单。请求导出到产物生成的时间含调度等待，不能视为纯模型延迟。AST 白名单和子代理读取指令也不构成操作系统安全沙箱。</p></div></div>
<details class="panel"><summary>查看代码预测耗时及其计量范围</summary>{{TIMING}}<p class="small">只有内存 Python predict 调用，包含模型内部复制；不含浏览器、网络、学习、修正和判定。直接预测产物的离线应用耗时不代表 LLM 推理时间，故不放入速度对照。</p></details>
<h3 style="margin-top:28px">复查入口</h3><div class="archive-grid"><a href="artifacts/results/summary.csv">全部数值 CSV<small>由冻结回放产生；包含各阶段与字段</small></a><a href="artifacts/results/summary.json">机器可读汇总<small>本报告的本地表格与图表直接读取此文件</small></a><a href="artifacts/results/failure_examples.json">失败案例<small>实际/预测状态与首次失败位置</small></a><a href="artifacts/frozen_run.json">31 回合冻结清单<small>模型、输入输出、字节数、哈希与调度时间</small></a><a href="SOURCE_MANIFEST.json">源码来源与固定版本<small>commit、文件哈希、下载状态与排除项</small></a><a href="artifacts/upstream_audit.json">原生组件审计<small>实际执行、替代接口和输入输出</small></a><a href="UPSTREAM_INTEGRATION.md">集成边界说明<small>11 个项目逐项说明</small></a><a href="papers/catalog.json">结构化文献目录<small>原文、作者代码、指标与限制</small></a><a href="artifacts/report/build_manifest.json">报告构建清单<small>输入哈希；本次整理没有新增模型调用</small></a></div>
<div class="panel"><h3>复现与重建命令</h3><p class="small">在此工作区运行，Python 3.11+。评分重放使用保存的代码与直接预测，无需模型凭据；重建报告只读实验文件。</p><pre class="codeblock">python scripts/build_research_report.py
python -m pytest tests -q
python -m issue_lab.upstream_audit
python -m issue_lab.replay replay
python -m issue_lab.report</pre><p class="small">不要重新生成数据后混用旧哈希；新的 LLM 调用须作为独立实验记录。相关说明：<a href="README.md">README</a>、<a href="EXPERIMENT_RESULTS.md">实测报告</a>、<a href="NEXT_RESEARCH.md">后续研究</a>、<a href="integrations/verienv/README.md">VeriEnv 接入</a>。</p></div>
<h3>论文原文索引</h3><p class="small">本轮是围绕网页预测、可执行动力学与反例修复的定向调研；以论文原文、作者项目和仓库为证据。下列数值是代表性实验摘述，并未覆盖每篇所有附录与消融。</p><ol class="source-list">{{SOURCE_LIST}}</ol>
</section>
<footer><p>证据截至 2026-10-20 · 本报告与样式、交互数据均在单个 HTML 中，可离线阅读。论文链接需联网，原始数据与源码链接需保留工作区相对目录。</p><p>原实验的冻结数据、模型和成绩未因本次报告整理而修改；文献解释与下一步建议属于研究判断。阅读参考：<a href="../%E7%A0%94%E7%A9%B6%E7%9B%AE%E6%A0%87.md">原研究目标</a>。</p></footer>
</main></div>
<script id="chart-data" type="application/json">{{CHART_DATA}}</script><script>{{JS}}</script>
</body></html>'''


if __name__ == "__main__":
    main()
