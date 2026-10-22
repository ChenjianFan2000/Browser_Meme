"""Native Playwright entry points. Submit with the phase2 browser tool.

run(h): inspect landing page.
open_account(h): navigate home, click the observed Account link, read back.
These are discovery/navigation scripts; no business write is implemented.
No retries are performed. Runtime exports original per-action evidence.
"""

def prediction(claim):
    return {'disposition':'accepted',
            'effects':{'persistent_state_changed':False,'affected_record_count':0},
            'ui_claims':[{'claim':claim,'evidence_expected':'Rendered DOM and URL after navigation'}],
            'unknowns':[]}

def run(h):
    h.expect(prediction('Landing page exposes a catalogue and Account link'),
             'Repeat the observed public landing navigation; no business operation')
    h.page.goto(h.origin)
    return h.observe('landing-readback')
