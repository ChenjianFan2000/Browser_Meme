> 便携交接副本。原文：本轮 `METHOD-AUDIT-001.md`；原始 SHA-256：`0d6ef98b42ac5fc25571ad4e1e6b94e89bfcc04cb300f31fb84207b004db4997`。本次仅追加本说明并转换交接链接：已发布材料指向包内或通用 Harness，未归档材料保留短来源标识；历史观察、代码示例、判断、失败与时间截点不改写。当前完整结果以 [发布汇总](../RESULTS.json) 和 [交接说明](../README.md) 为准。链接到汇总仅表示保留了摘录，不等于原始证据已公开。

# 通用方法审查 001

审查者：`contract_method_audit`，通用只读审查上下文。审查时间：2026-10-23 03:46–03:56 UTC。本文件只审查本轮通用接口及实现，不给网站模型或业务成绩背书。

读取范围为根 `AGENTS.md`、本目录协议与清单、`harness/replica/contracts_v1/` 的 schema、validator、runner、观察投影、通用测试及新增 oracle 进程包装。为核对接口，还读取了通用 `runner_playwright.py`、`transport.py` 和 v8 `browser_runtime.py` 的相关代码。未读取目标网站源码、work 站点 private、模型作者规则或任务答案；未运行浏览器，未修改实现代码。仅写本审查记录。

## 结论及适用边界

现有接口能区分先验结构约束和后验数据绑定；`unknown` 的合同判定会进入 stop，不能以其本身获得继续执行资格。检查器也具有真实的拒绝能力：本次合成控制观察到缺结构、错关系、缺绑定、未声明槽及后验改写分别失败或无法确认。

审查发现了三类实际实现问题，并及时交给 `contract_harness_001` / `generic_contract_validator`：业务检查 truthiness 误放行、参数值被解释为模式、以及 `False`→`0` 的预测改写未被 Python 相等比较识别。下文区分已独立复核的修复、只完成静态审查的修复和残留限制。不能把本次通用合成检查当成真实消费者闭环。

## 实际检查证据

使用 `PYTHONDONTWRITEBYTECODE=1 python - <<'PY'` 直接导入通用函数，构造只含 list/listitem/button 的内存合同与观察；使用 `unittest.mock.patch('pathlib.Path.read_text', ...)` 模拟动作日志，未访问真实运行证据。

| 控制 | 本次实际输出 |
| --- | --- |
| 正常结构与绑定 | `pass` |
| required 节点缺失、父子关系错误 | 各为 `fail` |
| required 槽未绑定、未在动作前声明 | 各为 `unknown` |
| 采集 incomplete、预测 disposition=unknown | 各为 `unknown` |
| 不支持的选择器字段、仅 source 的 wildcard 锚点 | 各为 `unknown` |
| 缺关系端点、all 量词的空端点集合 | 各为 `unknown`，未因空集合而通过 |
| 后验修改 parameters 后沿用旧 commitment | `fail` |
| 加入引用已绑定槽的选择器及其 parent 关系 | prior score 仍为 `3/3`；binding score 为 `3/3`；预测对象未改变 |
| 正常 action_before/action_after 顺序 | `prior_prediction` error 为 `None` |
| 缺 after、日志逆序 | `missing_or_ambiguous_prior_prediction` |
| 普通后验改写 | `prediction_rewritten` |

前两次尝试执行通用 pytest：`python -m pytest -p no:cacheprovider .../test_validator.py -q` 与 `/usr/bin/python3 -m pytest ...` 均因 `No module named pytest` 未运行。随后实现者提供现成测试解释器，本审查实际执行 `PYTHONDONTWRITEBYTECODE=1 work/audit-20261022/test-env/bin/python -m pytest -p no:cacheprovider harness/replica/contracts_v1/tests -q`，退出码 0，输出 **51 passed in 1.82s**。上表是本审查单独构造的直接函数调用控制；51 项为现有通用套件，包含真实 oracle 子进程，但没有启动浏览器或网站。

## 已复核的实现修复

1. **业务检查结果的空值/数值误放行。** 初始 `business_checkpoint` 接受 assessment verdict=pass，且 `checks` 为 `{'pass':0}`、`{'pass':''}`、`{'pass':[]}`、`{'pass':{}}`、`['fail']`、`{'x':'unknown'}` 或 `[{}]`，全部返回业务 `pass`。修复后本审查逐个重跑，上述值均变为 `unconfirmed`；`{'pass':True}` 仍为 `pass`。这说明原来的接口有实际误分路径，但不说明真实目标 oracle 曾返回这些形状。

2. **参数对象注入匹配运算符。** 合同选择器 `{'name':{'$param':'wild'}}`、参数 `{'wild':{'$type':'string'}}` 原先可匹配任意字符串 name，从而把本应是值的参数变成宽泛模式。修复后引用值以 `$const` 作为精确数据处理，同一控制返回 `fail`。这项已单独复核；实现者新增的 slot 注入测试也随上述通用套件实际运行通过。

3. **序列化预测中的布尔/数值改写。** action_before 的 `parameters.flag=False`，action_after 及 checkpoint 改为 `0`，原先 `prior_prediction` 返回无错误。改用规范 JSON 摘要比较后，同一 mocked 日志返回 `prediction_rewritten`，已独立复核。

## 业务 oracle 接口的补充修复与边界

第一轮修复后，`checks={'pass':True,'side_effect_safe':False}` 仍会返回业务 `pass`：`_bad_checks` 一旦找到 pass/status 等标记，就忽略同一对象其余字段。本审查再次提交反例；03:54 UTC 实现者增加有限元数据字段与其余检查递归检查后，独立复测该反例为 `unconfirmed`，`{'pass':True,'nested_checks':[{'verdict':'fail'}]}` 也为 `unconfirmed`。

元数据中的 `actual:false` 可以合法表示实测布尔值，故不应把所有 false 都判成失败。补充控制 `{'pass':True,'actual':False}` 与 `{'pass':True,'id':'check'}` 均为 `pass`，符合这种区分。实际适配器必须遵守这一字段语义：`detail`、`actual` 等元数据字段不承载待判定子检查；独立子检查需要放在非元数据字段或独立项中。长期仍建议固定正式检查行 schema。**本次已复现的误放行反例均已复核修复；尚未验证真实 adapter 的字段使用是否符合接口。**

`describe.independent=True` 是自我声明。接口把 capture 的事实与作者合同分开，并要求 evidence、coverage、reset receipt；但仅从通用 API 不能证明适配器没有使用作者预测作真值，也不能证明 evidence 内容与业务终点充分。此次未阅读目标适配器，独立源事实与副作用是否覆盖仍需独立评估者负责。

## 冻结、时序与动作屏障

- **动作前来源正确。** v8 `browser_runtime.py` 在调用原生动作前，把 wrapper 的 `prediction['prediction']` 写成 action_before 的顶层 prediction，`log()` flush 并 fsync；action_after 和 barrier 采用相同顶层格式。runner 的字段读取没有多取或少取一层。动作后计算的摘要自身不能证明先验时序，证明来源是 worker 已落盘的 before 记录及其顺序。
- **普通输入使用同一次读取。** script、modules、contract bundle 被读入后，同一字符串/对象既写冻结目录又交执行或验证；未观察到再次读取原文件导致使用别的输入版本。
- **代码冻结并非全程执行冻结副本。** 浏览器子进程使用 frozen runtime；controller、validator、oracle 对象及部分 runtime 辅助模块先加载，再复制文件作为快照。最新 runner 新增 `_verify_loaded_files()`，在入口和冻结之后检查已登记通用 Python 文件有无变化，并补存 shared controller 源文件，减少开发中编辑造成的错版风险。本审查仅静态确认此检查，未注入文件变更或进程比赛。它不等于只读快照/完整沙箱，也不能自动证明 adapter 及动态加载模块都与存档字节相同。实际评测应使用冻结后新进程、停止编辑，并保存运行自己的哈希。
- **prepare 耗时已纳入新版入口时钟。** 初始实现的 started 位于 prepare 之后，capture/assess 也同步无本地限时。新版 `run_source` 从入口计时，新增 `BoundedOracle` 的有限 deadline 包装 describe/prepare/capture/assess，prepare 未确认或超时不启动浏览器。本审查最终运行的套件中，4 个 oracle 进程测试验证真实 callback 状态延续、50ms 回调超时、prepare 消耗 wall budget、截止后不派发新回调及实际清理 receipt；全部通过。其中 run_source 的准备测试用 monkeypatch 排除了浏览器启动，不能当作真实网站重置验证。冻结、依赖扫描、清理本身仍不是一个抢占式整函数 deadline；总实验截止需要 root 外部监督，清理超时不应写成正常成功。
- **unknown 阻后缀的代码路径存在。** `check_checkpoint` 只有 contract pass、独立业务 pass 等全部层通过才给 continue；runner 首次 primary fail 释放 stop；v8 barrier 收到 stop 抛出 `ComparisonStop`。本审查没有运行真实浏览器来验证后缀实际未执行，这项还需要 live controls。

## 有限风险与未来完善

正数 required 下界、非 wildcard 锚点、槽声明、关系非空端点提供的是最低结构约束，并不自动保证合同充分。只预测“有一个按钮”的合同仍可能合法但很弱；需要作者与独立评估者说明哪些业务相关输出会被拒绝。各合同可以自选检查数量，`prediction_score` 的分子分母是合同内检查数，不能直接作为不同表示间的统一理解分数。

same/different 及 parent/ancestor 检查当前观察节点关系；它们不自动证明跨页持久对象身份。跨页身份、业务终点与禁止副作用仍应由独立 oracle 和固定任务分母报告。参数化 tree 的符号输出也不等于生成完整网站。当前协议已明确单原站、有限范围、隔离有限、strict_score=null，这些限制应保留。

审查期间实现仍在更新。03:51:59 UTC 读取的版本摘要如下，仅用于定位本审查快照，不替代评测运行的冻结清单：

| 文件 | SHA-256 |
| --- | --- |
| schema.py | `c745b03794d0357ce235facfd251969355129bcddc8eb82535f846ff3886c92d` |
| validator.py | `1c4fee41e6ba04056772ea5174d0d328668b3cde2e62f82e9ba98c3e4c40221f` |
| runner.py | `3c3532608cb214dac88b8341e59a5d1741df5d7cd4124a3219621d4502de7fcc` |
| PROTOCOL.md | `e73046680bdc5a1447e5247beca71517272cdbfe47fcb0feb79d28c60cd783ce` |
| MANIFEST.json | `74bd67241f1a402f050a8aa05111f4c779547d5cdfb5310d316488e37e7587e2` |

03:54 UTC 补充复测时，runner SHA-256 为 `d3ae1953697093e61ed81d1c314743acd4c3bf57e99458564a796bad60da0d8b`；新增 oracle_process.py 为 `a91860068a4fb2973a01e9ff4ac69f8581998ed28403800262574348ae728a4d`。前一个表保留原审查时刻快照。
