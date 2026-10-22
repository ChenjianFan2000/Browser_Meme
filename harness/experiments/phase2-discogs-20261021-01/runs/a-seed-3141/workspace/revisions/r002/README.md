# Condition A learning package r002

Read rulebook.md and rules.json for bounded claims, coverage.json for remaining uncertainty, and objects.json for observed identities. r001 is the retained parent. This package used the public origin, fixture keys and native browser observations; no private tasks were available.

The separate behavior_model.py exports predict(observation, intent) and returns the public prediction shape. Its module docstring documents input keys. Untested values and whole-task compositions return unknown; per-action predictions are not whole-task scores.

scripts.py supplies native Playwright entry points. Supply current observed record IDs and artist/title selection, and include both scripts.py and behavior_model.py in execute_script modules. A temporary task file may import scripts and export run(h). Read the runtime guide for exact tool usage. The default scripts.run only opens the home page. The runtime handles locator confirmation/scrolling and exports observations around each action.

Helpers return None on missing, ambiguous, invisible or disabled controls. Stop dependent work on None. Create Listing explicitly selects and verifies the requested release, verifies field values, submits once, and records row-count readback. Review exported network/DOM evidence before retrying any write. Visually identical inactive listings640/646 intentionally remain ambiguous to the reusable deactivation helper.

All evidence_refs use original workspace-relative browser export paths and sha256. evidence_manifest.json lists every exported file. failures.json separates locator/implementation problems from observed business rejection. Pre-execution policy errors have no fabricated browser evidence. The final wrappers were exercised as detailed in coverage.json; no independent success score is claimed.

The learning account/state may be reset before evaluation. Do not treat final observed availability/status as a permanent rule. Keep frozen rules/model unchanged during private tasks; temporary native scripts and current-task supervision are allowed by the contract.
