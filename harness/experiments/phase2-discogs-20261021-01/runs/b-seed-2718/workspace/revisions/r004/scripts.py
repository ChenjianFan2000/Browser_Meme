"""Native UI execution helpers for condition B; no behavior predictor.

Entry points take the runtime handle h. run() only inspects the home page.
Use these functions under current-task LLM supervision. Unknown business outcomes
are deliberately recorded as unknown. No function retries a write. An exception,
ambiguous locator, or unexpected readback ends the caller's script. Runtime
confirms targets and scrolls them into view before each native locator action.
Only the login and featured-release/cart flows have been exercised. Seller
creation, editing, filters and deactivation have no execution helper here.
"""

def _expect(h, rationale, claim='', business=False):
    # An action annotation, not a model mapping observations/intents to outcomes.
    h.expect({'disposition':'unknown' if business else 'accepted',
              'effects':{'persistent_state_changed':None if business else False,
                         'affected_record_count':None if business else 0},
              'ui_claims':[{'claim':claim,'evidence_expected':'Fresh rendered-page observation'}] if claim else [],
              'unknowns':['Business result requires readback'] if business else []}, rationale)

def _read(h, label):
    return h.observe(label)

def _one(locator):
    if locator.count() != 1 or not locator.is_visible():
        raise ValueError('Expected exactly one visible target; inspect current DOM before acting')
    return locator

def _click(h, locator, rationale, claim='', business=False):
    target = _one(locator)
    if not target.is_enabled():
        raise ValueError('Target disabled; no action submitted')
    _expect(h, rationale, claim, business)
    target.click()
    return _read(h, 'after-click')

def _fill(h, locator, value, rationale):
    target = _one(locator)
    _expect(h, rationale, 'Input receives requested value')
    target.fill(value)
    return _read(h, 'after-fill')

def home(h):
    _expect(h, 'Inspect registered public origin', 'Landing page renders')
    h.page.goto(h.origin)
    return _read(h, 'home')

def follow_observed_link(h, href):
    """Read navigation only. The supplied href must exist in current rendered DOM."""
    if not href.startswith('/') or href.startswith('//') or '?' in href:
        raise ValueError('Use an observed path without a query; add-to-cart uses its own entry point')
    target = h.page.locator('a[href="'+href+'"]')
    if not target.count():
        raise ValueError('Link absent; rediscover the page')
    # Repeated links to the same path are equivalent; a visible one is selected.
    visible = [x for x in target.all() if x.is_visible()]
    if not visible:
        raise ValueError('Link hidden; inspect/open its menu with a separately predicted action')
    return _click(h,visible[0],'Follow a currently rendered link','Requested page renders')

def login_from_current_form(h):
    """Requires /login with the observed two-input account form; never reads secrets."""
    if not h.page.url.endswith('/login') or h.page.locator('input').count() != 3:
        raise ValueError('Login structure changed; inspect DOM')
    _fill(h,h.page.locator('input').nth(1),h.fixture['account']['username'],'Fill fixture username without printing')
    _fill(h,h.page.locator('input[type=password]'),h.fixture['account']['password'],'Fill fixture password without printing')
    o = _click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Submit fixture sign-in','Home page or authentication error')
    return o

def add_membership_once(h, kind):
    """Current release only. Repeated clicks can inflate transient counters."""
    if kind not in ['Wantlist','Collection'] or '/release/' not in h.page.url:
        raise ValueError('Requires release page and Wantlist or Collection')
    return _click(h,h.page.get_by_role('button',name='Add to '+kind,exact=True),
                  'Add one membership, then verify by navigating to account list',
                  'Control counters may change; account list is needed for persistence',True)

def add_current_listing_once(h, listing_id):
    """Use a listing id read from an Add to Cart href on the current marketplace.
    Return immediately after one add; inspect cart response before another write.
    """
    if '/sell/release/' not in h.page.url:
        raise ValueError('Requires rendered release marketplace')
    listing_number = int(listing_id)
    target=h.page.locator('a[href="/cart?add='+str(listing_number)+'"]')
    return _click(h,target,'Add exactly one selected listing via its observed UI link',
                  'Cart renders; inspect listing id and quantity in exported response',True)

def remove_cart_item_once(h, title, seller):
    """Scope by identity; the newest added row was first in the observed cart.
    Structure-specific selector is derived from the exported cart DOM, but this
    improved helper was only syntax checked after learning stopped.
    """
    if not h.page.url.endswith('/cart'):
        raise ValueError('Requires cart without add query')
    # The immediate parent of the title/price group is the item container.
    title_links=h.page.get_by_role('link',name=title,exact=True)
    candidates=[]
    for link in title_links.all():
        row=link.locator('..').locator('..')
        if 'Seller: '+seller in row.inner_text() and row.get_by_role('button',name='Remove',exact=True).count()==1:
            candidates.append(row)
    if len(candidates)!=1:
        raise ValueError('Cart item ambiguous; inspect DOM, do not remove by row position')
    return _click(h,candidates[0].get_by_role('button',name='Remove',exact=True),
                  'Remove selected cart item once','Read remaining rows and total',True)

def checkout_once(h):
    """Commits an order in the one observed flow. Invoke only for a purchase goal.
    The observed control submitted immediately without a confirmation form.
    """
    if not h.page.url.endswith('/cart'):
        raise ValueError('Requires cart without add query')
    return _click(h,h.page.get_by_role('button',name='Checkout',exact=True),
                  'Submit current task-authorized checkout once; never automatically retry',
                  'Observe cart and exported order response',True)

def seller_search(h, query):
    """Current /sell page. Only query Dark Side was observed during learning."""
    if not h.page.url.endswith('/sell'):
        raise ValueError('Requires seller page')
    _fill(h,h.page.get_by_placeholder('Search releases...'),query,'Search seller release choices')
    return _click(h,h.page.locator('section').first.get_by_role('button',name='Search',exact=True),
                  'Run seller release search','Inspect returned choices and Selected text')

def run(h):
    return home(h)
