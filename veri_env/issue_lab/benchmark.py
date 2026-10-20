"""Deterministic data/export/scoring harness; never imported by a learner."""
from __future__ import annotations

import argparse
import ast
import builtins
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import time

from issue_lab.domain import IssueDomain
from issue_lab.verienv_bridge import fingerprint, judge_state

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'artifacts' / 'data'
PRIVATE = ROOT / 'artifacts' / 'private_eval'
MODELS = ROOT / 'artifacts' / 'models'


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def canonical(state):
    state = deepcopy(state)
    state['issues'] = sorted(state['issues'], key=lambda row: row['id'])
    for row in state['issues']:
        row['labels'] = sorted(row['labels'])
    state['selected'] = sorted(state['selected'])
    return state


def delta(before, after):
    result = {k: deepcopy(v) for k, v in after.items()
              if k != 'issues' and before.get(k) != v}
    changes = []
    previous = {r['id']: r for r in before['issues']}
    for row in after['issues']:
        change = {k: v for k, v in row.items() if previous[row['id']].get(k) != v}
        if change:
            changes.append({'id': row['id'], **change})
    if changes:
        result['issue_updates'] = changes
    return result


def apply_delta(state, change):
    state = deepcopy(state)
    for k, v in change.items():
        if k != 'issue_updates':
            state[k] = deepcopy(v)
    rows = {r['id']: r for r in state['issues']}
    for update in change.get('issue_updates', []):
        rows[update['id']].update(update)
    return canonical(state)


def fixture(seed, role='editor', version=1):
    env = IssueDomain(seed, version, role)
    rows = env.observe()['issues']
    good = [r['id'] for r in rows if r['status'] == 'open' and not r['blocked']]
    closed = [r['id'] for r in rows if r['status'] == 'closed']
    blocked = next(r['id'] for r in rows if r['blocked'])
    return env, good, closed, blocked


def sample(seed, name, prep, actions, role='editor', version=1):
    env = IssueDomain(seed, version, role)
    for action in prep:
        env.step(action)
    observation = env.observe()
    states = [env.step(action) for action in actions]
    return {'id': f'{name}-{seed}', 'seed': seed, 'family': name,
            'observation': observation, 'actions': actions, 'expected': states}


def cases(seed, split):
    env, good, closed, blocked = fixture(seed)
    g, c = good[0], closed[0]
    selected = [{'type': 'select', 'ids': [g, c]}]
    if split == 'train':
        specs = [
            ('sort', selected, [{'type': 'sort', 'direction': 'desc'}], 'editor'),
            ('select', [], [{'type': 'select', 'ids': [g, c, 9999]}], 'editor'),
            ('filter', selected, [{'type': 'filter', 'status': 'open'}], 'editor'),
            ('select_all', [{'type': 'filter', 'status': 'closed'}], [{'type': 'select_all'}], 'editor'),
            ('label', selected, [{'type': 'label', 'value': 'reviewed'}], 'editor'),
            ('close', [{'type': 'select', 'ids': good[:2]}], [{'type': 'close'}], 'editor'),
            ('reopen', [{'type': 'select', 'ids': [c]}], [{'type': 'reopen'}], 'editor'),
            ('comment', selected, [{'type': 'comment', 'text': 'Reviewed'}], 'editor'),
            ('blocked', [{'type': 'select', 'ids': [g, blocked]}], [{'type': 'close'}], 'editor'),
            ('mixed_reopen', selected, [{'type': 'reopen'}], 'editor'),
            ('permission', selected, [{'type': 'label', 'value': 'bug'}], 'viewer'),
            ('empty', [], [{'type': 'close'}], 'editor'),
        ]
    else:
        specs = [
            ('label_new', selected, [{'type': 'label', 'value': '  triaged  '}], 'editor'),
            ('filter_selected', selected, [{'type': 'filter', 'status': 'open', 'label': 'bug'}], 'editor'),
            ('blocked_atomic', [{'type': 'select', 'ids': [g, blocked]}], [{'type': 'close', 'reason': 'done'}], 'editor'),
            ('viewer_empty_comment', [], [{'type': 'comment', 'text': ''}], 'viewer'),
            ('reopen_mixed', selected, [{'type': 'reopen'}], 'editor'),
            ('sort_selected', selected, [{'type': 'sort', 'direction': 'desc'}], 'editor'),
            ('select_hidden', [{'type': 'filter', 'status': 'closed'}], [{'type': 'select', 'ids': [g, c, 9999]}], 'editor'),
            ('comment_empty', selected, [{'type': 'comment', 'text': ' '}], 'editor'),
        ]
    return [sample(seed, name, prep, actions, role) for name, prep, actions, role in specs]


def rollouts(seed):
    env, good, closed, blocked = fixture(seed)
    specs = [
        ('workflow_label_close', [], [{'type': 'filter', 'status': 'open'}, {'type': 'select', 'ids': good[:2]}, {'type': 'label', 'value': 'triaged'}, {'type': 'close'}]),
        ('workflow_reopen_empty', [], [{'type': 'select', 'ids': closed[:1]}, {'type': 'reopen'}, {'type': 'comment', 'text': 'reopened'}]),
        ('workflow_repeat_comment', [], [{'type': 'select', 'ids': good[:1]}, {'type': 'comment', 'text': 'checked'}, {'type': 'comment', 'text': 'checked'}, {'type': 'close'}]),
        ('workflow_failed_batch', [], [{'type': 'filter', 'status': 'open'}, {'type': 'select_all'}, {'type': 'close'}, {'type': 'label', 'value': 'needs-review'}]),
    ]
    return [sample(seed, name, prep, actions) for name, prep, actions in specs]


def drift_cases(seed, adaptation=False):
    env, good, closed, blocked = fixture(seed)
    specs = [
        ('drift_close', [{'type': 'select', 'ids': good[:1]}], [{'type': 'close'}]),
        ('drift_reason', [{'type': 'select', 'ids': good[:1]}], [{'type': 'close', 'reason': 'resolved'}]),
        ('drift_filter', [{'type': 'select', 'ids': good[:1] + closed[:1]}], [{'type': 'filter', 'status': 'open'}]),
    ]
    if not adaptation:
        specs.append(('drift_blocked_priority', [{'type': 'select', 'ids': [blocked]}], [{'type': 'close'}]))
    return [sample(seed, name, prep, actions, version=2) for name, prep, actions in specs]


INTERFACE = {
    'observation': 'Complete visible business records plus filter/sort/selected/role/feedback/visible_ids. Rule version is not observed.',
    'actions': ['filter(status=all|open|closed,label=string)', 'sort(direction=asc|desc)', 'select(ids=list[int])', 'select_all()', 'label(value=string)', 'close(reason=optional string)', 'reopen()', 'comment(text=string)'],
    'format': 'Each action is a JSON object with type and the parameters above. Infer conditions and effects from evidence, not from task names.',
    'delta': 'Only changed top-level keys are listed; issue_updates contains id and changed fields. Unlisted fields stay unchanged. This is an exact lossless encoding, not a description of rules.',
}


def public_evidence(samples):
    return [{'id': s['id'], 'observation': s['observation'], 'action': s['actions'][0],
             'observed_delta': delta(s['observation'], s['expected'][0])} for s in samples]


def build():
    train = sum((cases(seed, 'train') for seed in [11, 23, 37]), [])
    dev = sum((cases(seed, 'dev') for seed in [41, 43]), [])
    one = sum((cases(seed, 'test') for seed in [101, 103, 107]), [])
    multi = sum((rollouts(seed) for seed in [101, 103, 107]), [])
    adapt = sum((drift_cases(seed, True) for seed in [71, 73]), [])
    drift = sum((drift_cases(seed) for seed in [211, 223, 227]), [])
    dump(DATA / 'train.json', {'interface': INTERFACE, 'examples': public_evidence(train)})
    dump(DATA / 'adapt.json', {'interface': INTERFACE, 'examples': public_evidence(adapt)})
    dump(PRIVATE / 'splits.json', {'train': train, 'dev': dev, 'one_step': one, 'rollout': multi, 'drift': drift})
    manifest = {'created_before_model_calls': True, 'counts': {'train': len(train), 'dev': len(dev), 'one_step': len(one), 'rollout': len(multi), 'adapt': len(adapt), 'drift': len(drift)}, 'hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/'train.json', DATA/'adapt.json', PRIVATE/'splits.json']}}
    dump(DATA / 'manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False))


ALLOWED_IMPORTS = {'copy', 'json', 'math', 're', 'typing', 'collections', 'itertools', 'functools'}
FORBIDDEN = {'open', 'eval', 'exec', 'compile', '__import__', 'globals', 'locals', 'input', 'breakpoint', 'getattr', 'setattr', 'vars'}


def load_predict(path):
    source = Path(path).read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(n.name.split('.')[0] not in ALLOWED_IMPORTS for n in node.names):
                raise ValueError('Unapproved import')
        elif isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] not in ALLOWED_IMPORTS:
            raise ValueError('Unapproved from import')
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN:
            raise ValueError('Unapproved operation: ' + node.id)
        elif isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise ValueError('Dunder access prohibited')
    safe = {k: v for k, v in vars(builtins).items() if k not in FORBIDDEN}
    def import_allowed(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name.split('.')[0] not in ALLOWED_IMPORTS:
            raise ImportError(name)
        return builtins.__import__(name, globals, locals, fromlist, level)
    safe['__import__'] = import_allowed
    namespace = {'__builtins__': safe, '__name__': 'generated_issue_model'}
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace['predict']


def score_states(predicted, expected):
    predicted, expected = canonical(predicted), canonical(expected)
    native = judge_state(predicted, expected)
    return {'exact': native['passed'],
            'records': fingerprint(predicted.get('issues')) == fingerprint(expected.get('issues')),
            'interface': all(fingerprint(predicted.get(k)) == fingerprint(expected.get(k)) for k in ['filter','sort','selected','role','visible_ids']),
            'feedback': fingerprint(predicted.get('feedback')) == fingerprint(expected.get('feedback'))}


def validate_observation(value):
    """Check the public JSON contract, never a business rule or test answer."""
    required = {'issues', 'filter', 'sort', 'selected', 'role', 'feedback', 'visible_ids'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('Observation must contain exactly the public fields')
    if not isinstance(value['issues'], list):
        raise ValueError('issues must be a list')
    ids = []
    for row in value['issues']:
        if not isinstance(row, dict) or set(row) != {'id','title','status','labels','blocked','priority','comments'}:
            raise ValueError('Invalid issue record schema')
        if type(row['id']) is not int or type(row['priority']) is not int or type(row['blocked']) is not bool:
            raise ValueError('Invalid issue numeric/boolean types')
        if not isinstance(row['title'], str) or row['status'] not in ('open','closed'):
            raise ValueError('Invalid issue title/status')
        for key in ['labels','comments']:
            if not isinstance(row[key], list) or not all(isinstance(v,str) for v in row[key]):
                raise ValueError('Invalid issue text list')
        ids.append(row['id'])
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate issue IDs')
    for key in ['selected','visible_ids']:
        if not isinstance(value[key],list) or any(type(v) is not int for v in value[key]):
            raise ValueError('Invalid ID list')
        if len(value[key]) != len(set(value[key])):
            raise ValueError('Duplicate IDs in interface list')
    if not isinstance(value['filter'],dict) or set(value['filter']) != {'status','label'}:
        raise ValueError('Invalid filter schema')
    if value['filter']['status'] not in ('all','open','closed') or not isinstance(value['filter']['label'],str):
        raise ValueError('Invalid filter types')
    if value['sort'] not in ('asc','desc') or value['role'] not in ('editor','viewer'):
        raise ValueError('Invalid sort or role')
    if not isinstance(value['feedback'],dict) or set(value['feedback']) != {'ok','code'}:
        raise ValueError('Invalid feedback schema')
    if type(value['feedback']['ok']) is not bool or not isinstance(value['feedback']['code'],str):
        raise ValueError('Invalid feedback types')


def evaluate(model_path, split_names, response_path=None):
    splits = read(PRIVATE / 'splits.json')
    predictions = None
    if response_path:
        raw_predictions = read(response_path)['predictions']
        predictions = {r['id']: r['deltas'] for r in raw_predictions}
        if len(predictions) != len(raw_predictions):
            raise ValueError('Duplicate prediction case IDs')
        # Direct conditions receive opaque IDs, never family/version labels.
        for sample_list in splits.values():
            for case in sample_list:
                opaque = 'c_' + hashlib.sha256(case['id'].encode()).hexdigest()[:16]
                if opaque in predictions:
                    predictions[case['id']] = predictions[opaque]
    else:
        predict = load_predict(model_path)
    rows = []
    for split_name in split_names:
        for s in splits[split_name]:
            current = deepcopy(s['observation'])
            scores, states, error = [], [], None
            prediction_seconds = 0.0
            started = time.perf_counter()
            for i, action in enumerate(s['actions']):
                try:
                    if predictions is not None and len(predictions[s['id']]) != len(s['actions']):
                        raise ValueError('Need exactly one delta per action')
                    model_state, model_action = deepcopy(current), deepcopy(action)
                    prediction_start = time.perf_counter()
                    try:
                        current = (apply_delta(model_state, predictions[s['id']][i]) if predictions is not None else predict(model_state, model_action))
                    finally:
                        prediction_seconds += time.perf_counter() - prediction_start
                    validate_observation(current)
                    scores.append(score_states(current, s['expected'][i]))
                    states.append(deepcopy(current))
                except Exception as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
                    scores.extend([dict(exact=False, records=False, interface=False, feedback=False)] * (len(s['actions']) - i))
                    break
            rows.append({'id': s['id'], 'split': split_name, 'family': s['family'],
                         'scores': scores, 'final_exact': scores[-1]['exact'], 'all_steps_exact': all(v['exact'] for v in scores),
                         'valid': error is None, 'error': error, 'predicted': states,
                         'prediction_seconds': prediction_seconds,
                         'cpu_wall_seconds': time.perf_counter()-started})
    summary = {}
    for name in split_names:
        rr = [r for r in rows if r['split'] == name]
        summary[name] = {'n': len(rr), 'exact': sum(r['final_exact'] for r in rr),
                         'valid': sum(r['valid'] for r in rr),
                         'all_steps_exact': sum(r['all_steps_exact'] for r in rr),
                         'step_exact': sum(sum(s['exact'] for s in r['scores']) for r in rr),
                         'steps': sum(len(r['scores']) for r in rr),
                         'prediction_seconds': sum(r['prediction_seconds'] for r in rr),
                         'seconds': sum(r['cpu_wall_seconds'] for r in rr)}
    return {'summary': summary, 'rows': rows,
            'judge': 'original VeriEnv judge_dsl exact_match on independently computed canonical state SHA256',
            'normalization': 'sort issue records, labels and selected IDs; retain comment order, visible_ids order, string case/space and JSON types'}


def export_request(method, phase='initial', source_context=''):
    out = ROOT / 'artifacts' / 'requests' / method
    train = read(DATA / 'train.json')
    request = {'method': method, 'phase': phase, 'model': 'gpt-6-luna',
               'task': 'Infer a reusable deterministic Python transition model from evidence. This is a local issue-management transfer experiment, not a reproduction of a paper training run.',
               'interface': train['interface'], 'examples': train['examples'],
               'output_contract': 'Write only a standalone Python module defining predict(state:dict, action:dict)->dict. Return the complete next observation. Do not read files, use tools for external information, call a model at prediction time or hardcode example IDs. Only copy/json/math/re/typing/collections/itertools/functools imports are allowed. Save uncertainty and rule notes in a module docstring. Evidence fields are exhaustive for these experiments; do not invent inaccessible latent state.',
               'source_context': source_context}
    if phase != 'initial':
        request['previous_model'] = (MODELS / method / 'initial.py').read_text(encoding='utf-8-sig')
        if phase == 'repair':
            result = evaluate(MODELS / method / 'initial.py', ['dev'])
            examples = {s['id']: s for s in read(PRIVATE/'splits.json')['dev']}
            request['counterexamples'] = [{**examples[r['id']], 'predicted': r['predicted'], 'error': r['error']} for r in result['rows'] if not r['final_exact']][:8]
            request['task'] = 'Repair the previous model using development counterexamples. Preserve previously observed behavior. If no failures, retain the model. Output the complete module.'
        else:
            base = MODELS/method/'repaired.py'
            if base.exists():
                request['previous_model'] = base.read_text(encoding='utf-8-sig')
            request['new_environment_evidence'] = read(DATA/'adapt.json')['examples']
            request['task'] = 'The environment may have changed. Revise your current model using the six recent observed transitions, preserving unchanged rules. Do not assume a visible version field or ask for test answers.'
    dump(out/f'{phase}.json', request)
    return out/f'{phase}.json'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['build','request','score'])
    parser.add_argument('--method')
    parser.add_argument('--phase', default='initial')
    parser.add_argument('--source-context', default='')
    parser.add_argument('--model')
    parser.add_argument('--response')
    parser.add_argument('--splits', nargs='+', default=['one_step','rollout','drift'])
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'build': build()
    elif args.command == 'request':
        context = Path(args.source_context).read_text('utf-8-sig') if args.source_context else ''
        print(export_request(args.method, args.phase, context))
    else:
        result = evaluate(args.model, args.splits, args.response)
        if args.output: dump(args.output, result)
        print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
