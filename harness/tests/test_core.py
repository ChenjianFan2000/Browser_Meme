import copy
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
import io
from unittest.mock import patch

from harness.artifacts import verify_frozen, write_json
from harness.checks import check_one, evaluate_step
from harness.contract import load_inputs
from harness.handoff import validate_repair
from harness.runner import compare_baseline, error_category, execute


class FakeAdapter:
    def __init__(self, fail_reset=False, fail_final=False):
        self.value = 0
        self.fail_reset = fail_reset
        self.fail_final = fail_final

    def reset(self, case):
        assert set(case) == {'id', 'goal', 'parameters'}
        if self.fail_reset:
            raise RuntimeError('reset unavailable')
        self.value = 0
        return {'reset': True}

    def observe(self):
        return {'value': self.value}

    def evaluate(self, case, before, after):
        assert set(case) == {'id', 'goal', 'parameters'}
        return [{'id': 'actual_backend', 'passed': after['backend']['value'] == 1 and not self.fail_final, 'detail': 'independent backend comparison'}]


class FakeBrowser:
    adapter = None
    events_path = None
    closed = 0
    sessions = []

    def __init__(self, site, session, **kwargs):
        self.session = session
        self.sessions.append(session)

    def start(self):
        pass

    def observe(self, readouts):
        return {'url': 'http://127.0.0.1/', 'title': 'Fake', 'text': 'ok', 'fields': {}, 'errors': {}}

    def act(self, action):
        # Read the durable event file while execution is still in progress.
        events = [json.loads(line) for line in self.events_path.read_text(encoding='utf-8').splitlines()]
        assert events[-1]['kind'] == 'action_dispatch'
        assert events[-2]['kind'] == 'prediction'
        self.adapter.value = 1

    def wait(self, spec):
        pass

    def screenshot(self, path):
        path.write_bytes(b'fake-test-image')

    def close(self):
        self.closed += 1


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'source').mkdir()
        (self.root / 'source' / 'app.py').write_text('# source fixture\n', encoding='utf-8')
        (self.root / 'adapter.py').write_text('# independently authored adapter fixture\n', encoding='utf-8')
        self.site = {'site_id': 'fixture', 'base_url': 'http://127.0.0.1:1234', 'source_roots': ['source'],
                     'adapter': 'adapter.py', 'allowed_hosts': ['127.0.0.1']}
        self.cases = [{'id': 'C1', 'goal': 'create one object', 'parameters': {}},
                      {'id': 'C2', 'goal': 'repeat from reset', 'parameters': {}}]
        rule = {'id': 'R1', 'statement': 'fixture rule', 'source_refs': ['source/app.py:1'],
                'preconditions': [], 'branches': ['success'], 'forbidden_side_effects': [], 'status': 'source_supported'}
        step = {'id': 'S1', 'rule_ids': ['R1'], 'action': {'kind': 'open', 'url': '/'},
                'wait': {'kind': 'load', 'value': 'load'},
                'expect': [{'id': 'success', 'checks': [{'path': 'after.backend.value', 'op': 'eq', 'value': 1}]}],
                'invariants': [{'path': 'before.backend.value', 'op': 'eq', 'value': 0}]}
        self.bundle = {'schema_version': 1, 'site_id': 'fixture', 'model': 'independent-test-double', 'revision': 'v001',
                       'rules': [rule], 'readouts': {}, 'cases': [{**c, 'steps': [copy.deepcopy(step)]} for c in self.cases]}
        write_json(self.root / 'site.json', self.site)
        write_json(self.root / 'bundle.json', self.bundle)
        write_json(self.root / 'cases.json', self.cases)
        FakeBrowser.sessions = []

    def tearDown(self):
        self.temporary.cleanup()

    def run_fixture(self, adapter=None):
        adapter = adapter or FakeAdapter()
        FakeBrowser.adapter = adapter
        FakeBrowser.events_path = self.root / 'run' / 'events.jsonl'
        return execute(self.root / 'site.json', self.root / 'bundle.json', self.root / 'run',
                       browser_factory=FakeBrowser, adapter=adapter, repo_root=self.root)

    def test_success_records_prediction_before_action_and_independent_truth(self):
        summary = self.run_fixture()
        self.assertEqual(summary['metrics']['passed_cases'], 2)
        self.assertEqual(summary['metrics']['step_denominator'], 2)
        self.assertEqual(len(set(FakeBrowser.sessions)), 2)
        self.assertTrue((self.root / 'run' / 'report.html').exists())
        self.assertTrue(summary['activation']['activation_allowed'])
        self.assertEqual(summary['measurement_status'], 'completed')
        self.assertEqual(summary['metrics']['ui_actions_completed'], 2)

    def test_reset_failure_preserves_full_denominators(self):
        summary = self.run_fixture(FakeAdapter(fail_reset=True))
        self.assertEqual(summary['metrics']['case_denominator'], 2)
        self.assertEqual(summary['metrics']['step_denominator'], 2)
        self.assertEqual(summary['metrics']['passed_cases'], 0)
        self.assertTrue(all(c['status'] == 'blocked' for c in summary['cases']))
        self.assertTrue(all(c['steps'][0]['status'] == 'not_run' for c in summary['cases']))
        self.assertFalse(summary['activation']['activation_allowed'])
        self.assertEqual(summary['measurement_status'], 'not_started')
        self.assertIsNone(summary['metrics']['case_success_rate'])
        self.assertIsNone(summary['metrics']['step_match_rate'])
        self.assertEqual(summary['metrics']['pipeline_completion_rate'], 0)
        self.assertIn('未开始目标网站测量', (self.root / 'run' / 'report.html').read_text(encoding='utf-8'))
        feedback = json.loads((self.root / 'run' / 'feedback.json').read_text(encoding='utf-8'))
        for failure in feedback['failures']:
            self.assertEqual(failure['category'], 'infrastructure')
            self.assertFalse(failure['model_repair_allowed'])
            self.assertTrue(failure['evidence'])
            self.assertTrue(all((self.root / 'run' / item).is_file() for item in failure['evidence']))

    def test_generated_checks_cannot_override_independent_failure(self):
        summary = self.run_fixture(FakeAdapter(fail_final=True))
        self.assertEqual(summary['metrics']['matched_steps'], 2)
        self.assertEqual(summary['metrics']['passed_cases'], 0)
        self.assertEqual(summary['cases'][0]['status'], 'independent_failure')
        self.assertFalse(summary['activation']['activation_allowed'])

    def test_infrastructure_prefix_preserved_and_startup_failure_blocked(self):
        self.assertEqual(error_category(RuntimeError('infrastructure: CDP target timeout')), 'infrastructure')
        class UnavailableBrowser(FakeBrowser):
            def start(self):
                raise RuntimeError('infrastructure: CDP target unavailable')
        adapter = FakeAdapter()
        summary = execute(self.root / 'site.json', self.root / 'bundle.json', self.root / 'run',
                          browser_factory=UnavailableBrowser, adapter=adapter, repo_root=self.root)
        self.assertFalse(summary['activation']['activation_allowed'])
        self.assertTrue(all(case['status'] == 'blocked' and case['category'] == 'infrastructure' for case in summary['cases']))
        self.assertEqual(summary['metrics']['step_denominator'], 2)
        self.assertEqual(summary['measurement_status'], 'not_started')
        self.assertEqual(summary['metrics']['ui_actions_dispatched'], 0)
        feedback = json.loads((self.root / 'run' / 'feedback.json').read_text(encoding='utf-8'))
        self.assertTrue(all((self.root / 'run' / item).is_file() for failure in feedback['failures'] for item in failure['evidence']))

    def test_no_regressions_cannot_activate_all_failed_repair(self):
        summary = self.run_fixture(FakeAdapter(fail_final=True))
        comparison = compare_baseline(copy.deepcopy(summary), summary)
        self.assertEqual(comparison['regressions'], [])
        self.assertFalse(comparison['activation_allowed'])

    def test_partial_measurement_keeps_original_denominators(self):
        class PartialBrowser(FakeBrowser):
            calls = 0

            def act(self, action):
                type(self).calls += 1
                if self.calls > 1:
                    raise RuntimeError('infrastructure: connection lost before action')
                super().act(action)

        adapter = FakeAdapter()
        PartialBrowser.adapter = adapter
        PartialBrowser.events_path = self.root / 'run' / 'events.jsonl'
        summary = execute(self.root / 'site.json', self.root / 'bundle.json', self.root / 'run',
                          browser_factory=PartialBrowser, adapter=adapter, repo_root=self.root)
        self.assertEqual(summary['measurement_status'], 'partial')
        self.assertEqual(summary['metrics']['case_denominator'], 2)
        self.assertEqual(summary['metrics']['step_denominator'], 2)
        self.assertEqual(summary['metrics']['ui_actions_dispatched'], 2)
        self.assertEqual(summary['metrics']['ui_actions_completed'], 1)
        self.assertEqual(summary['metrics']['pipeline_completion_rate'], 0.5)
        self.assertFalse(summary['activation']['activation_allowed'])

    def test_dispatched_but_uncompleted_actions_keep_partial_measurement(self):
        adapter = FakeAdapter()
        class FailedActionBrowser(FakeBrowser):
            def act(self, action):
                adapter.value = 1
                raise RuntimeError('infrastructure: CDP response lost after possible mutation')

        summary = execute(self.root / 'site.json', self.root / 'bundle.json', self.root / 'run',
                          browser_factory=FailedActionBrowser, adapter=adapter, repo_root=self.root)
        self.assertEqual(summary['metrics']['ui_actions_dispatched'], 2)
        self.assertEqual(summary['metrics']['ui_actions_completed'], 0)
        self.assertEqual(summary['measurement_status'], 'partial')
        self.assertEqual(summary['metrics']['case_success_rate'], 0)
        self.assertEqual(summary['metrics']['step_match_rate'], 0)
        self.assertEqual(summary['metrics']['case_denominator'], 2)
        self.assertEqual(summary['metrics']['step_denominator'], 2)
        self.assertTrue(all(case['independent_checks'][0]['passed'] for case in summary['cases']))
        self.assertFalse(any(case['passed'] for case in summary['cases']))

    def test_dispatched_locator_failure_is_error_not_preflight_blocker(self):
        class LocatorFailureBrowser(FakeBrowser):
            def act(self, action):
                raise RuntimeError('locator: expected exactly one target')

        summary = execute(self.root / 'site.json', self.root / 'bundle.json', self.root / 'run',
                          browser_factory=LocatorFailureBrowser, adapter=FakeAdapter(), repo_root=self.root)
        self.assertEqual(summary['measurement_status'], 'partial')
        self.assertTrue(all(case['status'] == 'error' and case['category'] == 'locator' for case in summary['cases']))
        self.assertEqual(summary['metrics']['ui_actions_completed'], 0)

    def test_inputs_are_copied_and_tamper_detected(self):
        self.run_fixture()
        self.assertEqual(verify_frozen(self.root / 'run', self.root, self.site), [])
        (self.root / 'run' / 'inputs' / 'bundle.json').write_text('{}', encoding='utf-8')
        self.assertIn('input changed: bundle.json', verify_frozen(self.root / 'run', self.root, self.site))

    def test_source_hashes_detect_content_mutation(self):
        self.run_fixture()
        (self.root / 'source' / 'app.py').write_text('# changed\n', encoding='utf-8')
        self.assertIn('source/adapter content changed', verify_frozen(self.root / 'run', self.root, self.site))

    def test_independent_adapter_hash_detects_evaluator_change(self):
        self.run_fixture()
        (self.root / 'adapter.py').write_text('# changed evaluator\n', encoding='utf-8')
        self.assertIn('source/adapter content changed', verify_frozen(self.root / 'run', self.root, self.site))

    def test_frozen_cases_tamper_is_detected(self):
        self.run_fixture()
        write_json(self.root / 'run' / 'inputs' / 'cases.json', [])
        self.assertIn('input changed: cases.json', verify_frozen(self.root / 'run', self.root, self.site))

    def test_fixed_goals_are_immutable(self):
        self.bundle['cases'][0]['goal'] = 'easier goal'
        write_json(self.root / 'bundle.json', self.bundle)
        with self.assertRaisesRegex(ValueError, 'fixed cases'):
            load_inputs(self.root / 'site.json', self.root / 'bundle.json', self.root)

    def test_typed_equality(self):
        self.assertEqual(check_one({'path': 'after.v', 'op': 'eq', 'value': True}, {'after': {'v': 1}})['status'], 'fail')
        self.assertEqual(check_one({'path': 'after.v', 'op': 'gt', 'value': 0}, {'after': {'v': True}})['status'], 'unknown')

    def test_missing_vs_contradiction_and_irrelevant_readout_error(self):
        step = copy.deepcopy(self.bundle['cases'][0]['steps'][0])
        self.assertEqual(evaluate_step(step, {'backend': {'value': 0}}, {'backend': {}})['status'], 'unconfirmed')
        self.assertEqual(evaluate_step(step, {'backend': {'value': 0}}, {'backend': {'value': 2}})['status'], 'contradiction')
        result = evaluate_step(step, {'backend': {'value': 0}}, {'backend': {'value': 1}, 'ui': {'errors': {'optional': 'missing'}}})
        self.assertEqual(result['status'], 'matched')

    def test_refusal_branch_matches_and_invariant_overrides(self):
        step = {'expect': [{'id': 'refused', 'checks': [{'path': 'after.ui.text', 'op': 'contains', 'value': 'denied'}]}],
                'invariants': [{'path': 'after.backend.value', 'op': 'eq', 'value_from': 'before.backend.value'}]}
        before = {'backend': {'value': 0}}
        after = {'backend': {'value': 0}, 'ui': {'text': 'denied'}}
        self.assertEqual(evaluate_step(step, before, after)['matched_branches'], ['refused'])
        after['backend']['value'] = 1
        self.assertEqual(evaluate_step(step, before, after)['status'], 'contradiction')

    def test_repair_deletion_and_undeclared_changes_rejected(self):
        candidate = copy.deepcopy(self.bundle)
        candidate['revision'] = 'v002'
        diagnosis = {'parent_revision': 'v001', 'category': 'business_rule', 'evidence': ['evidence/01.json'],
                     'changed_rules': [], 'changed_steps': ['S1'], 'rationale': 'independent evidence'}
        candidate['cases'][0]['steps'][0]['invariants'] = []
        with self.assertRaisesRegex(ValueError, 'removed invariant'):
            validate_repair(self.bundle, candidate, diagnosis)
        candidate = copy.deepcopy(self.bundle)
        candidate['revision'] = 'v002'
        candidate['cases'][0]['steps'][0]['action']['url'] = '/changed'
        diagnosis['changed_steps'] = []
        with self.assertRaisesRegex(ValueError, 'undeclared step'):
            validate_repair(self.bundle, candidate, diagnosis)

    def test_regression_blocks_activation(self):
        summary = self.run_fixture()
        candidate = copy.deepcopy(summary)
        candidate['cases'][0]['passed'] = False
        comparison = compare_baseline(candidate, summary)
        self.assertFalse(comparison['activation_allowed'])
        self.assertEqual(comparison['regressions'], ['C1'])

    def test_blocked_preflight_never_loads_adapter_or_executes_tasks(self):
        from harness.preflight import execute as preflight
        with patch('harness.runner.load_adapter', side_effect=AssertionError('must not load adapter')), \
             patch.object(FakeAdapter, 'reset', side_effect=AssertionError('must not reset')):
            result = preflight(self.root / 'site.json', self.root / 'bundle.json', self.root / 'preflight',
                               repo_root=self.root,
                               http_probe=lambda *a, **k: {'available': False, 'reachable': False, 'error': 'offline fixture'},
                               dependency_probe=lambda: True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['measurement_status'], 'not_started')
        self.assertFalse(result['model_repair_allowed'])
        self.assertFalse(result['business_reset_performed'])
        self.assertFalse(result['business_tasks_executed'])
        self.assertIsNone(result['case_success_rate'])
        self.assertEqual(result['fixed_denominators']['cases'], 2)
        self.assertEqual(result['fixed_denominators']['steps'], 2)
        self.assertTrue((self.root / 'preflight' / 'inputs' / 'bundle.json').is_file())
        self.assertTrue((self.root / 'preflight' / 'report.html').is_file())

    def test_preflight_never_overwrites_or_reprobes_existing_output(self):
        from harness.preflight import execute as preflight
        calls = []
        def probe(*args, **kwargs):
            calls.append(args)
            return {'available': False, 'reachable': False}
        arguments = (self.root / 'site.json', self.root / 'bundle.json', self.root / 'preflight')
        preflight(*arguments, repo_root=self.root, http_probe=probe, dependency_probe=lambda: True)
        original = (self.root / 'preflight' / 'preflight.json').read_bytes()
        count = len(calls)
        with self.assertRaises(FileExistsError):
            preflight(*arguments, repo_root=self.root, http_probe=probe, dependency_probe=lambda: True)
        self.assertEqual(len(calls), count)
        self.assertEqual((self.root / 'preflight' / 'preflight.json').read_bytes(), original)

    def test_browser_discovery_does_not_imply_verified_capability(self):
        from harness.preflight import execute as preflight
        with patch('harness.preflight.run_smoke', side_effect=AssertionError('no implicit launch')):
            result = preflight(self.root / 'site.json', self.root / 'bundle.json', self.root / 'preflight',
                               repo_root=self.root, launch_browser=True,
                               http_probe=lambda *a, **k: {'available': True, 'reachable': True},
                               browser_discovery=lambda: 'C:/fixture/chrome.exe', dependency_probe=lambda: True)
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['browser_smoke']['status'], 'unverified')
        self.assertFalse(result['checks']['browser_selection']['launch_verified'])
        self.assertFalse(result['ready_for_measurement'])

    def test_cli_browser_selection_and_run_exit_codes(self):
        from harness.__main__ import main
        success = {'measurement_status': 'completed', 'metrics': {'passed_cases': 2, 'case_denominator': 2},
                   'activation': {'activation_allowed': True}}
        base = ['run', '--site', 'site.json', '--bundle', 'bundle.json', '--out', 'run']
        for options, expected_cdp in [([], 'http://127.0.0.1:9337'), (['--cdp', 'http://127.0.0.1:9999'], 'http://127.0.0.1:9999'), (['--launch-browser'], None)]:
            with patch('harness.runner.execute', return_value=success) as run, redirect_stdout(io.StringIO()):
                self.assertEqual(main(base + options), 0)
                self.assertEqual(run.call_args.kwargs['cdp_url'], expected_cdp)
        blocked = copy.deepcopy(success)
        blocked['measurement_status'] = 'not_started'
        blocked['activation']['activation_allowed'] = False
        with patch('harness.runner.execute', return_value=blocked), redirect_stdout(io.StringIO()):
            self.assertEqual(main(base), 1)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as context:
            main(base + ['--cdp', 'http://127.0.0.1:9337', '--launch-browser'])
        self.assertEqual(context.exception.code, 2)

    def test_preflight_cli_defaults_to_no_real_smoke(self):
        from harness.__main__ import main
        with patch('harness.preflight.execute', return_value={'ready_for_measurement': False}) as probe, redirect_stdout(io.StringIO()):
            self.assertEqual(main(['preflight', '--site', 'site.json', '--bundle', 'bundle.json', '--out', 'new']), 1)
        self.assertFalse(probe.call_args.kwargs['launch_browser'])
        self.assertFalse(probe.call_args.kwargs['smoke'])
        self.assertEqual(probe.call_args.kwargs['cdp_url'], 'http://127.0.0.1:9337')

    def test_explicit_preflight_smoke_only_verifies_transport_and_never_scores_tasks(self):
        from harness.preflight import execute as preflight
        calls = []
        def fake_smoke(out, cdp):
            calls.append((out, cdp))
            return {'status': 'passed', 'returncode': 0}
        result = preflight(self.root / 'site.json', self.root / 'bundle.json', self.root / 'preflight',
                           repo_root=self.root, launch_browser=True, smoke=True,
                           http_probe=lambda *a, **k: {'available': True, 'reachable': True},
                           browser_discovery=lambda: 'C:/fixture/chrome.exe', dependency_probe=lambda: True,
                           smoke_probe=fake_smoke)
        self.assertTrue(result['ready_for_measurement'])
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(calls[0][1], None)
        self.assertEqual(result['measurement_status'], 'not_started')
        self.assertIsNone(result['case_success_rate'])
        self.assertFalse(result['business_tasks_executed'])

    def test_step_regression_blocks_activation_even_for_previously_failed_case(self):
        summary = self.run_fixture(FakeAdapter(fail_final=True))
        candidate = copy.deepcopy(summary)
        candidate['cases'][0]['steps'][0]['status'] = 'unconfirmed'
        comparison = compare_baseline(candidate, summary)
        self.assertFalse(comparison['activation_allowed'])
        self.assertEqual(comparison['step_regressions'], ['C1/S1'])


if __name__ == '__main__':
    unittest.main()
