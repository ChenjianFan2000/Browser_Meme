def prediction(disposition='unknown', changed=None, count=None, claim=None):
    return {'disposition':disposition,'effects':{'persistent_state_changed':changed,'affected_record_count':count},'ui_claims':[] if claim is None else [{'claim':claim,'evidence_expected':'rendered page readback'}],'unknowns':['Scope limited to observed UI conditions'] if disposition=='unknown' else []}

def act(h, locator, method='click', value=None, why='Inspect UI behavior', disposition='unknown', changed=None, count=None, claim=None):
    h.expect(prediction(disposition, changed, count, claim), why)
    if value is None:
        getattr(locator,method)()
    else:
        getattr(locator,method)(value)
    return h.observe(why)

def go(h, path, why='Navigate to previously observed link'):
    h.expect(prediction('accepted',False,0),why)
    h.page.goto(h.origin+path)
    return h.observe(why)
