from ui import go,click,links,fields

def run(h):
    h.note('Repeat add doubled total without extra visible row; distinguish hidden quantity from duplicate rows via allowed cart response and remove. Combine different sellers then remove and checkout.')
    go(h,'/sell/release/221')
    click(h,h.page.locator('a[href="/cart?add=7"]'),'Add another seller listing to existing cart','Second row and aggregate total')
    click(h,h.page.get_by_role('button',name='Remove',exact=True).first,'Remove repeated first listing','Test removal of all quantity vs decrement')
    go(h,'/cart')
    click(h,h.page.get_by_role('button',name='Checkout',exact=True),'Explore checkout with one confirmed second-seller item','Checkout form or order response')
    fields(h);links(h)
    print('BUTTONS',h.page.get_by_role('button').all_text_contents())
