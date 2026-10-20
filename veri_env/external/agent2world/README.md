<h1 align="center">
🌍 <b>Agent2World: Learning to Generate Symbolic World Models via Adaptive Multi-Agent Feedback</b> 🌍
</h1>

<div align="center">

[![Paper](https://img.shields.io/badge/Paper-PDF-B31B1B?logo=adobeacrobatreader&style=flat-square)](assets/paper.pdf)
[![Documentation][docs-image]][docs-url]
[![Hugging Face][huggingface-image]][huggingface-url]
[![Stars][star-image]][star-url]
[![License][package-license-image]][package-license-url]

</div>

<div align="center" style="background-color: #e8f5e9; padding: 18px; border-radius: 14px; border: 2px solid #2e7d32; margin: 22px 0;">

<p style="font-size: 1.08em; margin: 8px 0; line-height: 1.55;">
  <b>Agent2World</b> is a tool-augmented multi-agent framework for generating <b>executable symbolic world models</b>
  (e.g., <b>PDDL</b> domains and <b>runnable simulators</b>) from natural language specs.<br/>
  It grounds generation in <b>execution-based feedback</b> to catch behavior-level errors missed by static validation.
</p>

<p style="font-size: 0.98em; margin: 8px 0 0; line-height: 1.5;">
  <b>Key points:</b>
  <b>Inference-time</b> achieves consistent SOTA on PDDL & executable-code benchmarks •
  <b>Training-time</b> repair trajectories enable SFT, yielding <b>+30.95%</b> average relative gain after fine-tuning
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
    <a href="README_zh.md" style="background-color: #424242; color: white; padding: 9px 16px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 0 6px; display: inline-block;">
      🇨🇳 中文说明
    </a>
    <a href="https://agent2world.github.io" style="background-color: #2e7d32; color: white; padding: 9px 16px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 0 6px; display: inline-block;">
      📘 Docs
    </a>
    <a href="#installation" style="background-color: #1e88e5; color: white; padding: 9px 16px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 0 6px; display: inline-block;">
      ⚡ Quick Start
    </a>
  </div>

</div>

# 📋 Table of Contents

- [📋 Table of Contents](#-table-of-contents)
- [Project Structure](#project-structure)
- [🛠️ Installation](#️-installation)
  - [Option 1: Use uv (recommended)](#option-1-use-uv-recommended)
  - [Option 2: Use venv + pip](#option-2-use-venv--pip)
  - [Option 3: Use conda](#option-3-use-conda)
  - [🔐 Environment Variables](#-environment-variables)
    - [Option 1: Use a `.env` file (recommended)](#option-1-use-a-env-file-recommended)
    - [Option 2: Set environment variables in terminal](#option-2-set-environment-variables-in-terminal)
    - [1.2 Evaluate planning performance](#12-evaluate-planning-performance)
    - [1.3 Analyze results](#13-analyze-results)
  - [2) ByteSized32 (Reasoning-heavy Text Games)](#2-bytesized32-reasoning-heavy-text-games)
    - [2.1 Code generation](#21-code-generation)
    - [2.2 Evaluation](#22-evaluation)
    - [2.3 Tables \& Figures (visualization)](#23-tables--figures-visualization)
  - [3) Text2World (PDDL World Models)](#3-text2world-pddl-world-models)
    - [3.1 Generation (multiprocess / parallel)](#31-generation-multiprocess--parallel)
    - [3.2 Evaluation](#32-evaluation)
  - [🧩 Model \& Backends Support (Unified)](#-model--backends-support-unified)
  - [Contributing](#contributing)
  - [Citation](#citation)
  - [License](#license)
  - [⭐ Star History](#-star-history)

# Project Structure

```text
🤖 src/
├─ 🌐 agentic_world_model/ – Core Agentic World Model logic
├─ 🧰 toolkits/            – Toolkits for environment execution, evaluation, web search, and adapters
└─ 🧠 models/              – Model backends (OpenAI / OpenRouter / DeepSeek / vLLM, etc.)

📈 results/  
└─ Auto-generated CWMs, run logs, and analysis artifacts
```

# 🛠️ Installation

> Note: Regardless of the installation method, clone the benchmark repos first (used in generation/evaluation workflows).

```bash
git clone https://github.com/cognitiveailab/BYTESIZED32.git ByteSized32
git clone https://github.com/nicoladainese96/code-world-models.git code-world-models
git clone https://github.com/Aaron617/text2world.git text2world
```

## Option 1: Use uv (recommended)

```bash
# 1) Create a virtual environment
uv venv .venv --python 3.10

# 2) Activate
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

# 3) Install project deps
uv pip install -r requirements.txt

# 4) Install benchmark repos (editable)
uv pip install -e ByteSized32
uv pip install -e code-world-models/RTFM
```

> Tip: You can also run without activating `.venv` via uv:
>
> ```bash
> uv run pytest -q --tb=short --capture=no
> ```

## Option 2: Use venv + pip

```bash
# 1) Create a virtual environment
python3.10 -m venv .venv

# 2) Activate
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

# 3) Install project deps
pip install -r requirements.txt

# 4) Install benchmark repos (editable)
pip install -e ByteSized32
pip install -e code-world-models/RTFM
```

## Option 3: Use conda

```bash
# 1) Create environment
conda create -n agent2world python=3.10 -y
conda activate agent2world

# 2) Install project deps
pip install -r requirements.txt

# 3) Install benchmark repos (editable)
pip install -e ByteSized32
pip install -e code-world-models/RTFM
```

## 🔐 Environment Variables

This project reads model backends and API keys from environment variables. Using a `.env` file is recommended for reproducibility and easy management.

### Option 1: Use a `.env` file (recommended)

1. Copy the template to create `.env` in the project root:
   ```bash
   cp .env_example .env
   ```

2. Edit `.env` and fill in the backends and keys you use (minimum run typically only needs `OPENAI_API_KEY`):

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

> Tip: For minimal examples or a single backend, only keep the relevant keys; others can be left empty or removed.

### Option 2: Set environment variables in terminal

- macOS/Linux (Bash/Zsh):

  ```bash
  export OPENAI_API_KEY="your-openai-api-key"
  export OPENAI_API_BASE_URL="https://api.openai.com/v1"   # optional
  ```

- Windows (CMD):

  ```bat
  set OPENAI_API_KEY=your-openai-api-key
  ```

- Windows (PowerShell):

  ```powershell
  $env:OPENAI_API_KEY="your-openai-api-key"
  $env:OPENAI_API_BASE_URL="https://api.openai.com/v1"    # optional

# 🚀 Quick Start

Minimal reproduction flows for three benchmarks (CWMB / ByteSized32 / Text2World): **generate → evaluate → summarize/visualize**.

## 1) CWMB (Code World Models Benchmark)

### 1.1 Generate CWM environments

```bash
# Generate CWM for idx = 0,1,2
python scripts/run_agentic_world_model_cwm.py \
  --idx 0,1,2 \
  --model "deep research" \
  --save_dir "results/cwm/agentic_world_model"
```

> Default: Omitting `--idx` (and related `--env` args in the script) will process all 18 tasks.

### 1.2 Evaluate planning performance

```bash
python code-world-models/src/experiments/eval_planning.py \
  --save_dir results/cwm \
  --experiment_name "agentic_world_model" \
  --n_episodes 10
```

Parameters:
* `--save_dir`: evaluation output directory (logs/results)
* `--experiment_name`: method/experiment name (to distinguish strategies)
* `--n_episodes`: number of episodes per environment (higher = more stable, but slower)

### 1.3 Analyze results

```bash
python code-world-models/analyze_results.py \
  code-world-models/results/cwm/results.json
```

---

## 2) ByteSized32 (Reasoning-heavy Text Games)

### 2.1 Code generation

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

### 2.2 Evaluation

```bash
python ByteSized32/scripts/run_code_evaluation.py \
  --game-folder results/bytes32/agentic_world_model \
  --results-file results/bytes32/eval_agentic_results.json
```

### 2.3 Tables & Figures (visualization)

```bash
python scripts/make_table2.py  --results results/bytes32/eval_agentic_results.json
python scripts/make_table3.py  --results results/bytes32/eval_agentic_results.json
python scripts/make_figure4.py --results results/bytes32/eval_agentic_results.json
```

---

## 3) Text2World (PDDL World Models)

### 3.1 Generation (multiprocess / parallel)

```bash
python scripts/run_text2world_multi_agent_parallel.py \
  --benchmark_type text2world \
  --dataset text2world/pddl_benchmark/our_benchmark.json \
  --output results/text2world \
  --num_workers 1
```

Notes:

- Configure Text2World API/model in `text2world/utils/.env` per `text2world/README.md`
- More model options and parameters are documented in `text2world/README.md`

### 3.2 Evaluation

- Please refer to `text2world/README.md` for evaluation instructions (aligned with official workflow)

## 🧩 Model & Backends Support (Unified)

- Supports **OpenAI / OpenRouter / DeepSeek / vLLM** backends, configured via `.env` in the project root
- Dynamically constructs and switches backends with `ModelFactory`
- For complex planning/long-chain tasks, models with tool-use and long context are recommended

## Contributing

Contributions are welcome via Pull Requests or Issues: code improvements, toolkit extensions, documentation updates.

## Citation

If this project helps your research or engineering, please cite:

```bibtex
```

## License

See `LICENSE` for details.

## ⭐ Star History

[![Star History](https://api.star-history.com/svg?repos=DeepExperience/agent2world-internal&type=Date)](https://star-history.com/#DeepExperience/agent2world-internal&Date)

[docs-image]: https://img.shields.io/badge/Documentation-EB3ECC
[docs-url]: https://agent2world.github.io
[star-image]: https://img.shields.io/github/stars/DeepExperience/agent2world-internal?label=stars&logo=github&color=brightgreen
[star-url]: https://github.com/DeepExperience/agent2world-internal/stargazers
[package-license-image]: https://img.shields.io/badge/License-Apache_2.0-blue.svg
[package-license-url]: https://github.com/DeepExperience/agent2world-internal/blob/main/LICENSE

[huggingface-url]: https://huggingface.co/agent2world
[huggingface-image]: https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Agent2World-ffc107?color=ffc107&logoColor=white
