# Version 2 descendant and repeated component constraints

This extension adds `has` descendant predicates and `each` local child contracts.
See [the schema](README.schema.md). It retains native Playwright and the unchanged
v8 worker and v1 controller mechanisms. No target application rules are included.

```python
from harness.replica.contracts_v2.runner import run_source
result = run_source(source_plan, script_path, out, contracts_path, **same_v1_options)
```

New contracts use `component-contract-bundle/v2` and `component-contract/v2`.
Existing v1 bundles and predictions are accepted without changing contracts,
scripts, or model bytes: that lane uses a copied frozen v1 validator and reports
`contract_version: v1`. This allows a new engineering replay of bounded cleanup;
it does not rewrite any original result. Before execution,
the wrapper creates a new sibling `RUN-contract-extension-ID` directory, freezes
the extension and original bundle, hashes them, and imports the validator directly
from those frozen bytes. A private instance of the unchanged v1 controller uses
that validator; no v1 module globals or historical files are changed. The outer
bundle identifier is normalized only to satisfy the v1 bundle loader; the v2
contracts themselves are unchanged. Registration records this normalization and
the extension manifest before browser launch.

Each-parent bindings are namespaced per actual observed parent and scored after
observation. They never become exact prior predictions. Empty known lists require
an explicit empty branch; a positive repeated component cannot hide missing rows
with a zero lower bound. DOM and AX ancestry remain separate captured trees.

`policy.completion_cleanup_seconds` defaults to 45 seconds, bounded by the remaining
total run wall budget. Expiration still terminates the worker and fails completion;
a nonzero exit status is never converted into a pass.
