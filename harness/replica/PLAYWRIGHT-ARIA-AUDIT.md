# Playwright ARIA snapshot 方法审查

结论：`locator.aria_snapshot()` 可作为新注册的“Playwright 脚本可访问语义”补充指标。它是 Playwright 从 DOM、ARIA 属性及 CSS 计算出的树，**不是 Chromium 原生 AX，也不能替代完整 AX 的严格比较**。本次只阅读本机官方包的接口文档与实现；未启动浏览器，未读取目标网站源码或私有证据，未修改 Harness 或门禁。

## 实现依据

本机 Playwright 版本为 **1.62.0**。下列路径统一位于：

`/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages/playwright/`

- `sync_api/_generated.py:19867`：`Locator.aria_snapshot` 文档及参数，默认 `mode="default"`；返回 YAML 字符串。包内文档指向 [官方 ARIA snapshots 说明](https://playwright.dev/python/docs/aria-snapshots)。本次未访问外部网页。
- `_impl/_locator.py:589`：发送 Frame 的 `ariaSnapshot` 请求。
- `driver/package/lib/coreBundle.js:24057`：默认 Locator 路径调用 `evaluateInUtility(... injected.ariaSnapshot(element, opts))`。
- 同文件第 19475 行包含打包后的 injected 实现：`generateAriaTree` 遍历 DOM，调用 `getAriaRole`、`getElementAccessibleName`、`isElementHiddenForAria`，再由 `renderAriaTree` 输出；这条路径没有调用 `Accessibility.getFullAXTree`。

该 bundle SHA256：`3258d1cf334c6afc95f22aa9c292436cb976b391e0437f1359c83b84f0cb9d66`。这是版本相关行为，升级 Playwright 后须重新注册和验收。

## 保留内容与明确缺失

| 项目 | 本机默认模式的行为 |
| --- | --- |
| 无名 DIV / generic / ignored | 隐式 role 表没有 DIV；没有 role 或 role 为 none/presentation 时不建立该节点，继续遍历子节点。显式 generic 及其他特殊情况不能概括为“一律删除”。不输出 Chromium 的 `ignored`、`ignoredReasons`、`chromeRole`。 |
| 角色、名称与文本 | 按 Playwright 的角色、命名算法生成；合并相邻文本并归一化空白。渲染器不输出长度超过 900 字符的名称。这些信息损失不能算成原始 AX 相等。 |
| 控件状态 | 输出部分角色适用的 checked、disabled、expanded、invalid、level、pressed、selected，以及部分输入值。多种 false/未定义状态都不产生标记；invalid 取 ARIA 状态，不能代替完整原生校验状态。 |
| 焦点 | 内部计算 active，但默认模式不渲染它。focus、selectionStart/End/Direction 必须继续由独立 DOM/live-properties 检查。 |
| 关系 | aria-labelledby 会影响名称，aria-owns 会影响遍历；不输出完整关系 ID 图，也不输出 accessible description、controls、activedescendant 等完整关系事实。相同名称不证明引用的是同一个对象。 |
| 可见性 | 默认采用 Playwright 的 ARIA 可见性算法，检查 display、visibility、aria-hidden、祖先与 shadow/slot 情况。不是命中测试、遮挡检查或完整动作可执行性检查。 |
| frame / shadow | 遍历 open shadow 和 slot；默认 Locator 路径不会递归采集 iframe 内文档。闭合 shadow 和未采集 frame 不得默认为通过。 |

`mode="ai"` 是另一种条件：包含临时 ref、额外 generic 节点、active 与不同的可见性规则，并可合并 iframe 快照。它不是默认模式的无损加强版，本建议不使用该模式，也不使用 ref 作为业务定位器。

## 可执行的补充指标方案

先冻结独立指标名称、包及 bundle hash、`mode="default"`、不截断深度、`boxes=False`、根节点、frame 覆盖、超时、观察时点，以及已有的 URL/秘密值处理策略。各 frame 分别采集时，必须保留独立 DOM 捕获确定的 frame owner 对应关系；缺失、超时或采集失败记为 unconfirmed，不能丢弃。

对两边实际返回的**完整字符串做 exact 比较**，或对严格解析且保留顺序和全部字段的树比较；不加业务文本正则或针对本次差异的过滤。`to_match_aria_snapshot()` 的默认实现使用 `containsList`，允许部分匹配，不能作为完整快照相等的判据。原始快照也可能包含实际输入值及链接代码，公开前必须经过已声明的安全处理并验证 canary。

输出单独的 `playwright_aria_snapshot_exact`。继续完整检查 public DOM、live properties、动作参数与实际目标身份、独立业务真值、初态/逐动作/末态以及 read-point 行为；完整 Chromium AX 和 raw strict 结果单独保留。该指标与 Playwright 角色定位共享部分算法，具有脚本适配价值，却不是独立于 Playwright 的无障碍真值。

如果原门禁遇到 full AX 差异就停止，增加一个补充字段不会允许后缀继续。若希望用新的语义条件运行完整后缀，须另行冻结新的协议、运行编号和门禁；旧运行的 full AX 严格失败仍然失败，不能追溯改分。

## 启用前的正反控制

- **正控**：同一通用页面重复采集；相同 DOM 经不同原生构建方式生成；无语义 wrapper 的变化。观察哪些差异会被该指标折叠，同时保留 DOM/full AX 的真实结果，不预设所有 wrapper 都无害。
- **应检出的反控**：改按钮名称/角色、普通输入值、checked/disabled/expanded、链接目标、可见内容顺序；以 aria-hidden 或 display:none 隐藏有意义控件。补充指标应产生明确差异。
- **应暴露的盲区**：仅改焦点或选区、超过 900 字符的名称、同文案但不同 labelledby/controls 对象、iframe 内控件。即使快照相等，其他对应检查必须失败或标明未覆盖，不能整例判成功。
- **执行与安全控制**：同文案但不同业务记录的两个对象、前端显示不变但后台写入错误、密码和执行 URL canary。实际目标身份/独立业务检查及导出安全层必须分别拦住这些情况。

以上是待执行的验收要求，本次没有运行这些控制，也没有证明当前网站的 Playwright 快照会相等。
