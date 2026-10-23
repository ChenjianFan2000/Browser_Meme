> 便携交接副本。原文：本轮 `METHOD-AUDIT-003.md`；原始 SHA-256：`e8c8edce50f2497c3bc1594a84fb072d2ac2fb0926cac187d6492232fc0cc46e`。本次仅追加本说明并转换交接链接：已发布材料指向包内或通用 Harness，未归档材料保留短来源标识；历史观察、代码示例、判断、失败与时间截点不改写。当前完整结果以 [发布汇总](../RESULTS.json) 和 [交接说明](../README.md) 为准。链接到汇总仅表示保留了摘录，不等于原始证据已公开。

# 通用方法审查 003：可空重复组件与 DOM/AX 身份集合

审查者：`contract_method_audit`。时间：2026-10-23 04:29–04:36 UTC。依据为 REPRESENTATION-EXPLORATION-004.json（本地历史引用，未随精选包归档；来源：`REPRESENTATION-EXPLORATION-004.json`）、v2 README/冻结清单及 HARNESS-V3-MANIFEST-001.json（本地历史引用，未随精选包归档；来源：`HARNESS-V3-MANIFEST-001.json`）。本次没有读取目标网站源码、目标模型、消费者答案或业务 oracle，没有启动浏览器，没有修改 v1/v2/v3 源码；本文件不改写 METHOD-AUDIT-001。

**结论：在本次检查的通用范围内，未发现阻断 v3 试用的新问题。** 零父项没有产生子项通过数；缺失 AX 行会被 DOM/AX 双向集合关系发现；重复或未解析桥身份为 unknown；后验槽依赖传播到子检查和身份关系。通用正反 live 证据支持这些路径确实接入动作门。此结论不确认目标模型正确、目标任务成功或 source oracle 的业务充分性，也不将新适应结果计入首次生成成绩。

## 冻结与证据范围

- 审查先读取协议和 v2 文档，收到实现者明确停止修改后才读取 v3 源码。提出“多个 AX 节点映射同一 DOM 是否被 set 去重掩盖”的预审问题；最终冻结版本已保守返回 `ambiguous_duplicate_DOM_identity`，本审查独立复核。
- v1 对照 HARNESS-MANIFEST-002 的 13 个文件、v2 对照 HARNESS-V2-MANIFEST-001 的 10 个文件，逐文件 SHA-256 全部一致；v3 对照新清单的 9 个文件也全部一致。
- v3 清单摘要为 `0a37a19413e34f2c0c8b02e3edde8f18bec6475c4f93fb40f09b34fcb6c1926c`。schema/validator 摘要分别为 `a8634de2cfb1148bcbd6efd10a0c834b0be0bca8602a18dc1423138b727a017a`、`e9b0fe0ed6f48dfac954a0acd85654b17c8943dd3ef57010040799b2fd43116b`。
- 已读取 offline-v3-controls-001.txt（本地历史引用，未随精选包归档；来源：`offline-v3-controls-001.txt`）：`27 passed in 0.16s`，包括 24 个验证器控制与 3 个版本兼容控制。本审查未重复整套测试；下表来自另外实际执行的小型内存控制。
- 已读取两次通用 live 的 result、registration、逐步合同判定、release 和 cleanup receipt；每次 extension 的 8 个存档文件哈希均匹配，registration 与 result 指向的 extension manifest 摘要均匹配。其 frozen base controller 与冻结 v1 相比，只有登记的两处替换：完成等待上限，以及复制 v1 源码的显式路径。

## 独立执行的内存控制

从仓库根以 `PYTHONDONTWRITEBYTECODE=1 work/audit-20261022/test-env/bin/python` 导入通用 fixture 和函数，内存中修改合同或观察，没有运行网站或写入新测试实现。

| 控制 | 实际结果 |
| --- | --- |
| 同一预先声明结构，父项数 0、1、3 | 均 pass；evaluated_instances 分别为 0、1、3 |
| 0 项分数 | prior `passed=4, not_applicable=1, total=5`；binding passed=0；child_passes=0，没有任何 `dom_rows[父id]/...` 检查 |
| DOM 有 2 行，AX 的 has 只留下 1 行 | fail；`same_dom_set` 为 `DOM_identity_set_contradiction` |
| 额外 AX 行映射到已有同一 DOM 行 | unknown；`ambiguous_duplicate_DOM_identity` |
| AX backend_dom_id 缺失、`f0/dom-unresolved/99`、不在 canonical map 的路径 | 均 unknown；分别明确未解析或映射不存在 |
| 槽用于 has、槽用于 scope、由 AX 观察绑定槽再选择 DOM 容器 | 三组均可 pass；对应 each 子检查与 same_dom_set 全部归入 observation_binding，prior 仅保留 2 个独立检查 |
| bundle schema 为 v999、误用 contract schema、空串、null | normalize_bundle 均抛 ValueError |
| contract schema 为 v999 | unknown，不能放行 |
| 总 wall=300、cleanup=45，剩余 wall 为 20 | completion_deadline 截断到剩余 20；余时充足时为 45 |

零项时的 4 个先验 pass 是容器、两侧集合数量约束及集合相等的检查，不是 4 个子项通过。`prediction_score.total` 包括 N/A，不能当作“已适用检查数”；`evaluation_instances.child_passes` 在非空情况下还可能包含观察绑定检查，不能直接替代 prediction_score。接口提供了分账字段，报告必须使用它们。

## 对已完成通用 live 的只读核验

证据目录：generic-v3-live-controls-001（本地历史引用，未随精选包归档；来源：`generic-v3-live-controls-001`）。这些浏览器运行由实现者执行，本审查只读核对已有证据。

| 运行 | state0 | 首动作之后 | 最终与后缀 |
| --- | --- | --- | --- |
| normal | DOM/AX each 都为 0 实例，child_passes=0，N/A，continue | 两侧各 2 行，桥集合相等，continue | 2 个检查动作，worker completed，Finish=1 |
| missing_ax_row | 同上 | DOM 2 行、AX 1 行，桥关系 fail，release=stop | 仅 1 个检查动作，worker stopped，Finish=0 |

两次运行的 browser 和 oracle 共 4 份 cleanup receipt 都记录 `status=cleaned`、`owned_processes_remaining=0`；各自结果也记录两类清理确认。负控中业务后缀 Finish=0 与 release=stop 一致，不能把 worker 进程 exit=0 单独当作任务通过。

这组 live 实际使用总 wall 约 90 秒、completion allowance=20 秒；运行用时分别约 14.72 秒和 11.31 秒。它验证有限预算内的正反路径，**没有实测耗尽 300/45 秒的边界**。

## 实现判断与保留边界

1. **0..N 有可检查前提。** schema 要求 min=0 的 each 显式依附此前正下界、无 each、无后验槽依赖的容器链；不能仅以空父集合逃避容器约束。即使为 0 项，required local slot 的未知声明也要事前存在。非空时仍逐实际父节点检查；已知非空继续使用 min=1。

2. **身份集合完整性是相对于选中集合的。** same_dom_set 将 DOM id 与 AX backend_dom_id 映射到实际 captured DOM 节点，两侧均检查重复映射后再比较集合，不按位置配对。它能发现 AX has 隐藏的坏行，前提是另一侧 DOM 集合保留了完整候选范围。如果 DOM 和 AX 同时用相同条件过滤掉同一坏行，两侧集合仍可能一致；这不是对全站全部对象的自动完整性证明。需要作者独立声明候选容器、对象范围及身份歧义，并由业务 oracle 检查业务集合。

3. **跨域绑定没有获得先验数值分。** 代码把 select/has/scope 的槽依赖传播到 each 的所有子检查，并把任一关系端点的后验依赖传播到 same_dom_set/same_dom_node。独立控制覆盖了这三种依赖路径。观察桥身份也只证明当前采集节点的对应，不自动证明跨页持久业务对象身份。

4. **兼容按版本选择验证器。** wrapper 只接受 v1/v2/v3 bundle；只规范化外层 schema 供 v1 controller 读取，保留合同内容和 prediction。v1/v2 的对应 schema/validator 复制到 extension/legacy 并从那里加载；v3 从 extension 加载。未知版本明确拒绝。已有 3 个离线兼容控制保持合同与预测哈希不变，但本次两次 live 都是 v3，不能称已经重跑全部 legacy 网站流程。

5. **冻结扩展确实进入执行路径，但仍依赖冻结 v1 公共辅助。** 实际 validator 和 patched base runner 从登记 extension 导入，两个 live 存档与执行登记相符。v3 schema 仍绝对导入共享 v1 literal matcher；本审查已核 v1 字节未改。此设计不是可脱离仓库环境执行的密封镜像，仍应保持旧版本文件冻结。两个 live 的 v3 extension 内容相同，符合复用同版本的要求。

6. **300/45 是调用策略，非当前通用默认。** v3 默认 wall 为 600 秒，completion 默认 45 秒；本轮目标评测必须显式传 `policy.wall_seconds=300`。wrapper 从 wall 扣掉自身冻结准备耗时，再将剩余预算传入原 controller；完成等待取“剩余总 wall”与 cleanup allowance 的较小值。进程终止及 oracle 清理仍可能另有有限收尾时间，不能称抢占式硬实时 300 秒。另一个有限计时偏差是最终 `elapsed_seconds` 来自内部 base runner，未加回 wrapper 的冻结准备耗时；本组约 0.03–0.06 秒。需要准确端到端成本时使用外部总时钟，不将该字段视作完整调用成本。

本轮只验证表示与执行基础设施的通用能力。目标 source oracle 的独立事实、禁止副作用、身份及持久性成绩仍由独立评估者在相应固定分母中报告；本审查不为其补充通过结论。
