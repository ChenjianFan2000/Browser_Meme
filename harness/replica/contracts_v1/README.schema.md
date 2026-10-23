# 通用组件合同 v1

`schema.py` 与 `validator.py` 只处理声明式 JSON，不包含网站规则、选择器、任务或 oracle。
入口为 `validate(contract, prediction, observation, *, commitment=None)`、
`commit_prediction(prediction)`、`render(contract, inputs, *, branch=None)`。

合同 bundle 为 `{"schema":"component-contract-bundle/v1","contracts":{"example": CONTRACT}}`。
controller 在执行前冻结 bundle，并按 `prediction.contract_ref` 取合同。

```json
{
  "schema": "component-contract/v1",
  "parameters": {"$type":"object", "$required":["heading"], "$properties":{"heading":{"$type":"string"}}, "$additional":false},
  "slots": {"labels":{"type":"array", "items":{"$type":"string"}, "required":true}},
  "coverage": ["container", "items", "no-alert"],
  "branches": {
    "ready": {
      "required": [
        {"id":"container", "select":{"source":"ax", "role":"list", "name":{"$param":"heading"}}, "count":{"min":1,"max":1}},
        {"id":"items", "scope":"container", "select":{"source":"ax", "role":"listitem"}, "count":{"min":1}, "bind":{"slot":"labels","field":"name","many":true}}
      ],
      "forbidden": [{"id":"no-alert", "select":{"source":"ax","role":"alert"}}],
      "relations": [],
      "tree": {"role":"list", "name":{"$param":"heading"}, "children":{"$slot":"labels"}}
    }
  }
}
```

相应动作前预测为：

```json
{"disposition":"accepted", "contract_ref":"example", "branch":"ready", "parameters":{"heading":"Results"}, "unknown_slots":["labels"]}
```

观察 envelope 为 `{"schema":"component-observation/v1","complete":true,"nodes":[...],"evidence_refs":[...]}`。
每个节点至少有唯一 `id`、`parent`（根为 null）、`source`（`ax` 或 `dom`）；
其余字段为观察器提供的 `role`、`name`、`properties`、`attributes`、`tag`、`text`、`visible` 等。
`select` 是节点的递归部分对象匹配，未声明字段不参与匹配。使用 `role` 而未写 `source` 时默认 `source=ax`。
`scope` 指此前 required 项的 id，仅其唯一匹配节点的严格后代可被选择；零匹配或多匹配 scope 是 unknown。
`count` 默认恰好 1；只写 min 表示无上限。forbidden 必须匹配 0 个。

JSON 模式支持精确标量/数组、递归部分对象，以及 `$type`（object/array/string/number/integer/boolean/null）、
`$const`、`$enum`、`$properties`、`$required`、`$forbidden`、`$additional`、`$items`、
`$minItems`、`$maxItems`、`$min`、`$max`、`$anyOf`。未知运算符拒绝。
`$param` 用点路径引用动作前 parameters 的嵌套对象/数组；`$slot` 引用观察绑定槽。
引用值始终作为精确 JSON 字面量匹配，数据中的 `$type` 等键不会被解释为模式运算符。
缺失参数/槽不会成为 wildcard。`branches.<name>.when` 若存在，是 parameters 的模式；预测 branch 必须明确选择一个分支。

槽声明 `type` 为上述 JSON 类型，数组可用 `items` 模式，对象可用 `properties` 模式及 `required_properties`。
`bind` 形如 `{"slot":"labels","field":"name","many":true}`；field 为节点中的点路径，many=true 保持匹配顺序构成数组，默认 false 要求恰好一个匹配。
每个 required 槽必须在动作前 `unknown_slots` 中声明并在本次观察绑定；重复绑定必须相同。
槽只代表外部数据，观察所得值不会回填动作前预测。引用槽的检查单独归入 `observation_binding_score`。

关系项形如 `{"id":"ownership","kind":"parent","left":"items","right":"container"}`；
kind 支持 parent、ancestor、same、different，左右引用 required 项 id。默认要求左右各一个；
`quantifier:"each"` 要求每个 left 至少有一个满足关系的 right，`quantifier:"all"` 要求每对均满足。
identity 属性可作为 `select.properties` 或其他观察字段精确匹配，same/different 检查观察节点 id。

coverage 必须是非空检查 id 列表，且每个 id 实际存在；每个分支至少一个有正数下界、非 wildcard 的 required 项。
结构缺失、状态错误、forbidden 命中或关系矛盾是 fail；采集不全、未知语义、缺失参数/绑定、模糊 scope 是 unknown。
二者均不能放行后续动作。返回值含 `checks`、`bindings`、`coverage` 和分离的 `prediction_score` / `observation_binding_score`。

`commit_prediction` 返回规范 JSON 的 SHA-256；动作前记录这个摘要，动作后传给 validate。
摘要不符直接 fail（prediction_rewritten），不得用后验值改写先验。
`render(contract, inputs, branch="ready")` 将输入代入 tree；未知槽保留为 `{"$unknown":{"slot":"labels","type":"array"}}`。
它校验 inputs；缺失/类型不符时返回 `status=unknown`、input_validation 和未解析参数清单，缺失 tree 参数保留 `$unknown.parameter` 标记。
它输出符号组件树及预测合同，不声称生成完整网站或盲复现副本。
