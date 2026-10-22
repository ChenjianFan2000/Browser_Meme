# 普通混合日志导出修复 v002

该版本是独立包装 `export_evidence_logtext_v002.py`，不修改 v001 导出器。父版本 SHA256 固定为 `fbbaea885afae45876d8f67e7b5aea298908e1b510d2a75c24d063857e001ec5`，不匹配时停止。

本次唯一已定位失败文件是普通 `.log`：34,153 字节、UTF-8、285 行，前 271 行为合法 JSON 对象，末 14 行为普通文本／片段，首个非 JSON 行为 272。只检查了编码、JSON 行格式与计数，没有输出正文、业务内容或可能凭据值。原处理按文件开头自动选择严格 JSON／JSONL，遇普通文本尾部即失败。

包装仅将 `.log` 作为混合 UTF-8 文本处理，保留父版本 JSON 片段解析、嵌入 JSON、Cookie／header、base64 和 token 脱敏。敏感值之外的字节、空白、行尾和转义保持不变；二进制及归档仍走原检查；`.json`、`.jsonl`、`.trace`、`.network` 仍走父版本严格格式策略。适用范围也包括 ZIP 中的 `.log`；本次实际重试只应包含明确失败项。

主协调者创建独立 retry inventory，保留原失败项源路径、原 archive_path 和原件 SHA，运行新目录：

```powershell
python harness/publication/phase2_20261022/export_evidence_logtext_v002.py export `
  --source-root G:\Browser_Meme `
  --inventory .runtime/publication-phase2-20261022/retry-inventory-logtext-001.json `
  --output-dir .runtime/publication-phase2-20261022/retry-logtext-001 --workers 1
```

不重跑全量，不修改原失败 manifest。新待审 manifest 中 `generator_sha256` 绑定包装版本，`parent_generator_sha256` 绑定未修改父版本；状态仍只有 pending／blocked。最终合并由协调者独立保持原始分母、失败历史和重试父子链，再交审计员；此工具不自动批准或发布。

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_export_logtext_v002.py -v
```

测试使用合成数据，覆盖 JSON 记录加普通尾部、方括号前缀、结构化片段与 header/token、严格格式不放宽、非敏感字节保持、二进制拒绝、嵌套归档和实际 CLI 的独立重试血缘。未把实际失败文件重新导出。
