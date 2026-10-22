"""Retrospective checkpoint scripts. Use with own behavior_model.py module.
Only release 221 discovery and first wantlist addition were observed by call 006.
"""
from behavior_model import predict

def run(h):
    h.expect({'disposition':'unknown','effects':{'persistent_state_changed':False,'affected_record_count':0},'ui_claims':[],'unknowns':['Inspect current release state.']}, 'Open previously discovered release 221')
    h.page.goto(h.origin + '/release/221')
    print(h.observe('release-current'))

def add_new_wantlist_221(h):
    run(h)
    button = h.page.get_by_role('button',name='Add to Wantlist',exact=True)
    if button.count()!=1 or not button.is_visible():
        raise ValueError('Inspect current DOM before acting.')
    # Membership baseline is deliberately unknown unless independently observed.
    h.expect(predict({'authenticated':True,'memberships':{}},{'operation':'wantlist.add','release_id':221}), 'One addition; do not retry on missing confirmation')
    button.click()
    print(h.observe('wantlist-add'))
    h.expect({'disposition':'accepted','effects':{'persistent_state_changed':False,'affected_record_count':0},'ui_claims':[],'unknowns':[]}, 'Fresh wantlist readback')
    h.page.goto(h.origin+'/me/wantlist')
    print(h.observe('wantlist-readback'))
