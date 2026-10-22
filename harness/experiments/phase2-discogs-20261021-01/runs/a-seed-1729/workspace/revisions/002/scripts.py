"""Reusable native Playwright functions, revised offline after exploration stop.

Execute with behavior_model.py supplied as an own helper module. These routines
were syntax-checked, not browser-tested after the boundary. Original executed
experiments in ../../experiments are the evidence. No business action retries.
"""
import re
from behavior_model import predict


def _unknown(reason):
    return {'disposition': 'unknown', 'effects': {'persistent_state_changed': None,
            'affected_record_count': None}, 'ui_claims': [], 'unknowns': [reason]}


def _read(h, label):
    observation = h.observe(label)
    print(observation)
    return observation


def _go(h, path, label):
    if not path.startswith('/') or path.startswith('//'):
        raise ValueError('Use a same-origin page path from an observed link.')
    h.expect({'disposition': 'accepted', 'effects': {'persistent_state_changed': False,
              'affected_record_count': 0}, 'ui_claims': [], 'unknowns': []}, label)
    h.page.goto(h.origin + path)
    return _read(h, label)


def _click(h, target, prediction, label):
    if target.count() != 1 or not target.is_visible() or not target.is_enabled():
        raise ValueError('Target not uniquely visible and enabled; inspect without retrying writes.')
    h.expect(prediction, label)
    # The runtime confirms and scrolls native locator targets before acting.
    target.click()
    return _read(h, label)


def _fill(h, target, value, label):
    if target.count() != 1 or not target.is_visible():
        raise ValueError('Input not uniquely visible.')
    h.expect({'disposition': 'accepted', 'effects': {'persistent_state_changed': False,
             'affected_record_count': 0}, 'ui_claims': [], 'unknowns': []}, label)
    target.fill(value)
    return _read(h, label)


def sign_in(h):
    """Use fixture values without printing them; no empty-form assumption."""
    _go(h, '/login', 'login-form')
    password = h.page.locator('input[type="password"]')
    if password.count() != 1 or not password.is_visible():
        return _read(h, 'login-input-state-unknown')
    form = h.page.locator('form').filter(has=password)
    _fill(h, form.locator('input').first, h.fixture['account']['username'], 'set-username')
    _fill(h, password, h.fixture['account']['password'], 'set-password')
    p = predict({'page_kind': 'login', 'fixture_credentials_supplied': True, 'account_scope': 'supplied_fixture'}, {'operation': 'auth.sign_in'})
    result = _click(h, h.page.get_by_role('button', name='Sign in', exact=True), p, 'submit-login-once')
    _go(h, '/', 'auth-readback')
    print({'account_button_count': h.page.get_by_role('button', name='Account', exact=True).count()})
    return result


def inspect_release(h, release_id=221):
    return _go(h, '/release/' + str(int(release_id)), 'release-details')


def add_membership(h, kind, release_id=221, baseline_facts=None):
    """Baseline -> one click -> fresh list readback. Unknown for untested IDs."""
    if kind not in ('collection', 'wantlist'):
        raise ValueError('Unknown list kind.')
    rid = int(release_id)
    href = '/release/' + str(rid)
    _go(h, '/me/' + kind, 'membership-baseline')
    present = h.page.locator('main a[href="' + href + '"]').count() > 0
    auth = h.page.get_by_role('button', name='Account', exact=True).count() == 1
    inspect_release(h, rid)
    facts = dict(baseline_facts or {})
    facts.update({'authenticated': auth, 'release_id': rid})
    memberships = dict(facts.get('memberships') or {})
    memberships[kind] = present
    facts['memberships'] = memberships
    p = predict(facts, {'operation': kind + '.add', 'release_id': rid})
    title = 'Add to Collection' if kind == 'collection' else 'Add to Wantlist'
    _click(h, h.page.get_by_role('button', name=title, exact=True), p, 'add-membership-once')
    result = _go(h, '/me/' + kind, 'membership-readback')
    print({'release_id': rid, 'kind': kind, 'observed_cards': h.page.locator('main a[href="' + href + '"]').count(),
           'note': 'Readback is evidence; this count is not independent task scoring.'})
    return result


def _total_from_cart(h):
    text = h.page.locator('main').inner_text()
    match = re.search(r'Total\s+USD\s+([0-9,]+\.[0-9]{2})', text)
    return int(round(float(match.group(1).replace(',', '')) * 100)) if match else None


def add_to_cart(h, listing_id, marketplace_path='/sell/release/221', baseline_facts=None):
    """Select only a currently rendered Add to Cart link; exactly one addition.

    baseline_facts may supply an explicitly observed complete cart snapshot and
    listing availability. Never supply facts from private/backend state.
    """
    _go(h, '/cart', 'cart-before-add')
    before = _total_from_cart(h)
    _go(h, marketplace_path, 'marketplace-before-add')
    target = h.page.locator('main a[href="/cart?add=' + str(int(listing_id)) + '"]')
    facts = dict(baseline_facts or {})
    facts['listing_link_visible'] = target.count() == 1 and target.is_visible()
    facts['authenticated'] = h.page.get_by_role('button', name='Account', exact=True).count() == 1
    p = predict(facts, {'operation': 'cart.add', 'listing_id': listing_id})
    _click(h, target, p, 'cart-add-once')
    result = _go(h, '/cart', 'cart-add-persistent-readback')
    print({'total_before': before, 'total_after': _total_from_cart(h),
           'unknowns': ['Quantity requires the sanitized UI-caused response; rendered line shows unit price.']})
    return result


def checkout_once(h, cart_facts=None, account_scope=None):
    """One non-idempotent checkout; no retry if confirmation is incomplete."""
    _go(h, '/cart', 'checkout-baseline')
    if _total_from_cart(h) in (None, 0):
        return _read(h, 'checkout-not-submitted-empty-or-unknown')
    facts = {'authenticated': h.page.get_by_role('button', name='Account', exact=True).count() == 1,
             'cart': cart_facts or {}, 'account_scope': account_scope}
    _click(h, h.page.get_by_role('button', name='Checkout', exact=True),
           predict(facts, {'operation': 'cart.checkout'}), 'checkout-once')
    result = _go(h, '/cart', 'checkout-fresh-readback')
    print({'observed_total_cents': _total_from_cart(h),
           'unknowns': ['Inspect the exported UI-caused checkout response for paid-order confirmation. Never infer a paid order solely from empty UI.']})
    return result


def inspect_selling(h):
    """Read selling controls. Create/deactivate business behavior is untested."""
    _go(h, '/sell', 'sell-inspection')
    print({'inputs': [{'type': x.get_attribute('type'), 'name': x.get_attribute('name'),
                      'placeholder': x.get_attribute('placeholder')} for x in h.page.locator('main input').all()],
           'buttons': [x.inner_text() for x in h.page.locator('main button').all()]})
    return _read(h, 'sell-controls')


def run(h):
    """Default safe entry point: inspect release 221 without a business write."""
    return inspect_release(h, 221)
