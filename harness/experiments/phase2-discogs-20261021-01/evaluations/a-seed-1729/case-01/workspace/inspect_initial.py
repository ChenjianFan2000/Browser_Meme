def run(h):
    h.expect({'disposition':'unknown','effects':{'persistent_state_changed':False,'affected_record_count':0},'ui_claims':[],'unknowns':['Initial UI not yet inspected']}, 'Read initial homepage only')
    h.page.goto(h.origin)
    print(h.observe('initial-home'))
