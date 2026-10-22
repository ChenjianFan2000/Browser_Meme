def expect(h, why, claim='', disposition='unknown', changed=None, count=None):
    h.expect({'disposition':disposition,'effects':{'persistent_state_changed':changed,'affected_record_count':count},'ui_claims':[{'claim':claim,'evidence_expected':'Rendered page readback'}] if claim else [],'unknowns':['Effects outside visible readback are unknown']},why)

def snap(h,label):
    o=h.observe(label)
    print(label, o.get('url'), o.get('visible_text','').split('DISCOGS')[0])
    return o

def go(h,path,why='Navigate to a DOM-discovered same-origin URL'):
    expect(h,why,'Requested page renders','accepted',False,0)
    h.page.goto(h.origin+path)
    return snap(h,'navigation')

def click(h,loc,why,claim='',disposition='unknown',changed=None,count=None):
    expect(h,why,claim,disposition,changed,count)
    loc.click()
    return snap(h,'after-click')

def fill(h,loc,value,why):
    expect(h,why,'Input contains requested value','accepted',False,0)
    loc.fill(value)
    return snap(h,'after-fill')

def select(h,loc,value,why):
    expect(h,why,'Requested option is selected','accepted',False,0)
    loc.select_option(value)
    return snap(h,'after-select')

def links(h):
    print('LINKS',[(x.inner_text(),x.get_attribute('href')) for x in h.page.locator('a').all()])

def fields(h):
    print('FIELDS',[(x.get_attribute('type'),x.get_attribute('name'),x.get_attribute('placeholder'),x.get_attribute('id')) for x in h.page.locator('input,textarea,select').all()])
