"""Condition B native UI execution helpers. No executable behavior predictor.
The supervising learner supplies per-action expectations; defaults are unknown.
Use through phase2.execute_script, with modules if importing from another script.
run(h) is a read-only smoke entry point. No automatic write retries.
"""
import re

UNKNOWN = {'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['Supervisor has not supplied a bounded prediction for this action']}

def act(h, label, operation, expectation=None):
    h.expect(expectation or UNKNOWN, label)
    operation()
    return h.observe(label)

def navigate(h, path):
    return act(h,'navigate '+path,lambda:h.page.goto(h.origin+path))

def sign_in(h):
    """Start at an observed sign-in page; preserves its next destination."""
    p=h.page
    act(h,'username',lambda:p.locator('main input').nth(0).fill(h.fixture['account']['username']))
    act(h,'password',lambda:p.locator('main input[type=password]').fill(h.fixture['account']['password']))
    return act(h,'sign in',lambda:p.get_by_role('button',name='Sign in',exact=True).click())

def search(h, query):
    p=h.page
    act(h,'search query',lambda:p.get_by_placeholder('Search artists, albums and more...').fill(query))
    return act(h,'submit search',lambda:p.get_by_role('button',name='Search',exact=True).click())

def add_membership(h, release_path, kind):
    """Caller verifies prior membership. Leaves independent account-list readback."""
    if kind not in ['collection','wantlist']: raise ValueError('unknown membership kind')
    navigate(h,release_path)
    name='Add to Collection' if kind=='collection' else 'Add to Wantlist'
    act(h,'add '+kind,lambda:h.page.get_by_role('button',name=name,exact=True).click())
    return navigate(h,'/me/'+kind)

def filter_marketplace(h, fields, sort=None):
    """Start at a discovered marketplace page; fields use observed input names."""
    p=h.page
    for key,value in fields.items():
        if key not in ['media_condition','sleeve_condition','ships_from','min_rating']: raise ValueError('unknown field')
        act(h,'filter '+key,lambda k=key,v=value:p.locator('input[name='+k+']').fill(str(v)))
    if sort is not None:
        act(h,'sort',lambda:p.locator('select[name=sort]').select_option(sort))
    return act(h,'apply filters',lambda:p.get_by_role('button',name='Apply',exact=True).click())

def find_listing_release(h, query, release_id=None):
    p=h.page
    act(h,'listing release query',lambda:p.get_by_placeholder('Search releases...',exact=True).fill(query))
    act(h,'listing release search',lambda:p.locator('main').get_by_role('button',name='Search',exact=True).click())
    if release_id is not None:
        # Exact identity must be confirmed in rendered button text by the caller.
        b=p.locator('main button').filter(has_text=re.compile(r'#'+re.escape(str(release_id))+r'$'))
        if b.count()!=1: raise ValueError('release identity ambiguous or absent')
        act(h,'select release '+str(release_id),lambda:b.click())
    return h.observe('release selection')

def fill_listing(h, media=None, sleeve=None, ships_from=None, quantity=None, price_cents=None, comments=None):
    p=h.page
    for index,value,label in [(1,media,'media'),(2,sleeve,'sleeve'),(3,ships_from,'ships from'),(4,quantity,'quantity'),(5,price_cents,'price cents'),(6,comments,'comments')]:
        if value is not None:
            act(h,'listing '+label,lambda i=index,v=value:p.locator('main input').nth(i).fill(str(v)))
    return h.observe('listing form filled')

def submit_listing(h):
    b=h.page.get_by_role('button',name='Create Listing',exact=True)
    if not b.is_enabled():
        h.note('Create Listing disabled; no write attempted. Backend behavior unknown.')
        return h.observe('creation blocked by UI')
    return act(h,'create listing once',lambda:b.click())

def deactivate_listing(h, title, price_text=None):
    card=h.page.locator('main div.flex.items-center').filter(has_text=title)
    if price_text is not None: card=card.filter(has_text=price_text)
    if card.count()!=1: raise ValueError('listing identity ambiguous')
    b=card.get_by_role('button',name='Deactivate',exact=True)
    if b.count()!=1 or not b.is_enabled():
        h.note('No enabled deactivation control; no write attempted')
        return h.observe('deactivation unavailable')
    return act(h,'deactivate listing once',lambda:b.click())

def add_cart(h, seller_text):
    row=h.page.locator('tr').filter(has_text=seller_text)
    if row.count()!=1: raise ValueError('seller identity ambiguous')
    return act(h,'add listing to cart once',lambda:row.get_by_role('link',name='Add to Cart',exact=True).click())

def remove_cart(h, seller_text):
    card=h.page.locator('main section div.flex.items-center').filter(has_text='Seller: '+seller_text)
    if card.count()!=1: raise ValueError('cart identity ambiguous')
    return act(h,'remove cart line once',lambda:card.get_by_role('button',name='Remove',exact=True).click())

def run(h):
    print(navigate(h,'/'))
