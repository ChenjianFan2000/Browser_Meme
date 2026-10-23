"""Synthetic v3 gate controls only; no browser, target, or hidden oracle."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import types
import unittest

from harness.replica import runner_playwright as runner

POLICY = {"playwright_version":"1.62.0","mode":"default","depth":None,"boxes":False,"name_limit":900}


def canonical_semantics(record, roots):
    result = deepcopy(record)
    for frame in result["frames"]:
        frame["url"] = runner.trees._url(frame["url"], roots)
    return result


COLLECTOR = types.SimpleNamespace(POLICY=POLICY, canonical_semantics=canonical_semantics)


class GenericUnitOracle:
    def __init__(self, verdict="pass"):
        self.verdict = verdict

    def capture(self, lane, case, checkpoint):
        return {"status":"confirmed","facts":{"generic_count":1},"logical_object_identities":{"item":"generic"},
                "coverage":{"count":True},"evidence_refs":["synthetic-unit-evidence"]}

    def assess(self, case, checkpoint, previous, current, action):
        return {"verdict":self.verdict,"checks":{"count":{"passed":True}},"evidence_refs":["synthetic-unit-evidence"]}


class PlaywrightControllerUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origins = ("http://source.invalid","http://replica.invalid")
        self.roots = {origin:"http://registered-origin.invalid" for origin in self.origins}
        self.records = []
        self.raws = []
        self.semantics = []
        for lane, origin in zip(("source","replica"),self.origins):
            directory = self.root/lane/"obs-0001"
            directory.mkdir(parents=True)
            text = {"nodeType":3,"nodeName":"#text","text":"Do thing","children":[]}
            button = {"nodeType":1,"nodeName":"BUTTON","attributes":{"id":"generic"},"live":{"focused":False},"children":[text]}
            body = {"nodeType":1,"nodeName":"BODY","attributes":{},"live":{"focused":False},"children":[button]}
            doc = {"nodeType":9,"nodeName":"#document","children":[body]}
            frame = {"key":"f0","parent":None,"owner":None,"url":origin+"/","name":"","cdp_frame_id":"frame",
                     "dom":doc,"activeElementPath":"document/children/0",
                     "cdp_dom":{"nodeType":9,"nodeName":"#document","backendNodeId":1,"children":[]},
                     "ax":[{"nodeId":"1","role":{"value":"RootWebArea"},"name":{"value":"Generic fixture"},"childIds":["2"]},
                           {"nodeId":"2","parentId":"1","role":{"value":"button"},"name":{"value":"Do thing"}}]}
            raw = {"schema":runner.trees.SCHEMA,"environment":{"fixture":"synthetic"},"frames":[frame],"unsupported":[]}
            semantics = {"schema":runner.SEMANTICS_SCHEMA,"status":"confirmed","policy":POLICY,
                         "frames":[{key:frame[key] for key in ("key","parent","owner","url","name")}|{"root":"body","snapshot":'- button "Do thing"'}],"unsupported":[]}
            record = {"checkpoint":"after_action","action":1,"method":"click","status":"observed",
                      "private_trees_directory":str(directory.parent),"evidence_directory":str(directory.parent),
                      "observation":{"dom":"obs-0001.html","auxiliary":{"playwright_semantics":{
                          "file":"playwright-semantics.json","schema":runner.SEMANTICS_SCHEMA,"status":"confirmed"}}},
                      "action_arguments":{"args":[],"kwargs":{}},"action_identity":{"owner":"Locator","method":"click","element":{"id":"generic"}},
                      "stability":{"enabled":True,"status":"stable"}}
            self.raws.append(raw);self.semantics.append(semantics);self.records.append(record)

    def compare(self, *, oracle=True):
        for lane,raw,semantics in zip(("source","replica"),self.raws,self.semantics):
            directory=self.root/lane/"obs-0001"
            (directory/"raw.json").write_text(json.dumps(raw))
            (directory/"playwright-semantics.json").write_text(json.dumps(semantics))
        return runner._compare_step(*self.records,self.root/"comparison",self.roots,mode=runner.MODE,
            semantics_module=COLLECTOR,oracle=GenericUnitOracle() if oracle is True else oracle,
            preparations={lane:{"initial_equivalence":"pass","reset_receipt":"unit-reset"} for lane in ("source","replica")})

    def test_identical_complete_payloads_pass_v3(self):
        result=self.compare()
        self.assertEqual(result["schema"],"replica-script-continuity/v3")
        self.assertTrue(result["script_continuity_pass"] and result["primary_pass"])
        self.assertTrue(result["full_ax_match"] and result["playwright_semantics_match"])

    def test_synthetic_full_ax_difference_is_diagnostic_only(self):
        self.raws[1]["frames"][0]["ax"][1]["ignoredReasons"]=[{"name":"uninteresting","value":{"value":True}}]
        result=self.compare()
        self.assertTrue(result["script_continuity_pass"])
        self.assertFalse(result["full_ax_match"] or result["ax_match"] or result["raw_strict_exact"])
        self.assertTrue(result["public_dom_match"] and result["playwright_semantics_match"])

    def test_exact_semantics_reject_extra_tail_not_contains_match(self):
        self.semantics[1]["frames"][0]["snapshot"]+='\n- button "Extra"'
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"playwright_semantics")

    def test_full_dom_difference_still_mandatory(self):
        self.raws[1]["frames"][0]["dom"]["children"][0]["attributes"]["style"]=""
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"public_dom")

    def test_no_independent_business_evidence_cannot_pass(self):
        result=self.compare(oracle=None)
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["business_verdict"],"unconfirmed")

    def test_independent_business_failure_cannot_pass(self):
        result=self.compare(oracle=GenericUnitOracle("fail"))
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"business")

    def test_readpoint_is_not_a_completed_task_pass(self):
        for record in self.records:record["status"]="needs_reading"
        result=self.compare()
        self.assertTrue(result["needs_reading"])
        self.assertFalse(result["script_continuity_pass"])
        self.assertEqual(result["first_failure_layer"],"needs_reading")

    def test_unstable_capture_cannot_pass(self):
        self.records[0]["stability"]["status"]="unconfirmed"
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"capture_stability_unconfirmed")

    def test_disabled_stability_cannot_pass(self):
        for record in self.records:record["stability"]["enabled"]=False
        self.assertFalse(self.compare()["primary_pass"])

    def test_unsupported_name_omission_cannot_pass(self):
        self.semantics[0]["status"]="unconfirmed"
        self.semantics[0]["unsupported"]=[{"kind":"accessible_name_exceeds_900"}]
        self.records[0]["observation"]["auxiliary"]["playwright_semantics"]["status"]="unconfirmed"
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"playwright_semantics_unconfirmed")

    def test_missing_aux_reference_cannot_pass(self):
        self.records[0]["observation"].pop("auxiliary")
        result=self.compare()
        self.assertFalse(result["playwright_semantics_match"])
        self.assertEqual(result["first_failure_layer"],"playwright_semantics_unconfirmed")

    def test_missing_frame_topology_cannot_pass(self):
        self.semantics[0]["frames"][0]["owner"]="unexpected-owner"
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"playwright_semantics_unconfirmed")

    def test_action_identity_is_mandatory(self):
        self.records[0]["action_identity"]["element"]["id"]="another-object"
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"action_identity")

    def test_terminal_missing_dom_returns_failure_without_keyerror(self):
        self.records[0]["status"]="terminated"
        self.records[0]["observation"]={"failure_category":"runtime_terminated"}
        result=self.compare()
        self.assertFalse(result["primary_pass"])
        self.assertEqual(result["first_failure_layer"],"runtime_terminated")

    def test_old_mode_is_rejected_before_reading_input_or_spawning(self):
        with self.assertRaisesRegex(ValueError,"separate v3 controller"):
            runner.run_pair({}, {}, "not-read.py",self.root/"must-not-exist",policy={"mode":"observable_continuity"})
        self.assertFalse((self.root/"must-not-exist").exists())


if __name__ == "__main__":unittest.main()
