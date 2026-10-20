"""Real-browser gate wiring test with a clearly labeled synthetic reviewer."""
import argparse
import json
import os
from pathlib import Path
import threading
import time

from .artifacts import digest
from .playwright_run import Recorder, ScriptHarness, write_json
from .supervision import GateStopped


def fixture_response(folder, failures):
    """No model call: only a transport fixture for this generic smoke test."""
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            paths = list(folder.glob("interventions/*/request.json"))
            if paths:
                request_path = paths[0]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                response = {
                    "request_id": request["request_id"], "request_sha256": digest(request_path),
                    "reviewer": "gpt-6.1-sol", "decision": "continue",
                    "classification": "planned_review",
                    "reason": "SYNTHETIC TEST FIXTURE ONLY: no Solar model was invoked.",
                    "evidence": ["request.json", "ui.dom.json", "ui.png"],
                }
                temporary = request_path.parent / "fixture.tmp"
                write_json(temporary, response)
                temporary.replace(request_path.parent / "decision.json")
                return
            time.sleep(0.05)
        raise TimeoutError("Smoke fixture never received review request")
    except Exception as exc:
        failures.append(str(exc))


def run(out):
    from playwright.sync_api import expect, sync_playwright

    out.mkdir(parents=True, exist_ok=False)
    outcomes = []
    with sync_playwright() as playwright:
        options = {"headless": True, "chromium_sandbox": True}
        if os.environ.get("HARNESS_CHROME"):
            options["executable_path"] = os.environ["HARNESS_CHROME"]
        else:
            options["channel"] = "chrome"
        browser = playwright.chromium.launch(**options)
        try:
            for permitted in (False, True):
                folder = out / ("permit" if permitted else "deny")
                folder.mkdir()
                context = browser.new_context()
                recorder = Recorder(folder / "events.jsonl")
                failures = []
                thread = None
                try:
                    context.tracing.start(screenshots=False, snapshots=True)
                    page = context.new_page()
                    page.set_content('<button id="change" onclick="document.querySelector(\'#value\').textContent=1">Commit</button><p id="value">0</p>')

                    class Adapter:
                        @staticmethod
                        def observe():
                            return {"value": int(page.locator("#value").inner_text())}

                        @staticmethod
                        def checkpoint(case, checkpoint_id, initial, current, history):
                            return {"decision": "continue" if permitted else "stop",
                                    "checks": [{"id": "fixture_permission", "passed": permitted}],
                                    "public_summary": "Synthetic fixture permission."}

                    case = {
                        "id": "generic_gate_fixture", "goal": "Validate gate wiring", "parameters": {},
                        "checkpoints": [{"id": "pre_commit", "before_step": "commit", "reason": "Fixture"}],
                        "steps": [{"id": "commit", "rule_ids": ["fixture"], "action": "Click the fixture",
                                   "expect": [{"id": "success", "checks": [
                                       {"path": "after.backend.value", "op": "eq", "value": 1}]}]}],
                    }
                    plan = {"schema_version": 3, "cases": [case], "readouts": {}, "supervision": {
                        "review_timeout_seconds": 30, "case_seconds": 60, "max_reviews_per_case": 2,
                        "on_step_failure": "diagnose_and_stop",
                    }}
                    monitor = ScriptHarness(page, case, plan, Adapter(), folder, recorder, [], "about:blank")
                    thread = threading.Thread(target=fixture_response, args=(folder, failures), daemon=True)
                    thread.start()
                    if permitted:
                        monitor.checkpoint("pre_commit")
                        with monitor.step("commit"):
                            monitor.confirm(page.get_by_role("button", name="Commit")).click()
                            expect(page.locator("#value")).to_have_text("1")
                        assert monitor.supervisor.all_consumed()
                        assert monitor.results[0]["status"] == "matched"
                    else:
                        try:
                            monitor.checkpoint("pre_commit")
                            raise AssertionError("Independent refusal was ignored")
                        except GateStopped:
                            pass
                        try:
                            with monitor.step("commit"):
                                raise AssertionError("Denied action dispatched")
                        except GateStopped:
                            pass
                        assert page.locator("#value").inner_text() == "0"
                        assert not monitor.results
                    thread.join(timeout=5)
                    assert not thread.is_alive() and not failures, failures
                    context.tracing.stop(path=str(folder / "trace.zip"))
                    outcomes.append({"independent_permission": permitted, "passed": True,
                                     "value": page.locator("#value").inner_text(),
                                     "actions_dispatched": len(monitor.results)})
                finally:
                    recorder.close()
                    context.close()
            report = {"scope": "Generic real-browser gate wiring; synthetic review file, no LLM call or website task.",
                      "browser_version": browser.version, "checks": outcomes,
                      "passed": all(item["passed"] for item in outcomes)}
            write_json(out / "result.json", report)
            return report
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.out), ensure_ascii=False))
