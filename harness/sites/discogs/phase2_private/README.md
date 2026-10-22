# 第二阶段管理侧私有适配

此目录仅供部署管理员和独立评估进程读取，不得挂载给学习者。作者上下文已读取目标源码及历史评价资料，不能作为第二阶段学习者。

- `deploy.py`：固定新 runtime，复用并哈希校验原生产构建、110 个上游源码文件、Python 依赖和原始基线，不更改站点版本。
- `build_inventory.py`：一次性建立私有30例及逐例初态；拒绝覆盖已有初态。任务只约束目标与参数，不提供执行脚本。
- `evaluator.py`：`reset(case)`、`observe()`、`evaluate(case,before,after,ui_evidence)`；读取评分数据库均使用 SQLite `mode=ro` 与 `query_only=ON`，重置单独执行。`public_case(case)` 仅投影 id/goal/parameters。`attach_ui(page)` 由可信管理浏览器宿主在动作前绑定，只保存非认证响应元数据及必要的非敏感目标参数。
- `validate_components.py`：在本轮 runtime 的临时数据库验证组件，不访问旧可变数据库，不启动服务，不运行浏览器。

从仓库根目录执行：

```powershell
python harness/sites/discogs/phase2_private/deploy.py inspect
python harness/sites/discogs/phase2_private/deploy.py prepare
```

`prepare` 本轮已成功执行，服务未启动。正式启动必须由主 Harness 在隔离核验后执行，设置位于本轮 runtime 的唯一且不存在的 `HARNESS_STOP_FILE`，再调用 `deploy.py serve`。固定服务地址为主机回环前端12042、后端12138；端口占用会拒绝启动，不复用其他运行服务。共享依赖与构建不构成严格速度对照。

管理宿主流程：获取排他运行 lease → 关闭前例全部浏览器上下文 → reset(case) → before=observe() → 创建独立浏览器上下文并绑定 attach_ui → 只发 public_case 给冻结学习者 → 执行原生 Playwright → 管理宿主保存截图、轨迹、事件和终止原因 → after=observe() → evaluate。before/after 与评估器、初态、目标真值均不得发给学习者。每个独立学习种子重复使用同一清单和初态，所有失败/拒绝/未知/超时保留30分母，冻结与适应运行分别归档。

评价真值来自管理侧真实状态和可信UI响应，既不读取学习者模型也不读取其预测来确定目标。截图路径仅作证据存在性检查，文件内容与事件来源真实性由可信宿主保证，不可把学习者自行提交的文件和事件当作可信证据。UI侧没有证据时，初态本已满足的任务不会自动通过。未执行的正向任务会失败。schema之外的任意UI声明先记 `unscorable`，不以模型自身断言补真值。

通用预测契约：`disposition=accepted|rejected|unknown`；`effects.persistent_state_changed` 为 boolean/null；`effects.affected_record_count` 为 integer/null；`ui_claims` 和 `unknowns` 为数组。changed/count 表示本次目标操作的持久业务记录变化，不包含浏览器缓存、cookie或认证。记录更新计一条；非目标表变化仍判副作用失败，无法精确计数时为 unscorable。每例只在同一 before/after 操作边界评价此预测；多步脚本必须另留逐步预测和证据，不得将全流程预测误称逐步预测准确率。

本轮组件验证实际通过6组，日志位于 `.runtime/phase2-discogs-20261021-01/private/component_checks/result.json`。首次组件检查发现 Python 默认路径捕获导致临时库观察错误，以及 SQLite 连接上下文未关闭文件句柄，已修正并重跑通过。组件中的模拟响应不是实际 UI 成功证据。

私有清单锁定不等于执行就绪：当前30例均未现场UI检查；历史动态路由阻碍需在原版本启动后复核，不能移除失败例。源码支持的参数有效性不证明当前生产UI业务生效。主动学习后还须审计参数/状态/组合是否已在探索出现；重叠会使新颖性标签失效，不得事后换题。现有操作家族覆盖有限，不能宣称全站覆盖、官方基准或严格速度成绩。
