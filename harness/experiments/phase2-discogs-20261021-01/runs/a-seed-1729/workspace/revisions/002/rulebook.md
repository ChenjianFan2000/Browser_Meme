# Bounded browser rulebook — revision 002

Condition A, independent gpt-6.1-sol, scheduling seed1729. Seed concerns experiment scheduling only. This document is a retrospective synthesis, not an independent correctness score. Only the supplied account and observed conditions are covered.

Browser exploration stopped after the runtime denied reading an input value attribute in call010. No subsequent browser action or submission was made. All final script corrections were made offline. Evidence: `evidence/call-010-cd631f88/result.json` (sha256 `3f7cb5665459f2b302ff36a771291ed7b91d3e204837702825118036b560c973`).

## R001 — verified

For the supplied account, submitting the prefilled login succeeded: a UI-caused response returned 200 with ok=true, navigation reached /, and subsequent pages showed a signed-in Account button.

Conditions: Observed /login with its seeded prefilled form; Same supplied account; one Sign in click.

Branches/limits: {"accepted": "Home navigation and later signed-in control", "unknown": "Blank/invalid credentials, other accounts, signed-out session behavior"}.

Evidence: `evidence/call-002-d2ff8107/obs-0007.html` (sha256 `a784eb5c57887b1f32941f833792c3af2db661f7124711885ebbfb732970b7ed`); `evidence/call-003-aed7b82b/network.json` (sha256 `474bd97d2a36708f39129ab4bdc9a0ef997de2a62d3d28e4b0294d0927759019`); `evidence/call-003-aed7b82b/obs-0006.html` (sha256 `e725566f1e846994d7f8a5aaef046fccbba52a35131b937ce699d60b53f2286e`); `evidence/call-005-458acab8/obs-0003.html` (sha256 `3c0b9173bb5060cd476664b8c9a2ea7c88cd6890c5577856ecd817c490b027c9`).

## R002 — verified

In the observed session Account was a link to /login before sign-in and a button after sign-in. Activating the signed-in button exposed Collection, Wantlist and Sign out; Collection navigated to /me/collection.

Conditions: Observed desktop header; Authentication state must be read from current rendered role.

Branches/limits: {"unsigned": "Account link", "signed_in": "Account button and menu"}.

Evidence: `evidence/call-002-d2ff8107/obs-0007.html` (sha256 `a784eb5c57887b1f32941f833792c3af2db661f7124711885ebbfb732970b7ed`); `evidence/call-004-9ff8981c/result.json` (sha256 `5b0d08c6b333af3757ce01f76d44b899a961aaa2389ab56bab41e1ba1c590536`); `evidence/call-006-67f666a9/obs-0006.html` (sha256 `6c61721a2ef3fbf80e2a4b8f0e06d808b2a2346ac491add400bd5ce02baa0bc0`); `evidence/call-006-67f666a9/obs-0009.html` (sha256 `8ddfada6623ce3625219bab4f5ad8a885e857b87afb023b05f26810820a39707`).

## R003 — verified

The visited release /release/221 was Pink Floyd - The Dark Side Of The Moon (1973), with release details, tracklist, Add to Wantlist, Add to Collection and a marketplace link. Its marketplace initially displayed 25 for-sale rows.

Conditions: Release 221 during this run before checkout.

Branches/limits: {"release": "Details plus membership controls", "marketplace": "/sell/release/221 shows seller, shipping country, conditions, price and Add to Cart links"}.

Evidence: `evidence/call-005-458acab8/obs-0006.html` (sha256 `f5fc237f8782cb82d18dfbee0dd4da3336bb80982e929d3383afc5cecae2043d`); `evidence/call-008-a75dfe0d/obs-0006.html` (sha256 `83890fff6c35864f01ea9350079617128adaf56901f4caca7a2096a898482dfe`).

## R004 — verified

When release 221 was absent from this account wantlist, one Add to Wantlist click succeeded and fresh /me/wantlist readback gained one card for 221 (10 to 11 cards).

Conditions: Authenticated supplied account; Release 221 absent from observed wantlist baseline.

Branches/limits: {"absent": "One membership added", "present": "See R005; not a new insertion"}.

Evidence: `evidence/call-006-67f666a9/obs-0012.html` (sha256 `1dc543cd463a9b951408afa714b68a7b820a4d632b495adf8961570d8ccb3eab`); `evidence/call-006-67f666a9/obs-0018.html` (sha256 `3192d6e11a0449e7594f41a1595f4c144360550d8c0b94b6b6cec4361d413585`); `evidence/call-006-67f666a9/obs-0021.html` (sha256 `96acb38c03449fcab19d4f1cba18bcf3fbcf874e68e5a30343c9194d2821f6e9`); `evidence/call-006-67f666a9/network.json` (sha256 `e8b693a1229f9d5a6eb147ac5b7d89b948b03a05a7182aa541ec9484e257bde5`).

## R005 — verified

For release 221 already in this account wantlist, one repeated Add to Wantlist returned ok=true and fresh list readback still contained one 221 card. The local sidebar Want briefly went from 4 to 5; later release navigation showed 4, not 5.

Conditions: Supplied account; One confirmed prior wantlist addition for 221.

Branches/limits: {"immediate": "Button remains Add to Wantlist; sidebar increments transiently", "readback": "One card; stable aggregate Want=4 in later navigation"}.

Evidence: `evidence/call-007-84712f42/obs-0003.html` (sha256 `ff3bec5fe35446964453ed6d8d3fd3cf794fdf5fd2d26a6f4a7dcc81538cb9a3`); `evidence/call-007-84712f42/obs-0006.html` (sha256 `266c1b66e52cc11144658279e810745862c0f653dc61e3c24cd7b26222831265`); `evidence/call-007-84712f42/obs-0009.html` (sha256 `96acb38c03449fcab19d4f1cba18bcf3fbcf874e68e5a30343c9194d2821f6e9`); `evidence/call-007-84712f42/obs-0012.html` (sha256 `ff3bec5fe35446964453ed6d8d3fd3cf794fdf5fd2d26a6f4a7dcc81538cb9a3`); `evidence/call-007-84712f42/network.json` (sha256 `be46804bbbf85dee8b67065556d8124f0d6b03e26d80e363a37dc50c2c94e769`).

## R006 — verified

For the supplied account and release 221, first Add to Collection gained one collection card (22 to 23 total); one repeat left one 221 card. Sidebar Have rose 2 to 3 on insertion and 3 to 4 on repeat, while a later release navigation showed 3.

Conditions: Supplied account; Release 221 initially absent from collection; One addition followed by one repeat.

Branches/limits: {"first": "Target collection membership inserted", "repeat": "Membership remains one; transient count is not stored count"}.

Evidence: `evidence/call-006-67f666a9/obs-0009.html` (sha256 `8ddfada6623ce3625219bab4f5ad8a885e857b87afb023b05f26810820a39707`); `evidence/call-007-84712f42/obs-0015.html` (sha256 `dee5387352f8e3ff17f507c68d59dbc4d8f05cc41f26572844bf3d73022120e8`); `evidence/call-007-84712f42/obs-0018.html` (sha256 `9832b35dec034e5821a50879b4d5854360fc9258337a408fe1e6dedff3ae976d`); `evidence/call-007-84712f42/obs-0024.html` (sha256 `60e5ccc63b28cd749e689527d6753bc6098bae55f77c5838de44092d87aa8fb4`); `evidence/call-007-84712f42/obs-0027.html` (sha256 `9832b35dec034e5821a50879b4d5854360fc9258337a408fe1e6dedff3ae976d`); `evidence/call-008-a75dfe0d/obs-0003.html` (sha256 `75f6f7cfe6964d4bc8ac9dd54638557cd535f3c5c51fa89acacfad79a89e7573`); `evidence/call-007-84712f42/network.json` (sha256 `be46804bbbf85dee8b67065556d8124f0d6b03e26d80e363a37dc50c2c94e769`).

## R007 — verified

In the tested short sequence, adding release 221 to Collection after Wantlist did not remove it from Wantlist: both account pages contained one 221 card.

Conditions: Sequence in calls 006-007; Same supplied account and release 221.

Branches/limits: {"combination": "Both memberships present", "unknown": "Other combinations, removals and other releases"}.

Evidence: `evidence/call-007-84712f42/obs-0027.html` (sha256 `9832b35dec034e5821a50879b4d5854360fc9258337a408fe1e6dedff3ae976d`); `evidence/call-007-84712f42/obs-0030.html` (sha256 `96acb38c03449fcab19d4f1cba18bcf3fbcf874e68e5a30343c9194d2821f6e9`).

## R008 — verified

From an empty account cart, clicking the visible Add to Cart link for the account own active listing 4 succeeded, producing one cart item with quantity 1, unit price 2145 cents and total USD 21.45; fresh navigation retained it.

Conditions: Supplied account signed in; Listing 4 for release 221 active at 2145 cents; Empty cart.

Branches/limits: {"accepted": "Own-listing insertion permitted in this case", "unknown": "Other own listings or later sold status"}.

Evidence: `evidence/call-008-a75dfe0d/obs-0009.html` (sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`); `evidence/call-009-79c1d31d/obs-0003.html` (sha256 `fbe28229878516311f771980567b340312ed89d2598b87a16d34c156c866c570`); `evidence/call-009-79c1d31d/obs-0006.html` (sha256 `b1296e4137ef6625ffdc71a472bf433ef43f4e527695b246fc8323c8b8485594`); `evidence/call-009-79c1d31d/obs-0009.html` (sha256 `617cb46230fe0ae67237388d316e4b69e0bc965e877be810ad683f6b27480b44`); `evidence/call-009-79c1d31d/network.json` (sha256 `a8424a48124395adabdc8dd3a4790c67102695dd9bebf9b8c2eb8b6f4a6110a4`).

## R009 — verified

With listing 4 quantity 1 in the cart, adding active listing 7 at 2285 cents created a second cart item and total 4430 cents. Repeating listing 7 once updated its same cart record from quantity 1 to 2, total 6715 cents. The visible line still showed the unit price USD 22.85; no quantity input was observed.

Conditions: Supplied signed-in account; Listings 4 and 7 active in observed sequence; Listing 7 transitions only 0 to 1 and 1 to 2.

Branches/limits: {"first": "Second cart record inserted", "repeat": "Existing listing-7 cart record quantity incremented", "unknown": "Quantity ceiling, other listings and later sold listings"}.

Evidence: `evidence/call-009-79c1d31d/obs-0015.html` (sha256 `c183e4c6289e91b07662d0338f5e2ae01a96674288519f47d0cd93dd035106a1`); `evidence/call-009-79c1d31d/obs-0018.html` (sha256 `c3a76ad5f906d62a27ea748ffc02ea3a975eefabf926c083014ad22b748e0b37`); `evidence/call-009-79c1d31d/obs-0024.html` (sha256 `ea9f2d4adca89ad3cbdb1692eabc1cfb058cbcb1a66cfbc8b23d415a1050f129`); `evidence/call-009-79c1d31d/obs-0027.html` (sha256 `e19cc08a64e7e618444ec21bfdc7c6c136a2cd0f4c97d405eacff445903090bd`); `evidence/call-009-79c1d31d/network.json` (sha256 `a8424a48124395adabdc8dd3a4790c67102695dd9bebf9b8c2eb8b6f4a6110a4`).

## R010 — verified

One Checkout click on the observed cart (listing 4 quantity 1, listing 7 quantity 2, USD 67.15) returned a paid order for those lines and cleared the cart. Fresh /cart navigation remained empty at USD 0.00. No separate confirmation step was observed before that write.

Conditions: Supplied signed-in account; Exact observed two-line cart and prices; One checkout click.

Branches/limits: {"accepted": "Paid order response plus empty persistent cart", "unknown": "Other carts, empty/repeat checkout, payment systems outside this local fixture, stock/authorization rejection and total affected record count"}.

Evidence: `evidence/call-010-cd631f88/obs-0003.html` (sha256 `e19cc08a64e7e618444ec21bfdc7c6c136a2cd0f4c97d405eacff445903090bd`); `evidence/call-010-cd631f88/network.json` (sha256 `b53ee273c87eed130ad1680172477245bb5cbb106da1a089db4a7a23153596f4`); `evidence/call-010-cd631f88/obs-0006.html` (sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`); `evidence/call-010-cd631f88/obs-0009.html` (sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`).

## R011 — verified

After that checkout, /sell readback showed the account listing 4 for release 221 as sold (quantity display remained 1). Its response also reported sold status. The full inventory accounting and marketplace result after sale were not observed.

Conditions: Checkout sequence in R010; Observed own listing 4.

Branches/limits: {"observed": "Status active before checkout and sold afterward", "unknown": "Exact inventory decrement and listing 7 seller inventory"}.

Evidence: `evidence/call-008-a75dfe0d/obs-0012.html` (sha256 `ffafd3c92812ddad9606d5f386148ff475bebcc21f1fa4eaaa06358927cd725e`); `evidence/call-008-a75dfe0d/network.json` (sha256 `ef4bbba2f39b2d1416ede06d35004bcc24db553a666d4fc8639a5000082675bb`); `evidence/call-010-cd631f88/obs-0012.html` (sha256 `ceac86270930b84aadafc2abc873e4a5a80802bdb50e4cf884f7420ac02bf763`); `evidence/call-010-cd631f88/network.json` (sha256 `b53ee273c87eed130ad1680172477245bb5cbb106da1a089db4a7a23153596f4`).

## R012 — verified

The visited /sell page rendered Find a release/Search, Media Condition, Sleeve Condition, Ships From, Quantity, Price (cents), Comments, Create Listing and My Listings with Deactivate buttons. No create, search or deactivation operation was executed.

Conditions: Supplied signed-in account; DOM inspection of /sell.

Branches/limits: {"observed": "Form and own listings visible", "unknown": "Validation, creation, activation/deactivation and permissions"}.

Evidence: `evidence/call-008-a75dfe0d/obs-0012.html` (sha256 `ffafd3c92812ddad9606d5f386148ff475bebcc21f1fa4eaaa06358927cd725e`); `evidence/call-010-cd631f88/obs-0012.html` (sha256 `ceac86270930b84aadafc2abc873e4a5a80802bdb50e4cf884f7420ac02bf763`).

## R013 — verified

The runtime rejected a native get_attribute("value") inspection of a /sell input with BoundaryError and directed use of input_value for nonsecret controls. Browser exploration ended immediately after that call; this is a runtime access boundary, not a website business rejection.

Conditions: Native getter attempt after four completed UI actions in call 010.

Branches/limits: {"runtime": "Boundary denied; no additional browser submissions", "site_business_rule": "No conclusion"}.

Evidence: `evidence/call-010-cd631f88/result.json` (sha256 `3f7cb5665459f2b302ff36a771291ed7b91d3e204837702825118036b560c973`); `evidence/call-010-cd631f88/actions.jsonl` (sha256 `e95cea0962e6baa3b98214242a4bb76a56aac8e3dfca4e1a3f5f6b88169f7fea`).

## H001 — hypothesis

The membership set semantics observed for 221 may extend to other releases or users.

Conditions: Other releases/accounts untested.

Branches/limits: {"distinguishing_experiment": "On an independently allowed future run, baseline another observed release, add once, repeat once, and reopen both membership page and release."}.

Evidence: `evidence/call-007-84712f42/network.json` (sha256 `be46804bbbf85dee8b67065556d8124f0d6b03e26d80e363a37dc50c2c94e769`).

## H002 — refuted

Repeated membership Add permanently increments the aggregate Have/Want count for release 221.

Conditions: Tested repeat in the authenticated supplied account.

Branches/limits: {"counterexample": "Repeated Want displayed 5 then reloaded 4; repeated Have displayed 4 then reloaded 3."}.

Evidence: `evidence/call-007-84712f42/obs-0006.html` (sha256 `266c1b66e52cc11144658279e810745862c0f653dc61e3c24cd7b26222831265`); `evidence/call-007-84712f42/obs-0012.html` (sha256 `ff3bec5fe35446964453ed6d8d3fd3cf794fdf5fd2d26a6f4a7dcc81538cb9a3`); `evidence/call-007-84712f42/obs-0024.html` (sha256 `60e5ccc63b28cd749e689527d6753bc6098bae55f77c5838de44092d87aa8fb4`); `evidence/call-008-a75dfe0d/obs-0003.html` (sha256 `75f6f7cfe6964d4bc8ac9dd54638557cd535f3c5c51fa89acacfad79a89e7573`).

## H003 — refuted

The account cannot add its own listing 4 to its cart in the observed active/empty-cart condition.

Conditions: Own active listing 4 at 2145 cents; Empty cart.

Branches/limits: {"counterexample": "Click succeeded and own listing persisted in cart."}.

Evidence: `evidence/call-009-79c1d31d/obs-0006.html` (sha256 `b1296e4137ef6625ffdc71a472bf433ef43f4e527695b246fc8323c8b8485594`); `evidence/call-009-79c1d31d/obs-0009.html` (sha256 `617cb46230fe0ae67237388d316e4b69e0bc965e877be810ad683f6b27480b44`); `evidence/call-009-79c1d31d/network.json` (sha256 `a8424a48124395adabdc8dd3a4790c67102695dd9bebf9b8c2eb8b6f4a6110a4`).

## U001 — unknown

Search matching, search pagination, marketplace filtering/sorting semantics, create listing validation, Deactivate effects, Remove effects and business rejection conditions remain unknown.

Conditions: Relevant affordances seen; operations not executed.

Branches/limits: {"next": "Use small single-variable UI experiments only in a separately authorized future run; do not resume this stopped run."}.

Evidence: `evidence/call-001-49942053/obs-0004.html` (sha256 `d66e644d72c9791d9b05d2ba3f43a7bd6802b376b869ca9fa92d78156151e044`); `evidence/call-008-a75dfe0d/obs-0006.html` (sha256 `83890fff6c35864f01ea9350079617128adaf56901f4caca7a2096a898482dfe`); `evidence/call-008-a75dfe0d/obs-0012.html` (sha256 `ffafd3c92812ddad9606d5f386148ff475bebcc21f1fa4eaaa06358927cd725e`); `evidence/call-009-79c1d31d/obs-0027.html` (sha256 `e19cc08a64e7e618444ec21bfdc7c6c136a2cd0f4c97d405eacff445903090bd`).

## Evidence interpretation

The runtime action log uses a generic unconfirmed classification even for many successful navigations. This package preserves that field in exploration.jsonl and separately classifies actual observations. Persistent business claims require the specific UI-caused response and subsequent readback cited above. A locator timeout is not a website rejection. The input-attribute boundary is a runtime restriction, not a business rule.

Initial experimental predictions are preserved even when wrong. In particular, the empty-login label describes an invalid experimental setup: no fields were cleared before submitting the seeded form. No rejected-credential claim is supported. Evidence: `evidence/call-003-aed7b82b/actions.jsonl` (sha256 `857b4936f3f842dc4b711752f90eba38573cf30179156613cd5c8a6dbd64143c`); `evidence/call-003-aed7b82b/network.json` (sha256 `474bd97d2a36708f39129ab4bdc9a0ef997de2a62d3d28e4b0294d0927759019`).

## Using the package

Load behavior_model.py and call predict(observation,intent) with explicit current observed facts. Follow model_interface.md in the final revision for the schema. Unknown means evidence is insufficient; it does not mean an action will fail. Original executed scripts remain in experiments/. Revised scripts.py offers native Playwright entry points; it is not an automatic action dispatcher or a claim of private-task success.
