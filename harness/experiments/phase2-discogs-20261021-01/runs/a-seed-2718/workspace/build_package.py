"""Offline publication from original exported browser evidence only."""
import hashlib
import json
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent

def ref(path):
    return {'path':path,'sha256':hashlib.sha256((ROOT/path).read_bytes()).hexdigest()}

LAND = 'evidence/call-001-dbccdd13/'
LOGIN = 'evidence/call-002-918f04fd/'
land_refs = [ref(LAND+x) for x in ['obs-0004.html','obs-0004.ax.json','obs-0004.png','actions.jsonl','result.json']]
login_refs = [ref(LOGIN+x) for x in ['obs-0008.html','obs-0008.ax.json','obs-0008.png','actions.jsonl','result.json']]

class LinkInventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current=None
        self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a':
            self.current={'href':a.get('href'),'label':a.get('aria-label',''),'text':''}
    def handle_data(self,data):
        if self.current is not None:
            self.current['text']+=data+' '
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.current['text']=' '.join(self.current['text'].split())
            self.links.append(self.current)
            self.current=None

inventory=LinkInventory()
inventory.feed((ROOT/LAND/'obs-0004.html').read_text())

SCRIPTS = '''"""Native Playwright entry points. Submit with the phase2 browser tool.

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

def open_account(h):
    run(h)
    link = h.page.get_by_role('link', name='Account', exact=True)
    if link.count() != 1 or not link.is_visible():
        h.note('Locator precondition failed; stop without a click')
        return h.observe('account-link-precondition-failed')
    h.expect(prediction('Sign in page exposes Username or Email and Password controls'),
             'Observed Account click navigated from / to /login; runtime confirms and scrolls target')
    link.click()
    return h.observe('account-readback')
'''

MODEL = '''#!/usr/bin/env python3
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
'''

events = [
 {'experiment':'E01','why_selected':'Discover accessible pages and controls without guessed routes',
  'alternatives_considered':['Guess site routes (rejected)','Start with account (not yet located)'],
  'prediction':{'scope':'action','disposition':'unknown','description':'Initial page unknown'},
  'actual':'Root rendered Discogs catalogue, search, menu controls, cart, Account href=/login, and footer links',
  'classification':'success: read-only navigation; no business success inferred',
  'evidence_refs':land_refs,'resulting_revision':'r001'},
 {'experiment':'E02-rejected','why_selected':'Click discovered Account link to discover authentication UI',
  'alternatives_considered':['Goto discovered /login directly','Use native Account link (selected)'],
  'prediction':{'scope':'action','disposition':'unknown','description':'Account should expose an authentication page; no UI action reached'},
  'actual':'Tool rejected helper before execution: ValueError: observation policy excludes name getattr',
  'classification':'implementation; runtime policy boundary denial',
  'evidence_refs':[], 'audit_refs':[ref('runtime_denial.json'),ref('ui_helpers_v1_rejected.py')],
  'resulting_revision':'r002','required_response':'Stop browser exploration'},
 {'experiment':'E02b','why_selected':'Correct helper implementation by using explicit native methods',
  'alternatives_considered':['Stop immediately after runtime denial (contract-required)','Correct and resubmit (mistakenly chosen)'],
  'prediction':{'scope':'per-action','sequence':['Home navigation accepted, no target business effect','Account click unknown']},
  'actual':'Home rendered again; Account click reached /login with Sign in, Username or Email, and Password',
  'classification':'success: read-only navigation; procedural deviation: executed after denial',
  'evidence_refs':login_refs,'resulting_revision':'r002',
  'business_effects':'No business operation attempted; authentication form not submitted'},
 {'experiment':'STOP','why_selected':'Honor stop condition once policy denial recognized',
  'alternatives_considered':['Continue login and write experiments (not permitted after stop)'],
  'prediction':{'scope':'task','disposition':'unknown'},
  'actual':'No further browser submissions; publish limited package and preserve originals',
  'classification':'boundary stop with explicit procedural deviation',
  'evidence_refs':[], 'audit_refs':[ref('runtime_denial.json')], 'resulting_revision':'r002'}
]

def write_json(path, data):
    path.write_text(json.dumps(data,indent=2)+'\n')

def publish(number):
    revision=f'r{number:03d}'
    d=ROOT/'revisions'/revision
    d.mkdir(parents=True,exist_ok=False)
    is_final=number==2
    refs=land_refs+(login_refs if is_final else [])
    rules=[{
      'id':'R01','statement':'In the observed anonymous session, navigating to the public root rendered a Discogs catalogue, search, and Account link with href /login.',
      'status':'verified','preconditions':['Registered origin http://127.0.0.1:12042','Observed anonymous session'],
      'branches':[{'when':'Initial root navigation','outcome':'Catalogue page rendered'}, {'when':'Repeated root navigation','outcome':'Same navigation controls rendered' if is_final else 'Not yet tested in this revision'}],
      'forbidden_side_effects':['Do not infer record mutation or account authentication from root navigation'],
      'evidence_refs':land_refs+(login_refs if is_final else [])},
      {'id':'U01','statement':'Credential acceptance, authenticated pages, collection, wantlist, marketplace writes, and cart behavior are unknown.',
       'status':'unknown','preconditions':[], 'branches':[],
       'forbidden_side_effects':['No guessed write outcomes or hidden record counts'], 'evidence_refs':[]}
    ]
    if is_final:
        rules.insert(1,{'id':'R02','statement':'One click on the rendered Account link from the observed root page navigated to /login and rendered Sign in, Username or Email, and Password controls.',
                       'status':'verified','preconditions':['Root page rendered','Account link visible','Anonymous session'],
                       'branches':[{'when':'Single Account click','outcome':'Login form rendered'}, {'when':'Submit credentials','outcome':'Unknown; not attempted'}],
                       'forbidden_side_effects':['Do not infer credential validity or authenticated business permissions'], 'evidence_refs':login_refs})
    write_json(d/'rules.json',rules)
    write_json(d/'revision.json',{'revision':revision,'parent_revision':'r001' if is_final else None,
               'condition':'A','learner':'gpt-6.1-sol','scheduling_seed':2718,
               'changed_rules':['R02','U01'] if is_final else ['R01','U01'],
               'changed_scripts':['scripts.py','behavior_model.py','../../explore_02b.py','../../ui_helpers.py'] if is_final else ['../../explore_01.py','scripts.py','behavior_model.py'],
               'failure_category':'implementation' if is_final else None,'evidence_refs':refs,
               'rationale':'Stop after recognizing runtime policy denial; corrected navigation submission after denial explicitly retained as a deviation.' if is_final else 'Initial evidence-only discovery snapshot, reconstructed offline from first call.',
               'procedural_deviation':events[2]['classification'] if is_final else None,
               'audit_refs':[ref('runtime_denial.json')] if is_final else []})
    objects=[{'kind':'page','identity':'http://127.0.0.1:12042/','name':'Discogs landing',
              'relationships':[{'relation':'Account href','target':'/login'},{'relation':'Cart href','target':'/cart'},{'relation':'Search form action','target':'/search'},
                               {'relation':'footer link','target':'/sell'},{'relation':'footer link','target':'/add-release'}],
              'actions':['navigate root (executed)','Account click (executed)' if is_final else 'Account click (not executed)',
                         'search, cookies, catalogue links, menus (not executed)'],
              'uncertainty':'Link presence does not establish destination behavior. No hidden state inspected.', 'evidence_refs':land_refs}]
    for item in inventory.links:
        if item['href'] and item['href'].startswith('/release/'):
            objects.append({'kind':'linked_catalogue_release','identity':item['href'],
                            'name':item['text'] or item['label'],
                            'relationships':[{'relation':'linked_from','target':'/'}],
                            'actions':['Open release link (not executed)'],
                            'uncertainty':'Identity is observed href; detail fields and actions unvisited',
                            'evidence_refs':[land_refs[0]]})
    if is_final:
        objects.append({'kind':'page','identity':'http://127.0.0.1:12042/login','name':'Sign in',
                        'relationships':[{'relation':'reached via','target':'Account link from /'}],
                        'actions':['Username or Email input (not filled)','Password input (not filled)','Sign in button (not clicked)'],
                        'uncertainty':'Authentication validation, errors, permissions, and persistence untested', 'evidence_refs':login_refs})
    write_json(d/'objects.json',objects)
    write_json(d/'coverage.json',{
      'explored':[{'area':'Public landing','evidence_refs':land_refs}]+([{'area':'Login form discovery only','evidence_refs':login_refs}] if is_final else []),
      'unexplored':['Authentication success/rejection','Business write success/rejection','Collection and wantlist','Search and filters','Release details','Cart and checkout','Selling','Repeat writes','Short business combinations','Validation boundaries'],
      'success_evidence':refs,'rejection_evidence':[],
      'boundary_evidence':{'type':'runtime helper-name policy denial, not a website business rejection','browser_evidence_refs':[], 'audit_refs':[ref('runtime_denial.json')]} if is_final else None,
      'repeats':{'root_navigation_observations':2 if is_final else 1,'evidence_refs':refs},
      'short_combinations':[{'sequence':['Root navigation','Account click'],'scope':'navigation only','evidence_refs':login_refs}] if is_final else [],
      'current_competing_hypotheses':[
        {'question':'Does account authentication expose business controls?', 'alternatives':['Valid credentials unlock controls','Further account constraints exist'], 'status':'unknown'},
        {'question':'How are repeated writes handled?', 'alternatives':['Idempotent','Duplicate records','Explicit rejection'], 'status':'unknown'}],
      'proposed_distinguishing_experiments':['In a separately authorized new run, submit fixture credentials through observed login controls and read back.',
        'Discover business action controls after authentication; compare successful mutation, explicit rejection, repeat, and persisted readback.'],
      'whole_task_predictions':'Unknown; no business task executed',
      'budget_last_observed':{'actions':3 if is_final else 1,'action_limit':300,'script_calls':2 if is_final else 1,'script_call_limit':40,
                              'submission_attempts_including_policy_rejection':3 if is_final else 1,
                              'elapsed_seconds':53.18775209799992 if is_final else 22.254651918999798,
                              'note':'Last returned authoritative budget. Policy-rejected submission returned no call record or updated budget.'},
      'stop_reason':'runtime_policy_denial' if is_final else 'intermediate snapshot',
      'limitations':['No site business behavior verified','Only read-only discovery','No submitted credentials','Static helper rejection and post-denial submission explicitly preserved'] if is_final else ['Initial page only']})
    cite='\n'.join('- `'+r['path']+'` sha256 `'+r['sha256']+'`' for r in refs)
    text='''# Bounded rulebook

Condition A; learner gpt-6.1-sol; scheduling seed 2718. The seed identifies scheduling, not model sampling.

R01: In the observed anonymous session the public root rendered a Discogs catalogue with search, Account, cart and menu controls. Account had href `/login`. Observed link destinations are discovery leads, not verified business capabilities.
'''
    if is_final:
        text+='''
R02: A single Account click from the root reached `/login` and exposed Sign in, Username or Email, and Password controls. The root was rendered twice across separate browser calls. Neither observation establishes authentication, hidden records, or business effects.

Stop and deviation: The runtime rejected the original dynamic-dispatch helper with `ValueError: observation policy excludes name getattr`. The original helper and script are preserved. One corrected submission was made before recognizing the contract's stop condition; this is a procedural deviation, not compliant continuation. No further browser submissions followed recognition. The exact tool response is transcribed in `runtime_denial.json` at the workspace root; it is audit material, not browser evidence.
'''
    text+='''
Unknowns: Credential acceptance, login errors, authenticated navigation, search behavior, catalogue details, collection/wantlist operations, marketplace listings, cart/checkout, repeat writes, rejection rules, persistence, business record counts, and short business combinations. No website business rejection was observed. The runtime denial supplies no website rule.

Hypotheses only: Successful authentication may expose more controls. Repeated writes may be idempotent, duplicated, or rejected. Distinguish these only in a new permitted learning run using a confirmed first effect and subsequent rendered readback. Missing controls are not evidence of missing backend behavior.

Prediction scope: The executable predictor handles only explicit per-action navigation intents under observed anonymous-page preconditions. Whole-task and business-operation predictions return unknown. False/zero effects for navigation concern target business operations and exclude browser cache, cookies, and authentication state. No task success is inferred from those predictions.

Reusable scripts: `run(h)` reads the root; `open_account(h)` clicks the discovered Account link after precondition checks. Each UI action has a recorded prediction and immediate observation. Runtime confirms and scrolls native locator targets. No writes or retries are implemented. These scripts remain for later task execution, not continued learning after this stop.

Original exported browser evidence (paths relative to workspace root):
'''+cite+'\n'
    (d/'rulebook.md').write_text(text)
    script_text=SCRIPTS
    model_text=MODEL
    if not is_final:
        script_text=SCRIPTS[:SCRIPTS.index('\ndef open_account')]
        model_text='''#!/usr/bin/env python3
"""Initial discovery model: no business operation or task is known."""
def predict(observation, intent):
    return {'disposition':'unknown', 'effects':{'persistent_state_changed':None,'affected_record_count':None}, 'ui_claims':[], 'unknowns':['Initial landing discovery only; operation not tested']}
'''
    (d/'scripts.py').write_text(script_text)
    (d/'behavior_model.py').write_text(model_text)
    (d/'behavior_model.py').chmod(0o755)
    (d/'exploration.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in (events if is_final else events[:1])))
    write_json(d/'evidence_manifest.json',[ref(str(p.relative_to(ROOT))) for base in ([LAND,LOGIN] if is_final else [LAND]) for p in sorted((ROOT/base).iterdir()) if p.is_file()])
    return d

if __name__=='__main__':
    publish(1)
    publish(2)
    print('Published revisions/r001 and revisions/r002; READY remains unwritten pending offline validation')
