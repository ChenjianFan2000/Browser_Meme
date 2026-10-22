from ui import go, click, snap, fields

def run(h):
    h.note('Discover login fields before using public account. Competing hypotheses: anonymous restrictions versus preauthenticated account.')
    go(h,'/')
    click(h,h.page.get_by_role('button',name='Accept All Cookies',exact=True),'Dismiss cookie banner for navigation','Cookie banner disappears','accepted',False,0)
    click(h,h.page.get_by_role('link',name='Account',exact=True),'Discover authentication UI','Login page is rendered','accepted',False,0)
    fields(h)
