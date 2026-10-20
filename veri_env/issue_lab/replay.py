"""Freeze and replay saved Luna artifacts; never calls a model or the internet."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from issue_lab.benchmark import ROOT, PRIVATE, canonical, dump, read
from issue_lab.experiment_plan import CODE_METHODS, DIRECT_METHODS
from issue_lab.verienv_bridge import fingerprint


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifacts():
    for method in CODE_METHODS + DIRECT_METHODS:
        phases = ['initial', 'repaired', 'adapted'] if method in CODE_METHODS else ['initial', 'adapted']
        ext = '.py' if method in CODE_METHODS else '.json'
        for phase in phases:
            yield method, phase, ROOT/'artifacts/models'/method/(phase+ext)


def freeze():
    records, missing = [], []
    for method, phase, path in artifacts():
        if not path.exists():
            missing.append(str(path.relative_to(ROOT)))
            continue
        req_phase = {'repaired':'repair', 'adapted':'adapt'}.get(phase, phase)
        request = ROOT/'artifacts/requests'/method/(req_phase+'.json')
        records.append({'method':method, 'phase':phase, 'model':'gpt-6-luna', 'reasoning_effort':'high',
                        'input':str(request.relative_to(ROOT)), 'input_sha256':sha(request), 'input_bytes':request.stat().st_size,
                        'output':str(path.relative_to(ROOT)), 'output_sha256':sha(path), 'output_bytes':path.stat().st_size,
                        'export_to_output_seconds_including_queue': max(0, path.stat().st_mtime-request.stat().st_mtime),
                        'tokens':None, 'billing':None})
    if missing:
        raise RuntimeError('Missing artifacts: ' + ', '.join(missing))
    manifest = {'frozen_utc':datetime.now(timezone.utc).isoformat(), 'model_calls':len(records),
                'notes':'Each output is one authorized Luna subagent learning/prediction turn. Outputs were not hand-corrected. Queue-inclusive timings are not model latency. Full prompts are request payloads plus isolation instructions in the session; hidden chain of thought is not stored.',
                'records':records, 'data_manifest':read(ROOT/'artifacts/data/manifest.json')}
    dump(ROOT/'artifacts/frozen_run.json', manifest)
    return manifest


def export_tasks():
    splits = read(PRIVATE/'splits.json')
    tasks = []
    for name in ['one_step', 'rollout', 'drift']:
        for sample in splits[name]:
            tasks.append({'task_id':sample['id'], 'site':'issue_lab', 'split':name,
                'observation':sample['observation'], 'actions':sample['actions'],
                'judge_for_infoagent':{'eval_type':'rinfo','parse':'json','checks':[
                    {'op':'exact_match','path':'state_sha256','expected':fingerprint(canonical(sample['expected'][-1]))}]}})
    dump(PRIVATE/'verienv_tasks.json', tasks)


def failed_result(names, error):
    """Retain the full benchmark denominator even after a load error/timeout."""
    splits = read(PRIVATE/'splits.json')
    summary, rows = {}, []
    for name in names:
        cases = splits[name]
        summary[name] = {'n':len(cases), 'exact':0, 'valid':0, 'all_steps_exact':0,
                         'step_exact':0, 'steps':sum(len(s['actions']) for s in cases),
                         'prediction_seconds':0, 'seconds':0}
        for case in cases:
            rows.append({'id':case['id'], 'split':name, 'family':case['family'],
                         'scores':[dict(exact=False,records=False,interface=False,feedback=False) for _ in case['actions']],
                         'final_exact':False, 'all_steps_exact':False, 'valid':False,
                         'error':str(error), 'predicted':[], 'prediction_seconds':0, 'cpu_wall_seconds':0})
    return {'summary':summary, 'rows':rows, 'run_failure':str(error)}


def patchworld_validation():
    from issue_lab.upstream_audit import native_patchworld_validate
    splits = read(PRIVATE/'splits.json')
    result = {}
    for phase, names in [('initial',['one_step']), ('repaired',['one_step']), ('adapted',['drift'])]:
        transitions = [{'state':s['observation'], 'action':s['actions'][0], 'next_state':s['expected'][0]}
                       for name in names for s in splits[name]]
        # Canonicalize set-like record fields before strict native serialization.
        transitions = [{**t, 'state':canonical(t['state']), 'next_state':canonical(t['next_state'])} for t in transitions]
        result[phase] = native_patchworld_validate(ROOT/'artifacts/models/patchworld'/(phase+'.py'), transitions)
    dump(ROOT/'artifacts/results/patchworld.native_validation.json', result)
    print(json.dumps({k: {'passed':v['passed'], 'transitions':v['transitions'],
                         'native_errors':len(v['errors']), 'strict_errors':len(v['strict_errors'])} for k,v in result.items()}))


def replay():
    frozen = read(ROOT/'artifacts/frozen_run.json')
    for record in frozen['records']:
        if sha(ROOT/record['output']) != record['output_sha256']:
            raise ValueError('Frozen artifact changed: ' + record['output'])
        if sha(ROOT/record['input']) != record['input_sha256']:
            raise ValueError('Frozen request changed: ' + record['input'])
    for path, expected in frozen['data_manifest']['hashes'].items():
        if sha(ROOT/path) != expected:
            raise ValueError('Dataset changed: ' + path)
    export_tasks()
    summary, failures = [], []
    for method, phase, path in artifacts():
        code = method in CODE_METHODS
        names = ['one_step','rollout','drift'] if code or phase == 'initial' else ['one_step','drift']
        output = ROOT/'artifacts/results'/f'{method}.{phase}.test.json'
        cmd = [sys.executable,'-m','issue_lab.benchmark','score', '--model' if code else '--response', str(path),
               '--splits', *names, '--output', str(output)]
        try:
            proc = subprocess.run(cmd,cwd=ROOT,timeout=30,text=True,capture_output=True,encoding='utf-8')
            if proc.returncode:
                raise RuntimeError(proc.stderr[-4000:])
            result = read(output)
        except (subprocess.TimeoutExpired, RuntimeError) as exc:
            failures.append({'method':method,'phase':phase,'error':str(exc)})
            result = failed_result(names, exc)
            dump(output, result)
        for split, metrics in result['summary'].items():
            rr = [r for r in result['rows'] if r['split']==split]
            summary.append({'method':method,'phase':phase,'split':split, **metrics,
                'records_exact':sum(r['scores'][-1]['records'] for r in rr),
                'interface_exact':sum(r['scores'][-1]['interface'] for r in rr),
                'feedback_exact':sum(r['scores'][-1]['feedback'] for r in rr)})
        unchanged = [r for r in result['rows'] if r['split']=='one_step' and r['family'] != 'filter_selected']
        summary.append({'method':method,'phase':phase,'split':'unchanged_v1','n':len(unchanged),
                        'exact':sum(r['final_exact'] for r in unchanged),
                        'valid':sum(r['valid'] for r in unchanged)})
    dump(ROOT/'artifacts/results/summary.json', {'rows':summary, 'failures':failures})
    fields = ['method','phase','split','n','exact','valid','all_steps_exact','step_exact','steps',
              'records_exact','interface_exact','feedback_exact','prediction_seconds','seconds']
    with (ROOT/'artifacts/results/summary.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    proc = subprocess.run([sys.executable,'-m','issue_lab.replay','native-patchworld'],cwd=ROOT,
                           timeout=45,capture_output=True,text=True,encoding='utf-8')
    dump(ROOT/'artifacts/results/native_patchworld_execution.json', {'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    print(json.dumps({'scored_artifacts':len(frozen['records'])-len(failures), 'failures':failures,
                      'summary':'artifacts/results/summary.csv', 'native_patchworld_returncode':proc.returncode}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['freeze','replay','native-patchworld'])
    args = parser.parse_args()
    if args.command == 'freeze':
        print(json.dumps({'frozen_artifacts':freeze()['model_calls']}))
    elif args.command == 'native-patchworld': patchworld_validation()
    else: replay()
