# 规则书、状态抽象与可执行网页模型：2026-10-23 学习档案

本目录保存本轮检索与原文核读的全部学习笔记：**15 篇已核读文献，另有 1 篇未取得全文的检索线索**。它是持续研究资料，不是实验成绩，也不宣称已复现任何论文。日期为本轮查阅日期；各篇的论文版本和正式发表状态见分篇记录。

本轮直接对应的问题是：完整 AX 匹配既昂贵也未必保留真正重要的状态；改用摘要或规则，又如何发现遗漏、错误合并和想当然的推断？结论是把“忽略某个差异”当作可反驳的假设，用独立行为结果和后续区分序列检验。文献尚未确立适用于任意网站的最优规则书格式。

当前研究状态见[交接页](../CURRENT_STATE_20261023.md)，最新工程探索见[组件合同精选包](../../harness/experiments/component-contract-pilot-20261023-01/published/README.md)。旧第二阶段已退役；这里保留文献和设计动机，不以其旧成绩支持当前结论。

## 阅读地图

| 文件 | 内容与职责 |
| --- | --- |
| [WEB_LITERATURE.md](WEB_LITERATURE.md) | 6 篇网页表示／规则手册论文＋Judge 待查线索，原文方法、数字口径、局限和复习题 |
| [EXECUTABLE_MODELS.md](EXECUTABLE_MODELS.md) | 4 篇可执行模型论文，状态与接口、修复、回放、规划及前提 |
| [ABSTRACTION_FOUNDATIONS.md](ABSTRACTION_FOUNDATIONS.md) | 5 篇抽象／部分可观测／预测状态／反例精化基础，理论保证所需的条件 |
| [CURRENT_IMPLEMENTATION.md](CURRENT_IMPLEMENTATION.md) | 旧第二阶段退役前的历史审计；不代表当前成果或准入依据 |
| [新试验协议](../../harness/experiments/phase2-representation-20261023-01/PROTOCOL.md) | 先筛表示、再做冻结 E/T/C 的具体设计，状态为草案未运行 |
| [实施清单](../../harness/experiments/phase2-representation-20261023-01/IMPLEMENTATION.md) | 通用 Harness 改动、独立网站评价任务与验收顺序 |

建议学习顺序：**AutoManual → WMA／FragGen → PatchWorld → Memento 3 → POMDP／双模拟／PSR → 两类 CEGAR → 其余对照文献**。先理解实际表示和误差，再学习“什么条件下抽象才有保证”。

## 引用索引

| ID | 文献与版本 | 本轮阅读定位 |
| --- | --- | --- |
| AUTOMANUAL | AutoManual，NeurIPS 2024；arXiv v3 | 规则属性、案例条件更新、消融与初始知识前提 |
| WMA | Web Agents with World Models，ICLR 2025；2410.13232v2 | AX 转移抽象、消融、错误分析 |
| FRAGGEN | Fragment-Based Test Generation For Web Apps，TSE 在线 2022／卷期 2023 | 片段去重与回归 oracle；语义相似的限制 |
| WEBDREAMER | Is Your LLM Secretly a World Model of the Internet?，2411.06559v2 | 简短后果预测、候选排序、多步幻觉 |
| WEBEVOLVER | WebEvolver，EMNLP 2025 最终论文 | 下一 AX 观察、联合训练和内在评价边界 |
| WEBSTEP | WebStep，2606.15673v2，COLM 2026 记录 | 人工构造语义 MDP、过程真值及覆盖限制 |
| MEMENTO3 | Memento 3，2610.11794v1，预印本 | Markdown 规则书、Python 引擎、完整历史回放与替代模型 |
| PATCHWORLD | PatchWorld，2605.30880v4，预印本 | 五接口、非预设 belief、类型化修复及预测／效用分歧 |
| WORLDCODER | WorldCoder，2402.12275v3 | 预设符号状态、转移／奖励程序、一致性与乐观约束 |
| POEWORLD | PoE-World，2505.10819v4 | 属性专家、概率组合、约束和对象提取前提 |
| BISIMULATION | Givan、Dean、Greig，2003 | 动作后果意义下的等价及模型约简保证 |
| POMDP | Kaelbling、Littman、Cassandra，1998 | 历史、隐藏状态、belief 的充分性条件 |
| PSR | Littman、Sutton、Singh，NIPS 2001 | 用未来动作—观察测试的预测表示状态 |
| CEGAR | Clarke 等，2003，CAV 2000 扩展版 | 保守抽象、伪反例及精化；黑盒方法不自动获得证明 |
| AUTOMATA-CEGAR | Aarts 等，2012 | 主动自动机学习中的输入抽象与反例精化 |
| JUDGE-LEAD | Judge，TOSEM 2026，DOI 10.1145/3736162 | **仅线索；全文未成功取得，不作为实质结论依据** |

原文链接、DOI、版本、具体章节、定量分母和复习问题保存在对应分篇，不依赖聊天引用编号。原文观点与“对 Browser_Meme 的研究推导”分别标注；代码公开、正文可读与实际可运行／复现是不同状态。

旧一轮更广的文献见 [veri_env/LITERATURE_REVIEW.md](../../veri_env/LITERATURE_REVIEW.md) 和[旧文献目录](../../veri_env/papers/catalog.json)。GIF-MCTS、VeriEnv、WebWorld、Code2World、Agent2World 等已有材料继续保留；未在本轮重新核读的工作不混进这 15 篇计数。

## 本轮应长期保留的判断

1. **完整观察生成、逐元素精确匹配、行为语义正确是三个问题。** WebEvolver 生成 AX 并不等于全树精确匹配；WMA 抽象转移的局部优势也不是所有网站的普遍结论。
2. **原始证据可以完整保留，模型表示可以压缩。** 保留来源可回查，才能检查模型是不是把关键差异删掉；摘要不能同时充当自己唯一的裁判。
3. **外观相同不保证状态相同，历史相符不保证未来正确。** 当前 AX 不一定包含后台状态、异步结果和历史影响。Memento 3 的历史回放也明确可能无法区分竞争规律。
4. **先固定接口，不必先固定所有状态字段。** PatchWorld 提供接口但不预设内部 belief schema。字段、关系、未知和历史如何表达，仍然应由学习与对照试验决定。
5. **规则、代码和真实环境之间有三道不同检查。** 文本表达完整、代码忠实、真实业务预测正确不可互相替代；模型与自制检查器一致尤其不够。
6. **观察重建更像，不一定更有用。** PatchWorld 的特定消融出现 Token F1 上升而任务成功下降；PoE-World 也把预测和规划表现分开评价。
7. **抽象应允许被反例修订。** 增加条件、历史或状态变量要留下反例、修订范围和回归结果；有限浏览器检验不能冒充 CEGAR 的形式化保证。
8. **E/T/C 是应用效用检验，不足以单独选出好表示。** 需要先测错误合并、无谓区分、多步预测、遗漏副作用与构建成本；还要观察 LLM 是否在补偿错误代码。

以上综合判断有文献支持的部分，也包含本研究的设计推论；其操作化和反驳条件以新协议为准。

## 勘误与避免误引

- WMA 的错误类别分析是 **50 个选取的错误预测**；100 个随机预测对应另一项覆盖评价。旧综述把二者混写的句子已在其入口加勘误提示，本轮详见 WMA 笔记。42% 不能不带样本与分析口径直接解释为总体错误率。
- FragGen 的 98.7% 是其**可见变异检测**结果，不是业务语义理解正确率；“页面匹配不依赖阈值”也不等于所有处理步骤均无阈值。
- AutoManual 正式会议题名使用 **Constructing**，本轮 arXiv v3 使用 **Generating**，两者是同一工作的不同记录。去掉 Type 的消融还改变了相关指令，不能当纯视觉排版实验。
- WebStep 的语义状态由受控站点构建并审核；不能说它已解决从任意 AX 自动发现正确状态。
- WorldCoder 的对象状态、PoE-World 的 RAM 对象提取，以及 Memento 3 的确定性离散画面，均是迁移到真实网页时需要重新验证的前提。

## 资料管理与维护

本目录无需额外软件依赖；UTF-8 Markdown 可直接阅读。根目录 README 和总体实验方案提供入口。后续增加论文时记录查阅日期、固定版本、原始链接、已读章节、结论与局限；未读全文的线索独立标注。更新结论保留日期和理由，不追溯修改冻结实验成绩。

**管理侧资料，不自动进入阶段二学习包。** 本目录含已讨论的历史站点结果和评测策略；后续学习者只收到另行审核的通用合同，不能继承这些研究笔记中的网站答案。
