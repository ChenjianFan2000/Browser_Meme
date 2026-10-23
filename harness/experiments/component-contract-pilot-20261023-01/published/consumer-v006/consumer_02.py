import components_v4 as c
import driver_v5 as d


def run(h):
    state = d.login(h)
    body = 'Contract consumer equal data 538c28fc.'
    state = d.create(h, state, body, 'first-equal-post-creation-event')
    card = c.post_card(h.page, body)
    if card.count() != 1:
        h.read_point('First created exact-body post is not unique before Like.')
    state = d.act(h, state, 'like', {'body': body}, card.get_by_role('button', name='👍 Like', exact=True), wait=card.get_by_role('button', name='👍 Liked', exact=True))
    state = d.verify_post(h, state, body, 'first-equal-post-creation-event')
    h.read_point('First causal object is Liked. Model still lacks duplicate-body creation and business write contracts: create_post requires public absence, even though candidate registries express distinct same-body entities. Preserve second-post/comment/cross-page persistence suffix; no second event fabricated, no DOM-order identity, task endpoint not achieved.')
