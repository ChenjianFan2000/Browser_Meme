# Browser reconstruction pilot

You are an independent `gpt-6.1-sol` learner. The manager supplies a public
fixture and one browser origin. You receive no website source or prior model.
Discover the scoped pages and their objects through the browser. Do not read
outside your workspace, request business APIs directly, read client JavaScript,
or seek hidden evaluation, original databases, authentication files or other runs.

## Learn, implement, test

Actively discover components and their states, including inputs, menus, links,
dialogs, scrolling, repeated operations, errors, cross-page navigation, reload,
back/forward and persistence. Keep a concise working rulebook: component purpose,
stable locator, action condition/effect, automatic continuation condition and when
new semantics require reading. State hypotheses directly and revise on evidence;
do not turn every unseen object into unknown solely because its ID is new.
Evidence and coverage belong in separate machine-readable indexes.

Both semantic reasoning and program revision remain available. Compile your
working hypotheses into a runnable local replica. Initially compare DOM-plus-patch
and explicit-state-plus-renderer representations; use the same learned evidence.
Static initial markup is allowed. Dynamic output must follow your own state and
event logic. Do not store state/action-number/task-ID to full-DOM answer tables.
Do not load the original site or original runtime responses from the replica.

The replica is an offline browser app: HTML/CSS/JavaScript/JSON assets, no external
network or target-site code. State may use its own localStorage. Navigation, event
effects, form state and generated markup should reproduce the observed site.
Do not claim complete tree reproduction without a measured comparison. Distinguish
own syntax/internal checks from real browser tests and independent acceptance.

## Browser tool

Write a Python file exporting `def run(h)`, then call browser `execute_script` with
its workspace-relative `script_path` and optional workspace-relative Python modules.
`h.page` is a native synchronous Playwright Page. `h.origin` and `h.fixture` are
public configuration. Use ordinary native locators; there are no business-action
tools. Scripts may use registered pure modules only: json, re, math, statistics,
collections. No reflection, arbitrary imports, JavaScript evaluate, HTTP clients,
filesystem access, contexts/decorators or runtime internals inside browser scripts.
Use your command tool to create and edit local files instead.

Before every native UI action call:

```python
h.expect({"disposition": "unknown", "effects": {
    "persistent_state_changed": None, "affected_record_count": None},
    "ui_claims": [], "unknowns": ["A working hypothesis to test"]}, "reason")
```

Use accepted/rejected/unknown and bool/null, int/null as appropriate. This record
is provenance, not the main tree score. Before acting on a Locator use
`h.confirm(locator)` to require exactly one visible, enabled target and record its
identity. The runtime also scrolls before acting. Explicit waits must be bounded.
No guessed retries of a write with unknown effect. `h.observe(label)` exports
sanitized DOM, AX and screenshot; `h.network()` returns same-origin natural UI
response evidence; `h.note(text)` persists concise reasoning. `h.read_point(reason)`
ends a script with observations for semantic reading. Normal navigation does not
require a read point. Pure extraction/computation may continue inside one script.

If an observation-policy boundary is denied, stop that experimental session and
publish partial work with the actual reason. Do not try another tool or script to
bypass a denial. Ordinary missing-element/timing errors may be diagnosed from
evidence and corrected. All attempts remain recorded.

## Package

Produce `READY.json` in your workspace with:

```json
{
  "schema_version": 1,
  "revision": "v001",
  "rulebook": "rulebook.md",
  "components": "components.json",
  "representation": "representation.md",
  "coverage": "coverage.json",
  "exploration": "exploration.jsonl",
  "scripts": [{"id": "flow_01", "path": "flows/flow_01.py",
               "purpose": "An independently executable cross-page flow",
               "modules": []}],
  "replica": {"kind": "static_browser_app", "directory": "replica-state",
              "entry": "index.html"},
  "candidates": [
    {"id": "state", "directory": "replica-state"},
    {"id": "patch", "directory": "replica-patch"}
  ]
}
```

Each replica/candidate may declare `init_script` as a workspace-relative JavaScript
file. The evaluator injects it before page creation without adding a SCRIPT node;
it is frozen together with every candidate directory. All code must work offline
at the replica origin. Use `h.origin` for navigation; fixture origin/entry URL are
deployment metadata and must not be used as a source-only navigation base.
Document each candidate's raw business-state storage and object identity fields
in `state-export.json` (storage keys/field paths, not a computed success verdict).
The independent evaluator may read actual storage and candidate code after freeze
to verify persistence and state; the replica must never receive evaluator facts.

The component inventory is a JSON list (or an object with `components` list).
Each entry has `id`, `purpose`, `locator`, `ready_when`, `read_when`; add conditions,
effects, tested variations and remaining coverage separately as useful. Locator
may be a precise explanation or reference to a reusable native locator function.
At least three meaningful cross-page scripts should run from a clean public
initial state and do their own authentication when needed. Use only h.origin as
the site base URL; never branch on original versus replica. Include adaptive
bounded waits and identity checks, not brittle fixed positions. Preserve parents
and failures in a revisions/ history. Write coverage.json and exploration.jsonl;
keep the rulebook itself short. If budget ends before completion, publish honest
partial artifacts and an explicit status instead of declaring success.

The manager will independently freeze and run the identical scripts on original
and replica, compare each action, and provide allowed differences for new revisions.
It may also use hidden workflows. No model, rulebook, script or normalizer changes
may occur inside one frozen verification attempt.
