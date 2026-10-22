# 发布工具的运行依赖

本轮实际使用 Windows Python 3.11.4。导出、合并、独立审核、ZIP 分卷与恢复使用 Python 标准库；`github_release.py` 另使用本机已安装的 `requests==2.32.5`。发布工具的单元测试使用 `unittest`，阶段二 Harness 回归使用既有 `pytest` 环境。

Git 工作树准备与 GitHub 发布需要已安装的 Git。发布器通过已有 Git credential helper 在内存中取得认证，不要求把令牌写入源码、参数或环境变量；它固定校验仓库和账号，不执行登录或修改可见性。

分卷与恢复命令见 [README](README.md)，新增格式处理见 [v003 说明](README-ico-v003.md)，合并命令见 [合并说明](MERGE_EXPORT_MANIFESTS_V001.md)，远端发布见 [Release CLI](GITHUB_RELEASE.md) 及 [必需正文哈希](GITHUB_RELEASE_BODY_BINDING_V002.md)。下载后的实际路径约定见 [恢复布局](RESTORE_LAYOUT.md)。这些发布步骤不启动浏览器实验或模型调用。
