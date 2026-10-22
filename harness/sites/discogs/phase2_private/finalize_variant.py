"""Freeze variant readiness and restore original learning state after UI checks."""
import importlib.util
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('private_eval',Path(__file__).with_name('evaluator.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
def main():
    runtime=e.RUNTIME
    report=json.loads((runtime/'private/ui-readiness-001/report.private.json').read_text(encoding='utf8'))
    if report['executed']!=30:raise RuntimeError('Incomplete fixed denominator')
    evaluations=[]
    for case in e.cases():
        folder=runtime/'private/ui-readiness-001'/case['id']
        captured=json.loads((folder/'result.json').read_text(encoding='utf8'))
        before=json.loads((folder/'before.private.json').read_text(encoding='utf8'));after=json.loads((folder/'after.private.json').read_text(encoding='utf8'))
        evaluations.append(e.evaluate(case,before,after,{'events':captured['events'],'screenshot_path':str(folder/'after.png'),'ui_error':captured['error']}))
    result={'kind':'independent_environment_acceptance_not_learner','variant':runtime.name,'denominator':30,'evaluations':evaluations,'inventory_sha256':e.digest(e.INVENTORY),'evaluator_sha256':e.digest(Path(__file__).with_name('evaluator.py'))}
    private=runtime/'private/final-evaluations.private.json'
    with private.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    reset=e.reset_learning(0)
    with (runtime/'private/learning-reset-000.private.json').open('x',encoding='utf8') as f:json.dump(reset,f,ensure_ascii=False,indent=2)
    pids=json.loads((runtime/'pids.json').read_text(encoding='utf8'))
    status='ready' if all(v['outcome']=='passed' for v in evaluations) else 'environment_limits_evidenced'
    summary={'variant':runtime.name,'status':status,'kind':'independent_environment_acceptance_not_learner','denominator':30,'checked_cases':30,'verified_expected_endpoints':sum(v['outcome']=='passed' for v in evaluations),'ordinary_fixture_logins_verified':sum(r['login_ok'] for r in report['results']),'side_effect_checks_passed':sum(v['side_effects_ok'] for v in evaluations),'inventory_sha256':e.digest(e.INVENTORY),'source_manifest_sha256':e.digest(runtime/'variant-source-manifest.json'),'build_manifest_sha256':e.digest(runtime/'variant-build-manifest.json'),'dependency_manifest_sha256':e.digest(runtime/'dependency-copy-manifest.json'),'final_evidence_sha256':e.digest(private),'learning_baseline_sha256':reset['baseline_sha256'],'learning_state_reset':True,'seed_semantics':'scheduling only; original frozen baseline identical across seeds','public_fixture_path':str(runtime/'public-fixture.json'),'services':{'launcher_pid':int(os.environ['BM_VARIANT_LAUNCHER_PID']),'backend_pid':pids['backend'],'frontend_pid':pids['frontend'],'ports':[12042,12138],'stop_marker':str(runtime/'stop-ui-readiness-001')},'prediction_scores_reported':False,'tokens':None,'cost':None,'not_claimed':['learner performance','complete site coverage','official benchmark','strict speed control','proven phase2 learner isolation']}
    with (runtime/'readiness.management.json').open('x',encoding='utf8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    code=runtime/'private/adapter-source';code.mkdir()
    for path in Path(__file__).parent.glob('*.py'):
        (code/path.name).write_bytes(path.read_bytes())
    files={str(p.relative_to(runtime)):e.digest(p) for p in runtime.rglob('*') if p.is_file() and not p.is_relative_to(runtime/'source') and not p.is_relative_to(runtime/'logs') and p.name not in {'discogs.db','artifact-hashes.private.json'} and '__pycache__' not in p.parts}
    with (runtime/'private/artifact-hashes.private.json').open('x',encoding='utf8') as f:json.dump(files,f,indent=2)
    print(json.dumps(summary))
if __name__=='__main__':main()
