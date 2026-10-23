# 连续网页复现与组件合同 Harness

这里保存连续跨页脚本、公开 DOM/AX 检查、参数化组件合同、预算和进程管理的通用实现。网站规则与消费者脚本另见[组件合同交接包](../experiments/component-contract-pilot-20261023-01/published/README.md)。

当前研究计划是**先探索表示，再做冻结的 E/T/C 对照**，新实验尚未启动；最新交接范围与原文同步缺口见[研究状态](../../research/CURRENT_STATE_20261023.md)。本目录的既有实现与构造预实验不等于新协议已实施，也不证明找到最优表示或提高了模型理解。

本次公开包保存通用代码、接口文档与精选产物，未包含原始浏览器轨迹、私有 fixture、网站部署源码、数据库、oracle 实现和本机认证。克隆后可以阅读、检查模型与运行适合本机的离线测试；重放真实网站流程还需要补齐受控环境与独立评价驱动。冻结接口文档中的旧运行路径只描述当时的实验，不应当成公开包附带文件。

## 两类评价入口

| 用途 | 入口 | 检查内容与限制 |
| --- | --- | --- |
| 原站与复现站成对运行 | `harness.replica.runner.run_pair` | 同脚本、同输入，比较公开 DOM、完整 Chromium AX、业务与动作身份；保留 `observable_continuity` 与 `raw_strict` |
| 双站 Playwright 脚本连续性 v3 | `harness.replica.runner_playwright.run_pair` | 使用 Playwright 派生 ARIA 快照和稳定性门禁；完整 Chromium AX 与 raw strict 单列 |
| 单原站参数化组件合同 v3 | `harness.replica.contracts_v3.runner.run_source` | 对原站动作前声明的结构合同逐步检查；[接口](contracts_v3/README.md)与[结构定义](contracts_v3/README.schema.md) |

双站评价的 v3 与组件合同的 v3 是不同接口。Playwright ARIA 快照不是完整原生 AX；观察后绑定实际值不等于动作前预测正确。组件合同可以预测未知列表的 0..N 结构与逐项关系，而不预言搜索返回的具体数量和内容。

旧双站探索的开发流程通过后，首项隐藏任务失败；后续修订曾在启动前被拒绝，不能视为验收成功。组件合同 v006 在固定三任务中有一项完成 11 动作跨页流程，另两项停读；targeted007 修订尚无真实 UI 验证。这些均为 `isolation_limited` 构造预实验，严格成绩为 null；以交接包中的逐版本结果与边界为准，不能并入新的 E/T/C 成绩。

## 组成

| 模块 | 作用 |
| --- | --- |
| `transport.py`、`runtime/` | 冻结学习接口；固定 origin gateway；命名空间内执行原生 Playwright；预算、脱敏、持续拒绝和进程清理 |
| `construction.py` | 在明确限制的构造模式中准备工作区，区分同作者延续与新上下文继承产物，服务 gateway；不调用模型、不重置网站 |
| `operation_lease.py` | 新构造运行的 call/maintenance 双锁排他、跨 CLI 固定总墙钟；持锁 guardian 清理与中断 receipt 闭锁 |
| `persistent_service.py` | 可信管理器显式交接长驻服务；固定命令、私有鉴权、PID/starttime/listener所有权与受管停止；不接入学习者工具 |
| `contracts.py` | 产物结构检查；冻结全部候选、脚本、声明的状态导出和证据索引；检测文件修改与新增 |
| `server.py` | 隔离运行静态浏览器复现应用，支持文档路由，不伪造不存在的 API |
| `service.py` | 持久启动、健康检查和停止复现服务，校验进程身份、实际监听者及全部服务文件 |
| `trees.py` | 保存完整 Chromium DOM/AX；显式 URL origin 映射；层级、属性、控件状态和首差异比较 |
| `runner.py` | 同脚本、同输入、独立浏览器状态，按初态/动作/终态成对比较；首失败停止双方 |
| `runner_playwright.py` | 双站评价 v3 入口；加入 Playwright 语义快照及稳定性门禁，完整 AX/raw 结果单列 |
| `monitor.py`、`status.py` | 进程/资源/无进展停止；只读展示 gateway、请求和动作状态，避免输出应用数据 |
| `contracts_v1/`、`contracts_v2/`、`contracts_v3/` | 单原站组件合同检查；动作前结构预测、0..N 列表、逐项约束及 DOM/AX 对应 |

## 环境

Linux、Python 3.11+、Playwright、Chromium、Bubblewrap，以及能够执行
`unshare` 的环境。历史运行使用 Python 3.12 与系统 `/usr/bin/chromium`。
实际模型学习另需可用的精确 `gpt-6.1-sol` 通道；准备和比较器正反控不调用模型。
不自动安装依赖、不改代理、不复制认证值。使用项目现有的运行环境与认证选择器。

v3 固定 **Playwright 1.62.0** 及其 `coreBundle.js` SHA256
`3258d1cf334c6afc95f22aa9c292436cb976b391e0437f1359c83b84f0cb9d66`。
版本号相同但 bundle 不同也会拒绝。已保存运行接口中的 worker Python 固定为
`/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python`；
浏览器启动路径为 `/usr/bin/chromium`，v3 还校验
`/usr/lib/chromium/chromium`。这些是原运行环境依赖，不是任意 Linux 的即装即用包。
迁移环境须核对路径、namespace 能力和完整依赖注册，不能靠安装一个不同版本的
Playwright 跳过冻结检查。v3 每次运行保存 `frozen/dependency-manifest.json`，
记录 SDK/driver 文件和执行文件哈希；这仍不是完整 OS 镜像。

历史严格运行的云端 CLI 模型连接被网络策略拒绝，该次运行保留为阻断；迁移时需重新检查实际连接能力。
平台 Solar 的构造模式只对浏览器 worker 实施强制隔离；学习者完整 shell
只有指令边界，必须如实标为 `isolation_limited`，严格成绩为 null。

## 学习和监督

以下是配置完成后的命令形状，`work/NEW*` 均为新建的本地路径，不是仓库附带的可直接运行配置。部署、重置、公开 fixture、独立业务 oracle 和认证选择器须由受控环境另外提供。私有 `sites/` 实站适配未纳入公开包；学习者业务接口与管理权限应继续隔离。

从仓库根目录运行：

```bash
python -m harness.replica.construction prepare --config work/NEW-CONFIG.json
python -m harness.replica.construction serve-gateway --plan work/NEW/private/launch-plan.json
python -m harness.replica.status --run work/NEW --watch 10
```

配置需提供新 `run_dir`、单一 `origin`、公开 `fixture`、`task` 或 `task_path`，
可配置有限的 `action_limit`、`script_call_limit`、`time_limit_seconds`。
可另设正有限数 `browser_call_timeout_seconds`，限制每次取得租约后的执行时间；
省略时沿用总预算值。总墙钟 deadline 和累计调用／动作额度不变，等待租约仍
受总 deadline 约束。新值写入冻结 lease 和 wrapper，旧运行不追溯变更。
`fixture` 必须是 JSON 对象，不能填文件路径；协调器先读取文件，再把对象放入配置。
`origin` 当前仅接受无路径、查询或凭据的单一 HTTP origin。`prepare` 需要已有认证
选择器，但不会发起模型调用；`serve-gateway` 也不会自动启动学习模型或部署站点。
同作者继续还须指定 `from_previous_workspace` 与 `same_author_continuation: true`，
新上下文继承产物则指定 `new_context_with_inherited_artifacts: true`，两者只能选一。
这两种延续都不能重新声称独立重复。可信协调器可用 `runtime_source` 选择已验证的
版本化执行接口，源目录和冻结副本的文件哈希均进入注册。
准备好的 `TASK.md`、`CONTRACT.md`、
`BROWSER_INTERFACE.md` 是该次运行的冻结接口，不能中途替换。

学习者只通过自身工作区的 `browser.py --script flow.py` 操作。
每次调用新建 browser/context/page，页面初始为 `about:blank`；只继承已保存的
cookies/localStorage，不继承活的页面对象或 sessionStorage。每份脚本显式导航。
单份 `def run(h)` 内允许连续跨页、查询、刷新和返回，使用 `h.origin`
作为部署 base。查询结果需要语义阅读时调用 `h.read_point(reason)`，真正终止后缀。

新准备的 construction 运行把 `time_limit_seconds` 固定为从 `prepare` 入口开始的
总墙钟预算。私有 `control/run-budget.json` 记录同一 boot 的 monotonic deadline，
进入注册哈希与冻结 wrapper；新启动 `browser.py` 不会刷新它。等待租约和执行均
受剩余时间约束；到期后 guardian 终止并清理活动进程，gateway 停止。
旧冻结运行没有这项新保证，不能追溯套用。

新运行的浏览器调用串行持有 operation lease。协调器需要维护时，必须通过同一
运行的管理入口传入显式命令；该入口不内置任何网站重置逻辑：

```bash
python -m harness.replica.construction maintenance --plan work/NEW/private/launch-plan.json --wait-seconds 0 --timeout-seconds 300 -- python YOUR_MANAGEMENT_SCRIPT.py
```

`--wait-seconds 0` 在活动调用期间原子拒绝并返回 75；正数先保留 admission gate，
挡住新调用后有界等待活动调用完成。执行期间的锁 FD 由 trusted guardian 继承，
上层 CLI 中断不会提前允许维护。缺少有效清理 receipt 的历史 claim 会持续拒绝
后续工作。维护有独立超时，不延长学习 deadline。租约覆盖通过该新运行接口
发起的操作；直接运行管理脚本、其他运行或完整 learner shell 不在此强制边界内。

旧 `maintenance` 入口适合有限时命令：命令退出后 guardian 会清理它的全部后代。
**不要在该入口内直接执行会派生长驻服务的 start 命令**，即使 start 短暂返回健康，
服务仍会在 command-exit cleanup 时被杀。需要长驻服务时，由可信协调器直接准备
独立管理器；以下三条命令均不再套 `construction maintenance`：

```bash
python -m harness.replica.persistent_service prepare --directory work/PRIVATE-SERVICE-OWNER --lease-directory work/NEW/private/operation-lease --guard work/NEW/private/runtime/process_guard.py --pid-file work/SERVICE.pid --listener-port 8000 --startup-seconds 30 -- python YOUR_FIXED_START.py
python -m harness.replica.persistent_service start-daemon --directory work/PRIVATE-SERVICE-OWNER
python -m harness.replica.persistent_service start --directory work/PRIVATE-SERVICE-OWNER --wait-seconds 10
```

daemon 自己获取同一运行的 admission / operation 锁，并验证遗留 claim 的清理
receipt；再套旧维护入口会自锁。RPC 只接受 start/stop/status、需要私有 token 和
同 UID，不能传入或改写任意命令；固定 argv、manager/helper/guard 字节在 prepare
时冻结。管理目录为 0700、token/socket 为 0600，不放进 learner workspace、浏览器
命名空间或 MCP 工具。此权限设计仍受 construction 完整 shell 的既有隔离限制。

交接只接受本次启动后代中明确 PID 文件指定的进程，并核对 kernel starttime 和
实际 localhost listener；未登记后代被清理，既有外部服务不在清理树内。
`current.json` 指向带 nonce、PID/starttime、guardian、boot ID 和 config hash 的
`owner.json`；只有 `handed_off` 是持久交接，不能把 prepared/短暂健康当成功。
提交前中断会在锁释放前清理；提交后即使 CLI 未收到响应，也应先查 durable owner
收据，而非假定没有服务。

重置或替换受管服务前，先直接执行同一 manager 的 `stop --directory ...`，确认
注册服务消失且 nonce/PID cleanup receipt 有效，再做短时维护。开发版在 guardian
丢失又缺 receipt 时明确拒绝停止成功；较早准备的 manager 保留其原字节与边界，
不原地升级。`status` 和 `/proc`/listener 存活证据只验运行机制，不验网站业务。

安全拒绝持续关闭该运行；普通定位或时序失败留证后可修。修复冻结接口须新建
运行，失败记录与原字节保留。创建运行根目录的 `STOP` 可停止 gateway 和新调用；
进行中的受管 worker 由其进程/预算监督器控制。

## 冻结、比较与迁移

双站作者产物的原接口见 [LEARNER_CONTRACT.md](LEARNER_CONTRACT.md)。规则书记录功能、定位、条件、变化与停读点；详细观察另存。旧双站协议要求实际构建 DOM+patch 与 state+renderer 候选，这项历史要求不自动替代新的表示筛选设计。schema 校验只证明结构满足接口。

冻结和服务管理的调用形状如下；输入目录须由本次运行准备，输出使用新目录：

```bash
python -m harness.replica.contracts snapshot --workspace work/AUTHOR/workspace --out work/NEW-FROZEN --parent PARENT-REVISION
python -m harness.replica.contracts verify --registration work/NEW-FROZEN/registration.json
python -m harness.replica.service start --directory work/NEW-FROZEN/package/replica-state --port 4410 --out work/NEW-SERVICE
python -m harness.replica.service health --out work/NEW-SERVICE
python -m harness.replica.service stop --out work/NEW-SERVICE
```

双站 v3 评价采用 Python API。以下示意可信驱动中的调用，`profile` 来自本次明确冻结的完整策略封装；本包不附带可直接重放旧实验的部署和私有评价输入：

```python
from harness.replica.runner_playwright import run_pair

result = run_pair(
    source_plan, replica_plan, common_script, new_output_directory,
    modules=common_modules,
    policy=profile["policy"],
    oracle=independent_business_oracle,
    case_ref=private_case_reference,
    runtime_source=profile["runtime_source"],
)
```

完整策略封装同时绑定 `policy`、`runtime_source`、runtime manifest、controller 和准备检查结果；传给 `run_pair(policy=...)` 的只是内部 `policy` 对象。策略至少明确 `mode="playwright_script_continuity"`、与采集器一致的 `semantics_policy_id`、`runtime_manifest_sha256`、启用且匹配的 `stability`，以及有限的动作、墙钟、无进展、barrier 和资源预算。不能仅传模式名称，也不能临时重算已修改开发目录的哈希来冒充历史冻结版本。

两份 plan 提供不同的 `origin`、`socket`、对应的 `upstream_host` / `upstream_port`，以及内容相同的 `public_fixture`。可选 `init_script` 是进入注册的脚本文本。两侧独立 context，控制面不把私有 case、原站状态或对侧树逐步注入复现应用。业务 oracle 由可信部署与评价方提供；学习者模型自身的成功断言不能替代它，缺失证据记为 `unconfirmed`。

`python -m harness.replica.runner_playwright --help` 可查看 CLI。该 CLI 没有 oracle 装载参数，直接调用只能用于界面诊断，业务项为 `unconfirmed`；取得联合通过须使用独立评价驱动。CLI 的 `--policy` 接收内部 policy 对象。当前没有自动完成部署、学习、生成与评价的单条通用命令。

历史双站 profile004 使用 `evaluation-playwright-semantics-v8`，总采集上限 60 秒、稳定采样窗 40 秒、pair 墙钟 900 秒及 soft RSS 4 GiB；这只是旧配置说明，不构成当前运行默认值或成功凭证。完整原生 AX 与 raw strict 当时仍未通过。版本化 runtime 需连同依赖注册迁移，不能将不同 profile、候选或预算的局部通过拼为一项完整成绩。

每次 snapshot、评测和服务收据使用新目录。作者 `registration.json` 只证明清单与字节一致；评测另存自己的冻结输入、逐 checkpoint 比较、清理收据和最终结果。首个主要差异停止后，前缀匹配不算完成；后续修订要保留父版本、失败分类和新运行结果。公开精选包能传递方法与当前证据摘要，不能替代完整运行证据或原环境。

## 状态检查与离线验证

`campaign_status` 可读取用户另行准备的 campaign 配置；旧 campaign 和 `work/` 原始结果不在本包。它只按目录和最终文件标记 `not_run/running/final`，证据年龄不能证明进程存活，清理文件存在也不等于已确认清理。可选状态输出限于本地 `work/replica-status/`，不修改历史运行证据。

组件合同各版本测试含同名模块，合并运行需使用 pytest 的 importlib 导入模式。从仓库根目录执行：

```bash
python -m pytest -q --import-mode=importlib \
  harness/replica/contracts_v1/tests \
  harness/replica/contracts_v2/tests \
  harness/replica/contracts_v3/tests \
  harness/tests/test_replica_runner.py \
  harness/tests/test_replica_trees.py
```

这是离线验证命令，实际通过、跳过和失败应按目标环境记录。进程预算测试依赖操作系统行为与紧时间窗；离线测试通过也不能替代浏览器验收。

新的消费者应只凭冻结规则书、组件定位说明、表示结构、通用接口和普通任务输入生成新脚本。已公开的网站模型、旧脚本与评测摘要不得泄漏给声称独立学习的新上下文。首次生成、反馈修订与模型原始预测、LLM 最终预测分别记录；作者脚本通过不能替代独立消费者验收。
