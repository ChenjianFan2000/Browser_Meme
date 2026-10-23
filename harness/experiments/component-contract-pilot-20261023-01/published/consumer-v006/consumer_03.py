import components_v4 as c
import driver_v5 as d


def run(h):
    state = d.login(h)
    page = h.page
    state = d.act(h, state, 'navigate', {'path': '/jobs'}, page.get_by_role('link', name='Jobs', exact=True), wait=page.get_by_placeholder('Search jobs', exact=True))
    used_query = 'Bioinformatics'
    used_location = ''
    state = d.search(h, state, used_query, used_location)
    candidates = d.targets(state)
    if len(candidates) == 0:
        h.note('Original query has no exact target. Use the task-provided complete target title and location as a second known-input query; results remain unknown external data.')
        used_query = 'Bioinformatics Scientist'
        used_location = 'Austin, TX'
        state = d.search(h, state, used_query, used_location)
        candidates = d.targets(state)
    if len(candidates) != 1:
        h.read_point('Two bounded public-condition queries did not resolve one exact target. This is an unresolved query outcome, not whole-task impossibility; preserve remaining save/apply/persistence suffix.')
    identity = candidates[0]
    state = d.select(h, state, identity)
    state = d.verify_detail(h, state, identity)
    job = state['jobs'][c.identity_key(identity)]
    if not job['saved']:
        state = d.act(h, state, 'save', {}, c.detail(page).get_by_role('button', name='Save', exact=True), wait=c.detail(page).get_by_role('button', name='Saved', exact=True))
        state = d.verify_detail(h, state, identity)
    job = state['jobs'][c.identity_key(identity)]
    if job['applied']:
        h.read_point('Already Applied is disabled; do not submit a duplicate application.')
    state = d.act(h, state, 'apply', {}, c.detail(page).get_by_role('button', name='Apply', exact=True), wait=c.detail(page).get_by_role('button', name='Applied', exact=True))
    state = d.verify_detail(h, state, identity)
    state = d.act(h, state, 'navigate', {'path': '/feed'}, page.locator('nav a[href="/feed"]'), wait=page.get_by_role('button', name='Start a post', exact=True))
    state = d.act(h, state, 'navigate', {'path': '/jobs'}, page.get_by_role('link', name='Jobs', exact=True), wait=page.get_by_placeholder('Search jobs', exact=True))
    state = d.reload(h, state, c.collection_prediction())
    state = d.search(h, state, used_query, used_location)
    candidates = d.targets(state)
    if len(candidates) != 1 or candidates[0] != identity:
        h.read_point('Post-reload public conditions do not uniquely re-resolve the same full tuple.')
    state = d.select(h, state, identity)
    state = d.verify_detail(h, state, identity)
    job = state['jobs'][c.identity_key(identity)]
    assert job['saved'] is True
    assert job['applied'] is True
    assert c.detail(page).get_by_role('button', name='Applied', exact=True).is_disabled()
