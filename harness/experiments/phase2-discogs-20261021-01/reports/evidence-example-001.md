# 单任务完整证据索引

运行：`a-seed-1729`；登记案例序号：`1`；案例 ID：`P01`。

选取规则：在最终准入包中优先 A 组，再按种子和登记案例序号选取首个有真实 UI 动作且安全结案的案例；不按成绩筛选。

这是管理侧只读索引。逐动作日志中的预测和分类保持原样；逐动作预测没有被本索引独立评分。案例级结论来自独立评估，执行无异常不等于预测正确。

独立任务结果：`passed`；业务结果：`accepted`；UI 动作：11；浏览器执行：4。

案例级三个预测字段的原始评分：

```json
{
  "disposition": "unknown",
  "persistent_state_changed": "unknown",
  "affected_record_count": "unknown"
}
```

原件入口：

- [完整冻结清单](../evaluations/a-seed-1729/case-01/case-manifest.json)；SHA256：`2c5372304cae442402aef2a5462d544866fe796099fbfcd1c38bd7f700caa565`。
- [独立评分与运行摘要](../evaluations/a-seed-1729/case-01/case-summary.json)。
- [当前案例登记、初态绑定与冻结输入](../evaluations/a-seed-1729/case-01/registration.json)。
- [完整模型与工具调用记录（含未分派的失败提交）](../evaluations/a-seed-1729/case-01/private/solar/events.jsonl)。
- [可信请求派发与响应记录](../evaluations/a-seed-1729/case-01/trusted-gateway.jsonl)。
- [浏览器退出与请求排空检查](../evaluations/a-seed-1729/case-01/management-barrier.json)。

学习规则书：[原始冻结规则书](../runs/a-seed-1729/workspace/revisions/002/rulebook.md)。

## call-001-f8474fb3

- [执行脚本与模块原件](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/job.json)。
- 脚本 SHA256：`96e5e08a63a4d4fc941b7646303d6054712d8d00935e451b556d47d37a06c193`。
- [完整观察、逐动作预测、等待耗时和错误记录](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/actions.jsonl)。

### 动作 1：`goto`

动作前预测（原样）：

```json
{
  "disposition": "unknown",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": [
    "Initial UI not yet inspected"
  ]
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/obs-0001.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/obs-0001.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/obs-0001.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/obs-0002.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/obs-0002.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/evidence/obs-0002.ax.json)。
- 原始执行耗时（秒）：`2.4745888449997437`。
- 原始执行错误：`None`。

该次执行的管理结果：[原始结果](../evaluations/a-seed-1729/case-01/private/browser/call-001-f8474fb3/management-result.json)。

## call-002-66834fb3

- [执行脚本与模块原件](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/job.json)。
- 脚本 SHA256：`d858e008befe7469a67a8086f1603451a0b7a937fc64c157f334a8440004e091`。
- [完整观察、逐动作预测、等待耗时和错误记录](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/actions.jsonl)。

### 动作 1：`goto`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0001.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0001.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0001.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0002.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0002.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0002.ax.json)。
- 原始执行耗时（秒）：`1.317742506000286`。
- 原始执行错误：`None`。

### 动作 2：`fill`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0004.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0004.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0004.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0005.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0005.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0005.ax.json)。
- 原始执行耗时（秒）：`0.8081685270003618`。
- 原始执行错误：`None`。

### 动作 3：`fill`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0006.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0006.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0006.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0007.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0007.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0007.ax.json)。
- 原始执行耗时（秒）：`0.9370486650000203`。
- 原始执行错误：`None`。

### 动作 4：`click`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [
    "Sign in reaches home; Account button appears"
  ],
  "unknowns": [
    "Only supplied valid account was learned"
  ]
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0008.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0008.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0008.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0009.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0009.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0009.ax.json)。
- 原始执行耗时（秒）：`1.4420290540001588`。
- 原始执行错误：`None`。

### 动作 5：`goto`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0011.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0011.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0011.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0012.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0012.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0012.ax.json)。
- 原始执行耗时（秒）：`1.8152956330000052`。
- 原始执行错误：`None`。

### 动作 6：`goto`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0014.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0014.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0014.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0015.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0015.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/evidence/obs-0015.ax.json)。
- 原始执行耗时（秒）：`1.139660659999663`。
- 原始执行错误：`None`。

该次执行的管理结果：[原始结果](../evaluations/a-seed-1729/case-01/private/browser/call-002-66834fb3/management-result.json)。

## call-003-ac0bf639

- [执行脚本与模块原件](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/job.json)。
- 脚本 SHA256：`049a15cb2141d931280ed6c07f4f1c7e015d8cb3e06156cf969ef35cbcc39b14`。
- [完整观察、逐动作预测、等待耗时和错误记录](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/actions.jsonl)。

### 动作 1：`goto`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/obs-0001.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/obs-0001.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/obs-0001.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/obs-0002.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/obs-0002.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/evidence/obs-0002.ax.json)。
- 原始执行耗时（秒）：`1.1441929379998328`。
- 原始执行错误：`None`。

该次执行的管理结果：[原始结果](../evaluations/a-seed-1729/case-01/private/browser/call-003-ac0bf639/management-result.json)。

## call-004-43275712

- [执行脚本与模块原件](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/job.json)。
- 脚本 SHA256：`547ef30b6b827fec915ea1ea1c5da43753cce76f00cd7c1776b5dd23bc0beb9c`。
- [完整观察、逐动作预测、等待耗时和错误记录](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/actions.jsonl)。

### 动作 1：`goto`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0001.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0001.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0001.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0002.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0002.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0002.ax.json)。
- 原始执行耗时（秒）：`1.3918490129999554`。
- 原始执行错误：`None`。

### 动作 2：`click`

动作前预测（原样）：

```json
{
  "disposition": "unknown",
  "effects": {
    "persistent_state_changed": null,
    "affected_record_count": null
  },
  "ui_claims": [],
  "unknowns": [
    "Only authenticated additions for release 221 were tested."
  ]
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0003.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0003.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0003.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0004.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0004.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0004.ax.json)。
- 原始执行耗时（秒）：`1.028871056999833`。
- 原始执行错误：`None`。

### 动作 3：`goto`

动作前预测（原样）：

```json
{
  "disposition": "accepted",
  "effects": {
    "persistent_state_changed": false,
    "affected_record_count": 0
  },
  "ui_claims": [],
  "unknowns": []
}
```

- 动作前观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0006.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0006.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0006.ax.json)。
- 动作后观察：[DOM](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0007.html) / [截图](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0007.png) / [无障碍树](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/evidence/obs-0007.ax.json)。
- 原始执行耗时（秒）：`1.4871708939999735`。
- 原始执行错误：`None`。

该次执行的管理结果：[原始结果](../evaluations/a-seed-1729/case-01/private/browser/call-004-43275712/management-result.json)。

## 核对信息

原始动作前记录 11 条，动作后记录 11 条；摘要登记 11 个动作。

完整结果与准入依据：[180 例原始统计](frozen-results-001.json)；[逐包准入及隔离索引](../handoff/phase3-001.json)。

私有真值原件的长期归档由最终独立审核绑定，本索引不重新评分、不改写原始声明或学习包。
