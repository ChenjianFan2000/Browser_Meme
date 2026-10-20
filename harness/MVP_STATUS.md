# 阶段一 MVP 交付状态 — 2026-10-20

通用 Harness 和独立 Solar 生成的首版模型已交付；完整目标网站 UI 测量尚未开始。当前没有任务成功率、规则预测准确率或网页端到端速度成绩。

## 已交付

| 项目 | 产物与状态 |
| --- | --- |
| 通用入口 | [README.md](README.md)、[launch.py](launch.py)：准备依赖、监督站点、浏览器验收、执行、清理 |
| 执行与验证协议 | [CONTRACT.md](CONTRACT.md)：预测先落盘，再执行、等待、回读、独立终点评价；保留失败和固定分母 |
| 首个现有复杂网站 | [Discogs 交付说明](sites/discogs/README.md)：完整目录及市场前后端，保留 110 个上游文件 |
| 独立初始模型 | [v001/bundle.json](sites/discogs/model/v001/bundle.json)：8 个固定任务、47 步 UI 操作、10 条源码支持规则 |
| 生成来源 | [provenance.json](sites/discogs/model/v001/provenance.json)：独立 `gpt-6.1-sol` subagent，非 API 调用 |
| 结构验收 | [验收记录](handoffs/discogs-v001-accepted-20261020.json)：`validated_pending_execution`，不表示规则已获真实网站验证 |
| 环境预检 | [可读报告](runs/discogs-preflight-20261020-mvp/report.html)、[原始记录](runs/discogs-preflight-20261020-mvp/preflight.json)：`blocked`，`measurement_status=not_started` |

首版 bundle 的 SHA256 为 `d82b0ffbff4afd05465f67aed882e639da402408c2225425c69a521a3715232a`，验收时保持不变。网站选择、部署评估与规则脚本分别交给独立 subagent；协调者只维护通用基础设施，没有手工补写网站规则、选择器、预测或修订。

初次生成由本次会话直接派发，文件交接 CLI 随 MVP 建成；验收记录是生成后的结构验收，不伪装成生成前预注册。来源文件哈希反映模型读取时的版本，随后通用文档与部署启动配置有增补，原始 provenance 不追溯改写。未开始真实 UI 执行，未发生业务模型修订。模型 token 和费用未由运行接口提供，保持未知。

## 实际验证

| 检查 | 实际结果 | 解释边界 |
| --- | --- | --- |
| 通用核心与生命周期测试 | 34 项通过 | 使用模拟浏览器或模拟进程，不代表真实 UI |
| Python 编译、入口帮助与模型结构 | 通过；8 任务、47 步、10 规则 | 结构合法不证明业务预测正确 |
| 原始后端迁移与种子 | 成功；30 用户、221 唱片、639 报价、120 订单 | 使用独立离线 venv 和 SQLite |
| 原始 API 与独立评估器 | 健康、登录拒绝/成功、真实收藏写入、观察只读、写入后重置均通过 | FastAPI TestClient 组件测试，不是浏览器操作 |
| 评估拒绝条件 | 目标未达成会失败；API 达成但缺 UI 证据仍失败 | 不用模型预测作为评估真值 |
| 重置与源码完整性 | 八例重置哈希一致；110 个上游文件及运行副本保持一致 | 不表示八例 UI 已执行 |
| 部署生命周期 | 停止文件、启动中断、拥有进程回收及无关进程保留通过 | 使用实际休眠 Python 子进程；未启动完整网站 |
| Chrome 通用真实验收 | 两次尝试失败 | `Page.enable` 连接中断，Chrome 日志记录 GPU 进程访问拒绝 |
| 最新目标环境预检 | 网站和 CDP 端点均不可达，输入完整性通过 | 未重置业务、未派发任务、未调用模型 |

通用检查的 [原始日志](runs/mvp-acceptance-20261020/unit-tests.log) 与 [验证清单](runs/mvp-acceptance-20261020/verification.json) 已保存。后端及生命周期的实际证据另存不可覆盖的本轮副本：

- [后端/API/重置验证](runs/mvp-acceptance-20261020/component_evidence/backend-offline-validation.json)
- [部署进程生命周期验证](runs/mvp-acceptance-20261020/component_evidence/lifecycle-validation.json)
- [依赖安装来源](runs/mvp-acceptance-20261020/component_evidence/offline-install-provenance.json) 与 [完整实际版本](runs/mvp-acceptance-20261020/component_evidence/offline-python-inventory.json)
- [运行副本源码清单](runs/mvp-acceptance-20261020/component_evidence/source_manifest.json)
- [首次浏览器验收失败](runs/browser-smoke-20261020-01/result.json) 与 [第二次失败](runs/browser-smoke-20261020-02/result.json)

## 当前阻碍

本轮实际工具进程仍为 `codexsandboxoffline`，`CODEX_PERMISSION_PROFILE=:workspace`，`CODEX_SANDBOX_NETWORK_DISABLED=1`。用户已经表示在界面开启完整权限，但这个进程仍收到上述限制；这不是实验协议要求使用 sandbox。

完整前端依赖不在本机缓存中，缺少 Next.js/SWC；此前依赖下载收到套接字权限拒绝。安装提权请求被自动审批的 `sandbox_approval=false` 拒绝；浏览器 MCP 新建页面请求另被 `approval policy is never` 拒绝。两次本地 Chrome 验收也未成功。未绕过权限、关闭 Chrome 安全沙箱、替换网站或把离线 API 成绩冒充 UI 成绩。

最新预检只读取本地端点，不再次尝试被拒绝的下载或浏览器启动。模型任务成功率和步骤预测匹配率均为 `null`，不是 0%。基础设施故障不触发网站规则修订。

## 恢复执行

当执行进程实际获得依赖源访问和正常 Chrome 运行能力后，从仓库根目录使用已经准备好的入口，不需要模型 API Key：

```powershell
python -m pip install -r harness/requirements.txt
python -m harness.launch --site harness/sites/discogs/site.json --bundle harness/sites/discogs/model/v001/bundle.json --out harness/runs/discogs-v001-NEW_RUN_ID
```

每次使用新的运行标识。启动器会先运行真实浏览器通用验收，只有通过后才执行八个固定任务。若真实业务反馈需要修订，继续通过独立 Solar subagent 生成新版本；首次结果与最多两轮修订结果分开保存。

完整 `launch` 链条尚未在可用网站/浏览器环境中完成实测。八例也不代表完整操作覆盖；阶段二隔离与探索、阶段三组合泛化、在线适应和严格速度对照均未开展。
