"""Offline integrity/scope validation, not independent website truth or scoring."""
import json,pathlib,hashlib,importlib.util
root=pathlib.Path(__file__).resolve().parent
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
def refs(obj):
    if isinstance(obj,dict):
        if set(obj)=={'path','sha256'}:yield obj
        for value in obj.values():yield from refs(value)
    elif isinstance(obj,list):
        for value in obj:yield from refs(value)
for version in ('001','002'):
    d=root/'revisions'/version
    required=['revision.json','rulebook.md','rules.json','objects.json','coverage.json','scripts.py','behavior_model.py','exploration.jsonl']
    check(version+' required files',all((d/n).is_file() for n in required))
    for file in d.iterdir():
        if file.suffix=='.json': obj=json.loads(file.read_text())
        elif file.suffix=='.jsonl':obj=[json.loads(line) for line in file.read_text().splitlines()]
        else:continue
        for r in refs(obj):
            p=root/r['path']
            assert p.is_file(),r
            assert p.resolve().is_relative_to(root),r
            assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],r
            if version=='001' and r['path'].startswith('evidence/call-'):
                assert int(r['path'].split('call-')[1][:3])<=6,r
    check(version+' all evidence refs exist with matching sha256',True)
    for file in d.glob('*.py'):compile(file.read_text(),str(file),'exec')
    check(version+' native scripts and model compile',True)
    rules=json.loads((d/'rules.json').read_text())
    fields={'id','statement','status','preconditions','branches','forbidden_side_effects','evidence_refs'}
    check(version+' complete rule schema',all(fields<=set(r) for r in rules))
    check(version+' verified/refuted evidence supplied',all(r['evidence_refs'] for r in rules if r['status'] in ('verified','refuted')))
    for r in rules:assert r['status'] in ('verified','hypothesis','unknown','refuted')
    entries=[json.loads(line) for line in (d/'exploration.jsonl').read_text().splitlines()]
    check(version+' per-action ledger count',sum(x['type']=='action' for x in entries)==(17 if version=='001' else 44))
check('parent revision retained',json.loads((root/'revisions/002/revision.json').read_text())['parent_revision']=='001')
spec=importlib.util.spec_from_file_location('behavior_model_test',root/'revisions/002/behavior_model.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
base={'authenticated':True,'account_scope':'supplied_fixture','release_id':221}
for kind in ('wantlist','collection'):
    for present in (False,True):
        o=dict(base,memberships={'wantlist':True,kind:present})
        p=model.predict(o,{'operation':kind+'.add','release_id':221})
        check(kind+' membership '+str(present)+' disposition',p['disposition']=='accepted')
        check(kind+' membership '+str(present)+' effect',p['effects']=={'persistent_state_changed':not present,'affected_record_count':0 if present else 1})
cart_cases=[(4,[],0,2145),(7,[{'listing_id':4,'quantity':1,'price_cents':2145}],2145,2285),(7,[{'listing_id':4,'quantity':1,'price_cents':2145},{'listing_id':7,'quantity':1,'price_cents':2285}],4430,2285)]
for num,(lid,items,total,price) in enumerate(cart_cases,1):
    o=dict(base,listing_active=True,listing_link_visible=True,listing_price_cents=price,cart={'items':items,'total_cents':total})
    p=model.predict(o,{'operation':'cart.add','listing_id':lid})
    check('observed cart transition '+str(num),p['disposition']=='accepted' and p['effects']=={'persistent_state_changed':True,'affected_record_count':1})
paid=dict(base,cart={'items':[{'listing_id':4,'quantity':1,'price_cents':2145},{'listing_id':7,'quantity':2,'price_cents':2285}],'total_cents':6715})
p=model.predict(paid,{'operation':'cart.checkout'})
check('observed checkout accepted without invented count',p['disposition']=='accepted' and p['effects']['affected_record_count'] is None)
unknown_cases=[({},{}),(None,{'operation':'cart.checkout'}),(base,{'operation':'listing.create'}),(dict(base,release_id=222,memberships={'wantlist':False}),{'operation':'wantlist.add','release_id':222}),(dict(base,account_scope='different',memberships={'wantlist':False}),{'operation':'wantlist.add','release_id':221}),(dict(base,authenticated=False,memberships={'wantlist':False}),{'operation':'wantlist.add','release_id':221}),(dict(base,cart={'items':[],'total_cents':0}),{'operation':'cart.checkout'}),(dict(base,listing_active=True,listing_link_visible=True,listing_price_cents=2285,cart={'items':[],'total_cents':0}),{'operation':'cart.add','listing_id':7}),(dict(base,memberships=[]),{'operation':'collection.add','release_id':221})]
for n,(o,i) in enumerate(unknown_cases):check('unsupported/malformed context unknown '+str(n),model.predict(o,i)['disposition']=='unknown')
for o,i in [(base,{'operation':'unknown'}),(paid,{'operation':'cart.checkout'})]:
    p=model.predict(o,i)
    check('public prediction schema '+i['operation'],set(p)=={'disposition','effects','ui_claims','unknowns'})
manifest=json.loads((root/'revisions/002/evidence_manifest.json').read_text())
check('all original exports indexed',len(manifest)==sum(p.is_file() for p in (root/'evidence').rglob('*')))
result={'status':'passed','checks':checks,'check_count':len(checks),'scope':'Offline package, evidence integrity, syntax and predictor regression/scope checks only. No new browser submission. These checks are not independent website truth or private-task scores.','browser_execution_of_final_reusable_scripts':'not performed after mandatory boundary stop'}
(root/'revisions/002/validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':'passed','checks':len(checks),'evidence_exports':len(manifest)}))
