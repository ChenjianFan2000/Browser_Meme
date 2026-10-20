"""Source-visible Solar task author: direct native Playwright, no API actions.

Every write is dispatched once. Browser-origin GET responses supplement the
visible cart because its UI omits quantities. No privileged state is read.
"""
import itertools
import re
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect


def money(text):
    match = re.fullmatch(r'([A-Z]{3})\s+(\d+\.\d{2})', text.strip())
    if not match:
        raise ValueError('unconfirmed: currency/price cannot be parsed: '+text)
    return match.group(1), int(Decimal(match.group(2))*100)


def offers(page):
    header = page.get_by_text(re.compile(r'^Marketplace listings')).inner_text()
    found = re.search(r'(\d+) for sale', header)
    if not found:
        raise ValueError('unconfirmed: marketplace total unavailable')
    rows = page.locator('main tbody tr').filter(has=page.locator('a[href^="/cart?add="]'))
    count = rows.count()
    total = int(found.group(1))
    if count != total or total > 50:
        raise ValueError('unconfirmed: incomplete candidate set; no purchase')
    result = []
    for i in range(count):
        row = rows.nth(i)
        cells = row.locator('td')
        seller = cells.nth(0).locator('div').nth(0).inner_text().strip()
        rating_text = cells.nth(0).locator('div').nth(1).inner_text().strip()
        rating = re.match(r'(\d+(?:\.\d+)?)%', rating_text)
        href = row.locator('a[href^="/cart?add="]').get_attribute('href')
        ids = parse_qs(urlsplit(href).query).get('add', [])
        if not rating or len(ids) != 1:
            raise ValueError('unconfirmed: offer identity/rating malformed')
        currency, cents = money(cells.nth(3).inner_text())
        result.append({'listing_id': int(ids[0]), 'seller': seller,
                       'seller_rating': float(rating.group(1)), 'currency': currency,
                       'price_cents': cents, 'ships_from': cells.nth(1).inner_text().strip(),
                       'condition': cells.nth(2).inner_text().strip(), 'href': href,
                       'row_text': row.inner_text()})
    if len({o['listing_id'] for o in result}) != len(result):
        raise ValueError('unconfirmed: duplicate listing identity')
    return total, result


def choose(candidates, params):
    # The candidate table itself is the public input, never an oracle answer.
    eligible = [o for o in candidates if o['currency'] == params['currency']
                and o['seller'] != params['exclude_seller_username']
                and o['seller_rating'] >= params['minimum_seller_rating']]
    pairs = []
    for a, b in itertools.combinations(eligible, 2):
        if a['seller'] == b['seller']:
            continue
        first, second = sorted([a, b], key=lambda x: x['listing_id'])
        pairs.append({'key': [a['price_cents']+b['price_cents'], first['listing_id'], second['listing_id']],
                      'offers': [first, second]})
    pairs.sort(key=lambda p: tuple(p['key']))
    if not pairs:
        raise ValueError('business_rule: insufficient distinct eligible sellers; no write')
    selected = pairs[0]
    if selected['key'][0] > params['maximum_total_cents']:
        raise ValueError('business_rule: minimum pair exceeds budget; no write')
    return selected, pairs


def verify_cart(cart, selected):
    rows = cart.get('items')
    if not isinstance(rows, list) or len(rows) != len(selected):
        raise ValueError('business_rule: cart row count does not match commitment')
    by_id = {r['listing']['listing_id']: r for r in rows}
    if set(by_id) != {o['listing_id'] for o in selected}:
        raise ValueError('business_rule: unexpected cart object; do not retry add')
    for o in selected:
        row = by_id[o['listing_id']]
        listing = row['listing']
        if row['quantity'] != 1 or listing['seller_username'] != o['seller'] or listing['currency'] != o['currency'] or listing['price_cents'] != o['price_cents']:
            raise ValueError('business_rule: cart identity/quantity/price changed')
    total = sum(o['price_cents'] for o in selected)
    if cart.get('total_cents') != total or cart.get('currency') != 'USD':
        raise ValueError('business_rule: cart calculation mismatch')


def run(case, h):
    page, params = h.page, case['parameters']
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(30000)
    dialogs = []
    def accept_dialog(dialog):
        dialogs.append({'type': dialog.type, 'message': dialog.message})
        dialog.accept()
    page.on('dialog', accept_dialog)

    def click(selector):
        target = page.locator(selector)
        h.confirm(target)
        target.click()

    def fill(selector, value):
        target = page.locator(selector)
        h.confirm(target)
        target.fill(str(value))

    with h.step('login_open'):
        page.goto(h.base_url+'/login', wait_until='domcontentloaded')
        page.locator('main input[type="password"]').wait_for(state='visible')
    with h.step('login_username'):
        fill('main form input:not([type="password"])', params['username'])
    with h.step('login_password'):
        fill('main input[type="password"]', params['password'])
    with h.step('login_submit'):
        click('main button:has-text("Sign in")')
        page.wait_for_url(h.base_url.rstrip('/')+'/', wait_until='domcontentloaded')
        page.get_by_text('Trending Releases', exact=True).wait_for(state='visible')
    with h.step('search_fill'):
        fill('header input[name="q"]', params['search_query'])
    with h.step('search_submit'):
        click('header button[type="submit"]')
        page.locator(f'main a[href="/release/{params["release_id"]}"]').wait_for(state='visible')
    with h.step('release_open'):
        click(f'main a[href="/release/{params["release_id"]}"]')
        page.get_by_text('Tracklist', exact=True).wait_for(state='visible')
    with h.step('marketplace_open'):
        click(f'main a[href="/sell/release/{params["release_id"]}"]')
        page.get_by_text(re.compile(r'^Marketplace listings')).wait_for(state='visible')
    with h.step('rating_fill'):
        fill('main input[name="min_rating"]', params['minimum_seller_rating'])
    with h.step('sort_select'):
        h.confirm(page.locator('main select[name="sort"]')).select_option(params['sort'])
    with h.step('filter_apply'):
        click('main button:has-text("Apply")')
        page.wait_for_url(lambda url: parse_qs(urlsplit(str(url)).query).get('min_rating') == [str(params['minimum_seller_rating'])], wait_until='domcontentloaded')
        page.get_by_text(re.compile(r'^Marketplace listings')).wait_for(state='visible')
        candidate_total, candidates = offers(page)
        assert all(o['seller_rating'] >= params['minimum_seller_rating'] for o in candidates), 'business_rule: rating filter contradicted'
        assert [o['price_cents'] for o in candidates] == sorted(o['price_cents'] for o in candidates), 'business_rule: price ordering contradicted'
    selected, comparison = choose(candidates, params)
    first, second = selected['offers']
    h.note('selection_commitment', {'release_id': params['release_id'], 'filter_url': page.url,
           'candidate_total': candidate_total, 'candidate_rows': candidates,
           'eligible_pair_comparison': comparison, 'selected': selected,
           'maximum_total_cents': params['maximum_total_cents'],
           'unit': 'USD cents; 100 cents = USD 1.00'})

    h.checkpoint('selection_committed')
    with h.step('first_cart_add'):
        target = page.locator(f'main a[href="{first["href"]}"]')
        h.confirm(target)
        with page.expect_response(lambda r: urlsplit(r.url).path == '/api/cart' and r.request.method == 'GET' and r.status == 200) as loaded:
            target.click()
        loaded.value.finished()
        first_cart = loaded.value.json()
        verify_cart(first_cart, [first])
        page.wait_for_url(h.base_url+'/cart', wait_until='domcontentloaded')
        page.get_by_text(params['search_query'], exact=True).wait_for(state='visible')
        page.get_by_text('Loading...', exact=True).wait_for(state='hidden')
    h.note('first_cart_confirmed', first_cart)
    with h.step('return_release'):
        click(f'main a[href="/release/{params["release_id"]}"]')
        page.get_by_text('Tracklist', exact=True).wait_for(state='visible')
    with h.step('return_marketplace'):
        click(f'main a[href="/sell/release/{params["release_id"]}"]')
        page.get_by_text(re.compile(r'^Marketplace listings')).wait_for(state='visible')
    with h.step('rating_refill'):
        fill('main input[name="min_rating"]', params['minimum_seller_rating'])
    with h.step('sort_reselect'):
        h.confirm(page.locator('main select[name="sort"]')).select_option(params['sort'])
    with h.step('filter_reapply'):
        click('main button:has-text("Apply")')
        page.wait_for_url(lambda url: parse_qs(urlsplit(str(url)).query).get('min_rating') == [str(params['minimum_seller_rating'])], wait_until='domcontentloaded')
        page.get_by_text(re.compile(r'^Marketplace listings')).wait_for(state='visible')
        new_total, new_candidates = offers(page)
        recalled = next((o for o in new_candidates if o['listing_id'] == second['listing_id']), None)
        if recalled != second:
            raise ValueError('business_rule: remembered second offer changed; no replacement')
    h.note('second_offer_memory_recheck', {'candidate_total': new_total, 'remembered': second, 'reobserved': recalled})
    with h.step('second_cart_add'):
        target = page.locator(f'main a[href="{second["href"]}"]')
        h.confirm(target)
        with page.expect_response(lambda r: urlsplit(r.url).path == '/api/cart' and r.request.method == 'GET' and r.status == 200) as loaded:
            target.click()
        loaded.value.finished()
        final_cart = loaded.value.json()
        verify_cart(final_cart, selected['offers'])
        page.wait_for_url(h.base_url+'/cart', wait_until='domcontentloaded')
        page.locator('main button:has-text("Checkout")').wait_for(state='visible')
        page.get_by_text('Loading...', exact=True).wait_for(state='hidden')
        expect(page.locator('main button:has-text("Checkout")')).to_be_enabled(timeout=30000)
    h.note('pre_checkout_cart_commitment', {'selection': selected, 'browser_cart_response': final_cart,
           'total_cents': final_cart['total_cents'], 'total_usd': str(Decimal(final_cart['total_cents'])/100)})

    h.checkpoint('before_checkout')
    with h.step('checkout'):
        target = page.locator('main button:has-text("Checkout")')
        h.confirm(target)
        with page.expect_response(lambda r: urlsplit(r.url).path == '/api/checkout' and r.request.method == 'POST') as committed:
            target.click()
        committed.value.finished()
        if committed.value.status != 200:
            raise ValueError('business_rule: checkout refused; never automatically repeat')
        order = committed.value.json()
        actual = {(i['listing_id'], i['price_cents'], i['quantity']) for i in order['items']}
        expected = {(o['listing_id'], o['price_cents'], 1) for o in selected['offers']}
        assert order['status'] == 'paid' and order['currency'] == 'USD' and order['total_cents'] == selected['key'][0] and actual == expected, 'business_rule: checkout result differs from commitment'
        page.get_by_text('Your cart is empty.', exact=False).wait_for(state='visible')
        expect(page.locator('main button:has-text("Checkout")')).to_be_disabled(timeout=30000)
    h.note('final_public_checkout', {'order': order, 'dialogs': dialogs})
