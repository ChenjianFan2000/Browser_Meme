from ui import go, click, fill, links

def run(h):
    h.note('Distinguish required-field validation, invalid credential rejection, and valid fixture authentication. No account value printed.')
    go(h,'/login')
    click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Test empty login boundary','Login remains visible','rejected',False,0)
    fill(h,h.page.get_by_label('Username or Email'),h.fixture['account']['username'],'Use fixture username')
    fill(h,h.page.get_by_label('Password'),'deliberately-invalid-2718','Test invalid password with seeded account')
    click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Distinguish credential validation from successful login','An authentication error is shown','rejected',False,0)
    fill(h,h.page.get_by_label('Password'),h.fixture['account']['password'],'Use fixture password without logging its value')
    click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Authenticate with public fixture','Account navigation becomes available','accepted',False,0)
    links(h)
