import json,hashlib,ast
from pathlib import Path
out=Path('revisions/r002')
def ref(p):return {'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
scripts=[ref(p) for p in sorted(Path('experiments').glob('*.py'))]+[ref(out/'scripts.py'),ref(out/'behavior_model.py')]
(out/'script_manifest.json').write_text(json.dumps(scripts,indent=2)+'\n')
revision=json.loads((out/'revision.json').read_text());new=json.loads((out/'rules.json').read_text());old={r['id']:r for r in json.loads(Path('revisions/r001/rules.json').read_text())}
revision['changed_rules']=[r['id'] for r in new if old.get(r['id'])!=r]
revision['changed_scripts']=['revisions/r002/scripts.py','revisions/r002/behavior_model.py']+[p.as_posix() for p in sorted(Path('experiments').glob('e*.py')) if p.stem[1:3].isdigit() and int(p.stem[1:3])>=17]
revision['validation']='validation.json records retrospective conformance and integrity checks, not independent task scores'
(out/'revision.json').write_text(json.dumps(revision,indent=2)+'\n')
coverage=json.loads((out/'coverage.json').read_text());status={r['id']:r['status'] for r in new}
coverage['explored']=[{**row,'status':status[row['rule_id']]} for row in coverage['explored'] if status[row['rule_id']] in ('verified','refuted')]
coverage['predictor_protocol']={'levels':'predict is for an individual intent/operation. scope=whole_task or steps returns unknown; no per-action score is reported as a whole-task result.','limits':'Only documented records/form combinations receive accepted/rejected predictions; extrapolations stay unknown.','schema':'See behavior_model.py module docstring. Observation keys must come from current allowed UI/network evidence.'}
(out/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
# Side-effect-free model imports and standalone Python entry points.
for p in [out/'behavior_model.py',out/'scripts.py']:
 tree=ast.parse(p.read_text())
 names={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 assert ('predict' if p.name=='behavior_model.py' else 'run') in names
print('Updated manifests and revision diff:',len(revision['changed_rules']),'changed/new rules;',len(scripts),'preserved/current Python files')
