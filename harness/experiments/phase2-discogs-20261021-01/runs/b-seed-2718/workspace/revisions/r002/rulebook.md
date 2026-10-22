# Condition B browser learning, revision 2

This is a bounded account/session report, not a complete website specification. Checkpoints were assembled after the terminal stop; revision history preserves evidence scope rather than claiming earlier publication. Only rendered DOM and UI-caused public responses were used. No source files, client-script bodies, direct API calls, JavaScript evaluation, private tasks or historical model were used. Evidence: `evidence/call-005-437a3c73/result.json` (sha256 `07a09a813106853b46450927310972cee189031e5ebb5b3f371148e1da9635c8`).

Each rule below is limited by its preconditions. Verified describes observed cases; hypothesis and unknown retain uncertainty. Runtime action_after classifications are raw instrumentation labels, not independent semantic scores. Per-action expectations are in exploration.jsonl; no whole-task score or prediction was produced. Evidence: `evidence/call-001-9faee651/actions.jsonl` (sha256 `a542398ff9d28d7ee7924ce4c6f745620961bf908a858e70ae5c988bbf2a9830`); `evidence/call-002-01f0dfe3/actions.jsonl` (sha256 `8328a276edc835cf8e332105433cda31ab140fe1b66850e9f61758708a3459b4`); `evidence/call-003-8c83c3e0/actions.jsonl` (sha256 `096dfd72f3a4a4d5e719f49e3b72c1e12009cef5bd655a5cc06afeff90eccc4c`); `evidence/call-004-e72d7816/actions.jsonl` (sha256 `7ec721327549da00cfafabd40a685f698f95f7956af524e2fdf8a3761aec3273`); `evidence/call-005-437a3c73/actions.jsonl` (sha256 `566f3453f608a54612a36fb4950d9efa259c4f706bfec6da6b13c570f8299151`).

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

## Execution and limitations

Use scripts.py under current-task supervision. Its helpers are native UI execution, do not derive behavior predictions, and never automatically retry writes. A task must authorize checkout, which committed immediately in the observed case. Confirm the current DOM before action; select cart items by identity rather than position. On any unconfirmed business write, stop and preserve evidence. New reusable helpers were syntax checked offline only. Original failed script versions remain under experiments/. Evidence: `evidence/call-003-8c83c3e0/result.json` (sha256 `2fa77c537dc3df228d65b48f563974bc7674f5c7dbc2ad0e260e7fd61add7233`); `evidence/call-004-e72d7816/result.json` (sha256 `19a408fb8250d8146fbd492a7d5e109cf925dde5b44f2c30db87a7b24ed7ac5e`).
