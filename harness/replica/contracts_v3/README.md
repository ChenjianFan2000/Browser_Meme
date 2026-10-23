# Repeated components with complete DOM and AX coverage

Version 3 permits a preregistered zero-to-many component shape and adds exact
cross-source identity coverage. See [the schema](README.schema.md). Empty lists
require a separately selected, nonempty container anchor. No child checks are
invented for zero items: the result records zero evaluated instances and explicit
`not_applicable` checks. A known nonempty list still uses a positive minimum.

`same_dom_set` compares DOM node IDs with captured AX `backend_dom_id` mappings,
requiring both selected collections to cover the same identities. It does not pair
nodes by position. Missing AX rows and wrong resolved mappings fail; unresolved
mappings are unknown. Both outcomes stop the native worker at its live barrier.

```python
from harness.replica.contracts_v3.runner import run_source
result = run_source(source_plan, script_path, out, contracts_path, **existing_options)
```

New bundles/contracts use `/v3`. Frozen `/v1` and `/v2` bundles are accepted without
changing their contract or prediction content; their exact respective validator
versions are copied and loaded from the new run's frozen extension directory.
The controller reuses the v2 bounded completion policy and unchanged v8 worker.
The default completion allowance is 45 seconds, capped by remaining total wall
budget. Nonzero exit status remains a failed completion.

Each run freezes the extension before import and records its manifest alongside
the original bundle. This is an explicit new controller revision; earlier runs,
manifests and results remain unchanged. Observed list contents and local bindings
remain separate from structural prior predictions.
