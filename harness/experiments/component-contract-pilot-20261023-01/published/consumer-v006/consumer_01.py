import components_v4 as c
import driver_v5 as d


def run(h):
    state = d.login(h, reject=True)
    body = 'Contract consumer new data 538c28fc: persistence.'
    state = d.create(h, state, body, 'created-post-event-01')
    state = d.act(h, state, 'navigate', {'path': '/jobs'}, h.page.get_by_role('link', name='Jobs', exact=True), wait=h.page.get_by_placeholder('Search jobs', exact=True))
    state = d.act(h, state, 'navigate', {'path': '/feed'}, h.page.locator('nav a[href="/feed"]'), wait=c.post_card(h.page, body))
    state = d.reload(h, state, c.expectation('post.body', branch='present', parameters={'body': body}))
    c.post_card(h.page, body).wait_for(state='visible', timeout=10000)
    assert c.post_card(h.page, body).count() == 1
    state = d.verify_post(h, state, body, 'created-post-event-01')
