# 第一阶段直接 Playwright 实验记录

日期：2026-10-20。协议：[PROTOCOL.md](PROTOCOL.md)。
本轮源码可见实验已完成首次执行、一次网站模型修订、完整回归和预先声明的两轮冻结重放。
固定的 20 个任务中，12 个通过独立终态评价，8 个未完成。
**整体模型未达到全部目标通过的激活条件**；不能称为全站覆盖完成。

## 查看产物

- [Solar 编写的中文规则书与证据展示](solar-presentation/report.html)。
- [最后一轮结账任务的完整七步流程](anchor-repeat-002/task-checkout.html)：逐步预测、原生 Playwright 动作、观察、截图、网络反馈与独立检查。
- [源码阅读独立审计](solar-presentation/source-coverage-audit.md)及[补充勘误](solar-presentation/audit-supplement.json)。
- [所有运行的机器可读汇总](aggregate-001.json)与[证据结构核验](evidence-audit-final-001.json)。
- [原八项最终重放](anchor-repeat-002/report.html)与[扩展十二项最终重放](extension-repeat-002/report.html)。

主 Agent 仅建设、运行通用 Harness 和汇总真实结果。
独立 `gpt-6.1-sol` subagent 阅读源码、撰写规则书、实现原生 Playwright 脚本并修订；
另一个独立 Solar 上下文负责部署及独立评价。
这项长期分工和浏览器接口已写入根目录 [AGENTS.md](../../../AGENTS.md)。
主 Agent 在用户纠正分工前接触过网站源码，已在协议中记录，不能充当阶段二学习者。

## 固定分母与实际结果

| 运行 | 任务完成 | 步骤预测匹配 | 套件实测耗时 |
| --- | --- | --- | --- |
| [原八项首次业务执行](anchor-initial-002/summary.json) | 4/8 | 38/44 | 198.578 秒 |
| [扩展首次业务执行](extension-initial-001/summary.json) | 8/12 | 53/66 | 202.422 秒 |
| [原八项修订回归](anchor-repair-001/summary.json) | 4/8 | 39/44 | 104.297 秒 |
| [扩展修订回归](extension-repair-001/summary.json) | 8/12 | 53/66 | 168.859 秒 |
| [原八项重放一](anchor-repeat-001/summary.json) | 4/8 | 39/44 | 106.485 秒 |
| [扩展重放一](extension-repeat-001/summary.json) | 8/12 | 53/66 | 185.844 秒 |
| [原八项重放二](anchor-repeat-002/summary.json) | 4/8 | 39/44 | 105.375 秒 |
| [扩展重放二](extension-repeat-002/summary.json) | 8/12 | 53/66 | 163.985 秒 |

两组任务 ID 不重叠。修订回归与每轮重放分别为 12/20 个目标通过、
92/110 个步骤预测匹配；未执行步骤保留在分母中。
汇总脚本核对四次重放与各自修订回归的冻结输入、逐任务结果、逐步匹配、
独立检查、数据库初态和浏览器版本全部一致。
所有业务运行的输入完整性检查通过；修订回归没有既有成功任务或步骤的回归。
失败可重复不代表任务成功，所有运行的 `activation_allowed` 均为 `false`。

更早的 [anchor-initial-001](anchor-initial-001/summary.json) 在任何 UI 动作派发前，
因通用接口未把完整公开计划传给脚本而阻塞，保留 8 个任务、44 个步骤，
业务成功率为 `null`。该缺陷由主 Agent 修复，记录于
[infrastructure-repair-001.json](infrastructure-repair-001.json)；
它不计作第一次网站模型业务测量，也没有据此修改网站规则。

耗时包含本次执行中的等待、回读、截图与独立检查。此处没有严格速度对照，
安装、构建、源码阅读和模型维护不包含在该列，不能据此声称加速比。
模型 token 与费用接口未提供，保持 `null`。

## 覆盖边界与反例

Solar 的源码清单登记 110 个文件：99 个文本实现、配置或文档实际阅读，
1 个依赖锁文件检查顶层元数据，6 个装饰资源登记，4 个任务答案或管理辅助文件
排除内容读取。独立审计核对了全部 110 个文件的哈希，并交叉检查重点模块；
这不等于独立认证全部文件的业务理解或全部分支已实测。
24 条规则的已验证、推断和待验证范围在展示中分别标注。
冻结模型保留原引用，两处行号越界在独立附录中勘误。

独立部署诊断将未完成目标的共同阻塞定位到原网站动态 API 路由的转发行为，
证据见 [DIAGNOSIS.md](environment-evidence/routing-diagnosis/DIAGNOSIS.md)。
网站源码未修改。Solar 据实际反馈修正等待与分支说明，未删除原目标、
削弱终点评价或把拒绝预测匹配记为业务完成。
同类但未实际执行的路由仍只记为推断，不将一次反例扩写为全站实测结论。

## 环境、验证与复现

- [部署清单](environment-evidence/deployment-manifest.json)：原始网站源码与运行副本哈希一致。
- 原生 Python Playwright 1.56.0；实测 Chrome 155.0.8059.84；每任务新进程、新浏览器上下文并恢复冻结数据库基线。
- [离线依赖复装验证](environment-evidence/offline-lock-validation.json)：新虚拟环境中 50 个发行包版本完全一致，`pip check` 通过。
- [真实通用浏览器验收](smoke-001/result.json)：6 项通过；这只验证通用执行通道。
- [最终通用测试日志](unit-tests-final-001.log)：43 项通过；真实业务 UI 证据单独保留。
- [预先声明的重复计划](repetitions.json)：四个运行串行执行，不共享任务浏览器状态。
- [导出证据核验](evidence-audit-final-001.json)：9 个运行、88 次任务记录、396 次派发均有先行预测，88 个 trace ZIP 可读，2236 个本地证据链接存在。4490 个文本条目的限定 JWT 模式检查无发现，不是任意秘密的全面检测。
- [展示渲染核验](presentation-visual-001/result.json)无页面错误和横向溢出；首屏尚未加载的懒加载图片经[逐图滚动验证](presentation-visual-001/lazy-image-verification.json)全部正常，共 7 张。
- [服务清理记录](teardown-001.json)：实验服务已按所有者停止标记退出，12042 与 12138 端口均不再监听。

从仓库根目录按 [Harness README](../../README.md) 启动部署适配器，
在独立终端执行给出的原生 Playwright 命令。每次使用新的输出目录；
既有 `registration.json` 保存各次精确命令和输入哈希。
同一部署上的套件不能并行运行，因为独立重置使用同一运行数据库。
报告、DOM、截图及 trace 均保存在本地，查看展示不需要站点服务继续运行。

重新汇总与审查已有结果的命令如下，不会发起新业务操作：

```powershell
python harness/experiments/phase1-discogs-pw-20261020-1633/aggregate_runs.py --out harness/experiments/phase1-discogs-pw-20261020-1633/aggregate-NEW_ID.json
python harness/experiments/phase1-discogs-pw-20261020-1633/audit_artifacts.py --out harness/experiments/phase1-discogs-pw-20261020-1633/evidence-audit-NEW_ID.json
```

本轮仅为第一阶段源码可见开发与回归，不是阶段二隔离学习、未见组合泛化、
官方基准成绩或三阶段全部完成。独立上下文和可信脚本接口不是操作系统沙箱。
