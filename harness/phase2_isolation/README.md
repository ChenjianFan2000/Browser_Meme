# 阶段二通用隔离组件

这些组件不包含网站规则、选择器或任务脚本。审计结果见 [AUDIT.md](../experiments/phase2-discogs-20261021-01/isolation/AUDIT.md)。

- `unix_gateway.make_gateway(socket_path, public_origin, upstream_host, upstream_port)`：在可信宿主启动 HTTP Unix gateway；调用返回 server 的 `serve_forever()`，结束时 `shutdown()`、`server_close()` 并删除 socket。只允许配置的单一 HTTP origin，连接固定 upstream，不解析请求来选择 backend，不允许 CONNECT。
- `unix_bridge.playwright_proxy(socket_path)`：在工具 namespace 内使用上下文管理器，得到原生 Playwright `launch(proxy=...)` 的配置；bridge 只转送字节到唯一文件可见的 socket，不提供网站业务动作。
- `linux_network_probe.py`：从 WSL 的系统 Python stdin 执行，使用下载到 `/opt/browser-meme/tmp/phase2-isolation-audit` 的精确 Codex0.163.0及既有 core Playwright1.44/Chromium1117，进行通用浏览器、网络与文件隔离验收。
- `solar_tools_probe.py`：可信侧工具探针 runner。需要事先用私密字节管道将现有 ChatGPT auth 放进独立 `solar-probe-home/auth.json`，目录0700、文件0600；不会归档此文件。脚本会调用精确 gpt-6.1-sol，不能作为普通文档检查运行。
- `mxc_canary.py`：Windows无模型探针；证明MXC文件拒绝有效，以及MXC online具有宿主loopback例外。浏览器正向在MXC内超时，不能替代Linux已通过证据。

## 可信侧启动与工具侧调用

可信侧使用 `make_gateway('/private-runtime/site.sock', 'http://site.example:12042', 'fixed-host-ip', 12042)`，在独立线程运行返回的 server。只向工具namespace映射这个socket。上游IP由管理侧固定；不能取自模型输入。

工具侧直接使用 Playwright：

```python
from playwright.sync_api import sync_playwright
from unix_bridge import playwright_proxy

with playwright_proxy('/private-runtime/site.sock') as proxy:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, chromium_sandbox=True, proxy=proxy)
        # 模型自己的原生 Playwright 脚本在这里运行。
        browser.close()
```

## 权限配置

实际逐项路径及完整argv见 `linux-playwright-reusable-relay.json`。原则配置如下；不使用glob匹配秘密文件，默认不映射其他路径。

```toml
default_permissions = "p2"
approval_policy = "never"
web_search = "disabled"
project_doc_max_bytes = 0

[features]
network_proxy = true
skip_host_skill_discovery = true
apps = false
plugins = false
multi_agent = false
hooks = false
browser_use = false
computer_use = false
image_generation = false
skill_search = false
skill_mcp_dependency_install = false

[permissions.p2.filesystem]
":root" = "deny"
":minimal" = "read"
":workspace_roots" = "write"
"/exact/path/to/codex" = "read"
"/exact/path/to/site.sock" = "read"
"/opt/browser-meme/envs/core" = "read"
"/opt/browser-meme/browsers/chromium-1117" = "read"

[permissions.p2.network]
enabled = true
allow_local_binding = true
dangerously_allow_all_unix_sockets = true
domains = {}

[permissions.p2.network.unix_sockets]
"/exact/path/to/site.sock" = "allow"
```

`dangerously_allow_all_unix_sockets` 是实测必需的 syscall 设置，不能隐去；实际宿主socket可见性仍由默认拒绝的filesystem namespace控制，host abstract sockets由network namespace隔离。禁止映射宿主 `/run`、`/tmp`、Docker socket、秘密目录或用户home。不要把运行依赖的父目录开放读权限。

正式CLI使用独立进程真实专用 `CODEX_HOME`（只含必要auth，工具namespace不可见），执行 `codex exec --ignore-user-config --ignore-rules --ephemeral --strict-config --skip-git-repo-check -m gpt-6.1-sol -C /isolated/workspace --json`，再用 `-c` 传入以上配置；`--ignore-user-config`意味着配置必须显式通过CLI覆盖传入。不要用 `sandbox -P` 替代实际exec验收。模型传输发生在可信CLI侧，不向工具放通模型API网络。

Windows传给 `wsl` 的带引号嵌套参数会重解析，审计runner采用 `subprocess.run(['wsl', '-d', 'BrowserMeme-Ubuntu', '--', 'python3', '-'], input=script_bytes, ...)`。使用bytes避免Windows换成CRLF。不要把auth、令牌或通用运行日志复制进模型workspace。
