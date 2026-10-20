# VeriEnv 本地 issue 子域集成

该目录遵循 VeriEnv 的 `websites/<site>/sdk/python/<package>/client.py` SDK 搜索布局，`site` 为 `issue_lab`。它不会覆盖原始 VeriEnv 代码包。

运行 `python -m issue_lab.server` 启动 `http://127.0.0.1:8877`。公开入口为 `GET /`、`GET /health`、`GET /api/state`、`POST /api/action`；评测管理员使用 `POST /admin/reset` 重置种子、角色和隐藏规则版本。SDK 的 `observe/step/reset` 与服务器使用同一业务实现。

`issue_lab/verienv_bridge.py` 直接加载用户代码包的原版 `judge_dsl.py`，执行 `parse_judge_spec` 和 `eval_rinfo_checks`。每次预测都进入这个原版判定器。为避免其大小写/空白归一化影响精确业务评分，判定对象是独立规范化后的完整状态 SHA-256；期望状态来自领域环境，不能来自待测模型。只把 issue 记录、标签、选择集合排序；评论、显示顺序及字符串保持原值。

`python -m issue_lab.replay replay` 会导出 `artifacts/private_eval/verienv_tasks.json`，包含48条固定任务的初始观察、动作序列和 VeriEnv rinfo 检查。它是评测私有产物，不能交给学习者。原始请求、冻结模型、轨迹与详细分数分别保存在 `artifacts/requests`、`models`、`private_eval`、`results`。

这属于 SDK、任务判定和本地环境集成。BrowserGym/Gym 环境注册、Playwright控制、VeriEnv的RFT策略训练未运行，不声称可直接执行作者全部训练入口。当前比较的是世界模型对固定动作的后果预测，不是自由导航agent成功率。浏览器自动化因当前工具连接和审批策略受限；已通过真实 HTTP SDK 测试，页面端到端交互仍待验收。
