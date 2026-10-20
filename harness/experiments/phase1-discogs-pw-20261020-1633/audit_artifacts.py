"""Audit exported evidence structure and links, without website semantics."""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from aggregate_runs import ROOT, RUNS, read


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in ("href", "src") and value)


def audit():
    issues = []
    token_findings = []
    counts = {"runs": 0, "cases": 0, "dispatched_steps": 0, "traces": 0,
              "text_entries_scanned": 0, "local_links": 0}
    jwt_pattern = re.compile(rb"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

    def scan(data, label):
        counts["text_entries_scanned"] += 1
        if jwt_pattern.search(data):
            token_findings.append(label)

    for run_id in RUNS:
        folder = ROOT / run_id
        summary = read(folder / "summary.json")
        counts["runs"] += 1
        if len(summary["cases"]) != summary["metrics"]["case_denominator"]:
            issues.append(f"{run_id}: case denominator mismatch")
        if sum(len(c["steps"]) for c in summary["cases"]) != summary["metrics"]["step_denominator"]:
            issues.append(f"{run_id}: step denominator mismatch")
        for number, case in enumerate(summary["cases"], 1):
            counts["cases"] += 1
            case_dir = folder / "cases" / f"{number:02d}-{case['id']}"
            events_path = case_dir / "events.jsonl"
            if not events_path.exists():
                issues.append(f"{run_id}/{case['id']}: event log missing")
                continue
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            predicted = set()
            for event in events:
                if event["kind"] == "prediction":
                    predicted.add(event["step"])
                elif event["kind"] == "action_dispatch":
                    counts["dispatched_steps"] += 1
                    if event["step"] not in predicted:
                        issues.append(f"{run_id}/{case['id']}: dispatch before prediction")
            if case["passed"] and (
                not case.get("independent_checks")
                or any(check["passed"] is not True for check in case["independent_checks"])
                or any(step["status"] != "matched" for step in case["steps"])
            ):
                issues.append(f"{run_id}/{case['id']}: unsupported success")
            for step in case["steps"]:
                for key in ("evidence", "screenshot"):
                    if step.get(key) and not (case_dir / step[key]).is_file():
                        issues.append(f"{run_id}/{case['id']}/{step['id']}: missing {key}")
            for path in case_dir.glob("*.json*"):
                scan(path.read_bytes(), str(path.relative_to(ROOT)))
            if case.get("trace"):
                trace_path = case_dir / case["trace"]
                with ZipFile(trace_path) as trace:
                    counts["traces"] += 1
                    if trace.testzip() is not None:
                        issues.append(f"{run_id}/{case['id']}: corrupt trace member")
                    for item in trace.infolist():
                        payload = trace.read(item)
                        if b"\x00" not in payload[:1000]:
                            scan(payload, f"{trace_path.relative_to(ROOT)}::{item.filename}")
        for html_path in folder.glob("*.html"):
            parser = Links()
            parser.feed(html_path.read_text(encoding="utf-8"))
            for url in parser.links:
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                counts["local_links"] += 1
                target = html_path.parent / unquote(parsed.path)
                if not target.is_file():
                    issues.append(f"{html_path.relative_to(ROOT)}: missing link {url}")
    return {
        "scope": "Exported run evidence, fixed denominators, prediction-before-dispatch, success support, ZIP integrity and relative HTML links.",
        "security_scope": "JWT-shaped value scan of case JSON/JSONL and textual trace members; not a universal secret detector. Findings contain paths only.",
        "counts": counts,
        "issues": issues,
        "jwt_pattern_finding_paths": token_findings,
        "passed": not issues and not token_findings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit()
    with args.out.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
