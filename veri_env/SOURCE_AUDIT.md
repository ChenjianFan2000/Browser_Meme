# 公开源码获取与可运行性审计

本次获取 **10 个作者公开主仓库、2 个 PoE-World 的固定版本子模块，共 1877 个源码/文本文件**。所有还原文件均按 Git blob 的 SHA-1 校验；不是网页正文摘录。完整递归树、commit、每文件 blob SHA、排除原因、许可证文件位置、ZIP 路径与 SHA-256 见 [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)。每棵 Git tree 均为 `truncated=false`。源码与上游字节一致，未修改作者实现。

`external/VeriEnv-main` 是用户提供的独立代码包，未写入或修改；原 ZIP SHA-256 为 `a6a8159d89849bc82b53a437c1d6ed6492ae4dd8ba138ce1358bc58d81950a96`，已解压 1205 entries，此数不计入上述 1877 文件。

## 固定版本与范围

| 项目 | 作者仓库 | 固定 commit | 已获取源码/文本 |
|---|---|---|---:|
| WorldCoder | haotang1995/WorldCoder | `9d9fc8d55b7537e2cc1e667a13185a0f2c9d9404` | 51 |
| PatchWorld | HKBU-KnowComp/PatchWorld | `5079da9203913381f45ed2e1df92c73c30571e2e` | 50 |
| WMA-Agents | kyle8581/WMA-Agents | `dd894640204895b52f050c66cc0b58f08e00f9b8` | 123 |
| WebDreamer | OSU-NLP-Group/WebDreamer | `e58941109170ca9f12658116d8e65bc70c1c57f3` | 11 |
| WebEvolver 及同仓库项目 | Tencent/SelfEvolvingAgent | `a82450e1b5e15070bee79ee8b79f8d9a97cb85f7` | 209 |
| GIF-MCTS | nicoladainese96/code-world-models | `e17e787b41137793bcef9f860bdfe9e6fc07b768` | 248 |
| PoE-World 主仓库 | topwasu/poe-world | `b499fb16a60793840a8ad97b3739518c7505ca3a` | 89 |
| WebWorld | QwenLM/WebWorld | `42fe66514869350646712f1226cda5ce1dde98cc` | 29 |
| Code2World | AMAP-ML/Code2World | `f01a98ffe8430c33cbd0490f917da1595974aed1` | 396 |
| Agent2World | DeepExperience/agent2world | `1330f3cde9509f05d204a255f0f7f43208515dce` | 126 |
| PoE 的 LLM 接口子模块 | topwasu/openai-hf-interface | `5838212297dff1bb4176af8606722664abe83d8f` | 11 |
| PoE 的 Atari 子模块 | topwasu/OC_Atari | `43b920b05dc457c36fa5f1ae8953b3a5537e51e7` | 534 |

12 个本地 ZIP 放在 `artifacts/source_downloads/*-source.zip`。PoE 主 ZIP 包含已展开的两个子模块，各子模块也单独打包。清单中的两个 `expanded_submodule` 是原始 gitlink 条目，不是遗漏源码。

排除的是图片/视频/字体、APK/JAR、ROM、NumPy/回放二进制、压缩数据、模型权重等资产，以及 3 个超过 1 MB 的 JSON 数据结果：WMA 的 `mind2web/data/memory/exemplars.json`，VScan 的两份评测结果。SVG 作为示意图资产排除。全部路径、大小和 blob SHA 仍保留在清单。没有排除 Python/Java/JavaScript 等源码文件。模型服务、训练数据及软件依赖未随源码自动安装。

Memento 3（2610.11794）在本轮论文/项目材料和仓库搜索中未找到可核验的官方公开代码；检索到的早期同名仓库不能据此归属于论文。此项状态是“未找到”，不是“已复现”。

## 能复用什么、如何接本地 issue 域

| 项目 | 原始核心与接口 | 本地 issue 子域的适配与限制 |
|---|---|---|
| PatchWorld | `patchworld/worldmodel_base.py`：`GraphState`、`BaseWorldModel` 的 `parse_observation/init_belief/predict_belief/correct_belief/readout_observation`；`worldmodel_data.py` 的 `Transition/Trajectory`；`worldmodel_validator.py` 的 `load_model_from_code/validate_model`；`worldmodel_inducer.py` 的 `Inducer.tracepatch_induce/refine`；`inducer_prompts.py`、`residual_memory.py`。 | 可将用户可见 issue 页面规范化为观测字符串、动作字符串和轨迹，保留原诱导、失败诊断、候选选择与修补流程。validator 含 Maze/Wordle/Textcraft/Webshop 专用比较逻辑，issue 应审计通用分支并补明确的观测比较适配；预测与看到新观测后的 correction 须分开计分。核心 validator/data/base 只需标准库与本包；Inducer 顶层还需 `openai`。默认 OpenAI 兼容 DeepInfra Qwen3-Coder 服务，可显式注入实际 model/base_url。无需作者专属训练 checkpoint，但换模型属于配置变化。 |
| WorldCoder | `worldcoder/agent/world_model/main.py` 的 `WorldModel.predict`；`agent/synthesizer/init_transit.py`、`refine_transit.py`、`synthesizer.py`、`evaluator.py`；`agent/planner/mcts.py`。 | `predict` 输入为 `(state, mission, action)` 列表，state/action 需有 `to_pyrunnable(exec_globals)`，state 还需 `from_pyrunnable`，reward_code 是 mission 到代码的映射。issue 需实现这些表示适配、experience/env_metadata 和可观察奖励约定；只喂 JSON 不是原接口。原转移/奖励综合与反例修订可保留，不能仅写一个生成函数即称完整原版。主要额外依赖含 dill、gitinfo、LLM SDK 及其包导入链。没有必需的作者训练权重。 |
| GIF-MCTS | `src/mcts/gif_mcts/gif_mcts.py` 的 `GIF_MCTS`；`code_state_node.py` 的 `CodeStateNode`；`parser.py` 的 `Parser`；`simulators/simulator_cwm.py` 的 `SimulatorLLM`（包中别名 `SimulatorLLMCWM`）；`data/prompts/`。 | 可保留 Generate/Improve/Fix 节点搜索与执行反馈，将 CWM 测试接口换成 issue 观测转移集合。原 `form_generate_prompt/form_fix_prompt/form_1_step_improve_prompt` 和 `check_code_world_model` 应连同搜索规则复用。包 `__init__` 会导入 torch、mloggers、autopep8 等，而完整环境路径还需 gymnasium；源码到位不表示环境已安装。基于基础代码模型生成，无必须的作者专属 checkpoint；替换模型、任务测试和预算都需记录。 |
| PoE-World | `learners/world_model_learner.py` 的 `PoEWorldLearner.synthesize_world_model/update_world_model`；`learners/models.py` 的 `MoEObjModel/WorldModel`；`obj_model_learner.py`、`synthesizer.py` 与 `prompts/synthesizer.py`；`programs.py`、`classes/helper.py`。 | 原法是 Atari 对象、属性、交互与概率专家的程序模型；issue 必须定义对象类型、属性、动作及观测似然，并保留专家候选、评分和更新。这是领域适配，单个一般代码 prompt 不构成 PoE 原版。依赖 torch、hydra/omegaconf、dill、已下载的 openai-hf-interface 与 OC_Atari；Atari ROM 不在源码中。issue 域可绕开 Atari 执行环境，但应说明更换表示与反馈。 |
| WMA-Agents | `run_w_world_model.py` 的原候选搜索/模型调用流程；`agent/agent.py` 的 `PromptAgent/SearchAgent`；`agent/prompts/jsons/state_prediction/` 和 `value_function/`；`dataset_construction/`。 | 状态预测与价值提示可用本地 issue 可见文本/动作适配；搜索与评分流程须保留才可声称方法适配。原实现深度绑定 browser_env、WebArena actions、Playwright、tiktoken、LangChain 和 torch；完整原法的状态预测模型/训练数据流程不能由通用模型的一段 prompt 取代。未下载或训练专属权重。 |
| WebDreamer | `world_model.py` 的 `WebWorldModel.state_change_prediction_in_website/action_proposal_in_imagination/state_change_prediction_in_imagination/multiple_step_change_prediction`；`simulation_scoring.py` 的 `single_action_simulation/evaluate_simulation`。 | 可输入本地 issue 页面截图、任务和动作描述，保留原想象、动作提议及打分模板。它输出文本状态变化与想象轨迹，不会自动成为可执行 Python 状态机。顶层强导入 anthropic、openai 及 `llms.utils`，运行评分还需 numpy/Pillow/tqdm。需真实兼容多模态模型服务；不必训练作者 checkpoint。 |
| WebEvolver | `WebEvolver/data/world_model_sft_data_construction.py`、`traj_synthesizing_world_model.py`；`WebEvolver/cognitive_kernel_v2/` 的原代理服务。 | 可复用轨迹到世界模型 SFT 样本与合成轨迹流程，将真实浏览器观测/动作替换为 issue 域。原法要求 policy 和 world model 的专门 SFT、vLLM 服务以及多轮共同改进，README 的模型服务配置属于运行前提。只运行数据脚本或换成普通 LLM 不能称原法重现。 |
| WebWorld | `core/tasks/web_wm.py` 的 `WebWorldModelTask.generate_prompt/evaluate`；`core/serve/unified_api.py`；`core/runner.py`、`demo/`。 | 原提示与 benchmark 输入可映射为本地页面状态和动作，但原方法的预测能力来自 Qwen/WebWorld-8B/14B/32B 专属权重。需要模型、tokenizer、模型服务以及 jsonlines/json_repair 等依赖；源码脚手架自身不是已训练世界模型。不得将 Luna 替换推理标作 WebWorld 权重复现。 |
| Code2World | `android_world/agents/m3a_qwen.py`，同目录代理集成，`server/`、`run.py`。 | 预测下一 GUI 的可渲染代码，再渲染为截图；需要显式适配 issue 浏览器截图/动作与渲染，不等于结构化 issue 状态转移程序。README 要求 GD-ML/Code2World 8B checkpoint，并依赖 AndroidWorld/emulator、其模型推理与 HTML 渲染服务。源码未带训练权重；通用模型生成 HTML 是替代基线。 |
| Agent2World | `src/agentic_world_model/agentic_world_framework.py` 的 `initialize_agent/agent2world_gen_code/agent2world_gen_cwmb_code`；`mcts_gen.py`；`src/prompts/{gen_code,play_code,pytest_code,research}.py`。 | 可保留研究、写代码、执行/玩家、pytest 角色交互与反馈，注入本地 issue simulator 和有预算的测试工具。`initialize_agent` 内各角色实际硬编码 OpenRouter GPT-4.1-mini，虽然签名接受 model_name；还会创建 sandbox、安装/运行工具代码并依赖检索服务，不能无审计直接启动。`consistency/gif_mcts_generic.py` 中作者自带的 `run_gif_mcts_simple` 不是 GIF-MCTS 论文作者原仓库的完整实现。原推理需要相应 API，训练结论需要其训练流程/模型；替换模型和工具要标适配。 |

## 轻量核验与实际阻碍

- [audit_results.json](artifacts/source_downloads/audit_results.json) 记录当前 Python 版本、逐仓库 Python AST 检查、依赖探测及 PatchWorld 原包 smoke import。全部 1020 个 Python 文件语法解析通过。AST 检查只证明语法可解析，不代表端到端复现。
- 实际导入并核对了原 `GraphState`、`BaseWorldModel`、`Transition`、`Trajectory`、`validate_model` 与 `load_model_from_code`；原轨迹 dataclass 的步数/任务观测行为通过。没有调用远程 LLM、下载后安装脚本、训练流程或完整 benchmark。
- 审计时缺少的依赖精确列表在 JSON 中，含 anthropic、gitinfo、mloggers、gymnasium、hydra/omegaconf、jsonlines/json_repair、Playwright、loguru、tiktoken、func_timeout、pygame、ale_py 等。PoE 接口源码已取得，但尚未安装为 `openai_hf_interface` 包。完整测试首先受这些依赖与模型/服务前提限制。
- PatchWorld validator 的 `signal.setitimer` 超时仅适用于 Unix；Windows 上直接跳过。因此生成代码执行需调用方另加进程级超时。源码没有因此被修改。
- 多仓库复用了 `src`、`core`、`agent`、`classes`、`utils` 等顶层包名。应分别启动进程或独立虚拟环境，不能将所有根目录无序加入同一个 PYTHONPATH。
- WMA-Agents、WebDreamer 未找到独立根许可证文件；WMA README 标注 MIT，并另有数据许可标注；WebWorld 的 Apache-2.0 声明在 README。其余独立及嵌套许可证路径都在 manifest，原文件随源码保存；不要把依赖目录许可证自动当成整个研究仓库的授权。

本地 git/urllib 直连外网受 WinError 10013 限制；本轮改用只读 GitHub MCP 的固定 tree/blob 获取成功。早期高并发工具宿主中断未影响落盘文件；之后持久化分批获取。两份 JSON 遇到远程断连后已重试成功，最终清单不保留未完成的源码条目。

可重跑 `python scripts/download_sources.py` 从保存的 MCP payload 恢复、校验并重新打包，再运行 `python artifacts/source_downloads/audit_sources.py`。前者是本地还原工具，不会执行作者代码；它不直接联网。payload 和完整 tree inventory 是本次获取的可审查证据。实验若只抽取原模板、解析函数或部分搜索组件，结果须明确标注“原组件复用/领域适配”；这里没有声称已复现任何论文性能。
