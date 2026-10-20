"""Lifecycle unit checks with fake processes; these are not real UI acceptance."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from harness import launch
from harness.artifacts import write_json


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.site_path = self.root / 'site.json'
        self.bundle_path = self.root / 'bundle.json'
        self.out = self.root / 'run'
        (self.root / 'source.py').write_text('# frozen source\n', encoding='utf-8')
        (self.root / 'adapter.py').write_text('# frozen independent adapter\n', encoding='utf-8')
        self.site = {'site_id': 'fixture', 'base_url': 'http://127.0.0.1:1234', 'source_roots': ['source.py'],
                     'adapter': 'adapter.py', 'allowed_hosts': ['127.0.0.1'], 'working_directory': '.',
                     'setup_argv': ['python', '-m', 'trusted_fixture', 'setup'],
                     'start_argv': ['python', '-m', 'trusted_fixture', 'start']}
        case = {'id': 'C1', 'goal': 'independent fixture goal', 'parameters': {}}
        bundle = {'schema_version': 1, 'site_id': 'fixture', 'model': 'test-double', 'revision': 'v001',
                  'rules': [{'id': 'R1', 'statement': 'fixture', 'source_refs': ['source.py:1'], 'preconditions': [],
                             'branches': ['success'], 'forbidden_side_effects': [], 'status': 'source_supported'}],
                  'readouts': {}, 'cases': [{**case, 'steps': [{'id': 'S1', 'rule_ids': ['R1'],
                      'action': {'kind': 'open', 'url': '/'}, 'wait': {'kind': 'load', 'value': 'load'},
                      'expect': [{'id': 'success', 'checks': [{'path': 'after.ui.title', 'op': 'eq', 'value': 'fixture'}]}]}]}]}
        write_json(self.site_path, self.site)
        write_json(self.bundle_path, bundle)
        write_json(self.root / 'cases.json', [case])
        self.stack = ExitStack()
        self.stack.enter_context(patch('harness.launch.repository_root', return_value=self.root))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.spawn = self.stack.enter_context(patch('harness.launch.spawn'))
        self.preflight = self.stack.enter_context(patch('harness.launch.preflight', return_value={'ready_for_measurement': False}))
        self.run = self.stack.enter_context(patch('harness.launch.run_experiment'))
        self.stack.enter_context(patch('harness.launch.wait_ready', return_value={'fixture': {'available': True}}))
        self.stop = self.stack.enter_context(patch('harness.launch.stop_owned', return_value={'status': 'cooperative'}))

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def process(self, pid, code):
        process = Mock(pid=pid, returncode=code)
        process.wait.return_value = code
        process.poll.return_value = code
        return process

    def execute(self, **options):
        return launch.execute(self.site_path, self.bundle_path, self.out, **options)

    def test_setup_failure_cannot_start_service_preflight_or_experiment(self):
        setup = self.process(101, 7)
        self.spawn.return_value = setup
        state = self.execute()
        self.assertEqual(self.spawn.call_count, 1)
        self.preflight.assert_not_called()
        self.run.assert_not_called()
        self.assertEqual(state['failure_stage'], 'setup')
        self.assertEqual(state['measurement_status'], 'not_started')
        self.assertFalse(state['model_called'])
        self.assertIsNone(state['case_success_rate'])
        self.assertTrue((self.out / 'report.html').is_file())
        self.assertEqual(state['cleanup'][0]['pid'], setup.pid)

    def test_failed_preflight_stops_owned_service_and_never_runs_experiment(self):
        setup, service = self.process(101, 0), self.process(102, None)
        self.spawn.side_effect = [setup, service]
        state = self.execute()
        self.preflight.assert_called_once()
        self.assertTrue(self.preflight.call_args.kwargs['smoke'])
        self.assertTrue(self.preflight.call_args.kwargs['launch_browser'])
        self.run.assert_not_called()
        self.assertEqual(state['failure_stage'], 'browser_preflight')
        self.assertEqual(self.stop.call_args_list[0].args, (service, self.out / 'stop-service'))
        self.assertEqual([entry['pid'] for entry in state['cleanup']], [102, 101])
        self.assertEqual(state['measurement_status'], 'not_started')

    def test_existing_output_is_never_overwritten(self):
        self.out.mkdir()
        sentinel = self.out / 'launch.json'
        sentinel.write_text('immutable previous result', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.execute()
        self.spawn.assert_not_called()
        self.preflight.assert_not_called()
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'immutable previous result')

    def test_working_and_output_paths_cannot_escape_workspace(self):
        self.site['working_directory'] = '..'
        write_json(self.site_path, self.site)
        with self.assertRaisesRegex(ValueError, 'escapes repository'):
            self.execute()
        self.spawn.assert_not_called()
        self.site['working_directory'] = '.'
        write_json(self.site_path, self.site)
        with self.assertRaisesRegex(ValueError, 'out path escapes workspace'):
            launch.execute(self.site_path, self.bundle_path, self.root.parent / 'outside-launch')
        self.spawn.assert_not_called()

    def test_process_argv_is_a_literal_array_and_shell_is_disabled(self):
        command = launch.command_argv({'start_argv': ['python', '-m', 'trusted_fixture', 'literal & text']}, 'start_argv')
        self.assertEqual(command[0], sys.executable)
        # Test the actual spawn helper, while suppressing process creation.
        with patch('harness.launch.subprocess.Popen') as popen:
            self.original_spawn(command, self.root, self.root / 'argv.log', {})
        self.assertEqual(popen.call_args.args[0], command)
        self.assertFalse(popen.call_args.kwargs['shell'])
        self.assertEqual(popen.call_args.kwargs['cwd'], self.root)

    def test_partial_execution_exception_recovers_durable_action_evidence(self):
        self.spawn.side_effect = [self.process(101, 0), self.process(102, None)]
        self.preflight.return_value = {'ready_for_measurement': True}
        def interrupted(*args, **kwargs):
            directory = args[2]
            directory.mkdir()
            (directory / 'events.jsonl').write_text(json.dumps({'kind': 'action_dispatch'}) + '\n{partial', encoding='utf-8')
            raise RuntimeError('report generation interrupted')
        self.run.side_effect = interrupted
        state = self.execute()
        self.assertEqual(state['measurement_status'], 'partial')
        self.assertEqual(state['ui_actions_dispatched'], 1)
        self.assertEqual(state['ui_actions_completed'], 0)
        self.assertEqual(state['malformed_event_lines'], 1)
        self.assertIsNone(state['case_success_rate'])
        self.assertTrue((self.out / 'report.html').is_file())
        self.assertEqual(len(state['cleanup']), 2)

    def test_integrity_check_exception_preserves_cleanup_and_report(self):
        self.spawn.return_value = self.process(101, 7)
        with patch('harness.launch.verify_frozen', side_effect=FileNotFoundError('frozen source missing')):
            state = self.execute()
        self.assertEqual(state['status'], 'integrity_failure')
        self.assertIn('unavailable', state['integrity_errors'][0])
        self.assertEqual(len(state['cleanup']), 1)
        self.assertTrue((self.out / 'launch.json').is_file())
        self.assertTrue((self.out / 'report.html').is_file())

    def test_setup_cannot_change_original_model_input_before_starting_service(self):
        setup = self.process(101, 0)
        def mutate_bundle(**kwargs):
            self.bundle_path.write_text('{}', encoding='utf-8')
            return 0
        setup.wait.side_effect = mutate_bundle
        self.spawn.return_value = setup
        state = self.execute()
        self.assertEqual(state['status'], 'integrity_failure')
        self.assertEqual(self.spawn.call_count, 1)
        self.preflight.assert_not_called()
        self.run.assert_not_called()
        self.assertTrue(any('original launch input changed: bundle.json' in error for error in state['integrity_errors']))
        self.assertEqual(len(state['cleanup']), 1)

    def test_cleanup_failure_is_reported_and_remaining_owned_processes_are_attempted(self):
        self.spawn.side_effect = [self.process(101, 0), self.process(102, None)]
        self.stop.side_effect = [RuntimeError('owned process cleanup failed'), {'status': 'already_stopped'}]
        state = self.execute()
        self.assertEqual(state['status'], 'cleanup_failed')
        self.assertEqual(len(state['cleanup']), 2)
        self.assertEqual(state['cleanup'][0]['status'], 'failed')
        self.assertEqual(state['cleanup'][1]['status'], 'already_stopped')
        self.assertTrue((self.out / 'report.html').is_file())


LaunchTests.original_spawn = staticmethod(launch.spawn)


if __name__ == '__main__':
    unittest.main()
