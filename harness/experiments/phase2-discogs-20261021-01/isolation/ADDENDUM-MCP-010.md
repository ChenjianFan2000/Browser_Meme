# 可信浏览器MCP准入验收

日期：2026-10-21。所有页面、按钮、凭据及cookie均为独立通用fixture；未读取目标网站源码、规则或评测材料。正式学习未由本审计启动。

最终机器gate为 `learning-browser-mcp-acceptance.json`，由 `harness/phase2_isolation/finalize_learning_gate.py` 对原始事件逐条断言后创建。关键源码hash必须与gate相同；修改代码后不能沿用。该gate只覆盖learning browser MCP，未来evaluation broker需另验。

## 实际修复及回归

- 006证明 `str.format` 字段能绕AST属性检查并读取假cookie的storageState。删除format白名单；format_map原本不在白名单。010真实MCP对该反例返回属性format拒绝。
- screenshot mask扩展到与DOM一致的password/token/secret输入；运行时只在私有内存采集这些值，用于AX、DOM、日志、console、返回值、network输出脱敏。007及010均有真实Chrome截图，输入字段以magenta遮罩；导出文本没有假token或JS正文marker。
- Page.type、Locator.type、Page.set_checked补入动作包装。009三次真实浏览器回归都在未提供第二次expect时拒绝，保留仅goto的action_count=1。
- 首次006遇到state单文件write映射被bwrap当root导致Not a directory，由主Agent改为独立state目录write。007后通过。

## 真正Solar MCP证据

010精确gpt-6.1-sol独立CLI自己创建原生Playwright脚本，经MCP执行goto、get_by_role click、observe、inner_text回读；服务端原始结果completed、exit0、actions2、return_value=Clicked。原始rollout含view_image实际input_image返回，管理侧亦目检截图。

010实际MCP拒绝workspace父路径、os/socket导入、evaluate、request、format反射；javascript导航在独立worker中返回BoundaryError且actions0。CLI直接TCP/Unix socket操作真实得到EPERM。learner CLI只映射workspace/minimal/codex，无site socket、core或browser；唯一MCP服务在可信侧启动独立namespace浏览器执行器。

008与009的MCP调用均被CLIapproval never阻止，不能算浏览器policy拒绝；完整保留。两工具配置 `approval_mode=auto`仍会触发此阻止。010使用明确的 `approval_mode=approve`，与官方MCP示例一致，且只对execute_script/status预授权，不改变OS权限。

010模型final表过度声称文件检查完成：实际合并命令因python不存在失败，重试只执行网络及脚本写入。审核者以原始事件发现，未采用该自述；011新的极短Solar probe用明确 `/usr/bin/python3` 实际检查private canary/config、site.sock、runtime源码四路径openable=false，host secret只做os.access=false、从未打开。gate引用011原始command输出。

## 自动上下文与范围

005及010 raw rollout确认无项目文档或技能指令注入，agents已禁，apps/plugins禁用；唯一允许MCP是所测试的phase2_browser。正式专用home仍须auth-only；project_doc_max_bytes=0不会禁home AGENTS。诊断home、rollout及usage不复用为正式学习状态。

证据引用和sha256见machine gate。`mcp-diagnostic-usage.json`只记录CLI回传的额外诊断usage，不归入正式组，不推算费用。所有gateway及HTTP server结束后已shutdown，测试site socket已unlink；auth仅留在0700专用WSL home、文件0600，没有归档。

这一验收证明列出的通用正负例通过，并非对所有Python程序、所有DOM形态或所有浏览器攻击面的穷尽证明。AST和原生方法过滤用于观察协议，OS namespace用于文件/进程/网络隔离，二者分别记录。
