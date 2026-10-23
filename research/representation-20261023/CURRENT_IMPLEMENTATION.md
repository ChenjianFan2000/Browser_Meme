# 旧第二阶段退役前的实现审计（历史参考）

> 整合注记（2026-10-23）：本文描述旧 Discogs 第二阶段退役前的实现与诊断，基于历史提交 `6b70630a93072d739e66d878c73cc5b57fd8acdb`。最新 `main` 已移除该轮结果；下列数字不再作为当前研究结论或第三阶段准入依据。当前入口为[研究状态](../CURRENT_STATE_20261023.md)与[组件合同交接包](../../harness/experiments/component-contract-pilot-20261023-01/published/README.md)。本文保留历史问题与原设计动机，不恢复退役产物。

审计日期：2026-10-23。范围：通用 Harness、已归档阶段二报告与学习产物。未由主 Agent 阅读目标站点源码提炼规则；本轮未重跑网站。历史浏览器证据部分仅在 Release 分卷中，读取本地审计报告不等于已恢复并实时重验所有证据。

## 退役前实现不只是 AX 抽取和绑定

当时的阶段二具备浏览器主动探索、动作前预测、原生 Playwright 执行、规则书／对象映射／行为模型产出、冻结任务评测与独立业务判定。AX 是观察来源之一，不是全部流程。历史产物还存在成功／拒绝／重复操作及回读后的规则修正；因此不能概括为“只找页面绑定”。

真正尚未充分建立的是：**所选规则与状态抽象是否保留了新对象、新状态和后续组合所需的信息，代码是否在公平条件下提供额外能力。** 结构验收和少量实例正确不足以回答这个问题。

## 固定历史提交中的证据

| 位置 | 已实现／实际含义 | 尚不能据此声称 |
| --- | --- | --- |
| [browser_runtime.py](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/phase2/browser_runtime.py)，`observe` / `action` | 保存 DOM、AX、截图、可见文本、允许响应；要求动作前 `expect` | 每一步语义已独立判断；`action_after.classification` 仍默认 `unconfirmed` |
| [records.py](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/phase2/records.py)，规则与证据检查 | 检查 schema、证据文件、原始哈希和导出一致性 | 规则语义真实；代码明确将其留给独立网站评价 |
| [review_learning_v002.py](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/phase2/review_learning_v002.py) | 静态与结构审核明确标 `not_established_by_this_structural_review` | 准入包的所有规则均已正确理解 |
| [evaluation_broker.py](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/phase2/evaluation_broker.py)，`declare` | 冻结哈希、一次预测回执；A 必须原样提交代码输出 | 与允许 LLM 推理的 B 是纯代码有无的公平对照 |
| [browser_broker.py](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/phase2/browser_broker.py)，`execute` | 受控脚本执行、预算与部分终止状态 | 每种终止性拒绝均已持久锁定；校验先于请求日志的问题需要修复 |
| [历史未知预测诊断](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/experiments/phase2-discogs-20261021-01/private/audit/prediction-unknown-diagnosis-001.md) | A 产物的适用范围过窄，实例条件与规律条件混杂 | 未知代表真实业务不允许，或所有代码模型必然弱于文本 |
| [历史逐包语义审核目录](https://github.com/ChenjianFan2000/Browser_Meme/tree/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/experiments/phase2-discogs-20261021-01/private/audit/run-reviews/) | 存在独立的归档规则／证据审核，不是完全没有语义检查 | 已覆盖未见组合、所有步骤或当前部署的实时回归 |
| [冻结结果](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/experiments/phase2-discogs-20261021-01/reports/frozen-results-001.json)与[有效性报告](https://github.com/ChenjianFan2000/Browser_Meme/blob/6b70630a93072d739e66d878c73cc5b57fd8acdb/harness/experiments/phase2-discogs-20261021-01/reports/validity-001.json) | 原始全分母结果与合规分析分开 | 6 个学习包均合规、全部可作为独立方法重复 |

独立站点评价的委派审计还确认：历史任务预测主要评分 `disposition`、`persistent_state_changed`、`affected_record_count`；UI 预测并未形成同等完整的可评分真值。下一轮须扩充对象身份、UI 读出、持久性、后续可用操作和副作用的独立判定。这里记录审计结论，不由主 Agent 据站点源码补写业务 oracle。

## 历史数字的正确解释

历史实验有 6 个学习包、180 个任务、540 个整任务预测字段。原始 A/B 结果如下：

| 组别 | 任务成功 | 预测正确 | 模型未知 |
| --- | --- | --- | --- |
| A：文本＋代码 | 87/90 | 3/270 | 267/270 |
| B：文本 | 89/90 | 233/270 | 37/270 |

A 的两个学习包因终止性拒绝之后继续调用被隔离，只有 seed 1729 是完整合规配对。该配对 A 任务 28/30、预测 0/90；B 任务 30/30、预测 81/90。隔离原因不是已经证明成功逃逸，也不能把隔离后保留的原始数字解释成合规方法均值。

差异同时涉及预测提交通道、模型的窄实例适用范围和学习过程；它不识别代码的因果效果。当时四包得到第三阶段准入，第三阶段尚未在该轮完成；该准入已随旧第二阶段退役失效，不再作为当前依据。任务通过也不意味着预测通过，更不意味着状态抽象已最优。

## 本轮因此新增什么

- 先比较表达相同命题的文本格式，再比较可执行表示；不沿用旧 A/B 差异直接下结论。
- 原始代码预测与统一 LLM 最终预测双轨保留，检查监督是否补偿模型缺陷。
- 固定配对挑战集，测错误合并、无谓区分、历史依赖和两三步后的分歧。
- 保留原始证据，独立 oracle 不复用学习者的抽象器，避免共同删掉关键属性。
- 先补通用隔离、终止锁、逐步评分和分母，之后才生成新的网站案例和学习包。

具体数量、预算和停止条件见[试验协议](../../harness/experiments/phase2-representation-20261023-01/PROTOCOL.md)。本说明记录依据，不修改任何旧协议、请求、产物或结果。
