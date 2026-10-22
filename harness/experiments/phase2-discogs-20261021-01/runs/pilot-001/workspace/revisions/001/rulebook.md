Browser behavior rulebook — revision 001

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

**U01 — unknown**: Membership, marketplace, selling, checkout and authentication business effects are not established at this initial checkpoint.

Preconditions: Only observations 1–3 are included.

- Use normal UI experiments and persistent readback before making claims.

Browser evidence:

- `evidence/call-001-709a330b/obs-0003.html` — sha256 `18166c0aaf4b299a93bf9bd4ae057a95e3ba29654cb11265c999afa65dbff3c5`
- `evidence/call-002-a1ce73a3/obs-0006.html` — sha256 `9b386f686f733cad013250d9d3603af3391bbca465a6d474c0c98dd29d1920dd`
