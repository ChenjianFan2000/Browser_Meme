"""Exact CLI permission arguments shared by trusted launchers."""
import json

CODEX = "/opt/codex/bin/codex"
CORE = "/opt/codex/runtimes/codex-primary-runtime/dependencies/python"
BROWSER = "/usr/lib/chromium"


def toml_inline(value):
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + "=" + toml_inline(v) for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(map(toml_inline, value)) + "]"
    return json.dumps(value)


def overrides(*, runtime=None, socket=None, extra_paths=None):
    filesystem = {":root": "deny", ":minimal": "read", ":workspace_roots": "write", CODEX: "read"}
    if runtime:
        filesystem.update({str(runtime): "read", CORE: "read", BROWSER: "read",
                           "/opt/codex/runtimes/codex-primary-runtime/dependencies/node": "read"})
    if socket:
        filesystem[str(socket)] = "read"
    filesystem.update(extra_paths or {})
    settings = {
        "approval_policy": "never", "default_permissions": "p2",
        "shell_environment_policy.inherit": "none",
        "shell_environment_policy.set": {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        "permissions.p2.filesystem": filesystem,
        "permissions.p2.network.enabled": bool(socket),
        "features.network_proxy": True,
        "permissions.p2.network.allow_local_binding": bool(socket),
        "permissions.p2.network.domains": {},
        "permissions.p2.network.dangerously_allow_all_unix_sockets": bool(socket),
        "permissions.p2.network.unix_sockets": {str(socket): "allow"} if socket else {},
        "web_search": "disabled", "project_doc_max_bytes": 0,
        "features.skip_host_skill_discovery": True,
        "agents.enabled": False, "agents.max_threads": 1, "agents.max_depth": 0,
        "features.multi_agent_v2": False,
        "skills.include_instructions": False, "skills.bundled.enabled": False,
        "memories.use_memories": False, "memories.generate_memories": False,
    }
    args = []
    for key, value in settings.items():
        args.extend(["-c", key + "=" + toml_inline(value)])
    for feature in ("apps", "plugins", "multi_agent", "hooks", "browser_use", "computer_use",
                    "image_generation", "skill_search", "skill_mcp_dependency_install", "memories"):
        args.extend(["--disable", feature])
    return args
