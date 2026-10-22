#!/usr/bin/env python3
"""Condition A model, bounded to observed navigation; unknown on business tasks.

Inputs:
 observation: {url: str, visible_text: str, account_link_visible: bool}
 intent: {operation: 'open_account'|'navigate_home'|other, scope: 'action'|'task'}
Aliases and natural-language business requests are deliberately not inferred.
Task predictions are unknown: no whole business task was executed.
"""
import json

def predict(observation, intent):
    observation = observation if isinstance(observation, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    answer = {'disposition':'unknown',
              'effects':{'persistent_state_changed':None,'affected_record_count':None},
              'ui_claims':[],
              'unknowns':['No observed business-operation or whole-task outcome is available']}
    if intent.get('scope') != 'action':
        return answer
    op = intent.get('operation')
    if op == 'navigate_home' and observation.get('url') in (
            'http://127.0.0.1:12042/', 'http://127.0.0.1:12042/login'):
        return {'disposition':'accepted',
                'effects':{'persistent_state_changed':False,'affected_record_count':0},
                'ui_claims':[{'claim':'Public landing page displays catalogue content and Account link',
                              'evidence_expected':'DOM at origin /'}],
                'unknowns':['Prediction limited to the observed anonymous session; no business write']}
    if (op == 'open_account' and observation.get('url') == 'http://127.0.0.1:12042/'
            and observation.get('account_link_visible') is True):
        return {'disposition':'accepted',
                'effects':{'persistent_state_changed':False,'affected_record_count':0},
                'ui_claims':[{'claim':'Navigates to /login and displays Sign in, Username or Email, and Password',
                              'evidence_expected':'URL /login and rendered login form'}],
                'unknowns':['Credential acceptance and login persistence are untested']}
    return answer

if __name__ == '__main__':
    print(json.dumps(predict({}, {})))
