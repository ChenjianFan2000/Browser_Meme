import publish_v2
import build_package as b
from pathlib import Path
import json, hashlib, shutil
b.rule('R36','Reusable native helpers added release221, initially absent in both account lists, first to wantlist and then collection; both memberships were independently read back and coexisted.',[35])
b.rule('R37','For release12, US shipping, exact default media/sleeve conditions and min_rating99.6 combined with newest sort returned only the active one-cent own listing. Packaged helpers explicitly selected release221 and filled quantity1 and price777 without submission.',[36])
b.rule('R38','Cart helper removal of the three known lines was confirmed individually across navigation. Empty cart rendered total0 and disabled Checkout. Adding listing643 then created a single cart line, quantity1, total1 cent.',[37])
b.rule('R39','A selector for the two identical release1 USD19.99 listing cards was ambiguous; reusable helper refused deactivation before any UI action. The disabled creation guard at price0 also returned an observation without submitting.',[38])
b.rule('R40','UI-caused cart responses used item id1 for listing145 in call12 and later item id1 for listing643 after the cart was emptied in call37. Cart item identity must include observed context and must not be assumed globally stable across deletion.',[12,37])
PURPOSES={
1:('Discover landing surface','Landing, login redirect, error','Public catalog and privacy banner'),
2:('Locate sign-in through rendered controls','Modal versus route; banner persistence','Cookie banner dismissed, Account link reached login'),
3:('Try semantic form labels','Associated label versus unassociated text','Locator timeout before fill; no business write'),
4:('Correct locator and contrast wrong versus fixture password','Both accepted, both rejected, only fixture accepted','Wrong password rejected; fixture login accepted'),
5:('Inspect authenticated Account identity','Link remains versus button/menu','Link assumption failed; DOM showed button'),
6:('Discover collection and release access','Collection route versus menu; release accessible name','Collection discovered; exact release link name assumption failed'),
7:('Inspect release, wantlist and seller objects','Membership toggle versus fixed add; selling absent versus form','Release data, seeded account memberships and seller form observed'),
8:('Repeat seeded membership and add other membership','Duplicate insert, idempotent, toggle, move','Repeated collection remained one; wantlist addition persisted'),
9:('Repeat wantlist and test collection/wantlist combination','Toggle, duplicates, independent memberships','One wantlist entry; release12 added to collection and retained wanted'),
10:('Search named artist and discover marketplace','Exact artist versus broad search; listings versus detail','Three Pink Floyd release identities; release12 marketplace two sellers'),
11:('Separate sort, shipping and minimum rating effects','Union versus intersection; validation versus no-match','Descending sort, AND filtering and101 empty response'),
12:('Add one listing from empty cart','No-op, rejected, single line','Cart quantity1 persisted'),
13:('Repeat same listing then add same release other seller','Idempotent, duplicate line, quantity increment','Same item quantity2; second seller separate item'),
14:('Remove a quantity2 line and discover seller search','Remove one unit versus whole item; release selection required','Whole line removed; unique title auto-selected'),
15:('Test negative price rejection','Disabled UI, server rejection, acceptance','Disabled button timed out; no business write'),
16:('Contrast numeric UI boundaries then create valid listing','Zero quantity disabled versus enabled; cents semantics','Quantity0 enabled, prices0/-1 disabled; valid quantity2 listing640 created'),
17:('Test own-listing cart prohibition','Reject ownership versus accept','Accepted own listing640; prohibition refuted'),
18:('Deactivate a carted listing and compare surfaces','Delete, inactive; cart invalidated versus retained','Inactive owner record, marketplace removal, cart retained'),
19:('Test empty and partial search, genre and add-release link','Case/partial matching, empty-query behavior, route implementation','Empty prompt; lowercase partial matched; genre page; Add Release404'),
20:('Test signed-out access and membership action','Redirect, render protected data, unauthorized write','Protected routes and membership click redirected to login'),
21:('Test login next destination and persistent cart','Home-only login versus next; cart clear versus retain','Login returned cart and prior contents; canonical want counter3'),
22:('Test unrecognized condition string','Enumerated rejection versus free string','Custom media string accepted as listing641'),
23:('Test cart quantity beyond stock1','Cap, reject, increment','Second add accepted item quantity2'),
24:('Test identical listing creation and explicit selection','Deduplicate, reject, distinct record','Distinct listing642; first-result auto-select and explicit221'),
25:('Discriminate marketplace text matching','Substring, exact, case-insensitive, case-sensitive','Tested condition/country exact and case-sensitive; AND sleeve'),
26:('Correct parent quantity0 claim and submit boundary','Disabled, accepted zero stock, backend rejection','Enabled UI;422 quantity>=1, no listing created'),
27:('Test fractional integer fields and minimum accepted price','Truncate, accept decimals, reject','Each fractional field422; one-cent listing643 created'),
28:('Test selector state after new/no/empty/repeated search','Retain selection versus clear or reset','No/empty selection cleared; repeat multi search selected first; inactive Deactivate enabled'),
29:('Repeat confirmed deactivation','Reject, delete, no state change','Success retained inactive owner state and cart'),
30:('Test equality and invalid minimum-rating format','Inclusive/exclusive threshold, bounded/unbounded, validation/error','92.7 inclusive; -1 accepted; abc application error'),
31:('Recover and discriminate search fields','Title/artist only versus label/year/genre matching','Home recovered; tested title partial and whitespace artist matched; other queries empty'),
32:('Follow genre tabs/style and community targets','Dedicated filtered views versus text search; real community route versus404','Genre links navigated search; Forum and Blog404'),
33:('Test three empty listing strings','Required strings versus empty acceptance','422 with individual min-length1 errors for all three'),
34:('Revisit previously rendered inactive-listing add UI route','Missing control only versus actual inactive rejection','UI-caused POST404 Listing not found; cart unchanged'),
35:('Exercise packaged membership helpers on fresh release221','Wrong identity, absent persistence, coexisting memberships','Both new memberships independently confirmed'),
36:('Exercise packaged filter and listing-form helpers','Wrong selection/filter or scope versus exact matching','One-cent own row matched four fields;221 explicitly selected; no form submission'),
37:('Exercise cart identity helpers, empty state and new line','Ambiguous seller, remove one unit, full removal; empty checkout enabled','All targets removed and read back; empty Checkout disabled; one-cent cart prepared'),
38:('Verify no-write guards and newest readback','Wrong duplicate selection or disabled submission versus refusal','Ambiguous deactivation and disabled creation refused; cart readback intact'),
39:('Smoke final packaged native functions and current state','Packaging/import/locator defects versus usable helpers','See original browser evidence'),
40:('Single checkout observation on one-cent active cart','Accepted checkout, rejected checkout, placeholder or unconfirmed write','See final browser evidence; never retry')}

def enrich(dest,max_call,stop_reason=None):
 d=Path(dest)
 cov=json.loads((d/'coverage.json').read_text())
 cov['explored']+=['fractional and zero quantity server rejection','one-cent accepted price','condition text and empty strings validation','stock-one cart boundary','distinct duplicate listing creation','search selection state','repeat deactivation and actual inactive-cart rejection','native helper execution and guards','empty-cart checkout disabled state']
 cov['unexplored']=['membership removal and listing reactivation through unavailable controls','checkout inventory, inactive-item and multi-seller semantics','larger numeric bounds, alternate accounts, unusual encodings and unobserved routes']
 cov['current_competing_hypotheses']=[{'question':'Untested checkout stock and inactive-item checks','alternatives':['validated at checkout','not validated','operation unavailable'],'distinguishing_experiment':'Separate checkout test after confirming cart and stock, within a new authorized budget'}]
 cov['rejection_evidence']+=b.refs(26,27,33,34)
 cov['boundary_evidence']+=b.refs(23,25,26,27,28,30,33,37,38)
 cov['success_evidence']+=b.refs(22,24,27,29,35,36,37)
 cov['stop_reason']=stop_reason
 cov['limitations']+=['Parent r001 contains a now-corrected quantity0 UI error. R17 in later revisions supersedes it with original and new browser evidence.','No whole-task success or prediction score is asserted. Execution helpers are procedural UI code, not an executable behavior-prediction model.']
 (d/'coverage.json').write_text(json.dumps(cov,indent=2)+'\n')
 obj=json.loads((d/'objects.json').read_text()); snapshots={}
 for call in sorted(b.CALLS):
  if call>max_call:continue
  folder=b.CALLS[call]
  for response in json.loads((folder/'network.json').read_text()):
   body=response.get('body');url=response.get('url','')
   if '/api/me/listings' in url and isinstance(body,dict) and isinstance(body.get('items'),list):
    for item in body['items']:
     public={k:v for k,v in item.items() if k in ['id','release_id','release_title','title','status','price_cents','quantity','media_condition','sleeve_condition','ships_from','comments','currency']}
     key='listing-state:'+json.dumps(public,sort_keys=True)
     if key not in snapshots:snapshots[key]={'kind':'observed owner listing state','fields':public,'first_observed_call':call,'evidence_refs':[b.ref(folder/'network.json')],'uncertainty':'Temporal observed state, not immutable identity or current-state guarantee'}
     snapshots[key]['last_observed_call']=call
   if '/api/cart' in url and isinstance(body,dict) and isinstance(body.get('items'),list):
    public={'items':body['items'],'total_cents':body.get('total_cents'),'currency':body.get('currency')}
    key='cart-state:'+json.dumps(public,sort_keys=True)
    if key not in snapshots:snapshots[key]={'kind':'observed cart snapshot','fields':public,'first_observed_call':call,'evidence_refs':[b.ref(folder/'network.json')],'uncertainty':'Cart item IDs may be reused after deletion; use this call context'}
    snapshots[key]['last_observed_call']=call
 obj['response_object_snapshots']=list(snapshots.values())
 obj['business_objects'] += [{'identity':'release/221','title':'The Dark Side Of The Moon','artist':'Pink Floyd','relationships':['new collection membership','new wantlist membership','marketplace25 observed listings'],'actions':['search result selection','add collection','add wantlist'],'evidence_refs':b.refs(10,35,36),'uncertainty':'Only observed supplied-account state'},{'identity':'listing/641 and listing/642','release_id':1,'relationship':'separate identical active own listings','actions':['creation','641 repeated cart add'],'evidence_refs':b.refs(22,23,24),'uncertainty':'Identical DOM cards can require explicit disambiguation; helper refuses ambiguity'},{'identity':'listing/643','release_id':12,'price_cents':1,'quantity':1,'relationship':'active own listing; final prepared cart','actions':['creation','cart add'],'evidence_refs':b.refs(27,37),'uncertainty':'Checkout state determined separately'}]
 (d/'objects.json').write_text(json.dumps(obj,indent=2)+'\n')
 lines=[json.loads(l) for l in (d/'exploration.jsonl').read_text().splitlines()]
 for x in lines:
  if x['level']=='experiment':
   why,alts,actual=PURPOSES.get(x['experiment'],('Unknown','Unknown','Unknown'))
   x['why_selected']=why;x['alternatives_considered']=alts;x['actual_evidence']['bounded_interpretation']=actual
 for call in sorted(b.CALLS):
  if call>max_call:continue
  folder=b.CALLS[call]; records=[json.loads(l) for l in (folder/'actions.jsonl').read_text().splitlines()]
  completed={int(x['label'].split('-')[1]) for x in records if x.get('kind')=='observation' and x.get('label','').startswith('after-')}
  for x in records:
   if x.get('kind')=='action_before' and x['action'] not in completed:
    lines.append({'experiment':call,'level':'per_action_failure','why_selected':x.get('rationale'),'alternatives_considered':PURPOSES.get(call,['',''])[1],'prediction':x.get('prediction'),'actual_evidence':{'result':json.loads((folder/'result.json').read_text()).get('error')},'classification':'locator' if call in [3,5,6] else 'business_rule + implementation' if call==15 else 'unknown','resulting_revision':d.name,'evidence_refs':b.refs(call)})
 (d/'exploration.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in lines))
 (d/'README.md').write_text('Condition B independent browser-only learning package.\n\nRead rulebook.md and rules.json for bounded observations and unknowns. revision.json records the parent; all parent directories and failed experiments remain. evidence_refs paths are relative to the workspace root and reference original exported browser artifacts.\n\nUse scripts.py through phase2.execute_script. It exports run(h), a read-only home smoke entry point, and supervised native helpers: navigate, sign_in, search, add_membership, filter_marketplace, find_listing_release, fill_listing, submit_listing, deactivate_listing, add_cart, remove_cart, checkout_once. Import via a temporary workspace script and pass this scripts.py in modules. Supply per-action expectations to act when known; default expectations remain unknown. Always inspect observations and UI-caused network evidence; no write retries are implemented.\n\nThese are task execution helpers, not a predictor. No behavior_model.py exists. Locator-based helpers intentionally refuse ambiguous records. No private tasks or evaluator feedback were used.\n')
 rev=json.loads((d/'revision.json').read_text());rev['failure_category']=['locator','business_rule','implementation']
 rev['rationale']='Supersede corrected parent with original-evidence-backed rules, response object snapshots, improved cart identity scoping and executable native helper validation. Preserve failures and all parent revisions.'
 rev['script_validation_evidence']=b.refs(*[c for c in [35,36,37,38,39,40] if c<=max_call])
 (d/'revision.json').write_text(json.dumps(rev,indent=2)+'\n')
 # Complete evidence inventory includes screenshots and original observations.
 manifest=[b.ref(p) for folder in b.CALLS.values() if int(folder.name.split('-')[1])<=max_call for p in sorted(folder.iterdir()) if p.is_file()]
 (d/'evidence_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return d
if __name__=='__main__':
 print(enrich(b.publish('r003','r002',38),38))
