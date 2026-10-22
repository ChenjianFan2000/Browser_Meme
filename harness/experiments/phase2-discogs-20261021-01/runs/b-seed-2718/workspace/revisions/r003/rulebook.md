# Condition B browser learning, revision 3

This is a bounded account/session report, not a complete website specification. Checkpoints were assembled after the terminal stop; revision history preserves evidence scope rather than claiming earlier publication. Only rendered DOM and UI-caused public responses were used. No source files, client-script bodies, direct API calls, JavaScript evaluation, private tasks or historical model were used. Evidence: `evidence/call-011-7a83aa24/result.json` (sha256 `9ca2d463dd5181ce7217163ac881f2531a9733d597dee547c3cf694d0b44359f`).

Each rule below is limited by its preconditions. Verified describes observed cases; hypothesis and unknown retain uncertainty. Runtime action_after classifications are raw instrumentation labels, not independent semantic scores. Per-action expectations are in exploration.jsonl; no whole-task score or prediction was produced. Evidence: `evidence/call-001-9faee651/actions.jsonl` (sha256 `a542398ff9d28d7ee7924ce4c6f745620961bf908a858e70ae5c988bbf2a9830`); `evidence/call-002-01f0dfe3/actions.jsonl` (sha256 `8328a276edc835cf8e332105433cda31ab140fe1b66850e9f61758708a3459b4`); `evidence/call-003-8c83c3e0/actions.jsonl` (sha256 `096dfd72f3a4a4d5e719f49e3b72c1e12009cef5bd655a5cc06afeff90eccc4c`); `evidence/call-004-e72d7816/actions.jsonl` (sha256 `7ec721327549da00cfafabd40a685f698f95f7956af524e2fdf8a3761aec3273`); `evidence/call-005-437a3c73/actions.jsonl` (sha256 `566f3453f608a54612a36fb4950d9efa259c4f706bfec6da6b13c570f8299151`); `evidence/call-006-6c0c68cf/actions.jsonl` (sha256 `abc6115220a312c92113e480d088ec039b923f92db94f5b93e3ecaf1e30423b9`); `evidence/call-007-5cbf52f9/actions.jsonl` (sha256 `9659368f2bec3223c0d42e17c5c1c42d553684f3f5d24e32e4bce6db4e559563`); `evidence/call-008-4ff7e232/actions.jsonl` (sha256 `7ff991498ece8099c857a02e1d47ffe2e778c668fa9dd7565e0caccea568064b`); `evidence/call-009-a4672f61/actions.jsonl` (sha256 `1e56d983edc430b237b85a163b3442e8141405ede59b67903f1c763f44d7e30f`); `evidence/call-010-c04f8715/actions.jsonl` (sha256 `aa2a0f60bf776763e59f44422c7abd82943a3fdf0e61cd92ba2882dba0ea3d7d`); `evidence/call-011-7a83aa24/actions.jsonl` (sha256 `be4fed2e9832f2c684ad0ead2b3153d522685f96d9379bb8b6c9372bef5905a4`).

## UI-COOKIE — verified

In the initial home-page state, Accept All Cookies dismissed the visible privacy banner. Its longer-term persistence was not tested.

Preconditions: Initial home page showed privacy banner.

Evidence: `evidence/call-002-01f0dfe3/obs-0004.html` (sha256 `d66e644d72c9791d9b05d2ba3f43a7bd6802b376b869ca9fa92d78156151e044`); `evidence/call-002-01f0dfe3/obs-0006.html` (sha256 `ec389d3baa871fc14edca664f9a413634dd19965cba2fc75c17a945d10f1b510`).

## AUTH-PREFILL — verified

The discovered login form was prefilled; submitting it without clearing fields navigated home and returned a successful authentication response. This was not an empty-credential test.

Preconditions: Discovered /login form in this fixture.

Evidence: `evidence/call-002-01f0dfe3/obs-0010.html` (sha256 `33a0a82a291a03b77ecca1cd05f6b733465ac081b44157a54b8c68e53dd08a11`); `evidence/call-003-8c83c3e0/obs-0006.html` (sha256 `5c3fa437fc2e6b0319fd069a0e44dc2bc46e3fdb2ca98bd9304edbf290ca61f5`); `evidence/call-003-8c83c3e0/network.json` (sha256 `bff459992a6808fa85365ac1b619189e7db368175f2bd71d0ed2dce377491abb`).

## AUTH-EMPTY — verified

With both login inputs explicitly cleared, submitting Sign in stayed on /login, displayed Invalid credentials, and produced an HTTP 400 authentication response.

Preconditions: Fixture browser session; Both login inputs explicitly cleared.

Evidence: `evidence/call-004-e72d7816/obs-0012.html` (sha256 `386a6af5584949ebd1e73a56766c463174368bf18018145a1c5f06a63f987814`); `evidence/call-004-e72d7816/network.json` (sha256 `6e8a99a80a7f85146ab553143ec1077a2d6e56ca9959fdd37bbeecb52eb18d73`).

## AUTH-LOCATOR-FAILURE — verified

After the prefilled login navigated home, a Username or Email locator timed out. This is a page/locator assumption failure, not evidence of credential rejection.

Preconditions: Experiment 03 continued after home navigation.

Evidence: `evidence/call-003-8c83c3e0/result.json` (sha256 `2fa77c537dc3df228d65b48f563974bc7674f5c7dbc2ad0e260e7fd61add7233`); `evidence/call-003-8c83c3e0/obs-0009.html` (sha256 `09e2afc664c5f4ffca9acd918a28c0f7b53f7c7189b54a11d05a04a8259a045c`).

## AUTH-INVALID — verified

The fixture username with the tested deliberately invalid password stayed on /login and displayed Invalid credentials with HTTP 400. This does not establish validation for all malformed accounts.

Preconditions: Fixture username; One deliberately invalid password.

Evidence: `evidence/call-004-e72d7816/obs-0021.html` (sha256 `53819b8210379bee1dfa737de4067a5d15379fb6ec8ec58075fc834512467260`); `evidence/call-004-e72d7816/network.json` (sha256 `6e8a99a80a7f85146ab553143ec1077a2d6e56ca9959fdd37bbeecb52eb18d73`).

## AUTH-VALID — verified

Submitting the fixture username/password navigated home with an ok authentication response. A fresh script retained the authenticated header. Authentication is excluded from business-record effects.

Preconditions: Public fixture credentials entered into discovered login controls.

Evidence: `evidence/call-004-e72d7816/obs-0027.html` (sha256 `b22cae2daccec49985e9e8b64f0c36027f48625945f8cdb6ff545a6bafc62682`); `evidence/call-004-e72d7816/network.json` (sha256 `6e8a99a80a7f85146ab553143ec1077a2d6e56ca9959fdd37bbeecb52eb18d73`); `evidence/call-005-437a3c73/obs-0003.html` (sha256 `cf6e53eac6b6380ed1aa15d5edcdbda83de0dcf3491ccaeadb595c627581febd`).

## AUTH-HEADER — verified

In the observed authenticated header, Account is a button rather than the anonymous Account link; its DOM contains Collection, Wantlist and Sign out controls. The menus themselves were not activated in the corrected exploration.

Preconditions: Authenticated header after fixture login.

Evidence: `evidence/call-002-01f0dfe3/obs-0010.html` (sha256 `33a0a82a291a03b77ecca1cd05f6b733465ac081b44157a54b8c68e53dd08a11`); `evidence/call-005-437a3c73/obs-0003.html` (sha256 `cf6e53eac6b6380ed1aa15d5edcdbda83de0dcf3491ccaeadb595c627581febd`); `evidence/call-004-e72d7816/result.json` (sha256 `19a408fb8250d8146fbd492a7d5e109cf925dde5b44f2c30db87a7b24ed7ac5e`).

## RELEASE-221 — verified

The observed featured /release/221 page identifies Pink Floyd, The Dark Side Of The Moon (1973), with release metadata and ten track rows, Add to Wantlist, Add to Collection, and a link to /sell/release/221. Initial Have/Want/For Sale figures were 2/3/25.

Preconditions: Featured release 221 in initial fixture state.

Evidence: `evidence/call-005-437a3c73/obs-0006.html` (sha256 `ceb8a7ee1a0fe06da112a30b7a5be7ffbbdb2cf7913e4142c7b382bafe31fbc0`).

## MEMBERSHIP-ADD — verified

For authenticated release 221 initially absent from both account lists, two Wantlist adds and two Collection adds each returned ok. Later list readbacks showed one new release identity in each list, not two cards. These membership operations were independently accessible on the same release.

Preconditions: Authenticated fixture account; Release 221 absent from baseline lists; Two consecutive adds per membership kind.

Evidence: `evidence/call-006-6c0c68cf/obs-0003.html` (sha256 `cde30971b7a972024ca2714a8af61dd019f35e8928789e45c499abf3248bddf3`); `evidence/call-006-6c0c68cf/obs-0006.html` (sha256 `9b648d5338065bb7f0d945fe31a09256c233cb1b0bc20ee37a2ec7e2f9857722`); `evidence/call-006-6c0c68cf/obs-0018.html` (sha256 `88a570b3a66e0396829adac8b6ff6209c2464ecacab5db3ad107a9e3ab92ed44`); `evidence/call-006-6c0c68cf/obs-0031.html` (sha256 `c919125611f9b9675a9716f31b9b93920940b0e416f9eea7693911d84dc04b2a`); `evidence/call-006-6c0c68cf/network.json` (sha256 `8cc934e5b791e4dfa4f7d629f0e6cb37ca4844f2c6d6a8f0d8ba6454b1e0bee3`).

## MEMBERSHIP-COUNTERS — verified

For release 221, each observed add click incremented the local sidebar count, including repeat adds, while the central summary stayed stale. Navigation reconciled Want from local 5 to 4, and Have from local 4 to 3. Local count changes alone do not establish new persistent memberships.

Preconditions: Release 221; Two repeated adds of each kind in the same rendered page.

Evidence: `evidence/call-006-6c0c68cf/obs-0012.html` (sha256 `b86d77693ef2d7ed7c6e7b0d5a5234e4e98f84624fc5573114555137bda4e023`); `evidence/call-006-6c0c68cf/obs-0015.html` (sha256 `300208976de8ab5f569223e4b95a4698c3da58afb395b748b9ca6e1a52c38888`); `evidence/call-006-6c0c68cf/obs-0021.html` (sha256 `869bc39824f8a0866b70eaba966e553a17a638dcc95a29a7d99a4f2da26bde6a`); `evidence/call-006-6c0c68cf/obs-0024.html` (sha256 `a9a4d94e65808e4eb2fe05f07d598dbe3f4aa5058017a6fa5e171cbcf05d0282`); `evidence/call-006-6c0c68cf/obs-0027.html` (sha256 `e067d1eb1be5b28a28ebab3394531bebfd83f233d9fff454526740f1620beb73`); `evidence/call-007-5cbf52f9/obs-0006.html` (sha256 `a625ebbe5dab6361ea743cd49dc0a3749ce76263d1cb919fb49c6bd01cf36e88`).

## MEMBERSHIP-REPEAT-EFFECT — hypothesis

The repeated membership adds appear to have set-like business behavior for this account/release, despite optimistic counter inflation. Hidden metadata effects and behavior for other releases remain untested.

Preconditions: Same membership kind repeated for account/release 221.

Evidence: `evidence/call-006-6c0c68cf/network.json` (sha256 `8cc934e5b791e4dfa4f7d629f0e6cb37ca4844f2c6d6a8f0d8ba6454b1e0bee3`); `evidence/call-007-5cbf52f9/obs-0006.html` (sha256 `a625ebbe5dab6361ea743cd49dc0a3749ce76263d1cb919fb49c6bd01cf36e88`).

## MARKET-221 — verified

The initial release-221 marketplace displayed 25 listing rows, with seller, shipping origin, media/sleeve condition, price, and Add to Cart links. The observed default order was increasing price. Filter controls existed for media/sleeve condition, ships-from, minimum rating and sort, but were not applied.

Preconditions: Release-221 marketplace before checkout.

Evidence: `evidence/call-007-5cbf52f9/obs-0010.html` (sha256 `43bbbbfe69b4fc4ab15fddcef9e1c0c9046dc9043a81765d3141bcf719b4c356`).

## CART-EMPTY — verified

In the observed authenticated empty cart, total was USD 0.00 and Checkout was disabled. No forced empty checkout was attempted.

Preconditions: Authenticated empty cart before adds and after checkout.

Evidence: `evidence/call-008-4ff7e232/result.json` (sha256 `3bd2de827ba0fb9f0dbb6bfca12bd5fb74a7cfaf0766d13f29f9506c559b84dd`); `evidence/call-008-4ff7e232/obs-0003.html` (sha256 `b361021e5c92bae7becbc119414ccf65c1d65eede4272f696fe9f30a119e32a0`); `evidence/call-010-c04f8715/obs-0003.html` (sha256 `b361021e5c92bae7becbc119414ccf65c1d65eede4272f696fe9f30a119e32a0`).

## CART-SELF — verified

Clicking listing 4 Add to Cart while authenticated as its seller was accepted in this observed case, and cart readback showed one item at USD 21.45. A universal self-purchase prohibition is contradicted by this case.

Preconditions: Fixture account is seller of active listing 4; Release 221 marketplace before checkout.

Evidence: `evidence/call-008-4ff7e232/obs-0009.html` (sha256 `bbd298c3e7a900057d2fb650c25edd7c7409284c4e2c8df1c258bbf50a27b3fa`); `evidence/call-008-4ff7e232/network.json` (sha256 `ffa77d8430fd8db4c76e9a47d4a3114a8f82a32136aab183b30e94c117566792`).

## CART-NO-SELF-PURCHASE — refuted

The hypothesis that this site always rejects buying one’s own listing is refuted by this account/listing case, including a later paid checkout response. No broader permission model is established.

Preconditions: Tested fixture account and listing 4.

Evidence: `evidence/call-008-4ff7e232/network.json` (sha256 `ffa77d8430fd8db4c76e9a47d4a3114a8f82a32136aab183b30e94c117566792`); `evidence/call-009-a4672f61/network.json` (sha256 `0310d60cb4183196c70a05e6a794a33b9874f44fc219f243dd6803072fcf46c7`).

## CART-REPEAT — verified

Adding listing 4 twice produced one cart item with quantity 2 in the exported UI-caused response, total 4290 cents, and one visible row displaying unit price USD 21.45. Cart revisit retained quantity/total; no visible quantity editor was discovered.

Preconditions: Authenticated account; Listing 4 added once then added once more; No intervening remove or checkout.

Evidence: `evidence/call-008-4ff7e232/obs-0022.html` (sha256 `55a62fe34c675362aecc7c60cedba7d85b5742fc27475de281426e3a4c480a3f`); `evidence/call-008-4ff7e232/network.json` (sha256 `ffa77d8430fd8db4c76e9a47d4a3114a8f82a32136aab183b30e94c117566792`).

## CART-COMBINE-REMOVE — verified

After adding listing 7 to the quantity-2 listing-4 cart, the total was 6575 cents and the new listing-7 row appeared first. Clicking the first Remove deleted cart item 2 (listing 7), leaving listing 4 at quantity 2 and total 4290. This does not test removing or decrementing a quantity-2 item.

Preconditions: Existing cart item 1 for listing 4, quantity 2; Listing 7 added then first visible Remove clicked.

Evidence: `evidence/call-009-a4672f61/obs-0006.html` (sha256 `d72e59132d6861376abc76b899617129fa7d90dd515418dc68a86fe98ef96233`); `evidence/call-009-a4672f61/obs-0009.html` (sha256 `55a62fe34c675362aecc7c60cedba7d85b5742fc27475de281426e3a4c480a3f`); `evidence/call-009-a4672f61/network.json` (sha256 `0310d60cb4183196c70a05e6a794a33b9874f44fc219f243dd6803072fcf46c7`).

## CHECKOUT-OBSERVED — verified

Clicking enabled Checkout with listing 4 quantity 2 immediately returned order 121, status paid, total 4290 cents, and item quantity 2; the cart became empty and stayed empty on revisit. The next seller view showed listing 4 as sold, still displaying Qty 1. No separate confirmation form was observed in this flow.

Preconditions: Fixture account cart containing only listing 4, quantity 2; One Checkout click.

Evidence: `evidence/call-009-a4672f61/obs-0015.html` (sha256 `b361021e5c92bae7becbc119414ccf65c1d65eede4272f696fe9f30a119e32a0`); `evidence/call-009-a4672f61/network.json` (sha256 `0310d60cb4183196c70a05e6a794a33b9874f44fc219f243dd6803072fcf46c7`); `evidence/call-010-c04f8715/obs-0003.html` (sha256 `b361021e5c92bae7becbc119414ccf65c1d65eede4272f696fe9f30a119e32a0`); `evidence/call-010-c04f8715/obs-0006.html` (sha256 `4f5e92c4450d32d7ed30f791359aa436da3c955944e41293d501d14ed171fbce`); `evidence/call-010-c04f8715/network.json` (sha256 `fa3cecce3802d5e0401b59b1e1c6d412f28f960bc628c0393c9fe5e67effba65`).

## CHECKOUT-STOCK — unknown

This observed checkout accepted cart quantity 2, while the subsequent seller view showed listing 4 with Qty 1 and sold status. Exact inventory validation, decrement behavior, checkout atomicity, repeat checkout and unavailable-item rejection remain unknown.

Preconditions: Only the single observed order for listing 4.

Evidence: `evidence/call-009-a4672f61/network.json` (sha256 `0310d60cb4183196c70a05e6a794a33b9874f44fc219f243dd6803072fcf46c7`); `evidence/call-010-c04f8715/network.json` (sha256 `fa3cecce3802d5e0401b59b1e1c6d412f28f960bc628c0393c9fe5e67effba65`).

## SELL-FORM — verified

The authenticated /sell page showed Create a listing and 21 existing seller listings. Before a release search/selection, Create Listing was disabled. It exposed media condition, sleeve condition, ships from, quantity, price in cents, and comments inputs, plus Deactivate controls on seller rows. No listing was created or deactivated.

Preconditions: Authenticated /sell, initial form state.

Evidence: `evidence/call-010-c04f8715/obs-0006.html` (sha256 `4f5e92c4450d32d7ed30f791359aa436da3c955944e41293d501d14ed171fbce`); `evidence/call-010-c04f8715/network.json` (sha256 `fa3cecce3802d5e0401b59b1e1c6d412f28f960bc628c0393c9fe5e67effba65`); `evidence/call-011-7a83aa24/result.json` (sha256 `9ca2d463dd5181ce7217163ac881f2531a9733d597dee547c3cf694d0b44359f`).

## SELL-SEARCH — verified

On /sell, submitting the seller release search query Dark Side returned one result, release 221, and showed Selected: Pink Floyd - The Dark Side Of The Moon without an explicit result click. The resulting DOM had Create Listing enabled. Behavior for zero/multiple results is unknown.

Preconditions: Authenticated seller page; Query Dark Side; One Search click in seller section.

Evidence: `evidence/call-011-7a83aa24/obs-0009.html` (sha256 `5a6d96628d8b35c6a9bcd95ad0664bbd35acfe14195ffc69a167bb07ab3cf1f9`); `evidence/call-011-7a83aa24/network.json` (sha256 `9ba324d4ff2f76b9f064d3f308e4add7b62729584e1e3f2740deb2f5e70ef58a`).

## ADD-RELEASE-PAGE — verified

Navigating to the discovered Add Release footer link /add-release rendered a 404 page in this session. This establishes only the observed page response, not the absence of release-creation backend behavior elsewhere.

Preconditions: Observed footer href /add-release; Authenticated session.

Evidence: `evidence/call-010-c04f8715/obs-0010.html` (sha256 `77a61128d23387c31e74cfc24f6b7aa8de6a8e8cb34df86a543dda16b392c8fa`).

## UNKNOWN-COVERAGE — unknown

Main catalog search, marketplace filtering/sorting, listing creation/deactivation, membership removal, stock rejection, anonymous business operations, multi-currency behavior, orders UI, and community pages were not exercised. Missing controls do not establish missing backend behavior.

Preconditions: Learning stopped at a runtime boundary before further experiments.

Evidence: `evidence/call-011-7a83aa24/result.json` (sha256 `9ca2d463dd5181ce7217163ac881f2531a9733d597dee547c3cf694d0b44359f`).

## Execution and limitations

Use scripts.py under current-task supervision. Its helpers are native UI execution, do not derive behavior predictions, and never automatically retry writes. A task must authorize checkout, which committed immediately in the observed case. Confirm the current DOM before action; select cart items by identity rather than position. On any unconfirmed business write, stop and preserve evidence. New reusable helpers were syntax checked offline only. Original failed script versions remain under experiments/. Evidence: `evidence/call-003-8c83c3e0/result.json` (sha256 `2fa77c537dc3df228d65b48f563974bc7674f5c7dbc2ad0e260e7fd61add7233`); `evidence/call-004-e72d7816/result.json` (sha256 `19a408fb8250d8146fbd492a7d5e109cf925dde5b44f2c30db87a7b24ed7ac5e`); `evidence/call-009-a4672f61/network.json` (sha256 `0310d60cb4183196c70a05e6a794a33b9874f44fc219f243dd6803072fcf46c7`); `evidence/call-011-7a83aa24/result.json` (sha256 `9ca2d463dd5181ce7217163ac881f2531a9733d597dee547c3cf694d0b44359f`).

The run stopped at 50 runtime-counted UI actions and 11 submissions when get_attribute(value) was denied. The appropriate accessor is input_value() for nonsecret controls; no correction was executed after denial. Seller creation, stock boundaries, catalog search, filters and remaining areas in coverage.json are unknown. This is a contract stop with budget remaining. Evidence: `evidence/call-011-7a83aa24/result.json` (sha256 `9ca2d463dd5181ce7217163ac881f2531a9733d597dee547c3cf694d0b44359f`).
