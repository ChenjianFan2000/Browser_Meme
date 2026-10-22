# REPORTING-001：纯管理报告与交接澄清

本增量仅新增 `report_v002.py`、`review_learning_v002.py`、`handoff_v002.py` 及通用测试。已被 `formal-inputs-001.json` 冻结的原版报告器、controller、runtime 和历史产物均保留，不追溯改写成绩。

最初提出这次汇总审查时，正式学习仍在运行、首次 private 测试尚未开始；本增量实施期间，管理方确认 `formal-001` 已依登记的 `stage all` 在六轮学习冻结屏障后进入评估。因此新增独立 review 使用 `phase=post_freeze_independent_review`，按事实记录评估是否已启动，不预填“首次 private 测试前已完成独立审查”。新增报告和审计不向学习者回传。

## 统计与证据

- 固定六轮各 30 例，总分母为 180 案例、540 个预测字段；A/B 各 90 案例、270 个字段。失败、拒绝、未知、不可评分、unsafe、未运行和基础设施异常不从分母移除。
- 无归档评估时为 `not_started`，不伪造零分。已有归档评估但 UI 动作为零时为 `evaluation_recorded_no_ui_actions`，可报告固定分母统计，同时明确 `browser_actions_measured=false`，单列零动作案例和实际 CLI 退出／超时，不称其为浏览器动作实测。
- CLI 输入、缓存输入和输出保持原字段分别求和，不把缓存输入再次加到输入，不臆算调用数或费用。任务目标成功、业务接受／拒绝和副作用核对分别报告。
- 每例必须有非空 manifest，且至少覆盖 summary 与 registration；验证所有列出的文件哈希及身份，报告同时保留 manifest 本身和 summary 的 SHA256。unsafe 的临时独立结论保留，但不升级为确认成功。
- 结构审查读取可解析动作日志，保留损坏行、缺失日志、缺失动作前／后记录和计数不一致。任一损坏、缺失或 reported 不匹配均不称证据完整。结构审查已完成与模型语义正确、业务覆盖完整分别记录；合法探索失败和诚实未知不自动成为审计未完成。

## 交接准入

`handoff_v002` 要求六个合规冻结包、完整的 v002 结构审查、与 180 例原件逐一一致的完整 v002 评估报告，以及最终独立 review。它验证身份、包／报告／模板冻结绑定、每项必需独立检查及其证据哈希。未知或缺失的必需管理证据、未完成评估、未解决的 blocking 问题不得准入；已披露的模型错误、未知和覆盖限制可以保留为 limitation。低分本身不阻止交接。

独立 review 接口按 `private/phase3/independent-review-reference-v002.json` 对齐。该 reference 的 `is_completed_review=false`，不是审查结果，不能当作准入凭据。新增交接只建立受限冻结包索引，不启动第三阶段，不证明组合新颖性，不把评测答案或管理审计报告提供给首次冻结组合上下文。

## 复现

从仓库根运行通用测试（只用临时生成的 generic 归档，不读取正式模型或任务）：

```powershell
python -m pytest harness/tests/test_phase2_reporting_v002.py -q
```

待相应正式归档和独立 review 实际齐备后，可用全新输出 ID 运行：

```powershell
python -m harness.phase2.report_v002 --report-id <new-id>
python -m harness.phase2.review_learning_v002 --review-id <new-id>
python -m harness.phase2.handoff_v002 --handoff-id <new-id> --learning-review reviews/<review-id>.json --evaluation-report reports/<report-id>.json --independent-review private/audit/<final-review>.json
```

命令使用独占新文件写入；本次开发没有运行这些正式报告或交接命令，没有创建“评估已完成”的正式报告。


## 公开证据交接补充

首次 v002 验证后发现，最终 revision 与 READY 清单不足以解析规则指向 `workspace/evidence` 的原始公共证据引用。交接清单现额外纳入经过 `validate_browser_exports` 校验的脱敏公共证据；公共文件、对应管理原件及其导出哈希清单都必须由 learning manifest 冻结并匹配。最终 revision 内容不改。私有 trace、state、auth、管理审计和评测反馈不进入任务允许清单。

新增测试覆盖规则公共引用可解析、公开证据与管理原件一致、缺冻结覆盖和危险私有导出拒绝。此次新哈希与验证记入 `isolation/reporting-v002-validation-002.json`，保留原 `reporting-v002-validation-001.json`。本补充没有运行正式交接。
