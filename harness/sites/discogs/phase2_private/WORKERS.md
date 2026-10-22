# 三worker管理部署（不交学习者）

`parallel-workers-v001`复制既有`phase2-routing-v002`源码、生产构建、依赖、公开装饰图片cache及原始baseline。三个worker的源码/构建manifest哈希与父站点一致，每个有20,041依赖文件独立哈希验证、独立DB/前端可写cache/日志；没有链接任何可写DB。原pilot服务及数据库内容未访问或修改，仅比较DB文件元数据来证明文件ID不同、link count为1。

| worker | runtime后缀 | 前端端口 | 后端端口 | 当前launcher | backend | frontend |
| --- | --- | --- | --- | --- | --- | --- |
| a | phase2-eval-worker-a | 13042 | 13138 | 21248 | 15028 | 20612 |
| b | phase2-eval-worker-b | 14042 | 14138 | 30972 | 25504 | 33744 |
| c | phase2-eval-worker-c | 15042 | 15138 | 13520 | 25780 | 33680 |

每个runtime均在`G:\Browser_Meme\.runtime\`下；本轮停止marker为各runtime的`stop-acceptance-002`。最初启动失败轮及其旧PID保留；当前权威归属看`readiness.management.json.services`或最新`pids-<launcher>.json`，不要把首次尝试的历史`pids.json`当当前进程。创建对应marker后launcher只清理自己所属子进程。未来重启选择新的不存在marker，PID会改变，不复用本轮PID数值。

管理命令：

```powershell
# prepare已执行，拒绝覆盖；不重建源码/生产构建。
python harness/sites/discogs/phase2_private/worker_deploy.py status --worker a
$env:HARNESS_STOP_FILE='G:\Browser_Meme\.runtime\phase2-eval-worker-a\stop-UNIQUE'
python harness/sites/discogs/phase2_private/worker_deploy.py serve --worker a
python harness/sites/discogs/phase2_private/driver.py --runtime G:\Browser_Meme\.runtime\phase2-eval-worker-a reset-learning --seed 1
python harness/sites/discogs/phase2_private/driver.py --runtime G:\Browser_Meme\.runtime\phase2-eval-worker-a reset-case --id CASE_ID
# begin/finish等其他driver子命令同样在--runtime后使用，输出只能在选定runtime内。
```

`--runtime`也可由`BM_DISCOGS_PHASE2_RUNTIME`设置；只接受原v002及三个注册worker目录。ports由worker registry固定，不接受任意端口来绕过映射。root的每个relay分别固定到所属worker前端，同时保持学习者唯一可见origin为`http://127.0.0.1:12042`；gateway事件仍用这个可见origin调用ingest_http。每worker内部case串行，独立browser context/cookie，按seed配对在同worker上比较两组并保持相同初态/资源条件；不声称速度对照。

Node preload在冻结前端外实施通用连接映射：所有受支持的Socket连接只允许自己的loopback后端；冻结配置的原内部固定目标映射到所属后端，其他worker、原前端和外部地址均拒绝，caller lookup也无法换出loopback。HTTP、net、内置fetch/undici与TLS路径均真实验证。首版误处理Node内部已归一化参数，导致健康检查失败；失败日志与v001源码保留，当前preload为v002兼容修订。前端源码/构建未更改。

范围是**可信冻结Node站点进程的部署连接约束**，不是针对任意恶意原生Node代码的OS沙箱。实验学习者仍由root独立Linux访问边界隔离，无权运行或篡改这个前端进程。私有验收Node探针不作为学习者执行接口。

各worker真实探针验证自身业务写生效、其他两库完全不变；未匹配GET/POST请求经实际冻结fallback返回404且均落本worker，不产生写入。最终核查实际前端全部允许连接的目标均为自身后端。外部装饰图片请求在cache未命中时被策略拒绝，可能显示缺图；此限制明确登记，不改业务逻辑，三worker及两实验组采用相同策略。

三worker分别固定30例原生UI验收全部通过（90/90），副作用全部通过，各自11组管理CLI回归通过。每例保存真实前后管理snapshot、响应证据、截图、DOM和trace；绝不作为学习模型/官方基准成绩。验收后只重置三个worker到相同原始学习baseline，未遗留私有case状态。

launcher每250ms查询宿主可用RAM，低于3GiB就通过finally只停止所属worker；最多3个活动worker。初始边界验收可用RAM约7.27GiB，UI并行运行抽样约5.52GiB，完成后约7.03GiB；这是观察样本，不是完整峰值统计。资源竞争不用于速度论证，实际监督和重试耗时仍需计入正式预算。

管理汇总：各runtime的`readiness.management.json`，总汇总在worker-a的`parallel-readiness.management.json`。细节只在private目录，不给学习者。tokens与费用未知，保持null。
