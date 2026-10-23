# Playwright semantics v6：通用实现与控制验收

本工作仅使用自建通用 HTTP fixture、本机 Playwright 1.62.0 官方实现和 Harness；没有读取目标网站源码、目标规则或业务产物。指标含义与限制见 [方法审查](PLAYWRIGHT-ARIA-AUDIT.md)。本文件记录后来实际运行的通用控制，不能把方法审查中的“未运行 Browser”理解为本文件也没有运行。

## 冻结接口

- Runtime：`runtime_versions/evaluation-playwright-semantics-v6`，派生于冻结 `evaluation-helper-settle-v5`。
- 完整文件映射 SHA256：`7e4d07ccaf328f78b9461cd174244e60f0ba81fa0a60f702c27a9294c02c4f98`。算法为排序文件相对路径→内容 SHA256 映射的紧凑 JSON，再 SHA256。
- `trees.py` 与 v5 字节相同。仅改 `browser_runtime.py`、`settle.py`、接口文档和版本元数据；新增 `playwright_semantics.py`、固定 83 项 `SEMANTICS_ROLES.json`。没有修改旧 runtime 或 v2 runner。
- Aux：`private-trees/<obs-stem>/playwright-semantics.json`；checkpoint 的 `auxiliary.playwright_semantics` 给出文件名、schema、status。
- Schema：`playwright-script-semantics/v1`；`policy`、`status`、完整 `frames`、`unsupported` 与采集 `timing` 分离。每个 frame 保留 `key,parent,owner,url,name,root,snapshot`。
- `canonical_semantics(record, roots)` 返回不含时长的 schema/policy/status/frames/unsupported。controller 必须检查 confirmed、unsupported 为空，再 exact 比较；不能使用 contains matcher。只明确 URL 字段做 origin 映射。
- 本机 API 没有 `refs` 参数；调用 `aria_snapshot(mode="default", depth=None, boxes=False)`，该固定实现内部选择 refs:none。

稳定版本为 `single-lane-dom-ax-playwright/v2`：每次样本顺序采集一次完整 DOM/Chromium AX，再采集各 frame 的语义快照；连续联合签名稳定后，最终 checkpoint 再联合核验。**顺序采集不是原子快照**，没有额外双 DOM 捕获，也没有增加既有 30 秒总窗或 22 秒采样窗。完整 Chromium AX 仍参与同 lane 稳定性，即使新 controller 仅将跨 lane 原生 AX 作为独立诊断。

名称保护使用固定角色清单与 Playwright 相同 accessible-name 算法的角色定位器，拒绝任何超过 900 UTF-16 单元的名称。页面、frame、body、明确 URL 解析或完整树采集失败一律不可确认；不丢弃失败 frame 后继续判成功。

## 安全与签名时序

可信 collector 显式调用 runtime 保存的原生 `Locator.aria_snapshot`，避免公开读包装器在 `secret_values` 建立前后只对最终样本提前脱敏而改变联合签名。原始和 JSON/YAML 转义形式的口令值在 private aux 持久化前统一遮蔽。

新 `POLICY.security_projection` 在评分和安全反馈共用的 canonical 函数中，仅将明确 `/url` scalar（lstrip 后不区分大小写）以 `javascript:` 开头的值投影为 `javascript:[REDACTED_EXECUTABLE_URL]`；名称、文本中的 `javascript:` 保持原样。私有 aux 保留原执行 URL，完整原生 AX 不被该新投影修改。模糊 URL 解析不获通过。

这不是对继承 v5 所有公开观察 API 的完整安全修复：旧公开 `aria_snapshot` read wrapper、旧 `.ax.json` 仍有旧策略。v6 新 aux 是 private，安全反馈必须使用 canonical 函数。若将原生 snapshot 字符串作为新的 learner 公共接口，须另注册共享安全投影，不能直接公开 private aux。

## 实际控制与证据

证据根目录：`work/replica-pilot/playwright-semantics-v6-preflight/`。`READY.json` 只记录 collector 接受状态；完整 controller/worker pair 仍须单独验收，不能据此称整个 v3 已通过。

| 控制 | 实际结果与范围 |
| --- | --- |
| 同 app、2 个同源 frame 与 owner 拓扑 | 真实采集相等，public DOM 也相等。 |
| 原生重建同一无名 wrapper | 真实语义相等；本 fixture 完整原生 AX 也相等。未声称复现目标上的原生 AX wrapper 差异。 |
| role/name/disabled/checked/order/visibility/普通 live value | 7 项真实语义分项反控均不同；不是仅靠 public DOM 判失败。 |
| 外部 CSS 隐藏按钮 label | 两服务 HTML 与 stylesheet href 相同，完整 public DOM 相等，实际语义快照不同。该反控证明此分项能检出 DOM 属性文本相同下的可见性变化。 |
| 长名称 | 900 UTF-16 单元 confirmed；901 及 451 个 emoji（902 单元）实际 unconfirmed。 |
| 跨源 frame | 实际 unconfirmed，不跳过 frame。 |
| DOM 副作用 | refs:none/boxes:false 采集前后完整 public DOM/live state 相等。 |
| password/token canary | 两者确实出现在原生语义字符串；持久化 sanitizer 后都不存在。原生回调绕过公开 read wrapper 后语义签名保持一致。 |
| JS URL canary | 原生字符串确实含执行正文；新 canonical 中正文消失，业务文字中的 `javascript:` 保留。 |
| 缺 body | 实际不能确认：上游 full-tree 采集抛 Error，另次 semantics 返回 unconfirmed（移除 body 同时影响 iframe 拓扑）。 |
| 联合稳定/final gate | 普通单元实际调用 v6 `signature_payload` 与 `Runtime.finish_stability`：仅改 semantics 即改变 hash/final 拒绝；仅改 DOM live state 或原生 AX 也改变联合 hash。完整真实 pair 由 controller 验收。 |

普通单元最终 **18 tests + 41 subtests 通过，0.54 秒**。它们另覆盖明确 URL 边界、特殊字符解析拒绝、frame 拓扑、JS 安全投影正反控及原记录不变；不伪称这些字符串控制是浏览器实测。

真实组 `collector-003/results.json` 有 22 项通过，随后在缺 body 控制中因测试只预期返回 record、实际上游抛错而结束。`collector-004-tail/results.json` 的 600 控件正控通过，缺 body 返回 unconfirmed，但尾段断言额外要求特定错误 kind，故原始文件仍 `passed=false`。该要求比预注册“缺失或采集失败必须拒绝”更窄；测试断言已修为接受 unconfirmed 且 unsupported 非空。**保留原始失败文件，没有重写成全绿，没有为通过而放宽 runtime，也没有重复浏览器运行已充分拒绝的负控。** READY 逐项说明接受依据。

600 控件 + 同源 frame 的真实耗时：名称 guard **0.406 秒**，新增语义采集总 **0.969 秒**，完整 DOM/AX **4.369 秒**。小 fixture 名称 guard 约 0.06–0.56 秒。这是通用样本的观测，不保证目标页面必在预算内；超时仍须失败。

## 仍需披露的限制

`collector-001/002` 的重复导航 iframe 场景触发继承 full-tree 捕获的 `Frame has been detached`，结果正确拒绝。后续分项控制改在同 Browser 的新 page 中独立构造状态，以隔离语义检测能力；这**没有解决或证明跨导航 iframe 捕获可靠**。原始失败保留，旧 trees 未改。

所有本 agent 的直接 Browser 都在 finally 中关闭。这不等于 worker 清理回执或外部进程树验收；后者由完整 paired 控制另做。新补充指标仍不是完整原生 AX/AT 等价，也不能弥补名称外其他角色状态/完整关系/焦点的损失；full public DOM/live props、动作身份、独立业务真值须继续全检查。
