
## 管理重置安全屏障（reset-safety-v001）

finish新增顶层`safe_to_reset:boolean`和`reset_safety:object`；`evaluation.management_safety`与reset_safety同内容。原任务/预测评分字段保留。controller只能在顶层严格`is True`且自身可信barrier全真时开始下一次reset；不得用缺失字段、进程wrapper返回0或当前DB快照代替证明。

UI evidence须由可信管理进程加入：

```json
{"management_barrier":{"relay_drained":true,"browser_tree_clean":true,"gateway_log_complete":true}}
```

`browser_tree_clean`应引用可信进程guard的nonce/PID专用清理成功收据，不能来自学习者或controller直接猜测。driver自动使用不可改写before中的captured_at_ns作为case时间边界。完整日志中的每个业务请求必须唯一配对`event_phase=dispatch,status=0`与其后的终态response；用(method,path,management_request_started_ns)关联。认证/查询排除，未识别的API写保守纳入。缺/重复/孤儿/倒序记录、旧case时间、缺cleanup/log证明、5xx/超时/未注册响应都返回false/unknown。管理诊断只使用请求引用hash，不向learner提供真值。

`reset_safety`字段：version、safe_to_reset、status（confirmed|unknown）、case_result_final、business_request_groups、business_events、unconfirmed_request_groups、reasons[]、request_diagnostics[]、recovery_policy、assumptions[]。这是基于完整可信日志与冻结站点控制流的管理判断，不是独立OS静止证明。

unsafe时先冻结case summary/manifest并停止调度；恢复时也不能跳过unsafe继续reset。原case固定分母保留，raw task_outcome和prediction_grading留作暂态证据；不得计确认成功或预测正确/错误。显式预测在汇总记unscorable，原unknown仍unknown。缺例/未运行/未声明则保留管理状态及3个预测unknown，整轮未执行不报模型实测率。

未确认业务写的恢复必须另外登记：保留原unsafe评价hash与原因，停止/等待受影响browser及**所属前端和后端完整进程树**退出（核对PID及创建时间防PID复用，检查原端口无遗留listener），确认SQLite无人持有后才可恢复原baseline并以新唯一stop marker重新启动、健康检查及按需回归。仅关闭客户端连接、HTTP超时、relay.active清零，甚至随后读到某个DB值，都不能证明原后端不会晚写。不能重放原写或补证后追溯提高首次成绩；恢复记录与下一例初始化另留版本。

验证：6组reset-safety组件含真实HTTP客户端超时后后端晚写临时SQLite的反例，标记在超时后/晚写后/服务关闭后均不自动提升。12组私有CLI回归含顶层/嵌套标记一致、失败任务可安全重置、缺终态写不能重置及before哈希不变。所有测试仅触临时DB和临时通用HTTP服务，不触活动站点、正式case或学习包。
