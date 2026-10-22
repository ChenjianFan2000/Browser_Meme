from ui import go,click,links,fields

def run(h):
    h.note('Compare own-listing restriction versus unrestricted cart, and repeated listing quantity versus membership. All adds use discovered links, with cart readback before repeats.')
    go(h,'/cart')
    print('CHECKOUT',[(x.is_enabled(),x.get_attribute('disabled')) for x in h.page.get_by_role('button',name='Checkout',exact=True).all()])
    go(h,'/sell/release/221')
    click(h,h.page.locator('a[href="/cart?add=4"]'),'Add cheapest listing belonging to fixture seller: test self-purchase restriction','Cart row or rejection')
    fields(h);links(h)
    go(h,'/cart')
    go(h,'/sell/release/221')
    click(h,h.page.locator('a[href="/cart?add=4"]'),'Repeat first add after confirmed cart readback','One row or quantity increases')
    go(h,'/cart')
    print('BUTTONS',h.page.get_by_role('button').all_text_contents());fields(h)
