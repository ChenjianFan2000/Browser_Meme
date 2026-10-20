# 独立源码覆盖审计

日期：2026-10-20。审计者：独立 Solar 子上下文。此次职责由通用 Harness 审查切换为源码覆盖审计；本上下文已经接触目标源码，不得用于阶段二独立学习。

## 范围与方法

只读检查 `harness/sites/discogs/model/pw-v002/{rulebook.md,rules.json,source_review.json}`、`pw-v001-audit-supplement.json`、目标网站文件清单及源码，并阅读公开的 `.runtime/phase1-discogs-pw-20261020-1633/diagnostics/anchor-initial-002-routing/DIAGNOSIS.md`。没有读取独立 evaluator、private_eval、task_instructions 内容或测试答案，没有修改冻结模型、目标网站或任务脚本。

自动核对整个目标目录与清单，以及清单的逐文件 SHA256；逐条核对 rules.json 源码引用的文件存在性及行号范围。语义复核采用重点模块交叉阅读，不声称审计者重新完整理解了全部99个标记已读文件。重点阅读全文包括 account/auth/deps/catalog/marketplace 后端、cart/sell/login/search 客户端、ReleaseActions/LogoutButton、后台请求封装、通配rewrite、认证及动态membership/cart/listing代理、数据库session、后端配置及应用入口。

## 可验证结果

- 清单覆盖110个原始文件，目标树无未登记文件；110项 SHA256 全部匹配。
- 状态明确区分99项 `read`、1项依赖元数据检查、6项仅资产登记、4项明确排除。任务生成器、上游任务文件及上游smoke不计作业务已读。没有把110文件完整性等同110文件业务理解。
- 页面、组件、客户端状态、认证服务、权限依赖、输入schema、数据模型、migration、启动与运行配置均在作者清单中；未发现这些类别的整个重要目录漏列。
- 24条规则的所有源码引用文件均存在；两处引用超过文件末行，见下表。
- 规则书主体明确标注源码支持与浏览器待验证。rules.json 对部分规则增加 `observed_branches` 及部分浏览器证据状态；末尾记录404反例，明确规则监控匹配不等于业务终点通过。不能据此声称24条规则全部分支实测通过。

## 发现及交回作者的修正项

| 项目 | 发现 | 最小处理 |
| --- | --- | --- |
| 引用精度 | CART-ADD 引用 `backend/app/schemas/cart.py:29-31`，实际30行，CartAddIn从27行开始；RUNTIME 引用 `frontend/package.json:1-30`，实际26行 | presentation附录给出更正引用，冻结产物保持原样 |
| 对应关系粒度 | 多个account代理的source_review条目使用同一概述且 `rule_ids=[]`；清单证明存在阅读声明，不能单凭概述证明逐路由分析充分 | 作者附录补充静态/动态代理与相关规则、cookie转换、拒绝传播的对应关系 |
| 运行可达性 | CART-REMOVE、SELL-MANAGE的规则主体仍描述正常UI终点；404补记主要点名membership及卖家搜索 | 附录逐项区分后端源码语义、当前部署可达性、已实测404、从相同rewrite机制推断但未实测的动态删除/更新/停用 |
| 条件与实测 | 通用代理丢query支持条件性422，但当前请求先被rewrite拦截而得404 | 保留“实际进入catch-all以后”的条件；不得把422写作当前运行的已测结果 |
| 退出登录失败分支 | LogoutButton等待fetch后不检查HTTP成功状态，非2xx已解析响应仍refresh/push；因此导航本身不能证明cookie已清除 | 作者附录增加HTTP拒绝分支，标注源码支持、未实测 |

上述项目已通过协作消息交给 `solar_source_model`，要求只补presentation附录，不改冻结模型。本审计不代替作者补写规则。附录是否完成及其内容需另行查看作者产物，本文件不预先宣布修正完成。

## 结论与限制

文件清单及哈希完整性通过；重点源码复核支持作者已覆盖主要架构类别。规则证据层级基本明确，但尚需补足代理逐路由映射、当前部署可达性和退出登录拒绝分支。引用存在两处小范围越界。现有证据不足以认证全站业务理解完整、全分支覆盖、冻结泛化或严格速度对照成绩。

公开404诊断来自另一独立部署审查者：本审计阅读并核对其与原始配置/源码的一致性，没有重放请求，也没有重新验证其构建内部路由顺序。该因果诊断及其环境边界按原文保留，不扩大为跨平台事实。
