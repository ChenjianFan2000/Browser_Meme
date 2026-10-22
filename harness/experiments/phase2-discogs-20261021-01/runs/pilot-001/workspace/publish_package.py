"""Offline artifact synthesis from the preserved browser exports; no website access."""
import json, hashlib
from pathlib import Path
from html.parser import HTMLParser

ROOT=Path('.')
CALLS={int(p.name.split('-')[1]):p for p in Path('evidence').glob('call-*')}
def ref(path):
 p=Path(path)
 return {'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def refs(*pairs):
 out=[]
 for call,file in pairs:
  out.append(ref(CALLS[call]/file))
 return out
def dom(c,n): return (c,f'obs-{n:04}.html')
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def rule(id,statement,status,preconditions,branches,evidence,forbidden=None):
 return dict(id=id,statement=statement,status=status,preconditions=preconditions,branches=branches,forbidden_side_effects=forbidden or ['No API fetching, client script inspection, DOM mutation, or blind retry after unconfirmed write.'],evidence_refs=refs(*evidence))

initial=[
 rule('R01','At the initial home route /, the rendered header exposes catalog search, Explore/Marketplace/Community menus, Cart, and an Account link to /login.','verified',['Initial unauthenticated home observation, supplied origin'],['Account link destination is /login; authentication behavior not yet tested at this checkpoint.'],[dom(1,3)]),
 rule('R02','The observed login form displays Username or Email and Password text, but native get_by_label("Username or Email") did not identify a unique visible input. This is a locator failure, not a credential rejection.','verified',['/login DOM in calls 2 and 3'],['A password-type input and a sign-in form input are rendered; explicit structural targeting needs verification.'],[dom(2,6),dom(3,4),(3,'result.json')]),
 rule('U01','Membership, marketplace, selling, checkout and authentication business effects are not established at this initial checkpoint.','unknown',['Only observations 1–3 are included'],['Use normal UI experiments and persistent readback before making claims.'],[dom(1,3),dom(2,6)])
]

learned=json.loads(json.dumps(initial))+[
 rule('R03','For the supplied fixture username and the pilot invalid password, Sign in remained at /login and rendered Invalid credentials. Replacing the password with the supplied fixture password and submitting returned to /.','verified',['Observed login form','Only the two credential cases tested; secrets are not stored in this package'],['Invalid case: rendered rejection; valid case: home navigation and later authenticated header.','Authentication changes are excluded from target business record counts.'],[dom(4,12),dom(4,18),dom(5,4),dom(6,6)]),
 rule('R04','After successful login, the hydrated Account control is a button and its menu exposes Collection, Wantlist and Sign out. The initial Account-link locator failed before any account-menu click.','verified',['Supplied signed-in account','Wait for hydrated Account button'],['Use the observed role appropriate to authenticated state.','A fresh page can initially render an Account link while authentication hydrates; header role must be read again.'],[dom(4,19),dom(5,4),(5,'result.json'),dom(6,6)]),
 rule('R05','For release 84 absent from this account collection, clicking Add to Collection kept the Add label, showed sidebar Have 7 from baseline 6, and added one release-84 card to /me/collection; revisiting the release showed Have 7.','verified',['Signed-in supplied account','Release 84 initially absent from account collection','Baseline Have 6'],['Immediate main summary still showed Have 6 while sidebar showed 7.','Fresh list and release readback confirmed membership and count.'],[dom(6,9),dom(6,15),dom(7,6),dom(7,10),dom(7,14),(7,'network.json')]),
 rule('R06','For confirmed collection membership of release 84, one repeated Add to Collection produced sidebar Have 8 locally, but one collection card remained and a fresh release visit restored Have 7. The observed target membership behaved idempotently despite the local increment.','verified',['Signed-in supplied account','Release 84 already added once and persistently confirmed'],['No toggle removal or duplicated card was observed.','Do not use the immediate sidebar increment as evidence of another persistent membership.','Hidden metadata changes were not observed.'],[dom(8,9),dom(8,18),dom(9,3),(8,'network.json')]),
 rule('R07','The account could add release 84 to its wantlist while it was already in collection: Want 6 became 7, and the release appeared in both account lists.','verified',['Signed-in supplied account','Release 84 absent from baseline wantlist, present in collection'],['Collection and wantlist membership coexisted for this release; other releases and accounts are untested.'],[dom(8,3),dom(8,12),dom(8,15),dom(8,18),(8,'network.json')]),
 rule('R08','One repeated wantlist add for release 84 temporarily showed sidebar Want 8, while a fresh release visit returned Want 7. The Add to Wantlist label remained unchanged.','verified',['Signed-in supplied account','Confirmed wantlist membership of release 84'],['Persistent visible count did not increase on the repeat; absence of hidden writes is not independently proven.'],[dom(9,3),dom(9,6),dom(9,9),(9,'network.json')]),
 rule('R09','Release 84 links to /sell/release/84. Its initial table had seven listings sorted by ascending price, and Add to Cart controls were links whose href identifies the listing, rather than buttons.','verified',['Observed release-84 marketplace table'],['Listing 354: caseyjones17, Japan, USD17.19.','Listing 355: melanie9414, US, USD18.05.','A button locator failed before dispatching a cart add.'],[dom(9,12),dom(10,7),(10,'result.json')]),
 rule('R10','From an empty signed-in cart, clicking the UI Add to Cart link for listing 354 created one cart item with quantity 1, total 1719 cents, and the UI remained consistent after navigating to /cart.','verified',['Signed-in supplied account','Empty cart','Listing 354 visible in release-84 marketplace'],['Target changed record count is one cart item; order effects were not observed for this action.','The UI shows the release title and seller; quantity is exposed in the naturally caused cart response.'],[dom(11,3),dom(11,9),dom(11,12),(11,'network.json')]),
 rule('R11','After a confirmed quantity-1 add of listing 354, adding that exact listing again kept one cart item and increased quantity to 2, total 3438 cents; this persisted on /cart readback.','verified',['Signed-in supplied account','Only listing 354 in cart with quantity 1'],['The repeat is non-idempotent for this observed transition; no quantity above 2 or stock ceiling was tested.'],[dom(12,6),dom(12,9),(12,'network.json')]),
 rule('R12','Checkout with the observed cart containing listing 354 quantity 2 returned a paid order for 3438 cents, quantity 2, and cleared the cart to zero. A later visit confirmed the empty cart.','verified',['Signed-in supplied account','Only listing 354 quantity 2 in the cart'],['Observed response order id was 121; do not predict future IDs.','Total affected business record count, fulfillment and stock effects remain unknown.'],[dom(12,9),dom(12,12),(12,'network.json'),dom(14,3)]),
 rule('R13','Checkout was disabled when the signed-in cart was empty. No empty-cart backend submission was attempted.','verified',['Observed empty signed-in cart after checkout'],['UI boundary only; backend rejection conditions remain unknown.'],[dom(12,13),dom(14,3),(14,'result.json')]),
 rule('R14','From an empty cart, adding listing 355 showed seller melanie9414 and USD18.05. Removing this sole quantity-1 item returned to empty total zero, confirmed after a fresh visit.','verified',['Signed-in supplied account','Only listing 355 quantity 1 when Remove was clicked'],['A naturally caused DELETE response returned ok true.','Removal of quantity>1 or multiple-item carts is untested.'],[dom(14,9),dom(14,12),dom(14,15),(14,'network.json')]),
 rule('R15','Applying Ships From US and Sort price_desc to release 84 returned two rows priced USD37.63 then USD18.05. Adding Minimum Rating 99 yielded zero rows and No listings match these filters.','verified',['Observed release-84 marketplace','Other filter fields blank','Apply submitted the staged inputs'],['Only these exact filters and this release were tested.','Case sensitivity, substring semantics, condition matching and rating endpoints remain unknown.'],[dom(13,12),dom(13,18)]),
 rule('R16','Submitting the header search Pink Floyd returned three release cards: Assimilated grid-enabled open system, Re-contextualized asynchronous Graphical User Interface, and The Dark Side Of The Moon.','verified',['Header search query exactly Pink Floyd'],['Observed /search?q=Pink+Floyd; other search matching and pagination rules are unknown.'],[dom(15,9)]),
 rule('R17','In this authenticated /sell page, Create Listing was disabled before release selection. Searching the exact release-84 title returned a unique #84 result that was automatically selected.','verified',['Signed-in supplied account','Fresh /sell form','Exact query Open-architected maximized Local Area Network'],['No explicit result click was required in this one-result case.','Multiple-result behavior is unknown.'],[dom(15,12),dom(16,3),dom(16,9),(16,'result.json'),(16,'network.json')]),
 rule('R18','Creating a listing for release 84 with quantity 0, price 1729 cents, media Near Mint (NM or M-), sleeve Very Good Plus (VG+), Ships From US, and the pilot comment returned 422 and quantity validation Input should be greater than or equal to 1.','verified',['Signed-in supplied account','Selected release 84','Exact staged values from call 17'],['The validation was a real backend rejection naturally caused by the UI submission.','The list did not gain the proposed release; successful positive creation remains untested.'],[dom(17,18),dom(17,21),(17,'network.json')]),
 rule('R19','With selected release 84, quantity 1, price 0 cents and otherwise default selling fields, Create Listing was disabled. Attempting its native click timed out; execution stopped.','verified',['Exact staged sell form in call 18'],['UI disabled-state boundary is observed.','This is not evidence of backend price validation; no successful submission was observed.','Terminal action effect stays unconfirmed under the contract; no further browser script was run.'],[dom(18,12),dom(18,15),dom(18,18),(18,'result.json'),(18,'actions.jsonl'),(18,'network.json')]),
 rule('R20','The linked /add-release route rendered 404 This page could not be found when visited in this run.','verified',['Navigation to observed footer href /add-release'],['This route observation does not prove absence of backend release creation or another UI.'],[dom(15,15)]),
 rule('H01','The release-84 membership behavior may generalize to other releases and accounts.','hypothesis',['Only one release and one supplied account were tested'],['Distinguish using a different release, separate membership baseline, single add, repeat, and fresh readback in a future reset run.'],[dom(7,14),dom(9,9)]),
 rule('H02','Local membership counters likely update optimistically while stored membership is a set.','hypothesis',['Observed local repeat increments and stable fresh counts'],['No client code was inspected; only the visible discrepancy and responses are known.'],[dom(8,9),dom(9,3),dom(9,6),dom(9,9)]),
 rule('F01','For the observed release-84 repeat, collection addition toggles membership off or creates another visible collection card.','refuted',['One confirmed repeat of release-84 collection addition'],['The release remained once in collection and fresh Have remained 7.','Other data or hidden metadata are not covered by this refutation.'],[dom(8,18),dom(9,3)]),
 rule('F02','For listing 354 quantity 1, repeating Add to Cart leaves the target quantity and total unchanged.','refuted',['Observed listing 354 quantity 1→2 transition'],['Natural cart response showed quantity 2 and total 3438.'],[(12,'network.json'),dom(12,9)]),
 rule('U02','Successful listing creation, deactivation/reactivation, anonymous write behavior, stock limits, multi-seller checkout, cancellation, account-list removal and other catalog routes remain unknown.','unknown',['The run stopped at call-018 timeout'],['Missing or disabled controls establish UI state only, not backend absence.','Future distinguishing experiments are recorded in coverage.json and were not executed.'],[dom(15,12),(18,'result.json')])
]
# Earlier unknown is retained with its checkpoint-specific scope and resolved status.
learned[2]['statement']='At checkpoint 001, business effects were not established. The later bounded rules resolve some cases; all other business behavior remains unknown.'

summaries={
1:('Discover entry point without guessed paths',['Home may be login-gated','Public catalog may be rendered'],'Public catalog and observed links; no business operation.',None),
2:('Discover authentication UI via actual Account link',['Account page','Login form'],'/login rendered two visible field descriptions and Sign in.',None),
3:('Try native label targeting for sign-in',['Associated labels','Visual text without label association'],'Target uniqueness check failed before any credential fill; no login submission.','locator'),
4:('Correct selector from exported DOM; compare invalid and valid credentials',['Bad credentials accepted','Rejection with error','Valid fixture access'],'Invalid credentials rendered; valid fixture returned home.',None),
5:('Inspect authenticated account destination',['Account remains link','Account changes role after hydration'],'Account-link uniqueness/visibility check failed; fresh DOM showed Account button.','locator'),
6:('Use observed authenticated button and inspect collection plus release',['Menu navigation','Direct account destination'],'Menu and collection rendered; release 84 baseline Have6 Want6 and seven listings.',None),
7:('Single absent-membership add with independent readback',['Toggle','Duplicate insert','Set membership'],'Release 84 added to collection; baseline Have6→fresh7 and one new list card.',None),
8:('Repeat confirmed add and test collection+wantlist combination',['Repeat is set-like','Repeat adds count','Wantlist excludes collection'],'Repeat local Have8 but one card; wantlist addition succeeded and coexisted.',None),
9:('Separate local repeat feedback from persisted counters; inspect market',['Local counter persists','Fresh count restored'],'Fresh Have7, repeat local Want8→fresh7; market seven listings.',None),
10:('Baseline cart then target exact cheapest listing',['Add control is button','Add control is navigation link'],'Cart empty; Add-to-Cart button lookup failed before write; DOM revealed link.','locator'),
11:('Correct Add control role, one add then fresh cart',['Transient feedback only','Persistent cart item'],'Listing354 quantity1, total1719 persisted.',None),
12:('Repeat confirmed cart add then short checkout combination',['Idempotent add','Quantity increment','Checkout just navigates','Checkout creates paid order'],'Quantity2 total3438 persisted; Checkout returned paid order121 and cleared cart.',None),
13:('Combine observed country filter and descending sort, then rating boundary',['Staged fields auto-apply','Apply required','High rating yields no matches'],'US two rows37.63,18.05; rating99 no matches.',None),
14:('Fresh checkout readback, UI disabled boundary, distinct add/remove',['Clear transient only','Empty checkout enabled','Remove persists'],'Empty Checkout disabled; listing355 added then removed and fresh cart empty.',None),
15:('Broaden to exact artist search and discovered contribution routes',['Release search only','Artist records too','Add-release form available'],'Pink Floyd three releases; selling form and own listings; /add-release404.',None),
16:('Inspect selection boundary and unique selling search',['Explicit result selection required','First/unique result auto-selected'],'Create disabled before selection; unique#84 auto-selected.',None),
17:('Hold price positive while testing quantity lower boundary',['Quantity0 allowed','Quantity minimum1'],'Natural422 quantity validation, no proposed listing appeared.','business_rule'),
18:('Hold quantity1 while testing price zero',['Zero price allowed','UI blocks zero','Backend rejects zero'],'Price0 disabled Create Listing; helper omitted enabled check; native click timed out. Stopped without retry.','implementation')
}
scriptfiles=sorted(Path('experiments').glob('[0-9]*.py'))
log=[]
for c,d in sorted(CALLS.items()):
 why,alts,outcome,failure=summaries[c]
 raw=[json.loads(x) for x in (d/'actions.jsonl').read_text().splitlines()]
 result=json.loads((d/'result.json').read_text())
 log.append({'kind':'experiment','experiment':f'E{c:03}','script_path':scriptfiles[c-1].as_posix(),'why_selected':why,'alternatives_considered':alts,'prediction':'See original per-action action_before predictions; no whole-task prediction was issued.','actual_evidence':outcome,'classification':failure or 'observed_success','failure_category':failure,'write_effect':'unconfirmed_terminal_attempt' if c==18 else 'see_per_action_and_rules','resulting_revision':'001' if c<=3 else '002','evidence_refs':refs((c,'actions.jsonl'),(c,'result.json'),(c,'network.json'))})
 before={x['action']:x for x in raw if x.get('kind')=='action_before'}
 after={x['action']:x for x in raw if x.get('kind')=='action_after'}
 for a,b in sorted(before.items()):
  z=after.get(a,{})
  classification='observed_ui_readback'
  action_outcome='UI operation returned; state limited to captured readback, not an assertion of business success.'
  if b['method']=='fill': action_outcome='Field staging read back; no target business write intended.'
  if c==4 and a==4: classification='business_rule';action_outcome='Invalid credentials rendered at /login.'
  if c==7 and a==2: classification='confirmed_business_change';action_outcome='New collection membership confirmed by later independent list and release readback.'
  if c==8 and a==3: classification='confirmed_repeat';action_outcome='Local Have8; fresh Have7 and one account card. Target membership unchanged.'
  if c==8 and a==4: classification='confirmed_business_change';action_outcome='Wantlist membership added while collection membership remained.'
  if c==9 and a==2: classification='confirmed_repeat';action_outcome='Local Want8, fresh Want7; persistent visible count stable.'
  if (c,a) in [(11,3),(12,2),(14,3),(14,4)]: classification='confirmed_business_change';action_outcome=outcome
  if c==12 and a==4: classification='confirmed_business_change';action_outcome='Natural response paid order121,3438cents,qty2; cart cleared and later fresh empty.'
  if c==15 and a==5: classification='business_rule';action_outcome='Rendered 404 on /add-release; not backend absence.'
  if c==17 and a==7: classification='business_rule';action_outcome='Natural422 greater_than_equal validation for quantity0.'
  if z.get('error'): classification='unconfirmed';action_outcome='Timed out on disabled Create Listing. Stop rule applied; no retry. Native auto-wait repeated enabled-state checks within one attempted UI action.'
  er=[(c,'actions.jsonl')]
  if b.get('observation'):er.append((c,b['observation']))
  if z.get('observation'):er.append((c,z['observation']))
  # Use the explicit observe after an action, if available, rather than only a generic runtime screenshot.
  for x in raw:
   if x.get('kind')=='observation' and x.get('label')==b.get('rationale'):
    er.append((c,x['dom']))
  log.append({'kind':'action','experiment':f'E{c:03}','action_in_call':a,'method':b['method'],'why_selected':b.get('rationale'),'alternatives_considered':alts,'prediction_scope':'action','prediction':b['prediction'],'actual_evidence':action_outcome,'classification':classification,'runtime_classification':z.get('classification'),'error':z.get('error'),'resulting_revision':'001' if c<=3 else '002','evidence_refs':refs(*er)})
log.insert(0,{'kind':'offline_setup','why_selected':'Discover workspace and runtime; inspect fixture key structure only','alternatives_considered':['rg unavailable → directory listing and HTML parser','python unavailable → python3'],'prediction':None,'actual_evidence':'rg and python commands were unavailable. One preliminary execute_script request had a missing script file and did not allocate a browser call. Corrected offline; authoritative browser calls begin at call001.','classification':'implementation','resulting_revision':'001','evidence_refs':[]})

class Links(HTMLParser):
 def __init__(self):super().__init__();self.active=None;self.depth=0;self.links=[]
 def handle_starttag(self,t,a):
  a=dict(a)
  if t=='a': self.active={'href':a.get('href'),'aria_label':a.get('aria-label'),'text':''}
 def handle_data(self,d):
  if self.active:self.active['text']+=d+' '
 def handle_endtag(self,t):
  if t=='a' and self.active:
   self.active['text']=' '.join(self.active['text'].split());self.links.append(self.active);self.active=None

pages={};release_objects={}
# Register routes visible in selected rendered DOM only; no routes guessed from API names.
for c,n in [(1,3),(2,6),(6,6),(6,9),(6,15),(8,3),(8,15),(9,12),(11,12),(13,12),(13,18),(15,9),(15,12),(15,15)]:
 p=CALLS[c]/f'obs-{n:04}.html';parser=Links();parser.feed(p.read_text())
 for item in parser.links:
  href=item['href']
  if not href or not href.startswith('/'):continue
  e=pages.setdefault(href,{'path':href,'link_texts':[],'discovery':'rendered_href','visited':False,'evidence_refs':[],'uncertainty':'Link discovery alone establishes neither page existence nor backend behavior.'})
  for label in [item['text'],item['aria_label']]:
   if label and label not in e['link_texts']:e['link_texts'].append(label)
  r=ref(p)
  if r not in e['evidence_refs']:e['evidence_refs'].append(r)
  if href.startswith('/release/') and href.split('/')[-1].isdigit():
   release_objects[href.split('/')[-1]]={'id':int(href.split('/')[-1]),'type':'release','path':href,'observed_card_text':item['text'],'actions':['open release'],'evidence_refs':[r],'uncertainty':'Card identity only unless separately detailed; titles need not be unique.'}
for c,d in sorted(CALLS.items()):
 for line in (d/'actions.jsonl').read_text().splitlines():
  x=json.loads(line)
  if x.get('kind')!='observation':continue
  url=x.get('url','')
  if not url.startswith('http://127.0.0.1:12042'):continue
  path=url[len('http://127.0.0.1:12042'):]
  e=pages.setdefault(path,{'path':path,'link_texts':[],'discovery':'UI_navigation_or_form_submission','visited':False,'evidence_refs':[],'uncertainty':'Behavior only established by bounded rules.'})
  e['visited']=True
  r=ref(d/x['dom'])
  if not any(y['path']==r['path'] for y in e['evidence_refs']) and len(e['evidence_refs'])<3:e['evidence_refs'].append(r)
release_objects['84'].update({'title':'Open-architected maximized Local Area Network','artist':'Chavez Trio','year':2016,'label':'Schneider Records — SCHN-1016','format':'1 x CD, LP, Reissue','country':'Canada','released':'2016-08-17','genre':'Hip Hop','style':'Boom Bap','actions':['Add to Collection','Add to Wantlist','Marketplace (7 for sale)'],'baseline_counts':{'have':6,'want':6,'for_sale':7},'fresh_counts_after_adds':{'have':7,'want':7},'evidence_refs':refs(dom(6,15),dom(9,9)),'uncertainty':'One supplied account; global counts are observed values, not permanent invariants.'})
listings=[]
for id,seller,country,price,media,sleeve in [(354,'caseyjones17','Japan',1719,'Near Mint (NM or M-)','Very Good Plus (VG+)'),(355,'melanie9414','US',1805,'Very Good Plus (VG+)','Mint (M)'),(351,'frazierdanny22','Australia',2224,'Very Good Plus (VG+)','Mint (M)'),(350,'barnesbrandy50','UK',2334,'Very Good Plus (VG+)','Good (G)'),(349,'caseyjones17','Netherlands',3484,'Near Mint (NM or M-)','Very Good (VG)'),(353,'jenniferross18','US',3763,'Very Good Plus (VG+)','Very Good (VG)'),(352,'carl9510','France',4113,'Good (G)','Very Good (VG)')]:
 listings.append({'id':id,'type':'marketplace_listing','release_id':84,'seller':seller,'ships_from':country,'price_cents':price,'currency':'USD','media_condition':media,'sleeve_condition':sleeve,'actions':['Add to Cart via observed /cart?add='+str(id)+' link'],'evidence_refs':refs(dom(9,12)),'uncertainty':'Only 354 and 355 were added; current stock and other listing writes are unknown.'})
objects={'pages':list(pages.values()),'releases':list(release_objects.values()),'listings':listings,'account':{'identity':'supplied public-fixture account, credential values omitted','actions':['Sign in','Account menu','Collection','Wantlist','Sign out control (untested)'],'relationships':['collection ↔ release','wantlist ↔ release','owns marketplace listings','cart items reference listings'],'evidence_refs':refs(dom(6,6),dom(6,9),dom(8,15),dom(15,12)),'uncertainty':'Only this account; anonymous and cross-account behavior untested.'},'observed_order':{'id':121,'status':'paid','total_cents':3438,'currency':'USD','items':[{'listing_id':354,'quantity':2,'price_cents':1719}],'actions':[],'evidence_refs':refs((12,'network.json')),'uncertainty':'Response identity; no orders UI or cancellation discovered.'},'cart':{'observed_item_id':1,'transitions':['empty→listing354 qty1→listing354 qty2→checkout→empty','empty→listing355 qty1→remove→empty'],'evidence_refs':refs((11,'network.json'),(12,'network.json'),(14,'network.json')),'uncertainty':'No multi-item or stock-boundary exploration.'}}

unknowns=[
 'Successful positive listing creation and listing deactivation/reactivation were not tested.',
 'Zero-price backend acceptance/rejection is unknown; only disabled UI and timed-out click were observed.',
 'Terminal write effect remains conservatively unconfirmed; the run stopped without a browser retry.',
 'Anonymous and cross-account writes, sign-out, account-list removal and membership generalization are unknown.',
 'Quantity ceilings, stock decrements, mixed currencies, multi-seller checkout, cancellation and fulfillment are unknown.',
 'Artist/label/genre/community pages, most footer routes and search case/substring/pagination behavior were not explored.',
 'Cookie settings/consent, newsletter subscription and account sign-out effects were not tested.',
 '/add-release rendered 404 but no inference about unavailable backend business behavior is made.',
 'Only 72/100 UI actions and 18/40 browser submissions were used because timeout required early stop.',
 'The final reusable scripts and predictor were compiled and checked offline; no browser validation followed the stop.'
]
coverage={'condition':'A','scheduling_seed':1729,'scheduling_note':'Seed is recorded for local scheduling. Experiment order was chosen adaptively for discriminating evidence; no claim about model sampling determinism.','scope':'One supplied account and origin; exploratory protocol pilot, no private tasks or formal scores.','budget_at_stop':{'actions':72,'action_limit':100,'script_calls':18,'script_call_limit':40,'elapsed_seconds_last_authoritative':439.66180173099974,'time_limit_seconds':3600,'runtime_stop_reason':None,'learner_stop_reason':'Contract stop after native UI click timeout in call018.'},'explored':['Home and observed navigation','Login invalid/valid cases','Account menu, collection and wantlist views','Release84 metadata and persistent membership additions','Confirmed repeats and collection/wantlist combination','Release84 marketplace listings, exact US/descending/rating99 filters','Cart adds, repeated quantity, checkout and sole-item removal','Pink Floyd header search','Seller unique release search and zero quantity validation','Zero-price disabled UI boundary','Observed Add Release route404'],'unexplored':unknowns,'success_evidence':refs(dom(7,10),dom(8,15),(11,'network.json'),(12,'network.json'),(14,'network.json')),'rejection_evidence':refs(dom(4,12),dom(17,21),(17,'network.json')),'boundary_evidence':refs(dom(13,18),dom(14,3),dom(16,3),dom(18,12),dom(15,15)),'repeat_evidence':refs(dom(8,9),dom(9,3),dom(9,6),dom(9,9),(12,'network.json')),'combination_evidence':refs(dom(8,15),dom(8,18),(12,'network.json'),dom(13,18)),'failure_evidence':refs((3,'result.json'),(5,'result.json'),(10,'result.json'),(18,'result.json')),'current_competing_hypotheses':[{'question':'Do membership semantics generalize?','alternatives':['Same set-like target membership elsewhere','Release/account-dependent behavior'],'status':'unknown outside release84','distinguishing_experiment':'In a future authorized/reset run, baseline a different release in both lists, add once, repeat after confirmation, compare separate list and fresh count.'},{'question':'What price-zero backend behavior exists?','alternatives':['UI blocks a backend-valid zero','Both UI and backend reject zero'],'status':'unknown; UI disabled only','distinguishing_experiment':'Only use a legitimate enabled rendered UI if discovered later; do not bypass disabled controls or call APIs.'},{'question':'Can positive listing creation and lifecycle succeed?','alternatives':['Valid listing creates active row','Further validation or account restrictions apply'],'status':'untested','distinguishing_experiment':'In a future run, exact selected release, positive price and quantity, single Create, inspect response/list/market before any follow-up; then deactivate once and read back.'},{'question':'What happens at cart stock limits?','alternatives':['Enforced limit','Higher quantities accepted'],'status':'untested beyond354 qty2','distinguishing_experiment':'Find UI-disclosed quantity/stock, baseline cart, add incrementally with persistent confirmation; stop on uncertainty.'}],'resolved_competing_hypotheses':[{'question':'Membership repeated add toggles/duplicates versus stable target set?','finding':'Stable fresh membership/count for observed repeat; local counters misleading.','evidence_refs':refs(dom(8,18),dom(9,3),dom(9,9))},{'question':'Cart repeated exact listing idempotent versus quantity increment?','finding':'Quantity1→2 and total1719→3438.','evidence_refs':refs((12,'network.json'))}],'terminal_failure':{'category':'implementation','action_classification':'unconfirmed','cause':'Helper checked uniqueness and visibility but not enabled; clicked disabled Create Listing.','response':'Preserved failure; stopped all browser submissions; final scripts add enabled-state guard.','evidence_refs':refs((18,'result.json'),(18,'actions.jsonl'),dom(18,18))}}

# Evidence index includes original browser exports, not derived assertions.
index=[]
for d in sorted(CALLS.values()):
 for p in sorted(d.iterdir()):
  if p.is_file():index.append(dict(ref(p),size_bytes=p.stat().st_size))
write('evidence_index.json',index)

for revision,ruleset,maxcall in [('001',initial,3),('002',learned,18)]:
 path=Path('revisions')/revision
 write(path/'rules.json',ruleset)
 selected=[x for x in log if x.get('experiment','E000')<=f'E{maxcall:03}']
 (path/'exploration.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in selected))
 if revision=='001':
  initpages=[x for x in objects['pages'] if any('/call-00'+str(c)+'-' in r['path'] for c in [1,2,3] for r in x['evidence_refs'])]
  
  for entry in initpages:
   entry['visited']=entry['path'] in ['/', '/login']
   entry['uncertainty']='Checkpoint001: link identity only unless path is / or /login.'
  write(path/'objects.json',{'pages':initpages,'objects':[],'uncertainty':'Retrospective initial DOM checkpoint; no business object mutations established.','evidence_refs':refs(dom(1,3),dom(2,6),dom(3,4))})
  write(path/'coverage.json',{'explored':['Initial public home','Login DOM'],'unexplored':['All target business mutations and credential outcomes at this checkpoint'],'success_evidence':refs(dom(1,3),dom(2,6)),'rejection_evidence':[],'boundary_evidence':[],'current_competing_hypotheses':['Visual labels may lack native association; inspect structural DOM before correction.'],'proposed_distinguishing_experiments':['Use observed form input structure; test invalid and valid fixture login separately.'],'evidence_refs':refs((3,'result.json'))})
  parent=None;changed=['R01','R02','U01'];failure='locator'
 else:
  write(path/'objects.json',objects);write(path/'coverage.json',coverage)
  parent='001';changed=[x['id'] for x in ruleset if x['id'] not in ['R01','R02']];failure='implementation'
 revision_meta={'revision':revision,'parent_revision':parent,'condition':'A','changed_rules':changed,'changed_scripts':['scripts.py','behavior_model.py'] if revision=='001' else ['experiments/004_auth_locator_fix.py','experiments/006_account_release_fix.py','experiments/011_cart_add_locator_fix.py','scripts.py: enabled-state guard and reusable native entry points','behavior_model.py: bounded evidence branches and unknown fallback'],'failure_category':failure,'evidence_refs':refs(*[(c,'result.json') for c in range(1,maxcall+1)]),'rationale':'Retrospective artifact checkpoint synthesized after browser learning; it does not claim the executable predictor generated earlier predictions. Original LLM per-action predictions remain in browser action logs. '+('Initial observations and failed label targeting preserved before corrected selector knowledge.' if revision=='001' else 'Add bounded rules from observed success, rejection, repeat, combinations and UI boundaries. Preserve original locator failures and terminal disabled-button timeout; final helper adds enabled guard without another browser run.'),'identity':{'learner_requested':'exact gpt-6.1-sol','condition':'A','scheduling_seed':1729,'protocol_pilot':True},'failure_categories_observed':['locator'] if revision=='001' else ['locator','business_rule','implementation','unconfirmed'],'whole_task_predictions':'None; no private tasks available. Per-action predictions and synthesized model are separate.','script_validation':'Offline compilation only; final guard not browser-retested after timeout.'}
 write(path/'revision.json',revision_meta)
 lines=['Browser behavior rulebook — revision '+revision,'','This is a limited exploratory checkpoint for condition A and scheduling seed 1729. Checkpoint artifacts were synthesized offline after learning. Original per-action predictions and observations are preserved. No whole-task scoring or private task access occurred.','']
 for r in ruleset:
  lines+=['**'+r['id']+' — '+r['status']+'**: '+r['statement'],'','Preconditions: '+'; '.join(r['preconditions'])+'.','']
  for branch in r['branches']:lines.append('- '+branch)
  lines.append('')
  if r['evidence_refs']:
   lines.append('Browser evidence:')
   lines.append('')
   for e in r['evidence_refs']:lines.append('- `'+e['path']+'` — sha256 `'+e['sha256']+'`')
   lines.append('')
 if revision=='002':
  lines+=['The terminal failed click is retained as unconfirmed. The disabled button is observed; backend price-zero validation is unknown. All subsequent work was offline artifact synthesis. See R19 evidence and coverage.json.','', 'Reusable execution: supply this revision’s scripts.py and behavior_model.py as modules to a native task wrapper. run(h) only opens home. Other functions expose login, search, membership, cart, filters and seller staging. They do not retry writes. Positive listing success is untested.','', 'Prediction interface: behavior_model.predict(observation, intent) returns the public shape. Structured current observations are required for business branches; intent scope defaults to action. scope=task, unsupported operations and out-of-sample conditions return unknown. Do not set authenticated or membership fields without permitted current observations.','']
 (path/'rulebook.md').write_text('\n'.join(lines))

# Annotate old helper entry point without overwriting the historical experiments/native.py.
with Path('revisions/001/scripts.py').open('w') as f:
 f.write(Path('experiments/native.py').read_text()+'\n\ndef run(h):\n    """Initial checkpoint: home observation only."""\n    print(go(h,"/","Initial checkpoint home inspection"))\n')
write('revisions/002/limitations.json',{'limitations':unknowns,'evidence_refs':refs((18,'result.json'),dom(18,18),dom(15,12))})
write('revisions/002/state_at_stop.json',{'authentication':'supplied account signed in, last observed in seller form','collection':'release84 added and fresh Have7','wantlist':'release84 added and fresh Want7','cart':'last independently confirmed empty after removal of listing355','order':'paid order121 for listing354 qty2 total3438 returned','proposed_listing':'quantity0 submission rejected422; subsequent price0 click timeout effect conservatively unconfirmed','do_not_retry_terminal_write':True,'evidence_refs':refs(dom(9,9),dom(14,15),(12,'network.json'),(17,'network.json'),(18,'result.json'))})
print(json.dumps({'revisions':['001','002'],'rules_final':len(learned),'exploration_records':len(log),'evidence_files':len(index),'discovered_page_links':len(pages),'release_cards':len(release_objects)}))
