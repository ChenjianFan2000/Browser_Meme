"""Solar source-authored direct Playwright scripts. No API writes or backend access."""
from urllib.parse import urlsplit

from playwright.sync_api import expect


def run(case, h):
    page=h.page
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(30000)
    # Native dialogs are UI evidence. Harness also listens to the dialog event.
    page.on('dialog', lambda dialog: dialog.accept())
    selected_offer=None
    for specification in case['steps']:
        action=specification['action']
        wait=specification.get('wait',{})
        with h.step(specification['id']):
            if action['kind']=='open':
                page.goto(h.base_url+action['url'],wait_until='domcontentloaded')
            elif action['kind']=='fill':
                target=page.locator(action['selector'])
                h.confirm(target)
                if 'offer_cell' in action:
                    if selected_offer is None:
                        row=page.locator('main tbody tr').first
                        selected_offer={
                            'ships_from':row.locator('td').nth(1).inner_text().strip(),
                            'media_condition':row.locator('td').nth(2).inner_text().split(' / ')[0].strip(),
                            'sleeve_condition':row.locator('td').nth(2).inner_text().split(' / ')[1].strip(),
                        }
                    target.fill(selected_offer[action['offer_cell']])
                else:
                    target.fill(action['value'])
            elif action['kind']=='click':
                target=page.locator(action['selector'])
                h.confirm(target)
                # Resolve completion through the original UI event and its visible result.
                target.click()
            elif action['kind']=='hover':
                h.confirm(page.locator(action['selector'])).hover()
            elif action['kind']=='select':
                h.confirm(page.locator(action['selector'])).select_option(action['value'])
            elif action['kind']=='reload':
                page.reload(wait_until='domcontentloaded')
            else:
                raise ValueError('Unimplemented native action '+action['kind'])
            if wait.get('kind')=='text':
                page.get_by_text(wait['value'],exact=False).first.wait_for(state='visible')
            elif wait.get('kind')=='selector':
                page.locator(wait['value']).first.wait_for(state='visible')
            elif wait.get('kind')=='enabled':
                expect(page.locator(wait['value'])).to_be_enabled(timeout=30000)
            elif wait.get('kind')=='url':
                value=wait['value']
                if value=='/cart':
                    page.wait_for_url(lambda url: urlsplit(str(url)).path=='/cart' and not urlsplit(str(url)).query)
                    page.get_by_text('The Dark Side Of The Moon',exact=True).wait_for(state='visible')
                    page.get_by_text('Loading...',exact=True).wait_for(state='hidden')
                elif value=='/':
                    page.wait_for_url(h.base_url.rstrip('/')+'/')
                    page.get_by_text('Trending Releases',exact=True).wait_for(state='visible')
                else:
                    page.wait_for_url(lambda url: urlsplit(str(url)).path==value)
                    page.get_by_text('Sign in',exact=True).first.wait_for(state='visible')
            if specification.get('verify_descending_prices'):
                prices=page.locator('main tbody tr td:nth-child(4)').all_inner_texts()
                cents=[round(float(v.strip().split()[-1])*100) for v in prices]
                assert cents and cents==sorted(cents,reverse=True), 'UI prices are not descending'
