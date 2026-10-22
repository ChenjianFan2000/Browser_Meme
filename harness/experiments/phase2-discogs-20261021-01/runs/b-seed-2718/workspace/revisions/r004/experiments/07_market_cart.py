from ui import go,click,links,fields

def run(h):
    h.note('Inspect cart baseline and release-specific marketplace; discover listing identity, shipping, cart constraints before purchase experiments.')
    go(h,'/cart'); links(h);fields(h)
    go(h,'/release/221')
    go(h,'/sell/release/221'); links(h);fields(h)
    print('BUTTONS',h.page.get_by_role('button').all_text_contents())
