# Native Playwright supervision — protocol 3

Protocol 3 adds explicit independent evaluation and Solar intervention to
[SCRIPT_CONTRACT.md](SCRIPT_CONTRACT.md). The original protocol-2 inputs and
archived executions remain valid. No target business logic belongs in the Harness.

## Frozen plan and script

The model plan uses `schema_version: 3`. It contains:

```json
{
  "supervision": {
    "review_timeout_seconds": 240,
    "max_reviews_per_case": 3,
    "case_seconds": 900,
    "on_step_failure": "diagnose_and_stop"
  },
  "cases": [{
    "id": "public_fixed_case",
    "goal": "exact fixed public goal",
    "parameters": {},
    "checkpoints": [{
      "id": "before_commit",
      "before_step": "commit",
      "reason": "Explain which decision requires independent evaluation.",
      "required_readouts": []
    }],
    "steps": []
  }]
}
```

All checkpoints require a live `gpt-6.1-sol` review. The author chooses meaningful
task-specific gates and calls `h.checkpoint("before_commit")` immediately before
the associated `with h.step("commit"):`. The gate is outside an action step.
The Harness rejects dispatch if a required checkpoint is missing or denied.
Checkpoints and UI actions have separate denominators.

Use native Playwright throughout. Every UI action remains inside a predicted
step. Pure local calculations may occur between steps. Persist the public inputs,
candidate comparison and calculated result using `h.note(name, json_value)`;
this saves a detached, redacted evidence file without granting backend access.
Notes must not contain credentials.

A task script must stop for an unmet required condition. It must never silently
substitute a weaker goal, alter the website, perform API writes, or repeat a
non-idempotent write whose outcome is unknown. Failed actions and contradictions
trigger a diagnosis request and stop this run; repairs require a new frozen model
and run ID. A review cannot turn a failed step into success.

## Independent evaluator

The site adapter additionally provides:

```python
checkpoint(case, checkpoint_id, initial, current, history)
# -> {
#   "decision": "continue" | "stop" | "unknown",
#   "checks": [{"id": "...", "passed": True | False | None, "detail": "..."}],
#   "public_summary": "Only public, non-oracle feedback suitable for the UI agent."
# }
```

`case` contains only fixed `id`, `goal`, `parameters`; observations and history
are actual evidence, without model predictions. The evaluator receives no script
notes as an answer key. It derives its verdict independently. It performs no
business writes. The script sees neither backend data nor the evaluator object.

Continue requires a nonempty check list, every check exactly `True`, and
`decision == "continue"`. `False`, `None`, missing checks, evaluator exceptions,
missing channels or an unsupported decision cannot authorize a write.
Only the verdict, check IDs/booleans and `public_summary` enter the review packet.
Privileged observations and detailed oracle checks remain under the separate
`private-supervision/NN-id/` directory. The review packet directory contains only
public evidence. A gate may name `required_readouts` from the plan; missing or
erroneous required readouts block approval. Missing UI/backend channels, or a
missing independent UI channel when the adapter supplies one, also block approval.

After Solar's response, the Harness reobserves and reevaluates. The public
URL/text/fields, independent UI and backend observation must still match the
reviewed state. A changed state, missing evidence or failed recheck stops the
run; the earlier permission is not reusable.

## Live intervention files

Each case has numbered `interventions/NN-id/` directories. Before waiting,
the Harness flushes a public `request.json`, `ui.dom.json` and masked `ui.png`.
The request contains a unique request ID, trigger, pending step, public UI,
independent public verdict and public evidence paths. It excludes backend
snapshots and evaluator implementation.

The coordinator gives only this packet and public task/model artifacts to an
independent Solar reviewer. The reviewer writes a temporary JSON file, then
renames it to `decision.json` in the same directory. Required fields:

```json
{
  "request_id": "exact request ID",
  "request_sha256": "SHA256 of request.json bytes",
  "reviewer": "gpt-6.1-sol",
  "decision": "continue",
  "classification": "planned_review",
  "reason": "Evidence-based explanation",
  "evidence": ["request.json", "ui.dom.json", "ui.png"]
}
```

Allowed classifications: `planned_review`, `locator`, `timing`,
`implementation`, `business_rule`, `unconfirmed`. Allowed decisions: `continue`
or `stop`. Evidence references must resolve to existing files beneath that
intervention directory. Identity and hash fields bind a decision to one packet;
they are provenance checks, not cryptographic authentication or OS isolation.

The evaluator's `stop`/`unknown` cannot be overridden by Solar. Failure diagnosis
packets accept only `stop`; no in-place repair or automatic retry is performed.
Missing, malformed, stale or late decisions fail closed. Waiting is bounded and
included in total elapsed time. Review time is also recorded separately.
The coordinator never fabricates Solar's response.

## Budgets and evidence

Protocol 3 permits at most 900 seconds per case, including intervention waits;
the exact value must be in the frozen plan and CLI. Individual Playwright calls
remain limited to 30 seconds, and the suite to 1800 seconds. At most 3 reviews per
case, each at most 240 seconds. All task failures retain the fixed step denominator.

The request binds its DOM, PNG and copied public notes with individual SHA256
hashes. Grants are consumed once by the exact pending step, whose dispatch entry
performs another state and independent evaluation check.

Each checkpoint stores the request, independent initial/recheck evaluations,
Solar decision, hashes, elapsed review time and gate outcome. Final success
requires all planned UI steps matched, all required gates granted, and independent
final business checks passed. A generic monitor's tests cannot replace actual
website evaluation. No stage-two isolation or unseen-task generalization is
claimed by this source-visible supervised demonstration.

The external decision-file wait pumps the Playwright event loop in short
intervals; these intervals do not decide UI success. This follows the
[Playwright Python event-loop guidance](https://playwright.dev/python/docs/library#time-sleep-leads-to-outdated-state).
