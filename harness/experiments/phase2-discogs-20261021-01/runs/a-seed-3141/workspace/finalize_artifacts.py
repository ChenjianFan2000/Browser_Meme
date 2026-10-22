import json, hashlib, re
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path('.')
OUT=Path('revisions/r002')
cache={}
def ref(p):
 p=Path(p);key=p.as_posix()
 if key not in cache: cache[key]={'path':key,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 return cache[key]
def write(name,v): (OUT/name).write_text(json.dumps(v,indent=2)+'\n')
call_dirs=sorted(Path('evidence').glob('call-*'))
def refs(*numbers): return [ref(p/f) for p in call_dirs if int(p.name.split('-')[1]) in numbers for f in ('actions.jsonl','network.json','result.json')]
class DOM(HTMLParser):
 def __init__(self): super().__init__();self.anchors=[];self.anchor=None;self.rows=[];self.row=None
 def handle_starttag(self,t,aa):
  a=dict(aa)
  if t=='a':self.anchor={'href':a.get('href',''),'text':[]}
  if t=='tr':self.row={'text':[],'hrefs':[]}
  if self.row is not None and t=='a': self.row['hrefs'].append(a.get('href',''))
  if self.anchor is not None and t=='img' and a.get('alt'): self.anchor['text'].append(a['alt'])
 def handle_data(self,s):
  if self.anchor is not None:self.anchor['text'].append(s)
  if self.row is not None:self.row['text'].append(s)
 def handle_endtag(self,t):
  if t=='a' and self.anchor is not None:
   self.anchor['text']=' '.join(' '.join(self.anchor['text']).split()); self.anchors.append(self.anchor);self.anchor=None
  if t=='tr' and self.row is not None:
   self.row['text']=' '.join(' '.join(self.row['text']).split());self.rows.append(self.row);self.row=None
releases={}; listings={};orders={};links={};latest_own={};cart_observations=[]
for cp in call_dirs:
 for dp in sorted(cp.glob('obs-*.html')):
  parser=DOM();parser.feed(dp.read_text())
  for a in parser.anchors:
   href=a['href']
   if href.startswith('/') and not href.startswith('//'):
    links[href]={'href':href,'label':a['text'],'evidence_refs':[ref(dp)],'uncertainty':'Discovered in rendered DOM; navigation verified only if listed among pages'}
   m=re.fullmatch(r'/release/(\d+)',href)
   if m:
    rid=int(m.group(1));releases[rid]={'kind':'release','id':rid,'href':href,'displayed_label':a['text'],'actions':['open release page'],'relationships':['Personal lists, search and discovery pages link release identities'], 'evidence_refs':[ref(dp)],'uncertainty':'Link identity confirmed; detailed metadata/actions tested only for84,153,221'}
  for row in parser.rows:
   for href in row['hrefs']:
    m=re.fullmatch(r'/cart\?add=(\d+)',href)
    if m:
     lid=int(m.group(1));v=listings.setdefault(lid,{'kind':'listing','id':lid,'uncertainty':[]})
     v.update({'observed_marketplace_text':row['text'],'add_href':href,'actions':['Add to Cart when rendered active'],'evidence_refs':[ref(dp)]})
 for response in json.loads((cp/'network.json').read_text()):
  url=response.get('url','');body=response.get('body');er=ref(cp/'network.json')
  if not isinstance(body,dict):continue
  if url.endswith('/api/me/listings') and response.get('method')=='GET':
   for item in body.get('items',[]):
    lid=item['id'];latest_own[lid]=dict(item)
    v=listings.setdefault(lid,{'kind':'listing','id':lid,'uncertainty':[]})
    v.update(item);v['actions']=['Deactivate in observed own listing UI']
    v['evidence_refs']=[er]
    v['owner']='supplied account'
  if url.endswith('/api/cart') or url.endswith('/api/cart/items'):
   if isinstance(body.get('items'),list):
    cart_observations.append({'call':cp.name,'items':body['items'],'total_cents':body.get('total_cents'),'evidence_refs':[er]})
    for item in body['items']:
     listing=item.get('listing',{});lid=listing.get('listing_id')
     if lid is not None:
      v=listings.setdefault(lid,{'kind':'listing','id':lid,'uncertainty':[]});v.update(listing)
  if url.endswith('/api/checkout') and response.get('method')=='POST' and response.get('status')==200:
   order=dict(body);order.update({'kind':'order','evidence_refs':[er],'actions':[],'uncertainty':'Paid response observed; order management UI and hidden related records not enumerated'})
   orders[order['id']]=order
for lid,item in latest_own.items():
 listings[lid].update(item)
 listings[lid]['uncertainty']=['Observed learning-state snapshot; evaluator may reset business state. Identity matching can be ambiguous when visible fields duplicate.']
for lid in listings:
 if lid not in latest_own: listings[lid]['uncertainty']=['Seller ownership/status may not be directly available; marketplace text is a dated observation, not current availability.']
objects=json.loads((OUT/'objects.json').read_text())
objects['identities']={'releases':list(releases.values()),'listings':list(listings.values()),'orders':list(orders.values())}
objects['discovered_hrefs']=list(links.values())
objects['cart_relationship']={'statement':'Cart rows join listing IDs, quantity and unit prices. Row IDs were reused after cart deletion/checkout and must not be treated as globally stable identities.','observations':cart_observations,'uncertainty':'Quantity is present in sanitized UI-caused responses but not printed as a cart control in the tested DOM'}
actions={'/':['search','discover release cards','hover navigation menus'], '/login':['fill username/password from fixture keys','Sign in; next handling'], '/search':['open matching release links'], '/sell':['search/select release','fill7 main inputs by observed order','Create Listing','Deactivate own row'], '/cart':['Remove whole row','Checkout'], '/me/collection':['open release links'], '/me/wantlist':['open release links'], '/genre/rock':['open release cards','Rock Releases and style text-search links']}
for page in objects['pages']:
 path=page['path'];page['actions']=actions.get(path,['Add to Wantlist','Add to Collection','open marketplace'] if path.startswith('/release/') else ['filter','sort','Add to Cart'] if path.startswith('/sell/release/') else [])
 page['uncertainty']='Only observed path/state; 404 pages do not establish route/backend absence elsewhere'
objects['form_fields']={'seller_main_input_order':['Find a release search','Media Condition','Sleeve Condition','Ships From','Quantity','Price (cents)','Comments'],'marketplace_names':['media_condition','sleeve_condition','ships_from','min_rating','sort'],'login':'Two main inputs, password has type=password; fixture supplies values and they are never printed','evidence_refs':refs(11,13,24,29,33)}
write('objects.json',objects)
failures=[
 {'id':'P01','classification':'implementation','stage':'offline preparation / pre-execution rejection','error':'python executable was unavailable; e01.py was not created; execute_script returned ValueError: input file is missing','correction':'Use python3, create the file, then make the first actual browser submission','evidence_refs':[],'browser_export_available':False},
 {'id':'P02','classification':'implementation','stage':'static script policy rejection','error':'ValueError: observation policy excludes name getattr','preserved_script_refs':[ref('experiments/common.py'),ref('experiments/e02.py')],'correction':'Explicit native methods in common_v2.py / e02_v2.py','evidence_refs':[],'browser_export_available':False},
 {'id':'P03','classification':'implementation','stage':'static module policy rejection','error':'ValueError: observation policy excludes name _prediction','preserved_script_refs':[ref('experiments/behavior_model_v2.py'),ref('experiments/task_scripts_v2.py'),ref('experiments/e32.py')],'correction':'Public helper name prediction_shape in behavior_model_v3; e32_v2.py executed successfully','evidence_refs':[],'browser_export_available':False},
 {'id':'L01','classification':'locator','stage':'E03 username selector','error':'input[type=text] found zero because the username input omitted type; no fill action occurred. Existing prefilled username was used; password fill and login succeeded.','evidence_refs':refs(3)},
 {'id':'L02','classification':'locator','stage':'E05 removal and E06 header control','error':'Remove membership controls absent; no action. Last header button was hidden Sign out and skipped; account hrefs were still discoverable in rendered DOM.','evidence_refs':refs(5,6)},
 {'id':'L03','classification':'locator','stage':'E19 explicit selection','error':'Exact accessible name without whitespace matched zero; first result153 remained selected. Two actual creations for153 were confirmed. No blind retries.','preserved_script_refs':[ref('experiments/e19.py')],'correction':'E20 uses observed #221 text; final helper verifies exact selected artist/title and stops on failure','evidence_refs':refs(19,20)},
 {'id':'L04','classification':'locator','stage':'E35 duplicate visible listing key','error':'After643 deactivation, helper for646 found both inactive640 and646 sharing title/price/status and returned None before any action.','correction':'E36 only captures final state; reactivation/hidden identity not inferred and no mutation retry attempted','preserved_script_refs':[ref('experiments/e35.py'),ref('experiments/e35_v2.py')],'evidence_refs':refs(35,36)},
 {'id':'B01','classification':'business_rule','stage':'Intentional validation/authentication/availability probes','error':'Observed401 invalid login,422 quantity/price/string boundaries,400 unavailable checkout and404 inactive/sold cart add','evidence_refs':refs(12,13,16,22,25,26,27,28,29)}
]
write('failures.json',failures)
budget={'actions':300,'action_limit':300,'executed_scripts':36,'executed_script_limit':40,'attempted_execute_script_submissions_including_preexecution_rejections':39,'preexecution_rejections':3,'last_authoritative_browser_elapsed_seconds':1801.441446536,'total_time_limit_seconds':7200,'single_script_timeout_seconds':300,'browser_work_stopped':'UI action budget reached; no later browser calls','offline_work_inclusive':'Artifact generation and validation after browser stop; final clock recorded in READY metadata'}
write('budget.json',budget)
coverage=json.loads((OUT/'coverage.json').read_text());coverage['budget']=budget
coverage['success_evidence']=refs(5,9,10,13,16,18,19,21,26,27,28,29,30,31,32,33,34,35,36)
coverage['rejection_evidence']=refs(12,13,15,16,22,25,26,27,28,29)
coverage['boundary_evidence']=refs(4,8,9,11,12,13,17,18,22,24,25,26,27,29,35,36)
coverage['script_entrypoints']={'executed':['search','filter_marketplace','select_release_for_listing','create_listing','add_membership','add_cart','remove_cart_item','deactivate_own_listing','go','act'], 'not_executed_as_exact_final_wrappers':['sign_in','sign_out','checkout'],'note':'Their native action sequences were observed in experimental scripts; wrapper-specific success is not claimed','evidence_refs':refs(16,21,30,31,32,33,34,35,36)}
coverage['independent_scoring']='No private tasks or independent scoring accessed. Retrospective validation is learner analysis, not evaluator truth.'
write('coverage.json',coverage)
rev=json.loads((OUT/'revision.json').read_text());rev['budget']=budget
rev['failed_versions']='See failures.json and preserved files in experiments/. r001 remains unchanged.'
rev['changed_scripts']=['scripts.py','behavior_model.py','experiments/e17.py through e35_v2.py; exact files listed in script_manifest.json']
rev['rationale']='Extend r001 using original browser counterexamples, explicit selection/readback guards, repeated writes, numeric/string boundaries, mixed cart states and session combinations. Verify only documented conditions and keep extrapolations as hypotheses.'
write('revision.json',rev)
# Append failures without inventing browser-export paths for static rejections.
journal=[json.loads(s) for s in (OUT/'exploration.jsonl').read_text().splitlines()]
for row in journal:
 if row.get('level')=='experiment' and row.get('experiment') in ('E19','E35'):row['classification']='locator'
for failure in failures[:3]:
 journal.append({'experiment':failure['id'],'level':'preexecution_failure','why_selected':'Prepare native browser script/module','alternatives_considered':'Explicit native method calls and public helper names','prediction':'No UI action was executed','actual':failure['error'],'actual_evidence':[],'preserved_script_refs':failure.get('preserved_script_refs',[]),'evidence_availability':'Pre-execution rejection has no browser evidence directory; conversation tool result is preserved by coordinator','classification':failure['classification'],'resulting_revision':'r002'})
(OUT/'exploration.jsonl').write_text(''.join(json.dumps(z)+'\n' for z in journal))
script_manifest=[ref(p) for p in sorted(Path('experiments').glob('*.py'))]+[ref(OUT/'scripts.py'),ref(OUT/'behavior_model.py')]
write('script_manifest.json',script_manifest)
manifest=[ref(p) for p in sorted(Path('evidence').rglob('*')) if p.is_file()]
write('evidence_manifest.json',manifest)
(OUT/'README.md').write_text('''# Condition A learning package r002

Read rulebook.md and rules.json for bounded claims, coverage.json for remaining uncertainty, and objects.json for observed identities. r001 is the retained parent. This package used the public origin, fixture keys and native browser observations; no private tasks were available.

The separate behavior_model.py exports predict(observation, intent) and returns the public prediction shape. Its module docstring documents input keys. Untested values and whole-task compositions return unknown; per-action predictions are not whole-task scores.

scripts.py supplies native Playwright entry points. Supply current observed record IDs and artist/title selection, and include both scripts.py and behavior_model.py in execute_script modules. A temporary task file may import scripts and export run(h). Read the runtime guide for exact tool usage. The default scripts.run only opens the home page. The runtime handles locator confirmation/scrolling and exports observations around each action.

Helpers return None on missing, ambiguous, invisible or disabled controls. Stop dependent work on None. Create Listing explicitly selects and verifies the requested release, verifies field values, submits once, and records row-count readback. Review exported network/DOM evidence before retrying any write. Visually identical inactive listings640/646 intentionally remain ambiguous to the reusable deactivation helper.

All evidence_refs use original workspace-relative browser export paths and sha256. evidence_manifest.json lists every exported file. failures.json separates locator/implementation problems from observed business rejection. Pre-execution policy errors have no fabricated browser evidence. The final wrappers were exercised as detailed in coverage.json; no independent success score is claimed.

The learning account/state may be reset before evaluation. Do not treat final observed availability/status as a permanent rule. Keep frozen rules/model unchanged during private tasks; temporary native scripts and current-task supervision are allowed by the contract.
''')
print('Objects:',len(releases),'releases,',len(listings),'listings,',len(orders),'orders;',len(manifest),'original evidence files;',len(journal),'journal entries')
