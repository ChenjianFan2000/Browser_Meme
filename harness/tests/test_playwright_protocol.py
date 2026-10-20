"""Protocol tests: ordering, evidence, redaction and fixed denominators."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from harness.artifacts import Recorder
from harness.playwright_run import ScriptContext, ScriptHarness, StepMismatch, all_steps_matched, invoke_script, redact, remember_request, sanitize_trace, validate_inputs


class Adapter:
    def __init__(self):
        self.value = 0

    def observe(self):
        return {"value": self.value}

    def observe_ui(self, page):
        return {"independent": True}


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)
        self.recorder = Recorder(self.out / "events.jsonl")
        self.adapter = Adapter()
        self.step = {"id": "create", "action": "native fixture operation", "rule_ids": ["R1"],
                     "expect": [{"id": "success", "checks": [
                         {"path": "after.backend.value", "op": "eq", "value": 1}]}]}
        self.case = {"id": "C1", "goal": "fixture", "parameters": {}, "steps": [self.step]}
        self.plan = {"schema_version": 2, "model": "gpt-6.1-sol", "revision": "fixture",
                     "cases": [self.case], "readouts": {}}

    def tearDown(self):
        self.recorder.close()
        self.temp.cleanup()

    def fixture(self):
        return ScriptHarness(None, self.case, self.plan, self.adapter, self.out,
                             self.recorder, [], "http://127.0.0.1")

    @patch("harness.playwright_run.observed_ui", return_value={"url": "about:blank", "text": "", "fields": {}})
    @patch.object(ScriptHarness, "_capture")
    def test_prediction_durable_before_action_independent_history(self, *_):
        harness = self.fixture()
        with harness.step("create"):
            events = [json.loads(line) for line in (self.out / "events.jsonl").read_text().splitlines()]
            self.assertEqual([e["kind"] for e in events[-2:]], ["prediction", "action_dispatch"])
            self.assertEqual(events[-2]["before"]["backend"]["value"], 0)
            self.adapter.value = 1
        self.assertEqual(harness.results[0]["status"], "matched")
        self.assertEqual(harness.history[0]["after"]["backend"]["value"], 1)
        self.assertTrue(harness.history[0]["after"]["independent_ui"]["independent"])
        self.assertNotIn("expect", harness.history[0])
        self.assertNotIn("backend", harness.read_ui())

    @patch("harness.playwright_run.observed_ui", return_value={"url": "about:blank", "text": "", "fields": {}})
    @patch.object(ScriptHarness, "_capture")
    def test_contradiction_stops_and_retains_actual_state(self, *_):
        harness = self.fixture()
        with self.assertRaises(StepMismatch):
            with harness.step("create"):
                self.adapter.value = 2
        self.assertEqual(harness.results[0]["status"], "contradiction")
        evidence = json.loads((self.out / "01.json").read_text())
        self.assertEqual(evidence["after"]["backend"]["value"], 2)

    @patch("harness.playwright_run.observed_ui", return_value={"url": "about:blank", "text": "", "fields": {}})
    @patch.object(ScriptHarness, "_capture")
    def test_action_exception_cannot_turn_into_success(self, *_):
        harness = self.fixture()
        with self.assertRaisesRegex(RuntimeError, "lost response"):
            with harness.step("create"):
                self.adapter.value = 1
                raise RuntimeError("lost response")
        self.assertEqual(harness.results[0]["status"], "error")
        self.assertEqual(harness.results[0]["prediction_after_error"]["status"], "matched")
        self.assertFalse(all_steps_matched(self.case, harness.results))

    @patch("harness.playwright_run.observed_ui", return_value={"url": "about:blank", "text": "", "fields": {}})
    @patch.object(ScriptHarness, "_capture")
    def test_catching_failed_step_cannot_activate(self, *_):
        harness = self.fixture()
        try:
            with harness.step("create"):
                self.adapter.value = 2
        except StepMismatch:
            pass
        self.assertEqual(harness._next, len(self.case["steps"]))
        self.assertFalse(all_steps_matched(self.case, harness.results))
        public = ScriptContext(harness)
        for name in ("initial", "current", "history", "_adapter"):
            self.assertFalse(hasattr(public, name))

    @patch("harness.playwright_run.observed_ui", return_value={"url": "about:blank", "text": "", "fields": {}})
    @patch.object(ScriptHarness, "_capture")
    def test_script_gets_detached_public_plan(self, *_):
        harness = self.fixture()
        class Script:
            @staticmethod
            def run(case, h):
                self.assertEqual(case["steps"][0]["id"], "create")
                self.assertFalse(hasattr(h, "_adapter"))
                case["steps"].clear()
        invoke_script(Script, self.case, harness)
        self.assertEqual(len(self.case["steps"]), 1)

    def test_case_mutation_rejected(self):
        site = {"site_id": "fixture", "base_url": "http://127.0.0.1",
                "allowed_hosts": ["127.0.0.1"], "adapter": "adapter.py", "source_roots": ["source"]}
        rules = [{"id": "R1", "statement": "fixture", "source_refs": ["fixture.py:1"],
                  "preconditions": [], "branches": [], "forbidden_side_effects": [], "status": "source_supported"}]
        cases = [{k: self.case[k] for k in ("id", "goal", "parameters")}]
        self.assertEqual(validate_inputs(site, cases, rules, self.plan)["steps"], 1)
        modified = copy.deepcopy(self.plan)
        modified["cases"][0]["goal"] = "changed"
        with self.assertRaisesRegex(ValueError, "fixed cases changed"):
            validate_inputs(site, cases, rules, modified)

    def test_trace_and_nested_body_redaction(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcd1234"
        data = {"headers": [{"name": "Authorization", "value": "Bearer secret"}],
                "cookies": [{"name": "session", "value": jwt}],
                "body": json.dumps({"access_token": jwt, "password": "secret"}),
                "status": 200}
        raw, target = self.out / "raw.zip", self.out / "clean.zip"
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("trace.network", json.dumps(data) + "\n")
            archive.writestr("resources/body.json", json.dumps({"access_token": jwt}))
        sanitize_trace(raw, target)
        with zipfile.ZipFile(target) as archive:
            contents = "\n".join(archive.read(name).decode() for name in archive.namelist())
        self.assertNotIn("secret", contents)
        self.assertNotIn(jwt, contents)
        self.assertEqual(redact(data)["status"], 200)
        self.assertNotIn("private-value", str(redact({"cookies": [{"name": "session", "value": "private-value"}]})))
        self.assertNotIn("private-value", redact('<input type="password" value="private-value">'))
        self.assertNotIn("private-value", redact('http://localhost/?token=private-value&item=1'))

    def test_observed_password_removed_from_unlabelled_trace_value(self):
        class Request:
            post_data_json = {"username": "fixture", "password": "secret-unlabelled-field"}
        remember_request(Request())
        trace = {"method": "fill", "params": {"selector": "#field2", "value": "secret-unlabelled-field"}}
        self.assertNotIn("secret-unlabelled-field", json.dumps(redact(trace)))


if __name__ == "__main__":
    unittest.main()
