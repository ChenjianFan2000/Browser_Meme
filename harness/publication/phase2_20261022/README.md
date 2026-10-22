# 第二阶段公开结果分卷工具 v001

本轮实验已结案，入口为[中文实验报告](../../experiments/phase2-discogs-20261021-01/reports/第二阶段实验报告-001.md)和[结案索引](../../experiments/phase2-discogs-20261021-01/reports/第二阶段结案索引-001.md)。全量证据通过 [GitHub Release](https://github.com/ChenjianFan2000/Browser_Meme/releases/tag/phase2-discogs-20261021-01) 分卷提供；代码与可直接阅读的报告保存在 Git。报告中的细粒度原始路径需下载全部分卷并恢复后查看。

公开范围包含全部学习、开发、冻结评测、独立真值检查、失败、超时、协议偏差与相关部署/隔离验收材料。`private/` 表示实验期间对学习者不可见，本次在首次冻结评测结束后向人类公开，不变更第三阶段的输入白名单。用户于 2026-10-22 明确授权保留现有公开仓库并公开发布全部结果。

本机未脱敏原件继续保留。公开副本去除会话 Cookie、JWT 等认证值，并记录原件与公开副本的双 SHA256；原始评分、协议和历史清单不追溯改写。认证存储、运行数据库、安装依赖与缓存不作为结果文件公开，其排除范围由清单说明。图片接受字节模式检查，不声称完成全量 OCR。公开副本按 `export_sha256` 验证，历史清单中因脱敏产生的受控差异按映射解释。

原始登记的 180 例任务成功 176 例；540 个整任务预测字段中正确 236、未知 304、错误 0。A2718 与 A3141 因学习期停止违规被隔离，结果仍全部保留；只有种子 1729 构成完整合规 A/B 配对。四个学习包获第三阶段准入，第三阶段尚未启动。本轮不构成严格速度对照、全站覆盖或官方基准成绩。

Python 3.11+ 标准库工具。只根据独立审计员批准并由调用者固定 SHA256 的导出清单打包，不决定哪些内容可以公开。工具对明示的认证存储、凭据目录与缓存路径硬拒绝；批准的合成 `public-fixture.json` 不因内容字段名称再次被否决。目录中的测试只读写临时合成数据。

实际格式检查发现一个此前未识别的临时 Chromium profile，已按[独立范围审查](temporary-browser-profile-exclusions-001.json)排除其中 23 个缓存/数据库文件，保留相邻正式浏览器证据。该目录在识别前曾被格式、字节或哈希检查；识别后的导出不再读取其内容。不能泛称浏览器认证状态从未被读取：trace/browser-state 本来就需要读取以脱敏；本机真实凭据文件的保护与这些本地实验会话材料分别说明。发现时尚未上传，也未输出匹配值。

## 独立副本导出与待审清单

`export_evidence.py` 先对本轮显式指定的目录、单文件及 runtime inventory 建立清单，再生成独立脱敏副本。主协调者指定实际范围并运行，不能把目录遗漏当成已经公开全部结果。目录中的符号链接、Windows junction/reparse point 和遍历错误会明确拒绝，不会静默跳过；认证存储与缓存目录则以排除记录保留。

```powershell
python harness/publication/phase2_20261022/export_evidence.py inventory `
  --source-root G:\Browser_Meme `
  --root harness/experiments/phase2-discogs-20261021-01 `
  --runtime-inventory .runtime/publication-phase2-20261022/runtime-inventory-002.json `
  --output .runtime/publication-phase2-20261022/inventory-001.json

python harness/publication/phase2_20261022/export_evidence.py export `
  --source-root G:\Browser_Meme `
  --inventory .runtime/publication-phase2-20261022/inventory-001.json `
  --output-dir .runtime/publication-phase2-20261022/exports-001 --workers 4
```

`--root`、`--file`、`--runtime-inventory` 可重复；上述是命令形状示例，最终还应加入本轮指定的通用实现、测试与其他范围。导出目录必须不存在。输出只会是 `exported_pending_independent_approval` 或 `export_blocked`，绝不自动批准；任何失败保留具体文件与失败分类并以退出码 2 停止成功声明。独立审计员需复核实际副本、排除与失败清单后，另写 `approved_for_publication` 清单并固定其 SHA。

脱敏支持任意字段顺序的请求／响应头、浏览器 cookie storage、敏感 local-storage name/value、嵌入 JSON 字符串、JSONL／trace、无扩展名 ZIP 资源与嵌套 ZIP。只替换敏感值跨度，保留其余 JSON 字节、空白、字段顺序、行尾及原字符串转义；无变化 ZIP 保留整个原字节，变化 ZIP 可能重压缩，但无变化成员的解压后字节保持不变。明确 `is_real_credential=false` 只豁免其范围内 password 类字段，tokens／cookies 从不豁免；该标记的真实性仍由独立审计确认。JWT、provider key、GitHub token、Google key、AWS AKIA／ASIA 与 PEM 形状均会检查。

HAR 的 `encoding=base64`、CDP 的 `base64Encoded=true` 以及 base64 source 对象的 text/body/data 会先解码再检查。JSON／文本按同样规则脱敏并重新编码，安全图片等二进制保留原编码字段；坏 base64、未知二进制、超大 payload 或 base64 中的归档会明确阻止并交独立审计，不会直接放行。

未识别扩展名的 UTF-8 纯文本仍扫描；未知二进制、二进制中的凭据形状、损坏结构化记录、未知编码、超深／超大内容会阻止导出。已识别图片等二进制不会盲目改写。被排除的独立认证存储不读取或计算哈希；ZIP 中的认证存储不解压、不单独计算成员哈希，父归档的原件 SHA 仍标识整个原归档。路径过滤和这些模式均不替代独立内容审计。

默认最多四个 worker、八个在途 future，磁盘 spool 的单层内存阈值 8 MiB，单段文本 32 MiB、JSONL 单记录 16 MiB、ZIP 单成员 512 MiB、嵌套 ZIP 深度五层。大文件和归档不整体并发驻留内存。导出阶段每十五秒输出计数进度，不输出匹配的凭据值；数据规模过限或编码不能识别时先保留失败记录，再由独立审计决定新导出版本。

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_export_evidence.py -v
```

合成测试也验证原件不改、敏感跨度外字节不变、认证存储读取／哈希前排除、链接拒绝、未知二进制失败，以及发布工具／测试文件不因运行时生成的合成凭据自我脱敏。

### 独立进程分片导出

CPU 密集的 JSON 处理可以使用 `run_export_shards_v001.py`。它不修改既有导出器，将同一原始 inventory 按唯一 `archive_path` 排序后稳定轮转分片；最多八个独立 Python 子进程，每个调用原导出器且固定 `--workers 1`。Windows 使用隐藏进程窗口。原单进程尝试由协调者停止并保留，不覆盖其产物。

```powershell
python harness/publication/phase2_20261022/run_export_shards_v001.py `
  --source-root G:\Browser_Meme `
  --inventory .runtime/publication-phase2-20261022/inventory-002.json `
  --inventory-sha256 <原始inventory的SHA256> `
  --output-dir .runtime/publication-phase2-20261022/exports-002-sharded `
  --shards 8 --jobs 8
```

输出目录必须新建。`shard-plan.json` 固定父 inventory、导出器 SHA、分配方法与每片输入 SHA；每片保留 inventory、PID／命令 launch 记录、stdout、stderr、导出目录及子 manifest。`shard-execution.json` 与总 `export-manifest.pending.json` 绑定各子 manifest／日志 SHA。父进度每十五秒仅报运行／完成分片计数，文件进度见各片 stdout。

合并保留每个子 entry 的完整字典，逐项验证父清单对应关系与双哈希字段，不改子结果。父 `excluded_roots` 只合并一次；每片输入不继承这些目录排除；逐条文件排除和失败仍由相应子结果保留。完整分母必须等于包含＋文件排除＋失败，目录排除另计。任一子进程非零、子清单缺失／绑定异常、覆盖不完整或调度中断只能生成 blocked；缺失子结果的所有原输入明确记为失败。最终清单仍仅 pending／blocked，由独立审计批准，调度器不执行上传或读取源凭据内容。

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_export_shards.py -v
```

小合成测试运行真实 1／2／8 个 Python 子进程，验证结果等效、完整覆盖、排除与失败聚合、缺失子结果、重复／路径／哈希拒绝及原件不变；不作为真实 13 GB 导出的完成记录或性能测量。

## 导出清单

UTF-8 JSON，顶层 `schema_version=1`、`status="approved_for_publication"`、非空 `entries`。每项格式：

```json
{
  "source_path": ".runtime/publication-phase2-20261022/exports/example.json",
  "archive_path": "harness/experiments/phase2-discogs-20261021-01/example.json",
  "original_sha256": "64位小写十六进制原件SHA256",
  "export_sha256": "64位小写十六进制导出副本SHA256",
  "treatment": "redacted"
}
```

- `source_path` 相对显式传入的仓库根目录；未脱敏项指原件，脱敏项指已审计的独立副本。工具仅访问清单列出的源文件，不为核对脱敏前哈希读取原件。
- `archive_path` 保留原始仓库相对路径，明确批准的 `.runtime/` 管理证据也可以保留路径。两种路径均使用 `/`，拒绝绝对路径、`..`、重复／大小写冲突、文件与祖先路径冲突、Windows 非法路径、符号链接和 junction/reparse point。
- `treatment="unchanged"` 要求两个 SHA256 相等；`redacted` 保留原件和导出件的双哈希。实际输入必须匹配 `export_sha256`。`exclusions` 等额外顶层审计信息可以保留，但不会进入 ZIP 文件列表。
- `auth.json`、`secrets`、`codex-home`、`.env`、常见私钥、缓存、依赖与字节码路径在读取前拒绝。工具不声称通过路径过滤证明任意文件正文或嵌套 ZIP 不含秘密；内容及嵌套归档的公开审计由批准清单负责。只批准清单文件不等于操作系统访问隔离。

## 打包

从 `G:\Browser_Meme` 运行。将下面的路径和哈希替换为独立审计员交付的确切值；清单不得在批准后修改。

```powershell
python harness/publication/phase2_20261022/package.py pack `
  --manifest .runtime/publication-phase2-20261022/approved-export-manifest.json `
  --approved-manifest-sha256 <审计员批准的清单SHA256> `
  --source-root G:\Browser_Meme `
  --output .runtime/publication-phase2-20261022/volumes-001 `
  --target-mib 512 --workers 4
```

输出目录必须不存在。预检完整清单与每个输入的实际 SHA 后才创建输出目录。最多四个压缩线程，按 `archive_path` 排序并以输入大小和 ZIP 开销稳定分卷；普通文本用 deflate level 1，PNG、ZIP 等已压缩格式直接存储。每卷是可以单独解压的标准 ZIP，保留条目相对路径和导出字节，不是跨卷分片流，也不使用 Git LFS。

每卷目标约 512 MiB，单个大文件可以独占超过目标的一卷；每个最终 ZIP 严格小于 2 GiB。无法独占容纳的大文件直接失败，不拆文件。实际 ZIP 写完后检查总大小，并重新读取 ZIP 内每个条目验证 SHA、大小、路径、成员类型与完整列表。输入预检、边写边复核和卷内复核都会读取字节，耗时计入真实打包过程。固定元数据与排序保证同一工具、Python/zlib 实现及相同输入产生稳定 ZIP；不承诺跨 zlib 版本字节一致。

成功产出 `volume-00001.zip` 等独立卷、`volume-index.json`、`SHA256SUMS`。索引含每卷 SHA／字节／文件数和每项路径／双哈希／处理方式。写入期失败保留输出及 `PACK_FAILED.json`；没有完成索引的失败目录不可发布，重试使用新目录。工具不上传、不修改 Git，也不读取或修改用户认证。

## 校验与恢复

下载同一批完整 ZIP 和索引到一个目录，先从可信发布页固定索引 SHA，再执行：

```powershell
python harness/publication/phase2_20261022/package.py verify `
  --index .runtime/publication-phase2-20261022/volumes-001/volume-index.json `
  --index-sha256 <可信发布页的索引SHA256> --workers 4

python harness/publication/phase2_20261022/package.py restore `
  --index .runtime/publication-phase2-20261022/volumes-001/volume-index.json `
  --index-sha256 <可信发布页的索引SHA256> `
  --output .runtime/publication-phase2-20261022/restored-001 --workers 4
```

恢复会先验证全部卷与成员，再写入不存在的新目录；不会覆盖现有仓库或账号配置。目标内保留 `harness/...`、明确批准的 `.runtime/...` 等原相对路径。逐卷直接解压也可得到该卷文件，但完整性验收应使用上述完整索引校验。索引 SHA 参数省略时只验证文件之间的一致性，不声称发布来源经过认证。

恢复后的文件必须匹配 `export_sha256`。脱敏项与 `original_sha256` 不同是公开映射的预期结果；冻结评分、原件清单与历史引用不重写。原实验哈希检查遇到脱敏项时，应依据公开映射解释差异，不能声称公开脱敏副本等于未脱敏学术原件。公开评估私有材料也不使其成为后续学习者允许输入。

## Release URL 补充索引

发布者在上传完成后将 GitHub Release REST 响应保存为新文件，例如 `release-rest.json`。本工具离线读取响应，核对每卷名称和大小，生成独立 URL 补充索引，不改原 ZIP 或原索引：

```powershell
python harness/publication/phase2_20261022/package.py asset-index `
  --index .runtime/publication-phase2-20261022/volumes-001/volume-index.json `
  --index-sha256 <卷索引SHA256> `
  --release-json .runtime/publication-phase2-20261022/release-rest.json `
  --output .runtime/publication-phase2-20261022/release-asset-urls-001.json
```

补充索引绑定卷索引 SHA，并列出浏览器下载地址与 REST asset URL。此步骤不发网络请求，也不检查远端实际内容 SHA；远端下载复核仍应重新运行 `verify`。

## 合成验证

```powershell
python -m unittest discover -s harness/publication/phase2_20261022 -p test_package.py -v
```

测试涵盖逐字节完整恢复、中文路径、空文件、脱敏双哈希、4 线程与顺序无关的稳定分卷、CLI、路径越界与重复、真实 Windows 链接／junction 逃逸、凭据与缓存路径读取前拒绝、ZIP 成员链接、损坏卷与成员哈希、大小硬边界、源文件预检后变更、失败目录保留、现有目录不覆盖，以及离线 REST URL 索引。真实实验数据打包结果应另记运行、输入批准清单 SHA 和最终产物 SHA，不把本合成测试当成实际 11 GB 打包验收。
