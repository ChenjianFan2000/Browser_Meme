# 上游原始组件执行审计

本审计覆盖 **VeriEnv 参考实现和另外10个比较项目，共11个源码目录**。实际执行的是原始源码中的可离线运行组件；没有完成任何一篇论文的完整训练、代码合成或导航算法运行，不能把这些通过项作为原方法在 issue 子域上的分数。

重放命令：

```powershell
python -m issue_lab.upstream_audit
```

脚本执行带断言的合成正反例，输出 [artifacts/upstream_audit.json](artifacts/upstream_audit.json)。JSON记录解释器、依赖探测、各源码SHA-256、AST提取行范围、保留方法、替代接口、实际输入输出和声明的执行范围。审计没有读取候选模型文件、private_eval或调用模型服务，没有安装依赖。合成状态由审计脚本手写，使用公开观察schema；没有导入领域实现或读取测试答案。

| 项目 | 本次真实执行的原始组件 | 原版在本机/子域直接运行的边界 | 接入 issue 子域必须修改的接口 | 完整方法的模型/训练要求 |
|---|---|---|---|---|
| VeriEnv | 完整原版 `judge_dsl` 模块；`parse_judge_spec`、`eval_rinfo_checks` 对嵌套JSON检查的正反例 | 判定DSL可直接运行；完整BrowserGym/网站合成链未运行，缺playwright、gymnasium | 任务检查可映射JSON；网站生成、浏览器动作和环境配置需另外适配 | 完整合成依赖LLM/浏览器；DSL不需权重 |
| PatchWorld | 完整原版 `BaseWorldModel`、`validate_model`、`compare_parsed_observations`，通过继承适配回放JSON轨迹 | 验证器可原生运行；inducer、residual memory和repair循环未运行 | JSON字符串parse/correct/readout与`predict(state, action)`包装；评分另加严格JSON检查 | 验证器不需权重；完整学习/修补需LLM后端 |
| WorldCoder | 原版 `_State/_Action`；AST提取的 `TransitEvaluator` 执行函数定位、转换、逐经验预测和对错聚合 | 原版 `eval_code` 在Windows因`signal.setitimer`缺失返回失败；替代执行器之后核心求值通过；完整planner未运行，缺gymnasium | JSON状态/动作子类；Windows可用的执行和超时后端；合成模板/环境API | 完整合成需LLM；求值器不需权重 |
| GIF-MCTS | 原版 `extract_code`、`Parser.parse(fix)`、`CodeStateNode.expand/value`，验证bug节点只生长fix子节点 | AST排除导入；缺mloggers，替换为空日志器；未运行MCTS搜索 | JSON转移代码的提示、回放评估/奖励、搜索预算接口 | 完整搜索需代码LLM服务或本地权重 |
| PoE-World | 原版 `RandomValues`、NumPy分支 `combine_random_values` 及原版归一化函数，实际组合两个专家概率 | 使用已安装真实numpy/scipy；AST排除pygame/torch/game导入；缺pygame、hydra；未拟合对象模型 | 将符号状态、标签/评论等可变列表编码到对象属性；替换游戏动作和轨迹接口 | 原完整方案涉及LLM程序合成和专家拟合；组合核不需权重 |
| WMA | 原版 `parse_playwright_code`，执行合法locator链和非法动作拒绝 | AST提取，TypedDict运行时构造以dict替代；缺playwright、gymnasium；无浏览器或预测推理 | JSON操作映射可执行click/type序列；JSON/浏览器观察转换；差分描述映射完整状态 | 原版提供Llama3.1-8B世界/价值模型适配器，需权重和服务 |
| WebDreamer | 原版 `WebWorldModel.multiple_step_change_prediction(k=1)`，实际进入3次提示/客户端调用并传播想象历史 | RecordingClient返回预声明文本，无真实API；Anthropic类型标记只用于选择OpenAI分支；未预测真实图像 | issue UI截图、业务操作到GUI动作映射；自然语言变化到JSON读出 | 原版GPT-4o/Claude服务或另外替换的VLM |
| WebEvolver | 原版SFT数据脚本的 `extract_info_from_action` 对click/type/stop解析 | AST排除pandas/requests/cognitive-kernel等导入及脚本副作用，隔离提供原设定`LLAMA_VERSION=3.3`；无训练/自进化 | cognitive-kernel轨迹schema、JSON动作/状态转换、新域数据构造 | 原版agent/world-model服务、自进化采样和SFT；README另需Cognitive Kernel部署 |
| WebWorld | 原版BaseTask和选取的 `WebWorldModelTask.generate_prompt` 单步分支；断言期望下一状态未出现在提示中 | 绕过构造器与数据/配置加载，提供合成samples_map；缺jsonlines、json_repair；未运行模型或LLM评判 | 新任务/数据schema；JSON文本可作为页面状态；精确JSON评分需替换原评判接口 | 生成模型后端和原版评判模型 |
| Code2World | 原版 `QwenModel.__init__/post/extract_clean_html`，执行提示构造、token切片、HTML清理和渲染分派 | 权重加载/processor/generate由记录接口替代；HTML保存只记录内存；renderer显式返回False；无截图或权重推理证据，缺android_env/playwright | Android截图/tap改为网页截图/click；HTML图像输出需额外恢复业务JSON；这会改变原生预测目标 | README要求GD-ML/Code2World 8B checkpoint、Android模拟器和渲染栈 |
| Agent2World | 完整原版response解析模块；原版 `select_best_code_candidate` 基于pass-rate排序合成候选 | AST提取排名函数，替换logger；未运行agent、sandbox、生成或self-consistency；原需求含缺失anthropic/gymnasium | 提供issue模拟器/toolkit、测试生成与JSON predict接口，替换text2world/bytesized任务 | agent模型后端；可选SFT；解析器/排名不需权重 |

上表的缺失依赖是针对已检查调用路径的探测结果，并非整个requirements的穷举。完整原法在issue子域的可行性不能仅由Python模块可导入判断。每一行都需要对应的数据、动作、预测读出及训练/服务准备后才能进入算法对比；其论文报告分数也不属于本地子域结果。

## PatchWorld 原生验证钩子

```python
from issue_lab.upstream_audit import native_patchworld_validate

result = native_patchworld_validate(
    code_path,  # 调用者明确指定的Python源文件，定义 predict(state, action)
    [{"state": public_before, "action": public_action, "next_state": observed_after}],
)
```

还可传入`[{"transitions": [...]}]`或原版`Trajectory`对象。观察和动作会JSON序列化；`env="issue_lab"`避免把完全观测业务状态错误声明为原版局部观测游戏。适配器继承原版`BaseWorldModel`，以真实观察执行correction、调用候选`predict`完成prediction、以JSON执行readout；原版`validate_model`继续负责加载、循环和原生错误分类。候选代码的语义完全来自调用者文件；钩子没有生成规则、搜索模型路径或读取其他实验文件。

返回字段：

- `errors`：原版验证器的错误列表。
- `strict_errors`：同次原始prediction调用的严格JSON不一致；保留大小写、空白、列表顺序及JSON数值类型。
- `strict_prediction_checks`：实际检查的prediction调用数。原验证器每步通常调用两次prediction，不能把此数当独立样本量。
- `passed`：原生验证与严格检查均通过；非空轨迹还要求至少发生一次prediction。
- `trajectories`、`transitions`：回放量。

原比较器对字符串做小写/空白归一化，对列表排序。因此“仅把标题改成大写”的错误预测能通过原生比较器。审计用这个反例确认`errors=[]`且`strict_errors`非空、最终`passed=False`。统一JSON评分应使用严格结果；保留原生结果只用于注明上游判定行为。

注意：该钩子的 `strict_errors` 是原始JSON序列检查；主评分器则把issue记录、标签和选中ID视为集合并排序，而保留评论与显示顺序。通用情况下两者不必相等，不能用原生钩子分数替代主表。当前生成模型回放已单独保存于 `artifacts/results/patchworld.native_validation.json`；repaired 的24条一步转移和 adapted 的12条变化转移均通过。首次回放因 Windows UTF-8 BOM 触发加载失败，记录保留在 `patchworld.native_validation.first_attempt.json`；适配器随后改用 `utf-8-sig` 读取，未修改冻结的模型文件。

钩子执行调用者提供的Python代码。原版Unix信号超时在Windows不可用，因此以`method_timeout_s=0`明确关闭；需要硬超时的调用者应在外层有超时的独立子进程运行。原版loader的临时Python文件在调用结束后清理。不要在同一进程并发调用本钩子，因为临时模块追踪会短暂包装原版loader。

## 本次执行证据

本次11项组件均执行成功。脚本断言包含：VeriEnv正反任务判定；PatchWorld正确预测、错误预测和归一化误通过反例；WorldCoder正确/错误转移分别得到1/0经验符合率；GIF修复分支；PoE概率归一化；WMA非法语法拒绝；WebDreamer三次实际原始调用与历史传播；WebEvolver三类动作解析；WebWorld下一状态提示隔离；Code2World原始token切片/HTML清理/失败渲染分派；Agent2World最终JSON解析和候选排序。

这些是组件接口执行和适配可行性证据，不是完整方法的预测、任务成功率或训练结果。
