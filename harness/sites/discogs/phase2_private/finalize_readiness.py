"""Re-score captured independent UI evidence; never replay writes."""
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('private_eval',Path(__file__).with_name('evaluator.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
def main():
    folder=e.RUNTIME/'private/ui-readiness-003'
    report=json.loads((folder/'report.private.json').read_text(encoding='utf8'))
    evaluations=[]
    for case in e.cases():
        path=folder/case['id']
        result=json.loads((path/'result.json').read_text(encoding='utf8'))
        before=json.loads((path/'before.private.json').read_text(encoding='utf8'))
        after=json.loads((path/'after.private.json').read_text(encoding='utf8'))
        evaluation=e.evaluate(case,before,after,{'events':result['events'],'screenshot_path':str(path/'after.png'),'ui_error':result['error']})
        evaluations.append({'id':case['id'],'classification':result['classification'],'evaluation':evaluation,'snapshot_hashes':{'before':e.digest(path/'before.private.json'),'after':e.digest(path/'after.private.json')}})
    private={'revision':'readonly-rescore-001','parent_run':'ui-readiness-003','denominator':30,'kind':'environment_acceptance_not_learner','evaluator_sha256':e.digest(Path(__file__).with_name('evaluator.py')),'evaluations':evaluations}
    out=e.RUNTIME/'private/ui-readiness-final-001.private.json'
    with out.open('x',encoding='utf8') as f:json.dump(private,f,ensure_ascii=False,indent=2)
    summary={'run_id':'phase2-discogs-20261021-01','status':'environment_limits_evidenced','kind':'independent_environment_acceptance_not_learner','denominator':30,'checked_cases':len(evaluations),'ordinary_fixture_logins_verified':sum(r['login_ok'] for r in report['results']),'classification_counts':report['classification_counts'],'side_effect_checks_passed':sum(v['evaluation']['side_effects_ok'] for v in evaluations),'prediction_scores_reported':False,'tokens':None,'cost':None,'inventory_sha256':e.digest(e.INVENTORY),'final_evidence_sha256':e.digest(out),'services':{'launcher_pid':25768,'backend_pid':32948,'frontend_pid':30748,'ports':[12042,12138],'stop_marker':str(e.RUNTIME/'stop-ui-readiness-001')},'limitations':['Original production dynamic routing blocker reproduced. No site source or task changes.','All 30 retained; environment acceptance is not learner performance.','Workflow novelty requires post-freeze exploration overlap audit.','A management reset and fresh browser context are required before each subsequent case.']}
    target=ROOT/'harness/experiments/phase2-discogs-20261021-01/private/readiness.management.json'
    with target.open('x',encoding='utf8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    manifest={str(p.relative_to(ROOT)):e.digest(p) for root in [ROOT/'harness/sites/discogs/phase2_private',ROOT/'harness/experiments/phase2-discogs-20261021-01/private'] for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='artifact-hashes.private.json'}
    with (target.parent/'artifact-hashes.private.json').open('x',encoding='utf8') as f:json.dump(manifest,f,indent=2)
    print(json.dumps(summary))
if __name__=='__main__':main()
