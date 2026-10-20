# VeriEnv 与可执行网页模型研究

本工作区整合 VeriEnv 与网页世界模型相关文献、公开源码，以及无需 WebArena 的本地 issue 管理派生实验。

- [综合 HTML 报告](RESEARCH_REPORT.html)：12篇论文的方法和原始数值实验、本地逐篇测试、全部对照成绩、研究结论与下一步取舍；可离线阅读、检索和打印。
- [原研究目标](../研究目标.md)
- [本轮文献综述](LITERATURE_REVIEW.md)
- [实验协议](EXPERIMENT_PROTOCOL.md)
- [源码审计](SOURCE_AUDIT.md)
- [实验结果](EXPERIMENT_RESULTS.md)
- [原始组件执行与集成边界](UPSTREAM_INTEGRATION.md)
- [下一轮研究方案](NEXT_RESEARCH.md)
- [全部数值CSV](artifacts/results/summary.csv)与[结果图](artifacts/results/comparison.png)

`external/` 保存原始上游源码，修改与移植放在 `issue_lab/`；`papers/` 保存文献清单；`artifacts/` 保存原始请求、模型产物及结果。模型学习输入与评测器及答案分开存放。环境为自建 issue 子域，不是 GitLab 或 WebArena 的官方实现。

HTML报告由 `scripts/build_research_report.py` 生成；逐篇中文解读在 `papers/report_notes.json`，本地数字直接读取冻结的 `artifacts/results/summary.json`。运行 `python scripts/build_research_report.py` 即可重建，脚本先复核31份请求及31份产物的哈希，不调用模型、不改实验结果。构建来源记录在 `artifacts/report/build_manifest.json`。

本轮已完成12篇定向综述，下载10个额外主仓库与2个子模块（1877个源码/文本文件、12个ZIP），执行11个项目的原组件检查。统一实验运行7个代码条件、5个直接预测条件，共31次真实Luna子代理回合，已冻结原始请求与产物。完整原法训练/搜索没有被提示适配替代为“复现”；Code2World只做组件检查，未填写不适用的业务状态分数。

当前方案开发修正后一步24/24，多步完整预测6/12；规则适应后12/12，未变化案例21/21。直接Luna基线的一步/多步为24/24、6/12。当前结果不能证明代码方案优于直接预测，详见报告中的失败案例和预算差异。

## 使用

Python 3.11+即可运行环境和冻结评分。测试需要pytest；完整原组件审计另需numpy/scipy；绘图需要matplotlib。本机依赖已具备，版本记录在 `artifacts/runtime.json`。无需WebArena或模型API凭据来重放已保存结果。

```powershell
python -m pytest tests -q
python -m issue_lab.replay replay
python -m issue_lab.report
python -m issue_lab.server
```

服务器地址为 `http://127.0.0.1:8877`，仅监听本机。若本轮后台实例还在运行，直接打开地址即可。管理员可使用 `integrations/verienv/websites/issue_lab/sdk/python/issue_lab_sdk/client.py` 的 `reset()` 重置；重置不是学习器动作。SDK与原版VeriEnv判定器的接法见[integrations/verienv/README.md](integrations/verienv/README.md)。

`python -m issue_lab.upstream_audit` 重放11个原始组件检查。`python scripts/download_sources.py` 从保留的GitHub payload重建、验哈希和打包源码；它不是联网安装器。源码ZIP位于[artifacts/source_downloads](artifacts/source_downloads)，固定commit、资产排除清单和校验值在[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)。图片、权重、ROM、大型回放/数据等未作为源码下载。

`artifacts/frozen_run.json` 固定31个请求/产物；`artifacts/data`是公开学习证据；`artifacts/private_eval`含答案，只用于评测。模型没有被手工修正；不要重新build数据或覆盖模型后混用本轮成绩。再次调用模型属于新实验，离线重放不会发起新Luna调用。

HTTP/SDK和评分共16项测试通过。浏览器UI验收未完成：agent-browser连接超时，备用Chrome MCP被自动审批拒绝（当前策略不允许审批）。本轮没有UI/API端到端速度成绩。
