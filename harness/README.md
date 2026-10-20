# 通用 Harness

## 当前：独立 Solar 模型与直接 Playwright

用户于 2026-10-20 固定了[职责边界](../AGENTS.md)：主 Agent 只维护上层
Harness 并调度运行；独立 `gpt-6.1-sol` subagent 阅读完整网站源码、
撰写规则书与实现原生 Playwright 脚本，另一独立上下文负责站点部署与评价。
不使用 agent-browser 或重标号元素引用作为实验接口。

新入口为 [playwright_run.py](playwright_run.py)，接口见
[SCRIPT_CONTRACT.md](SCRIPT_CONTRACT.md)，当前独立协议见
[第一阶段 Playwright 实验](experiments/phase1-discogs-pw-20261020-1633/PROTOCOL.md)。
本轮实际运行、限制及复现入口见
[实验记录](experiments/phase1-discogs-pw-20261020-1633/RESULTS.md)，
[中文规则书与证据展示](experiments/phase1-discogs-pw-20261020-1633/solar-presentation/report.html)
由独立 Solar 模型编写。
模型公开对象是原生 `playwright.sync_api.Page`；`h.step` 和 `h.confirm`
负责预测落盘及证据记录，不预设目标网站的业务动作。

该运行器每任务使用独立进程和浏览器上下文，Windows 通过 Job Object
清理拥有的浏览器后代进程；后台评价与脚本生成分开。保存逐步原始 DOM、
遮蔽凭据输入框的截图、脱敏网络反馈、Playwright DOM/动作轨迹、
独立后台观察、固定分母和完整失败记录。第一阶段的可信 Python 脚本
接口不是操作系统沙箱。

从仓库根目录执行。2026-10-20 的隔离运行环境已准备完成；
新机器先按部署适配器准备依赖。在一个终端启动站点并保持运行：

```powershell
$env:BM_DISCOGS_RUNTIME='G:\Browser_Meme\.runtime\phase1-discogs-pw-20261020-1633'
$env:HARNESS_STOP_FILE="$env:BM_DISCOGS_RUNTIME\stop-UNIQUE_ID"
python harness/sites/discogs/deploy.py serve
```

另一个终端执行。`UNIQUE_ID` 每次换成未使用的值：

```powershell
$env:BM_DISCOGS_RUNTIME='G:\Browser_Meme\.runtime\phase1-discogs-pw-20261020-1633'
$env:HARNESS_CHROME='C:\Users\29935\AppData\Local\Google\Chrome\Application\chrome.exe'
& "$env:BM_DISCOGS_RUNTIME\venv\Scripts\python.exe" -m harness.playwright_smoke --out harness/runs/pw-smoke-UNIQUE_ID
& "$env:BM_DISCOGS_RUNTIME\venv\Scripts\python.exe" -m harness.playwright_run --site harness/sites/discogs/site-pw.json --model-dir harness/sites/discogs/model/pw-v002 --protocol harness/experiments/phase1-discogs-pw-20261020-1633/PROTOCOL.md --out harness/runs/pw-anchor-UNIQUE_ID
```

扩展套件分别使用 `site-pw-extension.json` 与 `model/pw-extension-v002`。
同一站点的任务套件串行执行，因为每项任务会恢复同一运行数据库。
结束后创建第一个终端配置的确切停止标记，让部署适配器清理其拥有的服务；
不要按进程名称停止机器上的全部 Python、Node 或 Chrome。
所有输出目录必须为新目录。模型修订使用新目录和 `diagnosis.json`，
并通过 `--baseline-summary` 关联父运行；禁止删除步骤、减弱检查或
将修改后的结果追溯计入首轮。重复运行和首次运行分别记录。

2026-10-20 的[真实通用浏览器验收](experiments/phase1-discogs-pw-20261020-1633/smoke-001/result.json)
已通过六项检查。这是执行通道验收，目标网站成绩以每轮独立报告为准。

## 复杂任务：独立评价与 Solar 实时介入

[监督接口版本 3](SUPERVISION_CONTRACT.md) 在原生脚本接口上增加
`h.checkpoint(id)` 和只保存公开计算证据的 `h.note(name, value)`。
模型声明关键动作前的关卡，独立评价先核验实际状态，然后浏览器暂停，
由独立 Solar 阅读公开 DOM、截图与计算记录并写入绑定哈希的决策。
批准后和动作派发前分别复验；拒绝、未知、超时、缺失或状态变化都会阻止动作。
脚本失败只允许诊断并停止，修订需要新的模型和运行编号。

本次[复杂任务协议](experiments/phase1-complex-pw-20261020-1815/PROTOCOL.md)
固定一个19步任务、两个实时关卡；[实际执行记录](experiments/phase1-complex-pw-20261020-1815/RESULTS.md)
保存19步通过、两次真实Solar介入及全部独立检查的证据。站点由独立部署适配器
`harness/sites/discogs/complex_deploy.py` 启动，完整原生执行命令为：

```powershell
$env:HARNESS_CHROME='C:\Users\29935\AppData\Local\Google\Chrome\Application\chrome.exe'
& '.\.runtime\phase1-discogs-pw-20261020-1633\venv\Scripts\python.exe' -m harness.playwright_run --site harness/sites/discogs/site-complex.json --model-dir harness/sites/discogs/model/pw-complex-v001 --protocol harness/experiments/phase1-complex-pw-20261020-1815/PROTOCOL.md --case-seconds 900 --out harness/runs/pw-complex-UNIQUE_ID
```

此命令在两个关卡等待真正的 Solar 决策，不能单独无人监督地完成。
协调者将 `interventions/NN-id/` 公开目录交给 Solar；私有评价放在另一个
`private-supervision/` 目录。决策格式、240秒期限和最多3次review预算见监督接口。
真实模型调用与通道测试必须区分：`python -m harness.supervision_smoke --out 新目录`
会使用明确标注的合成决策测试允许/拒绝两条浏览器路径，不是 Solar 或业务任务成绩。

## 历史：阶段一 MVP

本目录负责协议校验、预测监控、真实 UI 执行、独立终态评价、冻结与证据报告。网站适配器、固定任务集和模型规则由独立实验模型提供；通用基础设施不填充网站答案。模型调用通过本次会话的 Codex collaboration subagent 完成；文件交接本身不会调用模型，也没有模型 API 密钥。

本次交付状态与证据见 [MVP_STATUS.md](MVP_STATUS.md)。首个站点为已有完整前后端的 [Discogs 派生站点](sites/discogs/README.md)，网站规则与脚本由独立 `gpt-6.1-sol` subagent 生成。

从仓库根目录运行（Python 3.11+，核心只使用标准库；浏览器需要 [websocket-client](requirements.txt) 和 Chrome）：

```powershell
python -m pip install -r harness/requirements.txt
python -m harness.launch --site harness/sites/discogs/site.json --bundle harness/sites/discogs/model/v001/bundle.json --out harness/runs/discogs-v001-RUN_ID
```

`RUN_ID` 每次替换为新的标识；已有输出目录会被拒绝，不覆盖历史。`launch` 依次准备依赖、启动站点、执行通用浏览器验收、运行实验、清理自己启动的服务。准备失败或浏览器验收失败时不会开始业务实验。依赖准备耗时单列，不混入目标网站的执行耗时。准备已完成时可加 `--skip-setup`；默认启动独立 Chrome，也可用 `--cdp http://127.0.0.1:9337` 连接专用实验浏览器。若 Chrome 不在标准安装目录，设置 `HARNESS_CHROME` 为其可执行文件路径。

输出根目录保存 `launch.json`、`report.html`、输入哈希与启动日志；`preflight/` 保存环境验收；只有通过验收后才生成 `execution/` 下的目标网站轨迹与结果。不要把准备完成、端点可达或找到浏览器可执行文件视为浏览器实验成功。

独立使用各模块：

```powershell
python -m harness --help
python -m harness validate --site harness/sites/NAME/site.json --bundle PATH/bundle.json
python -m harness preflight --site harness/sites/NAME/site.json --bundle PATH/bundle.json --out harness/runs/UNIQUE_PREFLIGHT --launch-browser
python -m harness preflight --site harness/sites/NAME/site.json --bundle PATH/bundle.json --out harness/runs/UNIQUE_SMOKE --launch-browser --smoke
python -m harness run --site harness/sites/NAME/site.json --bundle PATH/bundle.json --out harness/runs/UNIQUE_RUN --launch-browser
python -m unittest discover -s harness/tests -v
```

`preflight` 默认只探测本地端点、依赖与 Chrome 路径，不导入评估器、不重置业务、不启动浏览器。显式 `--smoke` 才运行通用浏览器夹具，验证输入、点击、滚动、重复定位拒绝及浏览器上下文隔离。它仍不产生目标网站成绩。未验证或阻塞返回非零退出码；`run` 也只有全部任务通过、证据完整且版本可激活才返回零。

`site.json` 的 `cases` 可指定仓库相对路径；省略时读取同目录 `cases.json`。固定任务文件可以是任务数组或含 `cases` 数组的对象。每个任务固定 `id`、`goal` 和 `parameters`；模型不能改写任务目标、参数、顺序或删除任务。输入格式与适配器接口见 [CONTRACT.md](CONTRACT.md)。`source_roots` 必须指向不会写入业务数据的源码目录；运行数据库与缓存放在外部独立运行目录。启动器使用可信部署适配器的 `setup_argv` / `start_argv`，以 `shell=False` 执行，不执行模型 bundle 提供的系统命令。

每个任务先由可信适配器重置，再创建独立浏览器会话。每一步先将预测及检查项写入 `events.jsonl`、flush 并 fsync，然后才派发动作。浏览器负责确认、滚动和可见性，Runner 负责等待、回读和记录。每步保存 UI 与后端原始观察以及可用截图。缺失证据记为无法确认；无关的可选读数错误不会单独使有效检查失败。匹配拒绝分支是正常预测结果；最终业务成功仍由独立适配器 `evaluate` 判断。适配器只收到固定任务和真实观察，不收到模型预测。

运行目录必须不存在。`inputs/` 保存输入副本，`manifest.json` 保存输入、源码、评价器和 Harness 的 SHA256。执行后再次检查这些内容，变化使本轮无效。`summary.json` 和 `report.html` 保留全部任务与全部计划步骤分母；`feedback.json` 为独立模型提供失败分类及证据位置。`events.jsonl` 提供逐步时序。无模型 token/费用数据时记为 null，不估计账单。单轮最多 90 步、每个浏览器命令 30 秒，任务间和步骤间检查 20 分钟总预算。适配器在当前 Python 进程运行，须自行限制其后端请求超时；当前总预算不是对任意可信适配器的强制进程终止边界。

复用交接流程：

```powershell
python -m harness request --site harness/sites/NAME/site.json --out handoffs/UNIQUE_INITIAL
# 由独立 subagent 阅读 request.json，生成完整 bundle.json。
python -m harness accept --site harness/sites/NAME/site.json --bundle PATH/bundle.json --out handoffs/UNIQUE_ACCEPT.json
python -m harness request --site harness/sites/NAME/site.json --baseline-summary runs/INITIAL/summary.json --out handoffs/UNIQUE_REPAIR
# 独立 subagent 读取反馈，生成新版本 bundle.json 与 diagnosis.json。
python -m harness run --site harness/sites/NAME/site.json --bundle PATH/v002/bundle.json --diagnosis PATH/v002/diagnosis.json --baseline-summary runs/INITIAL/summary.json --out runs/UNIQUE_REPAIR --cdp http://127.0.0.1:9337
```

初始运行后最多两次修订。修订声明父版本、诊断分类、证据、改变的规则和步骤。禁止删除旧步骤、规则链接、预期分支或减少检查数；预测变化必须声明为有证据的业务反例。该检查防止结构上的静默改弱，不能自动证明自然语言或任意替换谓词的语义强度；因此必须继续依赖独立终点评估和实际回归，不能把结构校验当作语义等价证明。网站诊断与修订仍交由独立模型完成，协调者不补写网站答案。源码与评价器变化会拒绝对比。之前成功的任务再次失败会阻止激活。初始结果与适应结果保存在不同运行目录，绝不追溯改写。

MVP 的激活条件是全部固定任务通过独立终态评价、全部执行检查匹配且输入完整性检查通过；修订还必须没有任务或步骤回归。全部阻塞或全部失败不会因为“没有回归”而获得激活。基础设施失败保留 `infrastructure` 分类，首次实际动作前的异常标记为 `blocked`；反馈交给基础设施维护方，不能据此修改网站业务规则。反馈只引用已经落盘的文件，重置失败时至少有错误记录与 JSONL 事件证据。等待条件由独立模型指定，Runner 不会重复读取直到预测通过。

`measurement_status` 结合 UI 动作派发与完成数区分 `not_started`、`partial`、`completed`。没有派发任何 UI 动作时，报告明确显示“未开始目标网站测量”，`case_success_rate` 与 `step_match_rate` 为 null；仍保留全部固定任务、步骤与阻塞记录。已经派发但未全部完成记为 `partial`：即使响应丢失，也不能假定动作没有改变状态。`pipeline_completion_rate` 仅表示已完成 UI 动作数除以计划步骤数，不能当作模型任务成功率。部分完成的测量仍保留固定分母，不删除未执行项。

当前属于阶段一通用基础设施与小规模白盒实验入口，不代表阶段二强制隔离、完整官方基准复现、三阶段实验完成或严格速度对照。独立 subagent 上下文也不是操作系统隔离。文件冻结提供变化检测，不是不可篡改存储。

首版采用通用 CDP 适配器实现浏览器执行；安装的 agent-browser 守护进程在本会话未能就绪，因此未用于实际站点执行。浏览器适配器只接受固定 UI 动作与读数，不接受模型提供的任意 JavaScript。通用单元测试使用假浏览器，不能作为真实 UI 验收证据；当前 Chrome 实测失败及后端组件验证的详细边界见交付状态。
