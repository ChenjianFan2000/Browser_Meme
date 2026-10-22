# Bounded rulebook

Condition A; learner gpt-6.1-sol; scheduling seed 2718. The seed identifies scheduling, not model sampling.

R01: In the observed anonymous session the public root rendered a Discogs catalogue with search, Account, cart and menu controls. Account had href `/login`. Observed link destinations are discovery leads, not verified business capabilities.

R02: A single Account click from the root reached `/login` and exposed Sign in, Username or Email, and Password controls. The root was rendered twice across separate browser calls. Neither observation establishes authentication, hidden records, or business effects.

Stop and deviation: The runtime rejected the original dynamic-dispatch helper with `ValueError: observation policy excludes name getattr`. The original helper and script are preserved. One corrected submission was made before recognizing the contract's stop condition; this is a procedural deviation, not compliant continuation. No further browser submissions followed recognition. The exact tool response is transcribed in `runtime_denial.json` at the workspace root; it is audit material, not browser evidence.

Unknowns: Credential acceptance, login errors, authenticated navigation, search behavior, catalogue details, collection/wantlist operations, marketplace listings, cart/checkout, repeat writes, rejection rules, persistence, business record counts, and short business combinations. No website business rejection was observed. The runtime denial supplies no website rule.

Hypotheses only: Successful authentication may expose more controls. Repeated writes may be idempotent, duplicated, or rejected. Distinguish these only in a new permitted learning run using a confirmed first effect and subsequent rendered readback. Missing controls are not evidence of missing backend behavior.

Prediction scope: The executable predictor handles only explicit per-action navigation intents under observed anonymous-page preconditions. Whole-task and business-operation predictions return unknown. False/zero effects for navigation concern target business operations and exclude browser cache, cookies, and authentication state. No task success is inferred from those predictions.

Reusable scripts: `run(h)` reads the root; `open_account(h)` clicks the discovered Account link after precondition checks. Each UI action has a recorded prediction and immediate observation. Runtime confirms and scrolls native locator targets. No writes or retries are implemented. These scripts remain for later task execution, not continued learning after this stop.

Original exported browser evidence (paths relative to workspace root):
- `evidence/call-001-dbccdd13/obs-0004.html` sha256 `d66e644d72c9791d9b05d2ba3f43a7bd6802b376b869ca9fa92d78156151e044`
- `evidence/call-001-dbccdd13/obs-0004.ax.json` sha256 `74b48b5480d8c6497e7b74408ca4a7bb59d631e646f8e1bac2497ec96bdcf873`
- `evidence/call-001-dbccdd13/obs-0004.png` sha256 `d993a21aced45159443a48eaa529fa9399225b9f0ebc77520d702aea39424b0a`
- `evidence/call-001-dbccdd13/actions.jsonl` sha256 `91273453e64dceafd2c21c7000839a062da2234ac709868f97834be019a3dd0f`
- `evidence/call-001-dbccdd13/result.json` sha256 `23505cb32a68df9d667011b01aff2278eec280fd55db14884972038d04a381bf`
- `evidence/call-002-918f04fd/obs-0008.html` sha256 `a784eb5c57887b1f32941f833792c3af2db661f7124711885ebbfb732970b7ed`
- `evidence/call-002-918f04fd/obs-0008.ax.json` sha256 `ea80298aae6c9efbd8300e7fab051c6975eba6b5a8a17aa567924a211e9bb943`
- `evidence/call-002-918f04fd/obs-0008.png` sha256 `9575426116ec8444ab9310b7ff7a41734ac4d736ca3c3858db1d7d35f303763f`
- `evidence/call-002-918f04fd/actions.jsonl` sha256 `045ccca4c842e959561f0abe517cfbc5e7b0b1f86f37556f1379efb5ae50c862`
- `evidence/call-002-918f04fd/result.json` sha256 `208907c3883e5571d524122e720d04266e383ba0dc5cf4dfb7c8c2a825d73a9c`

Offline revision r003 narrows executable navigation predictions to an explicit `anonymous_session: true` observation at the root URL. Model input uses `scope: action` for navigation and returns unknown for task scope and all business intents. Earlier draft r002 is preserved; this refinement introduces no new browser rule.
