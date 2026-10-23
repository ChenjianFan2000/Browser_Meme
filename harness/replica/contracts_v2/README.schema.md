# 组件合同 v2：逐父节点合同与后代过滤

v1 不变。bundle schema 为 `component-contract-bundle/v2`，合同 schema 为
`component-contract/v2`；基础模式、槽、分支、覆盖及身份关系继承 v1。

```json
{
  "id":"rows", "select":{"role":"row"}, "count":{"min":1},
  "has":[{"select":{"role":"cell","name":{"$param":"category"}},"count":{"min":1}}],
  "each": {
    "slots":{"title":{"type":"string","required":true}},
    "required":[{"id":"title","select":{"role":"link"},"count":{"min":1,"max":1},"bind":{"slot":"title","field":"name"}}],
    "forbidden":[{"id":"no-alert","select":{"role":"alert"}}],
    "relations":[{"id":"ownership","kind":"ancestor","left":"title","right":"$parent"}]
  }
}
```

顶层动作前 prediction 必须明确声明 `unknown_slots:["rows.*.title"]`。
`each.slots` 仅定义类型，不能替代动作前未知声明。顶层普通槽仍用普通名称。
输出 `bindings["rows.each"]` 为 `[{"parent_id":"...","bindings":{"title":"..."}}]`；
它保留逐父身份，不改变 prior prediction，也不给后验绑定追加先验预测分。

`has` 是父候选过滤条件，数组项取 AND；各项只匹配严格后代与同一 source 树，
默认 count 至少 1，允许 `{"min":0,"max":0}` 表达不存在。`$param` / `$slot` 仍是精确字面量，禁止数据注入模式。

`each` 对每个匹配父节点独立执行；局部默认 scope 为 `$parent`，自定义 scope 只能引用此前局部 required id。
`$parent` 可用于 parent/ancestor/same/different 关系。检查 id 为 `rows[父id]/局部id`。
局部槽逐父隔离；只支持一层 each，嵌套 each 返回 unknown。
each 父节点必须声明正数下界（默认 1）；min=0 返回 unknown，不能掩盖已知非空结果。
零父节点用独立 empty 分支：保留非空 root required，并用 forbidden rows 明确检查结果为空，不使用 each。
缺局部必需子节点、错误状态和归属是 fail；模糊局部 scope、漏绑定和采集不全是 unknown；均应阻止后续动作。

入口与 v1 相同：`validate(contract,prediction,observation,commitment=...)`、`commit_prediction`、`render`。
