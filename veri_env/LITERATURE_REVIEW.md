# 文献综述：从网页交互学习可执行、可修正世界模型

检索日期：2026-10-20。检索范围限定在论文原文（arXiv/会议论文）、作者项目页和作者仓库；本地 `chae26a.pdf` 是 VeriEnv 论文。下面将“核心”限定为直接支持从交互证据构建或使用可预测模型、并有持续验证/更新机制的研究；网页应用相关但表示不可执行的工作列为直接背景；相邻 GUI 或通用模型生成工作用于界定边界。文中“未见代码/权重”表示截至检索日，在所查官方材料中未找到可确认的公开产物，不代表作者绝无私有实现。

## 纳入标准和研究定位

纳入核心综述的工作至少满足一项：从交互或轨迹中学/合成环境动态；用生成模型显式预测动作结果供规划或控制；或提供可执行规则、回放验证、反例修复。直接网页工作即使内部表示为自然语言/神经网络也纳入，因为它们提供同域任务、观测、推理用途和失效证据。仅生成静态网页、普通任务执行器或与交互状态转移无关的代码生成不纳入。WebWorld、Code2World、Agent2World作为2026邻接工作核查：WebWorld是网页仿真训练模型而非代码状态转移；Code2World针对 Android GUI 的渲染代码预测；Agent2World面向一般符号世界模型生成。其原论文成绩不与核心论文合并排名；本轮另外检查其源码，并按实验协议运行可比较的 Luna 推理适配，Code2World只做原生组件检查。

本地目标见 [研究目标.md](../研究目标.md)，当前实施以 [README](./README.md) 与 [实验协议](./EXPERIMENT_PROTOCOL.md) 为准：本轮使用自建、可重置的 issue 管理微型网页，提供固定动作接口和完整可观察业务状态；不是真实 GitLab 实例，也不使用 WebArena。它侧重操作规律预测、组合流程和规则改变后的修复，不测控件自主发现、视觉定位、隐藏状态辨识或长期在线学习。未来如开展严格 UI/API 速度对照，可把固定版本的真实 GitLab 部署作为下一阶段候选，届时另行核验副作用等价与权限；那不是本轮设置。

## 主要发现

`chae26a.pdf` 与原研究目标有基础设施层面的相似性：都涉及可执行网页、操作后果和验证。**VeriEnv 的主要产物是用于训练 agent 的克隆网站与奖励判定；原目标的主要产物是由交互证据学到、能持续修正的站点行为模型。** 因此 VeriEnv 适合承担实验环境、重置、SDK和验证层，WorldCoder、PatchWorld及Memento 3更接近学习与修正机制。这里不把克隆网站本身当作已经从有限证据学到规律的证明。

| 工作 | 主要表示 | 从什么证据学习或预测 | 修正机制 | 在本研究中的位置 |
|---|---|---|---|---|
| VeriEnv | 可运行克隆网站、SDK、判定程序 | 截图/网站说明、生成任务轨迹 | 网站调试、策略训练 | 环境与独立验证底座 |
| WorldCoder | Python转移/奖励函数 | 对象状态与交互 | 反例修订、乐观可达约束 | 程序动力学与规划 |
| GIF-MCTS | 候选Python程序树 | 描述、回放、执行测试 | Generate/Improve/Fix搜索 | 合成搜索与预算对照 |
| PoE-World | 程序属性专家与概率组合 | 对象轨迹、示范 | 专家合成、拟合和更新 | 模块化规则与不确定性 |
| PatchWorld | belief、转移、校正、读出程序 | 离线文本轨迹 | 类型化反例和程序补丁 | 最接近可执行预测器的验证链 |
| Memento 3 | 规则书与执行引擎 | 持续交互和预测失配 | 分开修订假设与实现 | 当前方案的机制参考，无可核验代码 |
| WMA | 转移焦点文本 | 网页轨迹训练/当前页动作 | 候选动作筛选，非代码修补 | 神经差分预测对照 |
| WebDreamer | 想象的状态变化 | 当前截图和候选动作 | 推理期想象与打分 | 无专用训练的直接预测对照 |
| WebEvolver | 下一无障碍树模型 | 真实/合成轨迹 | agent与模型共同训练 | 训练型模拟器对照 |
| WebWorld | 网页神经模拟器 | 开放网页轨迹 | 训练与推理搜索 | 规模化模拟器背景 |
| Code2World | 下一GUI的HTML渲染代码 | Android截图和动作 | 神经生成与视觉前瞻 | 视觉模型背景，非业务状态程序 |
| Agent2World | 代码/PDDL模型及测试 | 说明、研究工具、执行反馈 | 多角色研发和测试闭环 | 生成/测试流程参考 |

这是一轮有明确边界的定向调研，共12篇；不宣称穷尽截至检索日的所有世界模型论文。论文原表、作者代码和本轮实际结果分开保存。

文献有两条互补但尚未合并的路线。网页智能体研究通常把状态变化编码为自然语言差分、下一页文本/无障碍树或神经世界模型，以候选动作筛选、lookahead或生成训练轨迹；它们与网页任务同域，却较少将模型作为可审计的站点规则程序持续修补。代码世界模型研究把转移、条件、状态和预测写成程序，并通过回放失败修正；但代表性验证大多在网格世界、文本环境或 Atari，通常把环境状态预先结构化，和真实网页 DOM/业务后端之间仍有感知、状态抽象及动作映射差距。

因此，研究贡献不应仅以“写出代码模型”或完成任务定义。更有判别力的证据是：对未见参数/状态的一步预测准确；对未演示操作组合的多步预测和执行；状态转移规律被受控改变后，预测误差能否定位到假设或实现并修复；修复是否保留其他已学规则。仅重放训练历史精确匹配不足以证明新状态泛化，任务成功或速度也不能独立证明模型理解。

## 逐篇证据

### 核心：可执行代码模型及其在线修正

#### WorldCoder（arXiv:2402.12275）

[论文](https://arxiv.org/abs/2402.12275)；[作者仓库](https://github.com/haotang1995/WorldCoder)。问题是低交互预算下学习可解释、可迁移的动力学模型，并用于规划。输入为环境返回的结构化对象状态、离散动作、奖励、终止和自然语言目标；论文假定确定性、目标间动力学固定的 episodic MDP。表示是 Python 转移函数 `T` 与按目标区分的奖励/终止函数 `R`，状态是对象集合及其字段。它在线积累交互，周期性用 GPT-4 生成/修订程序；学习时要求历史转移一致（φ1），同时要求模型规划器认为可达奖励（乐观约束 φ2）。通过深度受限价值迭代或 MCTS 规划，执行结果进入回放数据；新反例触发程序修订。环境是 Sokoban、MiniGrid、ALFWorld，不是网页。

关键实测：Sokoban 上模型在前 **50 个动作**内建立，之后可以不再调用 LLM 执行；作者报告 2-box 基础关卡的 ReAct 成功率为 **15%±8%**，深度 RL 学会 2-box 需 **>1M** 步（论文图3；该比较不是网页指标）。作者也加入带细微开关规律的 teleport gate 变体验证程序能学习新动力学。其证明建立在真模型属于候选程序类、确定性和最优规划器等假设下，不可直接外推到部分可观测、异步网页。仓库公开，README警告旧版 NumPy/Gymnasium/MiniGrid兼容性；论文基于 GPT-4，代码公开不等于在 Luna 上复现论文性能。

#### GIF-MCTS（arXiv:2405.15383，NeurIPS 2024）

[论文](https://arxiv.org/abs/2405.15383)；[作者仓库](https://github.com/nicoladainese96/code-world-models)。目标是提高 LLM 合成 Python 环境模型的成功率。模型输入取决于环境轨迹/回放缓冲；程序的 `step(s,a)` 联合输出下个状态、奖励与终止。GIF（Generate, Improve, Fix）让 MCTS 在多个候选程序及增量改写中搜索，执行单测/回放并反馈缺陷，最终由生成模型参与模型构造；用程序做后续仿真、规划，而非每步再问 LLM。候选模型通常依赖预先结构化状态和可回放转移，属于离线/回放驱动的合成，不是浏览器在线探索。

Table 1 的 APPS competition split **strict accuracy**（整题所有测试均通过）为 **28.3±1.4%**：Llama 3 70B、pass@20；WorldCoder 和 Zero-shot CoT 的对照分别为 25.1±1.4%与23.2±1.3%，均标作作者重实现。不要把代码问题成绩解释为网页世界模型预测成绩。作者另评 Code World Models Benchmark 与 Gym 任务，并报告模型可用于规划；具体单环境数值受模型、轨迹与预算影响。官方仓库有实验脚本和回放缓冲，并允许通过 `--budget` 控制 LLM 请求；复现需要原模型/API及环境，不是 Luna 一次性替换就等价。

#### PoE-World（arXiv:2505.10819，NeurIPS）

[论文](https://arxiv.org/abs/2505.10819)；[作者项目与代码](https://topwasu.github.io/poe-world)。针对整体单程序难以少样本学习复杂世界，方法将规则拆成大量 programmatic experts，并以指数加权的 product-of-experts 组合对随机环境进行概率预测。以 Atari 对象级观察和动作、短演示及 LLM 生成专家为输入；不直接看网页 DOM/业务内部状态。通过程序模块学习规则，专家组合建模随机性；误差反馈用于迭代模型合成。推理时用于层级规划/lookahead，也可在模型内预训练 PPO 后回环境微调。

Table 1：PoE-World + Planner 在 Pong / Pong-Alt 得分分别 **−12.33±0.88 / −13.67±0.67**，在 Montezuma’s Revenge / MR-Alt 为 **100±0 / 100±0**；WorldCoder + 同一层级 planner 是 −17±3、−19±1、0、0。注意 PoE/WorldCoder先获得 Pong 和 MR 的简短演示，之后最多训练3k步再评估；分数含义是 Pong 21分制结束时玩家对手分差，MR只有拿到钥匙才为正，不能与 WebArena 成功率比较。Table 2/3评估下一个观察及对象属性预测，作者报告大多数设置领先，但 Pong 随机帧测试没有充分触发击球规则。代码可见，运行论文实验使用 OpenAI 调用预算（作者报告每次 run 约20美元），完整planner在某些阶段并行约100 CPU，单模型加 planner 通常低于24小时；不可当作廉价在线网页修正基线。

#### PatchWorld（arXiv:2605.30880）

[论文](https://arxiv.org/abs/2605.30880)；[作者仓库](https://github.com/HKBU-KnowComp/PatchWorld)，[轨迹数据集](https://huggingface.co/datasets/HKBU-KnowComp/patchworld-trajectories)。这是“显式 belief + 可执行转移/校正/渲染”最接近本研究的修补机制之一。输入是离线 observation-action-next-observation 轨迹，仅文本观察；每环境生成独立 Python `BaseWorldModel`，含 parse、`init_belief`、`correct_belief`、`predict_belief`、readout 五类接口。LLM从对照性训练轨迹合成程序，执行回放验证器产生类型化反例，再由 LLM提出局部修补，只有验证回放改善才接受。在线模型推理本身可不调用 LLM；但这不意味着整个 agent或归纳流程没有 LLM。规划时仍由 ReAct LLM提出候选动作并由 LLM选择，实验测到的是世界模型作为独立预测模块的边际效用。

评测覆盖 AgentGym 七环境：AlfWorld、BabyAI、Maze、SciWorld、TextCraft、WebShop、Wordle；不含真实浏览器网站。摘要报告 PatchWorld-Simple 的实时一步前瞻宏平均成功率 **76.4%**。Table 2 的 held-out next-observation 评测使用 Token F1/BLEU-4（不是业务正确率）；文中 PatchWorld-Residual 的代码模型最好为 Qwen3-Coder-480B 下 0.69/0.50，Mimo-v2.5或DeepSeek-V4-Flash下最高0.70 F1，较配平的 WorldCoder/PoE-World行约高6–7点。Table 3 平均 rollout Token-F1：LLM-Direct 在 t=1/2/3/5 为 .64/.63/.60/.59，WorldCoder .63/.60/.58/.57，PoE .63/.57/.53/.51，PatchWorld-Simple .56/.50/.43/.40；预测词面匹配优势不等于控制效用优势。归纳每环境约17–28次 LLM 调用、300k–503k tokens，运行时预测模块0次 LLM 调用。Qwen3-Coder-480B、Mimo-v2.5、DeepSeek-V4-Flash作为归纳backbone；在线 agent 候选动作仍有LLM。公开代码和轨迹，仓库包含WebShop但未包含可复用的本地微型网页适配，且核心训练为离线轨迹和 AgentGym，需重新映射到本地网站。

#### Memento 3（arXiv:2610.11794）

[论文](https://arxiv.org/abs/2610.11794)；本地 [Memento 3 PDF](../2610.11794v1.pdf) 与 [VeriEnv PDF](./chae26a.pdf) 均已核对。Memento 3以冻结 LLM 和持久外部记忆解决新证据下环境假设修订。历史观察/动作及模型预测输入；表示拆成 Markdown rulebook（对象、动作语义、动力学、目标与未决假设）和 Python `world_model_engine.py`（内部状态、预测、渲染、目标判断）。每个交互周期由冻结 Claude Opus 5 harness 选择 retain / revise_rulebook / repair_code，再编译并回放；规则与实现分别诊断，回放要求对历史画面逐格一致，之后模型用于规划。此设计特别适合区分“规则错”与“代码实现错”，但历史精确重放仍不能证明未见状态预测正确。

评测为 ARC-AGI-3 的25个公开游戏（只能经动作接口交互）及 Atari Pong 案例，不是网页。论文 Table 1 报告25/25游戏均达到 **RHAE 100**（上限），总计7,518动作，即人类动作数44%；Pong在3个不同开局的评估episode均21:0获胜，运行期无需LLM调用。此结果依赖 Claude Opus 5 extra-high、coding-agent式工具环境；并且不同系统基线数来自官方榜单，不是同一模型重跑。规则书消融 Table 3 只选每个难度一款游戏，with rulebook 的动作数 ft09/ka59/cn04 为75/341/201，对比无 rulebook 79/382/216，支持规则书有益但样本很小。未发现作者仓库/权重链接；论文原文可审读，但不能假称复现其使用权重或模型配置。

### 直接网页背景：预测页面变化并供动作选择

#### VeriEnv（arXiv:2603.10505）

[论文](https://arxiv.org/abs/2603.10505)；[作者仓库](https://github.com/kyle8581/VeriEnv)。它不是可执行世界模型，而是可验证网站重建和网页智能体训练框架：GPT-5.2/Cursor按参考页面构造站点、后端数据库与Python SDK，再生成由可执行谓词核验的任务。训练轨迹通过成功判定筛选后用于Qwen3-4B或Llama-3.2-3B-Instruct监督微调；站点调试中也会按浏览器报告修补环境，但没有从交互轨迹归纳持久转移规则的机制。论文报告149个合成网站、7,400项任务。Table 3人工评估含30个独立样本、每个样本双标注（共60份标注），judge correctness为76%，task executability为90%，功能正确率均值90.3%，视觉评分4.7/5；不能将60份标注称为60个独立实例。Table 4 WebArena-Lite显示Qwen3-4B总成功率7.88%→13.94%（+6.06个百分点）；Llama-3.2-3B-Instruct为3.03%→12.73%（表中Δ +9.70），但正文写+9.09，存在报告不一致。它证明可验证环境可支持训练，不证明模型学到了可修正的站点世界模型；用Luna替换其训练底座不能复现原论文增益。

#### WMA（arXiv:2410.13232，ICLR 2025）

[论文](https://arxiv.org/abs/2410.13232)；[作者仓库及模型/数据](https://github.com/kyle8581/WMA-Agents)。WMA从 WebArena/Mind2Web 轨迹训练 Llama-3.1-8B-Instruct world-model adapter，输入 instruction、当前观察（无障碍树/页面）和动作，预测自然语言的“转移焦点差异”，不重建整个页面。冻结 policy 产生候选动作，world model预测后果，value LLM评分后执行；支持推理期筛选，也能持续自我修正候选动作，但未见在线更新世界模型代码模型机制。模型是神经语言模型，不是可执行状态转移程序。

Table 1 WebArena：GPT-4o、最大动作5时，WMA由无 action selection 的12.8%到有筛选的16.6%（+29.7%相对提升）；GPT-4o-mini为9.4%到13.5%（+43.6%）。Table 2 对 GPT-4o-mini 的域别总体：Vanilla CoT 9.4%，WMA 13.5%；GitLab 3.1%到8.7%。该 WebArena 子集、5步上限与本轮自建微型网页不是同一评测。Table 5显示在Map ablation下完整方案22.0% vs 不训练world model 17.5%、不做transition abstraction 14.5%；具体表的样本数/子集与主榜不同，不应混算。预测错误分析用100个样本、GPT-4o judge：42%为臆造反事实元素，说明下一页语言预测易生成环境中不存在的内容。权重适配器、数据与代码公开，但训练依赖 Llama 微调；用 Luna 直接提示模拟不能算原训练复现。

#### WebDreamer（arXiv:2411.06559，TMLR 2025）

[论文](https://arxiv.org/abs/2411.06559)；[作者仓库](https://github.com/OSU-NLP-Group/WebDreamer)。此工作把 GPT-4o 当作互联网的隐式世界模型，给当前观察、动作和目标，让它生成候选动作的假想结果，再以任务进度评分选择执行项；可组合到截图、DOM等设定。其世界模型主要是通用LLM的上下文预测，不学习可审计程序，也不通过反例持续修正。评估 VisualWebArena、Online-Mind2Web、Mind2Web-Live。

Table 1 成功率（%）：VisualWebArena / Online-Mind2Web / Mind2Web-Live，GPT-4o WebDreamer **23.6/37.0/25.0**；Reactive基线17.6/26.0/20.2；GPT-4o tree search在VWA为26.2。Online-Mind2Web与Live的任务数必须按原数据设置理解，论文该表比较统一重实现基线，不能与WMA的WebArena表拼排名。作者声称较Reactive相对提升34.1%、42.3%、23.8%。Table 2中 GPT-4o 下 VWA 各域 WebDreamer wall time约183.6–233.7秒，Reactive约68.3–87.7秒，说明更高成功率/更多推理计算有成本。代码、Dreamer-7B以及训练数据在作者仓库/HF公开；移植到本轮微型网页时，需独立检验预训练网页知识能否正确预测该站点业务状态。

#### WebEvolver（arXiv:2504.21024）

[论文](https://arxiv.org/abs/2504.21024)；[作者仓库](https://github.com/Tencent/SelfEvolvingAgent)。在自进化web agent循环中，world-model LLM基于观察和动作预测下一无障碍树/页面：一方面充当虚拟网页服务器合成训练轨迹，另一方面用于推理期lookahead。agent 与 world model 联合演化，训练策略比单独WorldDreamer式候选预测更重。表示为文本化页面/Accessibility Tree，非可执行代码模型；有训练数据/模型更新与 agent 训练，不提供显式规则级与代码级分诊修复。

任务覆盖 Mind2Web-Live、WebVoyager、GAIA-web 等真实/在线网页任务。论文 Table 1 的文本 WebVoyager 测试分母473 queries，Mind2Web-Live-filtered为53 queries；同表 Llama-3.3-70B 底座下，初始 self-improve 的 WebVoyager/M2W-Live 为32.98%/18.86%，WebEvolver 为42.49%/22.64%，在 WebEvolver 上加深度2的 WMLA 为51.37%/24.53%。同一表测试分母很小，结果来自两次时间窗实验平均、GPT-4o评估；不与其他论文排行榜横比。论文 Table 2 intrinsic judge 的迭代2模型在 lookahead depth1 的 STR/Sim/OA 为75.96/63.56/72.86%，depth大于2各项降至0.50以下，体现合成树深的误差。作者仓库公开，依赖特定 world-model 和 agent fine-tuning 权重/数据；只用 Luna 实现推理层想象，不是对联合训练的复现。

### 2026邻接方向（背景，不等同核心机制）

#### WebWorld（arXiv:2602.14721）

[论文](https://arxiv.org/abs/2602.14721)；[作者仓库/模型](https://github.com/QwenLM/WebWorld)。WebWorld是以开放网页轨迹训练的神经模拟器，用于合成策略训练数据及推理期搜索；它扩展网页环境规模，但不形成可审计的站点规则程序。Table 5中 Qwen3-14B 微调前后 WebArena 成功率为15.1%→24.3%（+9.2个百分点）；训练用8,000条合成轨迹。Table 6中MiniWob贪心64.3%，配WebWorld/GPT-5成对评分的BoN(3)为67.5%。两表未列任务分母，不能与其他榜单横比。仓库含模型/数据；权重推理成本与Luna微型网页实验并不匹配。

#### Code2World（arXiv:2602.09856）

[论文](https://arxiv.org/abs/2602.09856)；[作者项目/代码与数据](https://github.com/AMAP-ML/Code2World)。将当前 Android GUI 截图、动作、目标映射为可渲染 HTML 代码，再渲染下一截图。Figure 6 在116项 AndroidWorld导航任务上，Gemini-2.5-Flash由41.4%升至50.9%；Table 2 的 AndroidControl-High也报告了模型接入前后结果。它是可编辑代码表达的视觉后果模拟器，但没有从网页业务轨迹持续修订动作条件规则的证据；GUI渲染与本地微型网页业务状态预测不是同一任务。

#### Agent2World（arXiv:2512.22336，2025年末；2026核查的相邻工作）

[论文](https://arxiv.org/abs/2512.22336)；[作者仓库](https://github.com/DeepExperience/agent2world)。通用模型生成流程把知识搜集、PDDL/代码生成与自适应单测、模拟测试组成闭环，并以反馈轨迹微调开发器。Table 1 Text2World上GPT-4.1-mini的Agent2World Multi可执行率93.1%；Table 2 CWMB整体准确率/归一化回报0.5441/0.4811，高于直接生成0.4466/0.2620。Table 3 ByteSized32中其可运行游戏率0.8958。均不是网页交互结果；作者仓库公开，完整SFT用Llama-3.1-8B及8×A100，需相应资源。

## 复现实验设计启示：本地 issue 微型网页

建议保留显式代码模型为核心处理，但必须加入同一 Luna 直接预测基线，避免方法选择只利于代码表征。本轮协议已固定同一自建微型网页、动作接口、观测权限、业务状态和轨迹预算；以下建议细化预测和计分，真实 GitLab 镜像属于后续速度对照的建议，不纳入本轮。

1. **一步预测**：给当前无障碍树/DOM、动作及必要历史，预测可观测业务字段（issue状态、标签、assignee、评论/里程碑）和页面差分。业务状态由实验者独立读取，学习器不可访问隐藏数据库/测试oracle。分别报告字段级精确率/召回率或联合精确匹配、条件判断准确率、页面差分覆盖，不以整页像素完全相同作唯一指标。
2. **2–4步组合**：在单步学习过的操作中组出未演示的组合（例如筛选、更新标签、指派、评论/验证），提供开放环多步预测和实际闭环任务成功两项。区分已学操作缺失与组合失败；按业务状态初值和组合模板切分，防止同轨迹泄漏。
3. **可证伪规则变化**：在测试期受控改变一个动作前提或后果（例如状态仅允许特定角色更新、标签更新改为有状态依赖），记录首次预测失配、错误定位（规则/代码/状态估计）、提出修订、验证通过和对不相关规则的回归影响。将测试期在线修正与固定模型首次泛化分开报告。

对比至少四种方法：A. Luna根据同样轨迹直接给结构化下一状态预测（无额外更新）；B. Luna以相同token/API预算做基于历史的直接预测，并允许维护非执行文本记忆；C. Luna通过提示生成并迭代修复Python转移模型（主方法）；D. 无模型UI Agent/原生脚本基线与可读取业务状态的Oracle上界。A/B/C接受完全相同的观测权限、采样轨迹和训练/验证/测试划分，并输出同一状态字段schema；锁定相同的Luna版本、采样设置与累计调用/token预算。C额外写出的程序必须计入生成/修复token、运行和维护成本，A/B不能被人为限制为不看相同历史。建议对所有预测都先提交结构化预测再执行，避免通过事后解释更新分数。主任务结果、模型预测、变化后修复率及延迟分别报告；固定预算与“允许在线修正”条件分开。复用原文机制时称“基于/改编自 WorldCoder/PatchWorld/Memento 的派生实现”，不要称论文复现。

**模型权重限制**：WMA使用Llama-3.1-8B world-model/value adapters，WebEvolver是联合训练/自进化模型；VeriEnv以拒绝采样轨迹微调Qwen3-4B和Llama-3.2-3B-Instruct。即便这些项目发布权重，统一到闭源 Luna 只能做到相同输入/输出接口的推理适配或重写，不能复现其训练机制或原论文学习增益。WorldCoder/GIF-MCTS/PoE-World/PatchWorld/Memento含程序合成或模型内存机制，更适合做协议思想派生实现，但其结果也不会自动迁移至本轮自建微型网页。

## 可证伪假设

1. **已学原子动作上的参数/状态迁移**：在动作类型已见、参数值或issue当前状态未见的测试样本中，程序模型的业务字段下一状态联合准确率高于同Luna、同轨迹、同累计token预算的直接预测器；如果置信区间不支持差异，或优势只出现在逐字页面文本而非业务字段，假设不成立。
2. **组合迁移来自显式可组合规则**：对分别训练过各原子动作、但未见的2–4步操作组合，代码模型的闭环成功率高于不生成可执行规则的直接LLM基线；若只在已演示流程有优势，或加入等预算文本记忆后差异消失，则该机制主张被削弱。
3. **可修正性带来受控变化恢复**：引入动作前提/副作用变化后，允许在线更新的程序模型在固定数量反例内恢复一步预测准确率，且未变化操作的回归下降低于静态模型/文本预测器；若更新需要测试答案、预测持续漂移或修复后旧规则显著退化，则假设不成立。
4. **预测准确性可解释部分任务表现**：在给定统一任务和动作预算后，模型业务状态预测准确率能预测组合任务成功/恢复率；若两者不相关或收益完全由更多LLM采样次数解释，则“世界模型帮助执行”的解释不成立。

## 文献目录

完整结构化记录见 [papers/catalog.json](./papers/catalog.json)。摘要数值仅在已核对原文表格/图后保留；各论文的任务、底座和计分口径不同，不构成统一排行榜。

