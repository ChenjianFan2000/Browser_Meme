import json, hashlib, importlib.util, ast, collections
from pathlib import Path
OUT=Path('revisions/r002')
def ref(p):return {'path':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def eref(n):
 p=next(Path('evidence').glob('call-%03d-*'%n));return [ref(p/'actions.jsonl'),ref(p/'network.json')]
spec=importlib.util.spec_from_file_location('learner_model',OUT/'behavior_model.py');model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
cases=[]
def add(name,o,i,disp,changed,count,call):cases.append((name,o,i,disp,changed,count,call))
auth={'authenticated':True}
add('first221want',{**auth,'wantlist_contains':False},{'op':'add_to_wantlist','release_id':221},'accepted',True,1,5)
add('repeat221want',{**auth,'wantlist_contains':True},{'op':'add_to_wantlist','release_id':221},'accepted',False,0,6)
add('repeat84want',{**auth,'wantlist_contains':True},{'op':'add_to_wantlist','release_id':84},'accepted',False,0,18)
add('first153collection',{**auth,'collection_contains':False},{'op':'add_to_collection','release_id':153},'accepted',True,1,31)
add('guest153collection',{'authenticated':False},{'op':'add_to_collection','release_id':153},'rejected',False,0,31)
for name,q,p,c in [('qty0',0,1999,13),('qtynegative',-1,1999,26),('qtyfraction',1.5,1234,12),('pricefraction',1,1.5,26),('pricezero',1,0,11)]:
 add(name,auth,{'op':'create_listing','selected_release_id':221,'quantity':q,'price_cents':p},'rejected',False,0,c)
for key,c in [('media_condition',27),('sleeve_condition',29),('ships_from',29)]:
 add('empty_'+key,auth,{'op':'create_listing','selected_release_id':221,'quantity':1,'price_cents':2,key:''},'rejected',False,0,c)
add('create_corrected',auth,{'op':'create_listing','selected_release_id':221,'quantity':2,'price_cents':1234,'media_condition':'Near Mint (NM or M-)','sleeve_condition':'Very Good Plus (VG+)','ships_from':'US','comments':'Learner3141 controlled listing'},'accepted',True,1,13)
add('repeat_create153',auth,{'op':'create_listing','selected_release_id':153,'quantity':3,'price_cents':1111,'media_condition':'Near Mint (NM or M-)','sleeve_condition':'Very Good Plus (VG+)','ships_from':'US','comments':'Learner3141 duplicate experiment'},'accepted',True,1,19)
add('deactivate_sold643',{**auth,'listing_status':'sold'},{'op':'deactivate_listing','listing_id':643},'accepted',True,1,35)
add('inactive_add642',{**auth,'listing_status':'inactive'},{'op':'add_to_cart','listing_id':642},'rejected',False,0,25)
add('repeat_cart4',{**auth,'listing_status':'active'},{'op':'add_to_cart','listing_id':4},'accepted',True,1,9)
add('remove_quantity2',{**auth,'cart_contains_target':True},{'op':'remove_cart_item','listing_id':12},'accepted',True,1,23)
add('bad_checkout642',{**auth,'cart_items':[{'listing_id':642,'quantity':1,'status':'inactive'}]},{'op':'checkout'},'rejected',False,0,22)
add('mixed_bad_checkout',{**auth,'cart_items':[{'listing_id':643,'quantity':1,'status':'active'},{'listing_id':644,'quantity':1,'status':'inactive'}]},{'op':'checkout'},'rejected',False,0,28)
add('excess_checkout',{**auth,'cart_items':[{'listing_id':4,'quantity':2,'status':'active'}]},{'op':'checkout'},'accepted',True,None,10)
add('mixed_seller_checkout',{**auth,'cart_items':[{'listing_id':7,'quantity':1,'status':'active'},{'listing_id':641,'quantity':1,'status':'active'}]},{'op':'checkout'},'accepted',True,None,21)
add('known_filter',auth,{'op':'filter_marketplace','release_id':221,'filters':{'ships_from':'Sweden','min_rating':'99.1','media_condition':'Good (G)','sort':'price_desc'}},'accepted',False,0,32)
add('moon_search',{}, {'op':'search','query':'moon'},'accepted',False,0,17)
reports=[]
for name,o,i,d,ch,ct,c in cases:
 got=model.predict(o,i); expected={'disposition':d,'effects':{'persistent_state_changed':ch,'affected_record_count':ct}}
 passed=got['disposition']==d and got['effects']==expected['effects']
 assert passed,(name,got,expected)
 reports.append({'case':name,'observation':o,'intent':i,'prediction':got,'expected_from_browser_evidence':expected,'evidence_refs':eref(c),'passed':passed})
unknowns=[(None,None),({},'unseen_operation'),(auth,{'op':'activate_listing','listing_id':640}),({**auth,'collection_contains':True},{'op':'add_to_collection','release_id':153}), (auth,{'op':'checkout','scope':'whole_task'}),({**auth,'cart_items':[{}]},{'op':'checkout'}),({'url':[],'text':{}},{'op':'unknown'}), (auth,{'op':'filter_marketplace','release_id':221,'filters':{'min_rating':'not-a-number'}})]
for o,i in unknowns:
 got=model.predict(o,i);assert got['disposition']=='unknown',(o,i,got)
 assert got['unknowns'];json.dumps(got,allow_nan=False)
# Validate actual original artifacts, not a mock of their implementation.
required=['revision.json','rulebook.md','rules.json','objects.json','coverage.json','scripts.py','behavior_model.py','exploration.jsonl']
for f in required: assert (OUT/f).is_file()
for f in ['scripts.py','behavior_model.py']:ast.parse((OUT/f).read_text())
rules=json.loads((OUT/'rules.json').read_text());seen=set();refs_checked={}
def checkrefs(v):
 if isinstance(v,dict):
  assert 'source_refs' not in v
  if set(v)=={'path','sha256'}:
   p=v['path'];assert not p.startswith('/') and '..' not in Path(p).parts
   assert len(v['sha256'])==64
   if p not in refs_checked:
    assert Path(p).is_file(),p
    refs_checked[p]=hashlib.sha256(Path(p).read_bytes()).hexdigest()
   assert refs_checked[p]==v['sha256'],p
  else:
   for z in v.values():checkrefs(z)
 elif isinstance(v,list):
  for z in v:checkrefs(z)
for r in rules:
 assert set(['id','statement','status','preconditions','branches','forbidden_side_effects','evidence_refs'])<=set(r)
 assert r['id'] not in seen;seen.add(r['id'])
 assert r['status'] in ('verified','refuted','hypothesis','unknown')
 if r['status'] in ('verified','refuted'):assert r['evidence_refs']
for f in OUT.glob('*.json'):
 checkrefs(json.loads(f.read_text()))
rows=[json.loads(z) for z in (OUT/'exploration.jsonl').read_text().splitlines()]
for row in rows:checkrefs(row)
actions=[z for z in rows if z.get('level')=='action'];assert len(actions)==300
before=after=0;errors=[];runtime=collections.Counter()
for cp in sorted(Path('evidence').glob('call-*')):
 result=json.loads((cp/'result.json').read_text());assert result['status']=='completed';assert result['error'] is None
 for z in map(json.loads,(cp/'actions.jsonl').read_text().splitlines()):
  if z.get('kind')=='action_before':
   before+=1;prediction=z['prediction'];assert set(['disposition','effects','ui_claims','unknowns'])<=set(prediction)
  if z.get('kind')=='action_after':
   after+=1;runtime[z.get('classification')]+=1
   if z.get('error'):errors.append(z)
assert before==after==300 and not errors
report={'status':'passed','scope':'Offline retrospective evidence-conformance and package integrity only. This is learner analysis, not independent evaluation or a held-out benchmark.','browser_replay_cases':reports,'unknown_and_malformed_input_checks':len(unknowns),'required_artifacts':required,'rules_by_status':dict(collections.Counter(r['status'] for r in rules)),'action_predictions':before,'action_readbacks':after,'executed_scripts':len(list(Path('evidence').glob('call-*'))),'raw_runtime_classification':dict(runtime),'all_evidence_files_hash_verified':len(refs_checked),'independent_tasks_accessed':0,'limitations':'Native browser work stopped at300 actions; final pure-model guards were validated offline. The final model uses bounded cases and returns unknown elsewhere.'}
(OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:v for k,v in report.items() if k not in ('browser_replay_cases','required_artifacts')})
