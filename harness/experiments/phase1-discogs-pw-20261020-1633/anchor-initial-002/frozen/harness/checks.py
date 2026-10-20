"""Typed, three-valued checks over raw observation dictionaries."""
import re


class MissingEvidence(Exception):
    pass


def resolve(data, path):
    value = data
    try:
        for part in path.split('.'):
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (KeyError, IndexError, TypeError, ValueError):
        raise MissingEvidence(path) from None
    # A readout with an error is missing evidence, even when its value is null.
    parts = path.split('.')
    if len(parts) >= 4 and parts[1:3] == ['ui', 'fields']:
        errors = data.get(parts[0], {}).get('ui', {}).get('errors', {})
        if isinstance(errors, dict) and parts[3] in errors:
            raise MissingEvidence(path)
        if isinstance(errors, list) and any(parts[3] in str(e) for e in errors):
            raise MissingEvidence(path)
    return value


def json_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right


def check_one(check, evidence):
    result = {'check': check, 'status': 'unknown'}
    try:
        left = resolve(evidence, check['path'])
        right = resolve(evidence, check['value_from']) if 'value_from' in check else check.get('value')
        op = check['op']
        if op == 'exists':
            passed = (left is not None) == right
        elif op in ('eq', 'ne'):
            passed = json_equal(left, right)
            if op == 'ne':
                passed = not passed
        elif op in ('gt', 'gte', 'lt', 'lte'):
            if type(left) not in (int, float) or type(right) not in (int, float):
                raise TypeError('ordering requires numbers')
            passed = {'gt': lambda: left > right, 'gte': lambda: left >= right,
                      'lt': lambda: left < right, 'lte': lambda: left <= right}[op]()
        elif op in ('contains', 'not_contains', 'in'):
            container, member = (right, left) if op == 'in' else (left, right)
            if isinstance(container, str) and isinstance(member, str):
                passed = member in container
            elif isinstance(container, list):
                passed = any(json_equal(item, member) for item in container)
            elif isinstance(container, dict) and isinstance(member, str):
                passed = member in container
            else:
                raise TypeError('incompatible membership types')
            if op == 'not_contains':
                passed = not passed
        elif op == 'matches':
            if not isinstance(left, str) or not isinstance(right, str):
                raise TypeError('matches requires strings')
            passed = re.search(right, left) is not None
        else:
            raise TypeError('unknown operator')
        result.update(status='pass' if passed else 'fail', actual=left, expected=right)
    except (MissingEvidence, TypeError, ValueError, re.error) as exc:
        result['reason'] = str(exc)
    return result


def conjunction(results):
    if any(r['status'] == 'fail' for r in results):
        return 'fail'
    return 'unknown' if any(r['status'] == 'unknown' for r in results) else 'pass'


def evaluate_step(step, before, after):
    evidence = {'before': before, 'after': after}
    branches = [{'id': b['id'], 'checks': [check_one(c, evidence) for c in b['checks']]}
                for b in step['expect']]
    for branch in branches:
        branch['status'] = conjunction(branch['checks'])
    invariants = [check_one(c, evidence) for c in step.get('invariants', [])]
    invariant_status = conjunction(invariants)
    if invariant_status == 'fail' or all(b['status'] == 'fail' for b in branches):
        status = 'contradiction'
    elif invariant_status == 'unknown' or not any(b['status'] == 'pass' for b in branches):
        status = 'unconfirmed'
    else:
        status = 'matched'
    return {'status': status, 'branches': branches, 'invariants': invariants,
            'matched_branches': [b['id'] for b in branches if b['status'] == 'pass']}
