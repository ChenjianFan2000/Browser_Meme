# 本次 Git 上传检查（2026-10-23）

## 范围

上传现有组件合同探索的精选交接包、通用复现 Harness 和测试；从当前版本移除旧 Discogs 第二阶段结果及生成发布清单。[当前研究状态](CURRENT_STATE_20261023.md)记录新方案及尚未同步的两份原件。未启动新实验，未修改冻结模型或版本化运行接口。

原始 `work/`、浏览器轨迹、私有 fixture、数据库和实站特权适配排除出 Git。通用源码的定向扫描覆盖 246 个文本文件，未命中所检查的私钥头、常见 GitHub/OpenAI/AWS token、凭据式 URL 或 JWT 模式；这不是完整凭据审计，也不证明没有任意格式的敏感值。交接包自己的复制、哈希、链接和模式检查见其 `VALIDATION.json`。

暂存后的相同模式检查覆盖全部 283 个新增或修改文本文件，零命中；没有超过 1 MiB 的新增／修改文件，也没有符号链接。凭据扫描只输出命中的文件路径和类型，不打印值。

本次修改的入口文档与交接包通过 `git diff --cached --check`。全量检查仍指出原有冻结运行时代码的 CRLF，以及两个 runner 文件的末尾空行；允许 CRLF 后仅剩后两项。为保留冻结字节和哈希，本次不做格式化清理，也不把全量检查记作零告警。

## 离线测试

在仓库根目录使用现有测试环境运行：

```bash
python -m pytest -q --import-mode=importlib \
  harness/replica/contracts_v1/tests \
  harness/replica/contracts_v2/tests \
  harness/replica/contracts_v3/tests \
  harness/tests/test_replica_runner.py \
  harness/tests/test_replica_trees.py
```

- 首次合并运行未使用 `--import-mode=importlib`，同名测试文件导致 collection 错误；加该选项后继续验证。
- 首次有效运行：134 passed、2 failed、7 skipped。
- 单独复跑 `contracts_v1/tests/test_oracle_process.py`：4 passed。
- 同一合并命令复跑：136 passed、7 skipped。
- 另两个纯 Playwright semantics 单测文件：18 passed、41 subtests passed。

两项首败涉及 50ms 总预算：一项准备阶段超时后未取得清理确认，控制器返回 `oracle_cleanup_unconfirmed`；另一项在首次 `describe()` 返回前耗尽预算。两项都未执行网站 UI 操作。

只读代码检查发现 oracle supervisor 启动后没有 ready 握手，父进程可能在子进程建立信号处理和清理保护前请求终止。首败与这一竞态及调度延迟一致，尚不能断言唯一原因。**复跑通过不等于稳定性问题已修复。** 冻结版本保持原字节，后续需在新版本中修订并验证启动／清理边界，不能仅放宽测试时限掩盖问题。

这些离线检查不是目标网站重放，也不是新 E/T/C 实验的成绩。浏览器及目标环境依赖未满足的测试保持 skipped，不解释为通过。
