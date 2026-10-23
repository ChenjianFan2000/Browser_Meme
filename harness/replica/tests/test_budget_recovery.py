"""Generic persistent-budget regressions; no browser, model or target material."""
from pathlib import Path
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "runtime_versions/learning-budget-recovery-v1"
sys.path.insert(0, str(RUNTIME))
spec = importlib.util.spec_from_file_location("budget_recovery_broker_test", RUNTIME / "browser_broker.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Broker = module.Broker


class BudgetRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.private = self.root / "private"
        self.fixture = self.root / "fixture.json"
        self.fixture.write_text("{}")
        self.config = {"workspace":str(self.workspace), "private":str(self.private),
                       "runtime":str(RUNTIME), "origin":"http://generic.invalid", "socket":"unused",
                       "fixture_path":str(self.fixture), "action_limit":1000,
                       "script_call_limit":100, "time_limit_seconds":3600}
        self.broker = Broker(self.config)

    def append(self, row):
        self.broker.log(row)

    def job(self, number, count, *, suffix="aaaaaaaa", result=True, dispatch=True):
        key = f"call-{number:03d}-{suffix}"
        directory = self.private / key
        evidence = directory / "evidence"
        evidence.mkdir(parents=True)
        records = [{"kind":kind, "action":action} for action in range(1, count+1)
                   for kind in ("action_before", "action_after")]
        (evidence / "actions.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records))
        if dispatch:
            self.append({"event":"dispatch", "call":key, "time_ns":time.time_ns()})
        if result:
            self.append({"event":"result", "call":key, "actions":count, "status":"completed"})
            (evidence / "result.json").write_text(json.dumps({"actions":count,"status":"completed"}))
        return key, directory

    def test_completed_and_interrupted_counts_join_without_double_charge(self):
        for number, count in enumerate([10]*8+[16], 1):
            self.job(number, count)
        self.job(10, 5, result=False)
        restored = Broker(self.config)
        self.assertEqual((restored.actions, restored.calls, restored.next_call_number), (101,10,11))
        self.assertIn("execution_completion_unconfirmed", restored.closed_reason)
        self.assertEqual(Broker(self.config).closed_reason, restored.closed_reason)

    def test_duplicate_records_and_reused_ordinal_are_not_duplicate_charges(self):
        key, _ = self.job(9, 5)
        self.append({"event":"dispatch", "call":key})
        self.append({"event":"result", "call":key, "actions":5, "status":"completed"})
        self.job(9, 3, suffix="bbbbbbbb")
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls,restored.next_call_number),(8,2,10))
        self.assertIsNone(restored.closed_reason)

    def test_orphan_prepared_job_reserves_call_and_fails_closed(self):
        self.job(9, 0, dispatch=False, result=False)
        restored = Broker(self.config)
        self.assertEqual((restored.calls, restored.next_call_number),(1,10))
        self.assertIn("execution_completion_unconfirmed", restored.closed_reason)

    def test_truncated_action_journal_keeps_known_count_and_refuses_even_after_repair(self):
        _, directory = self.job(1, 3)
        path = directory / "evidence/actions.jsonl"
        complete = path.read_text()
        path.write_text(complete+'{"kind":"action_before",')
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls),(3,1))
        reason = restored.closed_reason
        self.assertIn("budget_recovery_unconfirmed", reason)
        path.write_text(complete)
        self.assertEqual(Broker(self.config).closed_reason, reason)

    def test_truncated_broker_journal_preserves_original_policy_reason(self):
        self.job(1, 2)
        reason = "policy_rejection:generic-secret-read-denied"
        self.append({"event":"policy_rejection","stop_reason":reason})
        with self.broker.journal.open("a") as stream:
            stream.write('{"event":')
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls),(2,1))
        self.assertEqual(restored.closed_reason,reason)
        self.assertFalse(restored.recovery["counts_complete"])

    def test_valid_json_without_final_newline_is_uncertain(self):
        self.job(1, 2)
        self.broker.journal.write_text(self.broker.journal.read_text().rstrip("\n"))
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls),(2,1))
        self.assertIn("unterminated_line", restored.closed_reason)

    def test_runtime_policy_refusal_survives_missing_broker_result(self):
        _, directory = self.job(1, 2, result=False)
        path = directory / "evidence/actions.jsonl"
        with path.open("a") as stream:
            stream.write(json.dumps({"kind":"policy_rejection","stop_reason":"generic-secret-denial"})+"\n")
        restored = Broker(self.config)
        self.assertEqual(restored.closed_reason,"policy_rejection:generic-secret-denial")
        self.assertEqual((restored.actions,restored.calls),(2,1))

    def test_runtime_termination_survives_missing_broker_result(self):
        _, directory = self.job(1, 2, result=False)
        path = directory / "evidence/actions.jsonl"
        with path.open("a") as stream:
            stream.write(json.dumps({"kind":"runtime_terminated","stop_reason":"runtime_terminated:page_closed"})+"\n")
        restored = Broker(self.config)
        self.assertEqual(restored.closed_reason,"runtime_terminated:page_closed")

    def test_conflicting_results_charge_the_larger_count_and_fail_closed(self):
        key, _ = self.job(1, 3)
        self.append({"event":"result","call":key,"actions":2,"status":"completed"})
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls),(3,1))
        self.assertIn("conflicting_reported_action_counts",restored.closed_reason)

    def test_confirmed_management_completion_can_recover_missing_broker_result(self):
        key, directory = self.job(1, 4, result=False)
        cleanup = self.private / "cleanup"
        cleanup.mkdir()
        receipt = cleanup / "fixture-nonce.json"
        receipt.write_text(json.dumps({"status":"cleaned","owned_processes_remaining":0,
                                       "nonce":"fixture-nonce","supervisor_pid":12345}))
        outcome = {"call":key,"result":{"actions":4,"status":"completed"},"process_tree_clean":True,
                   "cleanup_receipt":"cleanup/fixture-nonce.json","cleanup_nonce":"fixture-nonce",
                   "supervisor_pid":12345,"budget":{"stop_reason":None}}
        (directory / "management-result.json").write_text(json.dumps(outcome))
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls,restored.next_call_number),(4,1,2))
        self.assertIsNone(restored.closed_reason)

    def test_time_origin_and_original_budget_survive_restart(self):
        path = self.private / "budget-origin.json"
        origin = json.loads(path.read_text())
        origin["wall_ns"] -= 2_000_000_000
        origin["monotonic_ns"] -= 2_000_000_000
        path.write_text(json.dumps(origin))
        self.assertGreaterEqual(Broker(self.config).elapsed(),2)
        changed = {**self.config,"action_limit":2000}
        restored = Broker(changed)
        self.assertIn("registered_budget_changed",restored.closed_reason)
        self.assertEqual(Broker(self.config).closed_reason,restored.closed_reason)

    def test_legacy_missing_time_origin_recovers_counts_but_does_not_refresh_time(self):
        self.job(1, 3)
        (self.private / "budget-origin.json").unlink()
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls),(3,1))
        self.assertIn("legacy_time_origin_unknown",restored.closed_reason)

    def make_worker(self, *, interrupt=False):
        worker = self.root / "ordinary_worker.py"
        worker.write_text('''from pathlib import Path
import json,os,sys,time
job=Path(sys.argv[1]);root=job.parent;evidence=root/'evidence';evidence.mkdir()
with (evidence/'actions.jsonl').open('x') as stream:
 for action in range(1,6):
  for kind in ('action_before','action_after'):
   stream.write(json.dumps({'kind':kind,'action':action})+'\\n');stream.flush();os.fsync(stream.fileno())
if '''+repr(interrupt)+''':
 (root/'interrupted-ready.json').write_text(json.dumps({'pid':os.getpid()}))
 time.sleep(60)
else:
 (evidence/'result.json').write_text(json.dumps({'status':'completed','actions':5,'return_value':None}))
''')
        (self.workspace / "flow.py").write_text("def run(h): return None\n")
        return worker

    def test_actual_plain_worker_counts_live_call_once_and_restart_once(self):
        worker = self.make_worker()
        with patch.object(module,"worker_command",lambda *a,**k:[sys.executable,str(worker),str(a[1])]):
            outcome = self.broker.execute({"script_path":"flow.py"})
        self.assertTrue(outcome["process_tree_clean"])
        self.assertEqual((self.broker.actions,self.broker.calls),(5,1))
        restored = Broker(self.config)
        self.assertEqual((restored.actions,restored.calls,restored.next_call_number),(5,1,2))
        self.assertIsNone(restored.closed_reason)
        self.recovery_evidence = {"plain_worker":True,"browser_started":False,"recovered_actions":restored.actions,
                                  "recovered_calls":restored.calls,"next_call_number":restored.next_call_number,
                                  "process_tree_clean":outcome["process_tree_clean"]}

    def test_actual_broker_sigkill_recovers_five_unreported_actions(self):
        worker = self.make_worker(interrupt=True)
        for number, count in enumerate([10]*8+[16],1):
            self.job(number,count)
        config = self.root / "config.json"
        config.write_text(json.dumps(self.config))
        code = ("import sys,json;sys.path.insert(0,"+repr(str(RUNTIME))+");import browser_broker as m;"
                "m.worker_command=lambda *a,**k:[sys.executable,"+repr(str(worker))+",str(a[1])];"
                "m.Broker(json.load(open("+repr(str(config))+"))).execute({'script_path':'flow.py'})")
        child = subprocess.Popen([sys.executable,"-c",code],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
        ready = None
        try:
            deadline = time.monotonic()+8
            while time.monotonic()<deadline and child.poll() is None:
                ready = next(self.private.glob("call-010-*/interrupted-ready.json"),None)
                if ready:
                    break
                time.sleep(.01)
            self.assertIsNotNone(ready)
            child.kill();child.wait(timeout=3)
            restored = Broker(self.config)
            self.assertEqual((restored.actions,restored.calls,restored.next_call_number),(101,10,11))
            self.assertIn("execution_completion_unconfirmed",restored.closed_reason)
            with self.assertRaisesRegex(ValueError,"execution stopped"):
                restored.execute({"script_path":"flow.py"})
            self.assertEqual(len(list(self.private.glob("call-*"))),10)
            deadline = time.monotonic()+5
            while not list((self.private/'cleanup').glob('*.json')) and time.monotonic()<deadline:
                time.sleep(.01)
            receipts = list((self.private/'cleanup').glob('*.json'))
            self.assertTrue(receipts,"ordinary fake worker must be cleaned after parent kill")
            self.assertEqual(json.loads(receipts[0].read_text())["owned_processes_remaining"],0)
            self.recovery_evidence = {"broker_sigkill_exit_code":child.returncode,
                "seeded_completed_calls":9,"seeded_completed_actions":96,"new_plain_worker_journal_actions":5,
                "recovered_actions":restored.actions,"recovered_calls":restored.calls,
                "next_call_number":restored.next_call_number,"refusal_preserved":restored.closed_reason,
                "new_dispatch_after_refusal":False,"cleanup_receipt":json.loads(receipts[0].read_text()),
                "browser_started":False}
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
            child.stderr.close()


if __name__ == "__main__":
    unittest.main()
