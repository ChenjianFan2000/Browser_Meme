"""Offline artifact-integrity verification, not a website behavior test."""
import ast, hashlib, json, pathlib

root=pathlib.Path('.')
revision=root/'revisions/r002'
required=['revision.json','rulebook.md','rules.json','objects.json','coverage.json','scripts.py','exploration.jsonl']
for name in required:
    assert (revision/name).is_file(),name
assert not list(root.glob('**/behavior_model.py')),'Condition B forbids executable behavior prediction model'

seen={}
def check(x):
    if isinstance(x,dict):
        assert 'source_refs' not in x,'Prohibited citation key'
        if set(x)=={'path','sha256'}:
            p=pathlib.Path(x['path'])
            assert not p.is_absolute() and '..' not in p.parts,p
            assert p.is_file(),p
            actual=hashlib.sha256(p.read_bytes()).hexdigest()
            assert actual==x['sha256'],p
            seen[str(p)]=actual
        for value in x.values():check(value)
    elif isinstance(x,list):
        for value in x:check(value)

for d in [root/'revisions/r001',revision]:
    for p in d.glob('*.json'):check(json.loads(p.read_text()))
    for p in d.glob('*.jsonl'):
        for line in p.read_text().splitlines():check(json.loads(line))
rules=json.loads((revision/'rules.json').read_text())
assert len({r['id'] for r in rules})==len(rules)
for r in rules:
    assert set(['id','statement','status','preconditions','branches','forbidden_side_effects','evidence_refs'])<=r.keys()
    assert r['status'] in ['verified','hypothesis','unknown','refuted']
    if r['status'] in ['verified','refuted']:assert r['evidence_refs'],r['id']
    assert all(x['path'].startswith('evidence/') for x in r['evidence_refs'])
exploration=[json.loads(x) for x in (revision/'exploration.jsonl').read_text().splitlines()]
assert len(exploration)==40
assert sum(len(x['action_assessments']) for x in exploration)==214
assert exploration[-1]['classification']=='locator'
assert 'Subscribe not clicked' in exploration[-1]['interpretation']
assert json.loads((revision/'revision.json').read_text())['parent_revision']=='r001'
scripts=sorted(root.glob('experiments/*.py'))+[root/'ui.py',root/'reusable_scripts.py',revision/'scripts.py']
for p in scripts:
    tree=ast.parse(p.read_text())
    assert not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='predict' for n in ast.walk(tree)),p
inventory=[{'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed_during_learning':p.name!='40b_subscribe_locator_v2_UNEXECUTED.py'} for p in scripts if p.parent.name=='experiments']
(revision/'script_inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
report={'status':'passed','required_artifacts':required,'rules':len(rules),'verified_rules':sum(r['status']=='verified' for r in rules),'hypotheses':sum(r['status']=='hypothesis' for r in rules),'unknown_rules':sum(r['status']=='unknown' for r in rules),'refuted_rules':sum(r['status']=='refuted' for r in rules),'experiments':len(exploration),'per_action_records':sum(len(x['action_assessments']) for x in exploration),'referenced_files_sha256_verified':len(seen),'condition':'B','executable_behavior_prediction_model':False,'notes':['Offline validation only; semantic assertions remain bounded by original browser evidence.','Successful Python compilation was run separately.','No private tasks, independent scores, or exhaustive understanding claimed.','Script40 locator failed before newsletter fill/click; correction is unexecuted.']}
(revision/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
manifest=[{'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(revision.iterdir()) if p.is_file() and p.name!='package_manifest.json']
(revision/'package_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(report,indent=2))
