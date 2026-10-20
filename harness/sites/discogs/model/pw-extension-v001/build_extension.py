import copy
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
anchor=json.loads((OUT.parent/'pw-v001/plan.json').read_text(encoding='utf-8'))
cases=json.loads((OUT.parents[4]/'harness/sites/discogs/extension_cases.json').read_text(encoding='utf-8'))
login=anchor['cases'][3]['steps'][:4]
readouts=copy.deepcopy(anchor['readouts'])
readouts.update({
 'consent_count':{'kind':'count','selector':'button:has-text("Accept All Cookies")'},
 'release_cards':{'kind':'count','selector':'main a[href^="/release/"]'},
 'listing_rows':{'kind':'count','selector':'main tbody tr:has(a[href^="/cart?add="])'},
 'checkout_disabled':{'kind':'attr','selector':'main button:has-text("Checkout")','attribute':'disabled'},
})


def ck(path,op,value): return {'path':'after.'+path,'op':op,'value':value}
def same(path):return {'path':'after.'+path,'op':'eq','value_from':'before.'+path}
def st(id,rule,action,checks,wait=None,mutate=False):
 return {'id':id,'rule_ids':[rule],'action':action,'expect':[{'id':'expected','checks':checks}],
         'wait':wait or {'kind':'load','value':'domcontentloaded'},'invariants':[] if mutate else [same('backend.table_hashes')]}
def op(id,url,rule,text):return st(id,rule,{'kind':'open','url':url},[ck('ui.text','contains',text)],{'kind':'text','value':text})
def click(id,selector,rule,checks,wait=None,mutate=False):return st(id,rule,{'kind':'click','selector':selector},checks,wait,mutate)
def fill(id,selector,value,rule='CAT-SEARCH'):return st(id,rule,{'kind':'fill','selector':selector,'value':value},[ck('ui.url','contains','/')])
def add(member,id):
 title='Add to Collection' if member=='collection' else 'Add to Wantlist'
 return click(id,f'button:has-text("{title}")','MEM-COLLECTION' if member=='collection' else 'MEM-WANTLIST',[ck('backend.'+member+'_ids','contains',221)],{'kind':'enabled','value':f'button:has-text("{title}")'},True)
def cartadd(id):return click(id,'main a[href="/cart?add=1"]','CART-ADD',[ck('ui.url','matches',r'/cart$'),ck('backend.cart_count','eq',1),ck('ui.text','contains','The Dark Side Of The Moon')],{'kind':'url','value':'/cart'},True)
for c in cases:
 k=c['id']; s=[]
 if k=='consent_persistence':
  s=[op('home','/','CAT-HOME','Trending Releases'),click('accept','button:has-text("Accept All Cookies")','UI-CONSENT',[ck('ui.fields.consent_count','eq',0)],{'kind':'hidden','value':'button:has-text("Accept All Cookies")'}),st('reload','UI-CONSENT',{'kind':'reload'},[ck('ui.fields.consent_count','eq',0)],{'kind':'text','value':'Trending Releases'})]
 elif k=='genre_navigation':
  s=[op('home','/','CAT-HOME','Trending Releases'),st('explore','UI-NAV',{'kind':'hover','selector':'header button:has-text("Explore")'},[ck('ui.text','contains','Genres')]),click('genre','header a[href="/genre/rock"]','CAT-GENRE',[ck('ui.text','contains','Rock Genre Overview')],{'kind':'text','value':'Rock Genre Overview'}),click('release','main a[href^="/release/"] >> nth=0','CAT-DETAIL',[ck('ui.text','contains','Tracklist')],{'kind':'text','value':'Tracklist'})]
 elif k.startswith('search_'):
  q=c['parameters']['query']; text='Enter a query in the search bar.' if not q else 'Results for'
  s=[op('home','/','CAT-HOME','Trending Releases'),fill('query','header input[name="q"]',q),click('submit','header button[type="submit"]','CAT-SEARCH',[ck('ui.fields.release_cards','eq',0),ck('ui.text','contains',text)],{'kind':'text','value':text})]
 elif k.startswith('market_'):
  s=[op('market','/sell/release/221','MKT-FILTER','Marketplace listings')]
  if k=='market_filter_none':s += [fill('origin','input[name="ships_from"]','phase1-no-country','MKT-FILTER')]
  if k=='market_filter_combo':
   for key in ('media_condition','sleeve_condition','ships_from'):
    item=fill('filter_'+key,f'input[name="{key}"]','','MKT-FILTER');item['action']['offer_cell']=key;s.append(item)
  if k!='market_filter_none':s +=[st('sort','MKT-FILTER',{'kind':'select','selector':'select[name="sort"]','value':'price_desc'},[ck('ui.url','contains','/sell/release/221')])]
  text='No listings match these filters.' if k=='market_filter_none' else 'Marketplace listings'
  s +=[click('apply','main button:has-text("Apply")','MKT-FILTER',[ck('ui.fields.listing_rows','eq' if k=='market_filter_none' else 'gt',0),ck('ui.text','contains',text)],{'kind':'text','value':text})]
  if k!='market_filter_none':s[-1]['verify_descending_prices']=True
 elif k in ('collection_duplicate','wantlist_duplicate','signout_gate'):
  member='wantlist' if k=='wantlist_duplicate' else 'collection'
  s=copy.deepcopy(login)+[op('release','/release/221','CAT-DETAIL','Tracklist'),add(member,'add_first')]
  if k!='signout_gate':
   s +=[add(member,'add_second'),st('reload','MEM-UI-COUNT',{'kind':'reload'},[ck('backend.'+member+'_ids','contains',221)],{'kind':'text','value':'Tracklist'}),op('verify','/me/'+member,'MEM-WANTLIST' if member=='wantlist' else 'MEM-COLLECTION','My Wantlist' if member=='wantlist' else 'My Collection')]
   s[-1]['wait']={'kind':'selector','value':'main a[href="/release/221"]'};s[-1]['expect'][0]['checks'] +=[ck('ui.fields.target_release_count','eq',1)]
  else:
   s +=[st('account','UI-NAV',{'kind':'hover','selector':'header button[aria-label="Account"]'},[ck('ui.text','contains','Sign out')]),click('signout','button:has-text("Sign out")','AUTH-LOGOUT',[ck('ui.text','contains','Trending Releases')],{'kind':'text','value':'Trending Releases'}),op('gate','/me/collection','AUTH-GATE','Sign in')]
   s[-1]['expect'][0]['checks'] +=[ck('ui.url','contains','/login?next=')]
 elif k=='cart_repeat_remove':
  s=copy.deepcopy(login)+[op('market_first','/sell/release/221','MKT-FILTER','Marketplace listings'),cartadd('add_first'),op('market_second','/sell/release/221','MKT-FILTER','Marketplace listings'),cartadd('add_second'),click('remove','main button:has-text("Remove")','CART-REMOVE',[ck('backend.cart_count','eq',0),ck('ui.text','contains','Your cart is empty.'),ck('ui.fields.checkout_disabled','eq','')],{'kind':'text','value':'Your cart is empty.'},True)]
  s[-2]['expect'][0]['checks'] +=[{'path':'after.backend.cart_total_cents','op':'gt','value_from':'before.backend.cart_total_cents'}]
 elif k=='anonymous_cart_return':
  s=[op('market','/sell/release/221','MKT-FILTER','Marketplace listings'),click('anonymous_add','main a[href="/cart?add=1"]','AUTH-GATE',[ck('ui.url','contains','/login?next='),ck('ui.text','contains','Sign in')],{'kind':'url','value':'/login'})]+copy.deepcopy(login[1:])
  s[-1]['wait']={'kind':'url','value':'/cart'};s[-1]['invariants']=[];s[-1]['expect'][0]['checks']=[ck('ui.url','matches',r'/cart$'),ck('backend.cart_count','eq',1)]
 c['steps']=s
(OUT/'plan.json').write_text(json.dumps({'schema_version':2,'revision':'pw-extension-v001','model':'gpt-6.1-sol','readouts':readouts,'cases':cases},indent=2)+'\n',encoding='utf-8')
