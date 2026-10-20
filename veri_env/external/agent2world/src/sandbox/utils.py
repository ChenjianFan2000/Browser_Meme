from __future__ import annotations
"""
沙箱工具函数
"""
import os
import json
import requests
import tomli
from typing import List, Optional, Dict, Any


def get_github_repo_files(github_url):
    """获取GitHub仓库文件列表"""
    # 解析 owner 和 repo 名
    parts = github_url.rstrip('/').split('/')
    owner, repo = parts[-2], parts[-1]

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
    print(url)
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"访问失败: {url}")
        print(f"返回内容: {resp.text}")
        return []
    items = resp.json()
    files = []
    for item in items:
        if item["type"] == "file":
            files.append({
                "name": item["name"],
                "download_url": item["download_url"]
            })
    return files


def find_dependencies(data):
    """递归查找依赖项"""
    deps = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "dependencies":
                deps.append(v)
            else:
                deps.extend(find_dependencies(v))
    elif isinstance(data, list):
        for item in data:
            deps.extend(find_dependencies(item))
    return deps


def get_requirements(tools_path, mcp_server):
    """从工具配置文件获取依赖需求"""
    print(tools_path)
    print(mcp_server)
    with open(tools_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    servers = data.get("servers", [])
    github_url = None
    for server in servers:
        name = server.get("server_name") or server.get("name")
        if name and name.strip().lower() == mcp_server.strip().lower():
            github_url = server.get("metadata", {}).get("github")
            print("找到 github 地址：", github_url)
            break
    if not github_url:
        print("未找到对应的 github_url！")
        return None

    files = get_github_repo_files(github_url)
    requirements = []
    for f in files:
        if f["name"].endswith(".toml"):
            print(f"发现 toml 文件: {f['name']}")
            resp = requests.get(f["download_url"])
            if resp.status_code == 200:
                tmp_path = f"./tmp_{f['name']}"
                with open(tmp_path, "wb") as tmp_file:
                    tmp_file.write(resp.content)

                with open(tmp_path, "rb") as toml_file:
                    toml_data = tomli.load(toml_file)
                all_deps = find_dependencies(toml_data)
                flat_deps = []
                for dep in all_deps:
                    if isinstance(dep, list):
                        flat_deps.extend(dep)
                    else:
                        flat_deps.append(dep)
                requirements.extend(flat_deps)
                # print(requirements)
                os.remove(tmp_path)
                print(f"已删除临时文件: {tmp_path}")
            else:
                print(f"下载失败: {f['download_url']}")
        if f["name"] == "requirements.txt":
            print(f"发现 requirements.txt 文件: {f['name']}")
            resp = requests.get(f["download_url"])
            if resp.status_code == 200:
                # 直接处理 resp.text，不需要保存为临时文件
                lines = resp.text.splitlines()
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    requirements.append(line)
                print(f"requirements.txt 依赖: {requirements}")
            else:
                print(f"下载失败: {f['download_url']}")

    return requirements
