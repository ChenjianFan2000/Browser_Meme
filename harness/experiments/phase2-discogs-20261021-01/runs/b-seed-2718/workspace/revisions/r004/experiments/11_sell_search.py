from ui import go,click,fill,fields

def run(h):
    h.note('Find release selection UI; verify Create Listing requires selection. Avoid assuming text is programmatically labelled.')
    go(h,'/sell')
    print('CREATE_ENABLED',h.page.get_by_role('button',name='Create Listing',exact=True).is_enabled())
    fill(h,h.page.get_by_placeholder('Search releases...'),'Dark Side','Search seeded exact identity instead of guessing id')
    click(h,h.page.locator('section').first.get_by_role('button',name='Search',exact=True),'Run seller release search','Release choices shown','accepted',False,0)
    print('BUTTONS',h.page.locator('section').first.get_by_role('button').all_text_contents())
    print('INPUTS',[(i,x.get_attribute('value')) for i,x in enumerate(h.page.locator('section').first.locator('input').all())])
