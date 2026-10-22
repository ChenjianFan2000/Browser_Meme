# 协作接口与自动上下文验收补充

日期：2026-10-21。新增004/005均为中立基础设施probe，精确gpt-6.1-sol，不含网站材料，不属于正式学习预算。旧001–003证据不修改。

## 协作接口

CLI0.163.0支持canonical `agents.enabled=false`；同时设置 `features.multi_agent_v2=false`，防止V2覆盖。`--disable multi_agent`单独使用不足以证明协作工具不可用。`agents.max_threads=1`允许一个child，不应作为禁止child的边界；官方schema的该值下限为1。`agents.max_depth=0`仅对V1有意义，V2忽略。

004/005新session实际工具发现和原始rollout均未暴露协作调用。模型被要求若可调用则实际spawn一次；工具不可用，因此没有child，没有假称收到一次spawn拒绝。最终正式配置禁用整个协作接口，不再用003仅父模型转述的child结果作为权限继承证据。原始runtime工具发现输出、MCP空结果保存在 `solar-tools-probe-005.raw-rollout.jsonl`，结构化提取在 `.rollout-audit.json`。

## 自动注入反例与修正

- 004在专用home与workspace分别放通用AGENTS sentinel，`project_doc_max_bytes=0`成功阻止workspace文档，却仍自动注入专用home的AGENTS。004 raw response_item实际记录该home marker，不能只依赖模型自述。正式home必须为新建auth-only目录，禁止复制AGENTS、历史、skills和配置。
- `skip_host_skill_discovery=true`仍出现技能目录，004记录了系统技能和generic skill名称；其正文和memory sentinel未注入。
- 005增加 `skills.include_instructions=false`、`skills.bundled.enabled=false`、显式禁用generic skill，并关闭memory注入和生成。005仍放workspace AGENTS、generic skill、memory sentinel作为反例探针，**raw rollout中四个marker/名称均不存在**。
- 005 world_state实际为 `agents_md:{}`、`host_skills:{includeInstructions:false}`、`skills:{includeInstructions:false}`、apps/plugins instructions=false、managed developer instructions={}。MCP resources/templates调用均返回空。

005的新home无AGENTS或用户config；只有必要auth及通用审计sentinel，运行后增加该次session自身状态。auth在目录0700/文件0600，未归档。没有读取用户全局配置或历史。

## 正式CLI所需附加配置

在既有默认deny filesystem及固定工具网络之外，添加：

```toml
[agents]
enabled = false
max_threads = 1
max_depth = 0

[features]
multi_agent_v2 = false
memories = false

[skills]
include_instructions = false

[skills.bundled]
enabled = false

[memories]
use_memories = false
generate_memories = false
```

继续保留 `--ignore-user-config --ignore-rules --strict-config`、project_doc_max_bytes=0、apps/plugins/hooks/browser/computer/skills-search关闭。正式新home不得有AGENTS、skills或历史；005的 `skills.config` generic-sentinel条目仅用于审计，正式空home不需要复制它。

精确argv与请求在各 `.result.json`；004/005使用non-ephemeral专用home只为取得可审计原始rollout，不复用到正式学习。005真实usage input18329/cached8832/output238，004真实usage以其 `.events.jsonl` 的turn.completed为准。无费用推算。

官方schema来源：[config-schema.json](https://developers.openai.com/codex/config-schema.json)，本次副本为 `config-schema-audit.json`。schema说明agent开关优先级及限制，实际生效以上述原始运行记录为依据。
