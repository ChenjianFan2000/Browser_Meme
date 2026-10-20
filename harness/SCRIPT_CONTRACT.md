# Direct Playwright script contract — protocol 2

This is site-independent infrastructure. The independent `gpt-6.1-sol` author
reads website source, writes the rulebook, predictions and native Playwright
scripts. The coordinator supplies this interface, executes artifacts and returns
evidence. It does not supply website answers or repair target selectors.

## Inputs

All paths below are explicit inputs; a run directory must not already exist.

- `site.json`: `site_id`, `base_url`, `allowed_hosts`, `source_roots`, `adapter`,
  `cases` (repository-relative path), and optionally `runtime_env` containing
  non-secret environment configuration. The adapter independently exports
  `reset(case)`, `observe()` and `evaluate(case, before, after)`.
- `cases.json`: an ordered array of fixed public `{id, goal, parameters}` tasks.
- `rules.json`: an array of rules with unique `id`, `statement`, `source_refs`,
  `preconditions`, `branches`, `forbidden_side_effects`, `status`.
- `plan.json`: `{schema_version: 2, revision, model: "gpt-6.1-sol", readouts: {},
  cases: [...]}`. Each case copies the fixed `id`, `goal`, `parameters` exactly
  and adds ordered `steps`. Each step contains unique `id`, `rule_ids`, `action`
  (a human-readable description or object), nonempty `expect` branches and
  optional `invariants`. Each branch is `{id, checks: [...]}`.
- `scripts.py`: exposes `run(case, h)`. The author implements each task using
  `h.page`, a real synchronous `playwright.sync_api.Page`. It must not use
  agent-browser, numbered element refs, API writes or backend access.
  The `case` argument is a detached copy of the frozen public plan case, including
  its `steps`. Independent adapter calls receive only `id`, `goal`, `parameters`.

Checks use the existing generic predicate vocabulary in `harness/checks.py`:
`{path: "after.ui.text", op: "contains", value: "..."}` or
`{path: "after.backend.table_hashes", op: "eq",
value_from: "before.backend.table_hashes"}`. Comparisons within a step use that
step's before/after observations. Supported operators are defined in
`harness/contract.py`; `readouts` retain its selector/text/value/count/visible/
checked/attr format. Playwright selector syntax is accepted directly.

Backend observations are available to the independent monitor, not returned to
the task script. The author may use the public adapter schema to express checks.
An evaluator never receives the model plan or predictions. The script has no
privileged reset or evaluation entry point.

An independent adapter may also export `observe_ui(page)` for read-only sampling.
Its output is saved as `independent_ui`, separate from the model's declared
readouts. Final `after.history` contains ordered `{step_id, before, after}` actual
observations for independent trajectory checks. It contains no model predictions.

## Script interface

```python
def run(case, h):
    # Plan contains this step and its expectation before execution starts.
    with h.step("open_form"):
        h.page.goto(h.base_url + "/example", wait_until="domcontentloaded")
        h.page.get_by_label("Name").wait_for(state="visible")
    with h.step("fill_name"):
        target = h.page.get_by_label("Name")
        h.confirm(target)
        target.fill(case["parameters"]["name"])
    with h.step("submit"):
        target = h.page.get_by_role("button", name="Save", exact=True)
        h.confirm(target)
        target.click()
        # Wait for an independently observable completion condition. Do not
        # retry until model checks pass or hide an unexpected business result.
        h.page.get_by_role("status").wait_for(state="visible")
```

- `h.base_url`, `h.page`, `h.case`: ordinary public execution context.
- `h.step(id)`: context manager; enforces fixed step order and writes/fsyncs the
  prediction before yielding. On exit it records raw UI evidence, a screenshot,
  network evidence and independent backend observation, evaluates the declared
  branches/invariants, and stops on contradiction or inability to confirm.
- `h.confirm(locator)`: records the locator and matching count, requires exactly
  one element, scrolls it into view, checks visibility/enabled state, and records
  the element's DOM attributes and bounding box. It returns the locator.
- `h.read_ui()`: returns the current raw DOM/text/readouts without backend state.
  Additional read-only DOM queries and native Playwright locators are allowed.

Use one business UI action per step. Confirmation/scrolling and waits may be
within the same step. Navigation has no DOM scroll target. Use explicit bounded
waits, not a fixed sleep. Do not use `force=True`, DOM mutation via evaluate,
request routing to fake success, or direct fetch/API writes for business actions.
Read-only `page.evaluate` is permitted. Source-visible investigation may inspect
client scripts, but task actions must pass through the website UI.

The generic Harness observes HTTP method/status/content type and sanitized
request/response JSON, including browser-origin API traffic. SSR backend calls
are not automatically browser-visible and must be distinguished from observed
browser requests. `after.ui.network` is the cumulative browser record;
`after.ui.step_network` includes entries observed during this step. Tokens,
cookies, auth headers and password fields are redacted. Full DOM snapshots and
Playwright traces are saved, with credential redaction documented.

Screenshots at step boundaries mask password/secret/token input controls.
Trace recording uses DOM/action/network snapshots without its unmasked screencast;
the masked PNGs are separate evidence. Known credential fields, observed auth
JSON values, cookies and JWTs are redacted. If a future script uses private
environment credentials, name those variables in `HARNESS_REDACT_ENV_NAMES`
so values can be registered in memory before execution. This is a scoped
redaction policy, not a guarantee against arbitrary unknown secrets on a page.
The script receives a UI facade, without public backend/initial/history fields.
This is a trusted-code API convention, not protection against Python reflection
or filesystem access; no forced backend isolation is claimed in this phase.

## Revisions and evidence

Each execution snapshots inputs, website source hashes, adapter and Harness
hashes. No artifact may change during a run. Source-backed claims are not
automatically marked browser-verified. Network, backend and UI evidence are
different channels.

A repair writes a new directory and `diagnosis.json`: parent revision, failure
category (`locator`, `timing`, `implementation`, `business_rule`,
`unconfirmed`), evidence paths, changed rules/steps and rationale. Preserve fixed
tasks, steps, branches and checks. Prediction changes require business evidence.
Generic Harness defects are repaired by the coordinator and recorded separately.

This phase is source-visible, with trusted local Python scripts. Process/context
separation is not an OS sandbox. It must not be reused to claim phase-two
isolation. Website credentials are public local fixtures, never real accounts.
