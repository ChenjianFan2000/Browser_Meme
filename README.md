# Browser Meme

网页理解与可执行行为模型实验工程。当前方案通过规则书、原生 Playwright
脚本、独立评价和必要的模型介入，研究可预测、可执行、可监督并持续修正的
浏览器操作。

## 阅读入口

- [实验方案](实验方案.md)与[研究目标](研究目标.md)：三阶段实施方案、研究边界和评价设计。
- [协作约定](AGENTS.md)：主 Agent 负责通用 Harness；独立 `gpt-6.1-sol`
  负责网站源码阅读、规则书和原生 Playwright 脚本；独立上下文负责评价。
- [Harness](harness/README.md)：执行、证据采集、冻结、回归和监督接口。
- [环境准备](environment/README.md)：WSL、依赖锁、站点部署和恢复命令。
- [历史派生实验](veri_env/README.md)：文献、固定来源的上游源码、issue 子域实验和原始结果。

## 第二阶段：浏览器信息可见的主动探索

- [第二阶段中文实验报告](harness/experiments/phase2-discogs-20261021-01/reports/第二阶段实验报告-001.md)
- [结案、独立审核与第三阶段交接索引](harness/experiments/phase2-discogs-20261021-01/reports/第二阶段结案索引-001.md)
- [单任务完整证据示例](harness/experiments/phase2-discogs-20261021-01/reports/evidence-example-001.md)
- [全量结果 Release](https://github.com/ChenjianFan2000/Browser_Meme/releases/tag/phase2-discogs-20261021-01)及[分卷校验、恢复和脱敏说明](harness/publication/phase2_20261022/README.md)

6 个学习包、180 个首次冻结评测案例已完成并保留全部失败与未知结果。
任务成功 176/180；540 个整任务预测字段中正确 236、未知 304。
两个学习包因学习期停止违规被隔离，只有种子 1729 构成完整合规 A/B 配对。
四包获第三阶段准入；第三阶段尚未启动，本轮不构成严格速度对照或全站覆盖。

Git 保存源码、协议、报告和证据示例；全部轨迹、截图、逐例产物及管理验收证据由
Release 分卷提供。会话认证值在公开副本中脱敏，双哈希映射解释与原始冻结清单的差异。
首次冻结评测完成后的公开发布不改变后续学习者的访问白名单。

## 第一阶段浏览器实验

- [复杂任务运行记录](harness/experiments/phase1-complex-pw-20261020-1815/RESULTS.md)
- [规则书](harness/sites/discogs/model/pw-complex-v001/rulebook.html)
- [完整 Playwright 脚本](harness/sites/discogs/model/pw-complex-v001/scripts.py)
- [操作及评价介入条件](harness/sites/discogs/model/pw-complex-v001/operation-and-intervention.html)
- [中文展示](harness/experiments/phase1-complex-pw-20261020-1815/solar-presentation/report.html)
- [逐步执行证据](harness/experiments/phase1-complex-pw-20261020-1815/execution-001/task-budgeted_two_seller_purchase.html)
- [第一轮覆盖实验及限制](harness/experiments/phase1-discogs-pw-20261020-1633/RESULTS.md)

HTML 报告需克隆仓库后在本地浏览器打开，关联截图、DOM 和轨迹保留在相邻目录。
单个任务的成功不能解释为全站覆盖或官方基准成绩；历史失败和拒绝分支保留。

## 仓库范围与复现

仓库保留源码、依赖锁、规则与模型版本、实验协议、冻结快照、报告、截图、
浏览器轨迹、历史请求与评测记录，以及固定来源的上游源码与文献材料。
上游来源和版本见 [SOURCE_MANIFEST.json](veri_env/SOURCE_MANIFEST.json)，
第三方文件保留各自的许可和来源声明。
第三方材料中发现的疑似凭据原件排除出 Git；保留去除凭据的阅读副本，
具体范围及复现影响见 [首次上传说明](UPLOAD_NOTES.md)。

`.runtime/`、虚拟磁盘、下载与安装缓存、虚拟环境、`node_modules/`、运行数据库、
进程标记和本机凭据不提交。克隆仓库不会同时恢复本机运行环境；按环境说明及
相应实验的 `RESULTS.md` 准备依赖和站点，凭据仅在本机配置。

`.gitattributes` 关闭自动换行转换，以保留冻结材料的字节及哈希。
新实验必须使用新的运行编号和输出目录，不覆盖历史产物。
`private_eval/` 和 `private-supervision/` 是评价材料；后续阶段的学习者仍须按
协议隔离访问，仓库私有权限不等于实验中的进程与文件隔离。
