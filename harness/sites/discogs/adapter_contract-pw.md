# Direct Playwright independent extension adapter

The original eight fixed cases and `evaluator.py` remain unchanged. The fixed
12 public extensions are `extension_cases.json`; `site-pw-extension.json` selects
`pw_evaluator.py`. Both site configurations set `BM_DISCOGS_RUNTIME` to the new
dedicated runtime, inheriting the separately hashed original seeded baseline.

`reset`, `observe`, and `evaluate` retain the original contract. The independent
adapter never reads model plans, rules or predictions. `observe_ui(page)` reads
DOM, consent localStorage, navigation timing and only auth-cookie presence. It
also installs a passive response listener restricted to local public auth,
account and cart paths, storing method/path/status without request or response
bodies, credentials, headers or token values. This sampling initiates no network
request and does not change UI or database state.

The Harness saves these observations under `independent_ui`. Final `after.history`
contains the ordered actual `{step_id,before,after}` observations. History is
required to establish intermediate behavior (two real adds, quantity/total before
removal, anonymous refusal before login, genre page before tracklist and consent
reload). Missing evidence fails the corresponding check; a final state alone
does not establish a workflow. Script authors receive no backend snapshot or
private evaluation result while executing a task.

Marketplace rows are independently derived from all baseline active listings,
exact filter equality, backend price/time ordering and the default 50-row limit.
Visible listing identifiers, conditions, origin, currency and exact prices are
checked. Other database tables and unrelated account rows must remain unchanged.
Equal price/time ties allow equivalent ordering because upstream SQL specifies no
total order for such rows.

The original seller UI search is expected to fail in the unmodified upstream:
`frontend/src/app/api/backend/[...path]/route.ts` drops query strings, while
`backend/app/api/catalog.py` requires `q` for `/search`. Retain its task and real
failure evidence; no API workaround or silent source patch is permitted.
