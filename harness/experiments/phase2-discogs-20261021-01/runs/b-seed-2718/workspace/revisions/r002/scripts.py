"""Native UI execution checkpoint; no predictor. New helpers syntax checked only."""

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


def run(h):
    return home(h)


