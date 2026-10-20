"""Strict generic input validation. Target semantics belong to independent models."""
import json
from pathlib import Path
from urllib.parse import urlparse

OPS = {'eq', 'ne', 'contains', 'not_contains', 'gt', 'gte', 'lt', 'lte', 'matches', 'exists', 'in'}
ACTIONS = {'open', 'click', 'fill', 'select', 'check', 'uncheck', 'hover', 'focus', 'press', 'back', 'reload'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def repository_root():
    return Path(__file__).resolve().parent.parent


def local_path(root, value):
    path = (root / value).resolve()
    require(path.is_relative_to(root.resolve()), f'path escapes repository: {value}')
    return path


def canonical_cases(cases):
    return [{k: case[k] for k in ('id', 'goal', 'parameters')} for case in cases]


def validate_check(check):
    require(isinstance(check, dict), 'check must be object')
    require(isinstance(check.get('path'), str) and check['path'].startswith(('before.', 'after.')), 'invalid evidence path')
    require(check.get('op') in OPS, 'unsupported check operator')
    require(('value' in check) != ('value_from' in check), 'check needs exactly one value or value_from')
    if 'value_from' in check:
        require(isinstance(check['value_from'], str), 'value_from must be path')
    if check['op'] == 'exists':
        require(type(check.get('value')) is bool, 'exists requires boolean value')


def validate(site, bundle, cases):
    for key in ('site_id', 'base_url', 'adapter', 'source_roots', 'allowed_hosts'):
        require(key in site, f'site missing {key}')
    require(isinstance(site['source_roots'], list) and site['source_roots'], 'empty source_roots')
    require(isinstance(site['allowed_hosts'], list) and site['allowed_hosts'], 'empty allowed_hosts')
    require(all(host in ('localhost', '127.0.0.1', '::1') for host in site['allowed_hosts']), 'only loopback allowed')
    base = urlparse(site['base_url'])
    require(base.scheme in ('http', 'https') and base.hostname in site['allowed_hosts'], 'invalid base_url')
    require(bundle.get('schema_version') == 1, 'unsupported schema_version')
    require(bundle.get('site_id') == site['site_id'], 'site_id mismatch')
    require(isinstance(bundle.get('revision'), str) and bundle['revision'], 'missing revision')
    require(isinstance(bundle.get('model'), str) and bundle['model'], 'missing model')
    require(isinstance(bundle.get('rules'), list) and bundle['rules'], 'empty rules')
    rules = set()
    for rule in bundle['rules']:
        require(isinstance(rule, dict), 'rule must be object')
        require(isinstance(rule.get('id'), str) and rule['id'] not in rules, 'duplicate/missing rule id')
        rules.add(rule['id'])
        for key in ('statement', 'source_refs', 'preconditions', 'branches', 'forbidden_side_effects', 'status'):
            require(key in rule, f'rule missing {key}')
        require(isinstance(rule['source_refs'], list) and rule['source_refs'], 'rule requires source references')
    require(isinstance(cases, list) and cases, 'empty fixed cases')
    require(isinstance(bundle.get('cases'), list), 'missing bundle cases')
    require(canonical_cases(bundle['cases']) == canonical_cases(cases), 'case ids/order/goals/parameters differ from fixed cases')
    ids = [c['id'] for c in cases]
    require(len(ids) == len(set(ids)), 'duplicate fixed case ids')
    require(all(isinstance(c['parameters'], dict) and isinstance(c['goal'], str) for c in cases), 'invalid fixed case')
    require(isinstance(bundle.get('readouts', {}), dict), 'readouts must be object')
    for name, spec in bundle.get('readouts', {}).items():
        require(isinstance(spec, dict) and spec.get('kind') in ('text', 'value', 'count', 'visible', 'checked', 'attr'), f'invalid readout {name}')
        require(isinstance(spec.get('selector'), str) and spec['selector'] and '@e' not in spec['selector'], 'invalid readout selector')
        if spec['kind'] == 'attr':
            require(isinstance(spec.get('attribute'), str), 'attr requires attribute')
    total_steps = 0
    for case in bundle['cases']:
        require(isinstance(case.get('steps'), list) and case['steps'], 'case requires steps')
        step_ids = set()
        for step in case['steps']:
            total_steps += 1
            require(isinstance(step.get('id'), str) and step['id'] not in step_ids, 'duplicate/missing step id')
            step_ids.add(step['id'])
            require(isinstance(step.get('rule_ids'), list) and step['rule_ids'] and set(step['rule_ids']) <= rules, 'unknown/empty rule_ids')
            action = step.get('action', {})
            require(action.get('kind') in ACTIONS, 'unsupported action')
            kind = action['kind']
            if kind in {'click', 'fill', 'select', 'check', 'uncheck', 'hover', 'focus'}:
                require(isinstance(action.get('selector'), str) and action['selector'] and '@e' not in action['selector'], 'invalid selector')
            if kind in ('fill', 'select'):
                require('value' in action, 'action requires value')
            if kind == 'press':
                require(isinstance(action.get('key'), str), 'press requires key')
            if kind == 'open':
                require(isinstance(action.get('url'), str), 'open requires url')
                url = urlparse(action['url'])
                require((not url.scheme and not url.netloc) or (url.scheme in ('http', 'https') and url.hostname in site['allowed_hosts']), 'external navigation forbidden')
            wait = step.get('wait', {})
            require(wait.get('kind') in ('selector', 'text', 'url', 'load') and isinstance(wait.get('value'), str), 'explicit wait required')
            if wait['kind'] == 'load':
                require(wait['value'] in ('domcontentloaded', 'load', 'networkidle'), 'invalid load wait')
            require(isinstance(step.get('expect'), list) and step['expect'], 'prediction branches required')
            branch_ids = set()
            for branch in step['expect']:
                require(isinstance(branch.get('id'), str) and branch['id'] not in branch_ids, 'duplicate/missing branch id')
                branch_ids.add(branch['id'])
                require(isinstance(branch.get('checks'), list) and branch['checks'], 'branch checks required')
                for check in branch['checks']:
                    validate_check(check)
            require(isinstance(step.get('invariants', []), list), 'invariants must be list')
            for check in step.get('invariants', []):
                validate_check(check)
    require(total_steps <= 90, '90-step run budget exceeded')
    return {'cases': len(cases), 'steps': total_steps, 'rules': len(rules)}


def load_inputs(site_path, bundle_path, repo_root=None):
    root = Path(repo_root or repository_root()).resolve()
    site_path = Path(site_path).resolve()
    site, bundle = read_json(site_path), read_json(bundle_path)
    cases_path = local_path(root, site['cases']) if 'cases' in site else site_path.with_name('cases.json')
    raw = read_json(cases_path)
    cases = raw['cases'] if isinstance(raw, dict) else raw
    validate(site, bundle, cases)
    for path in [site['adapter'], *site['source_roots']]:
        require(local_path(root, path).exists(), f'missing source/adapter: {path}')
    return site, bundle, cases
