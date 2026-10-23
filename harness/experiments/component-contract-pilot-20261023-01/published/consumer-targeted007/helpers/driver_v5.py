import re
import components_v4 as c


def bind(h, result):
    if result.get('ok') is False:
        h.read_point(result['readpoint'])
    return result


def act(h, state, operation, parameters, target, value=None, fill=False, wait=None):
    q = c.plan(state, operation, parameters)
    if not q['ok']:
        h.read_point(q['readpoint'])
    h.expect(q['prediction'], 'Unified pre-action component/business plan: ' + operation)
    h.confirm(target)
    if fill:
        target.fill(value)
        # Secret controls allow writes, never value/body readback.
        # The native action checkpoint checks the declared public component;
        # subsequent auth outcome verifies credentials without disclosing them.
    else:
        target.click()
    if wait is not None:
        wait.wait_for(state='visible', timeout=10000)
    return q['state']


def reload(h, state, component):
    q = c.plan(state, 'reload', {'component': component})
    if not q['ok']:
        h.read_point(q['readpoint'])
    h.expect(q['prediction'], 'Reload preserves unified business state; commit only after native gate returns.')
    h.page.reload()
    h.page.get_by_role('link', name='Jobs', exact=True).wait_for(state='visible', timeout=10000)
    return q['state']


def login(h, reject=False):
    state = c.initial_state()
    page = h.page
    email = page.locator('input[autocomplete="email"]')
    password = page.locator('input[autocomplete="current-password"]')
    submit = page.get_by_role('button', name='Sign in', exact=True)
    email.wait_for(state='visible', timeout=10000)
    state = act(h, state, 'form_edit', {'component': c.expectation('auth.login')}, email, h.fixture['account']['email'], True)
    attempted = h.fixture['account']['password'] + '.contract-denied' if reject else h.fixture['account']['password']
    state = act(h, state, 'form_edit', {'component': c.expectation('auth.login')}, password, attempted, True)
    if reject:
        state = act(h, state, 'auth_reject', {}, submit, wait=page.get_by_text('Invalid email or password', exact=True))
        assert '/login' in page.url
        assert not state['authenticated']
        assert page.get_by_role('button', name='Start a post', exact=True).count() == 0
        state = act(h, state, 'form_edit', {'component': c.expectation('auth.login', branch='rejected')}, password, h.fixture['account']['password'], True)
    return act(h, state, 'auth_success', {}, submit, wait=page.get_by_role('button', name='Start a post', exact=True))


def verify_post(h, state, body, handle):
    obs = c.current_post_observation(h.page, body)
    if obs is None:
        h.read_point('No unique parseable complete-body post observation.')
    state = bind(h, c.bind_post(state, body, obs['liked'], obs['reactions'], obs['comments'], True))
    signature = dict(obs, body=body)
    if handle not in state['entities']:
        state = bind(h, c.register_entity(state, handle, signature, 'Successful independent create_post event and unique public post verification'))
    else:
        result = c.reconcile_entity(state, handle, signature, 'Public verification after own action/navigation', mode='verify')
        bind(h, result)
        state = result['state']
    candidates = c.match_entity_candidates(state, signature)
    bind(h, candidates)
    if candidates['identity_status'] != 'unique' or candidates['candidates'] != [handle]:
        h.read_point('Current public signature does not identify the causal handle uniquely.')
    return state


def create(h, state, body, handle):
    state = bind(h, c.bind_post_absence(state, body, c.post_card(h.page, body).count()))
    dialog = h.page.get_by_role('dialog')
    state = act(h, state, 'open_composer', {}, h.page.get_by_role('button', name='Start a post', exact=True), wait=dialog)
    state = act(h, state, 'fill_post', {'body': body}, dialog.get_by_placeholder('What do you want to talk about?', exact=True), body, True)
    state = act(h, state, 'create_post', {}, dialog.get_by_role('button', name='Post', exact=True))
    dialog.wait_for(state='hidden', timeout=10000)
    c.post_card(h.page, body).wait_for(state='visible', timeout=10000)
    return verify_post(h, state, body, handle)


def search(h, state, query, location):
    page = h.page
    field = page.get_by_placeholder('Search jobs', exact=True)
    place = page.get_by_placeholder('Location', exact=True)
    field.wait_for(state='visible', timeout=10000)
    state = act(h, state, 'search', {'query': query, 'location': place.input_value()}, field, query, True)
    state = act(h, state, 'search', {'query': query, 'location': location}, place, location, True)
    state = act(h, state, 'search', {'query': query, 'location': location}, page.get_by_role('button', name='Search', exact=True))
    return bind(h, c.bind_rows(state, c.public_jobs(page)))


def targets(state):
    matches = []
    for identity in state['rows']:
        parts = identity['location_mode'].split(' • ')
        if identity['title'] == 'Bioinformatics Scientist' and identity['company'] == 'Atlas Cloud' and len(parts) == 2 and parts[0] == 'Austin, TX':
            matches.append(identity)
    return matches


def select(h, state, identity):
    row = c.job_row(h.page, identity)
    if row.count() != 1:
        h.read_point('Complete public job tuple is ambiguous.')
    saved = row.get_by_role('button', name='Saved', exact=True).count()
    unsaved = row.get_by_role('button', name='Save', exact=True).count()
    if saved + unsaved != 1:
        h.read_point('No unique row-owned Save/Saved state.')
    normal = c.normalize_visible_job(identity, saved == 1)
    bind(h, normal)
    state = bind(h, c.bind_job(state, normal['identity'], normal['saved'], None, None))
    return act(h, state, 'select_job', {'identity': normal['identity']}, row, wait=c.detail(h.page))


def verify_detail(h, state, identity):
    detail = c.detail(h.page)
    parameters = c.detail_parameters(identity, 'Saved')
    if parameters is None or detail.count() != 1:
        h.read_point('Detail identity/mode grammar is unconfirmed.')
    title = detail.get_by_text(parameters['title'], exact=True)
    # Company/location/mode occupy one public metadata element. Match its
    # complete identity, anchored end-to-end, with display whitespace normalized.
    mode_parts = parameters['mode_text'].split()
    metadata_pattern = (r'^\s*' + re.escape(parameters['company']) +
                        r'\s*•\s*' + re.escape(parameters['location']) +
                        r'\s*' + r'\s+'.join(re.escape(part) for part in mode_parts) + r'\s*$')
    metadata = detail.get_by_text(re.compile(metadata_pattern))
    if title.count() != 1 or not title.is_visible() or metadata.count() != 1 or not metadata.is_visible():
        h.read_point('Full selected detail title and compound company/location/mode ownership is unconfirmed.')
    saved = detail.get_by_role('button', name='Saved', exact=True).count()
    unsaved = detail.get_by_role('button', name='Save', exact=True).count()
    applied = detail.get_by_role('button', name='Applied', exact=True)
    apply = detail.get_by_role('button', name='Apply', exact=True)
    if saved + unsaved != 1 or applied.count() + apply.count() != 1:
        h.read_point('Save/application public controls are ambiguous.')
    if applied.count() == 1 and not applied.is_disabled():
        h.read_point('Applied must be disabled.')
    meta = detail.locator('div[class="mt-1 text-[12px] text-black/60"]').filter(has_text='applicants')
    if meta.count() != 1:
        h.read_point('Applicants metadata public container is not unique.')
    count = re.search(r'(\d+)\s+applicants\b', meta.inner_text())
    if count is None:
        h.read_point('Public applicant count cannot be parsed.')
    return bind(h, c.bind_job(state, identity, saved == 1, applied.count() == 1, int(count.group(1))))
