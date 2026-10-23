# Component contract controller v1

This is a separate single-source experiment. It reuses the immutable v8 browser worker,
namespace, checkpoint barriers, process guard, and operation lease. The old paired
replica controller and all historical runs remain unchanged. This implementation does
not generate or claim a complete blind replica of a website.

The independent author writes a frozen contract bundle and native Playwright script.
Before each native UI action, `h.expect` includes `disposition`, `contract_ref`,
`branch`, `parameters`, and `unknown_slots`; see [the schema](README.schema.md).
The existing worker persists that prediction before the operation and blocks at its
post-action checkpoint. The new controller compares the persisted before/after
predictions, checks captured structure and scoped relations, and invokes a separate
truth adapter. Only a passing checkpoint receives `continue`; fail, unknown,
incomplete capture, missing independent truth, or missing coverage receives `stop`.
No suffix is run by the controller after that decision.

The generic projection uses the worker's existing canonical DOM and native Chromium
AX capture. AX nodes have `source: ax`, `role`, `name`, `properties`, `id`, `parent`,
`identity` and optional `description`, `value`, `ignored`, `backend_dom_id`. DOM nodes
have `source: dom`, `tag`, `attributes`, captured live `properties`, `id`, `parent`,
`identity`, and optional `text`/`urls`. Unavailable properties are not inferred.
Structural prediction scoring and binding observed external values are separate.
Bindings are written as a new observation update; they never rewrite a prediction.

Python entry point from the repository root:

```python
from harness.replica.contracts_v1.runner import run_source
result = run_source(source_plan, script_path, output_directory, contracts_path,
                    modules=(), policy=policy, oracle=independent_adapter,
                    case_ref=private_case_ref, state0_prediction=initial,
                    final_prediction=final)
```

`source_plan` uses the existing origin/upstream_host/upstream_port/public_fixture and
optional init_script fields. The default runtime is
`harness/replica/runtime_versions/evaluation-playwright-semantics-v8`. The controller
freezes and hashes runtime, script, modules, contracts, and controller dependencies.
`policy.lease_directory` selects a shared existing operation lease directory; absent
this option, sibling runs share `browser-operation-lease` in their parent directory.
The coordinator must also honor its experiment-wide browser slot.

The independent adapter keeps the existing interface:

- `describe()` explicitly returns `independent: true`.
- `prepare('source', case_ref)` returns `initial_equivalence: pass` and a reset receipt.
- `capture('source', case_ref, checkpoint)` returns confirmed status, facts, logical
  identities, nonempty complete coverage and evidence references.
- `assess(case_ref, checkpoint, previous, current, action)` returns a verdict,
  nonempty checks and evidence references. False/unknown check results cannot pass.

Checks and coverage require explicit `true`, `"pass"`, or `"confirmed"` leaves.
Check records may use `pass`, `passed`, `complete`, `status`, or `verdict` markers;
each supplied marker must explicitly pass. Only `id`, `name`, `label`, `reason`,
`message`, `detail`, `expected`, `actual`, and `evidence_refs` are metadata. Other
fields are recursively treated as checks. Thus `{"pass":true,"side_effect_safe":false}`
is unconfirmed, as are zero, empty containers, unknown strings, and absent checks.

The total wall budget begins at `run_source` entry, including preflight and reset.
Independent callbacks run in a persistent management process, with a default
15 second per-call bound (`policy.oracle_call_seconds`, positive and at most 25).
The existing runtime subreaper cleans this process and its descendants on timeout;
`oracle-cleanup.json` records the separate receipt. Adapter state persists between
callbacks in that process; facts must come from external storage or services rather
than mutable Python objects shared with the parent. An unconfirmed preparation
never launches a browser. Generic code modified since controller import is rejected:
start a fresh controller process after edits, then keep code fixed for the run.

Checkpoint context contains `kind`, `action`, `case_ref`, `lane`, raw `record`, the
projected `observation`, and the same source-keyed observations/evidence_directories/
private_trees_directories maps as the paired controller. No private adapter or facts
are sent into the worker. `state0_prediction` and `final_prediction` are mandatory
preregistered predictions; they are checked at their actual synchronous barriers.

Artifacts include `registration.json`, `frozen/`, `source/job/evidence/`,
`source/barrier/`, `checks/<checkpoint>/`, `progress.jsonl`, `status.json`,
`source/cleanup.json`, and `result.json`. Each check retains the prior commitment,
validation, independent truth, observation update, and release decision. The final
result is a measured live-gate result only when all required checkpoints, the worker
completion, action coverage, and verified cleanup pass.

Offline symbolic export and generic verification:

```bash
python -m harness.replica.contracts_v1 render --contracts BUNDLE.json --ref CONTRACT --inputs INPUT.json --branch BRANCH --out NEW-OUTPUT.json
work/audit-20261022/test-env/bin/python -m pytest harness/replica/contracts_v1/tests -q
```

`python -m harness.replica.contracts_v1 run --config CONFIG.json` accepts the same
named arguments as `run_source`; `source_plan` may be an object or JSON path. The
optional `oracle` configuration is `{"module":"private.adapter","factory":"create","kwargs":{}}`.
Use absolute input/output paths. The adapter remains management-only. A registered
`needs_reading` terminal observation can be assessed by the oracle and retained as
a partial stop; it is not counted as complete script execution.
