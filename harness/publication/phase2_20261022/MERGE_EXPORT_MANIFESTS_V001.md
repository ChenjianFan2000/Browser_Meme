# Metadata-only publication merge

No source payloads, credentials, websites or network are read by this tool. It hashes and parses only explicitly pinned inventory/manifest JSON inputs and writes a new directory. It does not approve publication, scan payloads or upload.

```powershell
python harness/publication/phase2_20261022/merge_export_manifests_v001.py --parent-inventory PARENT_INVENTORY SHA256 --parent-manifest BLOCKED_MANIFEST SHA256 --retry RETRY_INVENTORY SHA256 RETRY_PENDING SHA256 --supplement SUPPLEMENT_INVENTORY SHA256 SUPPLEMENT_PENDING SHA256 --output-directory NEW_DIRECTORY
```

Repeat `--retry` and `--supplement` as needed. Supplement is optional; every parent failure must be repaired exactly once. Both child manifests must be complete `exported_pending_independent_approval`, with no remaining failures and exact inventory SHA. Retry candidates must identify exact original failed source/archive/restore mappings; they cannot replace successful parent entries or exclude failures. Supplemental candidates must have entirely new original source/archive/restore identities. Parent and child original-hash bindings are enforced wherever registered. Every final included inventory candidate gains expected_original_sha256 equal to its unchanged complete manifest row's original_sha256. This strengthens the merged binding; it does not imply the old parent inventory had hashes it did not contain.

The parent partition (success/candidate exclusion/failure) must exactly cover its inventory. Parent success dictionaries remain unchanged, including arbitrary extra metadata, both hashes and source/export/restore paths. Parent exclusions are retained in their original order and content. Child exclusions may only repeat exact parent exclusions; no new exclusions are accepted. No old record is overwritten, deleted or marked resolved.

Outputs: inventory.merged.json, export-manifest.pending.json, audit-shard-01.pending.json through audit-shard-08.pending.json, and merge-summary.json. All lineage inputs and the merger code SHA are bound. Eight shards partition complete dictionaries and candidate exclusions; the actual independent check_union validates them against final pending and merged inventory. The merger never writes approved_for_publication. Pending still requires full independent audit and the upstream publication gate.

Use only a new output directory. Successful completion requires exit 0 plus merge-summary.json; if IO/input instability causes failure after partial new outputs, keep those outputs as an incomplete attempt and use another new directory. Do not adopt partial files as a completed merge. Inputs are rehashed before and after output writing. The original blocked manifest, all retry records and their original files remain untouched. Metadata validation is not a rehash of payload content; independent export audit and full-pack verification remain required.

Synthetic validation:

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_merge_export_manifests_v001.py -v
```
