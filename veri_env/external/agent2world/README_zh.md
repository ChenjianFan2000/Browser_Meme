<h1 align="center">
🌍 <b>AGENT2WORLD：利用自适应多智能体反馈学习符号化世界模型</b> 🌍
</h1>

<div align="center">

[![文档][docs-image]][docs-url]
[![Hugging Face][huggingface-image]][huggingface-url]
[![Star][star-image]][star-url]
[![软件许可证][package-license-image]][package-license-url]

</div>

<div align="center" style="background-color: #e8f5e9; padding: 18px; border-radius: 14px; border: 2px solid #2e7d32; margin: 22px 0;">

  <p style="font-size: 1.08em; margin: 8px 0; line-height: 1.55;">
    <b>Agent2World</b> 是一个工具增强的多智能体框架，用于从自然语言规格生成 <b>可执行的符号世界模型</b>
    （如 <b>PDDL</b> 域与 <b>可运行模拟器</b>）。它以 <b>执行反馈</b> 为核心，捕获静态校验容易遗漏的行为级错误。
  </p>

  <p style="font-size: 0.98em; margin: 8px 0 0; line-height: 1.5;">
    <b>关键点：</b>
    <b>推理阶段</b> 在 PDDL 与可执行代码基准上取得一致的 SOTA •
    <b>训练阶段</b> 利用修复轨迹进行 SFT，微调后平均相对提升 <b>+30.95%</b>
  </p>

  <h3 style="color:#2e7d32; margin: 14px 0 8px 0;">
    🧩 Overall Pipeline
  </h3>

  <p style="margin: 0;">
    <a href="assets/method.pdf" title="Open high-resolution PDF">
      <img src="assets/method.png" alt="Overall Pipeline of Agent2World (click to open PDF)" style="max-width: 900px; width: 100%; height: auto;" />
    </a>
  </p>

  <div style="margin-top: 14px;">
    <a href="README.md" style="background-color: #424242; color: white; padding: 9px 16px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 0 6px; display: inline-block;">
      🇺🇸 English
    </a>
    <a href="https://agent2world.github.io" style="background-color: #2e7d32; color: white; padding: 9px 16px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 0 6px; display: inline-block;">
      📘 文档
    </a>
    <a href="#安装" style="background-color: #1e88e5; color: white; padding: 9px 16px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 0 6px; display: inline-block;">
      ⚡ 快速开始
    </a>
  </div>
</div>

# 📋 目录

- [📋 目录](#-目录)
- [项目目录结构](#项目目录结构)
- [🛠️ 安装](#️-安装)
  - [选项 1：使用 uv（推荐）](#选项-1使用-uv推荐)
  - [选项 2：使用 venv + pip](#选项-2使用-venv--pip)
  - [选项 3：使用 conda](#选项-3使用-conda)
  - [🔐 设置环境变量](#-设置环境变量)
    - [选项 1：使用 `.env` 文件（推荐）](#选项-1使用-env-文件推荐)
    - [选项 2：直接在终端设置环境变量](#选项-2直接在终端设置环境变量)
- [🚀 快速开始](#-快速开始)
  - [1) CWMB（Code World Models Benchmark）](#1-cwmbcode-world-models-benchmark)
    - [1.1 生成 CWM 环境](#11-生成-cwm-环境)
    - [1.2 评估规划性能](#12-评估规划性能)
    - [1.3 结果分析](#13-结果分析)
  - [2) ByteSized32（Reasoning-heavy Text Games）](#2-bytesized32reasoning-heavy-text-games)
    - [2.1 代码生成](#21-代码生成)
    - [2.2 评估](#22-评估)
    - [2.3 表格与图（可视化）](#23-表格与图可视化)
  - [3) Text2World（PDDL World Models）](#3-text2worldpddl-world-models)
    - [3.1 生成（多进程 / 并行）](#31-生成多进程--并行)
    - [3.2 评估](#32-评估)
  - [🧩 模型与后端支持（统一入口）](#-模型与后端支持统一入口)
  - [贡献](#贡献)
  - [引用](#引用)
  - [许可证](#许可证)
  - [⭐ Star History](#-star-history)

<!-- # 📊 Benchmarks & Results

<p align="center">
  <img src="assets/text2world_result.png" width="900" />
</p>

<p align="center">
  <img src="assets/cwmb_result.png" width="900" />
</p> -->

<!-- <p align="center">
  <img src="assets/bytesized32_result.png" width="900" />
</p> -->

# 项目目录结构

```text
🤖 src/
├─ 🌐 agentic_world_model/ – 核心 Agentic World Model 逻辑  
├─ 🧰 toolkits/            – 环境运行、评估、网络搜索、适配器等工具包  
├─ 🧠 models/              – OpenAI / OpenRouter / DeepSeek / vLLM 等后端  

📈 results/  
– 自动生成的 CWM、运行日志与分析产物
```

# 🛠️ 安装

> **注意：无论使用哪种安装方式，都需要先拉取三个基准仓库**（用于生成/评估流程）。

```bash
git clone https://github.com/cognitiveailab/BYTESIZED32.git ByteSized32
git clone https://github.com/nicoladainese96/code-world-models.git code-world-models
git clone https://github.com/Aaron617/text2world.git text2world
```

## 选项 1：使用 uv（推荐）

```bash
# 1) 创建虚拟环境
uv venv .venv --python 3.10

# 2) 激活环境
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

# 3) 安装本项目依赖
uv pip install -r requirements.txt

# 4) 安装基准库（editable）
uv pip install -e ByteSized32
uv pip install -e code-world-models/RTFM
```

> 提示：也可以不激活 `.venv`，直接使用 uv 运行命令：
>
> ```bash
> uv run pytest -q --tb=short --capture=no
> ```

## 选项 2：使用 venv + pip

```bash
# 1) 创建虚拟环境
python3.10 -m venv .venv

# 2) 激活环境
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

# 3) 安装本项目依赖
pip install -r requirements.txt

# 4) 安装基准库（editable）
pip install -e ByteSized32
pip install -e code-world-models/RTFM
```

## 选项 3：使用 conda

```bash
# 1) 创建环境
conda create -n agent2world python=3.10 -y
conda activate agent2world

# 2) 安装本项目依赖
pip install -r requirements.txt

# 3) 安装基准库（editable）
pip install -e ByteSized32
pip install -e code-world-models/RTFM
```

## 🔐 设置环境变量

本项目通过环境变量读取模型后端与 API Key。推荐使用 `.env` 文件，便于复现与管理。

### 选项 1：使用 `.env` 文件（推荐）

1. **在项目根目录复制模板并生成 `.env`**：
   ```bash
   cp .env_example .env
   ```

2. **编辑 `.env`，填写你使用的后端与密钥**（最小运行通常只需 `OPENAI_API_KEY`）：

   ```env
   # --- Minimal (required for most examples) ---
   OPENAI_API_KEY=...

   # --- Optional: custom OpenAI-compatible base url ---
   OPENAI_API_BASE_URL=https://api.openai.com/v1

   # --- Optional: other backends ---
   OPENROUTER_API_KEY=...
   DEEPSEEK_API_KEY=...
   VLLM_BASE_URL=http://localhost:8000/v1

   # --- Optional: runtime ---
   MODEL_TIMEOUT=180
   ```

> **提示**：如果你只跑最小示例或单一后端，只需要保留对应的 key，其余字段可以留空或删除。

### 选项 2：直接在终端设置环境变量

- **macOS/Linux (Bash/Zsh)**：

  ```bash
  export OPENAI_API_KEY="your-openai-api-key"
  export OPENAI_API_BASE_URL="https://api.openai.com/v1"   # 可选
  ```

- **Windows (命令提示符 CMD)**：

  ```bat
  set OPENAI_API_KEY=your-openai-api-key
  ```

- **Windows (PowerShell)**：

  ```powershell
  $env:OPENAI_API_KEY="your-openai-api-key"
  $env:OPENAI_API_BASE_URL="https://api.openai.com/v1"    # 可选
  ```

# 🚀 快速开始

本节给出三大基准（CWMB / ByteSized32 / Text2World）的最小复现流程：**生成 → 评估 → 汇总/可视化**。

## 1) CWMB（Code World Models Benchmark）

### 1.1 生成 CWM 环境

```bash
# 生成 idx = 0,1,2 的 CWM
python scripts/run_agentic_world_model_cwm.py \
  --idx 0,1,2 \
  --model "deep research" \
  --save_dir "results/cwm/agentic_world_model"
```

> **默认行为**：省略 `--idx`（以及脚本中的 `--env` 相关参数）将处理默认的全部 **18** 个任务。

### 1.2 评估规划性能

```bash
python code-world-models/src/experiments/eval_planning.py \
  --save_dir results/cwm \
  --experiment_name "agentic_world_model" \
  --n_episodes 10
```

参数说明：

* `--save_dir`：评估输出目录（日志/结果保存位置）
* `--experiment_name`：方法名/实验名（用于区分不同生成策略）
* `--n_episodes`：每个环境运行回合数（越大越稳定但更耗时）

### 1.3 结果分析

```bash
python code-world-models/analyze_results.py \
  code-world-models/results/cwm/results.json
```

---

## 2) ByteSized32（Reasoning-heavy Text Games）

### 2.1 代码生成

```bash
python scripts/run_code_generate_agentic_world_model.py ByteSized32/data/experiment_action.csv \
  --output-folder results/bytes32/agentic_world_model \
  --model gpt-4.1

python scripts/run_code_generate_agentic_world_model.py ByteSized32/data/experiment_distractor.csv \
  --output-folder results/bytes32/agentic_world_model \
  --model gpt-4.1

python scripts/run_code_generate_agentic_world_model.py ByteSized32/data/experiment_object.csv \
  --output-folder results/bytes32/agentic_world_model \
  --model gpt-4.1
```

### 2.2 评估

```bash
python ByteSized32/scripts/run_code_evaluation.py \
  --game-folder results/bytes32/agentic_world_model \
  --results-file results/bytes32/eval_agentic_results.json
```

### 2.3 表格与图（可视化）

```bash
python scripts/make_table2.py  --results results/bytes32/eval_agentic_results.json
python scripts/make_table3.py  --results results/bytes32/eval_agentic_results.json
python scripts/make_figure4.py --results results/bytes32/eval_agentic_results.json
```

---

## 3) Text2World（PDDL World Models）

### 3.1 生成（多进程 / 并行）

```bash
python scripts/run_text2world_multi_agent_parallel.py \
  --benchmark_type text2world \
  --dataset text2world/pddl_benchmark/our_benchmark.json \
  --output results/text2world \
  --num_workers 1
```

说明：

- Text2World 的 API/模型配置请按 `text2world/README.md` 填写 `text2world/utils/.env`
- 更多模型选项与参数见 `text2world/README.md`

### 3.2 评估

- 请参考 `text2world/README.md` 的评估说明（保持与其官方流程一致）

## 🧩 模型与后端支持（统一入口）

- 支持 **OpenAI / OpenRouter / DeepSeek / vLLM** 等后端，统一通过项目根目录的 `.env` 配置；
- 通过 `ModelFactory` 动态构建与切换不同后端；
- 对复杂规划/长链路任务，推荐使用支持工具调用与长上下文的模型。

## 贡献

欢迎通过 Pull Request 或 Issue 贡献：包括代码改进、工具包扩展与文档完善等。

## 引用

如果本项目对你的研究或工程有帮助，欢迎在文献中引用：

```bibtex
等待添加
```

## 许可证

本仓库以 Apache License 2.0 分发与使用。详见 `LICENSE`。

## ⭐ Star History

[![Star History](https://api.star-history.com/svg?repos=DeepExperience/agent2world-internal&type=Date)](https://star-history.com/#DeepExperience/agent2world-internal&Date)

[docs-image]: https://img.shields.io/badge/Documentation-EB3ECC
[docs-url]: https://agent2world.github.io
[star-image]: https://img.shields.io/github/stars/DeepExperience/agent2world-internal?label=stars&logo=github&color=brightgreen
[star-url]: https://github.com/DeepExperience/agent2world-internal/stargazers
[package-license-image]: https://img.shields.io/badge/License-Apache_2.0-blue.svg
[package-license-url]: https://github.com/DeepExperience/agent2world-internal/blob/main/LICENSE

[colab-url]: https://colab.research.google.com/drive/1AzP33O8rnMW__7ocWJhVBXjKziJXPtim?usp=sharing
[colab-image]: https://colab.research.google.com/assets/colab-badge.svg
[huggingface-url]: https://huggingface.co/agent2world
[huggingface-image]: https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Agent2World-ffc107?color=ffc107&logoColor=white

[ambassador-url]: https://www.camel-ai.org/community
