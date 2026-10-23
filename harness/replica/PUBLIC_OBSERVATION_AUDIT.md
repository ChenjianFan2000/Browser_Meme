# 公共 DOM / AX 观察范围审计

本次仅检查通用 Harness 和自建通用网页，没有读取目标网站源码、规则或业务脚本，也没有调用实验模型。

旧的 `h.observe()` HTML 导出不能表示控件的实时 `value`、`checked`、焦点及选择区间；原始 CDP AX 的节点编号也不能直接对应删去 SCRIPT 后的 DOM 路径。独立比较器却会比较这些字段，因此存在信息粒度差异。

开发 runtime 新增 `obs-*.public-tree.json`，由本次已有采集的 canonical 树生成，没有再次读取页面，也没有注入另一 lane 的状态。单个文件包含公开 DOM、完整 AX、实时控件属性、焦点路径、iframe owner 和 AX 到 DOM 的路径引用。旧 HTML、AX、截图继续提供。

`runtime/public_snapshot.py` 中的 `_public_projection` 与当前 `runner.py` 函数源码完全相同，策略字典相同，使用相同方式计算 `projection.sha256`。真实浏览器测试验证投影结果、焦点、iframe owner、AX 控件引用以及 open shadow 路径。源码与 hash 等价测试防止两份实现静默分叉。

公共导出另有安全层：实际口令等值始终遮蔽；空值及选择区间继续按原协议保留；不接入 Storage、网络或评测私有数据。结构性检查拒绝 raw/CDP frame 或额外的私有 frame 字段，导出不修改私有 canonical 数据。

真实通用 fixture 发现旧导出的另一个缺口：`javascript:` 链接的代码虽然从 DOM 属性中删除，仍通过 AX 的 URL property 导出。初次测试为 1 过、2 失败，反例保存在 `work/replica-pilot/public-snapshot-preflight/initial-failure.json`。修复没有删去测试 canary：新增 `public_execution_projection()`，在旧 `.ax.json` 和新增公共树的导出末端将 AX `name=url` property 中的执行 URL 体替换为 `[EXECUTION URL REMOVED]`，保留字段和节点关系。该层使用独立 `security_projection` 元数据及 hash。另用真实 fixture 验证以 `javascript:` 开头的普通业务文本及 `data-note` 属性仍被完整保留，避免按字符串前缀误删业务信息。

**现有 v2 比较器仍比较完整 AX 中的执行 URL，私有 raw/canonical 捕获也保留它。** 新安全投影尚未进入既有 v2 评分；因此遇到此类 URL 时，不能宣称新增公共观察与 v2 评分逐字段完全同范围。后续若统一两者，必须另注册评测策略和运行，不能追溯改写旧成绩。当前改动没有修改 runner 的评分逻辑或旧候选结果。

开发 runtime 的三项测试已通过：同源码/策略/hash、真实 Chromium 结构及安全检查、实际沙箱 Broker 导出与同次私有捕获对照。收窄到 AX URL 字段并增加业务文本保留断言后的结果记录在 `work/replica-pilot/public-snapshot-preflight/development-passed-002.json`。该结果不代表目标网站复现成功，也不代表已启用到任何正在运行的 construction；版本化 runtime 需要单独冻结和验证后才能由后续新运行选择。

可供后续新运行显式选择的版本为 `runtime_versions/learning-public-tree-v2`，父版本是已验证的 `evaluation-helper-settle-v5`。它继承断连门禁、原子 checkpoint 发布及保留 caret 的截图修复，只添加公共导出代码、接口说明及版本元数据；其他文件与父版本一致。`learning-public-tree-v1` 是保留的 v4 父本草案，不作为新运行入口。

v2 已完成一轮实际 Broker 验收：2 个真实浏览器动作，公共文件与同次私有 canonical 树逐字段对照，全部代码/口令/Storage canary 检查通过，进程树清理通过；另通过不启动浏览器的投影源码/hash 检查。本轮共 2 项检查通过，只有 1 项启动浏览器。执行前后完整文件 hash 相同，原始 Broker 证据、manifest 及限制均保存在 `work/replica-pilot/public-snapshot-v2-preflight/READY.json` 及其引用路径。默认学习仍不开启 settle；是否启用必须由新运行另行注册。

```python
runtime_source = "/workspace/Browser_Meme/harness/replica/runtime_versions/learning-public-tree-v2"
```

```bash
PYTHONPATH=/workspace/Browser_Meme/work/audit-20261022/test-env/lib/python3.12/site-packages \
  python -m pytest harness/replica/tests/test_public_snapshot.py -q
```
