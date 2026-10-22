"""Condition A predictor. Only exact observed scopes are accepted.

Input observation is a dict of permitted current UI/readback facts, not hidden
state. See model_interface.md. Unknown or differently shaped inputs stay unknown.
Predictions are forecasts; callers must still record and inspect real readback.
"""

def _result(disposition='unknown', changed=None, count=None, claims=None, unknowns=None):
    return {'disposition': disposition,
            'effects': {'persistent_state_changed': changed,
                        'affected_record_count': count},
            'ui_claims': claims or [],
            'unknowns': unknowns or []}


def _claim(text, evidence):
    return {'claim': text, 'evidence_expected': evidence}


def _predict(observation, intent):
    """Return the public prediction shape; never perform website operations."""
    if not isinstance(observation, dict) or not isinstance(intent, dict):
        return _result(unknowns=['Provide explicit observed facts and a structured intent; free-text task interpretation is not learned.'])
    o, i = observation, intent
    op = i.get('operation', i.get('action', ''))
    aliases = {'add_to_wantlist': 'wantlist.add',
               'add_to_collection': 'collection.add',
               'add_to_cart': 'cart.add', 'checkout': 'cart.checkout',
               'login': 'auth.sign_in'}
    op = aliases.get(op, op)
    if op == 'auth.sign_in':
        if o.get('page_kind') == 'login' and o.get('fixture_credentials_supplied') is True and o.get('account_scope') == 'supplied_fixture':
            return _result('accepted', False, 0,
                [_claim('Sign in navigates to the home page; later signed-in UI has an Account button.', 'Home DOM followed by signed-in Account menu DOM.')],
                ['Only the supplied account and successful prefilled submission were observed; empty or incorrect credentials were not tested.'])
        return _result(unknowns=['Credentials validity and login input state are not confirmed.'])
    if op in ('wantlist.add', 'collection.add'):
        rid = i.get('release_id', o.get('release_id'))
        if str(rid) != '221' or o.get('authenticated') is not True or o.get('account_scope') != 'supplied_fixture':
            return _result(unknowns=['Only authenticated additions for release 221 were tested.'])
        kind = op.split('.')[0]
        memberships = o.get('memberships') or {}
        present = memberships.get(kind)
        if kind == 'collection' and memberships.get('wantlist') is not True:
            return _result(unknowns=['Collection was tested after confirmed wantlist membership for release 221.'])
        if present is not True and present is not False:
            return _result('accepted', None, None,
                [_claim('The Add button remains available after this observed operation.', 'Release DOM after action.')],
                ['Baseline membership is unknown; cannot distinguish insertion from an idempotent repeat.'])
        return _result('accepted', not present, 0 if present else 1,
            [_claim('The account list contains one card linking to /release/221 after readback.', 'Navigate to /me/' + kind + ' and count release 221 cards.'),
             _claim('The clicked Add button keeps its Add label; its sidebar count increments transiently.', 'Release DOM immediately after click; reload to distinguish stored counts.')],
            ['Exact hidden record totals are not inferred; affected count describes the targeted membership.',
             'Generalization to other releases, users, removal or concurrent actions is untested.'])
    if op == 'cart.add':
        try:
            listing_id = int(i.get('listing_id'))
        except (ValueError, TypeError):
            return _result(unknowns=['A listing ID from an observed Add to Cart link is required.'])
        cart = o.get('cart')
        if (o.get('authenticated') is not True or o.get('account_scope') != 'supplied_fixture' or o.get('listing_link_visible') is not True
                or o.get('listing_active') is not True or not isinstance(cart, dict)
                or not isinstance(cart.get('items'), list)):
            return _result(unknowns=['Require authenticated UI, a visible active listing link and a complete cart baseline.'])
        if listing_id not in (4, 7):
            return _result(unknowns=['Only listing 4 and listing 7 additions were observed.'])
        price = 2145 if listing_id == 4 else 2285
        if o.get('listing_price_cents') != price:
            return _result(unknowns=['Current listing price differs from the observed case.'])
        try:
            context = sorted((int(x['listing_id']), int(x['quantity']), int(x['price_cents'])) for x in cart['items'])
        except (KeyError, ValueError, TypeError):
            return _result(unknowns=['Complete observed cart line facts are required.'])
        allowed_contexts = ([([], 0)] if listing_id == 4 else [([(4, 1, 2145)], 2145), ([(4, 1, 2145), (7, 1, 2285)], 4430)])
        if (context, cart.get('total_cents')) not in allowed_contexts:
            return _result(unknowns=['Only the exact baseline cart sequences observed in call 009 are covered.'])
        matches = [x for x in cart['items'] if str(x.get('listing_id')) == str(listing_id)]
        if len(matches) > 1:
            return _result(unknowns=['Cart baseline does not match the observed single-line representation.'])
        quantity = matches[0].get('quantity') if matches else 0
        if (listing_id == 4 and quantity != 0) or (listing_id == 7 and quantity not in (0, 1)):
            return _result(unknowns=['This listing/quantity transition was not tested; stock ceiling unknown.'])
        claims = [_claim('Cart has a single line for this listing with quantity ' + str(quantity + 1) + ' in its UI-caused response.', 'Sanitized cart response after click and after reopening /cart.'),
                  _claim('Cart line displays unit price USD ' + format(price / 100, '.2f') + '.', 'Rendered Cart line; unit price does not show quantity.')]
        total = cart.get('total_cents')
        if isinstance(total, int):
            claims.append(_claim('Cart total becomes USD ' + format((total + price) / 100, '.2f') + '.', 'Rendered Summary Total and sanitized cart response.'))
        return _result('accepted', True, 1, claims,
            ['Only the observed quantity transitions are covered; checkout availability and stock limits are separate unknowns.'])
    if op == 'cart.checkout':
        cart = o.get('cart') or {}
        items = cart.get('items', [])
        try:
            signature = sorted((int(x['listing_id']), int(x['quantity']), int(x['price_cents'])) for x in items)
        except (KeyError, ValueError, TypeError):
            signature = []
        if (o.get('authenticated') is True and o.get('account_scope') == 'supplied_fixture' and signature == [(4, 1, 2145), (7, 2, 2285)]
                and cart.get('total_cents') == 6715):
            return _result('accepted', True, None,
                [_claim('Checkout response describes a paid USD 67.15 order with listing quantities 1 and 2.', 'UI-caused checkout response; generated order ID/time are unknown.'),
                 _claim('Cart becomes empty and total is USD 0.00, including after reopening.', 'Rendered /cart immediately after click and fresh navigation.')],
                ['Total affected business records cannot be counted from the observed response.',
                 'No claim about other carts, insufficient stock, external payment, repeat or empty checkout.'])
        return _result(unknowns=['Checkout was observed once for exactly listing 4 quantity 1 and listing 7 quantity 2, total 6715 cents.'])
    return _result(unknowns=['No observed rule for this operation and its supplied conditions.'])


def predict(observation, intent):
    """Public safe entry point: insufficient/malformed facts remain unknown."""
    try:
        return _predict(observation, intent)
    except (TypeError, ValueError, KeyError, AttributeError):
        return _result(unknowns=['Observation or intent lacks the structured facts required for a learned case.'])
