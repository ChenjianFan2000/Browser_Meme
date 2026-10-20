# 部署状态

更新：2026-10-15（北京时间）。用户运行国内镜像入口后，三套运行环境已全部安装并通过检查；站点镜像尚未下载。新环境、下载、缓存、日志与 WSL 虚拟磁盘均放在 G 盘；沿用原有 C 盘 WSL 主程序，未安装 Docker Desktop。

## 已完成

| 项目 | 结果 |
| --- | --- |
| 基础系统 | Ubuntu 24.04.4、Python 3.12.3，发行版 BrowserMeme-Ubuntu |
| Docker | Engine 29.9.0、Compose 5.6.0、Buildx 0.38.0；离线只读容器检查通过 |
| 工具 | Git / Git LFS、编译工具、字体、浏览器动态库；uv 0.13.1、pip 25.2、build、gdown |
| core | 148 个依赖已安装；依赖检查、WorkArena 导入、Chromium 125 本地点击测试通过 |
| agentlab | 241 个依赖已安装；AgentLab 0.4.2、CPU PyTorch 2.8.0；依赖检查与 Chromium 点击测试通过 |
| webchore | 依赖检查通过；BrowserGym 0.13.3、Playwright 1.50.0、Chromium 133 本地点击测试通过；已注册 538 个任务 |
| 公共资源 | CPU PyTorch wheel、NLTK punkt / punkt_tab、Playwright 1.44 Chromium 已下载 |
| WebChoreArena 源码 | 固定提交 542abc538fd9558362119714989166904d82f5f4；四个本地 BrowserGym wheel 已构建并校验 |
| 恢复机制 | 实时日志、阶段完成记录、哈希校验复用、HTTP / Google Drive 续传、超时重试、Windows 原盘检测与 WSL 恢复 |

安装证据：`.runtime/logs/smoke-core.json`、`smoke-agentlab.json`、`smoke-webchore.json` 和 `*-installed.txt`。完整安装日志：`.runtime/logs/20261015-164808-install.log`，最后一套检查于 16:50:30 通过。恢复逻辑通过回环 HTTP 故障注入及 Windows 进程监控测试；未通过拔掉运行中的 SSD 验证。

## 镜像导入报错排查

16:52:17 的 `.runtime/logs/20261015-165217-install.log` 显示错误来自 `load_images()`：五个镜像归档均缺失或未经校验。排查时 `.runtime/downloads/images` 尚不存在，也没有本次站点镜像下载日志。这条报错发生在离线导入阶段，不能据此判断下载源或网络故障。

应先运行 [Download-Images-CN.cmd](Download-Images-CN.cmd)，等下载成功后再运行 [Install-Images.cmd](Install-Images.cmd)。[Complete-Runtimes-CN.cmd](Complete-Runtimes-CN.cmd) 仅安装三套运行环境，本机已完成。具体入口与来源见 [国内镜像运行说明](国内镜像运行说明.md)。

已明确两个镜像入口的执行顺序；导入前先校验全部归档，缺少文件时给出下载入口提示并停止。镜像准备步骤 `research.ps1 -Action prepare -Profile images -Mirror cn` 已成功执行；本次排查未启动大镜像传输。

验证：19 项本地恢复与归档测试通过，包含“缺少任意归档时不执行 Docker 导入”及“全部校验通过后可导入”。实际导入入口在当前缺文件状态下按预期退出并提示先下载，日志见 `.runtime/logs/20261015-170009-install.log`。

## 大镜像留待下载

2026-10-15 用官方 Google Drive 的单字节 Range 响应确认：shopping 67.58 GB、shopping-admin 9.64 GB、reddit / postmill 53.44 GB、冻结 GitLab 77.76 GB，四个归档合计 208.41 GB。独立 GitLab CE 压缩层另约 1.45 GB；站点镜像合计约 **209.86 GB**，解包与运行数据另占空间。GB 按十进制计算。

精确字节数与响应头：`.runtime/logs/download-remote-sizes.json`。本次没有启动这些大镜像下载。需要时单独运行 [Download-Images-CN.cmd](Download-Images-CN.cmd)，成功后运行 [Install-Images.cmd](Install-Images.cmd)。其中四个 WebArena 归档仍需使用上游 Google Drive；没有已验证的国内替代源。

WorkArena / WorkArena++ 仍待 Hugging Face 实例授权，申请步骤见 [README](README.md)。未运行真实 ServiceNow 任务、自托管站点实验或付费模型调用。

## 磁盘观察

初次检查停滞时没有发现新的 G 盘设备移除，后台正在下载 NLTK，旧窗口仍显示较早的浏览器进度。后续 **15:53:26** 出现一次 UASPStor 129 通道重置和两条 Disk 153 I/O 重试；随后恢复读写，未见对应的新 USB 设备移除。记录见 `.runtime/logs/download-storage-events-20261015.json`，不能排除存储链路仍不稳定。脚本恢复不等于修复硬件原因。

Windows 自身及已有软件仍可能写入 C 盘；本次新增环境数据均安排在 G 盘。不要在 WSL 运行时拔盘。
