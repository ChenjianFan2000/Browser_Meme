# 原始生产站点动态 API 404：独立只读诊断

结论：当前实际运行的是未经修改的上游源文件和锁定的 Next.js 16.1.1 生产构建。上游 `next.config.ts` 中的通配重写先于动态 API handler 生效，将请求交给并不存在 `/api` 前缀路由的 FastAPI。这能同时解释收藏、愿望单和卖家搜索的实际 404。未发现部署器删掉 handler、改写业务源码或设置错误的实际后端地址。

这不表示环境与上游 Docker 完全相同：当前使用 Windows、Node 24.5.0、独立 Python venv、外置冻结 SQLite，前端端口覆盖为 12042；Docker 声明 Node 22 和端口 12093。本文没有在该 Docker/Node22 环境复现，不把当前结论扩展为跨平台测量。

## 实际证据

- [actual-network-responses.json](actual-network-responses.json) 仅从已完成 `anchor-initial-002/cases/*/events.jsonl` 的真实 `network_response` 事件抽取，保留 case、事件序号、时间、方法和状态，不读取模型预测。
- 收藏的 `POST http://127.0.0.1:12042/api/me/collection/221`、愿望单对应路径、卖家 `GET /api/backend/search?q=The%20Dark%20Side%20Of%20The%20Moon` 均返回 404；同轮静态登录、加购和结账路径有成功响应。
- [backend-route-excerpt.txt](backend-route-excerpt.txt) 记录 FastAPI 实际收到了 `POST /api/me/collection/221`、`POST /api/me/wantlist/221`、`GET /api/backend/search?q=...`，并返回 404。请求已到达正确的运行中后端，不是 DNS、端口、CORS 或浏览器等待造成的假象。
- 生产 `frontend/.next/server/app-paths-manifest.json` 包含 `/api/me/collection/[id]/route`、`/api/me/wantlist/[id]/route`、`/api/backend/[...path]/route` 和 `/api/cart/items/[id]/route`。相应动态路径也在 `routes-manifest.json` 中，handler 未在构建中遗漏。
- [diagnosis.json](diagnosis.json) 保存本轮检查范围、110 个原始文件一致性、冻结站点文件一致性、构建 ID，以及源码、构建清单和原始事件文件的 SHA256。没有新的浏览器/API 请求、数据库写入或重置，没有改任何冻结站点文件。

## 路由因果链

上游 `frontend/next.config.ts:5` 返回一个数组，其中包含：

```text
source: /api/:path*
destination: http://localhost:12138/api/:path*
```

生产 `routes-manifest.json` 将该规则放在 `rewrites.afterFiles`；`beforeFiles` 和 `fallback` 为空。锁定安装的 Next.js 自身实现 `node_modules/next/dist/server/lib/router-utils/resolve-routes.js:41` 明确依次排列：静态精确 `check_fs`、`rewrites.afterFiles`、随后执行包含动态路由匹配的 `checkTrue()`。遇到外部重写目标时直接返回该目标，不继续动态匹配。

因此实际顺序为：

1. `/api/auth/login`、`/api/cart/items`、`/api/checkout` 能精确命中静态 handler，使用 `backendFetch` 将 cookie 中的凭据转换为后端 Authorization，并访问无 `/api` 前缀的后端路由。
2. `/api/me/collection/221` 无静态精确文件名；本应匹配 `[id]`，但先被 `afterFiles` 通配重写为后端 `/api/me/collection/221`。
3. FastAPI 的 `backend/app/api/router.py` 直接挂载 account/catalog/auth/marketplace routers，没有 `/api` 前缀。不存在上述重写目标，故返回 404。
4. 卖家的 `/api/backend/search?q=...` 同样先命中重写。后端实际收到 `/api/backend/search?q=...`，而不是已实现的 `/search`，所以仍是 404。

这也预示动态购物车删除和卖家 listing 更新/停用可能受到同一配置影响；本文没有额外执行这些写操作，实际结果以后续 UI 证据为准。

## 部署适配核对

| 项目 | 上游材料 | 本轮实际与判断 |
| --- | --- | --- |
| 网站源码 | 完整 110 个文件 | 上游与运行副本逐文件哈希相同 |
| 前端依赖 | package-lock，Next 16.1.1 / React 19.2.3 | 原锁 `npm ci`，生产构建成功；未改配置 |
| 启动方式 | start_servers.sh 执行 build / next start | 本轮显式 build 后 next start，生产模式一致 |
| 后端端口 | ports.json 和硬编码 rewrite 均为 12138；README/.env.example 另写 12160，材料内部不一致 | 实际 uvicorn 与 API_INTERNAL_URL 均为 127.0.0.1:12138；日志证明请求到达该后端 |
| 前端端口 | ports.json/Docker 为 12093；README/.env.example 为 12042；脚本允许环境变量覆盖 | 本轮 12042，配套 URL/CORS 显式设置；不改变匹配路径 |
| 数据库 | 本地 start/reset 脚本支持 SQLite，compose 另提供 Postgres | 外置同一冻结 SQLite；本文不读取变化中的业务状态来构造答案 |
| Node/Python | Docker Node22 / Python3.11，Python需求未锁具体版本 | 本轮 Node24.5.0 / Python3.11.4，实际50个分发包已锁并离线重建验证；不是 Docker 位级复现 |

以上差异必须保留在协议中，但不能把有明确源配置和真实重写请求证据的 404 归咎于“缺包”或“错误后端端口”。尚未独立实测上游 Docker，不能排除其他环境差异引起的其他问题。

## 卖家搜索的第二个问题与先前诊断修正

先前独立检查只看了 `frontend/src/app/api/backend/[...path]/route.ts`，判断其不复制 `req.url` 的 query，后端必填 `q`，因而预期 422。这遗漏了更早执行的通配重写，属于不完整的路径分析。

现有证据支持的准确表述是：当前运行首先在外部重写路径得到 404；只有在未来版本解除该遮挡、实际进入 catch-all handler 后，源码中“只拼 path、不转发 query”的另一个缺陷才可能导致 `/search` 缺少 `q` 并返回 422。该后续 422 尚未在修复后的真实网站执行验证，不能写成当前已测结果。

## 可审查的后续修复方向（未实施）

这是上游网站配置/实现问题，不能用改模型选择器、调用后端 API 或放宽原目标来修复。本轮保持原站点与原8/扩展12目标，保留失败。

若另开修复站点版本，可评审两处最小变更：

- 删除通配 `/api/:path*` rewrite，让已有静态和动态 API handler 正常处理请求；或将其改放 `fallback`，使动态 handler 先有机会匹配。仅把重写目标的 `/api` 删掉并不充分：这仍会跳过 cookie 到 Authorization 的转换，且 `/api/backend/search` 也不会自动变成 `/search`。
- 在 catch-all handler 构造后端 URL 时保留 `new URL(req.url).search`，修复公开搜索参数传递。此变更不能自动证明所有通用代理认证与转发分支正确，仍需明确覆盖边界。

这些属于新网站配置/源码版本，不是修正一个错误环境变量。必须在新 runtime/协议/运行号中实施、重新构建与哈希登记，保留原始110文件和本轮冻结证据。修复后独立 UI 验证应覆盖匿名门控、两种 membership、重复添加、卖家搜索及创建/停用、动态购物车删除、静态登录/结账回归和无关状态；这里没有声称已完成任何修复或修复后成绩。
