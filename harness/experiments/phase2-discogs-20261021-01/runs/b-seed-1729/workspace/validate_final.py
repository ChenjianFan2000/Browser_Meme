import ast,json,hashlib
from pathlib import Path
r=Path('revisions/r004')
required=['revision.json','rulebook.md','rules.json','objects.json','coverage.json','scripts.py','exploration.jsonl']
for name in required:assert (r/name).is_file(),name
assert not list(Path('.').glob('**/behavior_model.py'))
assert (r/'scripts.py').read_bytes()==Path('reusable_scripts.py').read_bytes()
for f in list(Path('experiments').glob('*.py'))+[r/'scripts.py']:ast.parse(f.read_text())
seen=set()
def visit(x):
 if isinstance(x,dict):
  assert 'source_refs' not in x
  if 'path' in x and 'sha256' in x:
   p=Path(x['path']);assert not p.is_absolute()
   if str(p) not in seen:
    assert p.is_file(),p
    assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],p
    seen.add(str(p))
  for v in x.values():visit(v)
 elif isinstance(x,list):
  for v in x:visit(v)
for f in r.glob('*.json'):visit(json.loads(f.read_text()))
records=[json.loads(l) for l in (r/'exploration.jsonl').read_text().splitlines()]
for x in records:visit(x)
assert {x['experiment'] for x in records if x['level']=='experiment'}==set(range(1,41))
for x in json.loads((r/'rules.json').read_text()):
 assert all(k in x for k in ['id','statement','status','preconditions','branches','forbidden_side_effects','evidence_refs'])
 assert x['status'] in ['verified','hypothesis','unknown','refuted']
 if x['status'] in ['verified','refuted']:assert x['evidence_refs']
# Compare budget to original exported action-before records, including failed attempts.
actual=sum(sum(json.loads(l).get('kind')=='action_before' for l in p.read_text().splitlines()) for p in Path('evidence').glob('call-*/actions.jsonl'))
assert actual==286,actual
assert len(list(Path('evidence').glob('call-*/result.json')))==40
assert json.loads((r/'revision.json').read_text())['parent_revision']=='r003'
assert all((Path('revisions')/p/'revision.json').exists() for p in ['r001','r002','r003'])
print(json.dumps({'status':'passed','validated_hash_references':len(seen),'actual_ui_actions':actual,'browser_script_calls':40,'revision':'r004','predictor_present':False}))
