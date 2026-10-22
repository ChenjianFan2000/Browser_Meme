"""Offline package integrity and executable predictor interface verification."""
import ast, hashlib, importlib.util, json
from pathlib import Path

def validate():
 required=['revision.json','rulebook.md','rules.json','objects.json','coverage.json','scripts.py','behavior_model.py','exploration.jsonl']
 seen=set(); reference_count=0
 def walk(value):
  nonlocal reference_count
  if isinstance(value,dict):
   if 'source_refs' in value: raise AssertionError('Forbidden citation field')
   if 'path' in value and 'sha256' in value:
    p=Path(value['path'])
    assert not p.is_absolute() and '..' not in p.parts and p.exists(),p
    assert hashlib.sha256(p.read_bytes()).hexdigest()==value['sha256'],p
    reference_count+=1;seen.add(str(p))
   for x in value.values():walk(x)
  elif isinstance(value,list):
   for x in value:walk(x)
 for revision in ['001','002']:
  folder=Path('revisions')/revision
  for name in required: assert (folder/name).is_file(),name
  metadata=json.loads((folder/'revision.json').read_text())
  assert set(['revision','parent_revision','condition','changed_rules','changed_scripts','failure_category','evidence_refs','rationale'])<=metadata.keys()
  for p in folder.glob('*.json'):walk(json.loads(p.read_text()))
  rules=json.loads((folder/'rules.json').read_text())
  for r in rules:
   assert set(['id','statement','status','preconditions','branches','forbidden_side_effects','evidence_refs'])<=r.keys()
   assert r['status'] in ['verified','hypothesis','unknown','refuted']
   if r['status'] in ['verified','refuted']: assert r['evidence_refs']
  for line in (folder/'exploration.jsonl').read_text().splitlines():walk(json.loads(line))
  for p in folder.glob('*.py'):
   compile(p.read_text(),str(p),'exec')
   ast.parse(p.read_text())
  spec=importlib.util.spec_from_file_location('pilot_model_'+revision,folder/'behavior_model.py')
  model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
  cases=[({},{}),({'authenticated':True,'url':'http://127.0.0.1:12042/release/84','membership':{'collection':False}},{'action':'add_collection','release_id':84}),({'authenticated':True,'url':'http://127.0.0.1:12042/release/84','membership':{'collection':True}},{'action':'add_collection','release_id':84}),({'authenticated':True,'url':'http://127.0.0.1:12042/release/85','membership':{'collection':False}},{'action':'add_collection','release_id':85}),({'authenticated':True,'selected_release_id':84},{'action':'create_listing','quantity':1,'price_cents':0}),({'authenticated':True},{'scope':'task','action':'checkout'}),({'authenticated':True,'target_visible':True,'cart_items':[]},{'action':'add_cart','listing_id':354}),({'authenticated':True,'target_visible':True,'cart_items':[{'quantity':2,'listing':{'listing_id':354}}]},{'action':'add_cart','listing_id':354})]
  for observation,intent in cases:
   result=model.predict(observation,intent)
   assert set(result)==set(['disposition','effects','ui_claims','unknowns'])
   assert result['disposition'] in ['accepted','rejected','unknown']
   assert set(result['effects'])==set(['persistent_state_changed','affected_record_count'])
   assert isinstance(result['ui_claims'],list) and isinstance(result['unknowns'],list)
   for claim in result['ui_claims']:assert set(claim)==set(['claim','evidence_expected'])
  if revision=='002':
   a=model.predict(*cases[1]);b=model.predict(*cases[2])
   assert a['effects']=={'persistent_state_changed':True,'affected_record_count':1}
   assert b['effects']=={'persistent_state_changed':False,'affected_record_count':0}
   assert model.predict(*cases[3])['disposition']=='unknown'
   assert model.predict(*cases[5])['disposition']=='unknown'
   assert model.predict(*cases[7])['disposition']=='unknown'
 # Index independently checks every original browser export, including screenshots.
 index=json.loads(Path('evidence_index.json').read_text())
 walk(index)
 action_records=[json.loads(line) for line in Path('revisions/002/exploration.jsonl').read_text().splitlines()]
 assert sum(x.get('kind')=='action' for x in action_records)==72
 assert sum(x.get('kind')=='experiment' for x in action_records)==18
 return {'status':'passed','validation_scope':'Offline file integrity, schema, compilation, predictor interface and conservative state discrimination; no browser retest or private evaluation.','reference_occurrences_checked':reference_count,'unique_referenced_files':len(seen),'original_evidence_files_checked':len(index),'browser_actions_recorded':72,'browser_submissions_recorded':18,'final_scripts_browser_retested':False}

if __name__=='__main__':
 report=validate()
 Path('revisions/002/validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))
