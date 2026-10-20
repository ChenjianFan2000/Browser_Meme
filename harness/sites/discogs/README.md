# Discogs 源码可见阶段一站点交付

选择现有 [Discogs 上游站点](../../../veri_env/external/VeriEnv-main/websites/discogs/README.md)，因为它具有连接真实数据库的目录检索、账号认证、收藏、愿望单、市场报价、购物车、结账与卖家上架管理，比单一表单或本地 issue 子域具备更多业务组合。原始目录共 110 个文件、737,560 字节；这是现有 VeriEnv 派生站点，不是官方 Discogs，也不声称官方基准成绩。

原站点使用 Next.js 16.1.1、React 19.2.3、FastAPI 和 SQLAlchemy。后端原生支持 SQLite；无需为本实验另建 PostgreSQL。依赖与业务实现保留上游内容，运行副本和数据库位于 `.runtime/phase1-discogs-20261020/`，上游源码未修改。已有基线、请求和历史实验不被覆盖。

## 职责与入口

- [site.json](site.json)：通用入口读取的站点配置，包含 `setup_command`、`start_command`、工作目录和本地地址。
- [deploy.py](deploy.py)：复制与校验原源码、准备依赖、构建生产前端、初始化独立基线及监督服务进程。
- [cases.json](cases.json)：八个固定任务的 ID、目标和参数；执行脚本由独立实验模型生成。
- [evaluator.py](evaluator.py)：独立重置、只读观察和终点评估，不读取模型预测。
- [adapter_contract.md](adapter_contract.md)：公开状态结构、重置语义与评估边界。
- [validate_backend_offline.py](validate_backend_offline.py)：原始后端/API 和适配器组件验证，不作为 UI 验收。
- [validate_lifecycle.py](validate_lifecycle.py)：使用休眠子进程验证停止文件、信号和进程回收，不启动网站或浏览器。
- [selection.json](selection.json)、[offline_feasibility.json](offline_feasibility.json)：选型、依赖来源、已完成检查与阻碍。

## 完整生产准备与启动

以下命令从仓库根目录 `G:\Browser_Meme` 执行；这些是完整站点运行入口，目前尚未执行成功：

```powershell
python harness/sites/discogs/deploy.py prepare
python harness/sites/discogs/deploy.py serve
```

`prepare` 在独立 venv 安装后端依赖，在副本执行 `npm ci` 和 `npm run build`，再使用原始迁移、种子初始化数据库。它需要本机允许访问依赖源。`serve` 使用 `next start` 启动生产构建，前端地址为 `http://127.0.0.1:12042`，后端为 `http://127.0.0.1:12138`；原站点公开示例账号为 `demo` / `password123`。

通用入口为 `python -m harness.launch`，实际以 `shell=False` 使用配置中的 `setup_argv` / `start_argv`；对应字符串用于显示命令。父进程应保持 `serve` 所在会话存活，并为每次运行设置唯一的 `HARNESS_STOP_FILE` 文件路径。正常停止时创建该文件：部署器在启动、等待健康和运行期间均检查它，随后进入 `finally` 清理自己创建的直接服务子进程并等待回收；它不终止复用的既有服务。父进程等待最多 15 秒，仍无响应时仅对自己启动的进程树执行兜底清理。

手动运行还可在 Windows 使用独立进程组和 `CTRL_BREAK_EVENT` 请求正常停止；POSIX 使用 `SIGTERM`。部署器处理 `SIGINT`、`SIGTERM` 和可用的 `SIGBREAK`。Windows 的 `Popen.terminate()` 使用 `TerminateProcess`，不能执行 Python 清理代码；强制终止或父进程被杀时，通用父进程仍应负责整个进程树。当前未在完整网站运行中验证进程组事件投递，也不将此说明作为 Chrome 启动或 UI 运行证据。

`python harness/sites/discogs/validate_lifecycle.py` 已完成离线组件验证：停止文件触发正常退出、启动前停止、启动期间 `SIGTERM` 的清理、已创建子进程回收、无关进程保留及原信号处理器恢复均通过。使用的是休眠 Python 子进程，网站和浏览器均未启动；证据见 `.runtime/phase1-discogs-20261020/lifecycle-validation.json`。

## 已完成的离线后端验证

```powershell
python harness/sites/discogs/deploy.py prepare-backend-offline
```

该命令使用独立 `venv-offline`，通过 `--system-site-packages` 继承本机已有包，并用 `--no-index --no-deps` 安装四个经过哈希校验的本地 wheel：python-jose 3.3.0、ecdsa 0.19.1、rsa 4.9、Faker 40.43.0。本地缓存来源清单 `.runtime/phase1-discogs-20261020/offline-python-wheels.json` 是该本机复现的输入；完整版本与位置见 `offline-python-inventory.json`，安装来源与哈希见 `offline-install-provenance.json`。这不是完全独立的依赖环境，也没有满足 PostgreSQL 驱动等整份上游依赖清单。

2026-10-20 实际完成：

- 原始迁移和种子成功，形成 30 用户、221 唱片、639 报价和 120 订单。
- 原始 FastAPI TestClient 的健康检查返回 200；错误密码返回 400 且状态不变；正常登录及真实收藏写入返回 200。
- 连续只读观察一致，数据库字节哈希不变；真实 API 写入后重置恢复完整观察；八个任务的重置均匹配冻结表哈希。
- 未执行收藏的目标被独立评估器判失败；即使 API 已写入收藏，缺少 UI 证据仍不能通过完整目标。
- 110 个原始文件与运行副本哈希一致。验证脚本首次误用 `/login` 得到 404，修正为原始 `/auth/login` 后通过；没有改动网站、模型规则或评估器。

证据为 `.runtime/phase1-discogs-20261020/backend-offline-validation.json`。基线 SHA256 为 `6888037bdcda10c123d0cc99f1eda73501e5f5d5934c99d7d3257f236aa9bd50`；该基线首次生成后保存 UUID 和时间戳，后续重置直接恢复，不重新生成。

## 完整 UI 阻碍与覆盖边界

当前执行上下文禁止外部网络，依赖安装曾被系统套接字权限拒绝，额外权限请求也被自动审批拒绝。离线 npm 缓存缺少 Next.js/SWC；已安装的全局 React 版本与站点锁文件不同。浏览器 Chrome 启动还受当前执行权限和进程生命周期约束。未改写前端、未使用替代站点，也未再次尝试网络或权限绕过。因此没有完成生产前端准备、八任务浏览器执行或端到端速度测量。

八任务固定化便于审查分母和后续回归，涵盖认证拒绝、目录检索、匿名操作门控、收藏、愿望单、加购、结账组合与上架后停用。它不等于完整操作或条件覆盖；例如账号注册、全部筛选与分页、并发、售罄竞态和所有权限分支均未纳入这八例。后端组件通过也不代表八例 UI 通过。阶段二主动探索与强制隔离、阶段三冻结泛化与在线适应，以及严格速度对照仍需单独协议和实际运行。
