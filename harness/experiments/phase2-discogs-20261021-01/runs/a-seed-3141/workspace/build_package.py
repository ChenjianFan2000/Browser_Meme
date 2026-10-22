import json, hashlib, shutil, sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path('.')
revision=sys.argv[1]
maxcall=int(sys.argv[2])
parent=sys.argv[3] if len(sys.argv)>3 else None
out=ROOT/'revisions'/revision
out.mkdir(parents=True,exist_ok=True)
data=json.loads(Path('artifact_data.json').read_text())
def ref(p):
 p=Path(p)
 return {'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
calls={int(p.name.split('-')[1]):p for p in Path('evidence').glob('call-*') if int(p.name.split('-')[1])<=maxcall}
def refs(ns):
 return [ref(calls[n]/f) for n in ns for f in ('actions.jsonl','network.json','result.json')]
rules=[]
for rid,statement,status,conditions,branches,ns in data['rules']:
 if max(ns)>maxcall: continue
 rules.append({'id':rid,'statement':statement,'status':status,'preconditions':conditions,'branches':branches,'forbidden_side_effects':['No unobserved side effects claimed; do not blindly retry a write'], 'evidence_refs':refs(ns)})
(out/'rules.json').write_text(json.dumps(rules,indent=2)+'\n')
lines=['# Learned behavior — condition A, revision '+revision,'','Only the observed conditions below are verified. Seed3141 schedules this run and does not establish model sampling determinism. Each path is relative to the workspace; evidence hashes identify original browser exports.','']
for r in rules:
 lines += [r['id']+' ('+r['status']+'): '+r['statement'],'','Evidence: '+', '.join('`'+x['path']+'` sha256 `'+x['sha256']+'`' for x in r['evidence_refs']),'']
unknowns=data.get('unknowns',['Collection/wantlist removal and editing are unknown; missing controls do not establish missing backend behavior.','Reactivation of inactive listings is unknown.','Unobserved records, alternate accounts, currencies, concurrency, integer maxima, whitespace normalization, negative and nonnumeric quantity behavior remain unknown.','No claim about order management UI, refunds, shipping, release creation elsewhere, forum or blog functionality.','Checkout changed multiple kinds of record; exact affected count is unknown without inferring hidden state.'])
lines += ['## Unknowns and hypotheses','']+['- '+x for x in unknowns]
(out/'rulebook.md').write_text('\n'.join(lines)+'\n')
seen={}; journal=[]; allrefs=[]
for n,p in sorted(calls.items()):
 allrefs += refs([n])
 events=[json.loads(x) for x in (p/'actions.jsonl').read_text().splitlines()]
 result=json.loads((p/'result.json').read_text())
 journal.append({'experiment':'E%02d'%n,'level':'experiment','why_selected':data['experiments'].get(str(n),'Additional discriminating experiment'),'alternatives_considered':'Competing outcomes are stated in action rationales and pre-action predictions; unsupported alternatives remain hypotheses.','prediction':'See recorded per-action predictions below; no whole-task success prediction was substituted.','actual_evidence':refs([n]),'classification':'completed' if result.get('status')=='completed' else result.get('status','see_result'),'resulting_revision':revision})
 pending=None
 for e in events:
  if e.get('kind')=='action_before': pending=e
  if e.get('kind')=='action_after' and pending:
   ob=e.get('observation',{});net=ob.get('network',[])
   category='business_rule' if any(isinstance(z,dict) and z.get('status',0)>=400 and z.get('method') in ('POST','PATCH','PUT','DELETE') for z in net) else ('unconfirmed' if e.get('error') else 'observed')
   obsrefs=[ref(p/ob[k]) for k in ('dom','accessibility','screenshot') if ob.get(k) and (p/ob[k]).exists()]
   journal.append({'experiment':'E%02d'%n,'level':'action','action':pending.get('action'),'method':pending.get('method'),'target':pending.get('target'),'why_selected':pending.get('rationale'),'alternatives_considered':'Recorded prediction versus actual browser state; no implicit retry','prediction':pending.get('prediction'),'actual':{'url':ob.get('url'),'visible_text':ob.get('visible_text'),'error':e.get('error')},'actual_evidence':obsrefs+[ref(p/'actions.jsonl')], 'classification':category, 'runtime_classification':e.get('classification'),'resulting_revision':revision})
   pending=None
  if e.get('kind')=='learner_note':
   journal.append({'experiment':'E%02d'%n,'level':'note','actual':e.get('text'),'actual_evidence':[ref(p/'actions.jsonl')],'classification':'learner_note','resulting_revision':revision})
  if e.get('kind')=='observation' and e.get('url'):
   path=urlparse(e['url']).path
   if path not in seen:
    seen[path]={'path':path,'observed_url':e['url'],'title_or_summary':(e.get('visible_text') or '')[:1500],'evidence_refs':[ref(p/e['dom'])] if e.get('dom') else [ref(p/'actions.jsonl')]}
(out/'exploration.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in journal))
objects={'pages':list(seen.values()),'identities':data.get('objects',[
 {'kind':'release','id':221,'artist':'Pink Floyd','title':'The Dark Side Of The Moon','relationships':['Own listings4 and640; public marketplace /sell/release/221; personal list links'], 'actions':['Add to Wantlist','Add to Collection','Marketplace'], 'evidence_refs':refs([4,5,7,13]),'uncertainty':'Other releases not generalized'},
 {'kind':'listing','id':4,'release_id':221,'seller':'supplied account','price_cents':2145,'observed_transition':'active -> sold after checkout; quantity remained1','actions':['Add to Cart','Deactivate present'], 'evidence_refs':refs([9,10]),'uncertainty':'Cannot restore via observed controls'},
 {'kind':'listing','id':640,'release_id':221,'price_cents':1234,'quantity':2,'observed_transition':'created active -> inactive','actions':['Deactivate'], 'evidence_refs':refs([13,14,15]),'uncertainty':'Reactivation untested'},
 {'kind':'listing','id':7,'release_id':221,'price_cents':2285,'seller':'hernandezernest53','actions':['Add to Cart'], 'evidence_refs':refs([5,16]),'uncertainty':'Remaining stock unknown'},
 {'kind':'order','id':121,'observed_status':'paid','total_cents':4290,'items':[{'listing_id':4,'quantity':2}], 'actions':[],'evidence_refs':refs([10]),'uncertainty':'Order UI and management unknown'}]),'uncertainty':'Page inventory is observational, not an exhaustive route schema. Object ids come from DOM hrefs and sanitized UI-caused responses.'}
(out/'objects.json').write_text(json.dumps(objects,indent=2)+'\n')
coverage={'condition':'A','seed':3141,'explored':[{'rule_id':r['id'],'area':r['statement'],'evidence_refs':r['evidence_refs']} for r in rules],'unexplored':unknowns,'success_evidence':refs([5,9,10,13,16]),'rejection_evidence':refs([12,13,15,16]),'boundary_evidence':refs([4,8,9,11,12,13]),'competing_hypotheses':data.get('hypotheses',[{'hypothesis':'Other quantities/listings may enforce stock differently','status':'unknown','distinguishing_experiment':'Use a controlled listing with quantity3 and checkout one unit, read status and quantity'},{'hypothesis':'Create Listing repeated identical values may insert duplicates','status':'unknown','distinguishing_experiment':'Confirm first creation, deliberately submit same form again, compare ids'},{'hypothesis':'Filter media conditions may be exact equality rather than substring','status':'unknown','distinguishing_experiment':'Compare Mint versus Mint (M) in otherwise identical filters'}]),'evidence_refs':allrefs}
(out/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
manifest={'revision':revision,'parent_revision':parent,'condition':'A','changed_rules':[r['id'] for r in rules],'changed_scripts':['scripts.py','behavior_model.py'],'failure_category':['implementation','locator','business_rule'],'evidence_refs':allrefs,'rationale':'Independent browser-only discovery; conservative persisted-state predictions; retain optimistic-counter counterexamples, skipped locators and failed script versions. No source_refs.','provenance':{'model':'exact gpt-6.1-sol as supplied by launch','seed':3141,'script_calls_observed':len(calls)},'limitations':unknowns}
(out/'revision.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Built',out,'rules',len(rules),'journal entries',len(journal),'pages',len(seen))
