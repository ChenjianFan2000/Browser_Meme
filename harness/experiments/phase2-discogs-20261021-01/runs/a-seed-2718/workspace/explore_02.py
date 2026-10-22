from ui_helpers import act, go

def run(h):
    go(h,'/')
    act(h,h.page.get_by_role('link',name='Account',exact=True),why='Discover authentication form')
    print(h.observe('login-form'))
