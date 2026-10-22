# 公开归档的路径与校验

下载同一 Release 的全部 `volume-*.zip`、`volume-index.json`、`SHA256SUMS` 和 `approved-export-manifest.json`，按 [README](README.md) 的 `verify`、`restore` 命令校验并恢复到新目录。不要覆盖本机实验原件。

- `harness/...` 等研究文件按 `archive_path` 保留仓库相对位置。Git 中提供代码、报告和一个完整案例；其余逐例证据在分卷中。
- 原本位于 `.runtime/` 的部署及验收证据，在公开分卷中统一放在 `runtime-evidence/`。`approved-export-manifest.json` 中每项的 `original_source_path` 和 `restore_path` 记录原始位置。标准 `restore` 命令按 `archive_path` 解压，不会自动把这些文件搬回 `.runtime/`，也不会启动或重置站点。
- `export_sha256` 校验实际公开字节，`original_sha256` 标识本机封存原件。脱敏可能改变文件大小、ZIP 压缩结果及历史清单所引用的哈希；这是有记录的公开副本差异，不修改原始评分或实验结果。
- Release 中的审核清单和发布过程记录是独立附件。学习者的后续输入仍以阶段三交接白名单为准，不能把公开的评测私有材料加入学习者输入。

认证存储、依赖、缓存和运行数据库不属于本次公开结果文件，排除记录保留在清单中。分卷包含研究证据，不是整套运行环境的磁盘快照。
