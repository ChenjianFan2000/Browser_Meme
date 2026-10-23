"""Generic evaluation gates; no target-site sources or hidden task inputs."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading

import pytest

from harness.replica import runner
from harness.tests.test_replica_trees import sample


class IndependentFixtureOracle:
    """Fault injection oracle, independent of learner predictions and DOM diffs."""
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
    def describe(self):
        return {"independent":True,"adapter":"generic-test","site":"fixture","version":1,"fact_schema":{"count":"integer"},"checkpoint_obligations":["equivalence","persistence"],"identity_scheme":"fixed fixture object"}
    def prepare(self,lane,case_ref):
        return {"initial_equivalence":"pass","reset_receipt":"independent-fixture-reset-"+lane}
    def capture(self,lane,case_ref,checkpoint):
        corrupted = lane == "replica" and checkpoint["kind"] == self.fail_at
        return {"status":"confirmed","facts":{"count":2 if corrupted else 1},"logical_object_identities":{"object":"fixture-object"},"evidence_refs":["independent-fixture-control"],"coverage":{"equivalence":True,"persistence":True}}
    def assess(self,case_ref,checkpoint,before,after,action):
        assert "prediction" not in action
        return {"verdict":"pass","checks":[{"name":"independent control","pass":True}],"evidence_refs":["independent-fixture-control"]}


def records(tmp_path, *, kind="after_action", script_difference=False):
    result = []
    for lane in ("source","replica"):
        root = tmp_path/lane
        (root/"obs-0001").mkdir(parents=True)
        raw = sample(offset=100 if lane == "replica" else 0)["raw"]
        if script_difference:
            raw["frames"][0]["dom"]["children"].append({"nodeType":1,"nodeName":"SCRIPT","attributes":{},"children":[{"nodeType":3,"nodeName":"#text","text":lane,"children":[]}]})
        (root/"obs-0001"/"raw.json").write_text(json.dumps(raw))
        result.append({"private_trees_directory":str(root),"evidence_directory":str(root),"observation":{"dom":"obs-0001.html"},
                       "checkpoint":kind,"action":1 if kind == "after_action" else 0,"method":"click" if kind == "after_action" else kind,
                       "action_arguments":{"args":[],"kwargs":{}},"action_identity":{"owner":"Locator","element":{"id":"fixture-object"}},"error":None})
    return result


def compare_fixture(tmp_path, rows, *, oracle=None, mode="observable_continuity"):
    return runner._compare_step(*rows,tmp_path/"comparison",{},mode=mode,oracle=oracle,case_ref="private-fixture",previous={},
        preparations={lane:{"initial_equivalence":"pass","reset_receipt":"receipt"} for lane in ("source","replica")})


def test_mode_is_mandatory_before_any_output(tmp_path):
    with pytest.raises(ValueError,match="preregister"):
        runner.run_pair({}, {}, "unused", tmp_path/"never-created")
    assert not (tmp_path/"never-created").exists()


def test_script_only_difference_can_pass_public_policy_never_raw(tmp_path):
    result = compare_fixture(tmp_path,records(tmp_path,script_difference=True),oracle=IndependentFixtureOracle())
    assert result["primary_pass"]
    assert result["public_dom_match"] and result["ax_match"]
    assert result["raw_strict_exact"] is False
    assert "exact" not in result


def test_preregistered_raw_strict_mode_does_not_fall_back(tmp_path):
    result = compare_fixture(tmp_path,records(tmp_path,script_difference=True),oracle=IndependentFixtureOracle(),mode="raw_strict")
    assert not result["primary_pass"]
    assert result["first_failure_layer"] == "raw_strict"
    assert result["public_dom_match"] and result["ax_match"]


def test_partial_oracle_coverage_cannot_claim_business_pass(tmp_path):
    class PartialOracle(IndependentFixtureOracle):
        def capture(self,*args):
            value = super().capture(*args)
            value["coverage"]["persistence"] = False
            return value
    result = compare_fixture(tmp_path,records(tmp_path),oracle=PartialOracle())
    assert result["business_verdict"] == "unconfirmed"
    assert not result["primary_pass"]


def test_legitimate_false_business_fact_is_not_unknown(tmp_path):
    class BusinessFalseOracle(IndependentFixtureOracle):
        def capture(self,*args):
            value = super().capture(*args)
            value["facts"]["authenticated"] = False
            value["facts"]["optional"] = None
            return value
        def assess(self,*args):
            value = super().assess(*args)
            value["checks"][0].update({"expected":False,"observed":False,"detail":None})
            return value
    assert compare_fixture(tmp_path,records(tmp_path),oracle=BusinessFalseOracle())["primary_pass"]


def test_no_oracle_is_unconfirmed_never_business_pass(tmp_path):
    result = compare_fixture(tmp_path,records(tmp_path))
    assert result["raw_strict_exact"]
    assert result["business_verdict"] == "unconfirmed"
    assert not result["primary_pass"]


def test_independent_business_difference_fails_equal_ui(tmp_path):
    result = compare_fixture(tmp_path,records(tmp_path),oracle=IndependentFixtureOracle("after_action"))
    assert result["raw_strict_exact"] and result["public_dom_match"] and result["ax_match"]
    assert result["business_verdict"] == "fail"
    assert not result["primary_pass"]


def test_action_argument_or_functional_identity_difference_fails(tmp_path):
    rows = records(tmp_path)
    rows[1]["action_arguments"]["args"] = ["wrong input"]
    rows[1]["action_identity"]["element"]["id"] = "wrong-object"
    result = compare_fixture(tmp_path,rows,oracle=IndependentFixtureOracle())
    assert result["raw_strict_exact"]
    assert not result["action_identity_match"]
    assert not result["primary_pass"]


def test_style_and_business_text_cannot_be_projected_away(tmp_path):
    a = sample()["raw"]
    a["frames"][0]["dom"]["children"].append({"nodeName":"STYLE","nodeType":1,"children":[{"nodeName":"#text","nodeType":3,"text":"body{color:red}","children":[]}]})
    b = deepcopy(a)
    b["frames"][0]["dom"]["children"][-1]["children"][0]["text"] = "body{color:blue}"
    assert runner._public_projection(runner.trees.canonicalize(a)) != runner._public_projection(runner.trees.canonicalize(b))


def test_javascript_looking_business_attribute_is_retained():
    tree = runner.trees.canonicalize(sample()["raw"])
    node = tree["frames"][0]["document"]["children"][0]
    node["attributes"].update({"href":"javascript:invoke()","data-note":"javascript:business-text"})
    projected = runner._public_projection(tree)
    attrs = projected["frames"][0]["document"]["children"][0]["attributes"]
    assert "href" not in attrs
    assert attrs["data-note"] == "javascript:business-text"


@pytest.fixture
def fixture_servers():
    resources = []
    def start(body):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = body.encode()
                self.send_response(200);self.send_header("Content-Type","text/html");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self,*args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        resources.append((server,thread))
        return {"origin":"http://fixture.test:"+str(server.server_port),"socket":"unused-"+str(server.server_port),"upstream_host":"127.0.0.1","upstream_port":server.server_port,"public_fixture":{}}
    yield start
    for server,thread in resources:
        server.shutdown();server.server_close();thread.join(5)


GENERIC_SCRIPT = '''def run(h):
    h.expect({"disposition":"unknown"})
    h.page.locator("button").click()
    h.note("action suffix completed")
'''
BODY = '<!doctype html><html><head><title>Fixture</title></head><body><button onclick="document.querySelector(\'output\').textContent=\'changed\'">Apply</button><output>initial</output><script>const implementation = "VERSION";localStorage.setItem("fixture-control","independent-private-marker");</script></body></html>'


def run_fixture(tmp_path,fixture_servers,left,right,script=GENERIC_SCRIPT,oracle=None):
    source = tmp_path/"generic-script.py"
    source.write_text(script)
    return runner.run_pair(fixture_servers(left),fixture_servers(right),source,tmp_path/"new-preregistered-run",policy={"mode":"observable_continuity","wall_seconds":120,"progress_seconds":50,"barrier_wait_seconds":40,"min_memory_bytes":0,"min_disk_bytes":0,"collect_private_control_state":True},oracle=oracle,case_ref="generic-private-case")


real = pytest.mark.skipif(os.environ.get("BROWSER_REPLICA_RUNNER_SMOKE") != "1",reason="opt-in real paired namespace workers")


@real
def test_real_same_application_state0_action_final(tmp_path,fixture_servers):
    result = run_fixture(tmp_path,fixture_servers,BODY,BODY,oracle=IndependentFixtureOracle())
    assert result["primary_pass"], result
    assert result["raw_strict_exact"]
    assert result["state0_compared"] and result["final_compared"]
    assert result["compared_actions"] == 1
    for lane in ("source","replica"):
        private = tmp_path/"new-preregistered-run"/lane/"job"/"private-trees"/"obs-0001"/"control-state.json"
        assert json.loads(private.read_text())["local_storage"]["fixture-control"] == "independent-private-marker"
        assert "independent-private-marker" not in json.dumps(result["lanes"][lane]["result"]["last_observation"])


@real
def test_real_script_only_difference_observable_pass_raw_false(tmp_path,fixture_servers):
    result = run_fixture(tmp_path,fixture_servers,BODY,BODY.replace("VERSION","OTHER IMPLEMENTATION"),oracle=IndependentFixtureOracle())
    assert result["primary_pass"], result
    assert result["raw_strict_exact"] is False


@real
def test_real_state0_difference_stops_zero_actions(tmp_path,fixture_servers):
    result = run_fixture(tmp_path,fixture_servers,BODY,BODY.replace("initial","wrong initial"),oracle=IndependentFixtureOracle())
    assert not result["primary_pass"]
    assert result["first_failure"]["checkpoint"] == "state0"
    assert result["compared_actions"] == 0
    assert all(row["result"]["actions"] == 0 for row in result["lanes"].values())


@real
def test_real_read_point_suffix_write_is_not_executed(tmp_path,fixture_servers):
    script = 'def run(h):\n    h.read_point("inspect before write")\n    h.expect({"disposition":"unknown"})\n    h.page.locator("button").click()\n'
    result = run_fixture(tmp_path,fixture_servers,BODY,BODY,script,IndependentFixtureOracle())
    assert result["completion_status"] == "needs_reading", result
    assert not result["primary_pass"]
    assert all(row["result"]["actions"] == 0 for row in result["lanes"].values())
    assert all((tmp_path/"new-preregistered-run"/lane/"unexecuted-source-suffix.py").exists() for lane in ("source","replica"))
    assert all("changed" not in row["result"]["last_observation"]["visible_text"] for row in result["lanes"].values())


@real
def test_real_business_difference_stops_before_suffix(tmp_path,fixture_servers):
    script = GENERIC_SCRIPT + '    h.expect({"disposition":"unknown"})\n    h.page.locator("button").click()\n'
    result = run_fixture(tmp_path,fixture_servers,BODY,BODY,script,IndependentFixtureOracle("after_action"))
    assert not result["primary_pass"]
    assert result["business_verdict"] == "fail"
    assert result["compared_actions"] == 1
    assert all(row["result"]["actions"] == 1 for row in result["lanes"].values())
