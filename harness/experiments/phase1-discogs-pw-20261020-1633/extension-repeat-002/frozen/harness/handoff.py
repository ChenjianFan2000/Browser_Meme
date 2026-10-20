"""Reviewable file transport for independent Codex subagent model work."""
from pathlib import Path

from .artifacts import digest, write_json
from .contract import canonical_cases, load_inputs, read_json, require


def validate_repair(parent, candidate, diagnosis):
    require(parent['revision'] != candidate['revision'], 'repair revision must change')
    require(canonical_cases(parent['cases']) == canonical_cases(candidate['cases']), 'repair changed cases')
    require(diagnosis.get('parent_revision') == parent['revision'], 'diagnosis parent mismatch')
    require(diagnosis.get('category') in ('locator', 'timing', 'implementation', 'business_rule', 'unconfirmed'), 'invalid diagnosis category')
    for key in ('evidence', 'changed_rules', 'changed_steps', 'rationale'):
        require(bool(diagnosis.get(key)) or key in ('changed_rules', 'changed_steps'), f'diagnosis missing {key}')
    changed_rules = set(diagnosis['changed_rules'])
    changed_steps = set(diagnosis['changed_steps'])
    old_rules = {r['id']: r for r in parent['rules']}
    new_rules = {r['id']: r for r in candidate['rules']}
    require(old_rules.keys() <= new_rules.keys(), 'repair cannot delete rules')
    for rid, old in old_rules.items():
        if old != new_rules[rid]:
            require(rid in changed_rules, f'undeclared rule change {rid}')
            require(diagnosis['category'] == 'business_rule', 'rule revisions require business counterexample diagnosis')
    for old_case, new_case in zip(parent['cases'], candidate['cases']):
        new_steps = {s['id']: s for s in new_case['steps']}
        for old_step in old_case['steps']:
            sid = old_step['id']
            require(sid in new_steps, f'repair deleted step {sid}')
            new_step = new_steps[sid]
            if old_step != new_step:
                require(sid in changed_steps or f'{old_case["id"]}/{sid}' in changed_steps, f'undeclared step change {sid}')
            require(set(old_step['rule_ids']) <= set(new_step['rule_ids']), 'repair removed rule links')
            # Predicate replacements need declared business evidence; constraint deletion is always blocked.
            require(len(new_step.get('invariants', [])) >= len(old_step.get('invariants', [])), 'repair removed invariant checks')
            old_branches = {b['id']: b for b in old_step['expect']}
            new_branches = {b['id']: b for b in new_step['expect']}
            require(old_branches.keys() == new_branches.keys(), 'repair changed expected branch set')
            for bid, branch in old_branches.items():
                require(len(new_branches[bid]['checks']) >= len(branch['checks']), 'repair removed branch checks')
            if old_step.get('invariants', []) != new_step.get('invariants', []) or old_step['expect'] != new_step['expect']:
                require(diagnosis['category'] == 'business_rule', 'changed predictions require business counterexample diagnosis')
    return {'validated': True, 'note': 'Regression execution still required before activation.'}


def request(site_path, out, baseline_summary=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    packet = {'transport': 'independent Codex collaboration subagent', 'site': str(Path(site_path).resolve()),
              'contract': str(Path(__file__).with_name('CONTRACT.md').resolve()), 'phase': 'initial_generation',
              'expected_outputs': ['bundle.json'], 'tokens': None, 'cost': None,
              'instructions': 'Use target source and public adapter contract; author complete bundle independently. Coordinator must not author target rules.'}
    if baseline_summary:
        summary_path = Path(baseline_summary).resolve()
        summary = read_json(summary_path)
        require(summary.get('repair_round', 0) < 2, 'two-repair limit reached')
        packet.update(phase='repair', parent_revision=summary['revision'], repair_round=summary.get('repair_round', 0) + 1,
                      baseline_summary=str(summary_path), feedback=str(summary_path.with_name('feedback.json')),
                      expected_outputs=['bundle.json', 'diagnosis.json'])
    write_json(out / 'request.json', packet)
    return packet


def accept(site_path, bundle_path, out, baseline_summary=None, diagnosis_path=None):
    site, bundle, cases = load_inputs(site_path, bundle_path)
    result = {'site_id': site['site_id'], 'revision': bundle['revision'], 'bundle_sha256': digest(bundle_path),
              'fixed_cases': canonical_cases(cases), 'status': 'validated_pending_execution'}
    if baseline_summary:
        baseline = read_json(baseline_summary)
        require(baseline.get('repair_round', 0) < 2, 'two-repair limit reached')
        require(diagnosis_path is not None, 'repair requires diagnosis.json')
        parent = read_json(Path(baseline_summary).resolve().parent / 'inputs' / 'bundle.json')
        result['repair'] = validate_repair(parent, bundle, read_json(diagnosis_path))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    require(not out.exists(), 'acceptance output exists')
    write_json(out, result)
    return result
