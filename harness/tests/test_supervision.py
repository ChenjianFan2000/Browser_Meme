"""Exercise fail-closed gates independently of any website answers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from harness.artifacts import Recorder, digest, write_json
from harness.supervision import GateStopped, Supervisor, evaluate_gate, validate_decision, validate_supervision


class FakePage:
    def __init__(self, fixture):
        self.fixture = fixture
        self.answer = "continue"
        self.mutate_on_review = False

    def wait_for_timeout(self, milliseconds):
        for request_path in self.fixture._out.glob("interventions/*/request.json"):
            decision_path = request_path.parent / "decision.json"
            if decision_path.exists():
                continue
            request = json.loads(request_path.read_text(encoding="utf-8"))
            if self.mutate_on_review:
                self.fixture.state["backend"]["value"] += 1
            write_json(decision_path, {
                "request_id": request["request_id"], "request_sha256": digest(request_path),
                "reviewer": "gpt-6.1-sol", "decision": self.answer,
                "classification": "planned_review", "reason": "Unit-test fixture response; not a model call.",
                "evidence": ["request.json", "ui.dom.json", "ui.png"],
            })


class Fixture:
    def __init__(self, directory):
        self._out = directory
        self._recorder = Recorder(directory / "events.jsonl")
        self.state = {"ui": {"url": "http://localhost", "text": "Ready", "fields": {}},
                      "backend": {"value": 0, "private_marker": "oracle-only"}}
        self.case = {"id": "fixture", "goal": "fixture", "parameters": {}}
        self._case_plan = {**self.case, "steps": [{"id": "commit"}],
                           "checkpoints": [{"id": "gate", "before_step": "commit", "reason": "fixture"}]}
        self._plan = {"schema_version": 3, "supervision": {
            "review_timeout_seconds": 1, "max_reviews_per_case": 2,
            "case_seconds": 10, "on_step_failure": "diagnose_and_stop",
        }, "cases": [self._case_plan]}
        self._next = 0
        self._active = None
        self.results = []
        self.history = []
        self.initial = copy.deepcopy(self.state)
        self._adapter = self
        self.verdict = "continue"
        self.check_passed = True
        self.page = FakePage(self)

    def _observe(self):
        return copy.deepcopy(self.state)

    def _capture(self, name):
        write_json(self._out / f"{name}.dom.json", [{"html": "<p>Ready</p>"}])
        (self._out / f"{name}.png").write_bytes(b"fixture-image")

    def checkpoint(self, case, checkpoint_id, initial, current, history):
        return {"decision": self.verdict,
                "checks": [{"id": "fixture", "passed": self.check_passed, "detail": "oracle-only"}],
                "public_summary": "Fixture gate."}


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.tmp.name))
        self.supervisor = Supervisor(self.fixture, write_json)

    def tearDown(self):
        self.fixture._recorder.close()
        self.tmp.cleanup()

    def test_live_gate_then_single_consumption_and_public_projection(self):
        self.assertEqual(self.supervisor.checkpoint("gate")["decision"], "continue")
        packet = json.loads(next(Path(self.tmp.name).glob("interventions/*/request.json")).read_text())
        self.assertNotIn("oracle-only", json.dumps(packet))
        self.assertFalse(list(Path(self.tmp.name).glob("interventions/*/private*.json")))
        self.assertEqual(len(list(Path(self.tmp.name).glob("private-supervision/*/evaluation.json"))), 1)
        self.assertEqual(set(packet["public_evidence_sha256"]), {"ui.dom.json", "ui.png"})
        self.supervisor.before_dispatch("commit", self.fixture._observe())
        self.assertTrue(self.supervisor.all_consumed())
        with self.assertRaises(GateStopped):
            self.supervisor.before_dispatch("commit", self.fixture._observe())

    def test_solar_cannot_override_independent_refusal_or_unknown(self):
        for decision, passed in (("stop", False), ("unknown", None), ("continue", None)):
            with self.subTest(decision=decision, passed=passed):
                with tempfile.TemporaryDirectory() as folder:
                    fixture = Fixture(Path(folder))
                    fixture.verdict, fixture.check_passed = decision, passed
                    try:
                        supervisor = Supervisor(fixture, write_json)
                        with self.assertRaises(GateStopped):
                            supervisor.checkpoint("gate")
                        self.assertFalse(supervisor.all_consumed())
                    finally:
                        fixture._recorder.close()

    def test_denied_solar_review_cannot_dispatch(self):
        self.fixture.page.answer = "stop"
        with self.assertRaises(GateStopped):
            self.supervisor.checkpoint("gate")
        with self.assertRaises(GateStopped):
            self.supervisor.before_dispatch("commit", self.fixture._observe())

    def test_no_checkpoint_no_write(self):
        with self.assertRaises(GateStopped):
            self.supervisor.before_dispatch("commit", self.fixture._observe())

    def test_state_change_while_reviewing_stops(self):
        self.fixture.page.mutate_on_review = True
        with self.assertRaisesRegex(GateStopped, "state changed"):
            self.supervisor.checkpoint("gate")

    def test_state_change_after_grant_before_dispatch_stops(self):
        self.supervisor.checkpoint("gate")
        self.fixture.state["backend"]["value"] = 2
        with self.assertRaisesRegex(GateStopped, "stale"):
            self.supervisor.before_dispatch("commit", self.fixture._observe())
        self.assertFalse(self.supervisor.all_consumed())

    def test_missing_review_times_out_and_never_grants(self):
        self.fixture.page.wait_for_timeout = lambda _: None
        with self.assertRaisesRegex(GateStopped, "timed out"):
            self.supervisor.checkpoint("gate")
        self.assertFalse(self.supervisor.all_consumed())

    def test_changed_dom_or_stale_decision_is_rejected(self):
        self.supervisor.checkpoint("gate")
        folder = next(Path(self.tmp.name).glob("interventions/*"))
        request = json.loads((folder / "request.json").read_text())
        decision = json.loads((folder / "decision.json").read_text())
        bad = {**decision, "request_id": "some-older-request"}
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_decision(bad, request, digest(folder / "request.json"), folder,
                              request["public_evidence_sha256"])
        (folder / "ui.dom.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            validate_decision(decision, request, digest(folder / "request.json"), folder,
                              request["public_evidence_sha256"])

    def test_failure_review_cannot_resume_even_with_continue_decision(self):
        self.supervisor.diagnose_failure(RuntimeError("response lost"))
        self.assertFalse(self.supervisor.all_consumed())
        self.assertEqual(self.supervisor.records[0]["status"], "stopped")
        self.assertIn("cannot authorize", self.supervisor.records[0]["error"])

    def test_review_budget_exhaustion_never_grants(self):
        self.supervisor.config["max_reviews_per_case"] = 0
        with self.assertRaisesRegex(GateStopped, "budget"):
            self.supervisor.checkpoint("gate")
        self.assertFalse(self.supervisor.all_consumed())

    def test_truthy_or_empty_independent_checks_cannot_grant(self):
        for checks in ([], [{"id": "x", "passed": 1}], [{"id": "x", "passed": None}],
                       [{"id": "x", "passed": True}, {"id": "x", "passed": True}]):
            self.assertFalse(evaluate_gate({"decision": "continue", "checks": checks}))

    def test_missing_channels_and_required_readouts_block_independent_permission(self):
        for key in ("ui", "backend"):
            state = copy.deepcopy(self.fixture.state)
            del state[key]
            self.assertEqual(self.supervisor._independent("gate", state)["decision"], "unknown")
        self.supervisor.gates[0]["required_readouts"] = ["total"]
        self.fixture.state["ui"]["fields"]["total"] = None
        self.fixture.state["ui"]["errors"] = {"total": "missing"}
        self.assertEqual(self.supervisor._independent("gate", self.fixture.state)["decision"], "unknown")

    def test_structured_public_summary_cannot_expose_private_data(self):
        self.fixture.checkpoint = lambda *args: {
            "decision": "continue", "checks": [{"id": "x", "passed": True}],
            "public_summary": {"private_marker": "oracle-only"},
        }
        value = self.supervisor._independent("gate", self.fixture.state)
        self.assertEqual(value["decision"], "unknown")
        self.assertNotIn("oracle-only", json.dumps(self.supervisor._public_verdict(value)))

    def test_protocol_budget_and_required_failure_review_slot(self):
        validate_supervision(self.fixture._plan)
        self.fixture._plan["supervision"]["max_reviews_per_case"] = 1
        with self.assertRaisesRegex(ValueError, "reserve"):
            validate_supervision(self.fixture._plan)
        self.fixture._plan["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "protocol 2"):
            validate_supervision(self.fixture._plan)


if __name__ == "__main__":
    unittest.main()
