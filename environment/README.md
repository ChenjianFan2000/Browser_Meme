# 研究环境部署与下载

本目录服务于 [研究目标](../研究目标.md) 的三层实验：WorkArena L1、可控 GitLab UI/API 对照，以及 WorkArena++ / WebChoreArena 组合任务。环境准备不代表已经完成实验或获得基准成绩。

当前安装结果、已通过检查与待办见 [部署状态](STATUS.md)。三套 Python 环境已生成锁文件；下载脚本支持校验缓存、重试与恢复。

## 存储位置

- 发行版：`BrowserMeme-Ubuntu`，Ubuntu 24.04、Python 3.12。
- Linux 虚拟磁盘：`G:\Browser_Meme\.runtime\wsl\Ubuntu-24.04\ext4.vhdx`。
- WSL 交换文件：`G:\Browser_Meme\.runtime\wsl\swap.vhdx`，最大 4 GB。
- 下载包：`G:\Browser_Meme\.runtime\downloads`；日志：`.runtime\logs`。
- Linux 中的虚拟环境、缓存、浏览器、源码及凭据：`/opt/browser-meme`，物理位置均在上述 G 盘虚拟磁盘内。Docker 镜像、容器与卷位于同一磁盘内的 `/var/lib/docker`、`/var/lib/containerd`。

沿用原有 `C:\Program Files\WSL` 中的 WSL 主程序；没有重新安装 Docker Desktop。Windows 必须从用户目录读取 `.wslconfig`，因此 C 盘保留这个很小的配置文件。脚本将新环境及下载的主要存储放在 G 盘，但无法保证 Windows 自身的日志、更新或分页完全不写 C 盘。不要在运行中移动、删除 VHDX 文件。

## 环境划分

| 环境 | 作用 | 固定的主要版本 |
| --- | --- | --- |
| `core` | 浏览器交互、WorkArena L1 / ++、GitLab API、分析与 Jupyter | BrowserGym core 0.14.3、WorkArena 0.5.3、Playwright 1.44.0 |
| `agentlab` | 通用 Agent 对照基线 | AgentLab 0.4.2、BrowserGym 0.14.3、CPU PyTorch 2.8.0 |
| `webchore` | WebChoreArena 扩展实验 | 上游提交 `542abc538fd9558362119714989166904d82f5f4` 的 BrowserGym 分支、Playwright 1.50.0、CPU PyTorch 2.8.0 |
| `images` | 自托管实验站点 | GitLab CE 19.3.5；WebArena 上游四个冻结站点镜像 |

WebChoreArena 的 BrowserGym 分支与主线分别安装。两套 Chromium 共存，禁用 Playwright 自动清理旧版本。CPU PyTorch 用于框架依赖；当前研究尚未指定本地模型，因此未安装 CUDA、GPU 训练框架或下载模型权重。

基础系统已安装 Docker Engine、Compose、Buildx、Git/Git LFS、Python、编译工具、中文字体和浏览器动态库。2026-10-15 已通过 Docker 离线容器运行检查，三套锁文件分别包含 148、241、137 个依赖。精确安装结果以 `.runtime/logs` 中的版本清单、检查日志及 `smoke-*.json` 为准；空虚拟环境不计为安装完成。

## 换网络后下载与安装

**三套运行环境已安装并通过检查，站点镜像仍待下载。** 先阅读 [国内镜像运行说明](国内镜像运行说明.md)，按需要选择入口：

| 入口 | 执行内容 |
| --- | --- |
| [Complete-Runtimes-CN.cmd](Complete-Runtimes-CN.cmd) | 国内镜像优先，补齐并安装三套运行环境；不包含大站点镜像 |
| [Download-Images-CN.cmd](Download-Images-CN.cmd) | 单独下载约 210 GB 的站点镜像 |
| [Install-Images.cmd](Install-Images.cmd) | 离线导入已经下载的站点镜像 |

首次安装运行环境时，先双击 `Complete-Runtimes-CN.cmd`；本机已经完成，无需为下载镜像重跑。站点镜像按 `Download-Images-CN.cmd` → 下载成功 → `Install-Images.cmd` 的顺序执行。若导入提示缺少镜像文件，先完成下载。运行环境安装的等效 PowerShell 命令：

```powershell
Set-Location G:\Browser_Meme
powershell -NoProfile -ExecutionPolicy Bypass -File .\environment\Complete-Runtimes.ps1 -Mirror cn
```

如只下载或分批操作，可使用 `research.ps1` 的 `core`、`agentlab`、`webchore`、`runtimes` 或 `images` 范围。`runtimes` 包含三套 Python 环境、浏览器和分词资源：

```powershell
.\environment\research.ps1 -Action download -Profile runtimes -Mirror cn
.\environment\research.ps1 -Action install -Profile runtimes
# 大镜像单独下载：
.\environment\Download-Images-CN.cmd
```

`Complete-Runtimes.ps1` 默认使用 `cn` 国内优先模式；可显式传 `-Mirror official` 使用官方源。旧入口 `Download-All.cmd` 包含三套运行环境和全部约 210 GB 的站点镜像，成功后用 `Install-All.cmd` 离线安装；它不是只补齐运行环境的入口。

国内优先源包括清华 PyPI、上海交大 CPU PyTorch、npmmirror Playwright 和 DaoCloud 公共镜像。失败后尝试官方来源，可用 `-Mirror official` 直接使用官方源。Ubuntu / Docker 安装脚本也支持中科大镜像。镜像速度取决于新网络，不能保证所有资源均能从国内获取。

**WebArena 四个带数据的站点镜像没有已验证的国内替代源**，使用上游公布的 Google Drive 链接；其 Internet Archive 条目在核查时不可公开获取。2026-10-15 以单字节 Range 请求读取官方响应的总长度，结果如下（GB = 10⁹ 字节，完整响应头记录于 `.runtime/logs/download-remote-sizes.json`）：

| 站点归档 | 下载量 |
| --- | ---: |
| shopping | 67.58 GB |
| shopping-admin | 9.64 GB |
| reddit / postmill | 53.44 GB |
| 冻结 GitLab | 77.76 GB |
| 四个归档合计 | 208.41 GB |

独立 GitLab CE 另需约 1.45 GB 压缩层；站点镜像合计约 209.86 GB。Docker 解包和运行数据还会占用额外空间。来源可用性、配额及网络限制可能导致下载失败。

`prepare` 成功后生成 `requirements/*.lock`，固定当次解析的依赖及哈希；失败时不要把输入清单当作完整锁文件。下载阶段构建 wheel，生成 `requirements.offline.txt` 和 `SHA256SUMS`；安装阶段使用 `--no-index --require-hashes`。Ubuntu、源码与 CPU PyTorch 使用固定 SHA256；独立 GitLab 使用固定仓库摘要。四个旧站点归档没有上游 SHA256，下载后验证 Docker 归档结构并记录本地哈希，仅用于后续完整性检查。

本机已完成三套 `prepare`。重复执行会复用现有锁文件和已构建的 WebChoreArena wheel，不重新解析版本。2026-10-15 不同时段观察到国内源 TLS 失败及官方 PyPI 超时、慢速；这些是当时网络的观测，不代表换网络后的速度。

## 断线恢复与进度

- 窗口与 `.runtime/logs/*-download-recovery.log` 实时输出；运行中每 15 秒显示状态，`download-state.json` 记录当前阶段。心跳只说明监控仍在工作，字节增长才表示文件传输在前进。
- 完整文件先校验 SHA256；wheel 阶段保存完成记录并跨环境复用匹配锁文件的包。部分 HTTP / Google Drive 文件保留续传数据，完成且校验通过后才发布最终文件。旧脚本留下的残缺归档不会被当作完成。
- 单文件默认最多 6 次尝试，连接超时 10 秒，连续低速 60 秒后重试；一般阶段最多 3 次、无进度 300 秒重试。PyPI 使用 pip 的断点重试；Docker 复用已完成镜像层；Playwright 复用已完成浏览器，但中断的单个组件可能重新下载。
- Windows 监控在内存中运行。G 盘失联后等待原盘最多 10 分钟，确认盘标识且连续检测通过，再恢复本项目发行版；WSL 连续 5 分钟无输出也触发恢复。整个下载会话默认最多 6 次，不无限卡住，不重置发行版数据。
- 可在 PowerShell 中设置 `$env:BM_HOST_RETRIES='8'`、`$env:BM_DRIVE_WAIT_SECONDS='1200'` 调整 Windows 恢复上限。Linux 的 `BM_DOWNLOAD_ATTEMPTS`、`BM_STAGE_ATTEMPTS`、`BM_STALL_TIMEOUT` 可在 Linux 调用前设置。`Ctrl+C` 或关闭后重新执行同一下载命令即可继续；若报告已有任务，先检查原窗口，避免并行下载。

超出重试上限会明确失败并保留下载；校验不通过的数据移为 `.rejected-*` 以供检查，不作为安装输入。空间不足、文件系统损坏或持续硬件故障需要先处理原因，脚本不会格式化、重建虚拟磁盘或运行自动修盘。

恢复测试使用回环 HTTP 模拟断流、Range 不支持、404、损坏数据和无响应进程，并验证 Windows 掉盘探针与实际 WSL 启动；没有通过拔掉运行中的 SSD 测试。运行方法：

```powershell
wsl -d BrowserMeme-Ubuntu -u research --exec /opt/browser-meme/envs/tools/bin/python -B /mnt/g/Browser_Meme/environment/tests/test_download_recovery.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\environment\tests\test_download_supervisor.ps1
```

## 日常使用

```powershell
.\environment\research.ps1 -Action shell
```

进入 WSL 后激活所需环境：

```bash
source /mnt/g/Browser_Meme/environment/activate.sh core
python -m pip check
jupyter lab --ip=127.0.0.1 --no-browser
# 切换环境前可先 deactivate，再 source .../activate.sh agentlab 或 webchore
```

`webchore` 激活脚本自动切换到固定源码目录，因为其上游配置按当前目录读取。API 密钥和 Hugging Face token 只在本机 `/opt/browser-meme/secrets/research.env` 填写，参考 [config.example.env](config.example.env)；该文件权限为 `600`，不放进仓库或下载归档。尚未执行任何付费模型调用。

## 启动本地站点

完成 `images` 下载、安装后：

```powershell
.\environment\research.ps1 -Action gitlab-start
# 访问 http://localhost:8929；结束时：
.\environment\research.ps1 -Action gitlab-stop

.\environment\research.ps1 -Action webchore-start
# 结束时：
.\environment\research.ps1 -Action webchore-stop
```

独立 GitLab 首次启动可能需要数分钟，`root` 的随机初始密码保存在 Linux 的 `/opt/browser-meme/secrets/gitlab_root_password`。它是速度对照的候选环境，业务状态重置、UI/API 等价性和具体实验任务仍需另行设计。

WebChoreArena 的 shopping、shopping-admin、reddit、GitLab 分别使用 `7770`、`7780`、`9999`、`8023` 端口，首页使用 `4399`。这些冻结镜像保留上游测试账号与数据，只绑定本机回环地址。未部署四站任务不使用的地图、Wikipedia 或计算器；配置文件中地图与 Wikipedia 地址仅用于满足上游接口要求。停止站点保留数据，脚本不会自动重置实验状态。

本地首页是仅含四站导航及公开测试账号的静态适配版，替代需要 Flask 渲染的上游模板；账号依据[上游配置](https://github.com/web-arena-x/webarena/blob/dce04686a56253aefba7b18a4fa0937cf1dc987b/browser_env/env_config.py)。记录实验设置时应声明此适配。站点成功启动后，启动器会保留一个隐藏的 WSL 客户端；两组容器停止后自动退出。这是因为 [systemd 服务本身不会保持 WSL 运行](https://learn.microsoft.com/windows/wsl/systemd#how-does-enabling-systemd-affect-wsl-architecture)。

本机约 24 GB 内存，WSL 上限 10 GB、交换空间 4 GB。两组站点禁止同时启动；WebChoreArena 四站仍可能因 GitLab 初始化而使用交换空间，不应把这种资源限制混入严格速度对照。

## 申请 WorkArena / WorkArena++ 权限

1. 登录 Hugging Face，打开 [ServiceNow/WorkArena-Instances](https://huggingface.co/datasets/ServiceNow/WorkArena-Instances)。
2. 按页面要求填写申请、接受条款并等待批准。现在没有授权，不能运行真实 ServiceNow 任务。
3. 获批后，在 Hugging Face 的 token 设置中创建能读取该受限仓库的 token，仅在本机 `research.env` 填入 `HF_TOKEN`。激活 `core` 或 `agentlab` 后使用。保留官方 `HF_ENDPOINT`，凭据不经第三方镜像。
4. 按 [WorkArena 官方入门说明](https://github.com/ServiceNow/WorkArena#getting-started) 使用实例池；旧的 `SNOW_INSTANCE_URL` 等配置应按上游要求取消。WorkArena++ 与 L1 在同一 Python 包中。

本次检查不申请或占用远程实例，不运行 oracle、不重置 ServiceNow 数据。正式实验须记录任务划分、随机种子、资源预算、版本与命令，并隔离学习输入、测试答案和评测器内部数据。

## 重建与排查

当前机器无需重复安装 WSL。重新准备专用发行版时，依次执行 `Setup-Wsl.ps1`、`research.ps1 -Action bootstrap`、`research.ps1 -Action prepare -Profile all`，再下载和安装。`prepare` 只创建缺失锁文件；升级依赖应另行生成、审阅并验证，不直接覆盖现有实验锁。

`doctor` 检查 Docker、磁盘、Compose 配置和已安装 Python 环境；浏览器检查使用本地 HTML 按钮，不访问基准站点或模型服务。未下载内容会明确标为待完成。本机 WSL 使用 NAT，关闭了 WSL 的自动代理导入，Windows 原有代理保持原设置；下载需要 WSL 能直接联网。`research.ps1` 在 Linux 启动后手动挂载 G 盘，C 盘不自动挂载。

2026-10-14 的 G 盘只读检查曾测得 474～1371 ms 的无缓存 4 KB 读取；10 月 15 日复测为 0.21～0.50 ms，记录保存在 `.runtime/logs/windows-storage-read*.json`。但当天 12:04、12:06 又出现 Windows 磁盘 I/O 错误与 G 盘重连，不能仅凭短测判定连接已经稳定。调整硬盘接口前，应保存工作、正常关闭 WSL，并确认虚拟磁盘已经释放。

可运行 `research.ps1 -Action verify-base` 检查脚本语法、Compose 配置与离线 Docker 容器；在 Linux 内运行 `python3 /mnt/g/Browser_Meme/environment/scripts/check_plan.py` 可检查依赖锁和四个本地 wheel 哈希。后者不需要联网，也不代表应用已经安装。

如 WSL 服务完全无响应，先关闭实验任务，再在管理员 PowerShell 中运行 [Restart-Wsl-Service.ps1](Restart-Wsl-Service.ps1)。[Restart-Wsl-Compute.ps1](Restart-Wsl-Compute.ps1) 还会重启计算与容器网络服务，只在同机其他虚拟机、容器任务均已结束后使用。不要将这些恢复脚本作为每次下载的常规步骤。

相关安装依据：[Microsoft WSL 配置](https://learn.microsoft.com/windows/wsl/wsl-config)、[Docker Ubuntu 安装](https://docs.docker.com/engine/install/ubuntu/)、[WebChoreArena](https://github.com/WebChoreArena/WebChoreArena)、[WebArena 镜像来源](https://github.com/web-arena-x/webarena/blob/dce04686a56253aefba7b18a4fa0937cf1dc987b/environment_docker/README.md)。
