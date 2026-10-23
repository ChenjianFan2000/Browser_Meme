# v006 representation interface

This minimally repairs successful-state invariant closure in frozen v005; no prior version or failure is replaced. Import and register only `components_v4.py`. It owns the same pure state/plan/typed-binding logic and native locators; model.py re-exports the identical implementation. No hidden server ID or DOM-order identity is used.

Use `q=plan(s,action,parameters)` before UI; on `not q.ok`, read_point with its reason. Persist q.prediction through h.expect, confirm the unique native locator, perform action, wait/read and pass independent gates, THEN commit s=q.state. Never commit a hypothetical state on failure. Initial state assumes a fresh operator-reset baseline, unauthenticated /login. Login form_edit is allowed before auth; protected unauthenticated navigation is explicitly unsupported/blocked.

## Prior search shape, including zero rows

jobs.search has ONE ready branch before querying: query/location are known input parameters, results are unknown_external 0..N. It requires a stable DOM results container and an independent AX root, then applies local contracts to every selected DOM/AX row. Every DOM row has title/company/location and its own enabled Save/Saved BUTTON; same_dom_set requires the DOM/AX parent row sets to reference the exact same underlying public DOM nodes. Empty sets are legitimate: child contracts are not_applicable with zero evaluated instances, never counted as child passes. No empty/nonempty branch is selected from the response, no total is fixed, and no observed external leaves are inserted into the prior prediction.

`collection_prediction()` emits the same 0..N ready structure without query controls. `plan` automatically declares unknown_slots rows.*.title/company/location_mode/save_label for jobs.search or collection. Bindings are a separate output channel with capture-local parent provenance; those paths are not persistent object IDs.

`normalize_job_row_binding(binding)` accepts typed per-item slot data {title:string,company:string,location_mode:[location," • ",mode],save_label:Save|Saved}; it returns canonical identity {title,company,location_mode:combined visible string}, saved:bool and preserved raw_slots. `normalize_visible_job(identity,saved)` applies the same normalization to native visible extraction. `bind_contract_rows(s,bindings['rows.each'])` normalizes all contract-bound rows before bind_rows. Never pass slot arrays directly into the helper's string identity field. Unrecognized separators/types fail, rather than becoming wildcard strings. public_jobs/job_row/deterministic_job retain their documented native behavior; identity must still be unique before a write.

## Display content versus entity identity

`register_entity(s,handle,observation,provenance)` registers a caller's local causal handle, such as a known independent creation event. The handle is a model symbol, NOT a server ID, DOM path, index or visible text. Observation uses public fields body/author strings, liked bool and reactions/comments nonnegative ints. State retains mutable observable signatures and provenance.

`match_entity_candidates(s,observation)` returns all compatible handles, with unique/ambiguous/unmatched and action_allowed. Body-only observation can return multiple objects. A richer public signature can distinguish current candidates but is mutable; it is not a globally stable identifier. Missing distinctions keep multiple hypotheses. The body-keyed Like/comment action contracts remain unsupported once multiple same-body entities are registered; plan explicitly refuses them, even when one richer signature currently has one candidate. Do not use nth or silently merge the entities.

## Reconciliation

`bind_post(s,body,liked,reactions,comments,unique)` now checks EVERY supplied observation. First binding is recorded; equal later values record consistent; differing values return contradiction with prior/observed snapshots and state_changed=false. It never silently retains stale values as if verified.

`reconcile_entity(s,handle,observation,provenance,mode='verify')` compares a typed observation with stored signature. Verify mode rejects differences without changing prior state. Explicit mode external_update returns a separate reconciliation report, updates only observable knowledge with provenance, and gives no prediction credit. Uniquely associated legacy post state is synchronized; changed external reaction/comment baselines become unknown and dependent writes block. Changing content without stable public identity proof is refused. Known own action plans update the uniquely registered entity's predicted signature, so later matching observation is consistency verification, not external correction.

Other supported plan actions remain the v003 set: navigate, auth_success/auth_reject, form_edit, search/select_job/save/apply, open_composer/fill_post/create_post, like/open_comments/fill_comment/comment, reload. Existing unique-body guards and disabled Applied guard remain. Duplicate-body creation is an exploration outcome, not a new body-keyed create API that guarantees uniqueness.

Scope/limits: component structure and reset-relative effects, not full page clone. Public identical objects may be observationally ambiguous. DOM/AX bridge uses exact mapped backend references, not positions; missing mapping is unknown. No complete site or strict isolation claim. Evidence and probes are not consumer input. Independent task success is separate from author UI and local checks.

## Native Playwright prediction/commit pattern

For an already authenticated known jobs state, a query edit remains native:

```python
q = c.plan(s, 'search', {'query': new_query, 'location': s['location']})
if not q['ok']:
    h.read_point(q['readpoint'])
h.expect(q['prediction'], 'Prior 0..N shape; external row values not known')
field = h.page.get_by_placeholder('Search jobs', exact=True)
h.confirm(field)
field.fill(new_query)
if field.input_value() != new_query:
    h.read_point('Input confirmation failed')
s = q['state']  # only after native confirmation and controller gate release
```

Scoring stays split: prior structural anchors, per-item shape and DOM/AX correspondence are predictive assertions; exact row texts/identities are observation bindings, never prior exact-value successes. Unknown cardinality means neither predicted zero nor predicted twelve. Zero rows earn no child-instance passes. Entity candidate inference is separate from permission to execute: contextual unique matching does not enable the unsupported duplicate-body write contract. Explicit external updates produce provenance and differences, not a retroactive prediction pass.

## v005 registry consistency repair (offline only)

The compatible helper filename remains components_v4.py. The two views now have an enforced invariant: when a body refers to one registered entity, every shared liked/reactions/comments fact must agree. Register-first and bind-first ordering both check prior known facts, reject contradictions without mutating input, and enrich missing fields from already consistent knowledge. plan and candidate resolution also reject pre-existing conflicting state; an action cannot silently overwrite one registry from the other.

Registering another causal entity with the same displayed body retains both independent entity records and explicitly invalidates the legacy body-only alias, recording its old facts and provenance. It never merges their different reaction/comment states. Body-keyed binding and writes then remain ambiguous/blocked.

Verify reconciliation checks the combined known facts of both views. Explicit external_update remains the only supported update path for differing observations from a consistent prior: it records provenance/differences, synchronizes a uniquely associated body alias, gives no prediction credit and invalidates uncertain delta baselines. Already internally conflicting state must be rejected; external_update is not a silent repair of corrupt registry input. Existing legitimate own-action plans update both consistent views together.

This version is a pure-model repair: zero new UI execution and no new business capability or consumer strategy. Independent task execution remains unverified.

## v006 successful-state closure repair (offline only)

Every semantic state producer now checks the input and validates its candidate state before returning success: plan, bind_job, bind_rows, bind_contract_rows, bind_post, bind_post_absence, register_entity and reconcile_entity. A failed candidate is rejected without mutating the input. initial_state constructs a consistent initial state; clone is only a generic JSON-copy utility, not an accepted model transition.

Absence is a conservative fresh-body precondition, not proof that a previously known object was deleted. A zero current-view count cannot override known post/entity facts, so bind_post_absence rejects an already known body. Creation independently rejects a registered body and consumes its fresh absence precondition on success. Later positive post/entity binding invalidates any prior absence precondition. Internally conflicting absence/presence input is rejected before planning; no backend deletion or lifecycle semantics are invented.

The component contract bundle and business scope are unchanged. Finite pure-memory operation-sequence checks establish only the tested consistency invariant, not website reachability or independent task success. This revision adds zero UI execution.
