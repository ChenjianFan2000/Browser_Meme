> 便携交接副本。原文：本轮 `METHOD-AUDIT-FINAL.md`；原始 SHA-256：`a67f3a2d1b17b396f8e9c4c0341a1959f5f297ff4c3bf2b14a6651ac4bd9dd11`。本次仅追加本说明并转换交接链接：已发布材料指向包内或通用 Harness，未归档材料保留短来源标识；历史观察、代码示例、判断、失败与时间截点不改写。当前完整结果以 [发布汇总](../RESULTS.json) 和 [交接说明](../README.md) 为准。链接到汇总仅表示保留了摘录，不等于原始证据已公开。

# 最终方法与计数审计

**结果时间截点（as of）：2026-10-23 04:42:04.362880 UTC。** 本文是该时刻已登记结果的审计，不是 05:06:21 UTC 总截止后的最终清场证明。candidate004 已冻结，但该截点尚无消费者执行结果；不得提前记失败或通过。本文不修改已有结果或 METHOD-AUDIT-001/003。

审查者 `contract_method_audit` 仅读本轮协议、通用冻结与审计记录、公开模型 registration，以及 root 明确授权的 RESULT-INDEX、CONTROLLED-REPRODUCTION-INDEX、两个固定三任务 summary 和索引引用的 SAFE-OUTCOME/SAFE-ATTRIBUTION。没有读取目标源码、fixture 凭据、业务 oracle 代码或未授权的私有任务材料，没有启动浏览器或运行新目标检查。下文业务事实来自独立评估者的安全结果；本审查核对其计数、字段含义、归因和版本边界，没有重新实现业务真值。

## 固定分母与已定计数

协议的消费者任务分母为 **3**，独立继续/停读探针分母为 **2**。各版本重跑仍是同一组三任务；首次生成、适应、工程重放和探针分别列示，不能合并成额外独立样本。

| 阶段 | 固定分母 | 实际目标执行 | 完整连续通过 | 其他已定结果 |
| --- | ---: | ---: | ---: | --- |
| 首次生成 candidate001 / contracts_v1 | 3 | 3 | **0/3** | 1 项业务终点达成但工程退出完成未确认；2 项停读且任务未完成 |
| 适应 candidate002 | 3 | 0 | 无 live 通过结果 | 3 项静态模型阻断，保留 not_run；不是 3 次真实浏览器失败 |
| 适应 candidate003 / contracts_v2 | 3 | 3 | **1/3** | 2 项安全停读，完整任务未完成；没有未运行项 |
| 表示探索 candidate004 / contracts_v3 | 3（继承固定任务） | 截点尚无执行结果 | 待评测 | 模型冻结不等于消费者任务通过；不得把 pending 记作失败 |
| 独立继续/停读探针 | 2 | 2 | 算法继续探针 1 项连续完成 | 语义探针 1 项符合预期停读；该项 continuous_complete=false |

首次三任务真实动作数按任务为 **11、6、7**，合计 24；003 为 **11、7、7**，合计 25。本审查用逐例 SAFE 结果重算，与两个 fixed3 summary 一致。首次另外有两个 0 UI 基础设施尝试：wrapper import 登记失败和旧 lease admission 拒绝；它们应保留在尝试记录中，但不扩张固定任务分母，也不与实际模型动作失败混淆。

首次 summary 明确 `all3_scripts_frozen_before_feedback=true`，003 summary 同样记录全部脚本先冻结后反馈。此处核对安全摘要，不声称另读隐藏脚本或完整冻结闭包。各 model registration 的 `frozen_unvalidated` 是创建时的登记状态，不能用它代替后来逐次结果索引。

## 001 与 003 的关键区别

首次 task01 不是“业务模型已被反例推翻”。安全结果记录：初态、11 个动作及 final 共 **13/13 mandatory checkpoint pass**，独立最终业务目标 satisfied，worker 状态 completed；但受监督源进程退出码为 **143**，因此 `overall_pass=false`、`cleanup_or_completion_unconfirmed` 必须保留。两张 cleanup receipt 都为 cleaned/0，故也不能把它直接描述成已发现残留进程泄漏。固定 12 秒完成等待后被终止是记录中的潜在机制，不应仅凭退出码断言因果已被隔离证明。

003 task01 的 11 个动作、业务终点、退出码 **0**、browser/oracle cleaned/0 和已记录外部进程身份消失同时满足，才获得完整 `primary_pass=true`。它是**适应阶段**通过，不能回填首次结果。候选模型、消费者驱动及工程控制器均有版本变化；未执行“同一旧模型/脚本只换引擎”的可选重放，因此不能把 0/3→1/3 全部归因于表示更好或模型理解提高。

首次 task02/task03、003 task02/task03 都在受支持前缀后停读，退出码 0、清理确认，并不意味着完整任务成功。特别是 003 SAFE 中的 `business_verdict=pass` 与 `task_goal_complete=false` 同时存在：前者确认已执行前缀与副作用检查，后者决定完整任务尚未完成。

## 模型是否真的被消费

依据索引新增的 SAFE-ATTRIBUTION-model-consumption.json（本地历史引用，未随精选包归档；来源：`SAFE-ATTRIBUTION-model-consumption.json`）：

- **v001：消费了注册的组件与预测辅助函数。** 浏览器脚本导入 `components_v1`；消费者 helper 维护平面的预测状态，将辅助函数生成的预测交给 `h.expect`。独立目录中的 `component-model/model.py` **没有作为 browser module 加载**，不能称该单独状态机驱动了浏览器。
- **v003：消费了显式规划与状态更新接口。** 冻结消费者 driver 导入注册的 `components_v2`，从 `initial_state` 出发调用 `plan(state, operation, parameters)`，将 `q.prediction` 在原生动作前交给 `h.expect`，随后以 `q.state` 更新状态，并用公开观察绑定数据。
- **证据强度有边界。** 评估者记录执行前 input pins、执行后 `all_pins_unchanged=true`、实际非空 checkpoint `prior_prediction_sha256` 以及已比较预测字段；这些支持注册辅助模块及其预测被真实运行消费。没有函数级调用追踪，不证明每条模型分支执行过，也不证明完整隐藏状态正确。本审查没有越权读取这些底层私有脚本，而是核对安全归因与公开 registration 的模块摘要一致。

candidate003 registration 文件实际 SHA-256 为 `901c3f7aba39ac59ed0b8f57bf8ca8e1e0c0652aa40ceb14a009b05bdcc3b812`，与 RESULT-INDEX 相符；registration 中 `components_v2.py` 的摘要 `37dd2770445c6640fef4489f13fd52fce2e7763e6ef65a159507281418da5e72` 与安全消费归因中的实际模块摘要一致。candidate004 registration 文件摘要为 `8f4e780ef0a15f3640777418f19d7aaf98e3b56601eab42e6f2be63eeb701c7c`，仅支持其已冻结事实。

## 失败归因与两个探针

task03 最新 SAFE-ATTRIBUTION-v2.json（本地历史引用，未随精选包归档；来源：`SAFE-ATTRIBUTION-v2.json`） 纠正了更强的不可达解释：固定初始返回窗口没有目标，任务没有明确禁止合法的查询细化；评估者有只读证据表明可能存在细化路径，但消费者未实际尝试。应报告“初始返回前提不满足、消费者安全停读、细化未执行、任务未完成”，不能称目标在后台不存在、任务全局不可达或因此移除该任务分母。也没有证据把它归因成 parser/参数映射错误或已触发某个后续动作合同的反例。

固定两探针均已登记真实结果：

| 探针 | 动作数 | 已登记结果 | 允许的结论 |
| --- | ---: | --- | --- |
| algorithmic external result | 8 | 连续完成，业务目标满足，exit=0，两个 cleanup cleaned/0 | 该例可根据真实公开返回的唯一 tuple 绑定并继续；不证明任意重排鲁棒性或语义偏好推断 |
| semantic readpoint | 7 | expected_stop_compliance=true；primary_pass=false；continuous_task_complete=false；exit=0，两个 cleanup cleaned/0 | 在注册的语义选择与持久写入前适当停读；这是停读探针合规，不是完整业务流程连续通过 |

语义探针 SAFE 的 `task_goal_status=satisfied` 指**该探针预期停读目标**，与 `continuous_task_complete=false` 不冲突。可以说两个探针分别呈现了预期继续和停读，但必须同时说明连续完成只有算法探针，不能写成“2/2 连续任务成功”。

## 最容易误称的结论

1. **不能把先验字段匹配数写成任务数或全模型正确率。** 首次 task01 的 132/132 是跨动作重复字段比较，另有 2 个未计这些预测字段的 checkpoint；不是 132 个独立任务。003 的相同数量也不是完整内部状态验证。
2. **不能把停读或前缀业务 pass 合并进完整成功。** 首次完整通过仍为 0/3，003 为 1/3；适当停读另报。
3. **不能把新通用组件合同当作完整网站副本或精确全 AX 预测。** v3 正反控证明通用 0..N、集合桥和动作门的有限性质；candidate004 的网站效果在截点仍待评测。
4. **不能声称因果优势、最优表示或全站覆盖。** 只有一个受控站点和有限任务，模型/引擎/脚本共同修订，没有同知识、同预算的表示消融；不支持严格速度比较。
5. **不能将局部程序接入夸为独立 model.py 已驱动全部流程。** v001 与 v003 的消费层级不同，必须按上一节写。
6. **不能用 cleaned 收据宣布整个实验已经收尾。** 逐 run 的 browser/oracle 清理与长期站点、gateway、manager 的总收尾是不同层面；截止清场仍由 root 核验。
7. **不能计算未记录的 token 或账单。** provider tokens/actual cost 均 unavailable；学习、生成、等待、验证和维护成本也不能被单次运行耗时替代。首次与003 task01的约124.85秒/96.71秒不构成受控速度提升证据。

## 可复现入口与证据边界

CONTROLLED-REPRODUCTION-INDEX.json（本地历史引用，未随精选包归档；来源：`CONTROLLED-REPRODUCTION-INDEX.json`） 登记的是受控执行入口：003 走 `contracts_v2.runner.run_source`，新进程验证冻结闭包，使用独立可信 source oracle、外部私有 fixture、总 wall=300、action_limit=20、oracle_call=25、completion_cleanup=45，并持有 root 唯一浏览器槽。公开包不是凭据或 oracle 的替代品；普通 CLI 没有可信业务 oracle 时只能给 unconfirmed，不能声称业务真值通过。

最初读到该索引的 interpretation 比 RESULT-INDEX 旧，仍称 task02 未运行；本审查已通知评估者，最新索引改为003固定三任务已完成。后续报告应以最新安全结果索引的时间戳为准，不把登记时状态或旧进度文本当作最终状态。

仍保持协议的 `strict_score=null`、有限构造预实验和隔离限制：浏览器 worker 有命名空间约束，模型 shell 主要为指令隔离；独立上下文不等于完整 OS 隔离。业务 oracle 的实现独立性与全部业务覆盖未由本审查重读源码验证。

## 本次截点的证据摘要

| 文件 | SHA-256 / 截点 |
| --- | --- |
| RESULT-INDEX.json | `be2387eac1acedad86d7eea8206d2fa271a115c5825d8f0c7986c3a9202a1a23`；04:42:04.362880 UTC |
| FIXED3-FIRSTGEN-SUMMARY.json | `28b1d42bd48fa59d6ad5a717a67e6e769d1baf96eb3de195e589d51b4c971f2b` |
| adaptation003 FIXED3-SUMMARY.json | `5d3578c2d61cb2366c098e5c9a54d722e63866b0dea22ae5be14706a21ad8747` |
| SAFE-ATTRIBUTION-model-consumption.json | `fecec37f8fd40f800f3fdabede02e0af5f439a8097da2bf0673ed5a9e7a605bf` |

独立计数一致性检查通过；审查中没有修改任务输入、分母、模型或历史结果。candidate004 后续结果和总清场需要在收尾报告中追加新的明确时间截点，不能倒写为本文时刻已知。


## 最终追加：2026-10-23T05:06:34.436601+00:00

本节只追加终审，不改写上文 04:42:04.362880 UTC 截点。最终安全索引与物理账截至 **2026-10-23T05:04:45.204825+00:00**；本次只读安全结果、归因与交接元数据，没有运行新浏览器，没有读取源站、凭据或 oracle 实现。

### 固定分母与最终分类

| 阶段 | 固定分母 | 实际 UI 任务 | 连续整体通过 | 其余结果 | 实际动作 |
| --- | ---: | ---: | ---: | --- | ---: |
| 004 | 3 | 1 | 0 | 1 个接口边界错误；2 个因共用 helper 阻断未运行 | 2 |
| 005 | 3 | 0 | 0 | 3 个因纯模型不变量阻断未运行 | 0 |
| 006 | 3 | 3 | 1 | 2 个 readpoint incomplete | 29（按任务顺序 11 / 7 / 11） |
| 007 定向诊断 | 1 | 0 | 0 | 1 个 preflight / deadline admission rejected，未运行 | 0 |

001、002、003 与两个独立 probes 保持上文结果；不得把不同修订重复执行的同一任务并成独立样本。006 仍为 **1/3 完整通过**，007 不能将它改成 2/3。语义 probe 的预期停读合规仍与完整业务完成分开。

004 的实测错误发生于两次 fill 后，共用 helper 对密码控件调用被接口禁止的 input_value 读回；允许填写不等于允许读取秘密值。这是 consumer / 接口使用错误，没有证明后端业务迁移或模型表示错误，另外两项也不是实测网站失败。005 的三个任务在纯模型组合不变量检查阶段被阻断，0 UI，不能写成三个网站失败。

006 是模型兼容修复后迁移原 005 策略。READY 与 PRESERVED 元数据的五个输出哈希逐项一致：三个脚本、helper、checkpoint；仅访问元数据更新。因此不能称新的独立 consumer 生成，也不能据此建立模型表示的因果提升。这里核对的是登记的保存证据，不是重读策略代码。

006 的任务 01 完整通过，11 actions、业务终点通过、source exit 0，browser / oracle cleanup 均 clean 0。任务 02 仍停于未完成前缀（7 actions）。任务 03 **确实执行了第二次查询并唯一选择公开结果**（11 actions）；随后 consumer 对复合详情元数据使用孤立 exact-text 谓词，错误的文本粒度导致 ownership 未确认。保存、申请及持久化终点未执行或未证实，故仍 incomplete。该 SAFE 归因由保留观测的只读重建支持，没有新 live 重放；不能当作修复已通过，也不能把旧版本“尚未查询细化”继续套到 006。006 三项 exit 0、两类 cleanup clean 0、登记的 external alive 均为空；局部字段匹配仍不是独立任务数或完整内部状态证明。

007 是同 model 006、原任务 03 脚本与 checkpoint 的单项 helper 修正诊断。NOT-ADMITTED 记录两个不同的编排问题：先发生 root 交接哈希断言冲突，shell 随后仍调用 wrapper；wrapper 因全局剩余时间少于完整 260 秒门槛独立拒绝，尚未 prepare/reset/browser。RECOVERY-CLOSURE 保留原登记，列出 **22 个不可变输入全部匹配、唯一允许变更的 helper 已变更、4 个输出哈希完整**。原 WHITELIST 同时把允许改写 helper 当成不可变输入，属于 root 交接规则冲突，不能归为 consumer 越权或模型失败。此修正的业务效果仍未测得；未来运行须另登记预算与 run id，不能追认 007 已执行。

### 物理账与清理

独立重算最终物理账的 14 行 controller attempts：**12 次真实 UI 评估运行 + 2 次 0 UI 基础设施尝试，评估 95 actions**，返回的 controller elapsed 合计 **925.2226761779984 秒**。007 的两个连续 preflight 调用另列为一个外层尝试，没有启动 controller，不增加上述 14 / 12 / 95。静态阻断同样不伪装成 UI 运行。

作者学习为 **8 browser calls / 69 actions**；通用 live controls 为 **10 runs / 14 actions**，与评估分列。三类动作可相加为 **178 actions**；ledger 的 30 总数由 author calls 8 + generic runs 10 + evaluation runs 12 得来，计数单位混合，不宜称 30 个独立任务、浏览器会话或独立样本。worker elapsed 嵌套于 controller，外层 wrapper 又包含 controller，不能叠加。925.22 秒也不等于全实验成本；旧外层准备、离线构造与 provider tokens / 金额等未完整计量。

最终 SAFE-SERVICE-CLOSEOUT 给出四个当前 site 服务及对应管理进程均已停止，登记端口 8310 / 4310 / 8311 / 4311 无 listener，每项身份匹配且 stop complete。FINAL-ROUND-SUMMARY 另记录 non-zombie Chromium / crashpad 为空、4 个 zombie browser 进程仍被观测到；因此可以说本轮受管服务及活动浏览器已收尾，不能笼统声称操作系统中所有浏览器进程条目均消失。该判断依据安全清场凭证，本审查没有独立发送信号或扫描其他进程。此前 001 exit 143 的历史工程未确认结果保持不变，后续总清场不能倒改它。

README / TECHNICAL-REPORT 的中间审阅已提醒并纠正把旧 001 工程未确认表述为确定泄漏、把归档时间归因说成已验证原因的风险。最终仍应保留：001 的业务达成与整体通过不同；003、006 各 1/3 不证明表示优越性；007 未跑；strict_score 为 null。

### 本次实际核对证据

| 文件 | SHA-256 |
| --- | --- |
| RESULT-INDEX.json | `0bdb29ab6230754400ab9449e34189724feebda73cd76c49b41adb2c0bb55d85` |
| adaptation006 FIXED3-SUMMARY.json | `0fdfed0f73388c868c1ad2b8dffb173e3571a6af99335e15969232ed306ff2f4` |
| SAFE-PHYSICAL-ACCOUNTING.json | `efe03f78a15ffae9ccc7408c8f76243f9e78a4caaff883856465843a11ffafc1` |
| targeted007 NOT-ADMITTED.json | `8166f3d7c3ed8b755ebfc209b145ad2a2ca96790d69f55dab8ebf040a2b07829` |
| RECOVERY-CLOSURE.json | `2afdee0d893713840b9ebb8c5d74f196569991cc7c3532d97175490dececcc9e` |
| SAFE-SERVICE-CLOSEOUT.json | `0e50acc14ce69406746ffb2237436b87b217a6f8da3420ac5122799173b2cfa2` |
| FINAL-ROUND-SUMMARY.json | `2cbae2a05fb94fd25d665a85240cb82cb212242bed85c351eeee786b1aa6bb2f` |

原审计前 11008 字节 SHA-256 保持 `7e86d23627555c5b4fd28bf7e43b06306c46bbea66566553b872f8dd3984f979`。本次未更改源代码、任务、模型、固定分母或历史结果。
