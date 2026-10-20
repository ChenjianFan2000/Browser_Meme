import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
cases=json.loads((ROOT/'harness/sites/discogs/cases.json').read_text(encoding='utf-8-sig'))


def check(path, op, value):
    return dict(path='after.'+path,op=op,value=value)


def same(path):
    return dict(path='after.'+path,op='eq',value_from='before.'+path)


def step(id, rule, action, checks, unchanged=True, wait=None):
    return dict(id=id,rule_ids=[rule],action=action,expect=[dict(id='expected',checks=checks)],
                invariants=[same('backend.table_hashes')] if unchanged else [],
                wait=wait or {'kind':'load','value':'domcontentloaded'})


def open_step(id,path,rule,text):
    return step(id,rule,{'kind':'open','url':path},[check('ui.text','contains',text)],wait={'kind':'text','value':text})


def login(p):
    return [open_step('login_open','/login','AUTH-LOGIN','Sign in'),
            step('login_username','AUTH-LOGIN',{'kind':'fill','selector':'main form input:not([type="password"])','value':p['username']},[check('ui.fields.login_username','eq',p['username'])]),
            step('login_password','AUTH-LOGIN',{'kind':'fill','selector':'main input[type="password"]','value':p['password']},[check('ui.text','contains','Sign in')]),
            step('login_submit','AUTH-LOGIN',{'kind':'click','selector':'main button:has-text("Sign in")'},[check('ui.url','matches',r'/$'),check('ui.text','contains','Trending Releases')],wait={'kind':'url','value':'/'})]


for c in cases:
    p=c['parameters']; kind=p['kind']; steps=[]
    if kind=='invalid_login':
        steps=login(p)
        steps[-1]=step('login_submit','AUTH-LOGIN',{'kind':'click','selector':'main button:has-text("Sign in")'},[check('ui.text','contains','Invalid credentials'),check('ui.url','contains','/login')],wait={'kind':'text','value':'Invalid credentials'})
    elif kind=='catalog_search':
        steps=[open_step('search_open','/','CAT-HOME','Trending Releases'),
               step('search_fill','CAT-SEARCH',{'kind':'fill','selector':'header input[name="q"]','value':p['query']},[check('ui.fields.query','eq',p['query'])]),
               step('search_submit','CAT-SEARCH',{'kind':'click','selector':'header button[type="submit"]'},[check('ui.text','contains','Results for'),check('ui.fields.target_release_count','gte',1)],wait={'kind':'text','value':'Results for'}),
               step('search_release','CAT-DETAIL',{'kind':'click','selector':'main a[href="/release/221"]'},[check('ui.url','contains','/release/221'),check('ui.text','contains','Tracklist')],wait={'kind':'text','value':'Tracklist'})]
    else:
        if kind!='anonymous_collection': steps+=login(p)
        if kind in ('anonymous_collection','collection_add','wantlist_add'):
            steps+=[open_step('release_open','/release/221','CAT-DETAIL','Tracklist')]
            member='wantlist' if kind=='wantlist_add' else 'collection'
            button='Add to Wantlist' if member=='wantlist' else 'Add to Collection'
            if kind=='anonymous_collection':
                steps+=[step('membership_add','AUTH-GATE',{'kind':'click','selector':'button:has-text("Add to Collection")'},[check('ui.url','contains','/login?next='),check('ui.text','contains','Sign in')],wait={'kind':'url','value':'/login'})]
            else:
                steps+=[step('membership_add','MEM-WANTLIST' if member=='wantlist' else 'MEM-COLLECTION',{'kind':'click','selector':f'button:has-text("{button}")'},[check(f'backend.{member}_ids','contains',221)],False,{'kind':'enabled','value':f'button:has-text("{button}")'}),
                        open_step('membership_verify','/me/'+member,'MEM-WANTLIST' if member=='wantlist' else 'MEM-COLLECTION','My Wantlist' if member=='wantlist' else 'My Collection')]
                steps[-1]['expect'][0]['checks'] +=[check('ui.fields.target_release_count','gte',1),check(f'backend.{member}_ids','contains',221)]
                steps[-1]['wait']={'kind':'selector','value':'main a[href="/release/221"]'}
        elif kind in ('cart_add','checkout'):
            steps+=[open_step('marketplace_open','/sell/release/221','MKT-FILTER','Marketplace listings'),
                    step('cart_add','CART-ADD',{'kind':'click','selector':'main a[href="/cart?add=1"]'},[check('ui.url','matches',r'/cart$'),check('ui.text','contains','The Dark Side Of The Moon'),check('backend.cart_count','eq',1),check('backend.cart_total_cents','gt',0)],False,{'kind':'url','value':'/cart'})]
            if kind=='checkout':
                steps+=[step('checkout','CHECKOUT',{'kind':'click','selector':'main button:has-text("Checkout")'},[check('ui.text','contains','Your cart is empty.'),check('backend.cart_count','eq',0),check('backend.latest_demo_order.status','eq','paid'),check('backend.latest_demo_order.total_cents','gt',0)],False,{'kind':'text','value':'Your cart is empty.'})]
        elif kind=='seller_create_deactivate':
            steps+=[open_step('seller_open','/sell','SELL-MANAGE','Sell on Discogs'),
                    step('seller_search_fill','CAT-SEARCH',{'kind':'fill','selector':'main input[placeholder="Search releases..."]','value':'The Dark Side Of The Moon'},[check('ui.fields.seller_query','eq','The Dark Side Of The Moon')]),
                    step('seller_search','SELL-SEARCH-PROXY',{'kind':'click','selector':'main button:has-text("Search")'},[check('ui.text','contains','Field required'),check('ui.fields.create_disabled','eq','')],True,{'kind':'text','value':'Field required'})]
            c['execution_limitation']='Source predicts original UI search cannot select a release; retain task goal and report incomplete. Do not bypass using API or injected page state.'
    c['steps']=steps

readouts={'query':{'selector':'header input[name="q"]','kind':'value'},
          'login_username':{'selector':'main form input:not([type="password"])','kind':'value'},
          'target_release_count':{'selector':'main a[href="/release/221"]','kind':'count'},
          'seller_query':{'selector':'main input[placeholder="Search releases..."]','kind':'value'},
          'create_disabled':{'selector':'main button:has-text("Create Listing")','kind':'attr','attribute':'disabled'}}
(OUT/'plan.json').write_text(json.dumps(dict(schema_version=2,revision='pw-v001',model='gpt-6.1-sol',readouts=readouts,cases=cases),indent=2)+'\n',encoding='utf-8')
