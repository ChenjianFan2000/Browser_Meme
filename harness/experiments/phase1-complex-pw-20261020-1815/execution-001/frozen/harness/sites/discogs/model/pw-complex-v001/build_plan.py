"""Build source-authored predictions from independently frozen public task."""
import copy
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
cases = json.loads((ROOT/'harness/sites/discogs/complex_cases.json').read_text(encoding='utf-8'))
assert len(cases) == 1
case = copy.deepcopy(cases[0])
p = case['parameters']


def ck(path, op, value):
    return {'path': 'after.'+path, 'op': op, 'value': value}


def same(path):
    return {'path': 'after.'+path, 'op': 'eq', 'value_from': 'before.'+path}


def step(id, rules, action, checks, mutate=False):
    return {'id': id, 'rule_ids': rules, 'action': action,
            'expect': [{'id': 'expected', 'checks': checks}],
            'invariants': [] if mutate else [same('backend.table_hashes')],
            'wait': {'kind': 'native_explicit', 'value': 'Source-authored scripts.py bounded native URL/DOM/response assertion'}}


steps = [
 step('login_open', ['AUTH-LOGIN'], {'kind':'open','url':'/login'}, [ck('ui.text','contains','Sign in')]),
 step('login_username', ['AUTH-LOGIN'], {'kind':'fill','selector':'main form input:not([type="password"])','value':p['username']}, [ck('ui.fields.login_username','eq',p['username'])]),
 step('login_password', ['AUTH-LOGIN'], {'kind':'fill','selector':'main input[type="password"]','value':p['password']}, [ck('ui.text','contains','Sign in')]),
 step('login_submit', ['AUTH-LOGIN'], {'kind':'click','selector':'main button:has-text("Sign in")'}, [ck('ui.url','matches',r'/$'),ck('ui.text','contains','Trending Releases')]),
 step('search_fill', ['CAT-SEARCH'], {'kind':'fill','selector':'header input[name="q"]','value':p['search_query']}, [ck('ui.fields.query','eq',p['search_query'])]),
 step('search_submit', ['CAT-SEARCH'], {'kind':'click','selector':'header button[type="submit"]'}, [ck('ui.text','contains','Results for'),ck('ui.fields.target_release_count','eq',1)]),
 step('release_open', ['CAT-DETAIL'], {'kind':'click','selector':f'main a[href="/release/{p["release_id"]}"]'}, [ck('ui.text','contains','Tracklist'),ck('ui.url','contains',f'/release/{p["release_id"]}')]),
 step('marketplace_open', ['MKT-FILTER'], {'kind':'click','selector':f'main a[href="/sell/release/{p["release_id"]}"]'}, [ck('ui.text','contains','Marketplace listings'),ck('ui.fields.offer_rows','gte',2)]),
 step('rating_fill', ['MKT-FILTER'], {'kind':'fill','selector':'main input[name="min_rating"]','value':str(p['minimum_seller_rating'])}, [ck('ui.fields.minimum_rating','eq',str(p['minimum_seller_rating']))]),
 step('sort_select', ['MKT-FILTER'], {'kind':'select','selector':'main select[name="sort"]','value':p['sort']}, [ck('ui.fields.sort','eq',p['sort'])]),
 step('filter_apply', ['MKT-FILTER','TASK-SELECTION'], {'kind':'click','selector':'main button:has-text("Apply")'}, [ck('ui.url','contains','min_rating='),ck('ui.fields.offer_rows','gte',2),ck('ui.fields.offer_rows','lte',50)]),
 step('first_cart_add', ['CART-ADD','CART-READ','TASK-SELECTION'], {'kind':'click','selector':'main a[href^="/cart?add="]','binding':'exact public committed first offer href; scripts.py requires unique locator'}, [ck('backend.cart_count','eq',1),ck('backend.cart_total_cents','gt',0),ck('backend.cart_total_cents','lte',p['maximum_total_cents']),ck('ui.fields.cart_release_rows','eq',1)], True),
 step('return_release', ['CAT-DETAIL','TASK-MEMORY'], {'kind':'click','selector':f'main a[href="/release/{p["release_id"]}"]'}, [ck('ui.text','contains','Tracklist')]),
 step('return_marketplace', ['MKT-FILTER','TASK-MEMORY'], {'kind':'click','selector':f'main a[href="/sell/release/{p["release_id"]}"]'}, [ck('ui.text','contains','Marketplace listings')]),
 step('rating_refill', ['MKT-FILTER'], {'kind':'fill','selector':'main input[name="min_rating"]','value':str(p['minimum_seller_rating'])}, [ck('ui.fields.minimum_rating','eq',str(p['minimum_seller_rating']))]),
 step('sort_reselect', ['MKT-FILTER'], {'kind':'select','selector':'main select[name="sort"]','value':p['sort']}, [ck('ui.fields.sort','eq',p['sort'])]),
 step('filter_reapply', ['MKT-FILTER','TASK-MEMORY'], {'kind':'click','selector':'main button:has-text("Apply")'}, [ck('ui.fields.offer_rows','gte',2),ck('ui.fields.minimum_rating','eq',str(p['minimum_seller_rating']))]),
 step('second_cart_add', ['CART-ADD','CART-READ','TASK-MEMORY'], {'kind':'click','selector':'main a[href^="/cart?add="]','binding':'exact remembered second offer href; scripts.py requires unique locator'}, [ck('backend.cart_count','eq',2),ck('backend.cart_total_cents','gt',0),ck('backend.cart_total_cents','lte',p['maximum_total_cents']),ck('ui.fields.cart_release_rows','eq',2)], True),
 step('checkout', ['CHECKOUT','TASK-CHECKPOINT'], {'kind':'click','selector':'main button:has-text("Checkout")'}, [ck('backend.cart_count','eq',0),ck('backend.latest_demo_order.status','eq','paid'),ck('backend.latest_demo_order.total_cents','gt',0),ck('backend.latest_demo_order.total_cents','lte',p['maximum_total_cents']),ck('ui.text','contains','Your cart is empty.'),ck('ui.fields.checkout_disabled','eq','')], True)
]
# Independent exact offer/optimal-pair/business checks supplement these generic
# model predicates. Native script assertions verify public object commitments.
for s in steps:
    if s['id'] == 'checkout':
        s['expect'][0]['checks'] += [{'path':'after.backend.latest_demo_order.total_cents','op':'eq','value_from':'before.backend.cart_total_cents'}]
        s['invariants'] = [same('backend.collection_ids'),same('backend.wantlist_ids')]
    elif s['id'] in ('first_cart_add','second_cart_add'):
        s['invariants'] = [same('backend.orders'),same('backend.order_items'),same('backend.listings'),same('backend.collection_ids'),same('backend.wantlist_ids')]
case['steps'] = steps
case['checkpoints'] = [
 {'id':'selection_committed','before_step':'first_cart_add','reason':'First non-idempotent add: independently confirm authenticated demo, complete public candidate set and budget-feasible optimum before any cart write. Model commitment notes are evidence, never evaluator answer keys; exact actual pair is independently checked at before_checkout.'},
 {'id':'before_checkout','before_step':'checkout','reason':'Financial-state commit: Solar reviews public cart identity/quantity/price/sum and independent evaluator must explicitly continue; recheck unchanged state before single checkout.'}
]
readouts = {
 'login_username':{'kind':'value','selector':'main form input:not([type="password"])'},
 'query':{'kind':'value','selector':'header input[name="q"]'},
 'target_release_count':{'kind':'count','selector':f'main a[href="/release/{p["release_id"]}"]'},
 'minimum_rating':{'kind':'value','selector':'main input[name="min_rating"]'},
 'sort':{'kind':'value','selector':'main select[name="sort"]'},
 'offer_rows':{'kind':'count','selector':'main tbody tr:has(a[href^="/cart?add="])'},
 'cart_release_rows':{'kind':'count','selector':f'main section a[href="/release/{p["release_id"]}"]'},
 'checkout_disabled':{'kind':'attr','selector':'main button:has-text("Checkout")','attribute':'disabled'}
}
plan = {'schema_version':3,'revision':'pw-complex-v001','model':'gpt-6.1-sol',
        'supervision':{'review_timeout_seconds':240,'max_reviews_per_case':3,'case_seconds':900,'on_step_failure':'diagnose_and_stop'},
        'readouts':readouts,'cases':[case]}
(OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
