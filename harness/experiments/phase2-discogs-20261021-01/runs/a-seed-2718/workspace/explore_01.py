def run(h):
    h.expect({'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['Initial site unknown']}, 'Discover public landing page and login controls')
    h.page.goto(h.origin)
    print(h.observe('landing'))
