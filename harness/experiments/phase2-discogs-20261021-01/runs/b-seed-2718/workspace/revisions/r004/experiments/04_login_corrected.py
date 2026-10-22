from ui import go, click, fill, links

def run(h):
    h.note('Parent experiment 03 failed with locator timeout after Sign in navigated home. Original inputs were prefilled, so the attempted empty test was not empty. Classification locator; preceding authentication navigation confirmed, no business write attempted. Correct using observed input structure and explicit values.')
    go(h,'/login')
    fill(h,h.page.locator('input').nth(1),'','Actually clear prefilled username')
    fill(h,h.page.locator('input[type=password]'),'','Actually clear prefilled password')
    click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Submit truly empty credentials','Validation error; remain on login','rejected',False,0)
    fill(h,h.page.locator('input').nth(1),h.fixture['account']['username'],'Use public fixture username')
    fill(h,h.page.locator('input[type=password]'),'deliberately-invalid-2718','Test invalid password')
    click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Submit invalid password','Error shown','rejected',False,0)
    fill(h,h.page.locator('input[type=password]'),h.fixture['account']['password'],'Use public fixture password')
    click(h,h.page.get_by_role('button',name='Sign in',exact=True),'Submit fixture credentials','Navigate home','accepted',False,0)
    print('NETWORK',h.network())
    click(h,h.page.get_by_role('link',name='Account',exact=True),'Inspect account link after authentication','Account or login rendered','unknown',False,0)
    links(h)
