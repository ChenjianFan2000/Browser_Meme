from ui import go, click, links, fields

def run(h):
    h.note('Account locator disappeared after authentication; classify parent failure as locator, not business rejection. Inspect native anchor attributes before action. Explore featured release and sale controls.')
    go(h,'/')
    print('HEADER',[(x.get_attribute('href'),x.get_attribute('aria-label'),x.inner_text()) for x in h.page.locator('header a,header button').all()])
    go(h,'/release/221')
    links(h)
    fields(h)
