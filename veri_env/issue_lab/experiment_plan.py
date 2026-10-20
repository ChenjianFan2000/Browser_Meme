"""Export source-grounded, explicitly scoped Luna transfer conditions.

This module is an experimenter's tool. Never give it to a learner.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from issue_lab.benchmark import DATA, PRIVATE, ROOT, dump, export_request, read


CODE_METHODS = ['current', 'verienv_clone', 'worldcoder', 'patchworld',
                'gif_mcts', 'poe_world', 'agent2world']
DIRECT_METHODS = ['luna_direct', 'wma', 'webdreamer', 'webevolver', 'webworld']


def string_constant(path, name):
    """Extract a literal without importing upstream network-heavy packages."""
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = node.value
            if isinstance(value, ast.Call):
                value = value.func.value if isinstance(value.func, ast.Attribute) else value.args[0]
            return ast.literal_eval(value)
    raise KeyError((path, name))


def file_excerpt(path, start, end):
    return '\n'.join((ROOT/path).read_text(encoding='utf-8-sig').splitlines()[start-1:end])


def contexts():
    wc = 'external/WorldCoder/worldcoder/agent/synthesizer/init_transit.py'
    gif = 'external/code-world-models/data/prompts/gymnasium_envs/Taxi-v3/generate.md'
    poe = 'external/poe-world/prompts/synthesizer.py'
    a2w = 'external/agent2world/src/prompts/gen_code.py'
    wma = 'external/WMA-Agents/agent/prompts/jsons/state_prediction/text_only_description_with_tao_format.json'
    wd = 'external/WebDreamer/world_model.py'
    we = 'external/SelfEvolvingAgent/WebEvolver/cognitive_kernel_v2/backend/cognitive_kernel/call_web.py'
    ww = 'external/WebWorld/demo/prompts.py'
    return {
        'current': {'source': 'G:/Browser_Meme/研究目标.md', 'scope': 'proposed rule-memory plus executable predictor',
                    'text': (ROOT/'artifacts/method_context/current.txt').read_text('utf-8-sig')},
        'verienv_clone': {'source': 'external/VeriEnv-main/prompt.yaml', 'scope': 'behavior-clone proxy; native judge is separate; no RFT',
            'text': file_excerpt('external/VeriEnv-main/prompt.yaml', 6, 17) + '\nLOCAL ADAPTATION: reproduce the observable backend and interface behavior from transition evidence. No screenshots, website build, external assets, or policy fine-tuning are requested. Implement a pure state transition clone using the JSON contract.'},
        'worldcoder': {'source': wc, 'scope': 'original synthesis prompt adapted to JSON; no optimistic reward learning/planner',
            'text': string_constant(wc, 'FIRST_SYSTEM_MESSAGE') + '\n' + string_constant(wc, 'FIRST_MESSAGE') + '\nLOCAL ADAPTATION: the experiences are the JSON examples. Object records replace the native set-state wrapper. The required function is predict(state, action), replacing transition. No reward function or optimistic planning is evaluated.'},
        'patchworld': {'source': 'external/PatchWorld/patchworld/inducer_prompts.py', 'scope': 'original induction prompt plus native replay validator; no full TracePatch search',
            'text': (ROOT/'artifacts/method_context/patchworld.txt').read_text('utf-8-sig')},
        'gif_mcts': {'source': gif, 'scope': 'Generate/Improve/Fix prompt adaptation; one candidate and one repair, no MCTS search',
            'text': file_excerpt(gif, 1, 5) + '\nLOCAL ADAPTATION: synthesize the environment behavior solely from supplied issue transitions. Implement pure predict(state, action) rather than a Gym Environment. This condition is a Generate/Improve/Fix single-candidate ablation; it does not run a branching MCTS search. Consider edge cases and repair only from supplied development failures.'},
        'poe_world': {'source': poe, 'scope': 'deterministic attribute-expert adaptation; no learned probability weights or Atari planner',
            'text': string_constant(poe, 'explain_event_prompt') + '\nLOCAL ADAPTATION: replace Atari objects with issue records and interface fields. Factor effects into explicit guarded attribute experts and combine compatible outputs, keeping unchanged fields. The domain is deterministic: return the single predicted state. No RandomValues, geometry, external classes or unavailable probability training are required. Use only stdlib and pure predict(state, action). Do not claim a full product-of-experts probabilistic learner.'},
        'agent2world': {'source': a2w, 'scope': 'original code-agent prompt; independent feedback repair, no research tools, SFT or multi-agent pipeline',
            'text': string_constant(a2w, 'SYSTEM_PROMPT') + '\nLOCAL ADAPTATION: the specification is the common evidence and JSON contract; implement predict(state, action). Ignore physics-specific units. Do not create files beyond the requested output, tests, manifests or a __main__ example. No research/tool agent, sandbox service or policy fine-tuning is available.'},
        'luna_direct': {'source': None, 'scope': 'direct in-context transition prediction baseline',
            'text': 'Predict effects from the common observed transitions. Return structured predictions directly without generating or executing a transition program.'},
        'wma': {'source': wma, 'scope': 'original transition-focused instruction on Luna; structured observations; no Llama adapter/action selection',
            'text': read(ROOT/wma)['intro'] + '\nLOCAL ADAPTATION: structured public issue records stand in for the accessibility tree. The supplied action schema replaces browser click/type. Focus on changed fields and success/failure evidence. Return only the specified JSON deltas, with no free-form rationale.'},
        'webdreamer': {'source': wd, 'scope': 'state-change imagination instruction on Luna; no screenshots/action search/value model',
            'text': 'You are an agent that predicts the effect of an action on a webpage. Predict new, removed and changed elements, the resulting state, and whether the action has its intended effect.\nLOCAL ADAPTATION: this is the state-change component described in WebWorldModel.state_change_prediction_in_website. Use structured observations in place of screenshots and output exact JSON deltas. No candidate-action search or progress judge is run.'},
        'webevolver': {'source': we, 'scope': 'original world-model instruction on Luna; no joint self-evolution or fine-tuning',
            'text': string_constant(we, 'world_model_system_prompt') + '\nLOCAL ADAPTATION: use the complete structured observation rather than an accessibility tree and the local action contract. Predict the next observation, but encode only changed fields in the required JSON delta. Do not claim this reproduces the trained world-model weights or self-evolution loop.'},
        'webworld': {'source': ww, 'scope': 'original trajectory-prediction instruction on Luna; no Qwen/WebWorld weights',
            'text': string_constant(ww, 'WORLD_MODEL_SYSTEM') + '\nLOCAL ADAPTATION: page states are complete structured observations; actions use the local issue schema. For multiple actions, propagate your predicted state forward without seeing true intermediate states. Output the specified JSON deltas and omit reasoning tags.'},
    }


def opaque_id(case):
    return 'c_' + hashlib.sha256(case['id'].encode()).hexdigest()[:16]


def export_direct(method, phase='initial'):
    ctx = contexts()[method]
    splits = read(PRIVATE/'splits.json')
    names = ['one_step', 'rollout', 'drift'] if phase == 'initial' else ['one_step', 'drift']
    cases = [c for n in names for c in splits[n]]
    # The random-looking order and opaque IDs avoid revealing family/split/version.
    cases.sort(key=opaque_id)
    request = {
        'method': method, 'phase': phase, 'model': 'gpt-6-luna',
        'task': 'Predict every requested trajectory using only supplied evidence. Commit all predictions before any environment execution or scoring feedback. This is a Luna prompt transfer experiment, not an original trained-model reproduction.',
        'interface': read(DATA/'train.json')['interface'],
        'examples': read(DATA/'train.json')['examples'],
        'source_context': ctx['text'],
        'output_contract': 'Write a single JSON object with predictions: [{id: opaque case id, deltas: [one delta per action]}]. Each delta lists only changed top-level fields, plus optional issue_updates: [{id: issue id, changed_field: new_value}]. Unlisted fields persist. Always include actual feedback changes. Simulate each trajectory from its observation and then from your own previous predicted state. Do not generate or run a predictor program, access an environment, browse, read any other files, or obtain test answers. Cases are independent. Return no reasoning or markdown.',
        'cases': [{'id': opaque_id(c), 'observation': c['observation'], 'actions': c['actions']} for c in cases],
    }
    if phase == 'adapt':
        request['recent_observed_transitions'] = read(DATA/'adapt.json')['examples']
        request['task'] += ' The environment may have changed: recent evidence supersedes older conflicting evidence; retain other learned behavior. There is no observable rule-version flag.'
    path = ROOT/'artifacts/requests'/method/f'{phase}.json'
    dump(path, request)
    dump(ROOT/'artifacts/private_eval'/f'{method}.{phase}.id_map.json', {opaque_id(c): c['id'] for c in cases})
    return path


def prepare():
    registry = {}
    for name, spec in contexts().items():
        path = ROOT/'artifacts/method_context'/f'{name}.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(spec['text'], encoding='utf-8')
        registry[name] = {k:v for k,v in spec.items() if k != 'text'}
        registry[name].update({'kind': 'code' if name in CODE_METHODS else 'direct',
                              'model': 'gpt-6-luna', 'reasoning_effort': 'high',
                              'context_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        if name in CODE_METHODS:
            if not (ROOT/'artifacts/requests'/name/'initial.json').exists():
                export_request(name, source_context=spec['text'])
        elif not (ROOT/'artifacts/requests'/name/'initial.json').exists():
            export_direct(name)
    registry['code2world'] = {'kind': 'not_comparable', 'source': 'external/Code2World/android_world/agents/m3a_qwen.py',
        'scope': 'native prompt/transport component check only; screenshot-to-HTML prediction does not expose a business-state transition interface; no prediction score',
        'required_for_full_run': 'AndroidWorld emulator, GD-ML/Code2World checkpoint, image rendering, visual evaluation'}
    dump(ROOT/'artifacts/method_registry.json', registry)
    print(json.dumps({'code': CODE_METHODS, 'direct': DIRECT_METHODS, 'excluded_from_prediction': ['code2world']}))


if __name__ == '__main__':
    prepare()
