# Bounded browser rulebook — revision 001

Condition A, independent gpt-6.1-sol, scheduling seed1729. Seed concerns experiment scheduling only. This document is a retrospective synthesis, not an independent correctness score. Only the supplied account and observed conditions are covered.

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

The visited release /release/221 was Pink Floyd - The Dark Side Of The Moon (1973), with release details, tracklist, Add to Wantlist, Add to Collection and a marketplace link labeled 25 for sale. The marketplace itself was not yet visited at this checkpoint.

Conditions: Release 221 during calls 005-006.

Branches/limits: {"release": "Details plus membership controls", "marketplace": "Observed href /sell/release/221 and link label only"}.

Evidence: `evidence/call-005-458acab8/obs-0006.html` (sha256 `f5fc237f8782cb82d18dfbee0dd4da3336bb80982e929d3383afc5cecae2043d`).

## R004 — verified

When release 221 was absent from this account wantlist, one Add to Wantlist click succeeded and fresh /me/wantlist readback gained one card for 221 (10 to 11 cards).

Conditions: Authenticated supplied account; Release 221 absent from observed wantlist baseline.

Branches/limits: {"absent": "One membership added", "present": "See R005; not a new insertion"}.

Evidence: `evidence/call-006-67f666a9/obs-0012.html` (sha256 `1dc543cd463a9b951408afa714b68a7b820a4d632b495adf8961570d8ccb3eab`); `evidence/call-006-67f666a9/obs-0018.html` (sha256 `3192d6e11a0449e7594f41a1595f4c144360550d8c0b94b6b6cec4361d413585`); `evidence/call-006-67f666a9/obs-0021.html` (sha256 `96acb38c03449fcab19d4f1cba18bcf3fbcf874e68e5a30343c9194d2821f6e9`); `evidence/call-006-67f666a9/network.json` (sha256 `e8b693a1229f9d5a6eb147ac5b7d89b948b03a05a7182aa541ec9484e257bde5`).

## H000 — unknown

A repeat Add to Wantlist might be idempotent, duplicate a record or toggle membership; no repeat has been tested in this checkpoint.

Conditions: Evidence cutoff call 006.

Branches/limits: {"next": "After confirming membership, click Add once and reopen account list and release."}.

Evidence: `evidence/call-006-67f666a9/obs-0021.html` (sha256 `96acb38c03449fcab19d4f1cba18bcf3fbcf874e68e5a30343c9194d2821f6e9`).

## Evidence interpretation

The runtime action log uses a generic unconfirmed classification even for many successful navigations. This package preserves that field in exploration.jsonl and separately classifies actual observations. Persistent business claims require the specific UI-caused response and subsequent readback cited above. A locator timeout is not a website rejection. The input-attribute boundary is a runtime restriction, not a business rule.

Initial experimental predictions are preserved even when wrong. In particular, the empty-login label describes an invalid experimental setup: no fields were cleared before submitting the seeded form. No rejected-credential claim is supported. Evidence: `evidence/call-003-aed7b82b/actions.jsonl` (sha256 `857b4936f3f842dc4b711752f90eba38573cf30179156613cd5c8a6dbd64143c`); `evidence/call-003-aed7b82b/network.json` (sha256 `474bd97d2a36708f39129ab4bdc9a0ef997de2a62d3d28e4b0294d0927759019`).

## Using the package

Load behavior_model.py and call predict(observation,intent) with explicit current observed facts. Follow model_interface.md in the final revision for the schema. Unknown means evidence is insufficient; it does not mean an action will fail. Original executed scripts remain in experiments/. Revised scripts.py offers native Playwright entry points; it is not an automatic action dispatcher or a claim of private-task success.
