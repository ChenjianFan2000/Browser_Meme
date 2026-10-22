from ui import go,click,links,fields

def run(h):
    h.note('Checkout emptied cart; inspect natural response before any repeat. Discover Sell Music and Add Release pages without guessed routes or APIs.')
    go(h,'/cart')
    go(h,'/sell');fields(h);links(h)
    print('FORMS',[(x.get_attribute('action'),x.inner_text()) for x in h.page.locator('form').all()])
    print('SELECTS',[(x.get_attribute('name'),x.inner_text()) for x in h.page.locator('select').all()])
    go(h,'/add-release');fields(h);links(h)
    print('BUTTONS',h.page.get_by_role('button').all_text_contents())
