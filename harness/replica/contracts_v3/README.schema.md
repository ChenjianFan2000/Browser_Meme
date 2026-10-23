# 组件合同 v3：可空逐父结构与 DOM/AX 集合一致性

v1、v2 保持冻结。bundle schema 为 `component-contract-bundle/v3`，合同 schema 为
`component-contract/v3`。v2 的 typed slots、has、each、局部 scope 与 prior/postbinding 分账保持不变。

```json
{
  "required":[
    {"id":"container","select":{"source":"dom","tag":"UL","attributes":{"id":"results"}}},
    {"id":"dom_rows","scope":"container","select":{"source":"dom","tag":"LI"},"count":{"min":0},
      "each":{"required":[{"id":"title","select":{"source":"dom","tag":"A"}}]}},
    {"id":"ax_rows","select":{"source":"ax","role":"listitem"},"count":{"min":0}}
  ],
  "relations":[{"id":"row-coverage","kind":"same_dom_set","left":"dom_rows","right":"ax_rows"}]
}
```

`each count.min=0` 必须显式 scope 到当前分支此前的正数、独立 required 容器：
该锚点不能自身有 each，也不能由 `$slot` 选择。已知非空结果继续使用 min=1。
同一预先声明结构可接受 0、1、N 个父节点。零父节点输出显式 `not_applicable` 检查、
`evaluated_instances=0`、`child_passes=0`；不伪造任何子节点通过。

`same_dom_set` 比较左右选中节点对应的 DOM 身份集合，要求双向精确相等。
DOM 节点使用其 `id`，AX 节点使用采集器已映射的 `backend_dom_id`；不按位置配对。
每个选中节点必须有一个无歧义、在同侧不重复的 DOM 身份；任一侧重复映射返回
`unknown(ambiguous_duplicate_DOM_identity)`，防止多个 AX 节点掩盖一个 DOM 节点的覆盖歧义。
两边均空时集合关系成立并记录 `evaluated_instances=0`；缺失 AX 或错误已解析桥接是 fail。
缺失/非字符串身份，`/dom-unresolved/`、`@removed-execution-content` 等未解析标记是 unknown。
`same_dom_node` 要求每边恰好一个节点，然后按同样身份规则比较；模糊单节点 scope 是 unknown。
关系端点若依赖后验绑定，该关系只计入 observation_binding_score。

`evaluation_instances` 返回逐 each 父集合的实例计数与子检查结果；逐父 `bindings["rows.each"]`
及 `rows[父id]/局部检查id` 保持 v2 格式。顶层未知槽仍须预先声明为 `rows.*.title`。
入口 `validate`、`commit_prediction`、`render` 与 v2 相同，assessment 与 symbolic schema 使用 /v3。
