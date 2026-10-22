# 管理CLI（不提供给学习者）

`driver.py`只封装既有评价语义。固定使用`BM_DISCOGS_PHASE2_RUNTIME=G:\Browser_Meme\.runtime\phase2-routing-v002`（未设置时也只默认此已注册runtime），不构建、不更改案例、不修改既有freeze。每条命令可给`--output`，只能位于本runtime且使用独占创建；省略时生成`private/driver/<command>-<uuid>.json`。stdout仅返回command/output/sha256/status，不输出私有快照或账号。

```powershell
$env:BM_DISCOGS_PHASE2_RUNTIME='G:\Browser_Meme\.runtime\phase2-routing-v002'
python harness/sites/discogs/phase2_private/driver.py inventory-public --output G:\Browser_Meme\.runtime\phase2-routing-v002\private\public-inventory-UNIQUE.json
python harness/sites/discogs/phase2_private/driver.py reset-learning --seed 1
python harness/sites/discogs/phase2_private/driver.py reset-case --id CASE_ID
python harness/sites/discogs/phase2_private/driver.py begin --id CASE_ID --prediction-file FROZEN_PREDICTION.json --output G:\Browser_Meme\.runtime\phase2-routing-v002\private\before-UNIQUE.json
# 以上begin必须在对应UI动作/流程前调用，再运行受限Playwright并保存可信gateway事件。
python harness/sites/discogs/phase2_private/driver.py finish --id CASE_ID --before G:\Browser_Meme\.runtime\phase2-routing-v002\private\before-UNIQUE.json --ui-evidence TRUSTED_UI_EVIDENCE.json --output G:\Browser_Meme\.runtime\phase2-routing-v002\private\evaluation-UNIQUE.json
python harness/sites/discogs/phase2_private/driver.py novelty-audit --learning-evidence PRE_FREEZE_LEARNING_EVIDENCE
```

每次reset先持有管理lease并关闭上一浏览器上下文。`reset-learning`从原始冻结baseline恢复；`reset-case`从固定私有case初态恢复。`begin`保存管理snapshot及动作前预测的内容/hash/来源/时间；不提供预测则预测分项保持unknown。`finish`只从begin取得预测，拒绝事后inline prediction，不再读取可变预测源文件。before记录须留在本runtime；管理方负责其不可由学习者修改。finish在真实网站只读观察后调用原evaluate，保留after_snapshot用于独立复核。

`ui-evidence`为JSON object：`events`数组（每项必须来自管理hook并有`source=trusted_browser_gateway`）、`screenshot_path`（导出至本runtime的真实截图）、可选`ui_error`。不得包含inline `prediction`。事件来源标记不是密码学证明，隔离/可信宿主/trace证明由主Harness负责；不得把学习者自行声称来源的数组当成可信事件。脚本直接业务API仍禁止。

结果schema：`kind=independent_case_evaluation`、`case_id`、`runtime`、`evaluated_at`、`before_file_sha256`、`ui_evidence_sha256`、`prediction_provenance`、`evaluation`、`after_snapshot`、`denominator_retained=true`。其中evaluation保留原`task_outcome`、`business_disposition`、`transport_disposition`、`side_effects_ok`、`prediction_grading`、`checks`。快照/检查项含私有真值，不交学习者；首轮冻结评价不反馈逐例实际结果给后续案例生成上下文。

公共inventory只返回数组，每项严格包含`id:string`、`goal:string`、`parameters:object`。通用parameters值可为null/boolean/number/string/array/object；本清单目前全为空object，具体目标参数在goal文本中。在模型/规则版本冻结后，可一次性交给固定执行脚本生成上下文；执行仍须每例独立reset/context，且不得根据前例反馈修改模型再称首次泛化。批量交付暴露整体测试分布，需记录这一配置。

`novelty-audit`只做保守暴露检查：输入单文件或目录中的JSON/JSONL/TXT/MD/HTML/PY证据，记录输入哈希并查找目标公开对象/标题的精确迹象。命中标为possible exposure，未命中仍不能证明新颖。所有案例默认`novelty_claim_permitted=false`，必须独立审阅动作trace、状态和组合是否在冻结前演示。不得将截图缺乏可检索文字造成的未命中当作未见证明。输入应仅包含冻结前学习证据，不包含之后发布的测试任务或执行脚本。

组件验收已在临时DB通过6组，真实active DB未触及；涵盖独占输出、30例公共投影、动作前预测冻结、拒绝伪来源、保守新颖性判定。无额外网站运行或模型成绩。

## 逐例可信broker动作前声明（driver-002）

原`finish`不提供`--prediction-record`时行为保持不变。新流程先`reset-case`，再`begin --id CASE_ID --output BEFORE.json`（此时可无预测）；学习者通过唯一MCP声明工具声明预测。Windows可信管理进程将以下JSON独占写入本runtime的private目录后再ack学习者：

```json
{
  "source": "trusted_browser_broker",
  "case_id": "CASE_ID",
  "before_sha256": "BEFORE_FILE_BYTES_SHA256",
  "declared_at_ns": 0,
  "declaration_count": 1,
  "prediction": {}
}
```

其中时间必须由Windows管理进程`time.time_ns()`生成，不能信任模型或Linux时钟。`before_sha256`绑定当前不可改写before文件；case_id绑定当前实例。重复声明由可信broker拒绝。begin新记录含管理侧`captured_at_ns`（真实snapshot读取完成后的时间）；旧before记录不含该字段时仍可原方式finish，但不能用于新broker预测评分。

```powershell
python harness/sites/discogs/phase2_private/driver.py finish --id CASE_ID --before BEFORE.json --ui-evidence TRUSTED_UI.json --prediction-record BROKER_RECORD.json --output EXCLUSIVE_RESULT.json
```

新模式只使用该broker记录，不回退选择begin内已有预测。检查记录必须位于本runtime、有可信source、case与before哈希匹配、预测为object、单次声明、声明不早于begin且不在未来。每个相关业务写事件必须有`management_request_started_ns`：由同一Windows管理时钟在转发网站HTTP请求前生成。`management_received_ns`仍可记录响应后时间，但绝不参与预测有效性判断。声明必须严格早于所有相关业务写的最早started时刻；相等亦无效。独立私有边界将认证和查询排除，错误对象/错误动作的业务写仍参与，防止先写错再补预测。

缺失/不可读记录、缺时间、迟到、无写请求可验证、错误绑定或来源等均产生`prediction_provenance.status=invalid`和明确reason；`prediction_grading`保持unknown。任务完成、拒绝和副作用评价继续原语义，不因预测无效而跳过或追溯修改。有效时provenance额外记录record独立hash、declared_at_ns和first_business_write_started_ns。before从未修改，旧结果不覆盖。

时序可靠性边界：

- gateway必须保留每次已开始的业务请求，包括失败、pending、超时或响应丢失的请求（可用status=0），否则漏掉更早写请求可能错误接受迟到声明。
- 请求和声明必须由同一Windows管理进程/时钟排序；系统时钟回拨或异常会导致无效，不能静默调整时间补成绩。严格因果性还依赖broker串行接收/记录/转发和声明ack顺序。
- JSON中的source字符串不是来源证明。记录/事件/before不可由学习者写入，OS隔离与独占broker工具通道由主Harness保障。
- 同case的后台异步请求和重定向触发写入也须完整记录；结束后应清空/终止请求并关闭上下文后再重置下一例，防止旧请求越界污染新初态。
- 本接口不自行运行LLM或任务，不将监督调用、预测声明的耗时移出真实执行预算。全流程预测与逐动作预测仍须按各自边界解释。

新增组件已在临时DB验证11组：覆盖原finish回归、可信声明、严格先后、认证/查询排除、更早错误业务写、缺失事件时间、无写证据、重放绑定与来源拒绝。未启动任务或触及active DB。
