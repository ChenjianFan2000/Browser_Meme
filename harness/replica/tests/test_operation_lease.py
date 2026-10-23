"""Real subprocess lease races/interruption; no browser, target, or model."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from harness.replica import construction, operation_lease

MODULE = Path(operation_lease.__file__).resolve()
GUARD = Path(construction.__file__).resolve().parent/'runtime/process_guard.py'


def wait_for(predicate, seconds=10):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('subprocess evidence did not arrive before deadline')


def rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def alive(pid):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        return raw[raw.rfind(')')+2:].split()[0] != 'Z'
    except FileNotFoundError:
        return False


class OperationLeaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root/'lease'
        self.directory.mkdir()
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=22)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
        self.temp.cleanup()

    def launch(self, name, *, kind='browser-call', seconds=.1, wait=10, guard=GUARD, code=None, deadline_ns=None):
        event = self.root/(name+'.json')
        source = code or (f"import json,pathlib,time; p=pathlib.Path({str(event)!r}); "
                         "p.write_text(json.dumps({'start':time.monotonic()})); "
                         f"time.sleep({seconds}); "
                         "v=json.loads(p.read_text()); v['end']=time.monotonic(); p.write_text(json.dumps(v))")
        command = [sys.executable, str(MODULE), '--directory', str(self.directory), '--kind', kind,
                   '--guard', str(guard), '--wait-seconds', str(wait), '--timeout-seconds', '15',
                   '--expected-parent', str(os.getpid())]
        if deadline_ns is not None:
            command += ['--deadline-ns', str(deadline_ns), '--budget-boot-id', operation_lease.boot_id()]
        command += ['--', sys.executable, '-c', source]
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.children.append(child)
        return child, event

    def finish(self, child, expected=0):
        stdout, stderr = child.communicate(timeout=30)
        self.assertEqual(child.returncode, expected, (stdout, stderr))

    def test_calls_serialize_and_waiting_maintenance_blocks_new_call(self):
        first, first_event = self.launch('first', seconds=.6)
        wait_for(first_event.exists)
        maintenance, maintenance_event = self.launch('maintenance', kind='maintenance', seconds=.2)
        wait_for(lambda: any(row['kind'] == 'maintenance' and row['state'] == 'admission_acquired'
                             for row in rows(self.directory/'journal.jsonl')))
        second, second_event = self.launch('second')
        for child in (first, maintenance, second):
            self.finish(child)
        a, b, c = [json.loads(path.read_text()) for path in (first_event, maintenance_event, second_event)]
        self.assertLessEqual(a['end'], b['start'])
        self.assertLessEqual(b['end'], c['start'])
        print(json.dumps({'probe': 'maintenance_reserves_admission', 'first': a, 'maintenance': b, 'second': c}), flush=True)

    def test_nonblocking_maintenance_refuses_active_call_without_dispatch(self):
        first, event = self.launch('first', seconds=.7)
        wait_for(event.exists)
        blocked, blocked_event = self.launch('must-not-run', kind='maintenance', wait=0)
        self.finish(blocked, 75)
        self.assertFalse(blocked_event.exists())
        self.finish(first)
        print(json.dumps({'probe': 'busy_maintenance', 'exit_code': blocked.returncode,
                          'command_marker_exists': blocked_event.exists()}), flush=True)

    def test_cli_or_lease_death_retains_lock_until_actual_worker_cleanup(self):
        # Gate trusted cleanup deliberately, creating an observable interval
        # where a live detached worker must continue to exclude maintenance.
        delayed_guard = self.root/'delayed_guard.py'
        cleanup_gate = self.root/'allow-cleanup'
        cleanup_started = self.root/'cleanup-started'
        delayed_guard.write_text('import importlib.util,time,pathlib\n'
            f's=importlib.util.spec_from_file_location("real_guard",{str(GUARD)!r})\n'
            'g=importlib.util.module_from_spec(s);s.loader.exec_module(g)\n'
            'def terminate_owned():\n'
            f' pathlib.Path({str(cleanup_started)!r}).touch()\n'
            ' deadline=time.monotonic()+10\n'
            f' while not pathlib.Path({str(cleanup_gate)!r}).exists() and time.monotonic()<deadline: time.sleep(.01)\n'
            ' g.terminate_owned()\n')
        for killed in ('wrapper', 'lease'):
            with self.subTest(killed=killed):
                cleanup_gate.unlink(missing_ok=True)
                cleanup_started.unlink(missing_ok=True)
                marker = self.root/(killed+'-worker.json')
                broker = self.root/(killed+'-broker.py')
                broker.write_text('import subprocess,sys,time,json,pathlib\n'
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True)\n'
                    f'pathlib.Path({str(marker)!r}).write_text(json.dumps({{"pid":p.pid}}))\n'
                    'time.sleep(30)\n')
                workspace = self.root/(killed+'-workspace')
                workspace.mkdir()
                (workspace/'flow.py').write_text('def run(h): pass\n')
                lease_command = [sys.executable, str(MODULE), '--directory', str(self.directory),
                    '--kind', 'browser-call', '--guard', str(delayed_guard), '--wait-seconds', '10',
                    '--timeout-seconds', '15']
                wrapper = (construction._WRAPPER.replace('__COMMAND__', repr([sys.executable, str(broker)]))
                    .replace('__LEASE_COMMAND__', repr(lease_command)).replace('__STOP_PATHS__', '[]'))
                (workspace/'browser.py').write_text(wrapper)
                cli = subprocess.Popen([sys.executable, str(workspace/'browser.py'), '--script', 'flow.py'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                self.children.append(cli)
                wait_for(marker.exists)
                claim = json.loads((self.directory/'active.json').read_text())
                pid = json.loads(marker.read_text())['pid']
                self.assertTrue(alive(pid))
                os.kill(cli.pid if killed == 'wrapper' else claim['lease_pid'], signal.SIGKILL)
                wait_for(cleanup_started.exists)
                blocked, blocked_event = self.launch(killed+'-blocked', kind='maintenance', wait=0)
                self.finish(blocked, 75)
                self.assertFalse(blocked_event.exists())
                worker_alive_at_busy_return = alive(pid)
                self.assertTrue(worker_alive_at_busy_return)
                cleanup_gate.touch()
                cli.communicate(timeout=5)
                wait_for(lambda: not alive(pid))
                worker_alive_before_maintenance = alive(pid)
                after, after_event = self.launch(killed+'-after', kind='maintenance', wait=5)
                self.finish(after)
                receipt = json.loads(Path(claim['receipt']).read_text())
                self.assertEqual(receipt['owned_processes_remaining'], 0)
                self.assertTrue(after_event.exists())
                print(json.dumps({'probe': 'interruption', 'killed': killed, 'worker_pid': pid,
                    'blocked_exit_code': blocked.returncode,
                    'worker_alive_at_busy_return': worker_alive_at_busy_return,
                    'worker_alive_before_maintenance': worker_alive_before_maintenance,
                    'cleanup_receipt': receipt, 'maintenance': json.loads(after_event.read_text())}), flush=True)

    def test_unconfirmed_previous_cleanup_is_fail_closed(self):
        (self.directory/'active.json').write_text(json.dumps({'nonce': 'unknown',
            'supervisor_pid': 1, 'receipt': str(self.root/'missing.json')}))
        child, event = self.launch('must-not-run', kind='maintenance', wait=0)
        self.finish(child, 75)
        self.assertFalse(event.exists())

    def test_total_deadline_survives_two_wrapper_processes_and_maintenance(self):
        auth = self.root/'dummy-auth.json'
        auth.touch()
        prepared = construction.prepare({'run_dir': str(self.root/'prepared'),
            'origin': 'http://127.0.0.1:12345', 'task': 'Generic no-browser deadline fixture',
            'auth_source': str(auth), 'time_limit_seconds': 5})
        lease = prepared['operation_lease']
        budget = lease['run_budget']
        # Substitute an ordinary executor in the same generated wrapper template;
        # the tested lease command and immutable budget are production outputs.
        workspace = self.root/'deadline-wrapper'
        workspace.mkdir()
        effects = self.root/'effects.jsonl'
        broker = self.root/'deadline-broker.py'
        broker.write_text('import json,pathlib,sys,time\n'
            'request=json.loads(pathlib.Path(sys.argv[-1]).read_text())\n'
            f'with pathlib.Path({str(effects)!r}).open("a") as out: out.write(json.dumps({{"script":request["script_path"],"time_monotonic_ns":time.monotonic_ns()}})+"\\n")\n'
            'print(json.dumps({"result":{"status":"completed"}}))\n')
        wrapper = (construction._WRAPPER.replace('__COMMAND__', repr([sys.executable, str(broker)]))
            .replace('__LEASE_COMMAND__', repr(construction._operation_command(lease, 'browser-call')))
            .replace('__STOP_PATHS__', '[]'))
        (workspace/'browser.py').write_text(wrapper)
        for script in ('first.py', 'second.py'):
            (workspace/script).write_text('def run(h): pass\n')
        first = subprocess.run([sys.executable, str(workspace/'browser.py'), '--script', 'first.py'],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        wait_for(lambda: time.monotonic_ns() >= budget['deadline_ns'])
        maintenance = construction.maintenance(prepared['plan_path'], [sys.executable, '-c', 'pass'])
        self.assertEqual(maintenance['exit_code'], 0)
        second = subprocess.run([sys.executable, str(workspace/'browser.py'), '--script', 'second.py'],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(second.returncode, 124, second.stderr)
        self.assertEqual([row['script'] for row in rows(effects)], ['first.py'])
        registration = json.loads(Path(prepared['registration_path']).read_text())
        self.assertEqual(registration['run_budget']['deadline_ns'], budget['deadline_ns'])
        self.assertEqual(construction._verify(Path(prepared['plan']['run_dir']), registration), [])
        health = construction.serve_gateway(prepared['plan_path'], interval=.05)
        self.assertEqual(health['reason'], 'construction_total_wall_deadline')
        print(json.dumps({'probe': 'immutable_prepare_deadline', 'budget': budget,
            'first_exit': first.returncode, 'second_exit': second.returncode,
            'maintenance_exit': maintenance['exit_code'], 'effects': rows(effects),
            'gateway': health}), flush=True)

    def test_total_deadline_terminates_an_active_ordinary_process(self):
        marker = self.root/'active-process.json'
        suffix = self.root/'must-not-run'
        deadline = time.monotonic_ns()+4_000_000_000
        source = ('import json,os,pathlib,time; '
            f'pathlib.Path({str(marker)!r}).write_text(json.dumps({{"pid":os.getpid()}})); '
            f'time.sleep(30); pathlib.Path({str(suffix)!r}).touch()')
        child, _ = self.launch('deadline-active', code=source, deadline_ns=deadline)
        wait_for(marker.exists)
        pid = json.loads(marker.read_text())['pid']
        self.finish(child, 124)
        self.assertFalse(alive(pid))
        self.assertFalse(suffix.exists())
        receipt_path = list(self.directory.glob('*.cleanup.json'))[0]
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt['owned_processes_remaining'], 0)
        print(json.dumps({'probe': 'active_deadline', 'deadline_ns': deadline,
            'observed_finished_ns': time.monotonic_ns(), 'worker_alive': alive(pid),
            'suffix_exists': suffix.exists(), 'receipt': receipt}), flush=True)

    def test_running_gateway_stops_at_frozen_prepare_deadline_without_browser(self):
        auth = self.root/'dummy-auth.json'
        auth.touch()
        prepared = construction.prepare({'run_dir': str(self.root/'gateway-budget'),
            'origin': 'http://127.0.0.1:12345', 'task': 'Generic gateway budget fixture',
            'auth_source': str(auth), 'time_limit_seconds': 2})
        result = construction.serve_gateway(prepared['plan_path'], interval=.05)
        private = Path(prepared['plan']['private'])
        journal = rows(private/'gateway-heartbeat.jsonl')
        self.assertTrue(any(row['state'] == 'ready' for row in journal))
        self.assertEqual(result['reason'], 'construction_total_wall_deadline')
        self.assertFalse(Path(prepared['plan']['socket']).exists())
        print(json.dumps({'probe': 'running_gateway_deadline', 'budget': prepared['operation_lease']['run_budget'],
            'states': [row['state'] for row in journal], 'result': result}), flush=True)

    def test_prepare_freezes_lease_without_rewriting_an_earlier_run(self):
        auth = self.root/'dummy-auth.json'
        auth.touch()
        previous = self.root/'previous'
        previous.mkdir()
        (previous/'prior-artifact.txt').write_text('Generic prior construction artifact')
        selected_runtime = GUARD.parent.parent/'runtime_versions/helper-safe-v1'
        result = construction.prepare({'run_dir': str(self.root/'construction'),
            'origin': 'http://127.0.0.1:12345', 'task': 'Generic no-browser fixture',
            'auth_source': str(auth), 'runtime_source': str(selected_runtime),
            'from_previous_workspace': str(previous), 'new_context_with_inherited_artifacts': True})
        registration = json.loads(Path(result['registration_path']).read_text())
        lease = registration['operation_lease']
        self.assertTrue(Path(lease['module']).is_file())
        self.assertIn('private/control/operation_lease.py', registration['files'])
        self.assertEqual(construction._verify(Path(result['plan']['run_dir']), registration), [])
        self.assertEqual(result['plan']['runtime_source'], str(selected_runtime))
        self.assertTrue(registration['new_context_with_inherited_artifacts'])
        self.assertFalse(registration['same_author_continuation'])
        self.assertEqual(set(registration['inherited_artifact_hashes']), {'prior-artifact.txt'})
        marker = self.root/'maintenance-ran'
        outcome = construction.maintenance(result['plan_path'], [sys.executable, '-c',
            f'from pathlib import Path;Path({str(marker)!r}).touch()'])
        self.assertEqual(outcome['exit_code'], 0)
        self.assertTrue(marker.exists())


if __name__ == '__main__':
    unittest.main()
