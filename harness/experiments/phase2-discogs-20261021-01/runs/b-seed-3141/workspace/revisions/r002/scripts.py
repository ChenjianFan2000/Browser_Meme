"""Native UI execution only. The supervising learner supplies every prediction.

Entry points below require a current rendered page and explicit per-action
predictions; they do not predict behavior. Read each result before another write.
Use through phase2.execute_script, never as an HTTP client.
"""

def perform(h, target, method, prediction, rationale, value=None):
    if method != 'goto':
        if target.count() != 1:
            raise ValueError('Target must resolve uniquely before acting')
        if method == 'click' and not target.is_enabled():
            raise ValueError('Target disabled; inspect boundary without retrying')
    h.expect(prediction, rationale)
    if method == 'goto':
        h.page.goto(value)
    elif method == 'click':
        target.click()
    elif method == 'fill':
        target.fill(value)
    elif method == 'select':
        target.select_option(value)
    elif method == 'hover':
        target.hover()
    else:
        raise ValueError('Unsupported native action')
    observation = h.observe(rationale)
    print(observation)
    return observation

def navigate(h, observed_url, prediction):
    return perform(h, None, 'goto', prediction, 'Navigate to an already observed URL', observed_url)

def global_search(h, query, predictions):
    perform(h, h.page.get_by_placeholder('Search artists, albums and more...'), 'fill', predictions[0], 'Enter global query', query)
    return perform(h, h.page.get_by_role('button', name='Search', exact=True), 'click', predictions[1], 'Submit global query')

def sign_in(h, predictions):
    """On /login; enter fixture values without printing them."""
    perform(h, h.page.locator('input').nth(1), 'fill', predictions[0], 'Enter fixture username', h.fixture['account']['username'])
    perform(h, h.page.locator('input[type="password"]'), 'fill', predictions[1], 'Enter fixture password', h.fixture['account']['password'])
    return perform(h, h.page.get_by_role('button', name='Sign in', exact=True), 'click', predictions[2], 'Submit sign-in')

def account_menu(h, prediction):
    return perform(h, h.page.get_by_role('button', name='Account', exact=True), 'click', prediction, 'Open authenticated account menu')

def add_membership(h, kind, prediction):
    if kind not in ['Wantlist', 'Collection']:
        raise ValueError('Choose Wantlist or Collection')
    return perform(h, h.page.get_by_role('button', name='Add to '+kind, exact=True), 'click', prediction, 'Add current release to '+kind)

def find_listing_release(h, query, predictions):
    """On /sell. Search may auto-select its first match; read selected identity."""
    perform(h, h.page.get_by_placeholder('Search releases...'), 'fill', predictions[0], 'Enter release query', query)
    return perform(h, h.page.get_by_role('button', name='Search', exact=True).nth(1), 'click', predictions[1], 'Search listing releases')

def choose_listing_release(h, accessible_name, prediction):
    return perform(h, h.page.get_by_role('button', name=accessible_name, exact=True), 'click', prediction, 'Select exact release result')

def fill_listing_field(h, field, value, prediction):
    """Observed /sell input order; fail if expected eight inputs have changed."""
    positions = {'media_condition':2, 'sleeve_condition':3, 'ships_from':4, 'quantity':5, 'price_cents':6, 'comments':7}
    if h.page.locator('input').count() != 8:
        raise ValueError('Reinspect listing form structure')
    return perform(h, h.page.locator('input').nth(positions[field]), 'fill', prediction, 'Fill listing '+field, str(value))

def create_listing(h, prediction):
    return perform(h, h.page.get_by_role('button', name='Create Listing', exact=True), 'click', prediction, 'Create selected release listing; read status before any repeat')

def deactivate_listing(h, title, price_text, prediction, row_index=None):
    row = h.page.locator('div.divide-y > div').filter(has_text=title).filter(has_text=price_text)
    if row_index is not None:
        row = row.nth(row_index)
    return perform(h, row.get_by_role('button', name='Deactivate', exact=True), 'click', prediction, 'Deactivate uniquely identified own listing')

def apply_market_filter(h, name, value, predictions):
    if name not in ['media_condition','sleeve_condition','ships_from','min_rating']:
        raise ValueError('Unobserved filter')
    perform(h, h.page.locator('input[name="'+name+'"]'), 'fill', predictions[0], 'Enter marketplace filter '+name, value)
    return perform(h, h.page.get_by_role('button', name='Apply', exact=True), 'click', predictions[1], 'Apply marketplace filters')

def add_cart_row(h, row_text, prediction, row_index=None):
    row = h.page.locator('tbody tr').filter(has_text=row_text)
    if row_index is not None:
        row = row.nth(row_index)
    return perform(h, row.get_by_role('link', name='Add to Cart', exact=True), 'click', prediction, 'Add uniquely identified marketplace listing; repeated adds may increase quantity')

def remove_cart_item(h, seller_text, prediction, release_title=None, unit_price=None, row_index=None):
    item = h.page.locator('div.divide-y > div').filter(has_text=seller_text)
    if release_title is not None:
        item = item.filter(has_text=release_title)
    if unit_price is not None:
        item = item.filter(has_text=unit_price)
    if row_index is not None:
        item = item.nth(row_index)
    return perform(h, item.get_by_role('button', name='Remove', exact=True), 'click', prediction, 'Remove uniquely identified cart item')

def checkout(h, prediction):
    return perform(h, h.page.get_by_role('button', name='Checkout', exact=True), 'click', prediction, 'Checkout once, then inspect response and persistent readback')
