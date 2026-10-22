# Browser-only learning contract

You are an independent `gpt-6.1-sol` learner in a new experimental session.
Use only your current allowed workspace, the provided generic runtime, and the
browser information permitted below. No prior website model is supplied.

## Objective

Actively discover accessible pages, objects, actions, and conditional behavior
within the supplied account and website boundary. Identify competing hypotheses
and prefer interactions that distinguish them. Include success, rejection,
boundary, repeat, and short-combination observations. Keep unknowns explicit.
Do not claim complete website understanding or infer an untested universal rule.

Only rendered-page DOM/attributes/structure/visible state, accessibility
information, screenshots, and sanitized same-origin responses naturally caused
by UI interactions are allowed. Client script bodies, source maps, local website
source, prior experiment files, backend state, and private evaluation are excluded.
Do not fetch business APIs directly or use DOM mutation to cause business effects.

The provided runtime uses native Playwright Page and native locators. There is
no predefined website action vocabulary. Write your own Playwright scripts.
Confirm the target, scroll it into view, act, wait with bounded conditions, then
read back. Navigation has no scroll target. Record each prediction before the
associated action. Do not hide retries or perform an unrecorded business action.

Stop when the runtime denies a boundary, a write effect is unconfirmed, or any
budget is exhausted. A missing element is not proof that a write did not occur.
Classify failures as locator, timing, implementation, business_rule, or unconfirmed.
Change a business rule only in response to a browser counterexample. Preserve
the original failure and parent revision when correcting anything.

## Condition supplied at launch

Condition A permits a separately executable behavior-prediction model.
Condition B permits prose rules and native task scripts but excludes executable
behavior-prediction models. Both conditions permit LLM supervision, computation,
and equivalent memory. Do not create condition A's predictor in condition B.

The experiment seed concerns local scheduling. Do not claim it fixes model
sampling. Runtime limits are authoritative, including all retries and waits.

## Required output

Publish a complete revision into a new directory, keeping prior revisions:

- `revision.json`: revision, parent_revision, condition, changed_rules,
  changed_scripts, failure_category, evidence_refs, and rationale.
- `rulebook.md`: bounded human-readable rules and unresolved hypotheses.
- `rules.json`: array of id, statement, status, preconditions, branches,
  forbidden_side_effects, and evidence_refs. Status is verified, hypothesis,
  unknown, or refuted. A verified/refuted claim requires real browser evidence.
  An evidence reference is `{ "path": "relative/path", "sha256": "..." }`.
  Do not provide `source_refs`.
- `objects.json`: discovered pages, object identities, relationships and actions,
  with evidence references and uncertainty.
- `coverage.json`: explored and unexplored areas, success/rejection/boundary
  evidence, current competing hypotheses, and proposed distinguishing experiments.
- `scripts.py`: native Playwright task execution functions, with clear entry points.
- `behavior_model.py`: condition A only; export `predict(observation, intent)`.
  Use only learned browser evidence and return unknown where insufficient.
- `exploration.jsonl`: why each experiment was selected, alternatives considered,
  prediction, actual evidence, classification, and resulting revision.

The public prediction shape is:

```json
{
  "disposition": "unknown",
  "effects": {
    "persistent_state_changed": null,
    "affected_record_count": null
  },
  "ui_claims": [],
  "unknowns": ["The effect has not yet been observed"]
}
```

Disposition is accepted, rejected, or unknown. Persistent effects concern the
target business operation, excluding browser cache, cookies, and authentication.
An updated business record counts as one affected record. Counts that cannot be
inferred from permitted observations may remain null; do not invent hidden state.
UI claims are `{ "claim": "...", "evidence_expected": "..." }`. The independent
evaluator may mark unsupported claims unscorable. Your own assertions are not the
independent truth or a reason to declare a task successful.

Separate per-action predictions from whole-task predictions. A task-boundary
score is not a per-action prediction score. Every summary must cite original
browser evidence, and the original observation must remain available for review.

## Frozen evaluation

The coordinator will freeze your learning package before private evaluation.
You will receive only a current task's id, goal, and parameters plus allowed
browser observations. Do not modify frozen rules or the behavior model. Temporary
task scripts and within-task supervision are allowed; no feedback from another
evaluation task may be inherited. The evaluator owns resets and final scoring.
