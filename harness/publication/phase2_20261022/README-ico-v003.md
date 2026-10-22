# ICO 资源与混合日志导出包装 v003

独立新版本 `export_evidence_ico_v003.py`，不修改父导出器、v002、调度器或历史失败清单。它固定父导出器 SHA `fbbaea885afae45876d8f67e7b5aea298908e1b510d2a75c24d063857e001ec5` 与 mixed-log v002 SHA `788063e3ac8f9f26fd3b2cf611207951a223b49e3fa680c6030c5c5ed5e5464b`。

## 完整失败格式诊断

主 `exports-003-sharded` 的 768 个失败分为 766 个 trace ZIP 和两份 `.log`。对全部失败 ZIP 的成员头部检查，每个恰好有一个父版本未识别的非 UTF-8 ICO 成员，无第二种未识别签名。进一步对全部 766 个 ICO 只读结构校验及父版本整字节凭据形状检查：全部通过，payload 为同一 SHA；图标含三个 BITMAPINFOHEADER40／32bpp BI_RGB DIB 和一个 256px PNG。没有跳过任何实验 trace。

两份 `.log` 的字节 SHA 相同，均 34,153 字节、285 行：前 271 行合法 JSON 对象，后 14 行普通文本／片段；继续采用 v002 的混合日志分类。诊断未输出正文、图像像素或可能凭据值，也未将实际失败项重新导出。

完整只读诊断位于 `.runtime/publication-phase2-20261022/format-diagnosis-v003-001.json`（成员格式分类）及 `format-diagnosis-v003-002.json`（全部 ICO 结构校验与两份日志格式绑定）。旧主 manifest、探针 manifest 和源文件均保留。

## 新允许格式及不放宽的检查

- 新识别只作用于 `.ico` 或无扩展资源，并要求真实 ICO 头、有效目录与全部图像 payload。目录检查尺寸、类型、边界、无重叠、无遗漏和无尾部隐藏数据。
- DIB 只支持实际观察到的 BITMAPINFOHEADER40、32bpp、BI_RGB、双倍图标高度和匹配数据大小；其他变体明确失败。
- PNG 检查签名、IHDR／目录尺寸、合法位深／色型、每个 chunk 的边界和 CRC、IDAT zlib 流、有界解压及终止 IEND。
- ICO 验证后全部原字节仍经过父 `_binary_copy` 的敏感形状检查；命中则拒绝，绝不盲改二进制。验证通过保留原 ICO 字节和 SHA。
- ZIP 继续逐成员递归，内部 JSON、Cookie、header、token、base64 和其他文本照常扫描；不因图标存在跳过整个 ZIP。未变化成员 payload 保持字节相同；需要脱敏的 ZIP 容器可能重新压缩。
- `.json`、`.jsonl`、`.trace`、`.network` 的严格格式规则不改。未知二进制、伪造图标、损坏文本或损坏 ICO 不放行。base64 内 ICO 仍按父版本无法识别二进制的策略失败，不自动扩大该观察范围。

## 仅重试失败项

使用协调者已建立的 768 项 failed-only inventory；其路径与原 archive_path／expected_original_sha256 完整保留，SHA 为 `77273c42d172822195fc0360f27b4ad3d6b22962898021d35446176eeb7647bc`。

```powershell
python harness/publication/phase2_20261022/export_evidence_ico_v003.py sharded-export `
  --source-root G:\Browser_Meme `
  --inventory .runtime/publication-phase2-20261022/retry-inventory-001.json `
  --inventory-sha256 77273c42d172822195fc0360f27b4ad3d6b22962898021d35446176eeb7647bc `
  --output-dir .runtime/publication-phase2-20261022/retry-format-v003-001 `
  --shards 8 --jobs 8
```

该子命令调用未修改的 `run_shards(..., exporter=本包装文件)`，每个子进程仍 `--workers 1`。也可用普通 `export` 子命令对单个明确失败项重试。所有目录必须新建；本任务不重跑全量成功项。

每个子待审 manifest 的 `generator_sha256` 绑定 v003；`parent_generator_sha256` 绑定父导出器，`format_wrapper_parent_sha256` 绑定 v002。分片总 manifest 绑定 v003 SHA，并通过各子 manifest 路径／SHA保留完整父链。最终只能 pending／blocked；独立审计和原始分母下的历史／重试合并由协调者完成。工具不批准、不上传、不覆盖历史或冻结源。

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_export_ico_v003.py -v
```

合成测试验证 DIB／PNG 图标原字节、递归文本脱敏、二进制内凭据拒绝、伪造／截断／目录异常／CRC 异常拒绝、JSON 严格策略、混合日志兼容，以及 CLI 和两进程重试的哈希父链；不作为实际 768 项重试完成的声明。
