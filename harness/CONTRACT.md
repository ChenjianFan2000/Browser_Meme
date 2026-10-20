# Phase 1 Harness contract, MVP v1

This is infrastructure, not a website answer. The target-specific source package,
adapter, rulebook, scripts, predictions and repairs are authored by independent
`gpt-6.1-sol` subagents. The coordinator may fix generic infrastructure only.

## Roles and artifacts

- Deployment/evaluation model: choose an existing complete site; preserve its
  upstream source; supply isolated runtime, reset and independent backend
  observation/evaluation under `harness/sites/<site>/`.
- Experiment model: inspect the complete permitted target source and adapter
  public schema. Produce `bundle.json`; later repairs create a new version.
- Harness: validate/freeze inputs, record predictions before actions, execute UI,
  collect actual UI/backend evidence, classify outcomes, request diagnosis,
  and compare regressions before activating a revision.
- All model work is conducted through independent subagents in this session.
  File handoffs are reusable transport, not an unattended model API integration.
  A fresh subagent context is not an OS-enforced filesystem sandbox.

## Site configuration and adapter

`site.json` has `site_id`, `base_url`, `source_roots` (repository-relative paths),
`adapter` (repository-relative Python file), `allowed_hosts` (loopback only),
`description`, and optionally `start_command` / `working_directory`.
The supervised `python -m harness.launch` entry additionally consumes trusted
`setup_argv` and `start_argv` argument arrays with `shell=False`. Display-only
`setup_command` / `start_command` strings are not evaluated as shell code.
`health_urls`, if supplied, must be local HTTP endpoints; otherwise readiness
uses `base_url`. The launcher sets a unique `HARNESS_STOP_FILE`: the deployment
supervisor must notice that file, exit normally, and clean up only its children.
Source and business state must not be written into the frozen input directory.

`preflight` performs discovery only unless `--smoke` is explicit. It never
imports the target evaluator or resets business state. The supervised launcher
requires the generic real-browser smoke to pass before it dispatches any target
task. Discovery, component checks, and browser smoke are not target-site scores.

The trusted, independently authored adapter exports:

```python
def reset(case: dict) -> dict:
    """Reset only this experiment's isolated data; return setup evidence."""

def observe() -> dict:
    """Read actual backend state without changing it. JSON serializable."""

def evaluate(case: dict, before: dict, after: dict) -> list[dict]:
    """Independent final checks: [{id, passed: bool, detail}]."""
```

`case` passed to the adapter contains only `id`, `goal`, and `parameters`, never
the experiment model's predicted branches or checks. `before` / `after` contain
`ui` and `backend`. Final checks must inspect actual state independently of the
model. Publish the observation schema and reset semantics in `adapter_contract.md`
for the experiment model. Do not implement evaluator truth by loading its bundle.
If data is inaccessible or reset fails, raise an error; never invent success.

## Model output: bundle.json

Use UTF-8 JSON, no Markdown fences:

```json
{
  "schema_version": 1,
  "site_id": "<site>",
  "model": "gpt-6.1-sol",
  "revision": "v001",
  "rules": [
    {
      "id": "R1",
      "statement": "<source-supported behavior>",
      "source_refs": ["path/to/source.py:20"],
      "preconditions": ["<condition>"],
      "branches": ["<success>", "<refusal>"],
      "forbidden_side_effects": ["<what must remain unchanged>"],
      "status": "source_supported"
    }
  ],
  "readouts": {
    "field_name": {"kind": "text", "selector": "<CSS selector>"}
  },
  "cases": [
    {
      "id": "<stable case id>",
      "goal": "<independent, externally checkable business goal>",
      "parameters": {},
      "steps": [
        {
          "id": "<stable step id>",
          "rule_ids": ["R1"],
          "action": {"kind": "open", "url": "/"},
          "wait": {"kind": "selector", "value": "body"},
          "expect": [
            {
              "id": "expected_branch",
              "checks": [
                {"path": "after.ui.fields.field_name", "op": "contains", "value": "<text>"}
              ]
            }
          ],
          "invariants": [
            {"path": "after.backend.some_field", "op": "eq", "value_from": "before.backend.some_field"}
          ]
        }
      ]
    }
  ],
  "limitations": ["<uncovered features and assumptions>"]
}
```

Every case starts from adapter reset and a fresh browser session. Every step has
a nonempty `rule_ids`, an explicit `wait`, and at least one predicted branch with
at least one check. Use 6–8 meaningful cases for the MVP, including a composed
workflow, a refusal/validation branch, and an unchanged-state check. Keep the
total under 90 UI steps. Do not remove failed cases on repair.

Supported actions: `open` with relative or allowed local URL; `click`, `fill`,
`select`, `check`, `uncheck`, `hover`, `focus` with `selector`; `fill` / `select`
also have `value`; `press` has `key` and optional `selector`; `back`, `reload`.
Selectors are native CSS plus the supported element-text suffix
`:has-text("literal")`, not arbitrary agent-browser selectors or stale `@eN` refs.
The Harness confirms exactly one target, scrolls it into view, checks visibility,
performs the action, waits, and reads evidence. Use real UI actions; no API
mutation, JS clicks, or DOM rewrites in generated scripts.

Supported waits: `selector`, `text`, `url`, `load` with `value`. Prefer specific
conditions. `load` value is `domcontentloaded`, `load` or `networkidle`.
Readouts: `text`, `value`, `count`, `visible`, `checked`, `attr` (with `attribute`).
Missing optional readouts produce `null` plus an observation error. Common UI
fields are `url`, `title`, `text` (body text), `fields`, and `errors`.

Checks use dotted dictionary paths (numeric list indices supported) and:
`eq`, `ne`, `contains`, `not_contains`, `gt`, `gte`, `lt`, `lte`, `matches`,
`exists`, `in`. The right side is `value` or `value_from`. JSON types matter for
equality. Missing paths or unusable types are unknown, not pass. A branch with
all checks passing matches; all branches failing is a contradiction; incomplete
evidence is unconfirmed. Invariants are mandatory constraints across branches.
Expected refusal is a valid matched branch, not automatically a task failure.

## Diagnosis and repairs

On failure, consume the saved feedback packet. Classify each failure as
`locator`, `timing`, `implementation`, `business_rule`, or `unconfirmed` with
evidence references. Change business rules only for business counterexamples;
fix selectors/waits/runtime integration at the corresponding layer.
`infrastructure` failures are routed to Harness/deployment maintenance, with
`model_repair_allowed=false`; they do not authorize changing target rules.

Return a complete new bundle and `diagnosis.json` containing `parent_revision`,
`category`, `evidence`, `changed_rules`, `changed_steps`, and `rationale`.
Never overwrite the initial bundle, silently weaken checks, delete failed cases,
change goals, or change the evaluator to obtain a pass.

Initial MVP budget: one initial generation, up to two experiment-model repair
rounds; at most 90 steps per run, 30 seconds per browser command, 20 minutes per
run. Case order and goals are frozen before first execution. Infrastructure
retries are separately recorded. Regressions block activation of the repair.
Report first-run results separately from repaired results. Actual model tokens
and cost remain unavailable unless the runtime supplies them.

No dispatched UI actions means `measurement_status=not_started` with model/task
rates null. A dispatched action with a missing completion can still have changed
state and is a partial measurement. All planned actions completing is distinct
from all predictions and independent final goals passing.
