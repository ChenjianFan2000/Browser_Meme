# Condition B browser learning, revision 1

This is a bounded account/session report, not a complete website specification. Checkpoints were assembled after the terminal stop; revision history preserves evidence scope rather than claiming earlier publication. Only rendered DOM and UI-caused public responses were used. No source files, client-script bodies, direct API calls, JavaScript evaluation, private tasks or historical model were used. Evidence: `evidence/call-003-8c83c3e0/result.json` (sha256 `2fa77c537dc3df228d65b48f563974bc7674f5c7dbc2ad0e260e7fd61add7233`).

Each rule below is limited by its preconditions. Verified describes observed cases; hypothesis and unknown retain uncertainty. Runtime action_after classifications are raw instrumentation labels, not independent semantic scores. Per-action expectations are in exploration.jsonl; no whole-task score or prediction was produced. Evidence: `evidence/call-001-9faee651/actions.jsonl` (sha256 `a542398ff9d28d7ee7924ce4c6f745620961bf908a858e70ae5c988bbf2a9830`); `evidence/call-002-01f0dfe3/actions.jsonl` (sha256 `8328a276edc835cf8e332105433cda31ab140fe1b66850e9f61758708a3459b4`); `evidence/call-003-8c83c3e0/actions.jsonl` (sha256 `096dfd72f3a4a4d5e719f49e3b72c1e12009cef5bd655a5cc06afeff90eccc4c`).

## UI-COOKIE — verified

In the initial home-page state, Accept All Cookies dismissed the visible privacy banner. Its longer-term persistence was not tested.

Preconditions: Initial home page showed privacy banner.

Evidence: `evidence/call-002-01f0dfe3/obs-0004.html` (sha256 `d66e644d72c9791d9b05d2ba3f43a7bd6802b376b869ca9fa92d78156151e044`); `evidence/call-002-01f0dfe3/obs-0006.html` (sha256 `ec389d3baa871fc14edca664f9a413634dd19965cba2fc75c17a945d10f1b510`).

## AUTH-PREFILL — verified

The discovered login form was prefilled; submitting it without clearing fields navigated home and returned a successful authentication response. This was not an empty-credential test.

Preconditions: Discovered /login form in this fixture.

Evidence: `evidence/call-002-01f0dfe3/obs-0010.html` (sha256 `33a0a82a291a03b77ecca1cd05f6b733465ac081b44157a54b8c68e53dd08a11`); `evidence/call-003-8c83c3e0/obs-0006.html` (sha256 `5c3fa437fc2e6b0319fd069a0e44dc2bc46e3fdb2ca98bd9304edbf290ca61f5`); `evidence/call-003-8c83c3e0/network.json` (sha256 `bff459992a6808fa85365ac1b619189e7db368175f2bd71d0ed2dce377491abb`).

## AUTH-EMPTY — hypothesis

Explicitly empty credentials may be rejected; the first attempted empty test did not clear prefilled fields and cannot resolve this.

Preconditions: Login form explicitly emptied; not yet done at this checkpoint.

Evidence: `evidence/call-003-8c83c3e0/actions.jsonl` (sha256 `096dfd72f3a4a4d5e719f49e3b72c1e12009cef5bd655a5cc06afeff90eccc4c`).

## AUTH-LOCATOR-FAILURE — verified

After the prefilled login navigated home, a Username or Email locator timed out. This is a page/locator assumption failure, not evidence of credential rejection.

Preconditions: Experiment 03 continued after home navigation.

Evidence: `evidence/call-003-8c83c3e0/result.json` (sha256 `2fa77c537dc3df228d65b48f563974bc7674f5c7dbc2ad0e260e7fd61add7233`); `evidence/call-003-8c83c3e0/obs-0009.html` (sha256 `09e2afc664c5f4ffca9acd918a28c0f7b53f7c7189b54a11d05a04a8259a045c`).

## Execution and limitations

Use scripts.py under current-task supervision. Its helpers are native UI execution, do not derive behavior predictions, and never automatically retry writes. A task must authorize checkout, which committed immediately in the observed case. Confirm the current DOM before action; select cart items by identity rather than position. On any unconfirmed business write, stop and preserve evidence. New reusable helpers were syntax checked offline only. Original failed script versions remain under experiments/. Evidence: `evidence/call-003-8c83c3e0/result.json` (sha256 `2fa77c537dc3df228d65b48f563974bc7674f5c7dbc2ad0e260e7fd61add7233`).
