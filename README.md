# Browser Meme

研究网页规则书与可执行行为模型，能否帮助 Agent 预测操作后果、识别需要阅读的新信息，并连续编写跨页面 Playwright 脚本。

## 当前研究方向：先探索表示，再验证 E/T/C

2026-10-23 的最新设计先比较规则书格式、可执行表示和抽象失真，再冻结方法做 E/T/C 对照。各组保留相同的 LLM 监督，分别记录代码原始预测和最终预测，检查错误模型是否被 LLM 补偿。**新方案尚未启动真实实验。**

设计要点、20＋200＋180 回合预算和同步缺口见[当前研究状态与交接](research/CURRENT_STATE_20261023.md)，也已加入[实验方案](实验方案.md)。用户报告的新文献笔记与完整协议尚未出现在本工作区和本次检查的远端 `main`；本提交不把这两份原件标为已上传。

## 已归档的探索与工具

- [组件合同探索交接包](harness/experiments/component-contract-pilot-20261023-01/published/README.md)：规则书、冻结模型、跨页脚本、逐版本结果及限制。
- [连续网页复现 Harness](harness/replica/README.md)：观察、预测、比较、预算、停读点和进程管理；含通用合同接口与离线测试。
- [研究目标](研究目标.md)、[协作约定](AGENTS.md)：研究边界、职责和独立评价要求。
- [通用 Harness](harness/README.md)、[环境准备](environment/README.md)：历史执行接口与依赖说明。
- [Veri-Env 派生实验与来源](veri_env/README.md)：原协议下的历史材料。

组件合同探索在一个站点取得过 11 动作跨页流程通过；最新完成的固定三任务评价为一条完成、两条停读。它仍是 `isolation_limited` 构造预实验，严格成绩为 `null`，不能证明模型提高了理解，不能替代新 E/T/C 对照。目标网站、私有 fixture、独立 oracle 与本机环境不在交接包中；克隆后可阅读和运行相应离线测试，完整网站重放还需部署适配。

## 旧第二阶段已退役

按用户本次清理要求，旧 Discogs 第二阶段结果及生成发布清单已从当前版本移除，原结果不再作为当前研究结论或第三阶段准入依据。保留通用代码和测试，历史材料可从旧提交恢复，见[清理说明](harness/experiments/phase2-discogs-20261021-01/README.md)。本次清理没有重写 Git 历史，也没有删除历史 Release。

## 第一阶段参考

- [复杂任务运行记录](harness/experiments/phase1-complex-pw-20261020-1815/RESULTS.md)
- [规则书](harness/sites/discogs/model/pw-complex-v001/rulebook.html)、[Playwright 脚本](harness/sites/discogs/model/pw-complex-v001/scripts.py)
- [操作及评价介入条件](harness/sites/discogs/model/pw-complex-v001/operation-and-intervention.html)
- [中文展示](harness/experiments/phase1-complex-pw-20261020-1815/solar-presentation/report.html)
- [第一轮覆盖实验及限制](harness/experiments/phase1-discogs-pw-20261020-1633/RESULTS.md)

HTML 报告需克隆后在本地浏览器打开。单个任务成功不能解释为全站覆盖；这些网站专属材料也不能提供给要求独立探索该网站的新学习者。

## 上传范围

本机 `work/`、凭据、运行数据库、私有站点适配和本轮原始浏览器轨迹不提交。本轮交接资料仅发布经过挑选的副本，文件范围和哈希以交接包清单为准。第三方来源与许可见 [SOURCE_MANIFEST.json](veri_env/SOURCE_MANIFEST.json)；既有第三方凭据排除规则见[首次上传说明](UPLOAD_NOTES.md)。

`.gitattributes` 关闭自动换行转换，保留冻结文件字节。新实验使用新编号与输出目录；网站规则、测试答案和评价器访问权限仍须由实验协议隔离，GitHub 的可见性不代替实验隔离。
