# 第二阶段后续管理工具

工作目录为仓库根目录 `G:\Browser_Meme`。这些文件只处理调度、证据和报告；网站规则、选择器、预测模型、任务脚本与独立真值由指定的独立实验模型/评估上下文负责。

原 `FORMAL_SCHEDULE.json`、73 项正式输入及早期运行保持冻结。管理变更以 `PROTOCOL-004.md`、`PROTOCOL-005.md` 和独立扩容登记另记，不能用“旧文件未变”代替实际入口版本登记。

## 调度

| 文件 | 职责 |
| --- | --- |
| `run_expanded_case_v001.py` | 验证扩容登记，绑定新管理 driver 及原独立事件函数，复用冻结逐例执行流程 |
| `run_parallel_v001.py` | 固定 180 例的独占队列、已封存例校验、双宿主内存门槛、失败停派与在途自然结案 |
| `run_parallel_v002.py` | 在 v001 上增加领取案例前的全部登记前后端 TCP 存活检查；实际入口必须单独哈希绑定 |

同一时刻只运行一个队列控制器。恢复前必须确认上一批已结束、在途案例均封存且 `safe_to_reset` 为真；任何真实部分运行目录需显式处理，不能删除后重跑。新的批次编号必须未使用。`STOP_DISPATCH` 仅阻止新领取，不打断在途案例。

当前六实例登记为 `harness/experiments/phase2-discogs-20261021-01/EXPANSION_SCHEDULE-002.json`。它授权 a..f、最多六个并行案例，不能用于 g..l 或十二路派发。站点 readiness 是带时间的验收记录，不代表当前服务仍存活。

## 报告与交接

| 模块 | 输入及输出范围 |
| --- | --- |
| `report_v002` | 校验案例 manifest，汇总固定 180 例、540 个预测字段；未完成项保留 |
| `review_learning_v002` | 学习包结构、语法、真实动作证据与冻结绑定；不把结构检查当作业务正确性 |
| `validity_report_v001` | 绑定最终独立审查，保留原分母并另列合规配对敏感性视图 |
| `handoff_v003` | 仅输出已准入冻结包和公共学习证据的哈希白名单，另列隔离包；不启动第三阶段 |
| `execution_context_v001` | 调度归属、跨批次重复/重叠检查、模型服务错误及资源样本；不改分数 |
| `evidence_index_v001` | 生成一例可回查的完整规则、脚本、预测、动作、截图与轨迹索引；不按成功分数挑选 |
| `plot_results_v001` | 从完整原始汇总和合规报告生成 PNG/PDF 与来源哈希 |
| `render_report_v001` | 从完成的机器报告、独立审查及交接索引生成中文报告与来源记录 |
| `render_report_v002` | 沿用 v001 绑定与输出，明确资源故障的发现／恢复时点，避免推断未知的确切退出时刻；正式中文报告使用本版本 |
| `report_lineage_v001` | 核对精确命名引用与 180/540 分母，复核独立准入链，并绑定图表、证据索引及完整真值归档 |

一般管理工具使用 Python 标准库；验证使用 pytest；图表工具额外使用本机已有的 matplotlib，不升级实验环境依赖。每个 CLI 的参数可通过 `python -m harness.phase2.<模块> --help` 查看。输出为独占创建，重算时使用新输出名称，禁止覆盖冻结报告。

`run_parallel_v002` 在显示帮助前也校验登记，因此其 `--help` 需要同时指定 `--expansion-registration`。

最终报告的必要顺序：180 例封存 → 原始汇总 → 独立真值归档及最终审查 → 合规报告 → 第三阶段交接 → 完整证据索引、执行上下文、图表和中文报告。仅准备工具或启动任务不能记为该阶段已完成。

真值归档工具由独立评估方维护，位于实验目录的 `private/phase3/archive_evaluation_truth_v001.py`。只允许读取明确列出的实际 worker runtime；不能归档 `codex-home`、认证配置或其他凭据。私有评估资料不进入交接白名单。

最终独立审核以 `truth_archive_index: {path, sha256}` 精确绑定真值归档索引，路径相对实验根。中文报告显式接收 `--deviations`，并验证传入学习审查、独立审核、真值索引、图表及证据索引属于同一组最终结果。

## 通用管理测试

```powershell
python -m pytest harness/tests/test_phase2_parallel_v001.py harness/tests/test_phase2_live_dispatch_v002.py harness/tests/test_phase2_execution_context_v001.py -q
python -m pytest harness/tests/test_phase2_report_lineage_v001.py -q
```

这些测试验证队列、冻结绑定、失败停派、服务存活和统计分母；不能替代真实网站 UI、业务真值或操作系统隔离验收。完整历史证据以各批次 manifest、独立 gate 和报告来源记录为准。
