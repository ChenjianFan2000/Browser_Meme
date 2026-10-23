"""Generic construction handoff integration; no authentication or model calls."""
import ast
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from harness.replica.construction import prepare, serve_gateway


class ConstructionTest(unittest.TestCase):
    def test_separate_call_timeout_is_frozen_without_extending_run_deadline(self):
        for configured in (None, 120):
            with self.subTest(call_timeout=configured), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                auth = root / 'dummy-auth-selector.json'
                auth.touch()
                config = dict(run_dir=str(root / 'run'), origin='http://127.0.0.1:1',
                              task='Generic offline preparation.', auth_source=str(auth),
                              time_limit_seconds=1800)
                if configured is not None:
                    config['browser_call_timeout_seconds'] = configured
                result = prepare(config)
                registration = json.loads(Path(result['registration_path']).read_text())
                budget = registration['run_budget']
                self.assertEqual(budget['wall_seconds'], 1800)
                self.assertEqual(budget['deadline_ns'] - budget['started_ns'], 1800_000_000_000)
                self.assertEqual(result['plan']['time_limit_seconds'], 1800)
                tree = ast.parse((Path(result['workspace']) / 'browser.py').read_text())
                command = next(ast.literal_eval(node.value) for node in tree.body
                               if isinstance(node, ast.Assign)
                               and any(isinstance(target, ast.Name) and target.id == 'LEASE_COMMAND'
                                       for target in node.targets))
                self.assertEqual(float(command[command.index('--timeout-seconds') + 1]),
                                 1800 if configured is None else configured)
                self.assertEqual(int(command[command.index('--deadline-ns') + 1]), budget['deadline_ns'])
                self.assertEqual(registration['operation_lease']['browser_timeout_seconds'],
                                 1800 if configured is None else configured)
                for relative, digest in registration['files'].items():
                    self.assertEqual(hashlib.sha256((root / 'run' / relative).read_bytes()).hexdigest(), digest)

    def test_invalid_call_timeout_rejected_before_creating_run(self):
        for value in (None, True, False, 0, -1, float('inf'), float('nan'), '120'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                run = Path(directory) / 'invalid-run'
                with self.assertRaisesRegex(ValueError, 'browser_call_timeout_seconds'):
                    prepare(dict(run_dir=str(run), browser_call_timeout_seconds=value))
                self.assertFalse(run.exists())

    def test_fixture_path_is_rejected_before_creating_run(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / 'invalid-run'
            with self.assertRaisesRegex(ValueError, 'fixture must be a JSON object'):
                prepare({'run_dir':str(run), 'origin':'http://127.0.0.1:1',
                         'task':'Generic task', 'fixture':'/not/a/public/fixture/object.json'})
            self.assertFalse(run.exists())

    def test_continuation_freeze_wrapper_gateway_lifecycle(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<title>Generic construction fixture</title><main>Ready</main>'
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        scratch = Path('work/replica-pilot/construction-helper-tests')
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory, ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            root = Path(directory).resolve()
            threading.Thread(target=server.serve_forever, daemon=True).start()
            previous = root / 'previous'
            previous.mkdir()
            (previous / 'author-model.txt').write_text('Own earlier artifact')
            (previous / 'browser.py').write_text('STALE HELPER')
            (previous / 'TASK.md').write_text('STALE TASK')
            (previous / 'browser-requests').mkdir()
            (previous / 'browser-requests/old.json').write_text('{}')
            # This file is only a selector existence fixture. No credential is read.
            auth = root / 'dummy-auth-selector.json'
            auth.touch()
            result = prepare(dict(run_dir=str(root / 'new'), origin=f'http://127.0.0.1:{server.server_port}',
                task='Explore the supplied generic browser fixture.', fixture={'scope': 'generic'},
                auth_source=str(auth), from_previous_workspace=str(previous), same_author_continuation=True,
                time_limit_seconds=90, action_limit=5))
            workspace = Path(result['workspace'])
            private = Path(result['plan']['private'])
            registration = json.loads(Path(result['registration_path']).read_text())
            self.assertTrue(registration['same_author_continuation'])
            self.assertTrue(registration['isolation_limited'])
            self.assertFalse(registration['forced_learner_isolation'])
            self.assertTrue(registration['forced_browser_isolation'])
            self.assertFalse(registration['independent'])
            self.assertIsNone(registration['strict_scores'])
            self.assertEqual(registration['inherited_artifact_hashes'], {'author-model.txt': hashlib.sha256(b'Own earlier artifact').hexdigest()})
            self.assertFalse((workspace / 'browser-requests').exists())
            self.assertNotIn('STALE', (workspace / 'browser.py').read_text())
            self.assertEqual((workspace / 'TASK.md').read_text(), 'Explore the supplied generic browser fixture.')
            for relative, digest in registration['files'].items():
                self.assertEqual(hashlib.sha256((Path(result['plan']['run_dir']) / relative).read_bytes()).hexdigest(), digest)
            (workspace / 'probe.py').write_text('def run(h):\n h.expect({"disposition":"unknown"}, "Generic fixture navigation")\n h.page.goto(h.origin)\n return h.page.title()\n')
            command = [sys.executable, '-m', 'harness.replica.construction', 'serve-gateway', '--plan', result['plan_path'], '--interval', '.1']
            with (private / 'gateway-test.stdout').open('w') as out, (private / 'gateway-test.stderr').open('w') as err:
                child = subprocess.Popen(command, stdout=out, stderr=err)
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        health = private / 'gateway-health.json'
                        if health.exists() and json.loads(health.read_text())['state'] in {'ready', 'healthy'}:
                            break
                        self.assertIsNone(child.poll())
                        time.sleep(.05)
                    else:
                        self.fail('Gateway did not become ready')
                    browser = subprocess.run([sys.executable, str(workspace / 'browser.py'), '--script', 'probe.py'], capture_output=True, text=True, timeout=60)
                    self.assertEqual(browser.returncode, 0, browser.stderr)
                    response = json.loads(browser.stdout)
                    self.assertEqual(response['result']['return_value'], 'Generic construction fixture')
                    self.assertTrue(response['process_tree_clean'])
                    statuses = list((workspace / 'browser-requests').glob('*.status.json'))
                    self.assertEqual(len(statuses), 1)
                    status = json.loads(statuses[0].read_text())
                    self.assertEqual(status['state'], 'finished')
                    self.assertEqual(status['broker_status'], 'completed')
                    self.assertTrue(list((workspace / 'browser-requests').glob('*.stdout.txt')))
                finally:
                    child.send_signal(signal.SIGTERM)
                    child.wait(timeout=10)
            self.assertEqual(child.returncode, 0)
            self.assertEqual(json.loads((private / 'gateway-health.json').read_text())['reason'], 'signal:SIGTERM')
            self.assertFalse(Path(result['plan']['socket']).exists())
            (workspace / 'STOP').touch()
            self.assertEqual(serve_gateway(result['plan_path'])['reason'], 'STOP_present_before_start')
            (workspace / 'TASK.md').write_text('Changed frozen input')
            with self.assertRaisesRegex(ValueError, 'registered construction inputs changed'):
                serve_gateway(result['plan_path'])
            server.shutdown()

    def test_continuation_requires_explicit_provenance(self):
        with self.assertRaisesRegex(ValueError, 'exactly one explicit continuation provenance'):
            prepare(dict(task='Generic task', from_previous_workspace='unused'))


if __name__ == '__main__':
    unittest.main()
