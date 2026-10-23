> 便携交接副本。原文：本轮 `REPRESENTATION-GUIDE.md`；原始 SHA-256：`ffc6e1bee7a94c252fdc9fb8ca13544a112063570f569c9643a52a2e3b74c986`。本次仅追加本说明并转换交接链接：已发布材料指向包内或通用 Harness，未归档材料保留短来源标识；历史观察、代码示例、判断、失败与时间截点不改写。当前完整结果以 [发布汇总](../RESULTS.json) 和 [交接说明](../README.md) 为准。链接到汇总仅表示保留了摘录，不等于原始证据已公开。

# 本轮表示讲解与实现审查

本文以冻结公开包 **model-candidate-001 / v001** 的实际文件为准。它已经提供一组可检查的组件合同、浏览器定位辅助函数和局部离线预测函数；“有类型化状态”“有参数化树”等设计说明，还不能等同于完整状态机已经驱动真实浏览器执行。

审查只读根 AGENTS、本轮协议和清单、通用合同 README/schema、HARNESS-READY-002、METHOD-AUDIT-001、公开冻结包及作者允许的五个侧索引。未读目标站源码、private/oracle、消费者任务或脚本，未启动浏览器。本文仅解释和检查已交付表示，不新增网站规则。独立消费者结果由协调者另行补充。

## 1. 数据由哪几层组成

可以把一次操作理解成“先说会看到什么，再动手，再核对”。当前包把相关知识放在下列文件中。

| 层 | 文件及用途 | v001 的实际边界 |
| --- | --- | --- |
| 人能读的操作约定 | component-rulebook.md（本地历史引用，未随精选包归档；来源：`model-candidate-001 / component-rulebook.md`）：页面识别、对象身份、继续或停读的约定 | 是作者的有限范围知识声明，需要合同、脚本及独立事实分别落实 |
| 业务状态与局部预测 | component-model/model.py（本地历史引用，未随精选包归档；来源：`model-candidate-001 / model.py`）：初态、`predict`、`choose`、`symbolic`、`bind_observation` | 只有四类动作预测；作者将它登记为离线参考，未登记为浏览器 helper |
| 组件合同 | component-contracts.json（本地历史引用，未随精选包归档；来源：`model-candidate-001 / component-contracts.json`）：参数类型、外部槽、分支、必须/禁止出现的节点、关系、符号树 | 7 个合同、8 个分支；约束的是被声明的局部组件，不能代替完整 DOM/AX 或全站模型 |
| 动作声明 | transitions.json（本地历史引用，未随精选包归档；来源：`model-candidate-001 / transitions.json`）：`guard` 前置条件、`effect` 变化、`frame` 应保持不变的事实 | 内容是字符串列表；`model.py` 和浏览器 helper 均不读取并执行这份文件 |
| 已知、未知与停读策略 | knowledge-state.json（本地历史引用，未随精选包归档；来源：`model-candidate-001 / knowledge-state.json`） | 写出了状态分类和策略；不会仅因存在该文件就自动触发停读 |
| 浏览器接口 | components_v1.py（本地历史引用，未随精选包归档；来源：`model-candidate-001 / components_v1.py`）：原生 Playwright 定位器、行字段读取、确定性选择、预测字典构造 | 不含任务流程，也不导入 `model.py`；执行者仍需安排确认、动作、等待及回读 |
| 交接样例 | prediction-templates.json（本地历史引用，未随精选包归档；来源：`model-candidate-001 / prediction-templates.json`） | 展示预测字典形状；尖括号中的文字是待填占位符，不能直接当成真实动作参数 |

“状态”本身也是字典。例如 `query` 保存 `status=known` 和一个字符串值；`rows` 标记为 `unknown_external`、类型为数组；未建模反馈标记为 `unknown_semantics`。这些标签把“还不知道数据”与“还不知道含义”分开，但 v001 没有对整个业务状态实施统一类型校验，也没有自动把所有标签变成运行守卫。

## 2. 预测前后分别做什么

动作前，调用者选定合同和分支，把已知输入放进 `parameters`，把允许事后读取的槽列入 `unknown_slots`，并写出 `disposition`。例如输入框预期值应来自已经知道的输入参数；结果列表内容则可以事前声明为外部槽。此时不能把尚未看到的数据填成“准确预测”。

按[通用控制器约定](../../../../replica/contracts_v1/README.md)，`h.expect` 的预测在原生动作之前落盘；动作后的检查点停住浏览器。控制器核对前后预测是否一致，检查实际采集到的 DOM/AX，并要求独立业务事实检查。只有全部满足才释放后续动作；结构错误、缺绑定、身份无法确认等均不能放行。具体执行是否遵守这条链，仍要看该次运行的证据。

动作后，槽值另存为观察绑定。例如刚读到的结果对象可以用于下一步选择；它们不会回填、改写上一动作的先验。通用结果因此分开报告 `prediction_score` 与 `observation_binding_score`。后者回答“事先声明的外部数据是否按约束读到了”，不回答“模型是否事先猜对了这些数据”。合同内分数的分母来自作者选择的检查项，不宜直接拿来比较不同表示的理解程度。

`predict` 返回的下一状态也是**假说**。浏览器动作可能失败，检查也可能停止；只有完成观察和独立核对，执行者才有依据把假说晋升为已确认状态。v001 没有实现统一的“预测状态 → 检查 → 提交状态”事务接口。

## 3. 重复结构、AX 和未知槽：用本包的一个例子说明

本包的 `jobs.collection` 采用以下结构。这里省略了行选择器的两种完整 CSS class 字符串，保留会影响理解的字段：

```json
{
  "slots": {
    "row_paths": {
      "type": "array",
      "items": {"$type": "string"},
      "required": true
    }
  },
  "required": [
    {"id": "results", "select": {"source": "dom", "tag": "DIV"}},
    {
      "id": "row-data",
      "scope": "results",
      "select": {"source": "dom", "tag": "BUTTON"},
      "count": {"min": 0},
      "bind": {"slot": "row_paths", "field": "identity", "many": true}
    }
  ],
  "tree": {"component": "job-results", "rows": {"$slot": "row_paths"}}
}
```

这段是便于阅读的摘录，不能拿它替换原合同：原合同还精确匹配结果容器 class，并限制行 class 为两个值之一。实际动作前预测需选 `contract_ref=jobs.collection`、`branch=ready`，并声明 `unknown_slots=["row_paths"]`。

用本包 `symbolic` 函数代入空参数，实际得到：

```json
{
  "component": "job-results",
  "rows": {"$unknown": {"slot": "row_paths", "status": "unknown_external"}}
}
```

含义很具体：先承诺有可识别的结果容器；容器内匹配到零个或多个行按钮；动作后把这些节点的 `identity` 读成字符串数组。这里的 identity 是采集时的节点路径，不是可跨页复用的业务对象 ID。数组长度和字符串值事前未知，所以不会被当成已预测的结果数或持久身份。

**这一版尚未实现逐行展开的重复组件模板。** `rows` 只是槽引用，没有“每一项都必须拥有标题、公司、地点、保存按钮，且各字段属于同一行”的结构定义。合同允许零个匹配行，没有检查行的三个文本字段，没有行内关系，也没有证明所有实际行都被选中。新增了一种未被行选择器识别的结构时，它可能被遗漏。作者自己的 coverage 也注明：`zero-or-more row subset binding does not prove complete row coverage`。

AX 是浏览器的无障碍树。通用观察器保留 AX 节点的 role、name、properties、父节点等字段，合同可以用它们定位与约束，也可以检查 parent/ancestor 关系。本包确实用 AX 识别部分按钮、导航和错误文字；但上述重复列表使用 **DOM** 行路径，未交付每一项的 AX 子树模板。不能把“通用观察器能采 AX”写成“本模型已完整约束重复 AX 结构”。符号 `tree` 也只是局部结构表达，不是完整页面渲染器。

还有一个更弱的层次：`jobs.search` 只检查两个输入框当前值、Search 按钮和结果容器。它声明了可选 `row_texts` 槽，却没有任何 `bind` 项；`predict(search)` 也没有声明这个未知槽。所以搜索合同通过本身不证明结果集合已读取、逐项校验或完整绑定。

## 4. 对象身份和歧义如何表达

作者规则书把职位的公开身份写成三个完整字段：`title`、`company`、`location_mode`。这比只看标题或公司多了一项区分条件；它仍是有条件的公开身份，要求当前候选集合内唯一，不能据此推断全站永远唯一。

离线 `choose` 支持完整身份精确匹配，或明确指定的字典序选择策略；空结果、偏好未指定或完整三元组重复会抛出 `ReadPoint`。浏览器 helper 的 `public_jobs` 逐行读取三个字段，`deterministic_job` 排序并拒绝所选项重复，`job_row` 返回按三个完整字段过滤的定位器。数组下标仅用于枚举。帖子 helper 通过完整正文定位卡片，唯一性还需要调用者确认。

这些函数不是同一个自动身份管道：`job_row` 只返回 locator，不在函数内断言数量为一；`public_jobs` 碰到某行字段数不为三时返回空数组，和确实没有结果的返回值相同；`deterministic_job` 的无结果与歧义也都返回 `None`。脚本必须解释这些结果并停止，不能把空值当成可以继续的默认对象。

`model.py` 的 `select` 依赖调用者提交 `identity_unique`，没有自行把身份和当前 rows 交叉验证；`toggle_save` 依赖调用者提交 `before` 和详情参数，也不自行验证这些参数与已选对象一致。身份检查的意图已经表达出来，但尚未集中成一个不可绕过的模型接口。

## 5. model.py、helper 与控制器的实际分工

`model.py` 是普通 Python 纯函数参考。它会复制状态，处理 `post_create`、`search`、`select`、`toggle_save`，返回预测及下一状态假说；不会打开网页、点击按钮或读取 DOM。`choose` 做数据选择，`symbolic` 做参数替换，`bind_observation` 做前后通道分离。

`components_v1.py` 才是已登记的浏览器 helper，向脚本提供 Playwright 定位和读取函数，并可构造含 `effects`、`expected_business_state` 的预测字典。它没有调用 `model.py`，也不会自动维护后者的状态。作者的 policy-check.json（本地历史引用，未随精选包归档；来源：`construction-011 / policy-check.json`） 明写 `offline_model: not registered as browser helper; offline reference only`。该文件的 pass 是 AST 预检查结果，不是浏览器成功结果。

因此，**业务 state 在离线函数里确实被部分使用，但未形成已交付的单一运行状态机**：

- `created_posts` 会递增；`selected` 会被写入并用于保存动作；`saved` 会按选中身份记录新布尔值；查询与地点会更新。
- `authenticated`、`route` 在初态出现，却未被这四个预测分支更新或用于检查前置条件。登录的成功、拒绝与恢复只在合同/动作声明中表达，没有对应 `predict` 分支。
- `unknown_semantics` 标签不会自动阻断这些分支；未识别的 action 名称会抛 `ReadPoint`，是另一种较窄的保护。
- 保存动作使用外部传入的 `before`，没有验证它是否符合 `saved` 已知状态；选中与详情参数也可能来自不同来源。`frame` 中的禁止副作用需要独立事实检查，函数本身未逐项执行。
- `bind_observation` 只是复制所给内容，不检查槽名、类型、观察来源或合同；槽合法性依赖通用 validator。`symbolic` 也没有通用 `render` 文档中的输入类型校验与缺参返回协议，直接缺参时可能抛异常。

本审查没有读取消费者脚本，所以不判定消费者是否另行补上了这些调用和检查。上面的结论只描述冻结包自身具有什么能力，以及它没有自动连接什么。

## 6. 除重复结构外，合同还漏掉哪些约束

这些是合同的表达/检查范围，不是对原网站行为的新结论。

| 合同 | 能检查的关键内容 | 尚不能由该合同证明的内容 |
| --- | --- | --- |
| `auth.login` | 输入元素、提交按钮；拒绝分支的错误文字及无 feed composer | 输入值确实保留、业务认证状态、完整登录分支覆盖 |
| `feed.ready` | composer 与 Jobs 导航存在，登录提交按钮不存在 | 完整页面状态与持久业务对象 |
| `jobs.search` | 输入当前值、Search、结果容器 | URL 查询状态、结果与查询的业务关系、结果完整性、原详情是否已切换 |
| `jobs.collection` | 容器及零到多匹配行路径的绑定 | 每行字段和 AX 子树、所有实际行覆盖、持久业务身份 |
| `jobs.detail` | 已给定详情文本、保存标签、局部归属关系 | 保存标签必须属于一个按钮；详情与所选行/URL 的同一业务身份；其他对象未变化 |
| `post.composer` | dialog 内正文值、Post/Cancel 文本及正文归属 | 控件可用性、提交动作的业务结果、全部拒绝原因 |
| `post.body` | 全页存在唯一匹配正文文本，dialog 不存在 | 文本一定属于帖子卡片、是新创建对象、作者与持久身份正确、只增加一个对象 |

例如 `jobs.detail` 的保存项选择的是 detail 后代中的精确文本，未要求这段文本位于 BUTTON 下；公司、地点等也只是 detail 内的文本归属。`post.body` 没有复用 helper 的卡片作用域。因此“找到预期文字”与“验证正确对象和可操作结构”目前仍有间隔。独立业务 oracle 可以发现其中部分错误，但不能反过来声称组件合同本身已经约束了这些内容。

## 7. 已有什么证据，分别能说明什么

| 证据来源 | 记录内容 | 可支持的结论与边界 |
| --- | --- | --- |
| 作者 coverage.json（本地历史引用，未随精选包归档；来源：`construction-011 / coverage.json`） | 4 次真实 UI 探测、28 个动作：新集合、选择/保存、认证拒绝恢复、发帖；一次计划停读，三次 completed | 作者记录了真实浏览器探索；本审查没有重放原始证据，也不能把作者 completed 当独立业务通过 |
| 作者 public-matching.json（本地历史引用，未随精选包归档；来源：`construction-011 / public-matching.json`） | 8 个组件/分支匹配记录均 pass | 是作者对自己公开抓取的离线匹配；全部 `commitment_verified=false`，不能据此证明动作前冻结或独立闭环通过 |
| 作者 counterexample-controls.json（本地历史引用，未随精选包归档；来源：`construction-011 / counterexample-controls.json`） | 7 个本地变异控制均 fail 或 unknown | 表明这些指定错误有拒绝能力；未覆盖每行缺字段、遗漏行、保存文本脱离按钮等上述盲区 |
| HARNESS-READY-002.json（本地历史引用，未随精选包归档；来源：`HARNESS-READY-002.json`） | 51 项离线检查；通用真实浏览器正常、错状态、未绑定槽控制及清理结果 | 支持通用控制器机制可工作；测试页面不是目标站，不代表目标合同或消费者任务通过 |
| [METHOD-AUDIT-001.md](METHOD-AUDIT-001.md) | 独立通用方法审查与若干反例复核 | 支持明确的通用接口检查结论；不审查目标业务规则，也不证明 oracle 语义充分 |
| 本次表示审查 | 哈希、公开结构静态检查及下述纯内存调用 | 支持“文件和函数实际如何工作”，没有新增真实 UI 或独立业务测量 |

本审查核对了公开包中八个已读取文件的 SHA-256，均与其 MANIFEST 相符；未读取 `CONSUMER.md` 的内容，也未把它计入本次哈希核验。合同总数为 7，分支总数为 8。

本次仅在内存执行冻结 `model.py`，观察到：

- `initial_state()` 中 `authenticated=false`、`unmodeled_feedback=unknown_semantics`，随后 `predict(..., "search", {"query":"", "location":""})` 仍返回 `accepted`；原始 state 未被修改。这验证了纯函数复制行为，也说明认证/未知语义状态未成为此分支的守卫。
- `symbolic(jobs.collection,{})` 得到上文的未知 `row_paths` 槽。
- `bind_observation(prior,{"row_paths":123})` 原样保存数值 123，没有检查该槽应为数组。这只测试离线函数，不代表通用 validator 接受错误类型。

这些调用没有读真实目标数据、没有启动浏览器、没有写模型文件。

## 8. 最小且可以验证的下一步

以下是接口改进建议，不补写目标网站规则，也不把建议计入 v001 已完成能力。

1. **让重复项有可执行合同。** 从一份逐项结构定义生成每行约束，检查所需子项数量、类型、归属与完整覆盖；把“合法零结果”与“选择器遗漏了实际行”区分开。用缺一个字段、子项串到另一行、遗漏行、额外异形行的负控制验证，而不只测试容器是否存在。
2. **让状态与浏览器共用一条接口。** 明确浏览器脚本调用哪个预测入口，哪些 guard/frame 由它执行，哪些交给独立事实检查；让身份选择、详情参数和保存前状态来自已校验输入，避免仅凭调用者布尔声明。增加检查成功后才提交下一状态的约定。
3. **把薄弱文字锚点提升为对象关系。** 在已有公开知识支持的范围内，让控制文本属于预期控件、正文属于预期对象，并验证相应关系的错误会被拒绝；仍由独立事实检查承担持久身份与副作用真值。
4. **让未知状态有统一失败路径。** 统一空集合、结构异常、身份歧义、未知语义和缺失绑定的返回值/异常，验证每一种都阻断后缀；给离线绑定与符号渲染增加和通用接口一致的类型及缺参行为。

若后续交付 v002，应保留 v001 和以上结论，在新版本上复核相同控制。文档措辞变强、增加一个名为 repeat 的字段或新增状态字典，都不能单独证明限制已经解决。

## 9. 独立消费者结果与版本续记

**待协调者补充。** 本文未读取独立消费者任务、脚本或 oracle，不填写其通过率、首次连续动作长度、业务终点、禁止副作用、继续/停读探针或适应成绩。本轮固定分母为 3 个新消费者任务和 2 个探针，未运行和失败也应保留；首次冻结结果与后续适应分开报告。

本轮仍按协议（本地历史引用，未随精选包归档；来源：`PROTOCOL.md`）与清单（本地历史引用，未随精选包归档；来源：`MANIFEST.json`）解释为单站、有限范围、隔离有限的构造预实验，`strict_score=null`。本 guide 的 v001 发现不能被后续修订追溯覆盖；也不能由有限合同通过推导“完整网页理解”或“此表示已优于其他表示”。

## 10. candidate003 / v003 复查：共享执行入口与逐项合同

本节独立记录后续版本，不修改前九节的 v001 结论。复查对象是 candidate003 公开包（本地历史引用，未随精选包归档；来源：`model-candidate-003 / MANIFEST.json`），MANIFEST 的 SHA-256 为 `8251f9710ad609d8c03a543dc30b7592bebbc5e98f666f807803254b7f062df9`。本次读取的八个包内文件均匹配清单；未读取 `CONSUMER.md` 内容，未读消费者任务、脚本、private 或 oracle。

同时读取了 [contracts_v2 通用接口](../../../../replica/contracts_v2/README.schema.md)、其 schema/validator，以及 HARNESS-V2-MANIFEST-001.json（本地历史引用，未随精选包归档；来源：`HARNESS-V2-MANIFEST-001.json`）。通用清单列出的十个文件哈希均匹配。没有运行浏览器，也没有修改模型或通用实现；以下新增检查全部在内存执行。

v003 清单把本次修订登记为 `explicit_offline_guard_adaptation`。作者变更摘要（本地历史引用，未随精选包归档；来源：`construction-011 / v003-change-summary.json`）与最小 diff（本地历史引用，未随精选包归档；来源：`construction-011 / v003-minimal.diff`）显示，相对 v002 主要修复未认证登录表单编辑及受保护导航守卫，合同 bundle 沿用 v002。规则书、representation 等文件标题仍为 v002；不能仅因包版本为 v003，就把原有观察或测试写成一次新的真实浏览器验证。

### 已经实质解决的部分

| v001 问题 | v003 实际实现 | 本次复查结论 |
| --- | --- | --- |
| 离线 model 与浏览器 helper 两条实现 | model.py（本地历史引用，未随精选包归档；来源：`model-candidate-003 / model.py`） 只从 components_v2.py（本地历史引用，未随精选包归档；来源：`model-candidate-003 / components_v2.py`） 重新导出 `initial_state/plan/bind_*` | 已有共同函数实现；不是再维护一张离线转移表 |
| state 的认证字段未参与动作检查 | `plan` 检查认证、路由、已绑定对象和部分交互前态，并同时返回 prediction 与下一状态 | 未认证 search、未认证 `/jobs` 导航的内存调用均返回 `ok=false/readpoint`；v001 的该反例已被拒绝 |
| 动作 JSON 与运行逻辑脱节 | `transitions.json.operations` 来自 helper 的 `OPERATIONS` | 本次核对两者完全一致；business_change/records 被 `plan` 使用，guard 字符串仍是说明，真正判断由同一 helper 中的条件分支执行 |
| 外部观察仅原样包装 | `bind_rows/bind_job/bind_post` 检查字段类型；`select_job` 要求 rows 中唯一匹配且已登记 job | 部分类型与身份门禁已落实；数值字段排除 bool，缺绑定或重复身份有失败路径 |
| 列表只绑定行路径 | `jobs.collection.nonempty` 对每个匹配 DOM 行执行 `each`，逐行检查字段、文本和保存按钮并分别绑定 | 已有真正逐项执行的合同；删除一行的标题会失败，不能再用“存在一些行”概括这一部分 |
| 保存标签只是任意文本 | `jobs.detail` 要求 enabled BUTTON，并以 `has` 约束其内部保存文本 | v001 的“文字脱离控件仍满足保存项”缺口在这个合同中已收紧 |
| 帖子正文只做全页文字匹配 | `post.body` 要求唯一匹配 card、其内部真实正文 DIV 及归属关系 | 已加入卡片作用域；相同正文多卡时应成为歧义，而非随便选一个 |

新的共享入口共有 16 个 operation 名称，合同扩展到 11 个、13 个分支。它包含更多身份、计数和交互前态；不能只称为“增加了状态字典”。但“共享函数已经交付”仍不等于“独立消费者实际按它执行并正确提交状态”。本审查没有读取消费者脚本，后一个结论继续留给执行证据。

下一状态的提交仍由原生脚本负责。`plan` 返回计划，不拥有浏览器动作事务；规则书要求在 UI 成功且合同/事实门禁通过后才采用该状态。本包没有在函数内部自动完成浏览器执行、门禁和状态提交。

### each / has 的真实含义及仍有的覆盖缺口

`has` 先筛选父候选：只保留拥有指定同源树后代的父节点。`each` 再对每个**已被选中的父节点**独立执行局部合同，局部槽按 `parent_id` 分开保存。它们都有实际通用实现；不是只供展示的 tree 字段。当前通用接口支持一层 each，要求非空重复组有正数下界；空集合采用单独 empty 分支。

v003 的 DOM 行合同实际检查：标题容器与文本、公司容器与文本、位置/方式容器及三个文本片段，以及包含 Save/Saved 文字的 enabled BUTTON。局部 scope 保证字段位于当前行，避免一行借另一行的字段通过。绑定结果形如：

```json
{
  "rows.each": [
    {
      "parent_id": "该次采集的行节点 ID",
      "bindings": {
        "title": "观察到的标题",
        "company": "观察到的公司",
        "location_mode": ["位置片段", " • ", "方式片段"],
        "save_label": "Save"
      }
    }
  ]
}
```

这只是绑定格式示意，文字不是网站数据或预测结果。实际槽在动作前用 `rows.*.title` 等名称声明，实际值在观察后按父节点分别绑定。

**each 只覆盖选中的集合；has 本身不证明选中了全部对象。** DOM 父行仍依赖两种完整 class 值；不匹配父选择器的新结构不会自动纳入逐项检查。AX 的限制更直接：`ax-rows` 是全观察内“拥有 Save/Saved 子按钮的 button”，没有与 DOM 结果容器建立同一对象桥接，也没有核对两树行数一致。AX 只检查了嵌套保存按钮，没有逐一表达标题、公司和位置的 AX 子结构。

本审查用冻结合同和真实 v2 validator 构造两个 DOM 行、两个 AX 行的合成观察。没有借用目标数据，节点全部为内存中的 synthetic 值：

| 本次独立内存控制 | 实际结果 |
| --- | --- |
| 两个 DOM 行与两个 AX 行都有所需结构 | `pass`；DOM rows=2、AX rows=2 |
| 只删去第二个 AX 行的 Save 子节点，保留该 AX 行本身与两个完整 DOM 行 | **仍为 `pass`**；DOM rows=2、AX rows=1 |
| 删去第二个 DOM 行的标题容器及其文本，其他节点保持完整 | `fail`；局部 title 缺失，并产生 scope/slot unknown |

第二项复现的是当前合同的覆盖盲区：坏 AX 行因不满足 has 被筛掉，另一条合格 AX 行仍满足 min=1。第三项说明 DOM each 的改进确实生效。不能把这两个结论混成“重复结构已全部解决”或“each 没有作用”。后续最小负控制应包括 AX 子项消失、DOM/AX 数量不同、父选择器遗漏行，并明确哪些差异必须拒绝。

### 结果数量、typed binding 与对象身份的残留边界

**新 search 的结果数未知时，先验仍只覆盖表单和容器。** `plan(search)` 生成 `jobs.search`；它没有同时预测 empty/nonempty 的互斥结果分支。随后 `collection_prediction(nonempty)` 由调用者提供一个布尔条件，选择非空逐项合同或空集合合同。因此当前 repeat 是观察条件化的结构检查：已知要按非空或空集合检查以后，约束相应结构。它不等于搜索动作前已经预测结果数量、空/非空结果或成员集合。把后续读出的集合用于下一动作是合理的，但报告必须保持这个时间边界。

**typed binding 解决了一部分类型问题，尚未完成观察到状态的一致性闭环。** `bind_job` 对已有记录会拒绝已知状态矛盾；`bind_post` 则只在 body 首次出现时写入记录。body 已存在时，即使再次传入不同的 liked、reactions、comments，它仍返回旧记录，既不更新也不失败。本次内存复现：

```text
首次 bind_post：body="audit synthetic body", liked=false, reactions=3, comments=1
再次 bind_post：同 body, liked=true, reactions=9, comments=7, unique=true
实际返回：仍为 false / 3 / 1；没有 ok=false 或 readpoint
```

所以“类型正确”不能被解释成“最新观察与预测状态已经核对一致”。这会让后续 `plan(like/comment)` 继续使用旧计数假说。最小修复验收应要求：已有帖子的每个状态字段矛盾都产生明确拒绝或明确登记的重绑定流程，而不是静默忽略。

此外，validator 的 `location_mode` 局部槽是三个字符串的**数组**，helper 的 `bind_rows` 与公开 identity 使用拼合后的**字符串**，symbolic repeat 也标记为 string。helper 通过 DOM 文本读取获得拼合字符串，但没有提供从 `rows.each` 绑定记录到 state rows 的共享归一化接口；也未验证这两条读取通道的身份一一对应。当前这是一处显式接口缺口，不能把它们视作已经自动接通的同一份 typed binding。

**帖子 registry 仍以 body 为 key，不能表示同正文的两个业务对象。** `bind_post(..., unique=true)` 的唯一性来自调用者；字典 `posts[body]` 没有独立对象 ID，无法同时保存两个相同正文帖子的状态。当前合理适用范围是完整正文唯一；观察到同正文双对象时仍应停读，不能以 body key 冒充持久身份。`bind_post_absence` 的发布前正文不存在检查也不建立发布后的独立对象身份。

### v003 证据应怎样计数

作者 guard 回归（本地历史引用，未随精选包归档；来源：`construction-011 / v003-guard-regression.json`）记录 40 项离线检查通过；公开观察匹配（本地历史引用，未随精选包归档；来源：`construction-011 / v003-public-matching.json`）有 5 条 pass，但全部 `commitment_verified=false`；结构负控制（本地历史引用，未随精选包归档；来源：`construction-011 / v003-structural-controls.json`）有 4 条 fail/unknown。本审查读取并区分这些侧索引，没有把它们重命名为独立消费者结果。列表的 147 个 prediction 检查项来自逐项展开，不能直接与 v001 的少量合同项分数比较理解提升。

通用 HARNESS-V2 清单记录 23 项离线测试，以及正常/缺子项的两组通用真实浏览器控制，后者分别完成与阻断后缀。它支持通用 each 门禁机制，不证明本包 AX 父选择器覆盖完整；上面的合成反例说明两者可以同时成立。

v003 清单明确 `new_calls=0`、`new_actions=0`，独立 live validation 未运行。本审查也未增加真实 UI 观察。新增支持仅为冻结文件一致性、代码路径与上述纯内存结果。**独立消费者、业务终点与适应成绩继续由协调者补充；v003 没有独立通过结论。**

## 11. candidate004 / v004 复查：0..N 先验、观察桥与实体候选

本节只追加 v004 结论，前述 v001/v003 原文保留。依据为 candidate004 注册（本地历史引用，未随精选包归档；来源：`model-candidate-004 / registration.json`）、公开包（本地历史引用，未随精选包归档；来源：`model-candidate-004 / MANIFEST.json`）、通用 [contracts_v3](../../../../replica/contracts_v3/README.schema.md)、HARNESS-V3-MANIFEST-001（本地历史引用，未随精选包归档；来源：`HARNESS-V3-MANIFEST-001.json`）、[METHOD-AUDIT-003](METHOD-AUDIT-003.md)，以及 construction-012 的五份公开 v004 sidecar。公开 MANIFEST 摘要为 `fd8f54ef9fb933feaecd59ede7386df2081ab511176ee528d50875e46e7353a5`；本次读取的八个包内文件与清单一致，通用清单九个文件也一致。

本次与限定公开产物的子审查只做文件审查、纯模型和合成观察检查；没有调用 browser、执行目标网站、读取源码、原始浏览器证据、消费者或私有 oracle，也未读 `CONSUMER.md` 内容。注册状态为 `frozen_unvalidated`；本文不补充独立网站成功结论。

### 0..N 现在确实进入动作前结构预测

components_v4.py（本地历史引用，未随精选包归档；来源：`model-candidate-004 / components_v4.py`） 第 3 行为 jobs.search/collection 的 ready 预测预先声明四种逐行未知槽；第 122 行起的 `plan(search)` 直接生成 jobs.search，不读取结果数，也不再由 `nonempty` 参数选分支。新的 component-contracts.json（本地历史引用，未随精选包归档；来源：`model-candidate-004 / component-contracts.json`） 第 174 行起，把以下内容放进同一个 search ready 合同：

- 查询与地点的已知输入值、Search 控件、必须存在的结果容器。
- 结果容器内 `count.min=0` 的 DOM rows；每个实际匹配行都执行相同 each 子合同。
- 必须存在的 AX root 及 0..N 个 AX 行。
- DOM/AX 已选行的 `same_dom_set` 关系，逐行数据仍作为后验槽绑定。

因此，**v003“先看结果为空或非空，再选择重复结构分支”的接口限制已实质改善**。现在能够事先承诺“无论本次出现零行还是多行，容器和每个出现的行都应满足这套约束”。它依然不预测确切数量、排序、标题或查询应返回哪些业务对象；这些仍是 `unknown_external`。

本审查从公开 helper 的 `plan(search)` 取得一份预测，在不修改它及其摘要的情况下送入不同合成观察：0、1、2 行均通过。0 行的两组 each 都记录 `evaluated_instances=0`、`child_passes=0`、`children_status=not_applicable`。这验证了同一先验结构确实支持可空重复，而非通过另选 empty 分支获得通过。非空时的子检查数量会随实例数增加，不能把这一增长当成更多独立业务能力。

### DOM/AX 桥修复了单侧漏行，但有明确全集边界

合同第 503 行的桥关系比较 DOM 行 id 与 AX 行的 `backend_dom_id`，实现见 [validator.py](../../../../replica/contracts_v3/validator.py) 第 224 行起。它检查映射是否可解析、同侧是否重复，再比较双向身份集合；不按行位置配对。它说明的是**当前采集的 DOM 节点对应**，没有赋予对象跨页、跨会话的业务身份。

本审查独立合成检查结果：

| 操作 | v004 结果 |
| --- | --- |
| 完整的 2 个 DOM 行、2 个 AX 行 | `pass` |
| 只删除第二个 AX 行的 Save 子节点，该行被 AX has 过滤掉 | `fail`，桥发现 DOM={r0,r1}、AX={r0}；v003 的旧反例已被拒绝 |
| 在上一项基础上，再把第二个 DOM 行 class 改成父选择器不认识的值 | **`pass`**，两侧都只选 r0；第二行节点仍在合成观察里 |

第三项说明桥保证的是**两侧已选集合一致**。若两套选择条件同时遗漏同一个对象，集合相等不能自行发现遗漏。DOM 行选择仍依赖两种完整 class（合同第 245 行起），AX 行仍依赖含 Save/Saved 子按钮（第 451 行起）；未建模的新行形状、容器范围外对象和分页全集，不会因新增集合桥而自动获得覆盖。AX 子合同也仍只要求行内保存按钮，并未完整描述标题、公司、地点的 AX 子树。

这与通用 METHOD-AUDIT-003 的边界一致。最小后续验收应保留“单侧遗漏失败”控制，同时增加“两侧同时过滤同一坏对象”的候选全集检查；不能只把两个集合相等写成全量对象识别。

### 实体 registry 能保留同正文候选，动作仍不以 handle 寻址

状态新增 `entities[handle]`，记录 `known` 签名、provenance 和本地句柄的身份含义（helper 第 231 行起）。句柄由调用者提供，既不是数组位置，也不是已经发现的服务端 ID。签名包含正文及可选作者、反应/评论状态；`match_entity_candidates` 按当前兼容信息返回零个、一个或多个候选，保留歧义。

这比 `posts[body]` 能表达更多情况：两个正文相同的实体可以各自有 handle；只有正文的观察可以匹配多个候选，当前反应状态等较丰富签名有时能临时区分。可变计数或 Liked 状态只是当前定位证据，不能证明跨时刻持久身份，尤其不能保证这些字段改变后仍能重识别对象。

**可表达候选与可执行动作仍分开。** `plan` 的 Like/Comment 等参数仍是 body，读取 `posts[body]`；第 102 行明确拒绝同正文多实体的动作。`match_entity_candidates` 即使得到唯一当前候选，也会在同正文存在多个实体时给出 `action_allowed=false`。没有 handle 版本的点击定位、动作合同或结果绑定，所以本版仍不支持对同正文双对象分别执行已验证业务动作。`register_entity` 也不是由 `create_post` 自动建立的因果登记事务；调用者需提供登记与后续观察来源。

### 冲突与外部更新有了接口，但两个状态表还可能相互矛盾

v003 的 `bind_post` 静默忽略已有帖子新值问题已修复：第 75–86 行现在拒绝 posts 内的 liked/reactions/comments 矛盾，返回差异且保留原状态。第 244 行的 `reconcile_entity` 默认 verify 也拒绝差异；只有调用者显式选择 `external_update` 才接受变化，并记录 `prediction_credit=false`。

外部反应或评论变化会把相应 reset-relative delta 置为 `None`，`plan(like)`/`plan(comment)` 在第 162/171 行阻止依赖这些基线的写入；第 181–184 行只输出仍为已知整数的业务 delta。这一处理避免用未知基线制造准确增量预测。限制是：状态里没有公开 rebase 操作来重新建立这些基线；相关 delta 是全局域计数，所以某对象的外部变化可能阻断同域其他对象的后续写入。缺省 verify 和显式 external_update 是不同模式，现有接口没有独立证据证明变化确实来自外部；provenance 是调用者提供的字符串。

还存在一个新的**双表一致性缺口**。entities 保存实体状态，posts 保存动作使用的正文状态，两者没有统一绑定入口。限定公开产物子审查在内存复现：

```text
register_entity(h, body=B, liked=true, reactions=9, comments=7)
bind_post(B, liked=false, reactions=3, comments=1, unique=true) → 接受
plan(like, body=B) → 接受，并把 entity h 覆成 true / 4 / 1
```

原因是 bind_post 只对 posts 内已有记录对账、只检查同正文实体数量；register_entity 只向 entities 写入；动作先读取 posts，再把计算结果复制回唯一同正文 entity（helper 第 75–86、231–236、157–178 行）。于是两边各自类型正确，仍可合在一起形成矛盾状态。最小修复验收应覆盖两个登记顺序，并要求跨表矛盾拒绝或经过显式协调，不能靠下一动作覆盖来消除差异。

### 槽归一化已经接通，支持范围仍有限

第 218 行起新增 `normalize_job_row_binding`，把三个位置文本叶子合成 `location_mode` 字符串，并把 Save/Saved 转为布尔值；第 267 行的 `bind_contract_rows` 直接消费 validator 的 `rows.each`，保留每行 capture-local parent 来源，然后写入 state.rows。本审查把两行合成合同的真实绑定输出交给该函数，得到预期的三字段公开身份。这实质补上了 v003 中“合同数组与业务字符串没有共享转换入口”的缺口。

两个归一化入口仍不是对所有允许字符串都互为逆变换。子审查复现：合同侧接受 `['North • South', ' • ', 'Remote']` 并拼合；可见身份入口按 `split(' • ')` 分割，因得到三段而拒绝。故“作者记录的 12 行 roundtrip 一致”只适用于那些已观察数据，不是全类型域证明。应统一这两个入口的接受范围，或把含内部同分隔符的数据明确标为未知格式。

`bind_contract_rows` 只完成行身份和来源绑定，并未顺带建立 jobs 中的全部业务状态；保存/申请前仍需要相应 job 绑定。它也不接收完整 assessment 来自行验证整体 pass、每行 verdict 或采集真实性；调用者必须在已通过合同门禁之后交入绑定。不能把一个可接受绑定列表的函数视作整个观察流水线已自动受监督。

### v004 证据与未支持的数据结构

作者 summary（本地历史引用，未随精选包归档；来源：`construction-012 / v004-summary.json`）记录 construction012 的 2 次浏览器探测、19 个动作，一次 completed、一次计划停读；identity sidecar（本地历史引用，未随精选包归档；来源：`construction-012 / v004-identity-evidence.json`）把同正文卡片和本地因果句柄明确列为作者观察推断，没有声称独立后台身份真值。本审查没有重读原始抓取。

公开匹配（本地历史引用，未随精选包归档；来源：`construction-012 / v004-public-matching.json`）的 4 条 pass 全部 `commitment_verified=false`；state controls（本地历史引用，未随精选包归档；来源：`construction-012 / v004-state-controls.json`）记录 19 项；structural controls（本地历史引用，未随精选包归档；来源：`construction-012 / v004-structural-controls.json`）记录 5 项负控制及 12 行归一化。这些是作者自检，不能算独立 UI 成绩。通用 v3 清单的 27 项离线及两组 live 控制验证通用机制，也不能替代目标模型的独立网站执行。

本版数据结构已能表达未知数量下的统一重复合同、当前 DOM/AX 节点集合、独立于正文的本地实体句柄，以及带差异记录的观察协调。仍未提供：未匹配对象的全集证明、完整 AX 子树模型、持久服务端实体身份、同正文多对象动作、实体与正文状态的统一不变量、外部变化后的基线重建，以及跨任意文本格式的可逆归一化。**上述新增结论来自公开实现与有限合成检查；独立消费者和网站业务结果继续留给协调者补充。**

访问记录补充：本节完成后，为向作者转交最小反例，`list_agents` 同时返回了消费者的完成状态简述。未打开消费者任务、脚本或答案文件，也未把该摘要用于本节检查或结论。

## 12. candidate005 / v005：双表一致性的定向回归

本节只追加新版本结果。公开包 MANIFEST（本地历史引用，未随精选包归档；来源：`model-candidate-005 / MANIFEST.json`） 摘要为 `968ac19b10be379cb64bc4c1d0de3df836c48af25105aa541c11d9f37f955790`；本次读取的八个包内文件均匹配清单。实际模型变化集中在 components_v4.py（本地历史引用，未随精选包归档；来源：`model-candidate-005 / components_v4.py`），结构合同和其余七份已读文件沿用 v004；未读取 `CONSUMER.md`。没有访问消费者、源码、private/oracle 或浏览器。

新增 `registry_consistency`（第 325 行）检查同正文唯一实体与 posts 共享字段是否一致，以及多实体时是否还残留可操作的 body alias。`bind_post`、`register_entity`、`plan`、候选匹配和协调接口先检查已有状态；一致绑定可以补齐唯一实体的共享字段。第二个同正文实体登记时，会删除正文 alias 并记录 `body_alias_invalidated`，保留实体候选。

本次主审按七类路径直接调用冻结 helper，限定公开产物子审另执行了 **12 个纯模型控制**；两者有内容重叠，不合并成一个统一通过率。

| 独立纯模型复核 | 实际结果 |
| --- | --- |
| 原反例：先 register_entity(true/9/7)，再 bind_post(false/3/1) | 拒绝且原状态不变；原问题已修复 |
| 逆序 bind_post → register_entity，分别改变 liked、reactions、comments | 三类矛盾均拒绝，原状态不变 |
| 一致完整注册、部分签名补齐、随后合法 like | 接受，返回状态的两表一致性检查通过 |
| 第二个同正文实体登记、正文/丰富签名匹配 | alias 删除并留记录；正文保留两个候选；当前签名唯一也不给重复正文写入资格 |
| 重复正文的 like、重新 body bind、预先存在的重复 alias | 均阻断 |
| 默认 verify 遇到新观察差异 | 拒绝，保留原状态 |
| 合法状态上的显式 external_update | 同步共享值，`prediction_credit=false`，相关 delta 置 None，后续 like 阻断 |
| 人工构造已冲突的两表，调用 plan 或 external_update | 两者都拒绝；external_update 不能静默修复腐败 prior |

这些结果支持定向修复已经落实。对应位置为 helper 第 75 行的 bind_post、第 243 行的 register_entity、第 256 行的 alias 失效处理，以及第 269 行的 reconcile_entity；不是仅改写规则书措辞。

### 仍有 plan 输出不变量的缺口

入口检查尚不能保证每个计划返回的一定是一致状态。主审另在纯内存复现下列已被公开函数接受的输入链：

```text
已认证 feed 初态
register_entity(h, body=B, liked=true, reactions=9, comments=7)
bind_post_absence(B, matching_cards=0)
plan(open_composer) → plan(fill_post, body=B) → plan(create_post)
```

最后 `plan(create_post)` 返回 `ok=true`，把 posts[B] 建为 false/0/0，却保留 entity h 的 true/9/7。对这个返回状态立即调用同版 `registry_consistency`，得到 `ok=false`、`post and entity registries disagree`。各输入状态本身未被原地修改。

定位在第 205 行的 `bind_post_absence` 和第 166–167 行的创建分支：前者接受新的正文不存在声明，后者只检查 posts 和 absent_posts 后生成正文记录，没有处理已有同正文实体，也没有在返回前复核输出不变量。这是函数接口接受一串互相冲突的声明后产生不一致状态的反例；**没有证明真实网站会正常出现该操作链或结果**。最小后续验收应覆盖 absence/create 与实体登记的交叉路径，要求在动作派发前明确拒绝，或提供有证据的实体生命周期转移；不能只依靠下一动作再发现腐败状态。

v005 也没有增加 entity-handle 动作合同、外部基线重建、完整候选全集证明或新的归一化支持域；第 11 节关于这些能力边界仍适用。

### 自检与独立回归分开报告

作者 summary（本地历史引用，未随精选包归档；来源：`author-adaptation-005 / summary.json`）和 registry-regression.json（本地历史引用，未随精选包归档；来源：`author-adaptation-005 / registry-regression.json`）记录 **85 项作者纯内存检查**；policy-check.json（本地历史引用，未随精选包归档；来源：`author-adaptation-005 / policy-check.json`）是固定 AST 检查。本审查没有把它们重跑或改计为“独立85项”。本节表格来自另行直接调用公开 helper，包含已通过回归和新增输出不变量反例。

v005 登记 `source_calls=0`、`source_actions=0`，结构合同字节未变，独立网站验证未运行。这次回归只支持有限模型接口结论，不新增网站业务通过成绩，也不追溯改写 v004 的独立执行结果。

## 13. candidate006 / v006：已知序列的最终有限复核

本节追加 v006 的有限回归结果，保留此前版本的失败记录。新包 [MANIFEST](../model-v006/MANIFEST.json) 摘要为 `ecf648eff1e8d2667938ec53504180e6226b060359fca96f31740421b09dcc35`；本次读取的八个公开文件与清单一致。未读 `CONSUMER.md`、消费者、源码或私有 oracle，未运行浏览器，也未扩大到新的业务范围。

**在这批已知纯模型序列中，未再复现此前的阻断问题。** [components_v4.py](../model-v006/components_v4.py) 第 213 行的 absence 绑定拒绝已知正文对象；第 169 行的创建分支也检查同正文实体，并在创建后消费 absence 前置条件。第 343 行把“已知对象与 fresh-body absence 同时存在”纳入一致性错误；第 201/303 行及第 358 行的 `checked_state` 对返回状态增加检查。该实现变化针对的不只是入口。

主审实际检查 **13 个调用步骤：9 个按预期接受、4 个按预期拒绝**。拒绝步骤原状态均保持不变；接受步骤的返回状态均通过同版 `registry_consistency`：

| 已知范围内的复核 | 实际结果 |
| --- | --- |
| 已登记 entity 后再声明同正文 absence | 在 absence 绑定处拒绝；v005 原反例不能继续产生创建计划 |
| 人工保留“已知 entity + 旧 absence”的冲突种子，再调用 create_post 或 bind_rows | 两者入口均拒绝，不修改种子 |
| 新正文 absence → open_composer → fill_post → create_post | 接受，返回状态一致，absence 被消费 |
| 对新建正文 register → like → open_comments → fill_comment → comment | 接受，每步返回状态一致 |
| 对已创建正文再次声明 absence | 拒绝，不修改原状态 |

限定公开产物子审另外复跑 **12 项已知逆序/alias 控制，12 项符合预期**：bind_post → register 的三类共享字段矛盾拒绝；一致注册、部分签名补齐后的 like 正常；第二个同正文实体注销 body alias；丰富签名唯一仍不赋予重复正文写权限；重复正文写入、重新绑定和旧重复 alias 均阻断。对应 helper 第 256、272、117、343 行。两组报告保留各自分母，不把 setup 调用或每次断言拼成更大的独立成绩。

[作者 summary：发布回归摘录](../PURE-MODEL-CHECKS.json)（原始 summary.json 未归档）记录深度不超过 3 的有限状态序列、4807 项作者检查和固定 AST 结果；[补充回归：发布回归摘录](../PURE-MODEL-CHECKS.json)（原始 additional-regression.json 未归档）另记 6 项冲突种子检查。本审查没有重复作者整套 4807 项，也没有将这些数字计入上述独立复核。

结论限于这些已知序列的修复。它不是所有 Python 输入、所有状态转移或所有 UI 可达状态的不变量证明。结构 bundle 沿用 v004；候选全集、持久身份、重复正文 handle 动作、外部基线重建及归一化接受域等未新增能力的边界仍保留。**本节新增浏览器调用为零；真实固定任务的完成、拒绝、停读和副作用结果由协调者另行汇总。**
