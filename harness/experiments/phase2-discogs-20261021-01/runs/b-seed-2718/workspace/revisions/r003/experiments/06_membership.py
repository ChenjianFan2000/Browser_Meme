from ui import go,click,links,fields

def run(h):
    h.note('Compare membership set semantics vs duplicate rows vs toggle. Baseline each account list, add one known release twice with immediate readback and list navigation.')
    go(h,'/me/collection')
    links(h); fields(h)
    go(h,'/me/wantlist')
    links(h); fields(h)
    go(h,'/release/221')
    click(h,h.page.get_by_role('button',name='Add to Wantlist',exact=True),'First wantlist membership trial','Added status or count changes')
    print('BUTTONS',h.page.get_by_role('button').all_text_contents())
    if h.page.get_by_role('button',name='Add to Wantlist',exact=True).count():
        click(h,h.page.get_by_role('button',name='Add to Wantlist',exact=True),'Repeat confirmed wantlist action to test duplication','Membership may remain one')
    go(h,'/me/wantlist')
    go(h,'/release/221')
    click(h,h.page.get_by_role('button',name='Add to Collection',exact=True),'Add same release to independent collection','Collection membership changes')
    if h.page.get_by_role('button',name='Add to Collection',exact=True).count():
        click(h,h.page.get_by_role('button',name='Add to Collection',exact=True),'Repeat confirmed collection add','May permit multiple copies or remain one')
    go(h,'/me/collection')
    links(h);fields(h)
