import json,hashlib
from pathlib import Path

def ref(p):
 p=Path(p)
 return {'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
rules=json.loads(Path('revisions/002/rules.json').read_text())
byid={x['id']:x for x in rules}
mapping={'login':['R02','R03','R04'],'add_collection':['R05','R06'],'add_wantlist':['R07','R08'],'add_cart':['R09','R10','R11'],'checkout':['R12','R13'],'remove_cart':['R14'],'filter_marketplace':['R15'],'search_catalog':['R16'],'search_selling':['R17'],'create_listing':['R18','R19'],'navigate_add_release':['R20']}
support=[]
for branch,ids in mapping.items():
 support.append({'model_branch':branch,'rule_ids':ids,'scope':'Only matched observed conditions in behavior_model.py; other cases abstain.','evidence_refs':[e for id in ids for e in byid[id]['evidence_refs']]})
write('revisions/002/model_support.json',{'predictor_provenance':'Synthesized offline after learning. The learner LLM, not this final model, produced original action predictions; no formal prediction score is claimed.','prediction_scope':'Individual actions only; whole-task intents return unknown.','branches':support,'unknown_cases':['Different releases/accounts','Cart quantity above 2 or other combinations','Zero-price backend result and empty-checkout backend result','Positive listing creation and lifecycle','Any terminal unconfirmed write'],'evidence_refs':byid['R19']['evidence_refs']})
lineage=[]
for old,new,parent,call,reason in [('experiments/003_auth.py','experiments/004_auth_locator_fix.py','001',3,'Use rendered sign-in form structure after failed native label association.'),('experiments/005_account_release.py','experiments/006_account_release_fix.py','001',5,'Wait for authenticated Account button; original Account-link locator failed.'),('experiments/010_cart_add.py','experiments/011_cart_add_locator_fix.py','001',10,'Observed Add to Cart control was a link rather than a button.'),('experiments/018_sell_price_boundary.py','revisions/002/scripts.py','001',18,'Final reusable helper adds enabled-state guard after terminal disabled-control timeout; not browser-retested.')]:
 d=next(Path('evidence').glob(f'call-{call:03}-*'))
 lineage.append({'original_script':ref(old),'new_script':ref(new),'parent_revision':parent,'reason':reason,'evidence_refs':[ref(d/'result.json'),ref(d/'actions.jsonl')]})
write('revisions/002/script_lineage.json',lineage)
write('revisions/002/protocol.json',{'condition':'A','requested_learner_identity':'exact gpt-6.1-sol','scheduling_seed':1729,'formal_score':False,'site_origin':'http://127.0.0.1:12042','fixture_inspection':'Only keys and value types printed; credential values passed privately to observed login fields.','browser_channel':'Discovered mcp__phase2__execute_script; scripts export run(h), native Playwright.','offline_channel':'Command tools used only for file reading/writing, parsing exported evidence, compilation, hashing and package validation.','prediction_process':'h.expect before every dispatched UI action; originals in actions.jsonl. No task-boundary predictions or private tasks. Final executable model synthesized after exploration.','native_action_scroll':'Runtime confirms and scrolls locators on dispatch; no unrecorded explicit scrolls.','stopping_rule':'Stopped after one disabled-button click timeout. Runtime reported stop_reason null, but learner enforced stricter contract stop.','failure_preservation':'Original failed scripts and browser exports retained; offline corrected helper is separately versioned.','checkpoint_note':'Revision001 is a retrospective snapshot of observations1–3. Revision002 is the final synthesized package, not a claim that models existed before the action logs.','evidence_refs':[ref(next(Path('evidence').glob('call-001-*/actions.jsonl'))),ref(next(Path('evidence').glob('call-018-*/result.json')))]})
