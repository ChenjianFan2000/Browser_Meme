"""Generic UI execution and independently evaluated outcomes."""
import importlib.util
from collections import Counter
import time
import uuid
from pathlib import Path

from .artifacts import Recorder, freeze, verify_frozen, write_json
from .checks import evaluate_step
from .contract import canonical_cases, load_inputs, local_path, read_json, repository_root, require
from .report import produce


def load_adapter(path):
    spec = importlib.util.spec_from_file_location('harness_trusted_adapter_' + uuid.uuid4().hex, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('reset', 'observe', 'evaluate'):
        require(callable(getattr(module, name, None)), f'adapter missing {name}')
    return module


def error_category(error):
    text = str(error).lower()
    prefix = text.split(':', 1)[0].strip()
    if prefix in ('infrastructure', 'locator', 'timing', 'implementation', 'business_rule', 'unconfirmed'):
        return prefix
    if 'locator' in text or 'target' in text or 'selector' in text:
        return 'locator'
    if 'timeout' in text or 'timing' in text:
        return 'timing'
    return 'implementation'


def compare_baseline(summary, baseline):
    require(summary['fixed_cases'] == baseline['fixed_cases'], 'baseline case set/order/goals changed')
    require(summary['site_id'] == baseline['site_id'], 'baseline site mismatch')
    require(summary['source_hashes'] == baseline['source_hashes'], 'baseline sources/evaluator changed')
    previous = {case['id']: case for case in baseline['cases']}
    regressions = [case['id'] for case in summary['cases'] if previous[case['id']]['passed'] and not case['passed']]
    step_regressions = []
    for case in summary['cases']:
        current_steps = {step['id']: step for step in case['steps']}
        for old_step in previous[case['id']]['steps']:
            if old_step['status'] == 'matched' and current_steps.get(old_step['id'], {}).get('status') != 'matched':
                step_regressions.append(f'{case["id"]}/{old_step["id"]}')
    accepted = bool(summary['cases']) and all(case['passed'] for case in summary['cases']) and not summary.get('integrity_errors')
    return {'regressions': regressions, 'step_regressions': step_regressions,
            'acceptance_criterion': 'all fixed cases independently pass with intact evidence',
            'activation_allowed': accepted and not regressions and not step_regressions}


def execute(site_path, bundle_path, out, cdp_url=None, baseline_summary=None,
            browser_factory=None, adapter=None, repo_root=None, diagnosis_path=None):
    root = Path(repo_root or repository_root()).resolve()
    site, bundle, fixed_cases = load_inputs(site_path, bundle_path, root)
    baseline = read_json(baseline_summary) if baseline_summary else None
    if baseline:
        require(baseline.get('repair_round', 0) < 2, 'maximum two repair rounds reached')
        require(canonical_cases(fixed_cases) == baseline['fixed_cases'], 'repair changed frozen cases')
        require(bundle['revision'] != baseline['revision'], 'repair must have new revision')
        from .handoff import validate_repair
        require(diagnosis_path is not None, 'repair requires --diagnosis PATH (or sibling diagnosis.json via CLI)')
        parent = read_json(Path(baseline_summary).resolve().parent / 'inputs' / 'bundle.json')
        validate_repair(parent, bundle, read_json(diagnosis_path))
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'evidence').mkdir()
    manifest = freeze(Path(site_path), Path(bundle_path), site, fixed_cases, out, root)
    if baseline:
        require(manifest['sources'] == baseline['source_hashes'], 'repair changed source/evaluator')
    adapter_load_error = None
    if adapter is None:
        try:
            adapter = load_adapter(local_path(root, site['adapter']))
        except Exception as exc:
            adapter_load_error = exc
    browser_load_error = None
    if browser_factory is None:
        try:
            from .browser import Browser
            browser_factory = Browser
        except Exception as exc:
            browser_load_error = exc
    recorder = Recorder(out / 'events.jsonl')
    started = time.monotonic()
    summary = {'run_id': out.name, 'site_id': site['site_id'], 'revision': bundle['revision'],
               'model': bundle['model'], 'repair_round': baseline.get('repair_round', 0) + 1 if baseline else 0,
               'fixed_cases': canonical_cases(fixed_cases), 'source_hashes': manifest['sources'], 'cases': [],
               'limits': {'steps': 90, 'command_seconds': 30, 'run_seconds': 1200},
               'model_tokens': None, 'model_cost': None}
    summary['traceability'] = [{'case': case['id'], 'step': step['id'], 'rule_ids': step['rule_ids'],
                               'branches': {branch['id']: branch['checks'] for branch in step['expect']},
                               'invariants': step.get('invariants', [])}
                              for case in bundle['cases'] for step in case['steps']]
    feedback = []
    try:
        recorder.emit('run_start', revision=bundle['revision'], fixed_cases=summary['fixed_cases'])
        for index, case in enumerate(bundle['cases']):
            safe_case = canonical_cases([case])[0]
            result = {'id': case['id'], 'status': 'not_run', 'passed': False, 'steps': [], 'independent_checks': []}
            summary['cases'].append(result)
            prefix = f'{index + 1:02d}'
            browser = None
            before = after = None
            phase = 'setup'
            actions_completed = 0
            actions_dispatched = 0
            if time.monotonic() - started >= 1200:
                result.update(error='overall timeout; case retained in denominator', category='infrastructure')
            else:
                try:
                    if adapter_load_error:
                        raise RuntimeError(f'infrastructure: adapter import failed: {adapter_load_error}')
                    if browser_load_error:
                        raise RuntimeError(f'infrastructure: browser import failed: {browser_load_error}')
                    recorder.emit('reset_start', case=case['id'])
                    result['setup'] = adapter.reset(safe_case)
                    recorder.emit('reset_complete', case=case['id'], setup=result['setup'])
                    phase = 'browser_start'
                    browser = browser_factory(site, session='harness-' + uuid.uuid4().hex, timeout=30,
                                              cdp_url=cdp_url, event_sink=lambda event: recorder.emit('browser', case=case['id'], event=event))
                    browser.start()
                    phase = 'initial_observation'
                    before = {'ui': browser.observe(bundle.get('readouts', {})), 'backend': adapter.observe()}
                    write_json(out / 'evidence' / f'{prefix}-initial.json', before)
                    current = before
                    result['status'] = 'completed'
                    for step_index, step in enumerate(case['steps']):
                        phase = 'step'
                        if time.monotonic() - started >= 1200:
                            raise TimeoutError('overall run timeout')
                        evidence_name = f'{prefix}-{step_index + 1:02d}'
                        # emit() flushes AND fsyncs before action dispatch.
                        recorder.emit('prediction', case=case['id'], step=step['id'], action=step['action'],
                                      rule_ids=step['rule_ids'], expect=step['expect'], invariants=step.get('invariants', []), before=current)
                        step_result = {'id': step['id'], 'status': 'error'}
                        result['steps'].append(step_result)
                        actions_dispatched += 1
                        recorder.emit('action_dispatch', case=case['id'], step=step['id'], action=step['action'])
                        browser.act(step['action'])
                        actions_completed += 1
                        recorder.emit('action_complete', case=case['id'], step=step['id'])
                        browser.wait(step['wait'])
                        actual = {'ui': browser.observe(bundle.get('readouts', {})), 'backend': adapter.observe()}
                        evidence_path = f'evidence/{evidence_name}.json'
                        write_json(out / evidence_path, {'before': current, 'after': actual})
                        step_result['evidence'] = evidence_path
                        try:
                            image = out / 'evidence' / f'{evidence_name}.png'
                            browser.screenshot(image)
                            step_result['screenshot'] = image.relative_to(out).as_posix()
                        except Exception as exc:
                            step_result['screenshot_error'] = str(exc)
                        step_result.update(evaluate_step(step, current, actual))
                        recorder.emit('step_result', case=case['id'], step=step['id'], result=step_result)
                        current = actual
                        if step_result['status'] != 'matched':
                            result['status'] = step_result['status']
                            break
                    phase = 'final_evaluation'
                    after = {'ui': browser.observe(bundle.get('readouts', {})), 'backend': adapter.observe()}
                    write_json(out / 'evidence' / f'{prefix}-final.json', after)
                    independent = adapter.evaluate(safe_case, before, after)
                    require(isinstance(independent, list) and independent, 'independent evaluator returned no checks')
                    require(all(isinstance(c, dict) and isinstance(c.get('id'), str) and type(c.get('passed')) is bool for c in independent), 'invalid independent evaluator checks')
                    result['independent_checks'] = independent
                    result['passed'] = result['status'] == 'completed' and all(c['passed'] for c in independent)
                    if result['status'] == 'completed' and not result['passed']:
                        result['status'] = 'independent_failure'
                    recorder.emit('independent_evaluation', case=case['id'], checks=independent, passed=result['passed'])
                except Exception as exc:
                    category = 'infrastructure' if phase in ('setup', 'browser_start') else error_category(exc)
                    result.update(status='blocked' if actions_dispatched == 0 or category == 'infrastructure' else 'error',
                                  error=str(exc), category=category, phase=phase, passed=False)
                    recorder.emit('case_error', case=case['id'], error=str(exc), category=category, phase=phase)
                    write_json(out / 'evidence' / f'{prefix}-error.json',
                               {'case': case['id'], 'error': str(exc), 'category': category, 'phase': phase,
                                'actions_completed': actions_completed})
                    # A timed-out UI action may still have changed real state. Preserve
                    # independent final evidence without turning an execution error into success.
                    if browser is not None:
                        final = {}
                        capture_errors = {}
                        for key, observe in (('ui', lambda: browser.observe(bundle.get('readouts', {}))),
                                             ('backend', adapter.observe)):
                            try:
                                final[key] = observe()
                            except Exception as capture_error:
                                capture_errors[key] = str(capture_error)
                        write_json(out / 'evidence' / f'{prefix}-final.json', {'observation': final, 'capture_errors': capture_errors})
                        try:
                            browser.screenshot(out / 'evidence' / f'{prefix}-failure.png')
                        except Exception as capture_error:
                            capture_errors['screenshot'] = str(capture_error)
                        if before is not None and not capture_errors.get('backend') and not capture_errors.get('ui'):
                            try:
                                result['independent_checks'] = adapter.evaluate(safe_case, before, final)
                            except Exception as evaluation_error:
                                result['evaluation_error'] = str(evaluation_error)
                        recorder.emit('failure_observation', case=case['id'], final=final, errors=capture_errors,
                                      independent_checks=result['independent_checks'])
                finally:
                    if browser is not None:
                        try:
                            browser.close()
                        except Exception as exc:
                            category = result.get('category', error_category(exc))
                            result.update(status='blocked' if actions_dispatched == 0 or category == 'infrastructure' else 'error',
                                          category=category, passed=False, close_error=str(exc))
                            recorder.emit('close_error', case=case['id'], error=str(exc))
            result['ui_actions_dispatched'] = actions_dispatched
            result['ui_actions_completed'] = actions_completed
            attempted = {s['id'] for s in result['steps']}
            result['steps'].extend({'id': s['id'], 'status': 'not_run'} for s in case['steps'] if s['id'] not in attempted)
            if not result['passed']:
                category = result.get('category', 'business_rule' if result['status'] in ('contradiction', 'independent_failure') else 'unconfirmed')
                evidence_paths = [s['evidence'] for s in result['steps'] if 'evidence' in s]
                evidence_paths.extend(f'evidence/{prefix}-{suffix}.json' for suffix in ('initial', 'final', 'error'))
                evidence_paths.append('events.jsonl')
                feedback.append({'case': case['id'], 'category': category, 'status': result['status'], 'error': result.get('error'),
                                 'model_repair_allowed': category != 'infrastructure',
                                 'repair_owner': 'infrastructure' if category == 'infrastructure' else 'independent_model',
                                 'evidence': [path for path in evidence_paths if (out / path).is_file()]})
        integrity_errors = verify_frozen(out, root, site)
        summary['integrity_errors'] = integrity_errors
        if integrity_errors:
            for result in summary['cases']:
                result.update(passed=False, status='integrity_failure')
        total_steps = sum(len(c['steps']) for c in summary['cases'])
        matched_steps = sum(s['status'] == 'matched' for c in summary['cases'] for s in c['steps'])
        dispatched_actions = sum(case['ui_actions_dispatched'] for case in summary['cases'])
        completed_actions = sum(case['ui_actions_completed'] for case in summary['cases'])
        summary['measurement_status'] = ('not_started' if dispatched_actions == 0 else
                                         'completed' if completed_actions == total_steps else 'partial')
        summary['measurement_note'] = {
            'not_started': '未开始目标网站测量；阻塞记录属于基础设施管线结果，不能解释为模型成功率。',
            'partial': '已派发目标网站 UI 动作，测量部分完成；派发不保证动作已实际生效，固定分母包含失败、阻塞与未执行项。',
            'completed': '计划的全部 UI 动作完成；任务成功仍以独立评价及预测检查为准。',
        }[summary['measurement_status']]
        summary['metrics'] = {'case_denominator': len(fixed_cases), 'passed_cases': sum(c['passed'] for c in summary['cases']),
                              'step_denominator': total_steps, 'matched_steps': matched_steps,
                              'ui_actions_dispatched': dispatched_actions, 'ui_actions_completed': completed_actions,
                              'pipeline_completion_rate': completed_actions / total_steps,
                              'case_success_rate': sum(c['passed'] for c in summary['cases']) / len(fixed_cases) if dispatched_actions else None,
                              'step_match_rate': matched_steps / total_steps if dispatched_actions else None,
                              'elapsed_seconds': time.monotonic() - started}
        summary['metrics']['case_status_counts'] = dict(Counter(case['status'] for case in summary['cases']))
        summary['metrics']['step_status_counts'] = dict(Counter(step['status'] for case in summary['cases'] for step in case['steps']))
        summary['activation'] = compare_baseline(summary, baseline) if baseline else {
            'activation_allowed': not integrity_errors and all(case['passed'] for case in summary['cases']),
            'acceptance_criterion': 'all fixed cases independently pass with intact evidence', 'regressions': []}
        if integrity_errors:
            summary['activation']['activation_allowed'] = False
        write_json(out / 'feedback.json', {'revision': bundle['revision'], 'repair_round': summary['repair_round'], 'failures': feedback,
                                         'integrity_errors': integrity_errors,
                                         'instructions': 'Infrastructure failures require infrastructure repair before any target-model repair. '
                                         'Independent model may diagnose only eligible target failures using persisted evidence. Never edit this run.'})
        recorder.emit('run_complete', metrics=summary['metrics'], activation=summary['activation'])
        produce(summary, out)
    finally:
        recorder.close()
    return summary
