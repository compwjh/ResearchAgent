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
