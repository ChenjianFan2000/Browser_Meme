Condition B independent browser-only learning package.

Read rulebook.md and rules.json for bounded observations and unknowns. revision.json records the parent; all parent directories and failed experiments remain. evidence_refs paths are relative to the workspace root and reference original exported browser artifacts.

Use scripts.py through phase2.execute_script. It exports run(h), a read-only home smoke entry point, and supervised native helpers: navigate, sign_in, search, add_membership, filter_marketplace, find_listing_release, fill_listing, submit_listing, deactivate_listing, add_cart, remove_cart, checkout_once. Import via a temporary workspace script and pass this scripts.py in modules. Supply per-action expectations to act when known; default expectations remain unknown. Always inspect observations and UI-caused network evidence; no write retries are implemented.

These are task execution helpers, not a predictor. No behavior_model.py exists. Locator-based helpers intentionally refuse ambiguous records. No private tasks or evaluator feedback were used.
