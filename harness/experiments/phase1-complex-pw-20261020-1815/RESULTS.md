# 单个复杂任务：真实浏览器与评估介入

2026-10-20，按[本轮协议](PROTOCOL.md)，由独立 `gpt-6.1-sol`
编写脚本，主 Agent 运行通用 Harness，另一 Solar 上下文提供独立评价，
第三个 Solar 上下文在实际暂停期间审阅公开证据并决策。
任务在本地 Discogs 站点执行，使用真正的无头 Chrome 与原生 Playwright。

本次首次执行完成：**19/19 个 UI 步骤匹配预测，2/2 个评估关卡完成，
19/19 项独立业务终点检查通过**。无需修改模型或重跑。
这是一个任务实例的实测，不是总体成功率或未见任务泛化成绩。

## 完整脚本与证据入口

- [Solar 编写的完整中文流程与评估报告](solar-presentation/report.html)。
- [完整原生 Playwright 脚本](execution-001/inputs/scripts.py)。
- [逐步预测、实际动作和完整轨迹](execution-001/task-budgeted_two_seller_purchase.html)。
- [Solar 编写的规则与操作介入条件](execution-001/inputs/model/operation-and-intervention.html)。
- [固定计划](execution-001/inputs/plan.json)、[运行前冻结](execution-001/registration.json)、
  [真实结果](execution-001/summary.json)、[公开结果摘要](public-execution-summary.json)。
- [通用监督接口及复现约定](../../SUPERVISION_CONTRACT.md)。

任务为：以公开 demo 买家登录，搜索指定唱片，筛选评分至少95%的报价，
读取完整可见候选集合，比较不同卖家的两报价组合，在 USD100 预算内选择最低总价。
记住对象、价格和卖家，跨购物车、详情与市场页面回查，各加购一件，
在结账前核实购物车后只执行一次结账，并独立验证订单和无关副作用。
本轮选中的两报价为12与19，单价28.12与30.51美元，总价 **USD58.63**。

## 两次实际发生的评估介入

| 关卡 | 浏览器停在哪里 | 独立评价与 Solar 判断 | 等待时间 |
| --- | --- | --- | --- |
| selection_committed | 首次 Add to Cart 之前 | 独立评价通过；Solar根据原始页面和公开计算重算候选组合后允许继续 | 78.579秒 |
| before_checkout | 两件入车后的 Checkout 之前 | 独立评价通过；Solar核对DOM、截图及真实购物车响应中的对象、每件数量1、价格与合计后允许一次结账 | 49.844秒 |

每个关卡都有请求、DOM、截图与公开计算的哈希；Solar 决策绑定精确请求，
经独立状态复验后才允许对应步骤消费一次许可。实际事件审计证实，
19次动作派发均有先行预测，介入等待期间没有派发业务动作，
两个关卡均在对应动作派发前完成独立重检和一次性消费。

公开原始决策：

- [首次加购前请求](execution-001/cases/01-budgeted_two_seller_purchase/interventions/01-selection_committed/request.json)、
  [Solar 判断](execution-001/cases/01-budgeted_two_seller_purchase/interventions/01-selection_committed/decision.json)。
- [结账前请求](execution-001/cases/01-budgeted_two_seller_purchase/interventions/02-before_checkout/request.json)、
  [Solar 判断](execution-001/cases/01-budgeted_two_seller_purchase/interventions/02-before_checkout/decision.json)。

独立私有评价与公开请求分目录保存，没有提供给 Solar 审阅者。
模型作者的计算记录是待核对证据，独立评估器不将它作为答案。
源代码可见、上下文分工与文件目录约定不等于强制操作系统隔离。

## 条件及本轮验证边界

脚本为以下条件规定停止和诊断：候选不完整或不足、超出预算、
跨页面对象或价格变化、购物车对象/数量/金额不符、
加购或结账的写入结果无法确认、预期分支矛盾、评估未知或拒绝、
Solar 拒绝或超时、批准后的状态变化。未确认的非幂等写入不得自动重试。
脚本和规则需要修改时，必须另存版本并从固定初态回归；不能改写本轮结果。

本业务实测走的是两次批准的成功路径。其余停止条件没有在本业务运行中全部触发：

- [57项通用测试](unit-tests-001.log)覆盖拒绝、未知、缺失关卡、
  状态变化、请求/证据哈希、预算和超时等通用控制行为。
- [真实浏览器通道验收](supervision-smoke-001/result.json)在局部夹具中验证
  拒绝时0次动作、允许时1次动作。此处使用合成决策，明确不是 LLM 调用。
- [12项独立评价组件检查](environment-evidence/component-checks.json)覆盖正常与
  关键反例，包括未确认写入；它们不替代真实业务 UI 检查。
- [本轮证据审计](execution-audit-001.json)核对147个冻结文件无变化、
  两关卡证据与时序、107个报告链接和可读 trace。限定 JWT 模式扫描无发现，
  不代表任意秘密的全面检测。

## 时间与资源

端到端实际耗时 **196.796秒**，其中两次介入等待合计 **128.423秒**。
等待包括任务交接、证据审阅与返回决策，不等同于纯模型推理时间。
执行计时包含浏览器启动、回读、截图、评价和清理；安装、实现与源码阅读不在该列。
未做严格速度对照，不计算加速比。实际 token 和费用接口未提供，保持 `null`。

运行前核对原始110个源码文件、455个生产构建资产与50个已锁 Python
发行包；新数据库和日志与上一实验分开，数据库基线不重新种子化。
环境版本和构建证据见[准备清单](environment-evidence/setup-manifest.json)。
本轮服务已清理，两个服务端口已停止监听，见[收尾记录](finalization-001.json)。
[离线浏览器渲染检查](visual-001/result.json)确认报告及完整流程中的21张截图均可加载，
页面无脚本错误或横向溢出；查看产物不需要重新启动业务站点。

## 复现

从仓库根目录运行。已准备好的本地环境可通过以下命令启动，
每次将 `UNIQUE_ID` 换成新的值并保留该终端：

```powershell
$env:BM_DISCOGS_RUNTIME='G:\Browser_Meme\.runtime\phase1-complex-pw-20261020-1815'
$env:BM_DISCOGS_REFERENCE_RUNTIME='G:\Browser_Meme\.runtime\phase1-discogs-pw-20261020-1633'
$env:HARNESS_STOP_FILE="$env:BM_DISCOGS_RUNTIME\stop-UNIQUE_ID"
python harness/sites/discogs/complex_deploy.py serve
```

另一个终端运行完整冻结脚本：

```powershell
$env:HARNESS_CHROME='C:\Users\29935\AppData\Local\Google\Chrome\Application\chrome.exe'
& '.\.runtime\phase1-discogs-pw-20261020-1633\venv\Scripts\python.exe' -m harness.playwright_run --site harness/sites/discogs/site-complex.json --model-dir harness/sites/discogs/model/pw-complex-v001 --protocol harness/experiments/phase1-complex-pw-20261020-1815/PROTOCOL.md --case-seconds 900 --out harness/runs/pw-complex-UNIQUE_ID
```

协调者必须在每个关卡出现时将公开请求交给 Solar；240秒内没有合规决策会停止，
不能用无人审阅的 `continue` 文件代替。两次计划介入和一次故障诊断共最多3次，
单任务预算900秒。完成后创建本次确切的停止标记，清理拥有的服务。
不得并行执行共享这一数据库的业务套件。
