# Spec018 技术评审（Tech Lead）

- 评审者：当前协作 Agent（开发主管 / Tech Lead）
- 评审模型：`gpt-5.6-luna`，`xhigh`（本轮指定，仅用于本次技术评审）
- 评审时间：2026-09-08 19:49–19:54（Asia/Shanghai）
- 评审对象：`docs/sdd/specs/018-knowledge-document-chunk-inspector.md`、`docs/sdd/plans/018/README.md`、Task 02–07 计划及当前知识库前后端实现
- 评审方式：只读；未修改业务代码、测试代码、配置或用户数据，未运行会改变项目状态的命令
- 进展日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260908-194921.md`

## 结论

**打回，暂不通过。**

产品方向清楚，检查清单与 Qdrant 检索索引分离、复用现有 v1/v2、禁止检查器重新 embedding、Marked + DOMPurify 安全链路等原则正确；但当前 Spec 仍有四个实现前硬阻塞：

1. 现有 PDF 解析只保留纯文本，未保留 bbox；在现有规范化清洗之后无法凭空恢复稳定的 PDF 文本块坐标，核心双向定位还没有可实现证据。
2. 现有元数据仍是 `papers.json`/`paper_id`，Qdrant payload 仍是 `paper_id`，没有无损迁移、旧 point payload 兼容和 fingerprint 的冻结协议；“保留旧 ID”本身不足以保证旧切片能被新 `document_id` 查询。
3. Markdown 的 `page/page_end` 与当前 `Chunk`、`Hit`、引用提示词的整数页码契约冲突，且上传、解析、状态、映射和安全降级的协议没有冻结。
4. Manifest 的原子写入、跨线程/跨进程幂等、重启恢复、Qdrant 重建竞态、删除失败补偿和大文档容量上限没有被定义；现有任务去重只覆盖单进程索引任务。

因此当前不能进入用户确认后的实现阶段。Spec 必须先补齐下列 P0/P1 约束，并在技术复评通过后再确认；在此之前不应修改业务代码，也不应把 Task 02 的 Go/No-Go 当作实现阶段才发现的普通风险。

## 已确认可复用的基础

| 方面 | 代码事实 | 判定 |
|---|---|---|
| v1/v2 切分 | `backend/app/knowledge_base/infrastructure/chunkers.py:161-234` 已提供 v1 逐页切分、v2 结构切分和跨页 `page_end`；`parse.py:83-88` 保留 v1 委派 | 方向可复用，但必须冻结“索引时文本”与“建 manifest 时文本”的同源规则 |
| Qdrant point ID | `backend/app/knowledge_base/infrastructure/index.py:91-99` 已将 `paper_id + chunker + chunk_index` 纳入确定性 UUID | 可复用；迁移不得生成新 ID，也不得因检查器重建向量 |
| payload 基础字段 | `index.py:121-149` 写入 `paper_id/file_name/page/page_end/section/chunker/is_citation/chunk_index/text/uploaded_at` | 足以构造部分 `ChunkSnapshot`；没有 `document_id`、源 hash、fingerprint 字段或读取快照能力 |
| 任务串行化 | `backend/app/knowledge_base/infrastructure/tasks.py:21-62` 为单线程池并按 `(paper_id, chunker)` 去重 | 仅是单进程、索引任务级别；不能直接满足 manifest 的跨进程并发门禁 |
| Markdown 安全渲染 | `frontend/app.js:1392-1412` 使用 Marked + DOMPurify，缺库时转义降级；`frontend/index.html:248-250` 依赖本地 vendored 文件 | 可复用安全链路，但尚无“每个 block 带 block_id”的渲染协议；当前没有 PDF.js |
| 旧状态兼容 | `store.py:231-270` 仅在内存补齐 v1/v2，`store.py:322-347` 启动时把残留 `indexing` 置为 `failed` | 可作为迁移起点；不是 KnowledgeDocument/Manifest 的无损迁移实现 |

## 硬阻塞与具体修改建议

### P0-1：PDF bbox 与规范化文本没有来源映射协议（核心目标不可实现）

**证据：**

- `backend/app/knowledge_base/infrastructure/parse.py:37-55` 调用 `page.get_text("text")`，返回值只有 `(page, text)`；没有 PyMuPDF `blocks/words/dict` 的 bbox、block type、阅读顺序或页面尺寸。
- `parse.py:58-76` 再对整页文本调用 `normalize_text`；`chunkers.py:161-173` 与 `:201-234` 都只消费规范化后的 `(page, text)`，不会留下字符到原始 PDF block 的 provenance。
- Spec 要求 `SourceBlock.locator.kind=pdf_bbox`、相对页面坐标和双向点击（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:48-57,110-121`），但当前实现没有任何可用于生成这些字段的数据。
- Task 02 仅计划在 Spec 确认后验证（`docs/sdd/plans/018/task-02-validate-source-anchor-feasibility.md:16-28`），而其失败会触发 No-Go（同文件 `:42-46,58-61`）；这说明核心可行性尚未被技术评审所证明。

**风险：**

不能用对 `Chunk.text` 做字符串搜索来“补回” bbox：规范化会合并行末断词、改变硬换行并跳过空白页；双栏、重复段落、连字、旋转页、裁剪框和跨页 v2 都可能产生错误的 block。错误定位会以“ready”状态静默展示，违背检查器的事实来源目标。

**必须修改：**

1. 把 Task 02 变为实现前的硬门：用脱敏双栏/旋转/重复文本 fixture 产出明确的 Go/No-Go 文档，固定映射率、重复文本的 tie-break、坐标缩放误差阈值和失败降级；No-Go 必须先更新 Spec 缩小承诺，不能继续 Task 03。
2. 若 Go，冻结一个带 provenance 的后端解析 DTO：至少包括 page width/height/rotation、原始 block/line/word bbox、稳定阅读顺序、归一化后文本及其原始字符区间；索引和 manifest builder 必须使用同一版本的规范化产物。单独再次调用 `get_text("text")` 不足以满足。
3. 明确 PDF.js viewport/canvas/text-layer/overlay 的坐标转换（旋转、crop box、device pixel ratio、缩放和容差），只用公开 display API；验收须验证不同 zoom/rotation 下仍定位同一块。若不能稳定覆盖，状态必须是 `partial` 而不是 `ready`。

### P0-2：无损迁移和旧 Qdrant payload 身份契约不完整

**证据：**

- Spec 只规定 `paper_id` 原值迁为 `document_id`（`:33-46`），但当前领域对象仍为 `PaperRecord.paper_id`，存储仍为 `data/kb/papers.json`（`backend/app/knowledge_base/infrastructure/store.py:1-5,46-68`）。
- `store.load_papers` 对 JSON 解码错误直接返回空列表（`store.py:79-98`）；`save_papers` 直接 `write_text`（`:101-108`），没有迁移前备份、版本标记、临时文件、fsync 或“损坏时拒绝写入”。一次迁移遇到损坏 JSON 就可能把真实记录当成空列表覆盖。
- 现有 Qdrant payload 只有 `paper_id` 等字段（`index.py:121-149`），没有 `document_id`。新检查接口又要求按 `document_id + chunker` 读取真实片段（Spec `:95-108`，Task 04 `docs/sdd/plans/018/task-04-backend-document-inspection-api.md:21-28,41-46`）。旧 points 不会自动匹配新字段。
- 现有 legacy backfill 只补 `chunker/is_citation/section/page_end`（`index.py:363-405`），并没有 document identity、chunk fingerprint 或旧索引来源 hash。

**风险：**

“不重新 embedding”不等于“迁移完成”。若查询只过滤 `document_id`，旧文档会返回空清单；若同时盲目写 payload，又未校验 point 数、chunker、chunk_index 的完整性，可能把旧索引错归到另一文档。当前 JSON 读取失败的空列表降级尤其可能造成不可逆元数据丢失。

**必须修改：**

1. 在 Spec/Task 03 冻结 versioned migration：原子备份、输入 JSON 损坏/非 list 时 fail-closed、迁移前后记录数/ID/`stored_name`/时间/论文元数据/原件 hash/Qdrant point count 对照、重复运行无副作用、异常时保留原文件并可恢复。迁移要定义旧 naive `uploaded_at` 如何转换为带时区 `created_at`，不能静默伪造时区（Spec `:40-46` 与 `store.py:194-223`；当前 `datetime.now().isoformat` 无时区）。
2. 明确 `document_id` 与历史 `paper_id` 的存储兼容策略：建议长期在内部保存单一 ID，并在 Qdrant 仅做一次**payload 更新**（不触碰向量）写入 `document_id`/必要 schema 字段；在迁移完成前 API 读取必须兼容旧 `paper_id`，且要有旧点缺字段/重复/缺号的诊断结果。若不新增 payload 字段，则必须把“过滤 `paper_id` 作为 document_id 别名”写入 application 契约和验收，不能只写在实现者脑中。
3. 冻结 `index_fingerprint` 与 `chunk_fingerprint` 的 canonical JSON 字段、排序规则、空值/类型/Unicode 规范和 hash 算法；至少包含 `chunker, chunk_index, text, page, page_end, section, is_citation`，按 `chunk_index` 排序并拒绝重复/缺号。Qdrant `scroll` 的 point UUID 顺序不能代替 chunk 顺序。
4. 为旧文档增加“历史源 hash 未知”状态：首次 hash 只能证明当前原件，不证明它与当年 embedding 的源文本一致；应显示 `partial`/诊断或通过保存的旧索引证据核对，不能把当前 hash 直接宣称为历史索引 hash。

### P0-3：Markdown 语义与现有 Chunk/Hit/引用契约冲突

**证据：**

- Spec 允许 Markdown 的 `ChunkSnapshot.page/page_end` 为 null（`:59-69`），但现有 `Chunk.page` 是 `int` 且 `__post_init__` 把 `page_end` 归一为整数（`backend/app/knowledge_base/infrastructure/chunkers.py:81-99`）。
- `retrieve.Hit` 同样声明 `page: int`，并把 payload page 强制 `int(... or 0)`（`backend/app/knowledge_base/infrastructure/retrieve.py:68-102`）；`prompts._page_label` 总是生成“第 N 页”（`backend/app/knowledge_base/infrastructure/prompts.py:6-20`），`citation_payloads` 也总是传 `page/page_end`（`:35-47`）。
- 当前索引入口只接收 PDF 页文本：`index.py:206-230` 调 `extract_pages`，`index.py:260-323` 调 `extract_pages_normalized` 和 PDF 切分；上传路由只接受 `.pdf` 和 `%PDF` 前缀（`backend/app/api/routes_kb.py:107-132`）。
- Task 04 写了“Markdown 安全读取和块级解析，接入现有 v1/v2”（`docs/sdd/plans/018/task-04-backend-document-inspection-api.md:21-28`），但没有指定 Markdown 的输入 DTO、行号保留、chunker page 兼容、索引 citation 文案或空值迁移策略。

**风险：**

直接把 Markdown 伪装成 page=0 会产生错误的页码引用；直接传 `None` 会在现有 DTO、排序、引用和测试中产生契约错误。按“Markdown page null”实现会使同一 Qdrant collection 的检索结果无法用现有 `Hit`/prompt 安全展示。

**必须修改：**

1. 在 Spec 中明确 Markdown 的规范：允许扩展名（`.md`/`.markdown`）、MIME/UTF-8 BOM/NUL/CRLF 规则、1-based 行号、块切分（标题、段落、列表、表格、代码围栏、HTML block）和 heading path；固定 v1/v2 对 Markdown 的行为。
2. 冻结 media-specific locator/citation DTO，不能把 Markdown 转成伪页：要么扩展 `Chunk/Hit` 为 `page: int | None` 并让 prompt/citation 使用“行 X–Y/无页码”，要么定义独立但兼容的文档位置字段；同时保证 PDF 既有问答引用不回归。
3. 规定 Markdown 索引 payload 的 `page/page_end` 为空时，检索过滤、RRF、reranker、引用排序和前端展示的每个行为；补齐无页码、长行、空文档、表格/代码块边界测试。
4. 上传必须流式/分块限制大小，先验证编码和安全 parser，再一次性原子写原件和元数据；不得沿用 `routes_kb.py:112` 的整文件读入后只检查前四个字节的 PDF 逻辑。

### P0-4：Manifest 原子性、并发、重建竞态和删除补偿未闭环

**证据：**

- Spec 只写“按 `document_id/chunker` 独立原子写入”（`:81-95`），没有 manifest 目录布局、临时文件命名、替换/锁协议、版本冲突处理或恢复扫描。
- 当前 `save_papers` 是同进程 RLock 下直接 `write_text`（`store.py:101-108`）；`tasks._running` 是内存字典，去重逻辑在 `tasks.py:27-62`，服务多 worker/进程时并不共享。
- 启动恢复目前只处理索引 `indexing`（`main.py:18-46`、`tasks.py:139-145`）；没有 `building` manifest 的恢复逻辑。
- `routes_kb._submit_index_task` 先无条件把状态写成 `indexing` 再调用去重（`backend/app/api/routes_kb.py:135-147`）；reindex 对多个并发请求只返回 `submitted: false`，不是 Spec 声明的 409（`:150-166`）。
- 删除先删除元数据/原件，再尝试删 Qdrant；Qdrant 失败时仍 200，只返回 `vectors_removed=false`（`routes_kb.py:169-178`）。这与 Spec “删除原件、元数据、向量和检查清单”及原件丢失时“保留 Qdrant 证据”（`:147-158`）没有明确的状态机。

**风险：**

两个 worker 或重启期间可能重复构建；构建读取 payload 的同时 reindex 可生成“原件 hash 对、index fingerprint 旧/新不一致”的清单；直接保存 JSON 会留下半截文件；删除失败会遗留可检索但无元数据的 Qdrant 点，或先丢元数据后无法诊断。当前 `progress` 更新也没有单调比较，只做 0–100 截断（`store.py:281-318`）。

**必须修改：**

1. 冻结 manifest 物理布局，例如 `manifests/<validated-document-id>/<chunker>.json`，定义 lock/claim 文件、临时文件同目录 `fsync + os.replace`、残留临时文件清理、schema 校验和 fail-closed 读取。元数据迁移也应采用同等原子协议。
2. 用持久化 claim 或明确的单进程部署约束实现 `(document_id, chunker)` 互斥；如果保留单进程约束，Spec 必须写入部署/多 worker 禁止条件并测试多请求；否则使用跨进程文件锁/SQLite/原子 create-excl。进度更新要 `max(old, new)`，防止回退。
3. Manifest builder 必须在读取原件前后重新 hash，并在读取 Qdrant 前后复核 fingerprint；任一变化丢弃结果并重试/返回稳定冲突，不得保存混合快照。索引状态不是 fingerprint 的替代品。
4. 为 `building` 增加启动恢复：记录 owner/started_at/attempt；重启将其变为可重试 `pending`，清理过期 claim，不把仍有效的 ready manifest 擦掉。
5. 冻结删除状态机和错误码：成功必须能证明元数据、原件、manifest、Qdrant 均已处理；Qdrant 暂时不可用时保留 tombstone/待清理状态并返回可重试失败，不能只返回 200 + 布尔字段。原件丢失时仍应允许受控地清理向量/manifest或明确保留理由。

### P0-5：核心 API 状态码和错误体不足以实现客户端

**证据：**

- Spec 端点表只有文字状态（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:97-108`），没有稳定 `error_code`、响应字段、`Location/Retry-After/ETag/Content-Range`、分页/上限或重试规则。
- 当前路由使用自由文本 `detail`，如 PDF 校验错误（`routes_kb.py:107-119`）、文档不存在（`:157-162`）、删除失败降级（`:169-178`）；reindex 不会把重复执行映射为 409（`:164-166`）。
- `GET inspection` 一方面要求缺失时自动提交并返回 202，另一方面又要求“未完成索引 409”（Spec `:104`），没有定义 pending/building/indexing/fail/partial 的优先级和返回体。

**必须修改：**

冻结每个端点的 JSON schema 与稳定错误码，至少包括：

| 场景 | 建议稳定码/HTTP | 必须明确的行为 |
|---|---|---|
| 非法 chunker / 扩展名 / MIME / UTF-8 / 超限 | `INVALID_CHUNKER` / `UNSUPPORTED_MEDIA_TYPE` / `INVALID_ENCODING` / `PAYLOAD_TOO_LARGE`，400/415/413 | 不写原件、不写元数据、不提交任务 |
| 伪 PDF、加密/损坏 PDF、无文本层 | `INVALID_PDF` / `PDF_ENCRYPTED` / `PDF_NO_TEXT`，400 或受控 200 partial | 不泄漏 PyMuPDF 异常/绝对路径；是否保留文档记录要固定 |
| 文档/原件不存在 | `DOCUMENT_NOT_FOUND` / `SOURCE_NOT_FOUND`，404 | 不触发构建或删除其他文档 |
| 索引未完成/失败 | `INDEX_NOT_READY` / `INDEX_FAILED`，409 | inspection 不生成假清单，返回 chunker 状态/进度/重试信息 |
| manifest 正在构建/重复 reindex | `INSPECTION_BUILDING` / `INDEX_ALREADY_RUNNING`，202 或 409 | 返回 `Location`、`Retry-After`、任务标识和幂等语义 |
| Range 非法/越界/多 Range 不支持 | `INVALID_RANGE`，416 | 返回 `Accept-Ranges`、正确 `Content-Range`，定义 200/206/416 和 HEAD/缓存行为 |
| 原件 hash/index fingerprint 变化 | `SNAPSHOT_CONFLICT`，409/202 | 丢弃过期派生物，不能覆盖 ready 清单 |
| 清单损坏/过期/构建器不可用 | `MANIFEST_REBUILDING` / `MANIFEST_FAILED`，202/503 | 错误摘要脱敏，客户端可判断重试/人工处理 |

另需定义 `GET /documents` 摘要字段和大小上限、`inspection` 是否分页（不能“完整清单”与大文档虚拟化同时只给一个无限 JSON）、以及删除部分成功时的可观察状态。

## 数据模型与映射协议缺口

1. `SourceAnchor.chunk_index` 没有显式 `chunker`，虽 manifest 有版本字段，独立对象/缓存/前端事件仍可能把 v1/v2 同 index 混用；建议改为 `(chunker, chunk_index)` 或稳定 `chunk_id`。
2. `is_primary` 的约束互相矛盾：一方面“一个切片至少有一个主锚点”，另一方面又允许无法映射时没有锚点（Spec `:71-79`）。应明确 unmapped chunk 的 `is_primary=false`、`unmapped_reason` 和主锚点选择的 deterministic tie-break。
3. `coverage` 未定义分母、重复 overlap 如何计数、Unicode/空白/连字符如何归一化、重复段落如何消歧；没有这些规则，`ready/partial` 不可复现。应冻结 NFC、换行/空白/连字符策略、单调序列对齐、重复文本 tie-break 和 coverage 公式，并将算法版本写入 manifest。
4. `mapping_algorithm_version` 只覆盖映射算法；normalize 版本、Markdown parser 版本、PDF extraction/provenance 版本、chunker 参数和 Qdrant payload schema 改变也必须使 manifest 失效。建议增加 `source_parser_version`、`chunker_config_fingerprint`、`payload_schema_version`。
5. `source_sha256` 在旧文档上只能从当前文件计算。现有记录没有索引时的源 hash（`store.py:46-68`），不能把迁移后第一次 hash 误称为“历史索引对应 hash”；需在模型中区分 `current_source_sha256` 和 `indexed_source_sha256` 或明确 legacy unknown。
6. Manifest 同时保存全部 SourceBlock 文本、全部 ChunkSnapshot 文本和 anchors，50MB Markdown/PDF 可能产生数十 MB 到数百 MB JSON。必须定义每文档最大字节、页数、block/chunk/anchor 数、构建超时和响应分页/分段协议；“右侧虚拟化”不能解决后端一次返回无限清单。

## Qdrant、并发和性能风险

- `upsert_chunks` 在 `index.py:115-150` 持有 `_write_lock` 时执行 `embed_texts`（`:118-120`），这是长时间外部调用；新检查器不能复用这种持锁范围来做 manifest 构建或扩大锁范围。应维持“计算/scroll/对齐在锁外，短写入在锁内”的顺序，并在 Spec 写出锁顺序。
- Qdrant 本地文件模式的单例与写锁（`index.py:43-58,101-149`）是进程内约束；多个 Uvicorn worker 会各自打开本地 Qdrant。Spec 要么明确只能单进程部署，要么改为跨进程协调并补部署验证。
- `scroll` 读取真实 payload 必须分页、固定 `with_payload` 字段、按 `chunk_index` 排序、检查 duplicate/gap，并限制总 chunk 数与单次内存；不能按 UUID 迭代顺序直接生成 manifest。
- 读取 fingerprint 与 reindex 的删除/upsert 之间存在竞态；必须以 hash + fingerprint 双重检查保护原子保存，否则第 115 步“读真实切片”可能存成过期快照。
- 50MB 上限来自 `backend/app/platform/config.py:49-94`（默认 `KB_MAX_UPLOAD_MB=50`），当前路由 `routes_kb.py:112-116` 先整文件读入内存。新上传需检查 Content-Length 与流式累计字节，避免恶意 chunked 请求绕过内存预算；大文档验收要记录实际峰值内存/耗时，而不是只验证前端虚拟列表。
- `index.py:260-360` 的 v2 LLM/embedding 任务和 `tasks.py:21-22` 单 worker 可以复用，但 manifest 构建应明确不触发 embedding、不启动第二个队列、不与正在 reindex 的版本并行保存。

## PDF.js、Marked、DOMPurify 与安全边界

### PDF.js

当前仓库只有 `frontend/vendor/marked.min.js` 和 `purify.min.js`，没有 PDF.js（Task 05 也明确“尚无 PDF.js”：`docs/sdd/plans/018/task-05-frontend-chunk-inspector.md:10-19`）。在允许实现前需冻结：具体版本、许可证/NOTICE、display API 入口、worker 本地路径与资源版本号。必须明确 `getDocument` 配置和验收：不启用 PDF JavaScript/XFA/表单交互/annotation 或附件加载，不请求外部 URL，只从同源 source endpoint 读取；worker 与主库版本必须一致，Range/取消/损坏响应要有错误态。不能用 iframe/浏览器原生 PDF 页跳转冒充块级联动。

### Markdown

- 现有安全链路在 `frontend/app.js:1392-1412` 是“Marked 生成 HTML → DOMPurify sanitize → innerHTML”，可作为唯一渲染入口；禁止从原文拼接未净化 HTML。
- 当前净化配置明确禁止 `img` 等标签（`:1398-1401`），因此 Spec 要求“相对/远程图片显示占位和原地址”（Spec `:147-150`）需要一个安全的、文本化的 placeholder 规则，不能把原 URL 直接恢复成 HTML 属性。
- 为 block 绑定 `block_id` 时，应按后端 block DTO 分块调用同一净化函数，或在 DOM 节点上用安全属性绑定；不能对原始 Markdown 做正则包裹后再 `innerHTML`。代码块、表格、列表续行和恶意 HTML block 必须保持可渲染/不可执行的契约。
- Marked/DOMPurify 缺失时现有 `escapeHtml` fallback 是安全的（`:1394-1396`），但返回的是 HTML 字符串；检查器必须确保最终仍只写入该转义结果，并显示缺库状态，而不是把原文直接写入 `innerHTML`。

### 文件与错误信息

- `store.resolve_paper_path` 仅校验 `stored_name` basename（`backend/app/knowledge_base/infrastructure/store.py:132-158`），legacy fallback 直接拼 `paper_id`；新 document ID 和 manifest 路径必须做格式校验和 root containment，不能依赖“正常记录一定是 UUID”。
- 索引异常字符串可能原样持久化（`backend/app/knowledge_base/infrastructure/index.py:294-300,319-345`），新 `InspectionManifest.error` 明确要求无绝对路径/敏感信息（Spec `:88-93`），须采用稳定码 + 脱敏摘要，不把第三方异常直接下发。

## 复用边界与现有调用方

- `backend/app/knowledge_base/application.py:1-15` 声明 API/其他上下文只能依赖 application，但 `routes_kb.py:14-38` 直接从 application 导入大量 infrastructure re-export；新能力应新增受控 application 方法，不能让路由继续拼装 store/index/tasks。
- `KnowledgeBasePaperImportAdapter` 当前只处理 PDF、调用 v1 同步索引并在失败时清理（`application.py:170-247,249-339`）。论文发现导入必须保留同一 `document_id`、元数据身份去重和失败补偿，且必须写 `media_type/source_sha256/stored_name`；不能让论文发现另写一份 Document 或直接操作 store。
- 现有前端仍只读 `/api/kb/papers`、`paper_id`、PDF 上传和页码状态（`frontend/app.js:1505-1634,1661-1682`；`frontend/index.html:80-117`）。Spec 要迁移旧 `/api/kb/papers*` 调用方/测试到 `/api/kb/documents*`（`:97-108`），需要在 Task 03/04 明确全仓调用方清单、一次性迁移顺序、旧 ID 兼容和回归矩阵；不能让 Task 05 单独改前端而后端契约仍在漂移。
- `frontend/index.html:7,248-250` 有静态资源 query 版本，当前只加载 styles、DOMPurify、Marked；Task 05 必须把 PDF.js 主库和 worker 的固定版本、许可证与 `?v=` 同步纳入契约测试。

## 任务拆分、模型与上下文预算

### 当前计划不可直接执行

1. **Task 02 产物缺路径。** `docs/sdd/plans/018/task-02-validate-source-anchor-feasibility.md:63-69` 只写“固定样本、可执行验证、结论”，没有固定落盘文件名；Task 03 只依赖“02 Go”（`:3-4,16-20`）。必须指定报告路径、字段、hash 和 Go/No-Go 门槛，供下游只读交接。
2. **Task 02 与 Gate 3 存在顺序风险。** 它依赖“Spec 已确认”，但其 No-Go 会否定核心数据模型；应把 feasibility spike 作为确认后的第一道硬闸，并在 Spec 中写明 No-Go 自动退回 `待确认`、不进入 Task 03，或先把目标降级为无 bbox 的 `partial` 检查器。
3. **Task 03 混合了协议、迁移、应用边界、CONTEXT 和 ADR**（`task-03...:21-33`），修改范围和回滚边界不够小；应拆成文档协议/迁移（文档）与后端模型/application（代码）两个可审查子任务，明确各自产物。
4. **Task 04 明显超过本地 27B 分派粒度。** 它同时做 Markdown parser、Qdrant scroll/fingerprint、bbox/anchors、manifest store、并发恢复、五类 API、旧路由迁移（`task-04...:21-33`），固定 prompt 还要求一次完成全部内容（`:35-39`）。按 AGENTS.md 门禁，使用本地模型时涉及 ≥3 个代码文件必须拆成每任务 ≤2 个代码文件、改动 ≤150 行；应至少拆为迁移/application、manifest store、source/chunk mapping、routes/schemas/tests，并在每步冻结 API。
5. **Task 05 也超过本地分派粒度。** 它同时修改 `index.html/app.js/styles.css`、引入 PDF.js/worker/许可证、做双栏布局和联动测试（`task-05...:21-33`），需按 DOM skeleton、PDF/Markdown renderer、interaction/state、CSS/contract tests 拆成 ≤2 文件子任务；Vendored PDF.js 还应作为独立依赖审查。
6. **Task 06/07 缺少中间契约。** Task 05 依赖“Task 04 API 契约与后端测试通过”（`task-05...:16-19`），但没有命名的冻结 schema/fixture；Task 06/07 只依赖执行结果，无法保证跨 agent 只读交接。应落盘 API schema、fixture manifest、单端报告路径和性能基线。

### 执行配置问题

- Spec 执行配置把“后端开发 / 评审”“前端开发 / 评审”各合成一行（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:191-202`），没有独立 Tech Lead 行；这不满足 AGENTS.md/SDD-GATE-CHECKLIST 对开发主管评审者、模型、上下文和产出的审计要求。
- 当前 32k 上下文可以支撑一个 ≤2 文件的 backend/frontend 子任务，但不足以让 Tech Lead 一次性读完整 Spec、Task 02–07、后端迁移/并发代码、前端 DOM/安全契约并给出全局结论。建议 Tech Lead 使用 64k–128k，代码 agent 仍按 32k 最小上下文分派；每个 task prompt 只带冻结契约、证据路径和当前两文件。
- Task 02 计划将架构师与 backend-tester 混合，Task 07 又要求 backend-reviewer/frontend-reviewer/tester；应在 Spec 执行配置中逐角色列出模型、上下文、报告路径和失败重试规则。当前本轮技术评审使用的 `gpt-5.6-luna xhigh` 不应被写回为其他角色的永久模型名。

## 复评前必须补齐的强制约束（清单）

1. 落盘 Task 02 feasibility report（含 PDF bbox/双栏/旋转/重复文本/Markdown/真实 payload 证据）；No-Go 自动停在 Spec/Task 02。
2. 冻结 source extraction/provenance DTO、normalize/parser/version、坐标变换和映射算法；定义 `coverage`、主锚点、unmapped reason 和重复文本 tie-break。
3. 冻结 `document_id`/legacy `paper_id`、Qdrant payload 更新与兼容读取、point/chunk/index fingerprint canonicalization；证明旧 points 零 embedding 且数量/ID/向量不变。
4. 写 versioned、fail-closed、可恢复、幂等的 JSON migration；损坏 JSON 不得按空列表覆盖，旧 naive 时间必须有显式解释。
5. 冻结 Markdown parser、line/block DTO、page-null 的 index/retrieve/prompt/citation 契约及错误/状态语义。
6. 冻结 manifest 目录、临时文件 + fsync + replace、claim/lock、reboot recovery、hash/fingerprint 双重检查、单调进度和删除 tombstone/重试协议。
7. 给所有 endpoint 加稳定 schema/error code、202/409/404/416/413/415/503 规则、Range headers、ETag/缓存和 `Retry-After/Location`。
8. 定义文档、block、chunk、anchor、manifest 的容量/超时/分页上限，并验证 50MB 级 Markdown/PDF 的峰值内存和响应大小。
9. 固定 vendored PDF.js 版本、许可证、worker、display-only 安全配置；禁止 annotation/XFA/JS/附件/远程资源，补损坏/Range/取消测试。
10. 将 Markdown 图片安全占位与 block_id 绑定设计落在 Marked + DOMPurify 唯一入口，禁止正则包裹原文和未净化 `innerHTML`。
11. 为 Task 02–07 补命名产物、API schema/fixtures 和 ≤2 文件/≤150 行的本地 27B 子任务拆分；Tech Lead 单独加入执行配置并提高上下文预算。
12. 对论文发现导入、旧前端/测试、问答引用、reindex/delete 和 application-only 依赖做全仓迁移清单，保证不出现第二套索引流程。

## 签字

- 开发主管（Tech Lead）：当前协作 Agent，签字：**打回，暂不通过**
- 签字时间：2026-09-08 19:54 +0800

## 修订轮：仍不通过（2026-09-08 20:02，Asia/Shanghai）

本轮仅复核当前 Spec、计划索引 README 与本评审文档；未读取全项目、未修改业务代码，也未执行会改变项目状态的命令。需求评审修订轮已补齐产品旅程和多项验收观测，但首轮要求的实现前技术闭环仍未全部落盘，保留以下 P0，不能进入用户确认后的实现阶段：

### P0-1：Task 02 的 Go/No-Go 仍没有可交接的命名产物，且 PDF provenance/坐标协议未冻结

- Spec 只声明固定样本与 `*.expected.json` 应归档（Spec `:188-195`），Plan README 只要求 Task 02 给出 Go/No-Go（README `:27-30`），没有报告的固定路径、字段、样本/输入 hash、判定阈值及 No-Go 后自动退回 `待确认` 的状态动作。
- `SourceBlock` 仅冻结了相对 bbox 与文本块级 locator（Spec `:48-81`），没有首轮要求的 page width/height/rotation、原始 block/line/word provenance、阅读顺序、规范化文本到原始字符区间，以及 PDF.js viewport/canvas/text-layer/overlay 的旋转与缩放转换协议。

因此固定 fixture 的文字描述和 no-embedding 观测不能证明核心 bbox 映射可实现；Task 03 仍可能在 Go/No-Go 结论前被错误启动。

### P0-2：`paper_id → document_id` 的无损迁移和旧 Qdrant point 兼容仍未闭环

- Spec 明确 `document_id == paper_id`（Spec `:33-46,196-197`），但未冻结旧 payload 的读取兼容、一次性 payload 更新/别名策略、旧 point 缺字段/重复/缺号的诊断，或“只改 payload、不改向量和 point ID”的迁移协议。
- 旧 JSON 的 versioned、fail-closed、备份/恢复、损坏拒写和原子迁移协议未写入；`source_sha256` 也未区分当前原件 hash 与历史索引 hash unknown。验收写了重复迁移与 hash 观测（Spec `:194-197`），但观测项不能替代迁移状态机与兼容读取契约。

没有上述协议，inspection 仍可能按新字段读不到旧切片，或在损坏元数据时把真实记录当空列表覆盖。

### P0-3：Markdown 索引/引用/上传契约仍不足以实现

- Spec 允许 Markdown 的 `page/page_end` 为 null（Spec `:59-69`），但没有冻结 `.md/.markdown`、MIME/BOM/NUL/CRLF、块边界与 heading path、v1/v2 对 Markdown 的行为，以及 page-null 在检索过滤、RRF、reranker、prompt/citation、排序和前端显示中的完整契约。
- 上传契约仅写“校验大小/编码并返回稳定 400”（Spec `:106,117`），没有流式/分块限额与原件/元数据一次性原子提交规则。

仅有 Markdown hostile fixture 与净化验收，不能消除现有 `Chunk/Hit` 整数页码契约冲突，也不能防止 chunked 上传绕过内存预算。

### P0-4：Manifest 原子并发、恢复、竞态和删除补偿没有冻结

- Spec 仅写临时文件+原子替换、任务键 `(document_id, chunker)`（Spec `:83-99,128`），没有 manifest 物理布局、同目录 `fsync + replace`、持久 claim/跨进程锁、owner/started_at/attempt、残留临时文件清理和 fail-closed schema 读取。
- 没有规定原件读取前后 hash、Qdrant scroll 前后 fingerprint 的双重检查，`progress=max(old,new)`，服务重启将 `building` 恢复为可重试 `pending`，或删除时 Qdrant 失败的 tombstone/重试状态机。

验收中的“两并发打开/重启重试/point 不变”是测试目标，不是实现协议；当前文档仍不足以保证不会保存混合快照或留下不可诊断的孤儿向量。

### P0-5：API 错误体、缓存/重试及容量边界仍不完整

- Spec 只给出少量示例（如 `chunker_not_ready`）和 Range 的主要 headers（Spec `:114-120,199`），未为所有端点冻结稳定错误码、JSON schema、`Location`、`Retry-After`、`ETag`/缓存、HEAD 行为、202/409/503 优先级和删除部分成功的可观察状态。
- 仍未定义 document/block/chunk/anchor/manifest 的数量/字节/超时上限，或 inspection 大清单的分页/分段响应；“前端虚拟化”不能解决后端返回无限完整 JSON 的问题。

客户端无法据此可靠区分构建中、未索引、快照冲突、manifest 损坏和服务暂不可用，也无法在大文档上建立可执行的内存/响应边界。

### P0-6：PDF.js/Markdown 安全实现仍缺少可审计的依赖与绑定协议

- Spec 只要求本地 vendored PDF.js、公开 display API 和无远程请求（Spec `:129,200`），没有具体 PDF.js 版本、许可证/NOTICE、主库与 worker 路径/版本、`getDocument` 的 display-only 配置和取消/损坏错误契约。
- Markdown 只声明复用 Marked + DOMPurify、图片不请求、缺库转义降级（Spec `:130,163,201`），没有冻结按 block DTO 绑定 `block_id` 的唯一安全渲染入口、文本化图片占位规则，以及禁止正则包裹原文/未净化 `innerHTML` 的实现契约。

hostile fixture 的验收断言尚不能替代上述依赖版本和 DOM 绑定规范，前端实现仍有引入 iframe、原生 PDF 页跳转或未净化块包装的歧义。

### P0-7：Task 02–05 的细粒度拆分和中间产物未在可交接计划中冻结

- Spec 的任务表仍是每项一个大任务（Spec `:236-244`），Plan README 仅列任务目标/依赖/状态和全局门禁（README `:6-31`），没有 Task 02 feasibility 报告、Task 03 迁移/协议报告、Task 04 API schema/fixture、Task 05 DOM/PDF.js 契约与单端报告的固定路径、输入输出字段和验收门槛。
- Spec 执行配置仍把“后端开发 / 评审”和“前端开发 / 评审”合并为两行、均为 32k，未单列 Tech Lead；也没有落实首轮要求的每个本地 27B 子任务最多两份代码文件/约 150 行及每步冻结 API 的拆分。

在没有命名中间契约和可审计拆分前，下游 Agent 不能只读交接，Task 04/05 仍会同时承担多模块迁移、并发、渲染和测试，无法满足项目门禁。

### 复审结论

**修订轮：打回，暂不通过。** 需先补齐上述 P0 并更新 Spec/Plan 的对应产物路径与状态门禁，再重新提交技术评审；在此之前不得将 Spec 改为 `已确认`、运行 Task 02 或修改业务代码。

## 最终复审：通过（2026-09-08 20:29，Asia/Shanghai）

本轮仅只读核对当前 Spec 018、Plan README、Task 02–05 计划和本评审文档；未修改业务代码、未运行 Task/测试/服务。针对 P0-1～P0-7 的证据如下：

1. **P0-1 通过**：Spec 技术冻结协议（`:135-141`）和 Task 02 A/B/C/D 表（`:36-53`）固定 `source-anchor-feasibility-report.md`、`fixture-index.json`、`provenance-dto.schema.json`、fixture 根目录、逐样本 hash/命令/退出码/映射统计、bbox ≤0.005、Markdown 行号 100%、no-embedding/no-write 观测及 `GO|NO-GO`；No-Go 自动将 Spec 保持/退回 `待确认` 并停止 Task 03–07。PDF provenance、rotation、阅读顺序、原始字符区间及 PDF.js viewport overlay 也已冻结。
2. **P0-2 通过**：Spec（`:143-149`）和 Task 03（`:35-46`）固定 `paper_id == document_id`、旧 payload 双读/别名、一次 payload-only 更新、point/vector/UUID/fingerprint 不变、缺字段/重复/缺号诊断、`018-document-v1` JSON 迁移、备份与 `fsync + os.replace`、损坏输入 fail-closed 及 `legacy_unknown` hash 语义。
3. **P0-3 通过**：Spec（`:151-157,214-217`）和 Task 04（`:50-64`）冻结 `.md/.markdown`、MIME/BOM/NUL/UTF-8/CRLF、流式 50 MiB、block/line DTO、v1/v2 真实 payload、`page/page_end=null` 在检索/RRF/reranker/prompt/citation/UI 的行为、错误码、数量/超时和失败不得留下半截原件/metadata/task 的契约。
4. **P0-4 通过**：Spec（`:159-164`）和 Task 04 manifest 子任务（`:41-44`）固定 manifest/claim/tmp 物理布局、原子 claim、owner/attempt/recovery、schema fail-closed、`fsync + os.replace`、原件 hash/Qdrant fingerprint 前后双检、单调进度和删除 tombstone/`DELETE_PENDING` 重试状态机。
5. **P0-5 通过**：Spec 公开 API schema v1（`:174-202,214-217`）和 Task 04（`:48-67`）逐端点固定成功体、统一错误体与稳定 code，覆盖 202/409/404/416/413/415/503 优先级、`Location`、`Retry-After`、ETag、HEAD、Content-Range、304、cursor/limit/page_size 以及 document/block/chunk/anchor/manifest 数量/字节/超时/分页上限。
6. **P0-6 通过**：Spec（`:204-221`）和 Task 05（`:35-57`）固定 vendored `pdfjs-dist 4.10.38`、主库/worker/`LICENSE`/`NOTICE` 路径与 hash、workerSrc、display-only `getDocument` 配置、禁止 CDN/iframe/脚本/annotation/XFA/form/attachment/远程 URL；Markdown 唯一入口为 `SourceBlock → renderMarkdownBlock → Marked → DOMPurify → block container`，图片只用 textContent placeholder，缺库降级为 `RENDERER_UNAVAILABLE`。
7. **P0-7 通过**：Spec 执行配置（`:327-343`）单列 Tech Lead，单步交接最低 64k、最终 Gate 128k；Spec/README 的交接矩阵（Spec `:345-363`、README `:41-57`）及 Task 02–05 各自表格固定 A/B/C/D 边界、每个本地 27B 最多 2 个代码/资源文件、约 150 行、固定 artifacts、API/fixture/PDF.js/DOM 产物、backend/frontend 单端报告和逐项放行门槛。缺证据保持 `待执行/阻塞`，不得依赖聊天摘要。

**结论：最终复审通过。** P0-1～P0-7 均已有明确协议、固定路径、可审计交接物和阻塞/放行动作；Spec 仍保持 `待确认`，须待用户明确确认后方可进入实现门禁。复审日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260908-202847.md`。

- 开发主管（Tech Lead）：当前协作 Agent，签字：**最终复审通过**
- 签字时间：2026-09-08 20:29 +0800

## 自动重建修订待重新技术评审（2026-09-08）

首轮 Task02 `NO-GO` 后，Spec 新增生产级 PDF block provenance、Markdown parser、provenance-aware v1/v2、`LegacyInspectionUpgrade`、完整 point/payload/dense+sparse vector 快照、预计算后原地替换、跨版本失败恢复、成功删快照、首次失败后仅手动重试，并把 hostile PDF 的真实浏览器零网络硬门移交 Task05。

这些变化会修改上一版 P0-1、P0-2、P0-4、P0-5 和 no-embedding 假设，因此上一版“最终复审通过”只作为历史结论保留，**不覆盖当前修订**。当前技术评审状态为：`待评审（未执行）`。重新评审必须验证：

1. Task02A/02B 的顺序消除了“未实现前要求实现证据”的循环门禁。
2. 恢复快照能完整保存并恢复 dense/sparse vector，且不进入 Git、API 或敏感日志。
3. v1/v2 文档级事务、进程中断恢复、短写入窗口和仅手动重试状态机无歧义。
4. 新索引 inspection 的 no-embedding 路径与旧索引唯一 upgrade 路径严格分离。
5. Task05 明确承接 hostile PDF/Markdown 的真实浏览器网络硬门。

重新评审通过前不得执行 Task02A 或修改业务代码。

## 自动重建修订独立技术复审：打回（2026-09-08 22:25，Asia/Shanghai）

本轮只读核对了架构师角色规则、当前 Spec 018、Plan README、Task02A/02B、Task03–07、首轮 Task02 `NO-GO` 报告、上一版技术评审，以及现有 `parse/chunker/index/retrieve/tasks` 接口；未修改业务代码、未运行 Task/测试/服务。结论只能为 `GO|NO-GO`，本轮为 **`NO-GO`（打回）**。

### 已核对并成立的修订条款

1. Spec `:152-159` 已把 `PdfSourceProvenanceV1`、block 级 bbox、rotation/crop box、阅读顺序和 PDF.js public viewport 映射固定下来；Task02A `:23-29,80-94` 与 Task02B `:22-28,42-46,69-80` 已禁止测试专用 parser、保留 v1/v2 多对多关系，并把 hostile 浏览器零网络门移交 Task05。
2. Spec `:169-177`、Task02A `:28-29,48,80-94`、Task02B `:42-46,69-80` 已声明预计算后短写、v1/v2 全量恢复、dense/sparse 快照、升级期排除 RAG、成功删除快照和首次失败仅手动 retry；首轮证据仍为只读 `NO-GO`。
3. Task02A→02B 的名义依赖是单向的（02B 只读消费 02A 产物），且 Task02B `:24-28` 明确浏览器门留给 Task05，未发现形式上的反向依赖。

### P0 阻塞项（必须先补最小交接契约）

1. **升级期 RAG 排除没有绑定到现有召回入口。** 现有 `backend/app/knowledge_base/infrastructure/retrieve.py:125-184` 的 `hybrid_search` 只按 `paper_id/chunker` 过滤，dense 与 sparse 两路均未读取 `LegacyInspectionUpgrade` 状态；`backend/app/api/routes_kb.py:199-213` 直接调用该入口。Task02A 仅在 `:80-88` 将“普通 RAG 排除”列为验收目标，Task02B 的 FakeQdrant Prompt `:42-46` 也没有要求验证升级中两路召回均排除文档。最小修订：在 `artifacts/task-02a/implementation-contract.md` 冻结唯一 `document_id/operation_id → upgrade_active` 读取点、application/retrieve 过滤入口和两路 query 的观测字段；02A-D/02B-C 必须加入 `running/validating/restoring` 下 dense+sparse 均为零命中、恢复/完成后恢复可召回的 fixture 与退出码，否则不能宣称“升级中排除”已可实现。

2. **文档级 v1/v2 原子升级与现有按版本队列之间缺少可执行桥接。** 现有 `backend/app/knowledge_base/infrastructure/tasks.py:27-62` 以 `(paper_id,chunker)` 各自去重，`main.py:18-39` 启动时只把残留 `indexing` 标为失败；而 Spec `:171-175` 要求全部已有 v1/v2 共用一个持久 claim/`operation_id`、跨版本事务、删除后中断先恢复旧 points。Task02A `:31-39,48,52` 只描述“文档级升级”结果，未在固定交接物中冻结：谁创建/持久化 operation、如何跨两个 chunker 绑定同一 claim、启动恢复如何替换现有 `mark_interrupted_on_startup`、以及升级状态如何被 application/retrieve 读取。最小修订：02A-D 的 `implementation-contract.md` 增加 operation/claim/recovery 状态机和生产入口签名（含文件白名单），02B-C 以两个已有版本并发、delete 后进程中断、重启 restore 的 FakeQdrant 证据逐项核验；缺失即保持 `NO-GO`。

3. **恢复快照虽声明“完整”，但机器可校验 schema 尚未冻结。** Spec `:124,171-174` 只列出 point ID、payload、dense/sparse vector 和 chunker state；Task02A `:38` 与 README `:55` 仅命名 `reindex-snapshot.schema.json`，没有冻结 snapshot schema/version、全量 v1/v2 point 集、dense 维度与数值编码、sparse indices/values 的排序与空值、payload canonicalization、每点/整体 fingerprint、source hash、写入完成标记和截断/损坏 fail-closed 规则。仅凭报告中的“vector fingerprint”无法证明恢复的是完整可重放快照。最小修订：在 02A 固定产物中逐字段定义 schema 与 canonical round-trip oracle；02B 必须记录删除前后每个版本的 point ID/payload/dense/sparse 原值、维度/长度、fingerprint，并验证快照损坏、短写和恢复幂等；快照仍不得进入 API、日志或 Git。

4. **Task02A 要求生成 manifest，但正式 manifest 协议被延后到 Task03，形成交接缺口。** Task02A `:27-29,35-39` 要求新文档索引“同时生成 manifest”，而 Task03 `:21-27,35-46` 才定义 `InspectionManifest` schema/迁移，README `:57-59` 也把正式 manifest schema 固定在 Task03。Task02B 只能验证 provenance/chunk/anchor，无法验证 02A 产出的 manifest 是否符合下游唯一 schema；这会迫使 02A 私自定义临时 schema，或让 Task03 反向修改已通过的 02A 产物。最小修订二选一并写入交接表：要么 02A 只产出 provenance/chunk relation、明确 manifest 延至 Task03；要么在 02A 之前冻结最小 `InspectionManifest` schema/version 与 expected fixture，并让 02B 只读消费它。未选择前不得执行 02A。

### 结论与放行动作

当前文档已覆盖 provenance、Markdown v1/v2 复用、预计算/恢复意图、hostile Task05 移交和首次失败手动重试，但上述四项是与现有生产入口直接相关的 P0 交接缺口，不是实现后可接受的风险。Spec 018 继续保持 `待确认`；不得执行 Task02A、Task02B 或 Task03–07。完成最小契约修订、补齐固定 schema/fixture/报告字段后，重新提交独立技术评审。

复审证据日志：`.codebuddy/agent-logs/spec-018/task-01/architect/20260908-220742.md`。

## 自动重建修订 P0 补丁独立技术复审：通过（2026-09-08 22:27，Asia/Shanghai）

本轮只读核对了当前 Spec 018、Plan README、Task02A/02B/03 与真实 `application/retrieve/tasks/main` 入口；未修改业务代码、未运行 Task/测试/服务。针对上一轮四项 P0，结论为严格 **`GO`（通过）**。

### 四项 P0 证据

1. **application 检索包装与升级排除：通过。** Spec `:181-182` 固定唯一 `knowledge_base.application.hybrid_search` 包装、`LegacyUpgradeStore.get_active_document_ids()`、`excluded_paper_ids` 到 `must_not paper_id MatchAny`，以及 dense/sparse 共用同一 filter 和 RRF/reranker 零污染观测。Task02A `:37-41,50,54,66,90-92` 已指定 D3 owner、报告路径和双路命中断言；Task02B `:36,44,56,77` 已纳入正式入口/FakeQdrant 验证。真实 route 只从 application 导入 `hybrid_search`（`backend/app/api/routes_kb.py:14-39,212`）；当前 application 仍是 infrastructure re-export（`backend/app/knowledge_base/application.py:61-68`），但 D3 已明确这是待实现的唯一替换点，没有第二个 route 入口。
2. **文档级 operation、持久 claim 与启动恢复：通过。** Spec `:183-185` 固定既有单线程 `get_executor()` 上唯一 `(document_id,"legacy-upgrade")` operation、禁止按 chunker 嵌套提交、`data/kb/upgrades/<document-id>.json/.claim`、字段集合及恢复先后顺序。Task02A `:38-40,50,54,75` 和 Task02B `:36-37,44,56,76` 固定 D2 owner、联合 v1/v2、单 operation、delete 后中断 restore 和报告字段。现有 `tasks.py:27-62,65-90,139-145` 仍是旧 `(paper_id,chunker)` 队列、`main.py:35-39` 仍执行旧 interrupted 标记；这与当前 Spec `待确认/禁止改代码` 状态一致，且已被 D2/启动恢复契约明确替换边界，不构成文档评审阻塞。
3. **`reindex-snapshot-v1` 完整快照与 fail-closed：通过。** Spec `:187-192` 固定 schema/version、全量有序 points、canonical UTF-8 键排序 payload、float32 little-endian dense raw-bytes base64、uint32/float32 little-endian sparse raw-bytes base64、逐点/四类总 hash、snapshot hash、`complete`、2 GiB/磁盘余量门、损坏/截断/未知版本拒绝和恢复 round-trip。Task02A `:38,50,65,92-93`、Task02B `:44,55,75` 将 schema、报告、逐点与总 fingerprint、损坏/截断、幂等恢复绑定为放行条件；README `:55,68` 固定交接路径。满足上一轮要求的机器可校验完整性。
4. **02A→02B→03 manifest 单向交接：通过。** Spec `:194-197` 明确 02A 不生成/持久化 `InspectionManifest`，只产版本化 `SourceProvenanceBundle`；02B 只验证 bundle/升级/恢复；Task03 在 02B `GO` 后定义唯一 manifest schema，Task04 才持久化。Task02A `:29,37,41,73`、Task03 `:25,41-46`、README `:55-57,68-70` 的 artifacts、owner 和放行条件一致，已消除上一轮反向依赖。

### 结论与门禁

四项 P0 均已形成“Spec 条款 → Task owner → 固定 artifact/fixture → 观测字段 → 严格 GO/NO-GO”闭环；未发现新的技术阻塞或 02A→02B→03 循环。当前代码尚未实现新桥接，属于 Spec 仍为 `待确认` 时的预期状态，不应被误记为实现验收。

本轮通过不改变 Spec 状态：仍须用户明确确认后才能执行 Task02A；Task02B 必须取得严格 `GO` 后才可放行 Task03。复审证据日志：`.codebuddy/agent-logs/spec-018/task-01/architect/20260908-221835.md`。

## 全库索引替换修订待重新技术评审（2026-09-09）

用户已确认旧 vectors/manifest 可丢弃，当前 Spec/Plan 撤销 `LegacyUpgradeStore`、检索期 `must_not`、`reindex-snapshot-v1`、逐文档恢复和首次打开自动升级，改为：Task02A-D 只在 fixture/FakeQdrant 实现并验证候选重建服务/CLI；Task03 冻结 metadata/manifest；Task04 实现 API 与 finalize 门禁；Task06 停服执行真实候选构建、严格验证、`papers` alias 切换和 finalize。

因此以上历史技术结论只作审计记录，不覆盖当前修订。当前修订状态为：**待独立技术评审（未执行）**。复审必须核对阶段依赖、Qdrant 首次实体到 alias 的切换、全局锁、dry-run 零写、candidate cleanup、resume-switch/finalize、topology fail-closed、v1/v2+dense/sparse 完整性、metadata/manifest 提交顺序、不可变原件与真实 Task06 运行边界；通过前不得继续业务代码。

## 全库索引替换修订独立技术复审（2026-09-09 03:52，Asia/Shanghai）

### 复审范围与结论

- 模型：gpt-5.6-luna xhigh（临时，仅本轮）；角色：独立技术评审/Architect。
- 只读取本轮指定的 Spec、Plan README、Task02A/02B/03/04/05/06/07、本文最新待评审段，以及必要的 `knowledge_base` 配置、application、index、retrieve、store 和旧上传入口；未修改业务代码、Spec/Plan 或历史评审段。
- **结论：打回。** 阶段编排和“02A 固定样本/FakeQdrant、Task06 停服真实切换”的边界已经清楚，但候选写入隔离、崩溃恢复状态机、拓扑证明、跨 metadata/manifest 提交和 dry-run/锁语义仍存在会导致误写、误删或无法恢复的 P0 缺口。完成下列契约修订和 FakeQdrant 故障证据前，不得放行 Task02A-D、Task02B 或 Task03–07。

### 已核对通过的边界（非阻塞）

1. 依赖图是单向的：README `:11-17,21-26` 为 `02A→02B→03→04→05→06→07`；Task02A `:27-29` 明确只输出 `SourceProvenanceBundle`，Spec `:182-185` 明确最终 `InspectionManifest` 由 Task03/04 定义和持久化，Task06 `:25-30` 才执行真实切换。因此没有发现反向依赖循环。02A 的候选切换测试若严格限制在 FakeQdrant/临时候选，和 Task06 的真实 alias 边界也成立。
2. 首次“物理 `papers` → 同名稳定 alias”、后续 alias 原子更新、默认 dry-run、显式 `--confirm-replace`、停服运行和原件不可变的意图已经写入 Spec `:171-178`、Task02A `:46-50` 和 Task06 `:18-30,41-55`；问题在于故障窗口和生产复用入口尚未被写成可执行契约，见下列 P0。

### P0 阻塞项与具体修改建议

#### P0-1：候选写入没有与现有生产索引入口隔离，不能证明 dry-run/候选不会误写正式索引

证据：Spec `:173-175,184-185` 要求候选 Collection、v1/v2、dense+sparse 和不降级；Task02A `:46-50,63-69` 又要求 dry-run 三类写入为 0、只能 FakeQdrant/临时 Collection。现有 `backend/app/knowledge_base/infrastructure/index.py:101-149` 的 `upsert_chunks()` 没有目标 Collection 参数，直接 `ensure_collection()` 并写固定 `KB_COLLECTION`（`:119-123`），payload 仍写 `paper_id`（`:130-145`）；`index_paper_chunker()` 在 `:289-320` 更新正式 metadata/执行解析切分，并在 `:328-341` 删除固定集合旧点后 upsert，在 `:348-356` 再写 indexed 状态。现有 `retrieve.py:101-115,170-198,519-529` 也固定读取 `paper_id` 和 `KB_COLLECTION`。这组入口不能直接作为候选 builder 复用，否则即使命令声称 dry-run 或 candidate，也可能修改正式集合/元数据或产出不兼容 payload。

最小修订：在 `implementation-contract.md` 冻结唯一候选写入 port（显式 `destination_collection`、`document_id` payload、纯计算/写入分离、禁止 metadata update/delete-current-points），并规定正式索引与候选索引只能通过该 port 调用；为 dry-run、candidate 和 metadata/collection/upsert/delete/embedding 分别注入计数 spy。把 v1/v2 的 parser/chunker/embedding 配置和 `llm_used` 传入验证结果，禁止沿用 `index_paper_chunker()` 的隐式副作用。02B 必须用 FakeQdrant 证明正式 `papers`、metadata 和原件写计数为零，Task06 才能接入真实 destination。

#### P0-2：`switching`/`finalizing` 崩溃窗口没有可执行的恢复路径

证据：Spec `:117,123,176-178` 定义了 `switching`、`finalizing`、`finalize_pending`，并要求首次删除物理 `papers` 后创建 alias、失败仅 `resume-switch`；Task06 `:51-54` 却只允许 `ready_to_switch` 执行 `resume-switch`、只允许 `finalize_pending` 执行 `resume-finalize`。进程可能在 `ready_to_switch→switching` 写状态后、删除旧物理集合前后、或删除后 alias 创建前崩溃；此时状态既不是 `ready_to_switch`，又没有旧集合可恢复。后续 alias 原子更新成功后、metadata/manifest 尚未提交时同样可能停在 `finalizing`，而不是可执行的 `finalize_pending`。Task06 `:95-97` 只描述结果，没有定义这些中间状态如何安全收敛。

最小修订：冻结持久化 FSM 和每个破坏性动作的 intent/observed 记录（包括 candidate、旧物理集合、alias 目标、操作序号、拓扑摘要）；规定崩溃重启时 `switching`/`finalizing` 的允许命令、双读拓扑证明、幂等动作和转入 `INDEX_TOPOLOGY_AMBIGUOUS` 的条件。`resume-switch` 不能只接受字符串状态，必须在删除发生后仍能安全完成首次 alias 创建；`resume-finalize` 必须能从任意 finalize 子步骤重试。FakeQdrant 要注入每个动作前后中断并验证不会误删/误切换。

#### P0-3：拓扑 fail-closed 只有错误码，没有完整库存和动作矩阵

证据：Spec `:179`、Task02A `:48,67-68`、Task06 `:53-55,98` 仅规定“不明确时返回 `INDEX_TOPOLOGY_AMBIGUOUS`”，未冻结可判定的拓扑输入。至少仍需区分：`papers` 是物理 Collection 还是 alias、alias target 是否存在且唯一、alias 是否指向当前/候选、多个 `papers_rebuild_*` 候选、候选名冲突、孤立运行目录、状态与 Qdrant 目标不一致、旧集合删除后 alias 尚未创建。现有 config `backend/app/platform/config.py:49-56` 和 index `:117-123` 只提供固定 `KB_COLLECTION="papers"`，不能承担这些判断。

最小修订：冻结脱敏 topology inventory schema（物理集合、alias、目标、候选、run 状态、collection/alias hash 或版本）及每种 inventory 的命令结果矩阵：允许 dry-run、允许 build、允许 switch、允许 cleanup、必须停服/必须人工介入。所有 destructive 操作必须先以同一 inventory 和 run intent 双重校验；多个候选、未知 alias 类型、缺失 marker、候选已被其他 alias 指向均 fail-closed，不得通过“当前看起来唯一”推断。

#### P0-4：alias、metadata 与 Task04 manifest 之间没有 run-level 原子 finalize 协议

证据：Spec `:178` 要求 alias 成功后再原子提交文档状态、`indexed_source_sha256`、统计和 manifest，失败进入 `finalize_pending`；Task06 `:29,78-79,97` 同样要求 finalize 失败停服。但 Task03/04 只分别描述元数据/manifest 文件的迁移或临时文件替换（Task03 `:18-26,42-44`；Task04 `:70-76`），没有定义跨多个文件、多个文档和 alias 之间的提交 marker、完整清单 hash、恢复顺序或读门禁。现有 `backend/app/knowledge_base/infrastructure/store.py:101-108` 仍是直接 `write_text()`，若被错误复用，崩溃会留下半写 metadata；`load_papers()` `:87-98` 还把损坏/非 list 当空集合，和全局 fail-closed 相冲突。

最小修订：在 Task03/04 交接物中冻结 run-level finalize bundle：所有待提交 metadata/manifest 的路径、内容 hash、schema/version、候选 fingerprint、alias 目标和 commit marker。实现顺序必须是 staging→文件/目录 fsync→完整 bundle hash→单一 commit marker→放开 API/health 读取；marker 之前所有正常读取均拒绝或保持 `INDEX_FINALIZE_REQUIRED`，marker 缺失/不匹配必须 fail-closed。`resume-finalize` 以 bundle hash 幂等补写，确认所有新 manifest 后才能删除旧派生 manifest；旧文件不可作为成功结果返回。Task06 要注入每个文件和 marker 的故障，证明不会将 alias 已切换误报为 completed。

#### P0-5：dry-run 零写与全局 rebuild lock 的边界、生命周期和异常释放不明确

证据：Spec `:171-172` 与 Task02A `:46-50,63-68` 要求默认 dry-run、embedding/Collection/metadata write 为 0；Spec `:123` 同时要求固定写入 `state.json/events.jsonl` 和全局 lock，Task06 `:25-26,51-55` 又要求真实运行获得 lock。当前没有说明 dry-run 是否创建 runtime 目录、state/events 或 lock；也没有 owner/token、进程崩溃后的 stale lock 处理、锁释放时机、跨命令续持和“只允许一个 run”的原子获取方式。

最小修订：把写入按“Qdrant/Collection、embedding、metadata/original、candidate、run diagnostics、lock”逐项定义；若 dry-run 允许临时诊断文件，必须明确其不属于正式 runtime/metadata 且使用临时目录，否则 dry-run 对外报告所有 write counters 为 0。全局锁应采用 create-exclusive 的 owner/run/token/started_at/heartbeat 记录，异常 finally 释放；stale lock 只能在可验证进程不存在且人工确认或显式 cleanup 命令下处理，不能自动抢占。FakeQdrant/临时环境要覆盖两个 dry-run、dry-run 与 confirm 并发、异常/kill 后 lock 残留。

#### P0-6：候选清理失败和“可保留候选”的生命周期没有状态契约

证据：README `:33-36`、Spec `:174,176,179` 和 Task02A `:48,67-68` 要求失败候选清理、首次 alias 失败保留已验证候选；Task06 `:48,52-55,95-98` 只列 `--cleanup-failed`、从头重建和 `resume-switch`，没有规定删除候选本身失败、清理命令失败、已验证候选与未验证候选的状态差异，也没有规定清理失败后服务/正常命令的门禁。若删除 API 在异常后返回不确定，下一次执行可能把同名候选误认成安全候选或删除别的 run。

最小修订：增加 `cleanup_pending`（含 candidate、run、validation state、delete attempt、topology digest）及稳定错误码；区分“未验证候选可清理”和“已验证但 switch 未完成只能 resume-switch，不能 cleanup”。`--cleanup-failed` 必须只接受状态/拓扑双证据匹配的未验证候选，删除成功才转 `failed/cleaned`，不确定或失败则保持停服/禁止新 destructive run 并返回明确错误。测试需注入 delete 超时、部分删除、重试幂等和同名冲突。

#### P0-7：v1/v2+dense/sparse 的候选完整性和 fingerprint 交接仍不可机器验收

证据：Spec `:173-175`、Task02A `:48,58-60,77-80`、Task02B（候选验证/故障矩阵条款）与 Task06 `:26-29,67-70,88-90` 虽列出文档、point、维度、payload、anchor、hash、fingerprint 和真实 dense/sparse 查询，但固定交接物只有 `implementation-contract.md`/报告（README `:39-48`），没有字段封闭的 candidate run/validation schema。现有 `index.py:121-145` 的 dense+sparse payload 仍是旧 `paper_id` 结构，`index_paper_chunker()` `:311-315` 接收 `_llm_used` 后丢弃该事实；这使“v2 无规则降级”和“所有新点属于同一次配置”的硬门无法由报告之外的机器检查复算。

最小修订：在 02A-D 先冻结 candidate validation schema（run 状态、每文档/版本 chunk 数、point ID 集合/缺口、document_id、payload allowlist、dense/sparse name/dim/finite/nnz、source hash、anchor、parser/chunker/embed/model fingerprint、`llm_used`、canonical collection fingerprint、query probes），禁止 additional fields 或报告自填关键值。02B 必须通过公开 builder 从 fixture 真实生成并复算 schema/fingerprint；Task06 只能消费该 schema，不能另写一套计数器或接受规则降级/部分候选。

#### P1（在 Task04 放行前必须关闭）：现有上传入口尚未形成不可变原件的迁移/禁用证据

Spec `:165-166`、Task03 `:42-44`、Task04 `:41-49` 已声明原件不可原位修改、同 ID 不覆盖、删除后新 `document_id`。但现有 `backend/app/knowledge_base/infrastructure/store.py:179-191` 的 `save_upload()` 会按传入 `paper_id` 直接 `write_bytes()`，旧 `routes_kb.py:107-132` 上传后立即更新 metadata 并触发 v1/v2 索引。Task04 固定交接物尚未明确旧入口的关闭/迁移、并发上传的 source hash/ETag 约束及新入口如何证明同 ID 覆盖被拒绝。Task06 停服能暂时隔离重建，但不能替代上线后的不可变来源契约。

最小修订：Task03/04 的 API schema/contract report 增加旧 upload route 的迁移或拒绝矩阵、同 ID/重复 hash/并发写测试、写入后 source SHA-256 与 immutable marker；在 Task06 前证明重建期间 metadata/original pre/post hash 不变，重建入口不会调用上传/索引副作用。

### 检查命令与结果

- 只读行号核对：`nl -ba docs/sdd/plans/018/README.md ...`、各 Task/Spec 的 `nl -ba ... | sed ...`、`nl -ba backend/app/knowledge_base/infrastructure/{index,retrieve,store}.py ...`，退出码均为 **0**。
- 工作区边界核对：`git status --short`，退出码 **0**；现有修改仅作为上游待评审 Spec/Plan/评审上下文保留，本轮未回退或覆盖。
- 未运行 pytest、真实 Qdrant、服务启动或重建 CLI：当前 Task02A-D 尚未形成可执行实现，运行这些命令既不能验证新契约，也可能触碰用户数据；本轮为文档技术门禁，故不以“未运行”冒充通过。

### 风险、主 Agent 后续动作与放行条件

1. 先把 P0-1/2/3/4/5/6/7 的 schema、FSM、topology inventory、lock/zero-write 计数和 candidate validation contract 落到 Task02A 固定交接物，保持 02A 只改 fixture/FakeQdrant/临时候选。
2. 由独立 backend-tester/backend-reviewer 用公开入口注入每个 switch/finalize/cleanup/marker/lock 故障；报告必须给出退出码、状态轨迹、拓扑快照和前后写计数，不能只断言最终 alias。
3. Task02B 取得严格 `GO` 后，再让 Task03 冻结 metadata/manifest 的 run-level finalize bundle；Task04 必须通过 API/health 读门禁和不可变原件测试，Task06 才能在停服维护窗口执行真实命令。
4. 任何状态/拓扑不足以证明唯一动作时应保持停服并返回稳定错误；不得用旧 Collection 回滚、隐式重建、删除未知候选或以报告字段替代真实 Qdrant/metadata 观测。

复审日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260909-034718.md`。

## 全库索引替换修订 P0 补丁独立技术复审（第二轮）

### 复审范围与结论

- 时间：2026-09-09 10:24 +0800；模型：gpt-5.6-luna xhigh（临时，仅本轮）；角色：独立技术评审/Architect。
- 只读核对当前 Spec、Plan README、Task02A/02B/03/04/05/06/07、本文最近两轮评审，以及 `knowledge_base` 的 `index/application/retrieve/store/tasks`、旧上传路由和配置入口；未修改业务代码、Spec/Plan 或既有评审段，仅在本文末尾追加本轮结论。
- **结论：打回。** P0-1～P0-7 已在文档层形成较完整的候选隔离、零写观测、锁/FSM、拓扑、清理、验证和 finalize 契约；但上一轮明确要求的 P1“旧 upload 关闭矩阵”仍未落盘为可交接、可机械验收的矩阵，且当前旧入口仍可绕过新 documents application 直接写原件、metadata 和索引。在该矩阵和关闭门禁补齐前，不能将旧上传链路视为已关闭，也不能放行 Task04/Task06。

### P0 逐项核对

| 项 | 结论 | 当前证据 | 复核判断 |
|---|---|---|---|
| P0-1 CandidateIndexPort 与 dry-run 全写 spy | **通过（文档门）** | Spec `:184-186` 固定唯一 Port、显式 `destination_collection/document_id`、`document_id` payload、禁止固定 `KB_COLLECTION/paper_id`、metadata/current-point delete 和旧副作用入口；dry-run 逐项计数 `embedding/collection_create/upsert/delete/alias/metadata/source/manifest/runtime/lock=0`。Task02A `:46-50,66-67`、Task02B `:42,70-71` 固定 FakeQdrant/spy 放行。 | 契约方向正确；实现和 `implementation-contract.md`/candidate schema 尚未生成，符合当前 02A-D 待执行状态，必须继续作为硬门，不能以旧 `index.py` 现状代替实现证据。 |
| P0-2 lock/stale recovery、intent/observed FSM | **通过（文档门）** | Spec `:190-193` 固定 create-exclusive lock 字段、token/heartbeat/finally、显式 stale recovery 条件、破坏性动作前后 `intent/observed`、`switching/finalizing` 收敛；Task06 `:52-56` 固定命令和 fail-closed。 | 已有可执行字段、动作顺序和恢复入口；Task02A/02B 必须在故障注入报告中给出每动作前后轨迹，不能只验最终 alias。 |
| P0-3 TopologyInventory 动作矩阵 | **通过（文档门）** | Spec `:197-208` 固定 `TopologyInventoryV1` 字段、digest、build/switch/cleanup 唯一拓扑条件、歧义码和六行动作矩阵；Task02A `:48,67-70`、Task02B `:42,72` 固定 FakeQdrant 验证。 | 矩阵覆盖旧物理、alias、同 run candidate、finalize、cleanup_pending 和未知拓扑；机器 schema 文件仍待 02A-D 生成，缺失时不得放行 02B。 |
| P0-4 cleanup_pending 生命周期 | **通过（文档门）** | Spec `:199` 固定 `candidate/run_id/validation_state/delete_attempt/last_error_code/topology_digest`、停服、阻止新 destructive run、双重匹配重试、未知删除结果不当作成功；Task06 `:97-100` 固定失败处置。 | 已闭合“失败候选可清理、已验证候选只可 switch”的边界；仍需 committed 故障矩阵证明超时/部分删除/重试幂等。 |
| P0-5 CandidateValidation schema | **通过（文档门）** | Spec `:210-214` 固定 `additionalProperties:false`、run/topology/collection 字段、每文档 v1/v2 的 point/chunk/payload/anchor/dense/sparse/config/`llm_used` 字段和公开 builder 重算；README `:46`、Task02B `:68-73` 固定路径和放行条件。 | 已关闭“报告手填计数”歧义；`candidate-validation.schema.json` 尚不存在，须作为 02A-D 先行产物并由 02B 机械校验。 |
| P0-6 FinalizeBundle/generation marker | **通过（文档门）** | Spec `:216-220` 固定 `FinalizeBundleV1` 字段、受控相对路径、staging→schema/hash→fsync→bundle→原子替换→复核→清理→`data/kb/index-generation.json` marker 的顺序和 API/health 读门禁；Task03 `:42,61`、Task04 `:33,79-80`、Task06 `:29,54` 一致。 | finalize 语义已明确；Task03/04 尚未生成 schema/实现，marker 缺失/不匹配必须继续保持 `INDEX_FINALIZE_REQUIRED`，不能以旧 `store.py` 直接 `write_text()` 代替。 |
| P0-7 端到端候选验证与交接 | **通过（文档门）** | Spec `:173-179,212-225`、README `:24-26,46-51`、Task02A `:38,48-50,63-70`、Task02B `:42,68-73` 固定 v1/v2+dense+sparse、候选隔离、验证、切换、恢复、报告与依赖顺序。 | 阶段边界清楚；真实 Collection 仍只能由 Task06 在维护窗口操作，当前没有可宣称的实现验收。 |

### P1 阻塞：旧 upload 关闭矩阵仍缺失

当前文档只有泛化承诺，不是可交接矩阵：

- Spec `:138,147` 说旧 `/api/kb/papers*`、`/api/kb/upload` 调用方和测试“迁移”或由别名转发，但未逐项写明旧路径/符号的最终动作（移除、固定 410/409、还是转发）、生效版本/截止点、owner、测试 ID、日志证据和误调用时必须为 0 的写计数。
- Task04 `:42,58,78` 只要求“不可变原件”“必须迁移或关闭旧 upload 入口”和测试同 ID/重复 hash/并发上传，未提供固定 `upload-closure-matrix` 产物或 route/symbol-by-symbol 放行表。
- 现有实现仍存在真实旁路：`backend/app/api/routes_kb.py:107-132` 的 `/kb/upload` 读取整文件后直接调用 `save_upload`、`upsert_paper`、`index_paper_chunker`；`routes_kb.py:14-38` 从 application 导入这些旧能力；`backend/app/knowledge_base/application.py:37-50,69-95` 继续暴露旧 store/index/task facade；`backend/app/knowledge_base/infrastructure/store.py:179-191` 按传入 `paper_id` 直接 `write_bytes()`，可覆盖同 ID 原件。文档说 Task04 将来处理，不能证明当前 P1 已关闭。

**最小可执行修订（由主 Agent/架构师补入 Spec/Plan 后再评审）：**

1. 在 Task04 固定新增 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`（或等价固定文件），每行封闭记录 `legacy_route_or_symbol`、`current_owner`、`final_action={removed|410|409|forward_documents_application}`、目标入口、HTTP/错误码、同 ID/重复 hash/并发测试 ID、source/metadata/index 写计数、启用版本/截止点和报告 hash；至少覆盖 `/api/kb/upload`、`/api/kb/papers*`、`save_upload`、`upsert_paper`、`index_paper_chunker`、论文导入适配器及 CLI/后台入口。
2. 把矩阵列为 Task04/Task06 前置门：未逐项证明“旧入口不可写或只转发同一 documents application”、同 ID 覆盖拒绝、原件 SHA/metadata/ETag 一致、重建 Port 未调用旧 upload/index 副作用时，Task04 与 Task06 均保持阻塞；旧入口调用 spy 必须为 0 或明确计入同一新入口。
3. 在 `api-schema.json`/`api-fixture-index.json` 和 `backend-contract-report.md` 交叉引用矩阵，记录退出码与实际 route inventory，避免只在 prose 中声称“已迁移”。

### 交接与风险

- Task02A-D 的四份候选交接物当前均不存在：`implementation-contract.md`、`candidate-rebuild-run.schema.json`、`topology-inventory.schema.json`、`candidate-validation.schema.json`；这与 README `:46` 和 Task02A `:38-40` 的“待执行”状态一致，不作为本轮另一个实现失败，但在这些文件落盘前不能从文档门进入 02B `GO`。
- 旧实现的固定 `papers`、legacy `paper_id` 和直接上传路径是本轮观察到的主要误写风险；不应通过运行真实 Qdrant、服务或 pytest 伪造关闭证据。

### 检查命令与结果

- `nl -ba` 核对 Spec/README/Task02A/02B/03/04/06 与 `index/application/retrieve/store/tasks/routes_kb/config`：退出码 **0**。
- `rg -n` 检索 CandidateIndexPort、dry-run spy、lock/FSM、TopologyInventory、cleanup_pending、CandidateValidation、FinalizeBundle、generation marker 和 upload 入口：退出码 **0**。
- `git diff --check`：退出码 **0**。
- 固定候选 schema/implementation-contract 存在性检查：四份尚未生成（按当前 Task02A-D `待执行` 状态预期）。
- 未运行 pytest、真实 Qdrant、服务或 rebuild CLI；本轮为只读技术门禁，避免触碰真实用户索引和把未实现内容误报为验收通过。

### 主 Agent 后续动作

先补齐并固定旧 upload 关闭矩阵及 Task04/06 门禁，随后再由独立 backend-reviewer/backend-tester 复核实际 route inventory、同 ID 覆盖拒绝和新 application 唯一路径；同时按当前 Spec 生成四份 02A-D machine artifacts，取得严格 `GO` 后才放行 Task03–07。Spec 仍保持 `待确认`。

复审日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260909-040000+0800.md`。

## 全库索引替换修订 upload closure 设计门最终独立技术复审

### 双门结论

- 时间：2026-09-09 10:56 +0800；模型：gpt-5.6-luna xhigh（临时，仅本轮）；角色：独立技术评审/Architect。
- 只读核对最新 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`、Spec 旧上传链路矩阵、Task04、Task06，以及真实 routes/application/store/index/tasks/paper-import 入口；未修改业务代码、Spec/Plan 或历史评审段。
- **设计门：GO。** P1 的 baseline 设计已完整到足以在用户再次确认后开始 Task02A-D；P0-1～P0-7 沿用上一轮已关闭结论。
- **Task04/06 实现门：当前未放行/未实现。** baseline 仍必须保持 `open/pending/baseline_frozen`；只有 Task04-D 未来把所有 entry/test 更新为 `closed/passed`、`exit_code=0`、证据路径非空且 `review_status=verified`，Task06 才可进入真实维护窗口。此结论不把设计 GO 误报为 Task04/06 已完成。

### 设计门证据

1. **实际入口完整且名称准确。** 最新矩阵 `:6-14` 固定 `main.py` 加七个既有入口文件，并绑定 `inventory_git_revision`、逐文件 SHA-256、排序 digest；`:23-176` 共 17 个 entry 覆盖 `/api/kb/upload`、旧 reindex/delete、`/api/papers/imports`、`/api/papers/import-batches` 及 retry/cancel/login/resume、route helpers、paper import application/adapter、`save_upload/save_papers/upsert_paper/remove_paper/update_chunker_state/mark_interrupted_tasks`、index/task、`main.lifespan` 和 rebuild CLI。此前不存在的单数 `/api/papers/import` 已在 Spec `:220` 与 Task04 `:60` 明确为文档笔误且不属于兼容契约。
2. **字段、枚举和机械验证契约完整。** Spec `:218-220` 固定顶层/entry/test 的封闭字段、`closed_enums` 枚举、`required_status=closed`、真实 8 文件 inventory 和 digest 变化门；Task04 `:60,69,82-83` 固定实现后更新、所有 entry/test 关闭、退出码 0、证据非空和静态 inventory 防漏项。矩阵当前 `:16-21,178-192` 提供相同枚举、12 个 test、entry 映射、命令、`exit_code` 和 `evidence_paths` 字段。
3. **baseline 分层正确。** 当前矩阵 `review_status=baseline_frozen`，17 个 entry 均 `current_status=open`/`required_status=closed`，12 个 test 均 `status=pending`、`exit_code=null`、证据为空；这是实现前可审计基线，不是失败或伪造完成态。Task06 `:18-20` 明确 baseline 不得进入真实任务，必须等待 `verified/closed/passed`。
4. **hash/digest 可复算。** 本轮只读脚本确认 HEAD 等于矩阵 `inventory_git_revision`；8 个文件 SHA-256 全部匹配；按 `shasum -a 256` 行排序并带末尾换行计算的 digest 等于 `5ef5a5fd1d2ed100be950e462e52517536f003bd00bbde7ca189ac71abc8a9c7`；entry/test 引用无孤儿。

### Task04/06 当前实现状态与后续门

- Task04 的 `upload-closure-matrix.json` 目前是 baseline artifact，不代表 routes/store/index/application 已迁移；现有旧实现仍可观察到旧写路径，需由 04-C/04-D 实现和测试逐 entry 关闭。
- Task04-D 必须取得所有 entry `closed`、required tests `passed`、`exit_code=0`、`evidence_paths` 非空、inventory hash/digest 按实现后代码重算、`review_status=verified`；否则保持阻塞。
- Task06 仅在 Task04 verified、Spec 用户确认、dry-run 和其余 Task03–05 门禁均通过后执行真实 alias/finalize；不得因为本轮设计 GO 提前操作真实 Qdrant 或宣称实现验收。

### 检查命令与结果

- JSON 解析、entry/test 唯一性和映射检查：退出码 **0**；17 entries、12 tests，baseline 分层符合契约。
- HEAD、8 个文件 SHA-256、inventory digest 复算：退出码 **0**，全部匹配。
- `rg -n`/`nl -ba` 清点真实 routes、后台 symbols、Spec/Task 门禁：退出码 **0**。
- `git diff --check`：退出码 **0**。
- 未运行 pytest、服务、真实 Qdrant 或 rebuild CLI；实现门仍待 Task04/06 后续执行。

复审日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260909-040000+0800.md`。

## 全库索引替换修订 upload closure 独立技术复审（第二轮）

### 结论

- 时间：2026-09-09 10:50 +0800；模型：gpt-5.6-luna xhigh（临时，仅本轮）；角色：独立技术评审/Architect。
- 只读核对 `upload-closure-matrix.json`、Spec 旧上传链路矩阵、Task04/Task06，以及真实 `routes_kb.py`、`routes_paper.py`、`application.py`、`store.py`、`index.py`、`tasks.py`、`paper_import.py`；未修改业务代码、Spec/Plan 或历史评审段。
- **结论：NO-GO（打回）。** P0-1～P0-7 沿用上一轮“文档门已关闭”的结论；本轮矩阵已正确覆盖大部分旧路由/导入/task/index symbol，并正确区分 `baseline_frozen/open/pending` 与未来 `verified/closed/passed`，但仍遗漏真实后台写入口，不能关闭 P1，也不能放行用户确认后的 Task02A-D。

### 剩余阻塞

1. **遗漏启动期旧索引写入口。** 矩阵 `inventory_files`（`upload-closure-matrix.json:6-13`）只有七个文件，没有 `backend/app/main.py`；矩阵 entries 也没有 `backfill_chunker_defaults`。但 `main.py:12-15,34-46` 在 lifespan 中调用 `mark_interrupted_on_startup()` 和 `backfill_chunker_defaults()`，后者通过 `application`/`index` 更新旧固定 Collection。它是实际后台 index 写入口，不属于当前 16 entries，静态 inventory 因而无法证明“所有后台入口”已覆盖。
2. **直接 store 写 symbol 仍未逐项封闭。** `store.py:101-122` 的 `save_papers()` 是公开 metadata 写函数，`store.py:161-176` 的 `remove_paper()`、`store.py:281-320` 的 `update_chunker_state()` 和 `store.py:322-...` 的 `mark_interrupted_tasks()` 也会写 metadata/source 状态；矩阵仅以 `store.save_upload and store.upsert_paper`（`upload-closure-matrix.json:132-138`）代表 store 边界，`T-DIRECT-SYMBOLS` 无法机械证明这些可直接调用 symbol 已删除、私有化或拒绝不安全调用。
3. **baseline 证据尚未达到 Task04 实现放行，但这不是误判。** 当前矩阵 `review_status=baseline_frozen`、所有 entry `current_status=open`、所有 tests `status=pending`、`exit_code=null` 且 `evidence_paths=[]`（`upload-closure-matrix.json:15-20,168-181`），与 Spec `:218-226` 和 Task04 `:60,69,82-83` 的 baseline→verified 分层一致；它足以作为实现输入，但在补齐入口并由 Task04-D 产生 `verified/closed`, `passed`, `exit_code=0`, 非空证据后，才可解除 P1。不能把 baseline 当作 Task04 已完成，也不能用它放行 Task06。

### 需补齐后复审

- 将 `backend/app/main.py` 纳入 inventory 文件和 hash/digest，新增 `main.lifespan → application.backfill_chunker_defaults`（以及其 startup recovery 写入口）entry；明确它在新 generation/维护门禁下的删除、禁止或唯一 application 转发动作。
- 将 `store.save_papers`、`store.remove_paper`、`store.update_chunker_state`、`store.mark_interrupted_tasks` 等直接写 symbol 纳入逐项 entry 或明确证明它们已变为私有且由已登记 owner 唯一调用；更新静态 inventory 与 `T-DIRECT-SYMBOLS`/`T-BACKGROUND-INVENTORY` 覆盖集。
- 重新计算 inventory revision、逐文件 SHA-256 和 digest；Task04-D 再将所有 entry/test 更新为 `closed/passed`, `exit_code=0`, 非空 `evidence_paths`, `review_status=verified`。完成后即可重新提交本 P1 复审；此前 Spec 保持 `待确认`、Task02A-D 不放行。

### 检查命令与结果

- JSON 解析、entry/test 唯一性与映射检查：退出码 **0**；16 entries、11 tests，当前所有 entry 均 open、所有 tests 均 pending。
- 7 个 inventory 文件 SHA-256 与矩阵逐项一致，`shasum -a 256` 行排序摘要可复算为 `inventory_digest`；退出码 **0**。
- `rg -n`/`nl -ba` 路由和 symbol 清点：退出码 **0**；确认实际 plural import/batch 路由及 `main.lifespan` 写入口。
- 未运行 pytest、服务、真实 Qdrant 或 rebuild CLI；本轮为只读技术门禁。

复审日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260909-040000+0800.md`。

## 全库索引替换修订 upload closure 独立技术复审

### 范围与结论

- 时间：2026-09-09 10:34 +0800；模型：gpt-5.6-luna xhigh（临时，仅本轮）；角色：独立技术评审/Architect。
- 只读核对当前 Spec、README、Task04、Task06、本文上一轮复审，以及 `routes_kb.py`、`routes_paper.py`、`store.py`、`index.py`、`application.py`；未修改业务代码、Spec/Plan 或历史评审段，仅在本文末尾追加本轮结论。
- **结论：打回。** 上一轮 P0-1～P0-7 的“文档门已关闭”结论沿用；本轮 P1 仍未形成真正逐路由/逐 symbol、可机械核验的 upload closure。新增条款已经明确目标，但覆盖清单仍与现有路由/后台入口不一致，固定矩阵和机器可判定的 route inventory 尚未落盘，因此不能宣称当前技术评审最终通过。

### 残余缺口（仅 P1）

1. **矩阵列出的论文导入路由与真实路由不一致且不完整。** Spec `:218-225`、Task04 `:60` 固定列出 `POST /api/papers/import`，但当前 `routes_paper.py:653-664` 的实际 POST 路由是 `/api/papers/imports` 与兼容别名 `/api/papers/import-batches`；另有 `routes_paper.py:680-700,742-769` 的 retry/cancel/resume 入口可能触发后台导入。若矩阵不逐项决定这些真实路径的删除、转发或禁止动作，不能证明旧导入链路已关闭。
2. **“所有后台索引提交入口”仍是不可枚举的泛称。** Spec `:219,224`、Task04 `:60,82` 要求覆盖所有后台入口，但没有把当前实际 symbol 逐一列入固定集合：`routes_kb._submit_index_task`/`reindex_kb_paper`（`routes_kb.py:135-166`）、`tasks.submit_index_task`/`run_index_task_sync`（`tasks.py:43-90`）、`application.KnowledgeBasePaperImportAdapter._default_indexer`（`application.py:232-244`）以及仍暴露的 `application.index_paper`/`index_paper_chunker`（`application.py:386-388`）。仅写“所有”无法由 schema 或报告机械发现漏项。
3. **schema 虽封闭字段，但没有闭合值/库存绑定。** Spec `:218` 只固定 `route_or_symbol` 等字段名和 `additionalProperties:false`，未固定 `entry_kind/status/review_status` 的枚举、required test 的 `test_id/exit_code` 结构，或 `route_inventory_sha256`/静态 inventory 作为“所有入口”证明。Task04 `:69,82` 的“逐 entry closed、无 open/unknown”仍依赖人工自报；当前 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`、`api-schema.json`、`api-fixture-index.json`、`backend-contract-report.md` 均尚未生成。
4. **现有旁路尚未关闭，不能被文档承诺替代。** `routes_kb.py:107-132` 仍由 `/api/kb/upload` 直接调用 `save_upload`、`upsert_paper`、`index_paper_chunker`；`store.py:179-191` 仍按调用方 `paper_id` 直接 `write_bytes()`；`application.py:232-244,249-339` 的论文导入默认 indexer 仍走旧 `index_paper_chunker`，`index.py:101-149,260-356` 仍固定写 `KB_COLLECTION`/`paper_id`。这些可作为未来 04-D 的反例测试，但当前尚未有逐 entry 关闭证据。

### 最小修订与放行门

- 将矩阵覆盖集修正为真实路由和 symbol：至少加入 `/api/papers/imports`、`/api/papers/import-batches`、对应 retry/cancel/resume 入口、`routes_kb._submit_index_task`/`reindex_kb_paper`、`tasks.submit_index_task`/`run_index_task_sync`、`application` 默认 indexer/导出符号，并明确不存在的 `/api/papers/import` 是“删除/不提供”还是文档笔误。
- 在 schema 中固定 `entry_kind`、`status`、`review_status` 枚举和 `tests[]` 的 `test_id/command/exit_code/result` 字段；加入仓库 route/symbol inventory 的 hash 或等价完整集合，禁止只用“all”作为覆盖证明。
- 只有 `upload-closure-matrix.json` 实体存在、每个真实 entry 均 `closed`、测试命令/退出码和 source-write spy 均可复核，且 Task04 `:82` 与 Task06 `:19` 门禁实际消费该文件后，P1 才能关闭。此前保持 Task04/Task06 阻塞，Spec 继续保持 `待确认`。

### 检查命令与结果

- `nl -ba` 核对 Spec/README/Task04/Task06 和指定 routes/store/index/application：退出码 **0**。
- `rg -n` 清点 `/api/papers/import*`、upload、index/task/import symbols：退出码 **0**；确认实际路由为 plural `imports`/`import-batches`。
- 固定 Task04 upload closure/API/fixture/report 文件存在性检查：均为 **absent**（Task04 当前待执行）。
- 未运行 pytest、服务、真实 Qdrant 或 rebuild CLI；本轮只读技术门禁。

复审日志：`.codebuddy/agent-logs/spec-018/task-00/architect/20260909-040000+0800.md`。
