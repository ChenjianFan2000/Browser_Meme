# Native task execution

This is condition B. `scripts.py` executes supplied UI actions; it contains no behavior predictor. A supervising caller must provide a separate per-action prediction dictionary for every call. No private evaluation task was available during learning.

Use a workspace wrapper exporting `run(h)`, import the needed functions from `scripts`, and pass `revisions/r002/scripts.py` in the browser tool's `modules` array. The actual browser tool discovered in this run is `mcp__phase2__execute_script`. Navigate explicitly on each submission. Credentials come only from `h.fixture`; do not print their values.

Entry points are `navigate`, `global_search`, `sign_in`, `account_menu`, `add_membership`, `find_listing_release`, `choose_listing_release`, `fill_listing_field`, `create_listing`, `deactivate_listing`, `apply_market_filter`, `add_cart_row`, `remove_cart_item`, and `checkout`. `perform` verifies a unique target, checks click enablement, records the caller's prediction, performs one native action and exports a readback. It does not interpret observations or select an outcome prediction.

The reusable `add_cart_row`, `remove_cart_item` and `deactivate_listing` functions were executed in experiments35 and39. Their exact browser evidence and hashes are cited under R26/R28 in `rulebook.md`. Other entry points compiled; related native UI sequences were explored, but the extracted functions themselves were not all independently exercised. Pass `row_index` only after inspecting matching rows when title/price are not unique. Reinspect form input structure if it changes.

Original experiment scripts remain in workspace `experiments/`; the inventory records their hashes. Failed versions remain alongside corrections. `40b_subscribe_locator_v2_UNEXECUTED.py` is an explicitly unexecuted locator correction. Newsletter business behavior is unknown (U02). Do not treat any script's pre-action prediction as observed truth, or per-action predictions as whole-task scores.

Stop on an unconfirmed write. A repeat after confirmed success must be deliberate: cart adds and listing creation were non-idempotent in the bounded observed cases (R06/R24). A fresh navigation is useful for reconciling optimistic membership counters (R03/R04/R27). All business statements here are bounded by the cited rules and their exported browser evidence.
