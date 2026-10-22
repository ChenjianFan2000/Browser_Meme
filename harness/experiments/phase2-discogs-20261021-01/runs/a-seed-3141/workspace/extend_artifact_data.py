import json
from pathlib import Path
p=Path('artifact_data.json');d=json.loads(p.read_text())
r=d['rules']
r += [
['R16','Public searches pink floyd and PINK FLOYD returned the same three releases153,180,221; moon returned221. A deliberately unmatched query returned no release links; blank query showed Enter a query in the search bar.','verified',['Observed current seeded catalogue'],['Other search fields and matching behavior remain unknown'],[17,32]],
['R17','The Rock Releases and Classic Rock links navigated to text search queries rock and Classic Rock, each with zero results despite release221 displaying Rock/Classic Rock metadata.','verified',['Observed genre/rock and release221'],['Do not treat these links as verified metadata filtering'],[4,18,25]],
['R18','For release84, first Wantlist and Collection adds each persisted one membership. Repeating Wantlist raised the immediate sidebar count again but navigation returned Have7/Want7; personal lists each contained one release84 link.','verified',['Supplied account; release84 previously absent from personal lists'],['Analogous broader release behavior remains a hypothesis'],[18]],
['R19','Seller search Pink Floyd automatically selected the first of three results, release153. Explicit selection by the rendered #221 button changed it to221. A subsequent no-match search cleared selection and disabled Create Listing.','verified',['Observed multi-result and no-match queries'],['Exact accessible-name locator without whitespace failed; native regex/filter selector succeeded'],[19,20,33]],
['R20','Two consecutive confirmed Create Listing submissions with unchanged fields created distinct listings641 and642 for release153, each quantity3 at1111 cents. Creation was not idempotent for those submissions.','verified',['Observed first result153 remained selected during E19 locator miss'],['Both record identities confirmed by UI-caused201 responses and later rendered cart links'],[19,20]],
['R21','A mixed-seller cart containing one unit each of own listing641 and external listing7 checked out as one paid order122 for3396 cents and cleared the cart. Own listing641 became sold while its stored/displayed quantity remained3.','verified',['Exact observed active listings and quantities'],['Exact total affected-record count remains unknown'],[21]],
['R22','After active642 was added to cart and then deactivated, Checkout returned400 A listing in your cart is no longer available. The page showed the error without cart controls; navigation to /cart restored its unchanged row.','verified',['Exact inactive642 cart'],['No automatic retry; removal later succeeded'],[22,23]],
['R23','The frontend Add-to-Cart URLs previously rendered for inactive642 and sold4 caused UI requests returning404 Listing not found and left the cart empty; the resulting cart page did not retain an error message.','verified',['Same-origin frontend navigation to previously observed hrefs; no direct API calls'],['A missing visible error is insufficient to infer accepted write'],[25]],
['R24','Remove deleted the whole quantity2 row for listing12, leaving listing19 and total3051 cents. It did not decrement quantity2 to1. Removing19 then persisted an empty cart.','verified',['Observed two-row cart at8675 cents'],['Other cart row identities can be ambiguous in the DOM'],[23]],
['R25','With shipping Sweden, minimum rating99.1 included the displayed99.1 and99.8 sellers. Media Good yielded no rows, while Good (G) yielded nicole3573. Matching sleeve retained that row; raising minimum to99.2 excluded it.','verified',['Release221; tested filter combinations only'],['Evidence favors exact condition equality, inclusive threshold and intersection within these values'],[24,32]],
['R26','Negative quantity-1 was server-rejected with minimum1; price1.5 was server-rejected as noninteger. Price1 with quantity1 and valid defaults created active listing643 at USD0.01.','verified',['Selected release221; observed other fields'],['Higher limits and other numeric syntax remain unknown'],[26]],
['R27','Media condition Experimental Grade3141 was accepted for listing644 at price2/quantity1 with other default fields. Empty media condition was rejected with minimum length1. Empty sleeve and empty ships-from were separately rejected with minimum length1.','verified',['Observed release221 forms'],['Other custom strings, whitespace-only strings and length maxima remain unknown'],[27,29]],
['R28','Empty comments were accepted with default conditions, US, price3 and quantity1, creating active listing645.','verified',['Exact observed form values'],['No broader comment-length or encoding rule inferred'],[29]],
['R29','Newest sorting put newly created listing644 before643 in the observed release221 marketplace, whereas price-ascending placed643 before644.','verified',['Both listings active and created at distinct observed times'],['Tie-breaking among equal timestamps remains unknown'],[27]],
['R30','A cart with active643 and inactive644 failed checkout with unavailable error. Both rows remained and643 stayed active in seller readback. After removing644, checkout of643 alone returned paid order123 for1 cent, cleared the cart and marked643 sold.','verified',['Exact observed mixed-validity cart and subsequent correction'],['No claim about all-or-nothing behavior in every other checkout failure or hidden order side effects'],[28]],
['R31','The quantity1 cart row for645 survived sign-out and sign-in as the same account. Login next=/cart preserved the row without adding another unit.','verified',['Same supplied account; plain /cart next target'],['Other account/session persistence remains unknown'],[30]],
['R32','Guest Add to Collection for153 redirected to login next=/release/153. Successful login returned to153 without adding membership; a later explicit Add created one membership and persisted Have3.','verified',['Previously uncollected release153; observed authentication sequence'],['Wantlist post-login replay behavior was not directly tested'],[31]],
['R33','Reusable native helpers successfully selected release221 from the Pink Floyd multi-result search, created646 with correct identity, added and removed its cart row, and deactivated it. The deactivation helper safely stopped when inactive640 and646 became visually indistinguishable under its title/price/status key.','verified',['Exported validation scripts E32–E36; supplied account'],['Callers must stop dependent actions when helpers return None; cart/menu auth helpers have narrower validation'],[32,33,34,35,36]],
['R34','Deactivate on sold643 returned ok and persisted inactive; it did not reactivate or reject that sold listing.','verified',['Own listing643 sold after order123'],['Other sold listing behavior remains a hypothesis'],[35,36]],
['R35','The discovered /forum, /blog and /help links rendered404 in the observed session. The /genre/rock page rendered an overview, release cards and style/search links.','verified',['Observed linked paths only'],['This does not establish that community/help functionality is absent elsewhere'],[18,25]],
['F01','The tested Add to Wantlist or Add to Collection button becomes a Remove button after adding release221.','refuted',['Observed release221 after adds'],['Add labels remained; removal elsewhere unknown'],[5,6]],
['F02','Each immediate sidebar increment after a repeat Add represents a new persisted membership.','refuted',['Observed repeat adds for221 and84'],['Navigation and personal rows contradict transient increment'],[6,7,18,32]],
['F03','Repeated identical Create Listing submissions are deduplicated.','refuted',['E19 identical submissions with153 selected'],['Distinct201 identities641 and642 persisted'],[19,20]],
['F04','Buying one unit from own listing641 with stock3 leaves it active with stock2.','refuted',['Exact observed checkout122'],['It became sold and quantity remained3'],[21]],
['F05','Guest Collection intent for153 is replayed automatically after successful sign-in.','refuted',['Observed guest collection/login sequence'],['Membership was absent until another explicit click'],[31]],
['H01','Other releases probably use the same persisted-membership idempotence and optimistic counter behavior.','hypothesis',['Only221 and84 repeats observed'],['Test another previously present release and compare persisted counts and list rows'],[6,18]],
['H02','Other positive integer price/quantity values with nonempty required strings probably create listings.','hypothesis',['Only documented values/forms observed'],['Test other ranges, maxima, numeric syntax and string boundaries independently'],[13,19,26,27,29,33]],
['H03','Mixed invalid checkout may be atomic across every business record.','hypothesis',['Only active643/inactive644 combination observed'],['Order management and every hidden side effect cannot be inferred from retained cart and active status'],[28]],
['U01','Collection/Wantlist removal, editing, listing reactivation, arbitrary listing editing, order management, refunds and shipping workflows remain unknown.','unknown',['No successful controls tested for these operations'],['Missing UI controls do not establish missing backend behavior'],[7,14,36]],
['U02','Precise total affected-record counts for checkout and hidden order-related persistence remain unknown.','unknown',['Paid order, listing status and cart clearing observed'],['Do not invent an order-row or event count'],[10,21,28]]
]
d['experiments'].update({
'17':'Distinguish artist/title search, case sensitivity, substring, no-match and blank query. Use r001 executable model for form action predictions.',
'18':'Probe linked genre/community/help destinations and compare membership behavior on a second release84.',
'19':'Test multi-result selection and deliberate duplicate creation. Selector mismatch was skipped; first selection153 actually received two distinct confirmed records.',
'20':'Preserve E19 and correct selector using rendered #221; confirm explicit selection and no-match clearing. Inspect actual created release153 marketplace.',
'21':'Distinguish stock decrement from sold status on one-unit purchase of stock3 and test mixed-seller order grouping.',
'22':'Test stale cart after deactivation; distinguish checkout validation from stale acceptance; capture zero-listing boundary.',
'23':'Recover retained cart via navigation and test removing all units of one row while preserving a second row.',
'24':'Distinguish inclusive rating threshold, media substring/exact equality and sleeve intersection.',
'25':'Test whether genre/style links perform metadata filtering, and previously rendered frontend add URLs for now inactive/sold listings. No APIs directly accessed.',
'26':'Test negative quantity and fractional cents validation, then correct confirmed rejections and test minimum positive cent value.',
'27':'Distinguish media-grade enumeration from free text and empty-string rejection; compare newest versus price order.',
'28':'Test mixed active/inactive checkout for partial visible effects, then remove invalid row and checkout the valid minimum-price listing.',
'29':'Individually test empty sleeve, empty shipping country and optional comments with otherwise valid inputs.',
'30':'Distinguish account-persisted cart from session-local state and test login next without an add query.',
'31':'Distinguish guest collection intent replay from navigation-only login return; confirm explicit post-login membership.',
'32':'Validate reusable native search/filter/membership helpers. First dependency version statically rejected private-name helper; corrected public-name model preserved separately.',
'33':'Validate corrected reusable create helper using explicit release ID, field readback, one submission and subsequent public identity.',
'34':'Validate reusable cart add/remove and deactivation; verify new646 persisted and was removed from marketplace.',
'35':'Test sold643 deactivation and ambiguous inactive listing identity.643 became inactive; helper then stopped safely before ambiguous646 write.',
'36':'Correction/follow-up to E35 locator ambiguity. Capture only final persisted states in seven navigation actions, ending at300 actual actions.'
})
d['unknowns']=[
'Coverage is bounded to the supplied account and observed catalogue/listings; no private tasks or historical rules were supplied or accessed.',
'Other release/account combinations, stock and numeric maxima, whitespace-only fields, comment limits, international currencies and concurrency remain unknown.',
'Collection/wantlist removal/editing and listing reactivation/editing were not successfully observed; missing controls are not proof of missing backend behavior.',
'Order management, refunds, shipping, seller-to-buyer communications, catalogue contribution elsewhere and most footer destinations remain untested.',
'Checkout affected-record totals remain null because allowed evidence does not enumerate every order-related persisted record.',
'The predictor deliberately returns unknown for untested entities, unsupported parameter combinations and whole-task compositions; broader patterns appear as hypotheses.',
'The final deactivation helper can stop on visually identical listings (640/646); no hidden backend identity is inferred from absent DOM attributes.',
'Native sign_in/sign_out/checkout helper entry points use action primitives exercised during exploration, but those exact wrappers were not all executed. Search/filter/selection/create/membership/cart-add/remove/deactivate wrappers were executed.',
'Runtime action_after.classification was unconfirmed for all300 actions. This raw field is preserved; learner classifications rely on separate DOM/readback/sanitized-response evidence and are not independent evaluator truth.'
]
d['hypotheses']=[{'id':x[0],'hypothesis':x[1],'status':x[2],'distinguishing_experiment':x[4][0]} for x in r if x[2] in ('hypothesis','unknown')]
p.write_text(json.dumps(d,indent=2)+'\n')
