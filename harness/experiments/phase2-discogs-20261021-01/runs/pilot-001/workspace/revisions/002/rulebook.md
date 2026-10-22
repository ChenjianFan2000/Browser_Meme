Browser behavior rulebook — revision 002

This is a limited exploratory checkpoint for condition A and scheduling seed 1729. Checkpoint artifacts were synthesized offline after learning. Original per-action predictions and observations are preserved. No whole-task scoring or private task access occurred.

**R01 — verified**: At the initial home route /, the rendered header exposes catalog search, Explore/Marketplace/Community menus, Cart, and an Account link to /login.

Preconditions: Initial unauthenticated home observation, supplied origin.

- Account link destination is /login; authentication behavior not yet tested at this checkpoint.

Browser evidence:

- `evidence/call-001-709a330b/obs-0003.html` — sha256 `18166c0aaf4b299a93bf9bd4ae057a95e3ba29654cb11265c999afa65dbff3c5`

**R02 — verified**: The observed login form displays Username or Email and Password text, but native get_by_label("Username or Email") did not identify a unique visible input. This is a locator failure, not a credential rejection.

Preconditions: /login DOM in calls 2 and 3.

- A password-type input and a sign-in form input are rendered; explicit structural targeting needs verification.

Browser evidence:

- `evidence/call-002-a1ce73a3/obs-0006.html` — sha256 `9b386f686f733cad013250d9d3603af3391bbca465a6d474c0c98dd29d1920dd`
- `evidence/call-003-3e99425e/obs-0004.html` — sha256 `a0d6bd7bca75953455b9d2ab621204415eeddc25ea0a6cdf15805bd114479b7e`
- `evidence/call-003-3e99425e/result.json` — sha256 `70b6eb8c10b6e9331e11b0e843ce1ab1cc9fb39dd684d8f1c886c5d82758b412`

**U01 — unknown**: At checkpoint 001, business effects were not established. The later bounded rules resolve some cases; all other business behavior remains unknown.

Preconditions: Only observations 1–3 are included.

- Use normal UI experiments and persistent readback before making claims.

Browser evidence:

- `evidence/call-001-709a330b/obs-0003.html` — sha256 `18166c0aaf4b299a93bf9bd4ae057a95e3ba29654cb11265c999afa65dbff3c5`
- `evidence/call-002-a1ce73a3/obs-0006.html` — sha256 `9b386f686f733cad013250d9d3603af3391bbca465a6d474c0c98dd29d1920dd`

**R03 — verified**: For the supplied fixture username and the pilot invalid password, Sign in remained at /login and rendered Invalid credentials. Replacing the password with the supplied fixture password and submitting returned to /.

Preconditions: Observed login form; Only the two credential cases tested; secrets are not stored in this package.

- Invalid case: rendered rejection; valid case: home navigation and later authenticated header.
- Authentication changes are excluded from target business record counts.

Browser evidence:

- `evidence/call-004-e84ef858/obs-0012.html` — sha256 `481271cd9c8201dc53c5af47f52f658bb561b8482df7cad801e0b6f66a234c8e`
- `evidence/call-004-e84ef858/obs-0018.html` — sha256 `96e5ed5daf8d055550f017124aa5ff3cb923f7cfff2c29821c87e7032be6bd53`
- `evidence/call-005-b367f802/obs-0004.html` — sha256 `3c0b9173bb5060cd476664b8c9a2ea7c88cd6890c5577856ecd817c490b027c9`
- `evidence/call-006-2fe96bd8/obs-0006.html` — sha256 `3c0b9173bb5060cd476664b8c9a2ea7c88cd6890c5577856ecd817c490b027c9`

**R04 — verified**: After successful login, the hydrated Account control is a button and its menu exposes Collection, Wantlist and Sign out. The initial Account-link locator failed before any account-menu click.

Preconditions: Supplied signed-in account; Wait for hydrated Account button.

- Use the observed role appropriate to authenticated state.
- A fresh page can initially render an Account link while authentication hydrates; header role must be read again.

Browser evidence:

- `evidence/call-004-e84ef858/obs-0019.html` — sha256 `e0f4337b67665039dcfaa98403410f13489f586ab60581d824cd2dbcdb141428`
- `evidence/call-005-b367f802/obs-0004.html` — sha256 `3c0b9173bb5060cd476664b8c9a2ea7c88cd6890c5577856ecd817c490b027c9`
- `evidence/call-005-b367f802/result.json` — sha256 `ca0f09ad3cbd738401cb8648d862141bfc514697faf86165c61a7a6f255ec7bf`
- `evidence/call-006-2fe96bd8/obs-0006.html` — sha256 `3c0b9173bb5060cd476664b8c9a2ea7c88cd6890c5577856ecd817c490b027c9`

**R05 — verified**: For release 84 absent from this account collection, clicking Add to Collection kept the Add label, showed sidebar Have 7 from baseline 6, and added one release-84 card to /me/collection; revisiting the release showed Have 7.

Preconditions: Signed-in supplied account; Release 84 initially absent from account collection; Baseline Have 6.

- Immediate main summary still showed Have 6 while sidebar showed 7.
- Fresh list and release readback confirmed membership and count.

Browser evidence:

- `evidence/call-006-2fe96bd8/obs-0009.html` — sha256 `e50cf30d1bdd84456d6d74f08cb3f9050e303e10ccfb23a946c0321c59a959a3`
- `evidence/call-006-2fe96bd8/obs-0015.html` — sha256 `ee0f8ae2f2cceb423e00ee7bc92d313dbacd8a60fd56fb4c6f9259bea90ceb08`
- `evidence/call-007-b883c60f/obs-0006.html` — sha256 `642e6fac35d4e158ac44a37fe7b7ac2c480a44dc86fa93732d98aa27eec8cbfd`
- `evidence/call-007-b883c60f/obs-0010.html` — sha256 `f4f41eb0020d55a4ba5e964499d463ab890e0f38ff256620f2f83c2789a0ef15`
- `evidence/call-007-b883c60f/obs-0014.html` — sha256 `3b9ef70f2ac2e19192bc26cc0727968fae6de6d4bb8148e1581ca316779bd766`
- `evidence/call-007-b883c60f/network.json` — sha256 `0dc5b8ecfdb24a399224e6d539c8acaa1b90b04deefd6a90d1753bb1d185fce0`

**R06 — verified**: For confirmed collection membership of release 84, one repeated Add to Collection produced sidebar Have 8 locally, but one collection card remained and a fresh release visit restored Have 7. The observed target membership behaved idempotently despite the local increment.

Preconditions: Signed-in supplied account; Release 84 already added once and persistently confirmed.

- No toggle removal or duplicated card was observed.
- Do not use the immediate sidebar increment as evidence of another persistent membership.
- Hidden metadata changes were not observed.

Browser evidence:

- `evidence/call-008-d9a7b977/obs-0009.html` — sha256 `a10d60009e54831a5a3a43a0e9ab3c8e73b7dc5d7a4de4ff501b3f5ff2323180`
- `evidence/call-008-d9a7b977/obs-0018.html` — sha256 `f4f41eb0020d55a4ba5e964499d463ab890e0f38ff256620f2f83c2789a0ef15`
- `evidence/call-009-b1f265f4/obs-0003.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`
- `evidence/call-008-d9a7b977/network.json` — sha256 `592cd275f069a37457a272cac4610d57ea3088bbf21af23067c878e5ab11fa25`

**R07 — verified**: The account could add release 84 to its wantlist while it was already in collection: Want 6 became 7, and the release appeared in both account lists.

Preconditions: Signed-in supplied account; Release 84 absent from baseline wantlist, present in collection.

- Collection and wantlist membership coexisted for this release; other releases and accounts are untested.

Browser evidence:

- `evidence/call-008-d9a7b977/obs-0003.html` — sha256 `5f99967491793b497ae7a297ecfb8726fa0e0f0f5b86a0e9c4d462d11b1f5141`
- `evidence/call-008-d9a7b977/obs-0012.html` — sha256 `83a9a9d202ec56eb6d3b70d2af4b37d73273e3ad1fe0ca89eb4249db6ee165f4`
- `evidence/call-008-d9a7b977/obs-0015.html` — sha256 `6bae56e38925a94a05407d54f3ac44bbb869b63cd0e2268155535da283ade787`
- `evidence/call-008-d9a7b977/obs-0018.html` — sha256 `f4f41eb0020d55a4ba5e964499d463ab890e0f38ff256620f2f83c2789a0ef15`
- `evidence/call-008-d9a7b977/network.json` — sha256 `592cd275f069a37457a272cac4610d57ea3088bbf21af23067c878e5ab11fa25`

**R08 — verified**: One repeated wantlist add for release 84 temporarily showed sidebar Want 8, while a fresh release visit returned Want 7. The Add to Wantlist label remained unchanged.

Preconditions: Signed-in supplied account; Confirmed wantlist membership of release 84.

- Persistent visible count did not increase on the repeat; absence of hidden writes is not independently proven.

Browser evidence:

- `evidence/call-009-b1f265f4/obs-0003.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`
- `evidence/call-009-b1f265f4/obs-0006.html` — sha256 `1527652280033e6cc1a1213a8b7d1d68f4a24f60b22084c27ba2e84399756f37`
- `evidence/call-009-b1f265f4/obs-0009.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`
- `evidence/call-009-b1f265f4/network.json` — sha256 `4605800eb84e62c2c829e62caa47fc9838ec93d269ba6f3353a6d1714e6e4cc5`

**R09 — verified**: Release 84 links to /sell/release/84. Its initial table had seven listings sorted by ascending price, and Add to Cart controls were links whose href identifies the listing, rather than buttons.

Preconditions: Observed release-84 marketplace table.

- Listing 354: caseyjones17, Japan, USD17.19.
- Listing 355: melanie9414, US, USD18.05.
- A button locator failed before dispatching a cart add.

Browser evidence:

- `evidence/call-009-b1f265f4/obs-0012.html` — sha256 `45dc4780a23c7f988de55792acd98bace0a585d353fbdac6ddaca76a8f7398c4`
- `evidence/call-010-0358d125/obs-0007.html` — sha256 `1e4905574ca2ec7069c45a0785f853559a5f1b3595356ef0ace8d66cb1915763`
- `evidence/call-010-0358d125/result.json` — sha256 `13374c140ec057cf4d9539a4001d01e322dbac53e0380892347f3bef60b935a3`

**R10 — verified**: From an empty signed-in cart, clicking the UI Add to Cart link for listing 354 created one cart item with quantity 1, total 1719 cents, and the UI remained consistent after navigating to /cart.

Preconditions: Signed-in supplied account; Empty cart; Listing 354 visible in release-84 marketplace.

- Target changed record count is one cart item; order effects were not observed for this action.
- The UI shows the release title and seller; quantity is exposed in the naturally caused cart response.

Browser evidence:

- `evidence/call-011-0a0a4fed/obs-0003.html` — sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`
- `evidence/call-011-0a0a4fed/obs-0009.html` — sha256 `fa0c9a8906410b8e874da9a4bc4e97e0474ec87892ae4512cda3a2a98043350d`
- `evidence/call-011-0a0a4fed/obs-0012.html` — sha256 `50bf398f1455678f6d60110c9b16cdde2913c0a7d685279078cf1444f4929f1b`
- `evidence/call-011-0a0a4fed/network.json` — sha256 `00dfc06bcf6545f83d4cffab10aabbde1698f4b3fd5a69ea9afbaa092e34d924`

**R11 — verified**: After a confirmed quantity-1 add of listing 354, adding that exact listing again kept one cart item and increased quantity to 2, total 3438 cents; this persisted on /cart readback.

Preconditions: Signed-in supplied account; Only listing 354 in cart with quantity 1.

- The repeat is non-idempotent for this observed transition; no quantity above 2 or stock ceiling was tested.

Browser evidence:

- `evidence/call-012-18445869/obs-0006.html` — sha256 `0e5dfd2e7b1e0b4c412ce3ce6b052f63082c64315b7de397b57717a29d81b2fd`
- `evidence/call-012-18445869/obs-0009.html` — sha256 `03a791a450f7ac1e008c8ca9c41e16cabe625d18ffbbbcd4088e2a1852ebc014`
- `evidence/call-012-18445869/network.json` — sha256 `4515e345a5a93f64a69d1e6be1199e1aa7b78e26e42a052a9daca1a12eb62163`

**R12 — verified**: Checkout with the observed cart containing listing 354 quantity 2 returned a paid order for 3438 cents, quantity 2, and cleared the cart to zero. A later visit confirmed the empty cart.

Preconditions: Signed-in supplied account; Only listing 354 quantity 2 in the cart.

- Observed response order id was 121; do not predict future IDs.
- Total affected business record count, fulfillment and stock effects remain unknown.

Browser evidence:

- `evidence/call-012-18445869/obs-0009.html` — sha256 `03a791a450f7ac1e008c8ca9c41e16cabe625d18ffbbbcd4088e2a1852ebc014`
- `evidence/call-012-18445869/obs-0012.html` — sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`
- `evidence/call-012-18445869/network.json` — sha256 `4515e345a5a93f64a69d1e6be1199e1aa7b78e26e42a052a9daca1a12eb62163`
- `evidence/call-014-16db3469/obs-0003.html` — sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`

**R13 — verified**: Checkout was disabled when the signed-in cart was empty. No empty-cart backend submission was attempted.

Preconditions: Observed empty signed-in cart after checkout.

- UI boundary only; backend rejection conditions remain unknown.

Browser evidence:

- `evidence/call-012-18445869/obs-0013.html` — sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`
- `evidence/call-014-16db3469/obs-0003.html` — sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`
- `evidence/call-014-16db3469/result.json` — sha256 `81f5d451976a469784ff25cc9a1e322370a9942ab7de4945728e675fb3f32d6d`

**R14 — verified**: From an empty cart, adding listing 355 showed seller melanie9414 and USD18.05. Removing this sole quantity-1 item returned to empty total zero, confirmed after a fresh visit.

Preconditions: Signed-in supplied account; Only listing 355 quantity 1 when Remove was clicked.

- A naturally caused DELETE response returned ok true.
- Removal of quantity>1 or multiple-item carts is untested.

Browser evidence:

- `evidence/call-014-16db3469/obs-0009.html` — sha256 `7b715976829b247be1ec45039fffc6b19827a0b62ef3cc2ff015d728b856c5e2`
- `evidence/call-014-16db3469/obs-0012.html` — sha256 `1e50344c3bd2ee00d1d6872618e059a95d5b7156493c8d9a905a4ed880541dd5`
- `evidence/call-014-16db3469/obs-0015.html` — sha256 `90938ea2396c8c330e230b37006259a1a2b71bc86f378220fa3b56174c24cb4b`
- `evidence/call-014-16db3469/network.json` — sha256 `42bda1a3eb0d6d99682814d45a83821e569d440137c9077a2b7b8a4a2721b94a`

**R15 — verified**: Applying Ships From US and Sort price_desc to release 84 returned two rows priced USD37.63 then USD18.05. Adding Minimum Rating 99 yielded zero rows and No listings match these filters.

Preconditions: Observed release-84 marketplace; Other filter fields blank; Apply submitted the staged inputs.

- Only these exact filters and this release were tested.
- Case sensitivity, substring semantics, condition matching and rating endpoints remain unknown.

Browser evidence:

- `evidence/call-013-bec4f27e/obs-0012.html` — sha256 `ede0c66ea5bb59e7a15604e074c0f0538146529438808d1cbd17b453c420428f`
- `evidence/call-013-bec4f27e/obs-0018.html` — sha256 `71e1ea39d225a51eee37804ffb03da2a45375b7f164f510417da5537ca78237a`

**R16 — verified**: Submitting the header search Pink Floyd returned three release cards: Assimilated grid-enabled open system, Re-contextualized asynchronous Graphical User Interface, and The Dark Side Of The Moon.

Preconditions: Header search query exactly Pink Floyd.

- Observed /search?q=Pink+Floyd; other search matching and pagination rules are unknown.

Browser evidence:

- `evidence/call-015-b56c53e9/obs-0009.html` — sha256 `e5c038d38612e227b979add6094cc42a11dd0a6ecd70c8bbd42db4cc6bb98505`

**R17 — verified**: In this authenticated /sell page, Create Listing was disabled before release selection. Searching the exact release-84 title returned a unique #84 result that was automatically selected.

Preconditions: Signed-in supplied account; Fresh /sell form; Exact query Open-architected maximized Local Area Network.

- No explicit result click was required in this one-result case.
- Multiple-result behavior is unknown.

Browser evidence:

- `evidence/call-015-b56c53e9/obs-0012.html` — sha256 `ffafd3c92812ddad9606d5f386148ff475bebcc21f1fa4eaaa06358927cd725e`
- `evidence/call-016-92eb0477/obs-0003.html` — sha256 `ffafd3c92812ddad9606d5f386148ff475bebcc21f1fa4eaaa06358927cd725e`
- `evidence/call-016-92eb0477/obs-0009.html` — sha256 `9d4646d1fee976538cf82010de6d0cc92f57e5c4849e7df0e185cf47bce0b531`
- `evidence/call-016-92eb0477/result.json` — sha256 `3c5c8887692187e670f079d6b541c4ea019bf556b1d37751f6cd61ca3c35f9aa`
- `evidence/call-016-92eb0477/network.json` — sha256 `ee0909c610bdda81a08b27f50249826f3f6f422cdf416e6eea2eeaebfb7c7db8`

**R18 — verified**: Creating a listing for release 84 with quantity 0, price 1729 cents, media Near Mint (NM or M-), sleeve Very Good Plus (VG+), Ships From US, and the pilot comment returned 422 and quantity validation Input should be greater than or equal to 1.

Preconditions: Signed-in supplied account; Selected release 84; Exact staged values from call 17.

- The validation was a real backend rejection naturally caused by the UI submission.
- The list did not gain the proposed release; successful positive creation remains untested.

Browser evidence:

- `evidence/call-017-1d0e245a/obs-0018.html` — sha256 `0ce887b35c0ad5888a38996243788cc234aac08385cde2d309b28aa523b1e75e`
- `evidence/call-017-1d0e245a/obs-0021.html` — sha256 `a083ad967aacfb57e430d92e0ab1b902639bfc2661472db0562f5e2b4f533ec7`
- `evidence/call-017-1d0e245a/network.json` — sha256 `66d77562c1eeb5662471a282ff23a692514b587557a5fa53d89f1b752564d20f`

**R19 — verified**: With selected release 84, quantity 1, price 0 cents and otherwise default selling fields, Create Listing was disabled. Attempting its native click timed out; execution stopped.

Preconditions: Exact staged sell form in call 18.

- UI disabled-state boundary is observed.
- This is not evidence of backend price validation; no successful submission was observed.
- Terminal action effect stays unconfirmed under the contract; no further browser script was run.

Browser evidence:

- `evidence/call-018-ee1f9e5a/obs-0012.html` — sha256 `8fb43b4ffd6344f256f87c9fa8e38c19cd7b539abc5405edb8a62a253fb5b376`
- `evidence/call-018-ee1f9e5a/obs-0015.html` — sha256 `cacb6f6563a0aad3105411d2e5fd4ad0fba0522ee5f4fa5c50065439bb20649e`
- `evidence/call-018-ee1f9e5a/obs-0018.html` — sha256 `cacb6f6563a0aad3105411d2e5fd4ad0fba0522ee5f4fa5c50065439bb20649e`
- `evidence/call-018-ee1f9e5a/result.json` — sha256 `95b2410bd5e58ec41b79accef8b2c81f4f5137df6f0d243a52dd0653b5779058`
- `evidence/call-018-ee1f9e5a/actions.jsonl` — sha256 `27dfc919a1b07e8cfa6b7dd028d2d17765a41bd96a413b80a7b45e4e8dd751be`
- `evidence/call-018-ee1f9e5a/network.json` — sha256 `c6432d6eff21ef3effc87adf39f2d430389dbda952144a6335555cbc6c216f35`

**R20 — verified**: The linked /add-release route rendered 404 This page could not be found when visited in this run.

Preconditions: Navigation to observed footer href /add-release.

- This route observation does not prove absence of backend release creation or another UI.

Browser evidence:

- `evidence/call-015-b56c53e9/obs-0015.html` — sha256 `b408135f7e2c512af72ddd180b31dd9efebf0c18fa4df5f2305799e488d4f51f`

**H01 — hypothesis**: The release-84 membership behavior may generalize to other releases and accounts.

Preconditions: Only one release and one supplied account were tested.

- Distinguish using a different release, separate membership baseline, single add, repeat, and fresh readback in a future reset run.

Browser evidence:

- `evidence/call-007-b883c60f/obs-0014.html` — sha256 `3b9ef70f2ac2e19192bc26cc0727968fae6de6d4bb8148e1581ca316779bd766`
- `evidence/call-009-b1f265f4/obs-0009.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`

**H02 — hypothesis**: Local membership counters likely update optimistically while stored membership is a set.

Preconditions: Observed local repeat increments and stable fresh counts.

- No client code was inspected; only the visible discrepancy and responses are known.

Browser evidence:

- `evidence/call-008-d9a7b977/obs-0009.html` — sha256 `a10d60009e54831a5a3a43a0e9ab3c8e73b7dc5d7a4de4ff501b3f5ff2323180`
- `evidence/call-009-b1f265f4/obs-0003.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`
- `evidence/call-009-b1f265f4/obs-0006.html` — sha256 `1527652280033e6cc1a1213a8b7d1d68f4a24f60b22084c27ba2e84399756f37`
- `evidence/call-009-b1f265f4/obs-0009.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`

**F01 — refuted**: For the observed release-84 repeat, collection addition toggles membership off or creates another visible collection card.

Preconditions: One confirmed repeat of release-84 collection addition.

- The release remained once in collection and fresh Have remained 7.
- Other data or hidden metadata are not covered by this refutation.

Browser evidence:

- `evidence/call-008-d9a7b977/obs-0018.html` — sha256 `f4f41eb0020d55a4ba5e964499d463ab890e0f38ff256620f2f83c2789a0ef15`
- `evidence/call-009-b1f265f4/obs-0003.html` — sha256 `121abdbf52c4c75c9690c2a8c13cd67ffc68cb2cb93c95315ecca516e1cfa6bf`

**F02 — refuted**: For listing 354 quantity 1, repeating Add to Cart leaves the target quantity and total unchanged.

Preconditions: Observed listing 354 quantity 1→2 transition.

- Natural cart response showed quantity 2 and total 3438.

Browser evidence:

- `evidence/call-012-18445869/network.json` — sha256 `4515e345a5a93f64a69d1e6be1199e1aa7b78e26e42a052a9daca1a12eb62163`
- `evidence/call-012-18445869/obs-0009.html` — sha256 `03a791a450f7ac1e008c8ca9c41e16cabe625d18ffbbbcd4088e2a1852ebc014`

**U02 — unknown**: Successful listing creation, deactivation/reactivation, anonymous write behavior, stock limits, multi-seller checkout, cancellation, account-list removal and other catalog routes remain unknown.

Preconditions: The run stopped at call-018 timeout.

- Missing or disabled controls establish UI state only, not backend absence.
- Future distinguishing experiments are recorded in coverage.json and were not executed.

Browser evidence:

- `evidence/call-015-b56c53e9/obs-0012.html` — sha256 `ffafd3c92812ddad9606d5f386148ff475bebcc21f1fa4eaaa06358927cd725e`
- `evidence/call-018-ee1f9e5a/result.json` — sha256 `95b2410bd5e58ec41b79accef8b2c81f4f5137df6f0d243a52dd0653b5779058`

The terminal failed click is retained as unconfirmed. The disabled button is observed; backend price-zero validation is unknown. All subsequent work was offline artifact synthesis. See R19 evidence and coverage.json.

Reusable execution: supply this revision’s scripts.py and behavior_model.py as modules to a native task wrapper. run(h) only opens home. Other functions expose login, search, membership, cart, filters and seller staging. They do not retry writes. Positive listing success is untested.

Prediction interface: behavior_model.predict(observation, intent) returns the public shape. Structured current observations are required for business branches; intent scope defaults to action. scope=task, unsupported operations and out-of-sample conditions return unknown. Do not set authenticated or membership fields without permitted current observations.
