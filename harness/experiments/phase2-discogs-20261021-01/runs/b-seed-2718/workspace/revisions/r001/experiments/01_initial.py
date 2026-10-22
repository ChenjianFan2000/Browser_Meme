def run(h):
    h.expect({'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['Initial page unobserved']}, 'Discover public landing page and navigation')
    h.page.goto(h.origin)
    print(h.observe('initial'))
