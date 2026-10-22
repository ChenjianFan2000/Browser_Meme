"""Retrospective checkpoint using only calls 001-006; condition A."""
def predict(observation, intent):
    out = {'disposition':'unknown','effects':{'persistent_state_changed':None,'affected_record_count':None},'ui_claims':[],'unknowns':['No supported checkpoint rule for these conditions.']}
    if not isinstance(observation,dict) or not isinstance(intent,dict):
        return out
    op = intent.get('operation')
    if op == 'auth.sign_in' and observation.get('account_scope') == 'supplied_fixture' and observation.get('page_kind') == 'login' and observation.get('fixture_credentials_supplied') is True:
        out.update(disposition='accepted',effects={'persistent_state_changed':False,'affected_record_count':0},ui_claims=[{'claim':'Home page follows the valid seeded login.','evidence_expected':'Home DOM after Sign in.'}],unknowns=['Invalid and blank credentials untested.'])
    elif op == 'wantlist.add' and str(intent.get('release_id')) == '221' and observation.get('authenticated') is True and observation.get('account_scope') == 'supplied_fixture' and (observation.get('memberships') or {}).get('wantlist') is False:
        out.update(disposition='accepted',effects={'persistent_state_changed':True,'affected_record_count':1},ui_claims=[{'claim':'Wantlist gains a card for release 221.','evidence_expected':'Fresh /me/wantlist DOM.'}],unknowns=['Repeats, collection interaction and other releases untested.'])
    return out
