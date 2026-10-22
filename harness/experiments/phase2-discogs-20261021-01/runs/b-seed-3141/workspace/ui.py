def step(h, locator, action, value=None, claim='Control responds', disposition='accepted', changed=False, count=0, why='Read back each UI action'):
    h.expect({'disposition':disposition,'effects':{'persistent_state_changed':changed,'affected_record_count':count},'ui_claims':[{'claim':claim,'evidence_expected':'Rendered DOM and UI-caused response'}],'unknowns':[] if disposition != 'unknown' else ['Effect requires readback']}, why)
    if action == 'goto':
        h.page.goto(value)
    elif action == 'click':
        locator.click()
    elif action == 'fill':
        locator.fill(value)
    elif action == 'select':
        locator.select_option(value)
    elif action == 'press':
        locator.press(value)
    elif action == 'hover':
        locator.hover()
    print(h.observe(claim))

