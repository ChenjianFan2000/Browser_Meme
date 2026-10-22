# 阶段二隔离基础设施审计

日期：2026-10-21。审计者只读取通用配置、CLI 文档及通用探针，没有读取网站源码、规则书或私有测试。没有启动模型学习，没有读取或复制凭据，没有修改全局配置或宿主权限。

## 已测结论

- 本机 Codex CLI 0.163.0 默认 Windows elevated 后端拒绝 `:root=deny`：`elevated Windows sandbox requires effective :root read access`。
- 显式 `windows.sandbox=mxc` 可运行默认拒绝读取的进程沙箱，无需提权。绝对路径、大小写变体和 `../` 指向 workspace 外的通用 canary 都无法读取；workspace 内 canary 可读。仓库根 AGENTS.md 无法读取。
- MXC 内不能看到本轮单独启动的宿主 canary PID。这是有限探针，不能外推为对所有进程攻击面的完整证明。
- `network.enabled=false` 时，通用宿主 loopback TCP canary 与外部 TCP 均被拒。
- **打开 MXC managed network 后，未列入域名 allowlist 的宿主 loopback TCP canary 仍可直连。** 测试仅 allow `example.com`、启用 network proxy 和 MXC 要求的 `allow_local_binding=true`，直接 TcpClient 连接随机本机端口成功。因此该方案不能满足只准站点/CDP 端口的完整网络隔离。
- `codex sandbox -C ...` 中 PowerShell 位置显示 H:\，相对路径探针失败；绝对路径探针有效。调用脚本应使用绝对路径并显式切换目录。

## 命令及证据

从仓库根运行：`python harness/phase2_isolation/mxc_canary.py`。无模型请求。所有实际 argv 保存在 JSON，避免 PowerShell native 引号丢失。独立域名及路径表通过完整 TOML inline table 传入，不用带引号的 dotted path。

- `mxc-access-probe-offline.json`：允许读、拒绝读、进程及离线网络探针。
- `mxc-access-probe-managed-network.json`：loopback 绕过域名代理限制的反例。
- `mxc-browser-probe.json`：通用 Playwright 正向探针的最后结果；必须检查 `timeout` 和退出码，不能仅凭脚本已生成记为成功。
- `.runtime/phase2-isolation-audit/schema/`：本地 CLI 生成的 experimental app-server schema，不含网站数据。

## 可用接口与尚未验收的边界

本地 schema 的 ThreadStartParams 确认 `model`、`permissions`（命名配置，不与 sandbox 混用）、`runtimeWorkspaceRoots`、`environments=[]`、`ephemeral`。`exec --help` 确认 `--ignore-user-config --ignore-rules --ephemeral --strict-config`。这些字段存在不等于完整工具隔离已经验收。

当前 collaboration.spawn_agent 接口不能设置独立权限或禁用宿主工具；独立上下文不能作为 OS 隔离。命令沙箱只约束命令及子进程；附加 MCP、插件、浏览器内建工具和服务通信需要分别禁用或隔离。尚未进行正式精确 `gpt-6.1-sol` 的工具清单、自动指令来源、非 exec 读取与技能发现验收。不得将这些事项记成通过。

建议将模型推理和工具执行分开：宿主专用 CLI/app-server 实例只保留模型传输，清空配置/历史/插件继承；所有模型可调用执行工具使用默认拒绝的沙箱，并对浏览器工作进程实施真正的目的地址和端口边界。MXC offline 可作为本地执行隔离组件；MXC online 不能单独作为完整方案。WSL/Linux bubblewrap 或容器网络命名空间方案仍需正负验收，不能沿用有 docker 组权限的普通 research shell 就宣称隔离。

## WSL 后续实测：可执行拓扑

精确下载 Linux Codex 0.163.0（见 `linux-cli-download.json`），CLI 自带 Linux sandbox 所需运行组件，无须另装 bwrap。Linux 普通宿主 CLI 负责模型服务通信与认证；模型调用的命令、view_image、apply_patch 经其文件及进程 namespace。工具网络不放通任何域名，通过唯一可见的 Unix socket 访问可信固定 origin relay。sandbox 内临时 TCP→Unix bridge 给原生 Playwright 使用。网关不向浏览器暴露 API 动作集合。

`linux-playwright-reusable-relay.json` 已对可复用的 `unix_gateway.py`、`unix_bridge.py` 实测：原生 Playwright1.44.0 + chromium1117、`chromium_sandbox=True`，访问通用 HTTP fixture、click、回读、截图成功。外文件、docker.sock、宿主其他 filesystem Unix socket均不可见；宿主 abstract Unix socket及宿主 TCP 拒绝；外部直连失败；同一 host 的未准入端口返回403。截图为 `generic-browser.png`。

重要配置边界：CLI 的精确 Unix socket allowlist 本身不能让 Python 创建 AF_UNIX socket（EPERM）；`network.enabled=false` 连 namespace 内 TCP bridge 也不能创建。已验证方案使用 `network.enabled=true`、`features.network_proxy=true`、`domains={}`、`dangerously_allow_all_unix_sockets=true`，同时 filesystem `:root=deny`，只映射 gateway.sock、必要运行依赖和模型 workspace。该开关允许 namespace 内 Unix socket syscall；宿主可见 socket 由文件映射限制，abstract socket 由网络 namespace 限制。不能隐去这个开关或把其名称替代具体边界审计。

`linux-managed-port-filter.json` 保留了失败方案：仅父CLI HTTP_PROXY指向可信端口过滤上游，Codex的本地请求仍可绕过该上游，两个端口均可达。最终 Unix gateway 方案不依赖这一路径。

真正 Solar 工具验收记录在 `solar-tools-probe*.json*`，属于额外诊断调用，不是正式学习者。第一次执行成功，workspace command read / apply_patch 可用；外canary command read、view_image 和 apply_patch 均因namespace不可见失败，管理侧确认protected内容未改。第一轮 PNG 正向样本本身无效，因此另编号补测，不追溯修改第一轮结果。

第二轮有效PNG正向 `view_image` 成功；外PNG读取仍失败；MCP resources/templates实际均为空，`collaboration.list_agents`只见当前 `/root`。第三轮按指令尝试一次独立精确Solar子agent；主probe报告child允许读成功、外canary不可见。CLI JSON只记录collab wait及主模型转述，未单独输出spawn请求和child原始轨迹，因此不把child权限继承记录为与直接exec/图像/patch同等强度的独立证据。第三轮收到environment instructions及skill catalog，自述无项目instructions或技能内容自动加载；catalog的存在应记录，不能说所有工具或技能名称已彻底移除。

三轮CLI回传真实usage分别为：001 input34932/cached20608/output628；002 input47648/cached41472/output688；003 input33906/cached31232/output314。`solar-diagnostic-usage.json`保留原始字段，无费用推算；这些额外诊断不计入正式学习组。

最终 `linux-playwright-relay-negative.json` 补测同一namespace内经真实bridge发送CONNECT、Host不匹配、URL credentials、IPv6替换、chunked framing，均403；有效页面仍完成Playwright click/回读/截图。异常请求主动断开时通用探针的内联bridge产生一个ConnectionResetError日志，未影响退出码0及拒绝结果。

清理：各通用HTTP/Unix server在probe结束shutdown，测试socket unlink；Docker使用 `--rm`；Windows通用宿主canary进程在finally终止，第一次MXC浏览器超时后仅清理已确认的browser_probe进程13888/30868，第二次runner以本次Codex子PID执行taskkill /T清理。没有终止现有网站或宿主agent进程。专用Solar auth留在WSL独立0700 home下、文件0600，不在本归档；删除或转移该临时认证材料由可信管理侧处理。

## 官方依据

- [Permissions](https://developers.openai.com/codex/permissions)：命名权限配置、默认拒绝、命令与 MCP 等不同访问面的范围。
- [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)：MXC 无管理员配置，loopback 例外、子进程与精确版本兼容限制。
- [App Server](https://developers.openai.com/codex/app-server)：新 thread、命名 permissions、instructionSources。
- [Configuration Reference](https://developers.openai.com/codex/config-reference)：Windows 后端选择与禁用 web_search。
