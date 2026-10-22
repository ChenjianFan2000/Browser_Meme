"""Offline publication only; consumes exported browser evidence, never contacts site."""
import json, hashlib, shutil
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path('.')
CALLS={int(p.name.split('-')[1]):p for p in Path('evidence').glob('call-*')}
def ref(p):
 p=Path(p); return {'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def refs(*calls):
 return [ref(CALLS[c]/f) for c in calls for f in ['actions.jsonl','network.json']]
RULES=[]
def rule(i,s,c,status='verified',pre=None,branches=None):
 RULES.append({'id':i,'statement':s,'status':status,'preconditions':pre or ['Only the supplied fixture account and observed run state; no universal backend claim'],'branches':branches or [],'forbidden_side_effects':['No UI evidence licenses hidden state changes or automatic write retries'],'evidence_refs':refs(*c)})
rule('R01','The observed public home exposes search, Explore, Marketplace, Community, Cart and Account; accepting cookies removed its privacy banner.',[1,2])
rule('R02','With the fixture username and deliberately wrong password, Sign in rendered Invalid credentials; fixture credentials then reached home.',[4])
rule('R03','At the observed login form, visible Username or Email and Password text did not provide working get_by_label locators. main input index 0 and main input[type=password] worked.',[3,4])
rule('R04','In this authenticated session Account was a button; hovering exposed Collection, Wantlist and Sign out. The earlier signed-out Account was a link.',[2,5,6])
rule('R05','Release 1 already existed in collection. Repeating Add to Collection returned ok and left one account-list entry; its local Have counter rose from 1 to 2, then returned to 1 on navigation.',[6,8])
rule('R06','Adding release 1 to wantlist created one visible membership; repeating it returned ok and retained one entry. Local Want rose transiently to 4 after the repeat; a later canonical read was 3.',[7,8,9,21])
rule('R07','Release 12 was initially wanted but absent from collection. Adding it to collection persisted one entry while wantlist membership remained; release 1 also remained in both lists.',[6,7,8,9])
rule('R08','Searching Pink Floyd produced release links 153, 180, 221. Lowercase partial pink produced the same three identities in this catalog.',[10,19])
rule('R09','An empty submitted query rendered Enter a query in the search bar; the tested nonsense query rendered its query heading with no release cards.',[19])
rule('R10','Release 12 linked to a marketplace initially containing listing 145 melanie9414 at USD 31.34 and listing 144 zchandler55 at USD 36.55. Release 1 showed zero for sale.',[7,10])
rule('R11','For release 12 before own-listing creation, price_desc put USD 36.55 before USD 31.34; Germany restricted to the 92.7% seller. Germany plus min_rating 95 produced no listings; min_rating 95 alone returned the 97.4% Italy seller.',[11])
rule('R12','For release 12, minimum rating 101 was accepted as a filter query and rendered zero matching listings, without a range validation error.',[11])
rule('R13','Adding listing 145 from an empty cart created item 1 quantity 1 at 3134 cents; it persisted after navigation. Repeating the UI add changed the same item to quantity 2 and total 6268 cents.',[12,13])
rule('R14','Adding listing 144 for the same release created a separate cart item 2 for its other seller; combined total was 9923 cents. Rendered lines showed unit prices and omitted the quantity 2 visible in the UI-caused response.',[13])
rule('R15','Removing the melanie9414 cart line with quantity 2 removed that entire item, leaving zchandler55 at total 3655 cents across navigation.',[14])
rule('R16','On observed fresh sell form Create Listing was disabled before release selection. Searching the unique title Open-source exuding intranet automatically selected release 12 and enabled submission with defaults.',[14,15,16])
rule('R17','With release 12 selected and other defaults, negative price -1 and zero price disabled Create Listing. Price 1 enabled it; quantity 0 disabled it and quantity 2 enabled it. These are observed UI boundaries; backend validation outside UI remains unknown.',[15,16])
rule('R18','Creating release 12 with quantity 2, price 1234 cents, default conditions and US shipping, and distinct comments returned listing id 640. My Listings and marketplace readbacks showed active USD 12.34 quantity 2 owner listing.',[16])
rule('R19','Attempting to add the newly created own listing 640 to cart succeeded and persisted alongside the other seller item. Thus the proposed own-listing cart prohibition was false in this condition.',[17])
rule('H01','Own listings are always forbidden from cart.',[17],status='refuted',pre=['Counterexample: fixture account own active listing 640 for release 12'])
rule('R20','Deactivating listing 640 retained it as inactive in My Listings and removed it from release 12 marketplace. Its existing cart entry remained at 1234 cents, total 4889 with listing 144.',[18,21])
rule('R21','The observed Rock genre page was accessible through Explore > Genres. Following the footer Add Release link rendered a 404 page; backend submission capability is not determined by that missing page.',[19])
rule('R22','After sign-out, visits to collection, wantlist and sell redirected to login with next; a release 12 Add to Collection click while signed out redirected to login?next=%2Frelease%2F12.',[20])
rule('R23','Signed-out cart navigation redirected to login with next cart. Fixture sign-in then returned to cart with the prior business cart contents preserved.',[21])
rule('U01','Checkout behavior, stock limits, listing duplicates, arbitrary condition validation, and membership removal are not yet established.',[],status='unknown')

def publish(revision,parent,max_call,extra_rules=None,stop_reason=None):
 dest=Path('revisions')/revision
 dest.mkdir(parents=True,exist_ok=False)
 active=[r for r in RULES if all(int(Path(e['path']).parts[1].split('-')[1])<=max_call for e in r['evidence_refs'])]
 if extra_rules: active+=extra_rules
 allrefs=refs(*[c for c in sorted(CALLS) if c<=max_call])
 (dest/'rules.json').write_text(json.dumps(active,indent=2)+'\n')
 text=['Condition B prose knowledge; bounded independent browser learning.','No executable behavior-prediction model is included. Native execution scripts require supervision and readback.','Observed rules below concern this account, these objects and this run state only. Wider generalization is a hypothesis.','']
 for r in active:
  text += [r['id']+' ('+r['status']+'): '+r['statement']]
  for e in r['evidence_refs']: text.append('Evidence: '+e['path']+' sha256 '+e['sha256'])
  text.append('')
 text += ['Failure handling: preserve experiments 03, 05, 06 and 15 unchanged. Failures 03/05/06 are locator assumptions. Call 15 attempted a disabled click; classify UI business boundary and implementation failure to check enabled. Network and DOM confirm no listing submission from that disabled click.','Unknowns: hidden constraints, arbitrary accounts, write operations unavailable in this UI, effects beyond UI-caused public responses. Do not infer absent backend behavior from missing controls.','Per-action predictions are archived in original actions.jsonl. No whole-task outcome score was measured; predictions are expectations, not independent truth.']
 (dest/'rulebook.md').write_text('\n'.join(text)+'\n')
 class Links(HTMLParser):
  def __init__(self):super().__init__();self.links=[]
  def handle_starttag(self,t,a):
   d=dict(a)
   if t=='a' and d.get('href','').startswith('/'):self.links.append({'href':d['href'],'aria_label':d.get('aria-label')})
 pages=[]; links={}; logs=[]
 for c in sorted(CALLS):
  if c>max_call:continue
  folder=CALLS[c]; data=json.loads((folder/'result.json').read_text())
  observations=[]; before=None
  for line in (folder/'actions.jsonl').read_text().splitlines():
   v=json.loads(line)
   if v.get('kind')=='action_before': before=v
   if v.get('kind')=='observation':
    observations.append(v)
    if v.get('label','').startswith('after-') and before:
     logs.append({'experiment':c,'level':'per_action','why_selected':before.get('rationale'),'alternatives_considered':'Compare expected UI/result with rejection, no persistent change, or different record effect; narrow experiment named in rationale.','prediction':before.get('prediction'),'action':{'method':before.get('method'),'target':before.get('target')},'actual_evidence':{'url':v.get('url'),'visible_text':v.get('visible_text'),'dom_ref':ref(folder/v['dom'])},'classification':'observed; see experiment-level assessment and rule status, not a task success score','resulting_revision':revision,'evidence_refs':[ref(folder/'actions.jsonl')]});before=None
  for o in observations:
   if not o.get('url','').startswith('http'):continue
   f=folder/o['dom']; parser=Links();parser.feed(f.read_text())
   for a in parser.links:
    links.setdefault(a['href'],{'identity':a['href'],'kind':'DOM-discovered navigation target','relationship':'rendered anchor from observed page','actions':['navigate using observed link'],'uncertainty':'Link existence is not proof target is implemented; no unobserved backend inference','evidence_refs':[ref(f)]})
  final=data.get('last_observation') or {}
  pages.append({'call':c,'url':final.get('url'),'label':final.get('label'),'evidence_refs':[ref(folder/final['dom'])] if final.get('dom') else [],'uncertainty':'Page state at this call only'})
  classification='locator' if c in [3,5,6] else 'business_rule + implementation' if c==15 else 'browser_observation'
  logs.append({'experiment':c,'level':'experiment','why_selected':'See script step rationales and per-action predictions; independent browser discovery or discriminating experiment','alternatives_considered':'Acceptance, rejection, boundary, repeat and cross-page persistence as detailed in script rationales','prediction':'Per-action predictions archived separately; no whole-task prediction score','actual_evidence':{'status':data['status'],'error':data.get('error'),'final_url':final.get('url')},'classification':classification,'resulting_revision':revision,'evidence_refs':refs(c)})
 objects={'pages_observed':pages,'navigation_targets':list(links.values()),'business_objects':[{'identity':'release/1','title':'Business-focused directional knowledgebase','artist':'Walker Quartet','relationships':['collection','wantlist','zero marketplace listings observed'],'actions':['Add to Collection','Add to Wantlist','Marketplace'],'evidence_refs':refs(7,8,9),'uncertainty':'No visible removal workflow established'},{'identity':'release/12','title':'Open-source exuding intranet','artist':'Morgan Collective','relationships':['collection','wantlist','marketplace listings 144,145,640'],'actions':['membership adds','marketplace filters','cart add'],'evidence_refs':refs(7,10,16,18),'uncertainty':'Counts vary with run mutations'},{'identity':'listing/640','owner':'fixture account','release_id':12,'quantity':2,'price_cents':1234,'observed_state':'inactive after call 18; cart line retained','actions':['created','deactivated','added to cart'],'evidence_refs':refs(16,17,18),'uncertainty':'No reactivation tested'},{'identity':'cart items 1,2,3','relationship':'UI-caused responses identify cart items separately from listing IDs','actions':['add','repeat add','remove'],'evidence_refs':refs(12,13,14,17),'uncertainty':'Later mutations may change final state'}]}
 (dest/'objects.json').write_text(json.dumps(objects,indent=2)+'\n')
 coverage={'condition':'B','through_browser_call':max_call,'explored':['public home and cookie acceptance','login wrong and correct credentials','account menu and session persistence','collection and wantlist new/repeat/coexisting membership','artist and partial search; empty and no-match boundary','release data and marketplace filters/sorting','cart new/repeat/multi-seller/remove','seller listing selection, UI numeric boundaries, successful creation, ownership cart hypothesis, deactivation combination','Rock genre and Add Release 404'], 'unexplored':['checkout','inventory/stock caps','duplicate listing submission','other condition strings and numeric formats','membership deletion','arbitrary users or authorization beyond provided account','all other genre/community/editorial/footer targets'],'success_evidence':refs(4,8,9,12,13,14,16,17,18,21),'rejection_evidence':refs(4,20),'boundary_evidence':refs(11,15,16,19),'current_competing_hypotheses':[{'question':'Checkout with inactive listing','alternatives':['rejects','ignores inactive item','accepts all','placeholder'],'distinguishing_experiment':'Single checkout click with full readback; stop on unconfirmed write'},{'question':'Repeated identical listing creation','alternatives':['deduplicates','creates separate listing','rejects'],'distinguishing_experiment':'After first confirmed create, submit same form once and inspect My Listings and network'},{'question':'Stock cap on cart repeat','alternatives':['cap at inventory','unrestricted quantities'],'distinguishing_experiment':'Create controlled quantity-one listing; add twice with readback'}],'evidence_refs':allrefs,'limitations':['Only observed limited conditions are verified; executable prediction excluded for B','Missing controls and unavailable routes do not prove missing backend behavior','All browser calls include waits and locator failures; exported originals retained'],'stop_reason':stop_reason}
 (dest/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
 (dest/'exploration.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in logs))
 shutil.copyfile('reusable_scripts.py',dest/'scripts.py')
 rev={'revision':revision,'parent_revision':parent,'condition':'B','changed_rules':[r['id'] for r in active],'changed_scripts':['scripts.py']+[p.as_posix() for p in Path('experiments').glob('*.py')],'failure_category':['locator','business_rule','implementation'],'evidence_refs':allrefs,'rationale':'Independent native UI experiments; record bounded rules, preserve failed scripts and distinguish optimistic counters from canonical readback.','condition_constraints':'Prose rules and native execution only; no executable behavior model','scheduling_seed':1729}
 (dest/'revision.json').write_text(json.dumps(rev,indent=2)+'\n')
 return dest
if __name__=='__main__':
 print(publish('r001',None,21))
