# Restricted Release CLI

This tool is limited to `ChenjianFan2000/Browser_Meme`, public visibility, exact account `ChenjianFan2000`, and existing push/admin permissions. It does not change visibility or log in. The implementation and tests do not execute publication themselves.

From repository root:

```powershell
python harness/publication/phase2_20261022/github_release.py --plan <asset-plan.json> --registration <new-registration.json> prepare
python harness/publication/phase2_20261022/github_release.py --plan <asset-plan.json> --registration <same-registration.json> upload
python harness/publication/phase2_20261022/github_release.py --plan <asset-plan.json> --registration <same-registration.json> verify
python harness/publication/phase2_20261022/github_release.py --plan <asset-plan.json> --registration <same-registration.json> publish
```

Plan fields: `repository`, `tag`, `target_commit` (full 40-character SHA), `body_path`, `assets:[{path,name,size,sha256}]`. File paths resolve relative to the plan. Other approval/export-manifest/review binding fields remain in the plan and are covered by its original-byte SHA. The upstream export gate owns approval of those fields and publication content; this CLI verifies release identity and asset bytes, not redaction sufficiency. Keep the plan immutable and exclusively owned. Each asset must be less than 2 GiB; names are unique safe ASCII names. No command replaces existing assets.

`prepare` verifies the exact authenticated account, public repo, permissions, commit/tag and no release with this tag, hashes all local assets, creates a draft, then exclusively writes safe registration. Only that registration can resume. A lost draft-creation response is not retried or adopted: retain its journal and reconcile manually. Never delete a possible newly created draft merely because registration is absent.

`upload` streams open file objects using at most four threads. Existing uploaded assets must match name, size, uploaded state and GitHub SHA256 digest. If GitHub omits its digest, the tool streams the download and hashes it; redirects are restricted to GitHub asset hosts and do not forward bearer headers. It fails on unknown or conflicting assets. POST is never retried; a lost upload response triggers read-only asset reconciliation, which accepts only a complete exact matching object.

An explicit `upload --recover-owned-failed` may delete and recreate only a starter/failed asset whose numeric ID was previously recorded by this tool from a successful upload response in this registration's journal. Ambiguous partial objects without that ownership receipt are never deleted or adopted. Journals are append-only, thread-safe and contain only allowlisted safe fields. They are not credentials and must remain beside registration for recovery.

`verify` is read-only. `publish` revalidates all local/remote assets and exact binding while still draft, patches draft false, then revalidates the published result. A lost PATCH response is not retried; use verify to learn actual state. Exact commit/tag means no moving an existing tag.

Authentication invokes `git credential fill` with HTTPS GitHub and the fixed username, `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`. Credential helper output and bearer header exist only in memory; no token is put in argv, files, logs or environment. Do not add HTTP debug logging. Errors contain only type, endpoint without query and status; response bodies/headers and raw exceptions are suppressed.

Mock validation:

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_github_release.py -v
```

Ten tests passed. They cover concurrent upload/resume/publish, local/plan tamper, account/repo/visibility guards, existing release, remote digest mismatch, missing-digest download hashing, lost POST response reconciliation, unknown/unowned asset refusal, explicit owned partial recovery, and GET-only retry/error secrecy. No credential helper or real network is called by the tests.
