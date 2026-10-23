# 旧第二阶段通用 Harness

本目录负责独立模型启动、浏览器观察策略、操作系统权限、原生 Playwright 记录、不可变产物、预算及独立评价调度。
不包含目标网站规则、选择器、参考答案或任务脚本。网站部署与真值检查由 `../sites/discogs/phase2_private/` 的独立评估实现承担。

[旧第二阶段实验已退役](../experiments/phase2-discogs-20261021-01/README.md)，其协议、运行记录与验收产物已从当前工作树移除。本目录保留通用实现和测试，以下描述属于旧接口，不代表新研究方案已实施或完成。当前研究入口见[仓库 README](../../README.md)。
[隔离组件](../phase2_isolation/README.md)继续保留；旧验收结论不自动适用于新的运行环境。

## 依赖及访问边界

旧管理程序使用 Windows Python 标准库；通用测试使用 pytest。旧浏览器执行环境为 `BrowserMeme-Ubuntu`，
使用 `/opt/browser-meme/envs/core` 的 Playwright 1.44 与 Chromium 1117。
当时的独立模型配置为 Linux Codex CLI 0.163.0 和精确 `gpt-6.1-sol`。这些版本与访问边界须在复用前重新验收。
`management.py` 按内容哈希部署通用代码，不覆盖旧版本；每个模型会话创建全新配置目录并通过私密管道放入现有登录认证。
认证文件不写入实验归档。模型服务不可用时停止，不替换模型。

学习者命令工具与浏览器脚本各有独立的文件/进程/网络 namespace。只有浏览器执行进程可连接单站点 socket。
可信 MCP broker 验证观察接口并保存原件；脚本 AST 检查不被当成操作系统隔离。
模型仍直接编写原生 Playwright Page/Locator 脚本，自行发现目标与业务操作。

## 管理命令

下列合成测试可从仓库根目录执行：

```powershell
python -m pytest harness/tests/test_phase2_records.py harness/tests/test_phase2_observation.py -q
```

以下是历史管理命令，不能直接执行。`relay_probe`、`control_probe` 与 `run_learning` 仍含旧实验默认路径；旧运行目录、协议与验收文件已移除。复用前须适配独立输出配置并重新登记协议、预算和验收，真实学习还会调用模型并修改实验站点状态：

```powershell
python -m harness.phase2.relay_probe
python -m harness.phase2.control_probe
python -m harness.phase2.status RUN_ID
```

历史学习命令形状如下；其中旧验收路径已失效。新的真实运行必须提供重新通过且代码哈希一致的独立验收文件：

```powershell
python -m harness.phase2.run_learning --run-id pilot-001 --condition A --seed 1729 --pilot --isolation-acceptance harness/experiments/phase2-discogs-20261021-01/isolation/learning-browser-mcp-acceptance.json
python -m harness.phase2.run_batch --schedule SCHEDULE.json --batch-id UNIQUE_BATCH_ID --stage all
```

旧编号 `pilot-001` 不应复用。调度遇到半完成目录会停止并要求单独恢复记录；不会覆盖旧实验。
独立评估逐例重置、保存基线、启动新 Solar 上下文、固定任务预测、执行并关闭浏览器，最后由管理侧独立读取真实状态评分。
同一 worker 严格串行，不同 worker 使用不同数据库。真实请求派发时间和预测声明时间均来自 Windows 管理时钟。
开始新案例前必须排空上一案例请求；无法确认时停止，不把未知计为成功。

## 历史产物约定

每轮保存注册、实际提示、运行命令、CLI 事件及实际 usage、原生脚本、动作前预测、页面/截图/AX/网络证据、原始私有轨迹、规则版本、失败及哈希清单。
模型可见证据必须与不可写的管理原件逐文件匹配。规则语义是否正确仍由独立网站检查决定，文件校验不能替代它。
冻结评价的 A 组调用固定模型 `predict`；B 组使用相同 LLM 监督和自然语言知识但没有该代码模型。
无实际调用数、token 或费用数据的字段保持 null，不估计账单。
