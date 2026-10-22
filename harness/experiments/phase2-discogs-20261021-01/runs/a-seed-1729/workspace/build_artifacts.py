"""Offline package builder. Reads only exported browser evidence, never the site."""
import json, hashlib, pathlib, shutil
ROOT=pathlib.Path(__file__).resolve().parent
D=sorted((ROOT/'evidence').glob('call-*'))
def ref(path):
    p=ROOT/path
    return {'path':str(path),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def er(call,file):return ref(str(D[call-1].relative_to(ROOT)/file))
def write(path,obj):
    (ROOT/path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def rule(id,statement,status,pre,branches,refs,forbidden=None):
    return {'id':id,'statement':statement,'status':status,'preconditions':pre,'branches':branches,'forbidden_side_effects':forbidden or ['Do not infer hidden effects beyond the observed business operation.'],'evidence_refs':refs}
def citations(refs):return '; '.join('`'+r['path']+'` (sha256 `'+r['sha256']+'`)' for r in refs)
R=[]
R.append(rule('R001','For the supplied account, submitting the prefilled login succeeded: a UI-caused response returned 200 with ok=true, navigation reached /, and subsequent pages showed a signed-in Account button.','verified',['Observed /login with its seeded prefilled form','Same supplied account; one Sign in click'],{'accepted':'Home navigation and later signed-in control','unknown':'Blank/invalid credentials, other accounts, signed-out session behavior'},[er(2,'obs-0007.html'),er(3,'network.json'),er(3,'obs-0006.html'),er(5,'obs-0003.html')]))
R.append(rule('R002','In the observed session Account was a link to /login before sign-in and a button after sign-in. Activating the signed-in button exposed Collection, Wantlist and Sign out; Collection navigated to /me/collection.','verified',['Observed desktop header','Authentication state must be read from current rendered role'],{'unsigned':'Account link','signed_in':'Account button and menu'},[er(2,'obs-0007.html'),er(4,'result.json'),er(6,'obs-0006.html'),er(6,'obs-0009.html')],['Do not retry the signed-out Account link selector after successful login; inspect the changed role.']))
R.append(rule('R003','The visited release /release/221 was Pink Floyd - The Dark Side Of The Moon (1973), with release details, tracklist, Add to Wantlist, Add to Collection and a marketplace link. Its marketplace initially displayed 25 for-sale rows.','verified',['Release 221 during this run before checkout'],{'release':'Details plus membership controls','marketplace':'/sell/release/221 shows seller, shipping country, conditions, price and Add to Cart links'},[er(5,'obs-0006.html'),er(8,'obs-0006.html')]))
R.append(rule('R004','When release 221 was absent from this account wantlist, one Add to Wantlist click succeeded and fresh /me/wantlist readback gained one card for 221 (10 to 11 cards).','verified',['Authenticated supplied account','Release 221 absent from observed wantlist baseline'],{'absent':'One membership added','present':'See R005; not a new insertion'},[er(6,'obs-0012.html'),er(6,'obs-0018.html'),er(6,'obs-0021.html'),er(6,'network.json')]))
R.append(rule('R005','For release 221 already in this account wantlist, one repeated Add to Wantlist returned ok=true and fresh list readback still contained one 221 card. The local sidebar Want briefly went from 4 to 5; later release navigation showed 4, not 5.','verified',['Supplied account','One confirmed prior wantlist addition for 221'],{'immediate':'Button remains Add to Wantlist; sidebar increments transiently','readback':'One card; stable aggregate Want=4 in later navigation'},[er(7,'obs-0003.html'),er(7,'obs-0006.html'),er(7,'obs-0009.html'),er(7,'obs-0012.html'),er(7,'network.json')],['Do not treat the immediate optimistic counter as another persistent membership.']))
R.append(rule('R006','For the supplied account and release 221, first Add to Collection gained one collection card (22 to 23 total); one repeat left one 221 card. Sidebar Have rose 2 to 3 on insertion and 3 to 4 on repeat, while a later release navigation showed 3.','verified',['Supplied account','Release 221 initially absent from collection','One addition followed by one repeat'],{'first':'Target collection membership inserted','repeat':'Membership remains one; transient count is not stored count'},[er(6,'obs-0009.html'),er(7,'obs-0015.html'),er(7,'obs-0018.html'),er(7,'obs-0024.html'),er(7,'obs-0027.html'),er(8,'obs-0003.html'),er(7,'network.json')]))
R.append(rule('R007','In the tested short sequence, adding release 221 to Collection after Wantlist did not remove it from Wantlist: both account pages contained one 221 card.','verified',['Sequence in calls 006-007','Same supplied account and release 221'],{'combination':'Both memberships present','unknown':'Other combinations, removals and other releases'},[er(7,'obs-0027.html'),er(7,'obs-0030.html')]))
R.append(rule('R008','From an empty account cart, clicking the visible Add to Cart link for the account own active listing 4 succeeded, producing one cart item with quantity 1, unit price 2145 cents and total USD 21.45; fresh navigation retained it.','verified',['Supplied account signed in','Listing 4 for release 221 active at 2145 cents','Empty cart'],{'accepted':'Own-listing insertion permitted in this case','unknown':'Other own listings or later sold status'},[er(8,'obs-0009.html'),er(9,'obs-0003.html'),er(9,'obs-0006.html'),er(9,'obs-0009.html'),er(9,'network.json')]))
R.append(rule('R009','With listing 4 quantity 1 in the cart, adding active listing 7 at 2285 cents created a second cart item and total 4430 cents. Repeating listing 7 once updated its same cart record from quantity 1 to 2, total 6715 cents. The visible line still showed the unit price USD 22.85; no quantity input was observed.','verified',['Supplied signed-in account','Listings 4 and 7 active in observed sequence','Listing 7 transitions only 0 to 1 and 1 to 2'],{'first':'Second cart record inserted','repeat':'Existing listing-7 cart record quantity incremented','unknown':'Quantity ceiling, other listings and later sold listings'},[er(9,'obs-0015.html'),er(9,'obs-0018.html'),er(9,'obs-0024.html'),er(9,'obs-0027.html'),er(9,'network.json')],['Do not read one visible line or unit price as proof of quantity one.','Do not reopen an add-bearing link to confirm; reopen /cart without query.']))
R.append(rule('R010','One Checkout click on the observed cart (listing 4 quantity 1, listing 7 quantity 2, USD 67.15) returned a paid order for those lines and cleared the cart. Fresh /cart navigation remained empty at USD 0.00. No separate confirmation step was observed before that write.','verified',['Supplied signed-in account','Exact observed two-line cart and prices','One checkout click'],{'accepted':'Paid order response plus empty persistent cart','unknown':'Other carts, empty/repeat checkout, payment systems outside this local fixture, stock/authorization rejection and total affected record count'},[er(10,'obs-0003.html'),er(10,'network.json'),er(10,'obs-0006.html'),er(10,'obs-0009.html')],['Never blindly repeat Checkout after missing confirmation.','An empty cart alone does not prove a paid order; inspect exported checkout response.']))
R.append(rule('R011','After that checkout, /sell readback showed the account listing 4 for release 221 as sold (quantity display remained 1). Its response also reported sold status. The full inventory accounting and marketplace result after sale were not observed.','verified',['Checkout sequence in R010','Observed own listing 4'],{'observed':'Status active before checkout and sold afterward','unknown':'Exact inventory decrement and listing 7 seller inventory'},[er(8,'obs-0012.html'),er(8,'network.json'),er(10,'obs-0012.html'),er(10,'network.json')]))
R.append(rule('R012','The visited /sell page rendered Find a release/Search, Media Condition, Sleeve Condition, Ships From, Quantity, Price (cents), Comments, Create Listing and My Listings with Deactivate buttons. No create, search or deactivation operation was executed.','verified',['Supplied signed-in account','DOM inspection of /sell'],{'observed':'Form and own listings visible','unknown':'Validation, creation, activation/deactivation and permissions'},[er(8,'obs-0012.html'),er(10,'obs-0012.html')]))
R.append(rule('R013','The runtime rejected a native get_attribute("value") inspection of a /sell input with BoundaryError and directed use of input_value for nonsecret controls. Browser exploration ended immediately after that call; this is a runtime access boundary, not a website business rejection.','verified',['Native getter attempt after four completed UI actions in call 010'],{'runtime':'Boundary denied; no additional browser submissions','site_business_rule':'No conclusion'},[er(10,'result.json'),er(10,'actions.jsonl')],['Do not use get_attribute("value") or retry the denied inspection.','Do not continue browser exploration after this boundary.']))
R.append(rule('H001','The membership set semantics observed for 221 may extend to other releases or users.','hypothesis',['Other releases/accounts untested'],{'distinguishing_experiment':'On an independently allowed future run, baseline another observed release, add once, repeat once, and reopen both membership page and release.'},[er(7,'network.json')]))
R.append(rule('H002','Repeated membership Add permanently increments the aggregate Have/Want count for release 221.','refuted',['Tested repeat in the authenticated supplied account'],{'counterexample':'Repeated Want displayed 5 then reloaded 4; repeated Have displayed 4 then reloaded 3.'},[er(7,'obs-0006.html'),er(7,'obs-0012.html'),er(7,'obs-0024.html'),er(8,'obs-0003.html')]))
R.append(rule('H003','The account cannot add its own listing 4 to its cart in the observed active/empty-cart condition.','refuted',['Own active listing 4 at 2145 cents','Empty cart'],{'counterexample':'Click succeeded and own listing persisted in cart.'},[er(9,'obs-0006.html'),er(9,'obs-0009.html'),er(9,'network.json')]))
R.append(rule('U001','Search matching, search pagination, marketplace filtering/sorting semantics, create listing validation, Deactivate effects, Remove effects and business rejection conditions remain unknown.','unknown',['Relevant affordances seen; operations not executed'],{'next':'Use small single-variable UI experiments only in a separately authorized future run; do not resume this stopped run.'},[er(1,'obs-0004.html'),er(8,'obs-0006.html'),er(8,'obs-0012.html'),er(9,'obs-0027.html')]))
initial=R[:4]+[rule('H000','A repeat Add to Wantlist might be idempotent, duplicate a record or toggle membership; no repeat has been tested in this checkpoint.','unknown',['Evidence cutoff call 006'],{'next':'After confirming membership, click Add once and reopen account list and release.'},[er(6,'obs-0021.html')])]

initial[2] = dict(initial[2], statement='The visited release /release/221 was Pink Floyd - The Dark Side Of The Moon (1973), with release details, tracklist, Add to Wantlist, Add to Collection and a marketplace link labeled 25 for sale. The marketplace itself was not yet visited at this checkpoint.', preconditions=['Release 221 during calls 005-006'], branches={'release':'Details plus membership controls','marketplace':'Observed href /sell/release/221 and link label only'}, evidence_refs=[er(5,'obs-0006.html')])

# Only DOM-derived anchors and naturally UI-caused public JSON form the object catalog.
class Anchors:
    pass
from html.parser import HTMLParser
class LinkParser(HTMLParser):
    def __init__(self):super().__init__();self.current=None;self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            a=dict(attrs);self.current={'href':a.get('href'),'aria_label':a.get('aria-label'),'text':''}
    def handle_data(self,data):
        if self.current is not None:self.current['text']+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.current['text']=self.current['text'].strip();self.links.append(self.current);self.current=None

def objects(cutoff):
    pages={}
    anchor_refs=[(1,'obs-0004.html'),(2,'obs-0007.html'),(5,'obs-0006.html'),(6,'obs-0009.html'),(6,'obs-0012.html')]
    if cutoff>6:anchor_refs += [(8,'obs-0006.html'),(8,'obs-0012.html'),(9,'obs-0027.html')]
    for c,f in anchor_refs:
        parser=LinkParser();parser.feed((D[c-1]/f).read_text())
        for x in parser.links:
            href=x['href']
            if href and href.startswith('/'):
                if href not in pages:pages[href]={'path':href,'labels':[],'visited':False,'evidence_refs':[],'uncertainty':'Anchor observed; behavior untested unless visited and separately ruled.'}
                p=pages[href];label=x['aria_label'] or x['text']
                if label and label not in p['labels']:p['labels'].append(label)
                r=er(c,f)
                if r not in p['evidence_refs']:p['evidence_refs'].append(r)
    for c,d in enumerate(D[:cutoff],1):
        for x in map(json.loads,(d/'actions.jsonl').read_text().splitlines()):
            if x.get('kind')=='observation' and x.get('url','').startswith('http://127.0.0.1:12042'):
                path=x['url'].replace('http://127.0.0.1:12042','')
                if path not in pages:pages[path]={'path':path,'labels':[],'visited':True,'evidence_refs':[er(c,x['dom'])],'uncertainty':'Visited page; only rules explicitly cited are verified.'}
                pages[path]['visited']=True
    records={}
    for c,d in enumerate(D[:cutoff],1):
        for x in json.loads((d/'network.json').read_text()):
            url=x.get('url','');b=x.get('body')
            if url.endswith(('/api/me/collection','/api/me/wantlist')) and isinstance(b,list):
                membership=url.rsplit('/',1)[-1]
                for row in b:
                    key='release:'+str(row['id'])
                    if key not in records:records[key]={'kind':'release','identity':row['id'],'title':row['title'],'artist':row['artist'],'year':row['year'],'observed_account_memberships':[],'evidence_refs':[],'uncertainty':'Only public card-level attributes and list membership observed; full details unvisited except 221.'}
                    if membership not in records[key]['observed_account_memberships']:records[key]['observed_account_memberships'].append(membership)
                    r=er(c,'network.json')
                    if r not in records[key]['evidence_refs']:records[key]['evidence_refs'].append(r)
    special=[{'kind':'account','identity':'supplied fixture account','credential_location':'h.fixture.account; values intentionally omitted','relationships':['owns observed collection/wantlist memberships','signed-in header menu'],'evidence_refs':[er(3,'network.json'),er(6,'obs-0006.html')],'uncertainty':'Only one account tested.'}]
    if cutoff>6:
        for c in (8,10):
            for x in json.loads((D[c-1]/'network.json').read_text()):
                if x.get('url','').endswith('/api/me/listings') and isinstance(x.get('body'),dict):
                    for row in x['body'].get('items',[]):
                        key='listing:'+str(row.get('id',row.get('listing_id')))
                        if key not in records:records[key]={'kind':'listing','identity':row.get('id',row.get('listing_id')),'observations':[],'evidence_refs':[],'uncertainty':'Own listing UI-caused response; create/deactivate not executed.'}
                        records[key]['observations'].append({'call':c,'public_response_fields':row})
                        records[key]['evidence_refs'].append(er(c,'network.json'))
        special += [
            {'kind':'listing','identity':7,'release_id':221,'seller_username':'hernandezernest53','price_cents':2285,'currency':'USD','observed_actions':['cart add once','repeat add once','checkout quantity 2'],'evidence_refs':[er(9,'network.json'),er(10,'network.json')],'uncertainty':'Other quantities, stock and seller inventory untested.'},
            {'kind':'cart','identity':'supplied account cart','relationships':['cart item 1 -> listing 4 quantity 1','cart item 2 -> listing 7 quantity 1 then 2'],'final_observed_state':'empty after checkout','evidence_refs':[er(9,'network.json'),er(10,'obs-0009.html'),er(10,'network.json')],'uncertainty':'Remove and quantity ceiling untested.'},
            {'kind':'order','identity':121,'status':'paid','total_cents':6715,'currency':'USD','items':[{'listing_id':4,'quantity':1,'price_cents':2145},{'listing_id':7,'quantity':2,'price_cents':2285}],'evidence_refs':[er(10,'network.json')],'uncertainty':'No order detail page discovered; generated identity is run-specific.'}]
    page_actions={
        '/':['Search submit: untested','Account link/button: observed','Navigate observed release links: 221 tested'],
        '/login':['Sign in with seeded prefilled form: successful; blank/invalid input untested'],
        '/release/221':['Add to Wantlist: first addition tested by cutoff006','Add to Collection: tested only after cutoff006','Navigate Marketplace: tested only after cutoff006'],
        '/me/collection':['Read account release cards','Open release links; removal controls not observed'],
        '/me/wantlist':['Read account release cards','Open release links; removal controls not observed'],
        '/sell/release/221':['Add listing4 and listing7 to Cart: tested','Media/Sleeve/Ships From/Rating filter and Sort/Apply: affordances only'],
        '/cart':['Checkout: one observed paid order','Remove: visible but not executed'],
        '/sell':['Find a release/Search: untested','Create Listing: untested','Deactivate own listing: visible but untested']}
    for page in pages.values():
        page['actions']=page_actions.get(page['path'],['Only a rendered navigation link was discovered; destination behavior unknown.'])
    for record in records.values():
        if record['kind']=='release':
            record['relationships']=['Listed in supplied account '+k+' at an observed point in the run' for k in record['observed_account_memberships']]
            record['actions']=['Open observed release card link'] + (['Add to Wantlist; tested first insertion by cutoff006'] if record['identity']==221 else [])
            if record['identity']==221 and cutoff>6:record['actions'] += ['Add to Collection; first and repeat tested','Repeat Wantlist Add tested','Navigate release marketplace tested']
        else:
            record['relationships']=['Own listing for release identified in public_response_fields.release_id']
            record['actions']=['Deactivate rendered; untested','Navigate corresponding release marketplace rendered']
    for obj in special:
        obj.setdefault('actions',[])
    return {'scope':'Observed supplied account and public catalog only','pages':list(pages.values()),'objects':list(records.values())+special,'route_templates':[{'template':'/release/{id}','status':'hypothesis outside visited 221','evidence_refs':[er(1,'obs-0004.html'),er(6,'obs-0012.html')]},{'template':'/cart?add={listing_id}','status':'Observed links; navigation performs a write, never use for readback','evidence_refs':[er(8,'obs-0006.html'),er(9,'network.json')]}] if cutoff>6 else []}

exps=[
('Initial discovery','Discover page type and affordances before choosing a business operation.',['Inspect initial UI','Guess a catalog route (discarded)'],'Home and account/search/catalog links observed.','observed',None),
('Login discovery','Use the observed Account link to learn actual sign-in UI.',['Account link','Guess login selectors (discarded)'],'/login rendered prefilled form.','observed',None),
('Prefilled login and mistaken empty-form assumption','Try a login boundary before supplying credentials; the setup was flawed because fields were already prefilled.',['Empty values reject','Seeded defaults authenticate'],'The click authenticated, contrary to prediction; a later label fill timed out on the new home page. This was not an empty-credential experiment.','implementation','locator'),
('Signed-in account locator mismatch','Inspect account destination after authentication.',['Original Account link remains','Role changes with authentication'],'The old link locator timed out; rendered control was an Account button. No business write was attempted by this failed locator.','locator','locator'),
('Corrected header inspection and release discovery','Inspect current roles and choose a visible release from its observed href.',['Continue guessing account links (discarded)','Read actual header roles and release links'],'Account button/menu links found; release 221 details and operations discovered.','observed',None),
('Membership baselines and first wantlist add','Establish both lists before a confirmed first insertion.',['Release already present','Release absent and new membership created'],'Collection had 22 cards, wantlist 10 without 221; one add returned ok and fresh wantlist gained 221.','observed',None),
('Repeated membership and short combination','Distinguish set semantics, duplicate rows and toggle; test collection after wantlist.',['Idempotent membership','Duplicate membership','Toggle removal'],'Repeat wantlist retained one card; first collection gained one card; repeat collection retained one; both lists retained 221. Local counters briefly incremented on repeats.','observed',None),
('Counter reload and marketplace/selling discovery','Separate transient optimistic counts from stored aggregates; inspect commercial affordances and cart baseline.',['Repeat permanently increments aggregate','Repeat count is local UI only'],'Release reload showed Have3 Want4; marketplace 25 rows; cart empty; /sell had create form and 21 own listings.','observed',None),
('Own cart eligibility and repeated external listing','Compare own-vs-other listing acceptance and repeat quantity-vs-duplicate behavior.',['Own listing rejected','Own listing accepted','Repeat increments quantity','Repeat idempotent'],'Own listing4 added at 2145; listing7 added at 2285; repeat7 increased same cart item to quantity2 and total6715. Fresh /cart confirmed each.','observed',None),
('Checkout and attempted control inspection','Distinguish checkout confirmation flow from immediate completion; removal was conditional on surviving rows.',['Separate confirmation','Immediate paid order','Empty cart without order'],'One checkout returned paid order121 total6715; cart cleared and stayed empty; own listing4 showed sold. No Remove executed. Later get_attribute(value) was denied; all browser exploration stopped.','implementation','implementation')]

def exploration(cutoff,revision):
    entries=[]
    for c,d in enumerate(D[:cutoff],1):
        title,why,alternatives,actual,classification,failure=exps[c-1]
        log=[json.loads(line) for line in (d/'actions.jsonl').read_text().splitlines()]
        before={x['action']:x for x in log if x.get('kind')=='action_before'}
        after={x['action']:x for x in log if x.get('kind')=='action_after'}
        entries.append({'type':'experiment','experiment_id':'E'+str(c).zfill(2),'script_path':str(sorted((ROOT/'experiments').glob('e'+str(c).zfill(2)+'_*.py'))[0].relative_to(ROOT)),'title':title,'why_selected':why,'alternatives_considered':alternatives,'prediction':{'level':'per_action','recorded_predictions':[x['prediction'] for x in before.values()],'whole_task_prediction':None},'actual_evidence':actual,'classification':classification,'failure_category':failure,'resulting_revision':revision,'evidence_refs':[er(c,'actions.jsonl'),er(c,'network.json'),er(c,'result.json')],'note':'Retrospective offline synthesis of original fsynced predictions; not an independent score.'})
        for action,b in before.items():
            a=after.get(action,{})
            obs=next((x for x in log if x.get('kind')=='observation' and x.get('dom')==a.get('observation')),None)
            failed=bool(a.get('error'))
            entries.append({'type':'action','experiment_id':'E'+str(c).zfill(2),'action_in_call':action,'why_selected':b.get('rationale'), 'alternatives_considered':alternatives,'prediction':{'level':'per_action','value':b['prediction']},'actual_evidence':{'method':b['method'],'target':b.get('target'),'error':a.get('error'),'url':obs.get('url') if obs else None,'visible_text':obs.get('visible_text') if obs else None},'classification':'locator' if failed else 'observed','runtime_classification':a.get('classification'),'failure_category':'locator' if failed else None,'resulting_revision':revision,'evidence_refs':[er(c,'actions.jsonl')]+([er(c,a['observation'])] if a.get('observation') else [])+[er(c,'network.json')],'limits':'Runtime generic unconfirmed action tag is retained. Manual observed classification refers to rendered evidence; business persistence is confirmed only by the later readbacks and network cited in rules.'})
    if cutoff==10:
        entries.append({'type':'boundary_stop','why_selected':'Inspect /sell form input metadata after confirmed checkout.','alternatives_considered':['get_attribute(value) (attempted and rejected)','input_value for nonsecret controls (runtime guidance; not retried)'],'prediction':None,'actual_evidence':'BoundaryError: active-code or input-value attribute is excluded; use input_value for nonsecret controls','classification':'implementation','runtime_failure_category':'boundary','resulting_revision':revision,'evidence_refs':[er(10,'result.json')],'continued_browser_actions':0})
    return entries

for version,cutoff,rules in [('001',6,initial),('002',10,R)]:
    dest='revisions/'+version+'/'
    write(dest+'rules.json',rules)
    write(dest+'objects.json',objects(cutoff))
    exp=exploration(cutoff,version)
    (ROOT/(dest+'exploration.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in exp))
    coverage={'evidence_cutoff_call':cutoff,'scope':'One supplied account; only release 221 detail and its marketplace fully visited. Other release cards and own listing summaries were observed, not their behaviors.','explored':[{'area':'Account and successful sign-in','evidence_refs':[er(2,'obs-0007.html'),er(3,'network.json'),er(6,'obs-0006.html')]},{'area':'Release221 and first wantlist addition','evidence_refs':[er(5,'obs-0006.html'),er(6,'obs-0021.html')]}], 'unexplored':['Incorrect/blank login and signed-out business actions','Search matching, pagination, genres, forum/blog and linked informational pages','Membership removal and other releases/accounts','Marketplace filter/sort application and no-results boundaries','Listing creation, form validation, deactivate/reactivate and editing','Cart removal, quantity ceiling, unavailable/inactive/sold listing handling','Empty/repeat/insufficient-stock checkout; other currencies; concurrent changes'],'success_evidence':[{'claim':'First wantlist addition persisted.','evidence_refs':[er(6,'obs-0021.html'),er(6,'network.json')]}],'rejection_evidence':{'business_rejection_observed':False,'reason':'Attempt called empty-login actually submitted prefilled credentials and succeeded; it cannot verify blank-input rejection. Locator failures are not business-rule rejections.','evidence_refs':[er(3,'actions.jsonl'),er(3,'network.json'),er(4,'result.json')]},'boundary_evidence':[],'competing_hypotheses':[{'question':'Does set-like membership generalize beyond release221?','status':'untested','proposed_distinguishing_experiment':'On a future allowed run, baseline another visible release, add, repeat, reopen list and release.','evidence_refs':[er(6,'obs-0021.html')]}], 'evaluation_limits':['No private tasks were supplied or consulted.','Predictions are forecasts, not independent task scores.','Snapshots and observed UI-caused responses bound all claims.']}
    if cutoff==10:
        coverage['explored'] += [{'area':'Wantlist and collection repeats, independent membership sequence','evidence_refs':[er(7,'network.json'),er(7,'obs-0030.html'),er(8,'obs-0003.html')]},{'area':'Own/external cart addition and repeat quantity aggregation','evidence_refs':[er(9,'network.json'),er(9,'obs-0027.html')]},{'area':'One paid checkout and sold own-listing readback','evidence_refs':[er(10,'network.json'),er(10,'obs-0009.html'),er(10,'obs-0012.html')]}]
        coverage['success_evidence'] += [{'claim':'Repeated adds retained one membership card; counters reloaded to stable values.','evidence_refs':[er(7,'network.json'),er(8,'obs-0003.html')]},{'claim':'Cart adds changed persisted quantities and total; checkout returned paid order and cleared cart.','evidence_refs':[er(9,'network.json'),er(10,'network.json'),er(10,'obs-0009.html')]}]
        coverage['boundary_evidence']=[{'kind':'runtime_access_boundary','category':'implementation','claim':'Native input value attribute read denied; browser exploration stopped.','evidence_refs':[er(10,'result.json')]}]
        coverage['repeats_and_combinations']=[{'sequence':'Add wantlist221 -> repeat -> add collection221 -> repeat -> reopen both lists','evidence_refs':[er(6,'actions.jsonl'),er(7,'actions.jsonl'),er(8,'obs-0003.html')]},{'sequence':'Add own listing4 -> add listing7 -> repeat7 -> Checkout -> fresh cart -> own listing sold','evidence_refs':[er(9,'actions.jsonl'),er(9,'network.json'),er(10,'actions.jsonl'),er(10,'network.json')]}]
        coverage['competing_hypotheses'] += [{'question':'Does cart quantity enforce available inventory and how do unavailable listings fail?','status':'unknown; only listing7 quantity1 to2 observed','proposed_distinguishing_experiment':'Future allowed run: discover explicit stock through permitted UI, confirm baseline, add up to a known boundary with readback after each; stop on unconfirmed write.','evidence_refs':[er(9,'network.json')]},{'question':'Do checkout effects generalize to empty or different carts?','status':'unknown','proposed_distinguishing_experiment':'In a separate allowed run, test empty checkout before preparing a single external listing, then one checkout with response and inventory readback.','evidence_refs':[er(10,'network.json')]}]
        coverage['budget_at_browser_stop']={'actual_ui_actions':44,'actual_ui_action_limit':300,'browser_script_submissions':10,'browser_script_submission_limit':40,'elapsed_seconds_authoritative_at_last_call':302.84254755100005,'inclusive_time_limit_seconds':7200,'stop_reason':'runtime_access_boundary; not budget exhaustion','evidence_refs':[er(10,'result.json'),er(10,'actions.jsonl')]}
    else:
        coverage['competing_hypotheses'] += [{'question':'Repeat membership may be a no-op, duplicate or toggle.','status':'unresolved at checkpoint cutoff','proposed_distinguishing_experiment':'Repeat one confirmed membership and reopen list and release.','evidence_refs':[er(6,'obs-0021.html')]}]
    write(dest+'coverage.json',coverage)
    revision={'revision':version,'parent_revision':None if version=='001' else '001','parent_revision_directory':None if version=='001' else 'revisions/001','condition':'A','model':'gpt-6.1-sol','scheduling_seed':1729,'changed_rules':[r['id'] for r in rules] if version=='001' else [r['id'] for r in R[4:]],'changed_scripts':['scripts.py','behavior_model.py'],'failure_category':'locator' if version=='001' else 'implementation','runtime_failure_category':None if version=='001' else 'boundary','evidence_refs':[er(c,'result.json') for c in range(1,cutoff+1)]+[er(c,'network.json') for c in range(1,cutoff+1)],'rationale':'Retrospective complete checkpoint published offline after exploration, using only calls001-006; not a claim that these files existed before later experiments.' if version=='001' else 'Best revision supported before the mandatory boundary stop. Added repeat/composition/cart/checkout evidence, refuted transient-count and own-listing-rejection hypotheses. Broader behaviors remain unknown. All browser work ended at call010.','failed_versions_preserved':['experiments/e03_login.py','experiments/e04_account_release.py']+(['experiments/e10_checkout_remove.py'] if version=='002' else []),'corrections':'e03 mislabeled prefilled login as empty; e04 reused a signed-out link role; final scripts inspect current state. Final scripts omit denied value attribute getter and are only offline syntax-checked.','evidence_integrity':'Original exported evidence retained unchanged; coordinator separately retains originals.'}
    write(dest+'revision.json',revision)
    book=['# Bounded browser rulebook — revision '+version,'','Condition A, independent gpt-6.1-sol, scheduling seed1729. Seed concerns experiment scheduling only. This document is a retrospective synthesis, not an independent correctness score. Only the supplied account and observed conditions are covered.','']
    if version=='002':book += ['Browser exploration stopped after the runtime denied reading an input value attribute in call010. No subsequent browser action or submission was made. All final script corrections were made offline. Evidence: '+citations([er(10,'result.json')])+'.','']
    for r in rules:
        book += ['## '+r['id']+' — '+r['status'],'',r['statement'],'','Conditions: '+'; '.join(r['preconditions'])+'.','','Branches/limits: '+json.dumps(r['branches'],ensure_ascii=False)+'.','','Evidence: '+citations(r['evidence_refs'])+'.','']
    book += ['## Evidence interpretation','','The runtime action log uses a generic unconfirmed classification even for many successful navigations. This package preserves that field in exploration.jsonl and separately classifies actual observations. Persistent business claims require the specific UI-caused response and subsequent readback cited above. A locator timeout is not a website rejection. The input-attribute boundary is a runtime restriction, not a business rule.','','Initial experimental predictions are preserved even when wrong. In particular, the empty-login label describes an invalid experimental setup: no fields were cleared before submitting the seeded form. No rejected-credential claim is supported. Evidence: '+citations([er(3,'actions.jsonl'),er(3,'network.json')])+'.','','## Using the package','','Load behavior_model.py and call predict(observation,intent) with explicit current observed facts. Follow model_interface.md in the final revision for the schema. Unknown means evidence is insufficient; it does not mean an action will fail. Original executed scripts remain in experiments/. Revised scripts.py offers native Playwright entry points; it is not an automatic action dispatcher or a claim of private-task success.']
    (ROOT/(dest+'rulebook.md')).write_text('\n'.join(book)+'\n')

# Whole evidence manifest contains every unchanged export, including screenshots.
manifest=[ref(str(p.relative_to(ROOT))) for p in sorted((ROOT/'evidence').rglob('*')) if p.is_file()]
write('revisions/002/evidence_manifest.json',manifest)
write('revisions/001/evidence_manifest.json',[x for x in manifest if any(x['path'].startswith(str(d.relative_to(ROOT))+'/') for d in D[:6])])
print('Built both complete revisions; evidence files:',len(manifest))
