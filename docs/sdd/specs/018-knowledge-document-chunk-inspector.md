# Spec 018 — 知识文档切片检查器与双向原文定位

## 状态

**当前状态：`实施中`（全库索引替换修订已确认；主线门禁仍按 Task02A-D 推进，Task06E/06F 已完成针对性热修复）**

> 2026-09-08 首轮 Task02 的 `NO-GO` 与固定证据永久保留；Task02A-A～C 已完成并分别通过独立后端评审。2026-09-09 用户明确旧 Qdrant 索引可以全部抛弃，只要求新索引生效，因此撤销此前“逐 point/vector 快照、原地恢复、首次打开自动升级”的未完成设计，改为一次性全库候选 Collection 重建与维护窗口切换。全库替换修订的独立需求评审与技术设计门均已通过，用户于 2026-09-09 明确要求“开始执行”；现仅放行 Task02A-D，Task02B `GO` 前继续阻塞 Task03–07，Task04/06 的实际 upload closure 门仍未放行。未提交的旧快照实现不属于交付物。

## 一句话目标

在个人知识库中新增“切片检查”Tab，让用户选择一份已入库的 PDF 或 Markdown 文档，在原文视图与切片视图之间进行文本块级双向点击、滚动和高亮，并看到真正写入索引的 v1/v2 切片结果。

## 背景与问题

- 当前知识库只在问答命中引用时展示少数切片，无法查看某份文档的完整切分结果。
- 当前 `Chunk` 只保存文本、页码范围、切片序号和章节，没有 PDF 坐标、Markdown 块位置或稳定来源锚点。
- Qdrant 中的片段是检索索引，不适合作为原文展示与双向定位的唯一事实来源。
- 当前上传、存储与接口仍使用“论文/Paper”命名且只接受 PDF，不能覆盖 Markdown 等通用知识文档。
- 既有 PDF 已经完成 embedding，但旧索引没有来源坐标。旧 Qdrant points 被重新定义为可丢弃派生数据：正式迁移不逐 point 修补或恢复，而是从仍受保护的 PDF/Markdown 原件与元数据完整生成新 Collection，验证通过后统一切换。

## 领域语言

- **知识文档（Knowledge Document）**：进入个人知识库的原始文件；包括手工上传或论文检索导入的 PDF，以及手工上传的 Markdown。
- **原文块（Source Block）**：原文视图中可被点击、定位和高亮的最小内容单位。
- **切片快照（Chunk Snapshot）**：某个切片版本实际写入检索索引的片段；检查器不得临时重跑切分后冒充真实结果。
- **来源锚点（Source Anchor）**：一个原文块与一个切片快照之间的多对多对应关系。
- **检查清单（Inspection Manifest）**：一份知识文档在一个切片版本下的原文块、切片快照、来源锚点和构建状态。

确认后应将以上术语写入根目录 `CONTEXT.md`，并创建 ADR `docs/adr/0001-separate-source-chunk-manifest-and-vector-index.md`，记录原件、检查清单与 Qdrant 检索索引分离的决定。

## 数据模型

### `KnowledgeDocument`

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `document_id` | str | 必填、全局唯一；已有 `paper_id` 原值迁移为 `document_id`，不得重新生成导致引用失效 |
| `file_name` | str | 必填，仅用于展示；不得作为磁盘路径 |
| `media_type` | enum | `application/pdf` / `text/markdown` |
| `source_sha256` | str | 当前原件字节摘要，用于检查清单失效判定；旧索引对应摘要另见 `indexed_source_sha256` |
| `indexed_source_sha256` | str/null | 同一索引构建前后核对得到的源摘要；旧文档无法证明历史对应关系时为 null |
| `source_hash_state` | enum | `verified` / `legacy_unknown` / `mismatch`；不得把当前摘要冒充历史索引摘要 |
| `stored_name` | str | 服务端生成的安全文件名；只允许 basename |
| `status` | enum | 沿用现有索引状态语义 |
| `created_at` | ISO datetime | 带时区；迁移旧数据时保留原 `uploaded_at` |
| `page_count` | int/null | PDF 为页数；Markdown 为 null |
| `chunkers` | map | v1/v2 状态、进度、片段数和错误 |
| 论文元数据 | optional | 标题、作者、年份、会议、DOI、DBLP key、来源 URL 等原样保留 |

### `SourceBlock`

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `block_id` | str | 在同一 `document_id + source_sha256` 下稳定 |
| `ordinal` | int | 从 0 递增，决定原文顺序 |
| `text` | str | 用于对齐的规范化文本 |
| `locator.kind` | enum | `pdf_bbox` / `markdown_lines` |
| PDF locator | object | `page` 为 1-based；`bbox` 使用相对页面宽高的 0–1 坐标 |
| Markdown locator | object | `start_line`、`end_line` 为 1-based；可带 `heading_path` 与块类型 |

### `ChunkSnapshot`

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `chunker` | enum | `v1` / `v2` |
| `chunk_index` | int | 与已入库 payload 一致 |
| `text` | str | Qdrant 中实际切片文本 |
| `page` / `page_end` | int/null | PDF 页码范围；Markdown 可为空 |
| `section` | str | 允许空值 |
| `is_citation` | bool | 沿用现有参考文献标记 |
| `chunk_fingerprint` | str | 对实际 payload 中稳定字段计算摘要 |

### `SourceAnchor`

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `block_id` | str | 必须引用同一检查清单中的原文块 |
| `chunker` | enum | `v1` / `v2`；与 manifest 版本共同构成 anchor 身份 |
| `chunk_index` | int | 必须引用同一 `chunker` 版本的切片快照 |
| `coverage` | float | 0–1，等于该原文块与切片在同一规范化来源流中已证明重叠的字符数除以切片文本字符数；用于选择主定位目标 |
| `is_primary` | bool | 可映射切片至少有一个主锚点；以最大真实重叠、再按 block ordinal 稳定选择；无法映射时为 false 并记录 `unmapped_reason` |
| `block_range` / `chunk_range` | tuple/null | 可可靠取得时记录文本区间；首版 UI 只要求块级高亮 |
| `unmapped_reason` | str/null | 无 anchor 时的稳定原因码，不含第三方异常或绝对路径 |

映射比较前统一采用 Unicode NFKC、CRLF 转 LF、去除行尾空白、连续水平空白折叠为一个空格，且不跨原文块边界。`coverage` 定义为规范化文本重叠字符数除以 chunk 文本字符数；空文本 coverage 为 0。同覆盖率按 `block.ordinal`、`chunker`、`chunk_index` 升序稳定排序，首项为 `is_primary=true`；所有关联项均返回，未映射项由 manifest 的 `unmapped_count`、`unmapped_reason` 和用户警告显式表示。PDF `bbox` 为 `[x0,y0,x1,y1]` 的 0–1 相对页面坐标，固定样本允许 ±0.005 误差；Markdown 行号为精确的 1-based 原始行范围，即使净化 HTML 也不改变块的原始范围。

### 来源锚点稀疏映射修订：`source-anchor-v2`

`source-anchor-v1` 曾将每个切片与每个原文块做 `SequenceMatcher` 模糊比较，并把任意正分项全部写为 anchor。常见词、页眉和极短重叠会被误判为来源关系，产生近似 `chunk 数 × block 数` 的组合爆炸；它不符合产品的“点击 Introduction，只展示实际包含 Introduction 的切片”语义。v1 manifest 不得继续作为可交互定位事实使用。

`source-anchor-v2` 的唯一关系依据是切片生成时保留的、可验证的规范化来源字符区间：

1. 每个 PDF 页和 Markdown 文档先由 parser 的有序 `SourceBlock` 构成不跨 block 边界的规范化来源流，并记录每个 block 的 `[start,end)` 区间；v1 的重叠切片与 v2 的结构切片均在生成时记录其对应来源流区间。该区间是构建时短暂证据，`SourceAnchor` 只持久化由它证明的 block/chunk 关系及可选 ranges。
2. 仅当 block 区间与 chunk 区间有正的真实字符交集时建立 anchor。不得以任意共同词、编辑距离、`SequenceMatcher` 的零散子串或全文相似度推断关系；标题（如 `1 Introduction`）同样只能由其在 chunk 区间中的真实出现建立关系。
3. 一个原文块关联它实际覆盖的全部切片；一个切片关联其实际覆盖的全部原文块。v1 overlap 或 v2 跨页自然产生少数相邻关系，但不得用“最多 N 条”的人为截断掩盖错误，也不得出现近似全连接关系。
4. 不能把既有 chunk 文本唯一、精确地对齐回来源流时，该 chunk 必须为 `unmapped` 并记录稳定原因 `SOURCE_RANGE_UNRESOLVED`；不得退回 v1 模糊匹配。PDF/Markdown 的映射均保持可重复、按 ordinal/chunk_index 稳定排序。
5. 此次算法变更只使 inspection manifest/anchor 派生数据失效；已验证的 v1/v2 chunk 文本、向量和个人原件不重写。重建必须从受保护原件和当前 Qdrant chunk snapshot 复核 fingerprint 后生成 v2 manifest；不匹配则 fail-closed，不 embedding、不下载、不写入 Qdrant。

### `InspectionManifest`

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `schema_version` | int | 初始 1 |
| `mapping_algorithm_version` | str | 必填；算法改变时使旧清单失效 |
| `source_parser_version` | str | PDF provenance 或 Markdown parser 版本；变化使旧清单失效 |
| `chunker_config_fingerprint` | str | v1/v2 参数和 normalize 版本摘要；变化使旧清单失效 |
| `payload_schema_version` | int | Qdrant payload schema 版本；变化使旧清单失效 |
| `document_id` / `chunker` | str | 组合唯一 |
| `status` | enum | `pending/building/ready/partial/failed` |
| `progress` | int | 0–100，单调不回退 |
| `source_sha256` | str | 原件变化时触发重建 |
| `indexed_source_sha256` | str/null | 历史索引对应源摘要；legacy unknown 时为 null |
| `source_hash_state` | enum | `verified` / `legacy_unknown` / `mismatch` |
| `index_fingerprint` | str | 切片集合变化时触发重建 |
| `mapped_count` / `unmapped_count` | int | 不得隐瞒无法定位的切片；unmapped chunk 不得设置 primary |
| `unmapped_reasons` | map | 稳定原因码到数量的汇总 |
| `error` | str/null | 面向用户的稳定错误摘要，不含绝对路径或敏感信息 |

检查清单是可删除后重建的派生数据，按 `document_id/chunker` 独立原子写入；原件和知识文档元数据是长期事实，Qdrant 继续只承担检索索引。

### `IndexRebuildRun`

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `run_id` | str | 一次全库重建的稳定 ID；候选 Collection 名由它生成且只含安全字符 |
| `source_collection` | str/null | 当前物理 Collection 或 alias 指向；仅作审计，不读取其 point 作为新索引来源 |
| `candidate_collection` | str | 新建的独立物理 Collection，未验证前不得承接查询 |
| `chunkers` | list | 本次明确请求重建的 v1/v2；所有可重建文档使用同一选择 |
| `status` | enum | `preflight/building/validating/ready_to_switch/switching/finalizing/finalize_pending/cleanup_pending/cleaned/completed/failed` |
| `progress` | int | 0–100，单调不回退 |
| `document_counts` / `point_counts` | map | 计划、完成、失败、跳过和按 chunker 的实际数量 |
| `new_fingerprint` | map | 新 Collection 的 point ID、payload、dense/sparse 维度与 canonical 摘要 |
| `error_code` | str/null | 稳定、脱敏错误码；不得包含原文、绝对路径、向量正文或第三方异常 |

`IndexRebuildRun` 只保存脱敏运行摘要，不保存旧向量快照。运行状态固定写入 `.sdd/runtime/spec-018/rebuild/<run-id>/state.json`，事件写入同目录 `events.jsonl`；全局 rebuild lock 只允许一个 run。原件和知识文档元数据仍是长期事实；旧 Qdrant Collection 是可删除派生数据。候选构建失败时自动删除本次未验证候选并保持当前查询入口不变；候选验证成功后才能进入维护窗口切换。首次从名为 `papers` 的物理 Collection 迁移到同名稳定 alias 时，先停止服务，再删除旧物理 Collection并创建 `papers → candidate` alias；若 alias 创建失败，保留已验证候选并保持服务停止，只允许幂等 `resume-switch`。alias 已切换但元数据或 manifest 提交失败时进入 `finalize_pending`，保留新 Collection、禁止正常启动并只允许幂等 `resume-finalize`。后续重建使用 Qdrant alias 原子切换，再删除旧物理 Collection，不实现逐 point 回滚。

> 状态映射与摘要约定：既有 `indexed_partial` 对外转换为 manifest `partial`；`indexing` 转为 `building`，`pending`、`indexed`、`failed` 分别转为 `pending`、`ready`、`failed`。当前 `mapping_algorithm_version` 固定为 `source-anchor-v2`；`source-parser`、normalize、chunker 参数或 payload schema 任一变化也使旧清单失效。`source_sha256` 为当前原件字节 SHA-256；`index_fingerprint` 为新 Collection 实际 payload 中全部切片快照按 `(chunker, chunk_index)` 排序、键排序 JSON 序列化后的 SHA-256。新文档必须由同一次索引流水线生成 chunks、anchors 和 manifest。旧文档缺少 provenance 或仅有 `source-anchor-v1` 时不得旁路伪造 manifest；必须返回稳定的重建提示。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `GET /api/kb/documents` | — | `{documents:[KnowledgeDocumentSummary...]}` | 200 空列表 |
| `POST /api/kb/documents/upload` | multipart PDF 或 UTF-8 Markdown | 新文档 ID、格式和 v1/v2 状态 | 400 扩展名/魔数/编码/大小非法；409 重复内容；500 受控失败 |
| `GET /api/kb/documents/{document_id}/source` | 文档 ID；PDF 可带 Range | 原件流，正确 Content-Type，PDF inline | 404 文档或原件不存在；416 Range 非法 |
| `GET /api/kb/documents/{document_id}/inspection?chunker=v1\|v2` | 文档 ID、版本 | 200 清单；旧索引缺 provenance 时返回稳定的重建提示 | 400 版本非法；404 不存在；409 `INDEX_REBUILD_REQUIRED`/版本未完成；503 依赖不可用 |
| `POST /api/kb/documents/{document_id}/reindex` | `{chunker:"v1"\|"v2"\|"all",reason?:"manual"}` | 新架构启用后的单文档显式重建 | 404 原件丢失；409 已在执行/原件 hash 冲突/全库迁移尚未完成 |
| `DELETE /api/kb/documents/{document_id}` | 文档 ID | 删除原件、元数据、向量和检查清单 | 404 不存在 |

旧 `/api/kb/papers*` 调用方和测试在本 spec 内迁移到通用 `/api/kb/documents*`，不保留两套长期并行的数据模型或第二套索引流程。论文发现导入必须调用知识库 application 入口，不能直接操作存储。

### 接口契约补充

- `GET /api/kb/documents` 成功返回 `{documents:[KnowledgeDocumentSummary...]}`；summary 至少含 `document_id`、`file_name`、`media_type`、`status`、`source_sha256`、`page_count`、`chunkers` 和每个版本的 manifest 状态/进度。空库仍返回 200 空数组。
- `POST /api/kb/documents/upload` 的成功返回至少含 `document_id`、`media_type`、`chunkers` 和原件/索引状态；原件提交后不可原位修改，不提供 `PUT`、`PATCH` 或同 ID 覆盖。删除后重新上传按新提交生成新 `document_id`，重复内容仍沿用既有 hash 去重规则。拒绝空文件、扩展名/魔数、UTF-8、大小或 basename 非法时返回稳定 400 错误码，受控服务失败返回 500 且不留半截记录。
- `GET /api/kb/documents/{document_id}/source` 无 Range 返回 200；单一合法 Range 返回 206 和 `Accept-Ranges: bytes`、`Content-Range`、`Content-Length`、正确媒体类型及 inline disposition。非法 ID、文档不存在或原件缺失返回 400/404；越界或多 Range 返回 416，错误不含绝对路径。
- `GET /api/kb/documents/{document_id}/inspection?chunker=v1|v2`：当前 `source-anchor-v2` 的 ready/partial 清单返回 200。旧索引缺 provenance 或 v1 模糊 anchors 时只返回 409 `INDEX_REBUILD_REQUIRED` 和管理员可执行的 manifest 重建提示；打开页面不触发切片、embedding、删除或后台升级，也不得返回虚假 anchors。
- `POST /api/kb/documents/{document_id}/reindex` 仍只接受 `v1`/`v2`/`all` 与 `reason="manual"`，但必须在首次全库迁移完成后才可使用；原件 hash 与元数据不一致时返回 409 `SOURCE_HASH_MISMATCH`。`DELETE` 成功删除原件、元数据、当前 Collection 中的向量和检查清单，不再清理旧升级任务或恢复快照。
- 旧 `/api/kb/papers*`、`/api/kb/upload` 的调用方与测试在同一变更中迁移；不保留第二套业务实现。若为已有外部调用提供过渡别名，别名只能转发到同一 documents application 入口，并在迁移完成后按变更日志移除。

## 技术冻结协议（进入实现前必须满足）

### PDF provenance、坐标与 Task 02A/02B 解阻门禁

- Task 02 的固定产物路径为 `docs/sdd/plans/018/artifacts/task-02/source-anchor-feasibility-report.md`、`docs/sdd/plans/018/artifacts/task-02/fixture-index.json`、`docs/sdd/plans/018/artifacts/task-02/provenance-dto.schema.json`；原件和期望输出必须位于 `docs/sdd/fixtures/spec-018/`。报告必须逐样本记录 `sample_id`、原件/期望 JSON SHA-256、git revision、parser/provenance/normalize/mapping 版本、命令与退出码、页数/列数/rotation、block/line/word 数、映射率、重复文本 tie-break、bbox 最大/中位误差、Markdown 行号结果、Qdrant point 数/ID/fingerprint、embedding/切分/Qdrant 写调用次数、失败码和 Go/No-Go。`fixture-index.json` 必须逐项列出原件、expected JSON、DTO schema 的相对路径、SHA-256、媒体类型、期望状态和阈值；报告结论只允许 `GO` 或 `NO-GO`，不得以“有条件通过/风险接受”代替。
- 首轮 Task02 的 `NO-GO` 报告、fixture 和 schema 保持不可改写的历史证据。Task02A 在 Spec 修订重新确认后实现生产级 PDF/Markdown provenance 基础；Task02B 只读消费 Task02A 实现和原固定样本，重新裁决 `GO|NO-GO`。Task03–07 仅依赖 Task02B `GO`。
- Task02B 的功能 Go 门槛固定为：`pdf-single-column-v1`、`pdf-two-column-v1-overlap`、`pdf-v2-cross-page` 和 `markdown-blocks` 的期望 block/chunk/anchor 集合全部匹配；正常 PDF 文本块 bbox 归一化最大误差 ≤0.005；Markdown 行号 100% 精确；重复文本按 ordinal/chunk_index tie-break；新文档索引的 duplicate/gap 为 0。word 级坐标仅为可选诊断，不是硬门。`pdf-no-text-layer` 只能为 `partial`/`failed` 且错误码为 `PDF_NO_TEXT`。2026-09-09 用户决定功能优先：Task02A-E 评审发现的生产加固项允许作为显式 `security_debt` 留账，不再阻塞 Task02B 的功能裁决与 Task03–05；但债务未全部关闭前，Task06 不得连接真实 Qdrant、不得执行 `--confirm-replace`、不得切换或删除真实 Collection。
- Hostile PDF 在 Task02B 只验证后端 parser 不执行 JavaScript、表单动作、附件或远程资源，也不发起网络请求；真实浏览器中的 PDF.js 零外部网络记录移至 Task05 最终安全硬门，避免以尚未实现的前端阻塞后端基础实现。
- 后端统一使用 `PdfSourceProvenanceV1` DTO 生成索引和 manifest：每页包含 `width`、`height`、`rotation`、`crop_box`；每个 block 必须包含稳定 ordinal、原始文本、原始字符 `start/end`、PDF point bbox 和 normalized 0–1 bbox。line/word 可作为诊断附带，但首版 UI 和 GO 门只承诺 block。规范化文本与字符区间必须来自同一 DTO；禁止再次调用只返回整页字符串的 `get_text("text")` 来补坐标。
- PDF.js 坐标转换冻结为：后端保存未旋转 crop box 的 0–1 bbox；前端用同页 public `getViewport({scale, rotation})` 对 bbox 四角做 viewport transform，取转换后的 min/max 作为 CSS overlay，devicePixelRatio 只影响 canvas backing store 不改变 CSS 坐标；缩放、旋转和 crop box 变化重新计算 overlay，不使用 PDF.js 私有字段。任何转换误差超过 ±0.005、无法恢复原始 block 或只得到页级文本时，manifest 为 `partial` 并带 `PDF_PROVENANCE_UNAVAILABLE`，不得伪装为 `ready`。

### 身份、Qdrant payload 与 fail-closed 迁移

- `document_id` 永远等于历史 `paper_id` 原值；不得生成替代 ID。新 Collection 的 payload 只写 `document_id` 及当前 schema 字段，不对旧 points 做 payload-only 迁移，也不从旧 payload 推断新索引内容。
- 旧 Qdrant Collection 只用于确认当前查询入口和迁移前统计；新索引的唯一输入是原件、知识文档元数据、已确认 parser/chunker/embedding。旧 point UUID、payload 与向量不要求保留，新 point ID 按当前确定性规则生成。
- JSON 元数据迁移使用 `migration_version="018-document-v1"`，输入不存在且确认是首次初始化时才可得到空集合；JSON 解码失败、根类型非 list、记录非 object 或必需 ID 重复时必须 fail-closed，返回 `MIGRATION_INPUT_INVALID`，不得把空列表写回。迁移前创建同目录只读备份，临时文件写入后 `fsync` 文件与目录再 `os.replace`；异常只保留原文件和备份，重复运行无副作用。
- `source_sha256` 表示当前原件字节 hash；重建前的旧记录保持 `indexed_source_sha256=null`、`source_hash_state="legacy_unknown"`，不得把当前摘要冒充旧 embedding 来源。候选 Collection 中每个文档必须在解析前后双检原件 hash，一致后写入 `indexed_source_sha256` 并转为 `verified`。
- 原件成功提交后是不可变对象，不提供原位修改或同 ID 覆盖；删除成功后重新提交生成新的 `document_id`，不建立版本链。重建中的多次 hash 只用于发现损坏或越界文件变更，不代表支持原位更新。
- 迁移报告必须记录元数据迁移前后记录数、`document_id/paper_id` 集合、stored basename、时间、论文元数据、原件 hash，以及候选 Collection 的文档/point 数与 fingerprint。默认任何候选构建异常都不得删除原件或元数据；本次 Task06-B 已由用户明确授权一次性清理已确认 `status=failed` 且解析错误为 `PDF_EMPTY` 的 42-byte 空壳原件及其 metadata 行，必须先生成可恢复备份并逐项核对 ID/尺寸/hash，除此之外仍不得删除或覆盖数据。

### 旧索引全量替换与 Collection 切换

- 重建只允许通过 `python -m backend.app.knowledge_base.rebuild_index` 显式执行，不由页面首次打开、GET、服务启动或普通问答隐式触发。无参数默认 dry-run；实际替换必须带 `--confirm-replace`。恢复只允许 `--resume-switch <run-id>`、`--resume-finalize <run-id>`，失败候选只允许 `--cleanup-failed <run-id>`。命令不自动结束服务；检测到应用或 Qdrant 正被占用时应停止并给出操作提示。
- 正式元数据记录是重建目标的权威集合；目录中的孤立文件只写入报告，不自动导入、删除或索引。权威集合为空返回 `NO_DOCUMENTS_TO_REBUILD`，不得创建候选或修改当前入口。preflight 必须校验全部目标元数据、唯一原件、记录 hash、PDF/Markdown 解析、目标 v1/v2 配置、embedding 和 Qdrant 可用性；任一缺失、损坏或配置不可用即在创建候选前失败。dry-run 可以完整解析，但 embedding、Collection write 和 metadata write 调用必须为 0。
- 构建阶段创建唯一 `papers_rebuild_<run-id>` 候选物理 Collection，使用已确认的 PDF/Markdown parser、v1/v2、SourceProvenanceBundle、现有 dense+sparse embedding 与索引写入能力。候选未完成前，查询入口不得指向它。
- 所有可重建文档必须同时生成 v1 和 v2。v2 模型不可用、发生规则降级、任一文档解析/embedding/upsert 失败时，本次候选失败并自动删除未验证候选；当前查询入口保持不变，下次从头构建，不做逐文档续跑。不得提交半套候选，也不得用规则降级结果冒充成功 v2。
- 候选验证至少覆盖：每个元数据文档有原件且记录 hash 匹配；PDF/Markdown 均成功解析；v1/v2 均非规则降级且每文档/版本至少一个 chunk；point ID 唯一；chunk_index 无重复和缺口；dense/sparse 均存在且维度符合当前配置；payload schema、source hash、anchors、配置 fingerprint 和 canonical index fingerprint 正确；受控 dense 与 sparse 查询均命中候选。所有硬门通过才可标记 `ready_to_switch`。
- 首次迁移若 `papers` 仍是物理 Collection：保持服务停止，删除旧物理 Collection，再创建稳定 alias `papers → candidate`。alias 创建失败时保留候选、保持服务停止并返回 `INDEX_ALIAS_SWITCH_FAILED`；重复执行 switch 必须幂等。此时不恢复旧 Collection。
- 后续迁移若 `papers` 已是 alias：使用 Qdrant alias update 原子指向新候选，确认查询成功后删除旧物理 Collection。候选验证前或 alias 切换失败时不得删除当前物理 Collection。
- alias 成功后才原子提交知识文档状态、`indexed_source_sha256`、索引统计和 Task04 定义的 manifest；提交失败进入 `finalize_pending`，保留新 Collection 且禁止正常服务，只能幂等补写，不恢复旧索引。确认全部新 manifest 后再删除旧 schema/run 的派生 manifest；旧 manifest 在此之前不得作为可用结果返回。
- Collection/alias 与运行记录不一致、存在多个无法归属的候选或状态文件不足以唯一证明动作时返回 `INDEX_TOPOLOGY_AMBIGUOUS`，不得自动推断、切换或删除。脚本成功后生成脱敏报告；报告不得包含原文、向量正文、绝对路径或凭据。
- 因候选 Collection 与当前查询入口隔离，不实现逐文档 `must_not`、`LegacyUpgradeStore`、point/vector snapshot、启动恢复或旧索引回滚。允许的维护窗口必须在部署说明和验收报告中记录。

#### 候选写入 Port 与 dry-run 零副作用

- 候选构建必须通过唯一 `CandidateIndexPort`，输入显式包含 `destination_collection`、`document_id`、`chunker`、版本化 parser/chunker/embed 配置与已经计算的 `SourceProvenanceBundle`；输出为不含用户原文的 write receipt。该 Port 只允许创建/写入传入候选 Collection，payload 必须写 `document_id`，不得隐式使用 `KB_COLLECTION`、`paper_id`、更新 metadata、删除当前 Collection points 或调用现有带副作用的 `index_paper_chunker()`。
- 可复用现有 parser/chunker/embed 纯能力；现有 `upsert_chunks()` 只有在参数化为显式 `destination_collection`、显式 payload identity 且不触发 metadata/delete 后才能被候选 Port 调用。正式单文档索引与全库候选索引最终都必须复用该 Port，禁止复制 embedding/Qdrant 写入实现。
- dry-run 不创建正式 runtime 目录、不获取写锁、不调用 embedding、不创建/删除/写入 Collection，不写 metadata、原件、manifest 或 commit marker；结果只输出到 stdout/调用方内存。必须分别注入并断言 `embedding/collection_create/upsert/delete/alias/metadata/source/manifest/runtime/lock` 写计数全部为 0。dry-run 可并发执行；开始和结束均只读检查全局锁，期间出现真实 run 时结果标记 `PREFLIGHT_STALE`，不得用于 confirm 放行。

#### 全局锁、状态机与崩溃恢复

- 真实 `confirm-replace`、resume、cleanup 使用 create-exclusive 全局锁 `.sdd/runtime/spec-018/rebuild.lock`，字段固定为 `schema_version,run_id,owner,pid,host,token,command,started_at,heartbeat_at`。只有持有相同 token 的进程能 heartbeat 或释放；正常/异常退出在 `finally` 中尝试释放。进程崩溃后的锁不得按时间自动抢占，只能通过显式 `--recover-stale-lock <run-id>`，且必须同时证明 PID 不存在、run state 与 topology inventory 唯一匹配、没有正在执行的 Qdrant 动作；否则返回 `REBUILD_LOCK_AMBIGUOUS`。
- 每个破坏性动作前先持久化 `intent`，字段包含 `sequence,action,candidate,previous_target,expected_topology_digest,started_at`；动作后再持久化 `observed`，包含 fresh topology、结果和时间。state、intent、observed 均以临时文件、文件/目录 fsync 和原子替换写入。
- `resume-switch` 接受 `ready_to_switch` 或 `switching`，但必须依据 intent 与 fresh topology 收敛：首次切换中，`papers` 仍为旧物理 Collection时可继续删除并建 alias；旧物理已不存在、alias 不存在且已验证候选唯一存在时只创建 alias；alias 已唯一指向候选时直接进入 finalizing；其余情况均 `INDEX_TOPOLOGY_AMBIGUOUS`。后续切换中，alias 仍指旧目标时可重做原子更新，已指候选时进入 finalizing，其余拒绝。
- `resume-finalize` 接受 `finalizing` 或 `finalize_pending`，按 finalize bundle 逐项比对并幂等补写，任何已完成步骤必须验证 hash 后跳过。只有最终 commit marker 写入并重新读取验证成功才转 `completed`；中间崩溃保持正常服务关闭。

#### Topology Inventory 与候选生命周期

- 每次 build/switch/cleanup 前都生成字段封闭的 `TopologyInventoryV1`：`physical_collections[]`、`aliases[{name,target}]`、`candidate_collections[]`、`run_directories[]`、`active_generation`、`state_run_id/status/candidate`、`inventory_digest`。数组规范排序后计算 digest；不得记录向量或原文。
- 允许新 build 的唯一拓扑是：没有未决 run/candidate，且 `papers` 要么是单一物理 Collection、要么是唯一 alias 且 target 存在。允许 switch 的唯一拓扑由当前 run intent 证明；允许 cleanup 的对象必须是同一 run 的未验证候选且未被任何 alias 指向。多个候选、候选名冲突、未知 alias、alias target 缺失、候选被其他 alias 引用、state/marker/run 目录不一致均返回 `INDEX_TOPOLOGY_AMBIGUOUS`。
- 未验证候选删除失败进入 `cleanup_pending`，记录 `candidate,run_id,validation_state,delete_attempt,last_error_code,topology_digest` 并保持停服、阻止新的破坏性 run；`--cleanup-failed <run-id>` 只在 state 与 fresh inventory 双重匹配时重试，确认候选不存在才转 `cleaned/failed`。已验证但尚未 switch 的候选禁止 cleanup，只允许 resume-switch。删除超时或结果未知不得假定成功。

| TopologyInventoryV1 类型 | dry-run | 新 build | resume-switch | resume-finalize | cleanup | 服务 |
|---|---|---|---|---|---|---|
| 唯一旧物理 `papers`，无候选/未决 run | 允许 | 允许 | 拒绝 | 拒绝 | 拒绝 | 可按旧索引受限启动，inspection 返回重建提示 |
| 唯一 `papers` alias 且 target 存在，无候选/未决 run | 允许 | 允许 | 拒绝 | 拒绝 | 拒绝 | 允许 |
| 同 run 已验证唯一候选，状态 `ready_to_switch/switching` | 只读诊断 | 拒绝 | 按 FSM 允许 | 拒绝 | 拒绝 | 停止 |
| alias 已指同 run 候选，状态 `finalizing/finalize_pending` | 只读诊断 | 拒绝 | 仅确认 switch 已完成 | 按 bundle 允许 | 拒绝 | 停止 |
| 同 run 未验证候选，状态 `cleanup_pending`，且未被 alias 引用 | 只读诊断 | 拒绝 | 拒绝 | 拒绝 | 允许 | 停止 |
| 多候选、未知 alias、目标缺失、state/marker 不一致 | 只读诊断并报歧义 | 拒绝 | 拒绝 | 拒绝 | 拒绝 | 停止并人工审计 |

#### Candidate Validation V1

- Task02A 必须冻结 `candidate-rebuild-run.schema.json`、`topology-inventory.schema.json` 与 `candidate-validation.schema.json`；每层 object 均固定 `additionalProperties:false`。validation 至少包含 `schema_version,run_id,candidate_collection,topology_digest,documents[],collection_totals,config_fingerprints,query_probes,collection_fingerprint,validated_at`。
- `documents[]` 每项固定含 `document_id,media_type,source_sha256,indexed_source_sha256,parser_version` 以及 v1/v2 各自的 `chunk_count,point_ids,chunk_indexes,payload_schema_version,chunker_config_fingerprint,embedding_config_fingerprint,model_config_fingerprint,llm_used,anchor_count,unmapped_count,dense{name,dimension,all_finite,vector_digest},sparse{name,point_count,all_indices_sorted,all_values_finite,total_nnz,vector_digest},payload_digest,anchor_digest`。vector digest 只保存 canonical SHA-256，不保存向量正文；v2 的 `llm_used` 必须为 true，规则降级不得通过。
- collection fingerprint 对按 `(document_id,chunker,chunk_index,point_id)` 排序后的稳定字段做 UTF-8、键排序、无空白 JSON SHA-256；不得包含向量值或原文正文，但必须包含 dense 维度/finite、sparse nnz/digest、payload/anchor/config digest。`query_probes` 至少分别记录 dense/sparse 的 query digest、top document IDs 和 candidate 命中布尔值。Task02B 与 Task06 必须通过公开 builder 重新计算，不接受人工填写的报告值。

#### 旧上传链路关闭矩阵

- Task04 必须消费固定基线 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`。顶层、inventory file、entry、test 均为 `additionalProperties:false`；顶层字段固定为 `schema_version,inventory_git_revision,inventory_digest,inventory_digest_algorithm,inventory_files[],closed_enums,entries[],tests[],review_status`。每个 entry 固定为 `entry_id,entry_kind,route_or_symbol,current_behavior,target_behavior,allowed_callers,forbidden_calls,required_test_ids,current_status,required_status`；每个 test 固定为 `test_id,entry_ids,assertions,command,exit_code,status,evidence_paths`。
- 枚举封闭为：`entry_kind={route,route_helper,application,store,index,task,maintenance}`、`current_status={open,closed,blocked,not_applicable}`、`required_status={closed}`、`review_status={baseline_frozen,implementation_ready,verified,rejected}`、`test_status={pending,passed,failed,blocked}`。固定基线允许以 `open/pending/baseline_frozen` 描述尚未实现的真实现状；Task04-D 放行时必须更新为所有 entry `closed`、所有 required test `passed` 且 `review_status=verified`。
- inventory 固定绑定当前 Git revision、八个受控入口文件（含 `backend/app/main.py`）的 SHA-256 与排序清单摘要；实现改变任一 inventory 文件时必须重新生成 hashes/digest，并由静态 inventory 测试证明没有遗漏入口。固定基线逐项枚举实际存在的 `/api/kb/upload`、`/api/kb/papers/{paper_id}/reindex|delete`，`/api/papers/imports`、`/api/papers/import-batches`、两条 retry 别名、cancel、login、resume，相关 route helper、`KnowledgeBasePaperImportAdapter`、paper import orchestration、`save_upload/save_papers/upsert_paper/remove_paper/update_chunker_state/mark_interrupted_tasks`、index/task symbols、`main.lifespan` 的旧索引回填和全库 rebuild CLI；不存在的单数 `/api/papers/import` 是此前文档笔误，不属于兼容契约。通过标准如下：
  - 旧 upload route 被删除，或只作为不接收 `document_id` 的薄转发器调用唯一 `KnowledgeDocument` 创建入口；不得直接调用 `save_upload/upsert_paper/index_paper_chunker`。
  - source 创建使用服务端生成的新 `document_id` 与 create-exclusive 写入；已存在目标拒绝，禁止按调用方提供 ID 调用 `write_bytes/rename/replace` 覆盖。
  - `upsert_paper` 只能迁移为 metadata-only 内部能力，不能创建或修改 source；`index_paper_chunker` 只能拆出纯计算并经 CandidateIndexPort 显式写目标 Collection，不能删除当前 points 或更新 source/metadata。
  - 论文发现导入仍由同一 application 创建新文档，目标文件冲突生成新安全 basename；重复身份/hash 沿用既有去重；补偿只能删除本次新建且 owner/token 匹配的资源。
  - rebuild CLI 和后台索引入口禁止调用 upload/save-source；Task06 必须证明执行前后全部原件 hash 集合不变。
  - `main.lifespan` 必须移除旧固定 Collection 的 `backfill_chunker_defaults` 写入；启动期只允许校验 generation marker 和恢复普通 document reindex 状态，不得写 source、切 alias 或猜测 rebuild FSM。
- 固定测试至少覆盖同 ID 覆盖拒绝、同 hash 去重、同名不同内容、两个并发上传、论文导入、失败补偿、旧 route、直接 symbol 调用边界及 rebuild source-write spy=0。矩阵任一 entry 未关闭或未测试，Task04/06 不得放行。

#### Run-level Finalize Bundle

- Task03/04 必须冻结 `FinalizeBundleV1`：`schema_version,run_id,candidate_collection,alias_name,collection_fingerprint,metadata_staged_path/sha256,manifests[{document_id,chunker,staged_path,live_path,sha256}],obsolete_manifests[],bundle_sha256`。staged/live path 均必须是受控相对路径，禁止调用方提供任意路径。
- finalize 顺序固定为：在 `.sdd/runtime/spec-018/rebuild/<run-id>/finalize/` 生成全部 staged metadata/manifest → schema/hash 校验 → 文件和目录 fsync → 写并验证 finalize bundle → 幂等原子替换 live metadata/manifest → 复核全部 live hash → 清理 bundle 列出的旧派生 manifest → 最后原子写入并验证 `data/kb/index-generation.json` commit marker。marker 固定含 `schema_version,run_id,alias_name,alias_target,bundle_sha256,collection_fingerprint,metadata_sha256,manifests_digest,committed_at`。
- 正常 API/健康检查只有在 alias、live files 与 commit marker 全部相互匹配时开放；marker 缺失、损坏或不匹配一律 `INDEX_FINALIZE_REQUIRED`。`resume-finalize` 只能消费同一 run 的已验证 bundle，缺失或歧义则 fail-closed，不从旧 manifest 猜测完成态。

#### Task02A 与 Task03 的协议边界

- Task02A 不生成或持久化 `InspectionManifest`。它只产出版本化 `SourceProvenanceBundle`：`pages/blocks/chunks/anchors/source_sha256/source_parser_version/chunker_config_fingerprint/payload_schema_version`，并证明该 bundle 可由正式索引流水线生成。
- Task02A-D 实现 rebuild service/CLI，但只使用固定样本、FakeQdrant 和临时候选 Collection；Task02B 验证 bundle、候选构建、验证和切换协议，不触碰真实用户索引。Task03 在 Task02B `GO` 后定义唯一 `InspectionManifest` schema；Task04 实现持久化与 API；Task06 才执行真实全库切换和 finalize。Task03 不得反向修改 Task02A parser/chunker 语义。
- Task02A/02B 的结果必须把“功能通过”与“生产切换安全门”分开记录。允许带 `security_debt` 的功能 `GO` 只放行 Task03–05；Task06 前必须由独立 backend-tester/backend-reviewer 重新执行候选删除授权、恢复拓扑、artifact 防篡改、目录 fsync、真实 SDK stub 和故障矩阵，并取得无 P0 的生产门 `GO`。

### Markdown、page-null 与上传资源边界

- 只接受扩展名 `.md`/`.markdown`，媒体类型固定为 `text/markdown`；非空 multipart MIME 不是 `text/markdown` 时返回 415。允许 UTF-8 BOM 并在解析前剥离；非法 UTF-8 或任意 NUL 返回 400 `INVALID_ENCODING`；CRLF/CR 统一为 LF 后解析，`source_sha256` 仍对原始字节计算。上传按流累计，超过 50 MiB 立即终止并返回 413，不得先整文件读入内存。
- Markdown block 边界固定为 heading、连续 paragraph、列表（含续行/嵌套）、GFM table、fenced code、blockquote、horizontal rule 和 HTML block；每个 block 保留精确 1-based `start_line/end_line`、`heading_path`、`block_type` 和稳定 ordinal。净化 HTML 不改变其原始行范围；图片作为独立 inline 资源记录给前端 placeholder，不成为可加载资源。
- Markdown 的 `page/page_end` 永远为 null，位置字段使用 `start_line/end_line`。索引过滤不把 null 转成 0；RRF/reranker 只使用检索分数、rank、text 和 chunker，不按 page 排序或做页码运算；prompt/citation 位置显示为“行 X–Y”，绝不生成“第 0 页”；前端列表、引用和跨栏定位显示 line range，PDF 继续使用 page/page_end。空文档、长行、表格/代码块边界均需有 expected fixture。
- v1/v2 对 Markdown 复用同一 chunk DTO 和 chunker 配置 fingerprint，允许跨 block 但不得丢失 source block ranges；v1/v2 只读取各自已经写入的真实 payload，不能因 `page=null` 猜测页码、回退到另一版本切片或隐式重切分；两版本均必须按同一 `start_line/end_line` 规则生成 locator。任何 chunk 无 page 时仍必须能被检索、RRF、reranker、prompt、citation 和 UI 安全消费。解析、索引、citation 的错误使用稳定 `MARKDOWN_PARSE_FAILED`/`INVALID_ENCODING`，不泄露原始异常或路径。
- 上传预算固定：单文件 50 MiB、解析输入最多 200,000 blocks、最多 100,000 chunks、单文档 anchors 最多 400,000、manifest JSON 最大 256 MiB；上传请求累计 60 秒超时，inspection 构建 300 秒超时，Qdrant scroll/source 读取 30 秒超时。超过数量/时间返回稳定 413/503，不提交半截原件、metadata 或任务。

### Manifest 物理布局、并发恢复与删除 tombstone

- manifest 物理路径固定为 `data/kb/manifests/<validated-document-id>/<chunker>.json`；`document_id` 必须匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`，不得含路径分隔符。claim 为同目录 `<chunker>.claim`，临时文件为 `.<chunker>.<owner>.tmp`，残留临时文件只在校验 owner/mtime 后清理。
- claim 使用原子 create-exclusive，字段固定 `owner`、`pid`、`started_at`、`attempt`、`heartbeat`、`expires_at`；同一 `(document_id, chunker)` 只有一个 owner。重启扫描过期 claim，将 manifest `building` 置为可重试 `pending`、增加 attempt 并清理 claim；未过期或 ready manifest 不得被擦除。claim、manifest 和临时 JSON 读取均需 schema 校验，损坏或未知版本 fail-closed 为可诊断失败，不能按空清单继续；进度更新为 `max(old_progress, new_progress)`。
- 对已具备 provenance 的新索引，manifest 重建顺序固定为：原件 hash-before → 当前 alias 指向的 Qdrant Collection 分页 scroll → provenance/对齐 → fingerprint-after → 原件 hash-after → schema 校验 → 原子替换；该路径不得启动 embedding。旧索引缺 provenance 时返回 `INDEX_REBUILD_REQUIRED`，不得由 manifest builder 私自 embedding 或建立第二条索引链路。
- 删除先写 `data/kb/tombstones/<validated-document-id>.json`（包含 owner、started_at、attempt、targets、last_error），再按 Qdrant → manifest → 原件 → metadata 顺序处理；Qdrant 不可用时保留 tombstone 和可诊断 metadata，返回 503 `DELETE_PENDING` 与 Retry-After，后台/重试可安全继续。只有全部目标确认完成才标记 tombstone `completed` 并返回 200；不得用 `vectors_removed=false` 的 200 掩盖部分成功。

### 端点错误、缓存、分页与容量契约

- 所有错误统一为 `{error_code,message,retryable,request_id,document_id?,chunker?,task_id?,details?}`，message 为脱敏稳定摘要；不再向客户端直接暴露自由文本第三方异常。固定错误码覆盖 `SOURCE_HASH_MISMATCH`、`INDEX_REBUILD_REQUIRED`、`INDEX_FINALIZE_REQUIRED`、`INDEX_ALIAS_SWITCH_FAILED`、`INDEX_TOPOLOGY_AMBIGUOUS`、`NO_DOCUMENTS_TO_REBUILD`、`REBUILD_LOCK_AMBIGUOUS`、`CANDIDATE_CLEANUP_PENDING` 和 `PREFLIGHT_STALE`；旧 `LEGACY_UPGRADE_*`、`UPGRADE_RESTORE_FAILED` 与 `SNAPSHOT_*` 不再属于当前协议。
- 202 必须返回 `Location`（同一 inspection URL 的可重试地址）、`Retry-After: 2`、`task_id`、`status`、`progress`；409 必须返回稳定错误体、当前状态、是否可重试和建议动作；503 必须带 `Retry-After`（默认 10 秒）。上传校验失败不得写文件/metadata/任务。
- source 支持 `GET` 与 `HEAD`；HEAD 返回与 GET 相同的 ETag、Content-Length、Content-Type、Accept-Ranges 和 Content-Range 相关 headers 但无 body。原件 hash 为 ETag；manifest ETag 为 `source_sha256 + index_fingerprint + mapping_algorithm_version + cursor` 的 SHA-256。匹配 `If-None-Match` 返回 304；合法单 Range 206，完整读取 200，越界/多 Range 416。
- `GET /documents` 使用 `limit` 默认 50、上限 100 与 opaque `cursor`，响应含 `next_cursor`、`total` 和 ETag；inspection 使用 `page_size` 默认 200、上限 500 与 `cursor`，响应含 manifest 摘要、当前页的 blocks/chunks/anchors、`next_cursor` 和 total counts，不允许无限完整 JSON。单次 source Range 上限 8 MiB，manifest 256 MiB/数量上限沿用本节；超限返回 413。
- 每个端点的最大请求/构建时间、字节和数量限制必须在 schema/测试中断言；`Location`、`Retry-After`、`ETag`、`HEAD`、202/409/404/416/413/415/503 的行为不得由实现者自行解释。

### 公开 API schema v1（P0-5 冻结）

所有 JSON 成功/错误响应使用 UTF-8、稳定字段名和稳定错误码；未知字段允许向前兼容，但下列必填字段不得省略。`request_id` 由服务端生成或透传，绝不包含原文、绝对路径或第三方异常。

| 端点 | 成功响应（必填字段） | 状态/错误优先级与固定行为 |
|---|---|---|
| `GET /api/kb/documents` | `200 {documents:[KnowledgeDocumentSummary],next_cursor:string|null,total:int}`；响应带 `ETag` | 非法 `limit` 为 `400 INVALID_LIMIT`，非法/过期 `cursor` 为 `400 INVALID_CURSOR`；空库也为 200；不得因单条损坏记录返回自由文本 500 |
| `POST /api/kb/documents/upload` | `201 {document_id,media_type,file_name,source_sha256,status,chunkers,task_id:string|null}` | 先校验扩展名/MIME/编码/大小，再写入不可变新原件；不提供 PUT/PATCH/同 ID 覆盖；`415 UNSUPPORTED_MEDIA_TYPE`、`400 INVALID_ENCODING/INVALID_PDF`、`413 PAYLOAD_TOO_LARGE` 均不得写原件、metadata 或任务；受控依赖不可用为 `503 QDRANT_UNAVAILABLE` + `Retry-After` |
| `GET/HEAD /api/kb/documents/{id}/source` | GET 无 Range 为 `200`，合法单 Range 为 `206`；HEAD 无 body；均带 `ETag,Content-Type,Content-Length,Accept-Ranges`，206 另带 `Content-Range` | 文档/原件不存在分别为 `404 DOCUMENT_NOT_FOUND/SOURCE_NOT_FOUND`；非法、越界或多 Range 为 `416 INVALID_RANGE`；匹配 `If-None-Match` 为 `304` 且无 body |
| `GET /api/kb/documents/{id}/inspection` | ready/partial 为 `200 {manifest,blocks,chunks,anchors,next_cursor,total}`；每页只返回当前 `cursor` 范围；带 manifest `ETag` | 首次全库未完成为 `409 INDEX_REBUILD_REQUIRED`；正常新索引的缺失/失效清单只幂等提交一次并返回 `202`；未完成索引优先 `409 INDEX_NOT_READY`；失败清单为 `409 INDEX_FAILED`；原件/ID 错误优先 `404`；构建服务不可用为 `503 MANIFEST_FAILED/QDRANT_UNAVAILABLE` |
| `POST /api/kb/documents/{id}/reindex` | 接受任务为 `202 {task_id,document_id,chunker,status,progress,reason}`，带 `Location` 与 `Retry-After` | 已运行优先 `409 INDEX_ALREADY_RUNNING`；hash 冲突 `409 SOURCE_HASH_MISMATCH`；原件不存在 `404 SOURCE_NOT_FOUND`；依赖不可用 `503 QDRANT_UNAVAILABLE` |
| `DELETE /api/kb/documents/{id}` | 全部目标确认完成才 `200 {document_id,status:"completed",deleted:{source,metadata,manifests,vectors}}` | ID 不存在 `404 DOCUMENT_NOT_FOUND`；部分失败/待重试为 `503 DELETE_PENDING`，带 `Retry-After` 和 tombstone 状态；不得返回带 `vectors_removed:false` 的 200 |

统一错误体固定为：`{error_code:string,message:string,retryable:boolean,request_id:string,document_id?:string,chunker?:string,task_id?:string,details?:object}`。`message` 只能是脱敏稳定摘要；`details` 只能包含 schema 已列出的计数、状态、`retry_after_seconds`、`allowed_range`、`current_etag` 等非敏感值。固定码和 HTTP 映射如下：`INVALID_CHUNKER/INVALID_DOCUMENT_ID/INVALID_CURSOR`→400，`INVALID_ENCODING/INVALID_PDF/PDF_NO_TEXT`→400，`UNSUPPORTED_MEDIA_TYPE`→415，`PAYLOAD_TOO_LARGE`→413，`DOCUMENT_NOT_FOUND/SOURCE_NOT_FOUND`→404，`INDEX_REBUILD_REQUIRED/INDEX_NOT_READY/INDEX_FAILED/INDEX_ALREADY_RUNNING/SOURCE_HASH_MISMATCH`→409，`INVALID_RANGE`→416，`INSPECTION_BUILDING/MANIFEST_REBUILDING`→202，`INDEX_FINALIZE_REQUIRED/MANIFEST_FAILED/QDRANT_UNAVAILABLE/DELETE_PENDING`→503。维护命令另使用 `NO_DOCUMENTS_TO_REBUILD`、`INDEX_ALIAS_SWITCH_FAILED`、`INDEX_TOPOLOGY_AMBIGUOUS`、`REBUILD_LOCK_AMBIGUOUS`、`CANDIDATE_CLEANUP_PENDING` 和 `PREFLIGHT_STALE` 作为稳定退出错误码。所有错误均不得泄露绝对路径、原始 URL、PDF/Markdown 原文或第三方异常。

202 的响应必须带 `Location`（同一 inspection 或 reindex 任务可重试地址）、`Retry-After: 2`、`task_id`、`status`、`progress`；可重试的 409 必须带当前状态和建议动作；503 默认带 `Retry-After: 10`，并在 `details.retry_after_seconds` 重复可执行等待秒数。source 的 200/206/HEAD/304 行为、inspection/list 的 ETag 计算和 `If-None-Match` 命中行为必须按本节执行，不由实现者自行解释。

### API 容量、超时与分页上限（P0-5 冻结）

| 范围 | 固定上限/默认值 | 超限或超时行为 |
|---|---|---|
| 上传请求 | 单文件 50 MiB；流式累计；JSON 控制体 64 KiB | `413 PAYLOAD_TOO_LARGE`，立即终止且不写半截资源 |
| source | 单次 Range 最大 8 MiB；source 读取 30 秒 | `416 INVALID_RANGE` 或 `503 SOURCE_TIMEOUT`，不返回部分未声明范围 |
| inspection 输入/产物 | 200,000 blocks、100,000 chunks、400,000 anchors、manifest JSON 256 MiB | `413 PAYLOAD_TOO_LARGE`；不得保存 partial 临时文件为 ready |
| 请求/构建 | upload 60 秒；inspection build 300 秒；Qdrant scroll 30 秒 | `503 MANIFEST_FAILED` 或 `503 QDRANT_UNAVAILABLE`，保留可诊断状态并可重试 |
| documents 列表 | `limit` 默认 50、最大 100；opaque `cursor`；总数只作 metadata | 单页不得超过 100；无效 cursor 为 `400 INVALID_CURSOR` |
| inspection 清单 | `page_size` 默认 200、最大 500；opaque `cursor`；`total` 返回 block/chunk/anchor 计数 | 单页不得超过 500；不得返回无限完整 JSON |

分页 cursor 必须绑定 `document_id/chunker/schema_version`，篡改、跨文档或过期均返回 `400 INVALID_CURSOR`；cursor 不携带原文。所有上述字节、数量和时间边界必须在 API schema、fixture 与端到端测试中断言，错误优先级固定为“请求格式/媒体 → 身份/原件 → 状态冲突 → 依赖不可用”。

### Vendored PDF.js 与按 block DTO 的安全渲染

- 固定 vendored `pdfjs-dist 4.10.38`，文件位于 `frontend/vendor/pdfjs/pdf.min.mjs`、`frontend/vendor/pdfjs/pdf.worker.min.mjs`，并提交该版本的 `LICENSE` 与 `NOTICE`；主库、worker 和资源 query 版本必须一致，禁止 CDN。只允许 public `getDocument/getPage/getViewport/getTextContent/render`，禁止 iframe、浏览器原生 PDF 页跳转和 PDF.js 私有字段。
- `getDocument` 只接受同源 `/api/kb/documents/{document_id}/source`，配置 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`；不调用 annotation/form/XFA/attachment API，不执行 JavaScript、不加载远程 URL。Range、取消、损坏响应分别映射为稳定 UI 状态，主库与 worker 版本不一致直接受控失败。
- Markdown 必须按后端 `SourceBlock` DTO 逐块调用同一 `renderMarkdownBlock`：先 Marked 生成 HTML，再由 DOMPurify 使用既有禁止脚本/事件/资源策略净化，最后只把净化结果写入 block 容器；`data-block-id`/ARIA 等属性由 DOM API 设置。禁止对原始 Markdown 正则包裹、禁止未净化 `innerHTML`。图片统一替换为 textContent 生成的“图片已阻止：<原地址>”占位（长度截断 2048），不恢复 src、不发请求。缺库时只展示 `escapeHtml` 转义纯文本并显示 `RENDERER_UNAVAILABLE`。

### 修订 C：P0-5/P0-6 可审计契约补充（2026-09-08）

以下条款与 `docs/sdd/plans/018/artifacts/task-04/api-schema.json`、`api-fixture-index.json` 及 `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json` 同步；实现、测试和评审只能消费这些冻结字段，不得以实现便利自行改名或改变状态语义。

- **端点成功体的必填字段与类型**：`GET /api/kb/documents` 的 200 体固定为 `{documents:KnowledgeDocumentSummary[],next_cursor:string|null,total:int}`；每个 summary 必须含 `document_id:string`、`file_name:string`、`media_type:"application/pdf"|"text/markdown"`、`source_sha256:string`、`status:string`、`page_count:int|null` 和 `chunkers:object`。`POST /api/kb/documents/upload` 成功固定为 201 `{document_id:string,media_type:string,file_name:string,source_sha256:string,status:string,chunkers:object,task_id:string|null}`。source 是原始字节流，错误才使用统一 JSON；GET 与 HEAD 必须返回相同状态和缓存/Range headers，HEAD 永远无 body。inspection 的 200 体固定为 `{manifest:InspectionManifest,blocks:SourceBlock[],chunks:ChunkSnapshot[],anchors:SourceAnchor[],next_cursor:string|null,total:{blocks:int,chunks:int,anchors:int}}`，其中数组只对应当前 cursor 页；reindex 的 202 体固定为 `{task_id:string,document_id:string,chunker:"v1"|"v2"|"all",status:string,progress:int}`；delete 只有全部目标完成才返回 200 `{document_id:string,status:"completed",deleted:{source:bool,metadata:bool,manifests:bool,vectors:bool}}`。
- **统一错误体与稳定 code**：所有 JSON 错误固定为 `{error_code:string,message:string,retryable:boolean,request_id:string,document_id?:string,chunker?:string,task_id?:string,details?:{limit_name?:string,limit_value?:number,observed_value?:number,current_status?:string,retry_after_seconds?:number,allowed_range?:string,current_etag?:string}}`。在原 code 集合上新增 `SOURCE_HASH_MISMATCH`、`INDEX_REBUILD_REQUIRED`→409 与 `INDEX_FINALIZE_REQUIRED`→503；维护命令固定使用 `NO_DOCUMENTS_TO_REBUILD`、`INDEX_ALIAS_SWITCH_FAILED`、`INDEX_TOPOLOGY_AMBIGUOUS`、`REBUILD_LOCK_AMBIGUOUS`、`CANDIDATE_CLEANUP_PENDING`、`PREFLIGHT_STALE`。旧 `LEGACY_UPGRADE_*`、`UPGRADE_RESTORE_FAILED` 和 `SNAPSHOT_*` 从当前协议移除。不得以自由文本 `detail`、第三方异常、原始 URL、路径或原文替代 `error_code`。
- **状态码、headers 和优先级**：请求格式/媒体/Range/大小校验分别优先产生 400/415/416/413；ID 或原件不存在产生 404；索引状态冲突产生 409；依赖不可用或超时产生 503。所有 202 必须带 `Location`（inspection 使用同一 `document_id+chunker` 的 inspection URI，reindex 使用同一文档/版本的状态 URI）、`Retry-After: 2`、`task_id`、`status`、`progress`。可重试的 503 必须带 `Retry-After`（默认 10 秒）和 `details.retry_after_seconds`；`DELETE_PENDING` 另带指向同一文档删除重试 URI 的 `Location`。合法 source 单 Range 为 206 并带 `Content-Range: bytes start-end/total`；非法/越界/多 Range 为 416 并带 `Content-Range: bytes */total`。200/206/HEAD 的 ETag 为带引号的 `"sha256:<source_sha256>"`；documents ETag 对规范化 summary+cursor 计算，inspection ETag 对 `source_sha256+index_fingerprint+mapping_algorithm_version+cursor` 计算。GET/HEAD 命中 `If-None-Match` 必须返回 304、无 body；HEAD 的状态、ETag、Content-Type、Content-Length、Accept-Ranges 和适用的 Content-Range 必须与 GET 一致。
- **按领域对象冻结容量、超时和分页**：单 document 原件≤50 MiB、`file_name` UTF-8≤255 bytes、元数据控制体≤64 KiB、ID 长度≤128；单 document 最多 200,000 blocks、100,000 chunks、400,000 anchors。单 block 的规范化 UTF-8 `text`≤1 MiB、序列化 DTO≤2 MiB；单 chunk `text`≤256 KiB、序列化 DTO≤512 KiB；单 anchor 序列化 DTO≤4 KiB；单 manifest JSON≤256 MiB。上传累计 60 秒、source 读取 30 秒、每个 Qdrant scroll 页 30 秒、inspection 全量构建/映射 300 秒、manifest fsync/replace 30 秒；超时不保存临时结果为 ready，统一返回 503 `SOURCE_TIMEOUT`/`MANIFEST_TIMEOUT`/`QDRANT_UNAVAILABLE`。documents `limit` 默认 50、最大 100；inspection `page_size` 默认 200、最大 500；opaque cursor≤512 bytes；单页 JSON≤8 MiB。数量/字节上限返回 413 `PAYLOAD_TOO_LARGE`，并在 `details` 给出 `limit_name/limit_value/observed_value`；cursor 必须绑定 document、chunker 和 schema version，非法或跨文档返回 400 `INVALID_CURSOR`。
- **PDF.js vendor manifest 与 display-only 配置**：只允许本地 vendored `pdfjs-dist 4.10.38`，主库 `frontend/vendor/pdfjs/pdf.min.mjs`、worker `frontend/vendor/pdfjs/pdf.worker.min.mjs`、同版本 `LICENSE` 和 `NOTICE` 必须存在；manifest 必须逐项记录 package/version、四个相对路径、主库/worker/LICENSE/NOTICE SHA-256、资源 query 版本、`GlobalWorkerOptions.workerSrc` 和允许 API。worker 路径必须为同源本地文件且与主库版本一致；`getDocument` 只能接收同源 source URI，固定 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`、`disableAutoFetch:true`，只允许 `getDocument/getPage/getViewport/getTextContent/render`，禁止 annotation/form/XFA/attachment、JavaScript、iframe、原生 PDF 导航、私有字段和远程 URL。取消、Range、损坏响应或版本/hash 不一致必须进入稳定受控错误态。
- **Markdown 唯一安全渲染入口**：每个后端 `SourceBlock` DTO（至少 `block_id/ordinal/text/locator/heading_path/block_type`）只能调用 `renderMarkdownBlock(dto)`；在 detached template 中由 Marked 解析 `dto.text`，再由 DOMPurify 按既有禁止脚本、事件和外部资源策略净化，只有净化结果才可进入该 block container。`data-block-id`、ARIA、focus 等属性只由 DOM API 设置；禁止正则包裹原文、禁止未净化 `innerHTML`。所有 image token 必须在挂载前替换为 DOM API 创建且以 `textContent` 写入的“图片已阻止：<原地址>”纯文本（原地址最多 2048 字符），不保留 `src/srcset`、不恢复相对附件、不发网络请求。缺 Marked 或 DOMPurify 时只展示 `escapeHtml` 纯文本并返回/显示 `RENDERER_UNAVAILABLE`。

P0-5/P0-6 的机器可校验交接以 Task 04 的 `api-schema.json`/`api-fixture-index.json` 和 Task 05 的 `pdfjs-vendor-manifest.json`/`dom-contract.schema.json` 为唯一下游输入；这些文件缺失、字段/哈希/退出码不全或与本节不一致时，Task 04/05 保持阻塞，不允许实现者在代码中自行解释契约。

## 交互与数据流

1. 用户进入知识库，选择二级 Tab“切片检查”。
2. 页面显示全部知识文档及格式、索引状态；用户主动选择文档，不自动打开第一份文件。
3. 用户选择 v1 或 v2；一次只展示一个版本。
4. 若首次全库索引替换尚未完成，页面只显示 `INDEX_REBUILD_REQUIRED`；若为 `finalize_pending`，服务保持维护状态。只有新索引已生效时，缺失或失效清单才由后端幂等构建：读取原件 → 生成原文块 → 读取 Qdrant 中真实切片 → 顺序对齐 → 原子保存清单。
5. PDF 原文视图使用本地 vendored PDF.js 的公开 display API，渲染 Canvas、文本层和本项目自己的来源块高亮层；不依赖 PDF.js 内部字段。
6. Markdown 原文视图使用块级解析结果渲染，并复用现有 Marked + DOMPurify 安全链路；只显示渲染视图。
7. 点击原文块：高亮所有关联切片，并滚动到覆盖率最高且位置最近的主切片。
8. 点击切片：高亮全部关联原文块，并滚动到第一个主锚点；v2 跨页时所有相关页块均高亮。
9. 程序化滚动不反向触发新的联动，避免两栏无限抖动；只有点击或键盘激活触发跨栏跳转。
10. 桌面端左右双栏；窄屏用“原文 / 切片”切换器，联动时自动切到目标栏并保留两侧滚动位置。

## 现有实现复用与替换边界

### 必须复用

- PDF 文件校验、知识库文件存储、失败补偿与删除语义。
- `extract_pages_normalized` 的清洗语义、v1/v2 切分器、异步索引任务和状态轮询。
- Qdrant collection、确定性 point ID、dense+sparse、RRF、reranker 与引用字段。
- 现有 Marked + DOMPurify 的先净化后渲染策略。
- 论文发现导入后的身份去重和知识库 application 接口。

### 必须扩展或替换

- 把只表示 PDF 论文的存储领域对象升级为通用知识文档；保留旧 ID 和用户数据。
- 增加按文档与 chunker 读取全部实际切片的受控 application 能力。
- 增加 PDF 块坐标、Markdown 行块和多对多来源锚点。
- 增加原件读取与检查清单接口。
- 把现有单一“论文 RAG”页面拆成“问答 / 切片检查”二级 Tab。

### 禁止重复实现

- 不新建第二套 embedding、Qdrant collection、rerank、下载、PDF 安全或索引任务实现。
- 不为检查器重新运行切片并把结果冒充已有索引。
- 不允许前端提交文件系统路径；原件只通过服务端生成的文档 ID 读取。

## 边界与失败场景

- 空文件、伪 PDF、非 UTF-8 Markdown、超过现有大小上限：拒绝且不留下半截记录。
- Markdown HTML、脚本、事件属性、`javascript:` URL：净化；远程图片不请求，相对图片显示占位和原地址。
- PDF JavaScript、表单编辑、附件和远程资源：不执行、不加载。
- 原件丢失或 hash 不符：文档列表保留诊断状态，原文和检查清单接口返回受控错误；全库 preflight 失败且不切换候选，不能用旧向量掩盖损坏。
- v1/v2 未完成或失败：版本选择显示状态，不允许生成虚假清单。
- 同一 `document_id + chunker` 并发打开：只运行一个清单构建任务。
- 服务重启时残留 `building`：标记为可重试中断并重新构建，不永久卡住。
- v1 重叠导致一个原文块关联多个切片：全部返回并高亮。
- 对齐不完整：状态为 `partial`，未映射切片仍可阅读并带警告。
- 清单 JSON 损坏、schema 过期、原件 hash 或索引指纹变化：丢弃派生清单并重建，不修改原件和向量。
- 扫描 PDF 没有文本层：沿用现有失败/部分索引语义，本 spec 不引入 OCR。
- 大文档：PDF 页面按视口懒加载，右侧切片列表虚拟化或分段渲染；不得一次绘制全部 PDF 页面阻塞主线程。
- 键盘操作：文档、Tab、版本、原文块和切片均可聚焦；Enter/Space 与点击等价。
- 文件名和原文内容均视为不可信输入，不使用未净化 `innerHTML`。

## 明确不做

- 不编辑切片文本、拖动切片边界、修改切片参数或创建用户自定义切片版本。
- 不支持 Word、HTML、EPUB、LaTeX、压缩包或 Markdown 附件目录。
- 不提供 Markdown 源码视图。
- 不加载 Markdown 远程图片或相对附件。
- 不做字符级任意选区映射；首版只承诺文本块级联动。
- 不做扫描 PDF OCR、PDF 注释编辑、表单填写或脚本执行。
- 不保留旧向量 Collection、旧 manifest、逐 point 快照或长期双索引；不建立第二套 embedding/Qdrant 流程。
- 不允许原位编辑、PUT/PATCH 或同 ID 覆盖原件；用户只能删除后重新提交。
- 不在本 spec 顺手重构论文发现、聊天或 Task 账本。

## 验收方式

- 所有固定样本和期望输出归档在 `docs/sdd/fixtures/spec-018/`；每个样本同时提供原件、`*.expected.json`（manifest/anchor 期望）和 `README.md`（观察点）。实现不得用临时生成的切片替代期望输出。
- 固定 PDF 样本：`pdf-single-column-v1.pdf`（普通段落）、`pdf-two-column-v1-overlap.pdf`（双栏、v1 重叠）、`pdf-v2-cross-page.pdf`（v2 跨页）、`pdf-no-text-layer.pdf`（无文本层）和 `pdf-hostile-features.pdf`（JavaScript/表单/附件/远程 URL）。固定 Markdown 样本：`markdown-blocks.md`（标题、段落、列表、表格、代码块）和 `markdown-hostile.md`（脚本、事件属性、`javascript:`、远程图片、相对附件）。
- 每个期望文件至少断言：`schema_version`、`mapping_algorithm_version`、`document_id`、`chunker`、`status`、`progress`、`source_sha256`、`index_fingerprint`、`mapped_count`、`unmapped_count`、按 ordinal 排序的 `block_id/locator`、按 chunk_index 排序的 chunk 快照、完整 anchor 对、`coverage`、`is_primary` 和用户可见 `error`。允许的 PDF bbox 误差为相对页面宽高的 ±0.005；Markdown 行号必须精确。
- Task 02 报告必须位于 `docs/sdd/plans/018/artifacts/task-02/source-anchor-feasibility-report.md`，fixture 索引位于 `docs/sdd/plans/018/artifacts/task-02/fixture-index.json`，provenance DTO schema 位于 `docs/sdd/plans/018/artifacts/task-02/provenance-dto.schema.json`；报告中的每个原件、expected JSON 和 DTO schema 都记录 SHA-256。正常 PDF/Markdown fixture 的 expected block/chunk/anchor 集合必须 100% 匹配、bbox 最大误差 ≤0.005、Markdown 行号 100% 精确，Qdrant duplicate/gap 和检查路径写调用为 0；否则 No-Go 并自动退回 `待确认`，不得进入 Task 03。
- 对齐规范固定为：比较前对文本做 Unicode NFKC、CRLF 转 LF、去除行尾空白、连续水平空白折叠为一个空格；不跨越原文块边界。`coverage` 为规范化文本的重叠字符数除以 chunk 文本字符数（空文本为 0）；同覆盖率时按文档 ordinal、chunk_index 升序稳定排序，首项为 primary。所有关联项按该稳定顺序返回并高亮。
- `source_sha256` 为原件字节的 SHA-256；`index_fingerprint` 为从 Qdrant 实际 payload 读取的全部切片快照，按 `(chunker, chunk_index)` 排序后以 UTF-8、键排序、无空白 JSON 序列化再计算 SHA-256。当前 `mapping_algorithm_version` 固定为 `source-anchor-v2`；`source-anchor-v1` 仅保留为历史迁移证据，不得作为当前交互依据。算法或规范化规则变化必须使旧清单失效，因而 v1 清单必须重建而不能继续复用。
- 期望 manifest 还必须断言 `source_parser_version`、`chunker_config_fingerprint`、`payload_schema_version`、`indexed_source_sha256`、`source_hash_state` 和 `unmapped_reasons`；旧文档 `source_hash_state=legacy_unknown` 时不得标记为历史源 hash 已验证。
- 双向验收必须断言：原文块点击返回其全部 anchor 关联切片，默认滚动到 primary；切片点击返回其全部关联原文块，默认滚动到第一个 primary；双栏 fixture 还必须断言页面、列顺序和高亮 bbox，而不是只断言文本出现。
- 新索引中重复打开只能读取或重建派生 manifest，要求 embedding、切分和 Qdrant 写调用均为 0。旧索引缺 provenance 时固定返回 `INDEX_REBUILD_REQUIRED`，打开、刷新和服务启动均不得自动重建。
- 全库重建验收覆盖 dry-run 零写入、权威文档集合、孤立文件、空库、缺失/损坏原件、v1+v2、dense+sparse、构建失败清理、全局锁、首次 alias、后续 alias 原子切换、`resume-switch`、`finalize_pending`、`resume-finalize` 与 topology ambiguous。成功后旧 Collection 不保留；失败不删除原件和元数据。
- 旧 `papers.json` 元数据迁移覆盖：有/无原件、论文元数据存在/缺失、重复 ID、重复迁移和无时区时间。迁移后 `document_id == paper_id`，文件只保留安全 basename，原件 hash 和论文元数据可追溯；旧索引状态不冒充新索引完成态，只有 Task06 finalize 后写入新的 v1/v2 状态。
- `partial` 清单必须展示映射率、未映射数量和每项警告；未映射切片仍可阅读，单项失败不使整篇不可读。既有 `indexed_partial` 对外映射为 manifest `partial`，`pending/building/ready/failed` 的状态与 HTTP 语义按本 Spec 的端点契约一致。
- PDF 原件接口验收合法单 Range 返回 206、正确 `Content-Range`/`Content-Length`/`Content-Type` 和 `Accept-Ranges: bytes`；无 Range 返回 200 inline；非法、越界或多 Range 返回 416 且不泄露路径。伪造/穿越 document ID 返回 404 或 400，错误摘要不含绝对路径。
- 每个端点还要验证统一 error schema/codes、`Location`、`Retry-After`、`ETag`、`HEAD`、分页 cursor、limit/page_size、50 MiB/8 MiB/数量和超时边界，以及 202/409/404/416/413/415/503 的固定优先级；inspection 不返回无限 JSON。
- PDF.js 只从本地 vendored 资源和同源 document source 接口加载，版本与 worker 路径锁定在 fixture 记录；使用 public display API，不执行 PDF JavaScript、不显示可提交表单、不打开附件、不请求 PDF 内远程 URL。对 hostile PDF 使用浏览器网络记录断言除本地 source/worker 外无请求。
- Markdown 使用现有 Marked + DOMPurify 链路；脚本、事件属性、`javascript:` 被净化，远程图片和相对附件不发请求并以安全占位显示原地址；缺少任一库时展示转义纯文本。验收检查 DOM、网络记录和脚本执行计数，不能只比较可见文本。

PDF.js 依赖交接固定为 `pdfjs-dist 4.10.38`：主库 `frontend/vendor/pdfjs/pdf.min.mjs`、worker `frontend/vendor/pdfjs/pdf.worker.min.mjs`、`LICENSE`、`NOTICE` 和 `pdfjs-vendor-manifest.json` 必须同一版本提交；资源 query 版本、workerSrc 与 manifest 必须一致。`getDocument` 只能接收同源 source URL，并固定 `isEvalSupported:false`、`enableXfa:false`、`useWorkerFetch:false`、`stopAtErrors:true`；只允许 `getDocument/getPage/getViewport/getTextContent/render` display API，禁止 annotation/form/XFA/attachment、iframe、原生 PDF 页跳转、私有字段、脚本和远程 URL。取消、Range、损坏响应和版本不一致必须映射为稳定 UI 错误码，不得让异常文本直接显示。

Markdown 渲染必须消费后端 `SourceBlock` DTO（至少含 `block_id,ordinal,text,locator,heading_path,block_type`），每个 block 只通过同一 `renderMarkdownBlock(dto)` 入口：Marked 生成 HTML，DOMPurify 按现有禁止脚本/事件/外部资源策略净化，随后才写入该 block 容器；`data-block-id`、ARIA 和 focus 属性只能由 DOM API 设置。禁止对原始 Markdown 正则包裹、禁止未净化 `innerHTML`。图片不恢复 `src`、不发请求；用 `textContent` 生成“图片已阻止：<原地址>”占位，原地址最多 2048 字符。缺少 Marked/DOMPurify 时只展示 `escapeHtml` 纯文本并报 `RENDERER_UNAVAILABLE`。上述依赖、DTO、图片 placeholder 与 hostile fixture 的契约必须落盘到 `docs/sdd/plans/018/artifacts/task-05/`。
- 桌面 viewport `>= 761px` 固定为原文左栏/切片右栏；窄屏 viewport `<= 760px` 固定为“原文/切片”单栏切换器。每个 `(document_id, chunker)` 保存各栏 `scrollTop` 和当前目标 block/chunk；点击联动自动切到目标栏、恢复目标位置，程序化滚动不触发反向联动，Tab/Enter/Space 的焦点和激活结果与鼠标一致，且无横向溢出。
- 长文档 fixture 至少包含 200 页或 10,000 个切片之一；验收记录首屏可见页/切片数、初次打开时间、滚动后新增渲染数和主线程长任务，要求不得一次绘制全部 PDF 页面，切片列表必须虚拟化或分段渲染。
- 回归上传、论文检索导入、v1/v2 索引、重建、删除、问答引用、RRF 和 reranker；后端定向测试、前端静态契约、全量 pytest、部署后 HTTP 冒烟和真实浏览器验收全部通过。

### 产品使用步骤（桌面与窄屏）

1. 用户打开知识库；页面保留“问答”与新增的“切片检查”二级 Tab，不自动打开第一份文档。切换到“切片检查”后，列表展示文件名、PDF/Markdown 格式、原件状态、v1/v2 索引状态和清单状态。
2. 用户选择文档。若原件不存在，列表保留诊断状态并提示“原件不可用”，原文和清单请求显示受控 404；若列表为空，显示空状态和上传入口。
3. 用户选择 v1 或 v2，一次只展示一个版本。版本未完成或失败时显示当前状态、进度/稳定错误摘要和可执行的“重建索引”入口，不显示虚假清单。
4. 对已索引但无清单的版本，页面显示“正在构建清单”和 0–100% 单调进度；构建完成后自动刷新为 ready/partial。两个窗口同时打开只出现一个构建任务，第二个窗口复用同一状态。
5. PDF 使用原件视图：页面按视口懒加载，文本层上叠加可聚焦的来源块高亮；双栏文档按期望阅读顺序展示。Markdown 使用安全的渲染视图，块可聚焦并显示对应行范围；不提供 Markdown 源码视图。
6. 用户点击原文块或用 Enter/Space 激活：该块的全部关联切片高亮，切片栏滚动到覆盖率最高的 primary；若没有 anchor，页面保留阅读位置并显示“未映射”警告。
7. 用户点击切片或用 Enter/Space 激活：全部关联原文块高亮，原文栏滚动到第一个 primary；v2 跨页切片会高亮全部相关页。程序化滚动只改变位置，不重新触发另一栏联动。
8. 桌面端两栏同时可见，用户可分别滚动；窄屏端显示“原文/切片”切换器，一次只显示一个栏。联动时自动切换到目标栏，切换回去仍保留用户之前的滚动位置和焦点目标。
9. 用户可通过键盘依次聚焦文档、Tab、版本、原文块和切片；Enter/Space 与点击等价，状态提示使用 aria-live，切换器使用可读的 pressed/selected 状态。
10. 打开或刷新文档不得重新切片或 embedding。若首次全库重建尚未完成，页面显示稳定的“需要管理员重建索引”状态，不自动执行；`finalize_pending` 时服务保持维护状态。用户可在迁移完成后显式重建或删除，删除需二次确认；原件不可原位编辑，删除后重新提交会创建新文档 ID。
11. 对恶意 Markdown/PDF，用户只看到净化后的渲染和安全占位；浏览器网络记录没有远程资源请求，任何库缺失都降级到转义纯文本或受控错误，不执行原文中的脚本。

## 执行配置

> 2026-09-08 通过 `ollama list` 再次核实本机存在 `qwen3.8:27b-mlx` 与 `qwen3.5:9b`。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Spec、领域决策、编排和最终裁决 |
| Tech Lead / 开发主管 | 自身（当前执行任务的 Agent） | 128k（单步交接复核最低 64k；最终 Gate 签字使用 128k） | 主会话；技术复评与 Gate 签字 | 独立核对 Spec、API schema、任务交接、模型预算和 P0 门禁；不把本轮 `gpt-5.6-luna xhigh` 记为永久角色模型 |
| 产品经理 | `qwen3.5:9b` | 32k | `doc-updater` | 产品步骤与验收场景 |
| 后端开发 | `qwen3.8:27b-mlx` | 32k | `backend-dev`；每个本地 27B 子任务最多 2 个代码文件、约 150 行 | 文档模型、清单、接口、安全实现 |
| 后端评审 | `qwen3.8:27b-mlx` | 32k | `backend-reviewer`；逐子任务只评已冻结交接物 | 后端边界、迁移、并发、API schema 评审 |
| 前端开发 | `qwen3.8:27b-mlx` | 32k | `frontend-dev`；每个本地 27B 子任务最多 2 个代码文件、约 150 行 | 双栏检查器、PDF/Markdown 渲染实现 |
| 前端评审 | `qwen3.8:27b-mlx` | 32k | `frontend-reviewer`；逐子任务只评已冻结交接物 | DOM、PDF.js 依赖、XSS 与版本契约评审 |
| 后端 / 前端测试 | `qwen3.5:9b` | 32k | `backend-tester` / `frontend-tester` | 单端回归 |
| 跨端验收 | `qwen3.5:9b` | 32k | `tester` | 集成、真实浏览器、部署验收 |

Task02A–05 的每个子任务必须先读取上游命名产物。只有使用本地 Ollama 模型时，dispatch manifest 才限制最多 2 个代码文件、目标约 150 行；使用线上 Agent 时取消资源限制，但仍须保持文件白名单与单一职责。任何子任务失败不得由主会话静默代行，须按项目规则缩小范围、重试并在报告中记录。

### Task 02A–05 交接产物索引

| Task | 可交接子任务 | 固定产物路径（下游只读） | 放行门槛 |
|---|---|---|---|
| 02（历史） | 首轮 fixture/probe/Go-No-Go | `docs/sdd/plans/018/artifacts/task-02/source-anchor-feasibility-report.md` 及既有 fixture/schema | 已完成，结论永久保留为 `NO-GO`，不放行下游 |
| 02A | PDF provenance、Markdown parser、SourceProvenanceBundle、候选 rebuild service/CLI | `docs/sdd/plans/018/artifacts/task-02a/implementation-contract.md`、`source-provenance-bundle.schema.json`、`candidate-rebuild-run.schema.json`、`topology-inventory.schema.json`、`candidate-validation.schema.json`、`candidate-rebuild-report.md`、`backend-test-report.md` | A–C 保留；D 的 Port/FSM/dry-run/build/validate/switch/finalize/cleanup 模拟与 E 评审通过；不得触碰真实索引 |
| 02B | 重新执行固定样本、后端 hostile 安全与 Tech Lead Go/No-Go | `docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md`、更新后的 fixture-index/schema hash | 仅 `GO` 放行 Task03；浏览器网络硬门明确留给 Task05 |
| 03 | 03-A DTO/schema/finalize bundle、03-B JSON metadata migration、03-C application boundary、03-D reviewer | `docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`、`finalize-bundle.schema.json`、`index-generation.schema.json`、`migration-fixture-index.json`、`migration-report.md` | ID/原件/元数据无损、旧向量零迁移、run-level finalize/marker、损坏输入 fail-closed |
| 04 | 04-A source/chunk DTO、04-B manifest store、04-C routes/upload closure/health schemas、04-D backend tests/review | `docs/sdd/plans/018/artifacts/task-04/api-schema.json`、`upload-closure-matrix.json`、`api-fixture-index.json`、`backend-contract-report.md`；fixture 在 `docs/sdd/fixtures/spec-018/api/` | inspection no-embedding；旧入口全关闭；未迁移/finalize、immutable source 与删除通过 |
| 05 | 05-A vendored dependency、05-B DOM skeleton、05-C renderer、05-D interaction/contract test/review | `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md`；fixture 在 `docs/sdd/fixtures/spec-018/frontend/` | 本地资源/worker 版本与许可证一致，block DTO 安全渲染、图片不请求、DOM/键盘/窄屏联动通过 |

### P0-7 A/B/C/D 串行交接矩阵

下表是 Task02A–05 的唯一分派边界。本地 Ollama 子任务最多列 2 个已点名代码/资源文件、目标约 150 行；线上 Agent 不受该资源上限，但不得越过列出的职责和允许范围。D 阶段只做报告/评审/交接，不得补写未冻结实现。

| Task | A | B | C | D | 固定 artifacts / fixture | 放行门槛 |
|---|---|---|---|---|---|---|
| 02A | PDF block provenance（已完成） | Markdown provenance + SourceProvenanceBundle（已完成） | CandidateIndexPort + rebuild FSM/CLI + FakeQdrant | backend tests/review + Tech Lead | `implementation-contract.md`、bundle/run/topology/validation schemas、`candidate-rebuild-report.md`、`backend-test-report.md` | dry-run 零写、候选硬门、switch/finalize/cleanup 故障恢复通过才进入 02B |
| 02B | 冻结首轮证据与新 revision | fixture 精确重放 | 后端 hostile/no-write + candidate rebuild audit | Tech Lead Go/No-Go closure | `artifacts/task-02b/source-anchor-revalidation-report.md`、fixture/schema hash | 仅严格 `GO` 放行 Task03；真实索引留给 Task06 |
| 03 | DTO/manifest/finalize/generation schemas；Tech Lead 128k | JSON metadata migration；`backend-dev` 27B/32k | application/import boundary；`backend-dev` 27B/32k | review/handoff；`backend-reviewer` 32k + Tech Lead 最低 64k | knowledge-document、inspection-manifest、finalize-bundle、index-generation schemas；migration report/fixture | ID/原件/元数据无损、旧向量零迁移、marker-last、fail-closed、幂等、评审通过 |
| 04 | source/chunk DTO；`backend-dev` 27B/32k | manifest/finalize store；`backend-dev` 27B/32k | routes/upload closure/health schema；`backend-dev` 27B/32k | tests/review/handoff；`backend-tester` 9B + reviewer/Tech Lead | `api-schema.json`、`upload-closure-matrix.json`、`api-fixture-index.json`、`backend-contract-report.md` | inspection 无写入；旧入口关闭、rebuild/finalize、immutable source 与删除通过 |
| 05 | vendored PDF.js；`frontend-dev` 27B/32k | DOM skeleton；`frontend-dev` 27B/32k | block renderer；`frontend-dev` 27B/32k | interaction/contract/review；`frontend-tester` 9B + reviewer/Tech Lead | `artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md`；frontend fixture | vendor/hash/许可证一致，DOM/安全/键盘/窄屏联动通过 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec 018 与任务计划 | 本文件 | — | 完成 |
| 02 | 首轮来源锚点可行性审计 | [`task-02-validate-source-anchor-feasibility.md`](../plans/018/task-02-validate-source-anchor-feasibility.md) | 01、上一版 Spec 已确认 | 已完成（`NO-GO`） |
| 02A | 实现生产级来源定位与候选重建基础 | [`task-02a-production-provenance-foundation.md`](../plans/018/task-02a-production-provenance-foundation.md) | 本修订重新评审并确认 | 暂停（A–C 已完成；D/E 待确认） |
| 02B | 重新验证来源锚点（Go/No-Go） | [`task-02b-revalidate-source-anchor-feasibility.md`](../plans/018/task-02b-revalidate-source-anchor-feasibility.md) | 02A | 待执行 |
| 03 | 定义通用文档协议与迁移 | [`task-03-document-contract-and-migration.md`](../plans/018/task-03-document-contract-and-migration.md) | 02B Go | 待执行 |
| 04 | 实现后端检查清单与接口 | [`task-04-backend-document-inspection-api.md`](../plans/018/task-04-backend-document-inspection-api.md) | 03 | 待执行 |
| 05 | 实现前端双栏切片检查器 | [`task-05-frontend-chunk-inspector.md`](../plans/018/task-05-frontend-chunk-inspector.md) | 04 | 待执行 |
| 06 | 真实全库索引替换、恢复与性能验收 | [`task-06-legacy-backfill-and-resilience.md`](../plans/018/task-06-legacy-backfill-and-resilience.md) | 04、05 | 待执行 |
| 06E | 修复来源锚点稀疏映射与双向定位回归 | [`task-06e-sparse-source-anchor-correction.md`](../plans/018/task-06e-sparse-source-anchor-correction.md) | 04、05、当前 v1 manifest | 已完成 |
| 06F | 修复 PDF 上传失败与错误可见性 | [`task-06f-pdf-upload-repair.md`](../plans/018/task-06f-pdf-upload-repair.md) | 04、06E 当前服务 | 已完成 |
| 07 | 评审、验收、部署与复盘 | [`task-07-review-acceptance-deploy-retro.md`](../plans/018/task-07-review-acceptance-deploy-retro.md) | 06 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/018-requirement-review.md`（历史修订通过；全库替换修订待重新评审）
- 技术评审：`docs/sdd/reviews/018-tech-review.md`（历史修订通过；全库替换修订待重新评审）
- 验收评审：`docs/sdd/reviews/018-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-08 | 用户 | 要求在个人知识库新增切片检查 Tab，支持原文与切片双栏、PDF/Markdown 原格式展示和双向点击定位 |
| 2026-09-08 | 用户 | 通过 Grill with Docs 访谈确认 PDF + Markdown、文本块级映射、单版本切换、只读检查、Markdown 仅渲染、重叠全高亮、旧文档自动补建与窄屏切换 |
| 2026-09-08 | 架构师（自身） | 核对现有 PDF-only 存储、v1/v2 payload、前端知识库和安全渲染能力，创建本 Spec 与 Task 02–07 |
| 2026-09-08 | 开发主管 / 需求评审修订轮（gpt-5.6-luna xhigh） | 根据首轮打回意见补齐产品使用步骤、端点状态契约、固定 PDF/Markdown 样本、manifest/anchor oracle、旧 paper_id→document_id 补建、no-embedding 观测、PDF.js/Markdown 安全、Range 和窄屏滚动验收；需求评审重新判定为通过，Spec 仍待用户确认与技术评审 |
| 2026-09-08 | 架构师（自身） | 根据技术评审 P0-1～P0-4 补齐并冻结 Task 02 命名产物/阈值与 No-Go 状态动作、PDF provenance/PDF.js 坐标映射、`paper_id→document_id` 与旧 Qdrant payload fail-closed 迁移、Markdown page-null 契约，以及 manifest 原子并发/恢复、hash+fingerprint 双检和删除 tombstone；技术复评与用户确认前仍不得执行代码任务 |
| 2026-09-08 | 架构师（自身） | P0-5/P0-6 复核补丁统一 `INVALID_LIMIT` 与 `INVALID_CURSOR` 映射，并明确 Task 04/05 的机器可校验 schema、fixture、依赖哈希和 DOM 绑定证据是唯一下游输入；缺证据时保持阻塞，未修改业务代码 |
| 2026-09-08 | 架构师（自身） | 根据技术评审 P0-5～P0-7 补齐公开 API v1 成功/错误 schema、稳定错误码与 202/409/404/416/413/415/503、Location/Retry-After/ETag/HEAD、容量/超时/分页上限；冻结 PDF.js 4.10.38 vendored 许可证/NOTICE/worker/display-only 与 Marked+DOMPurify block DTO/图片占位；为 Task 02–05 增加可交接子任务、固定产物路径、≤2 代码文件/约 150 行的本地 27B 约束，并单列 Tech Lead 上下文预算。技术复评前仍不得执行代码任务 |
| 2026-09-08 | 架构师（自身） | P0-7 最终小修订将 Task 02–05 的 A/B/C/D、固定 artifacts、API/fixture/PDF.js/DOM 交接证据、单端报告与放行门槛汇总成表格；Task 02 增加只读 02-D handoff closure，Tech Lead 单步最低 64k、最终 Gate 128k；未修改业务代码 |
| 2026-09-08 | 用户 / 架构师（Grill with Docs） | 首轮 Task02 `NO-GO` 后确认：旧 PDF 首次打开自动重建已有 v1/v2；原地替换前保存完整 point/vector 快照，失败恢复、成功删除；块级 bbox 为硬门，word 可选；partial 可切换；v2 模型失败不降级；失败后仅手动重试；hostile 浏览器零网络硬门移至 Task05。本轮仅修订文档，新增 Task02A/02B，待重新评审和确认 |
| 2026-09-08 | 架构师（自身） | 根据自动重建独立技术评审的四项 P0，冻结 application hybrid_search 唯一包装与 dense+sparse 共用 must_not、既有单线程 executor 上的文档级 operation/claim/启动恢复、reindex-snapshot-v1 的 canonical/base64 round-trip schema，并将 Task02A 限定为 SourceProvenanceBundle、Task03 才定义 manifest；重新提交技术复审，未修改业务代码 |
| 2026-09-08 | 独立需求/技术评审 | 自动重建修订需求复审通过；技术首轮打回四项 P0，补齐后复审通过。用户已明确确认执行，Spec 转为实施中并仅放行 Task02A |
| 2026-09-09 | 用户 / 架构师（Grill with Docs） | 用户确认旧 Qdrant vectors 与旧 manifest 可全部丢弃，但原件、元数据和身份必须保留；经三轮访谈冻结候选 Collection、显式 dry-run/confirm、全程停服、v1+v2、dense+sparse、全局锁、alias/finalize 恢复、拓扑 fail-closed、不可变原件与删除再提交新 ID。Spec 退回待确认，暂停业务代码并重新评审 |
| 2026-09-09 | 架构师（自身） | 保留 Task02A-A～C 已提交成果，废弃未提交 D1 snapshot 草稿；将 Task02A-D 改为仅在 fixture/FakeQdrant 上验证的 rebuild service/CLI，将真实全库替换推迟至 Task06，并同步 Task02B/03/04/06/07 与计划 README |
| 2026-09-09 | 独立技术评审 / 架构师（自身） | 全库替换技术复审首轮打回 7 项 P0 和 1 项 P1；补齐 CandidateIndexPort、dry-run 全写 spy、锁 token/stale recovery、intent/observed FSM、TopologyInventoryV1、cleanup_pending、CandidateValidationV1、FinalizeBundleV1/generation marker 及不可变上传迁移矩阵，重新提交技术复审；未修改业务代码 |
| 2026-09-09 | 独立技术评审 / 架构师（自身） | 第二轮确认 P0-1～P0-7 已关闭，仅打回旧 upload 关闭证据；新增字段封闭的 `upload-closure-matrix.json`，逐项覆盖旧 route、store/index symbol、论文导入、CLI 与后台入口，并设为 Task04/06 放行门；未修改业务代码 |
| 2026-09-09 | 架构师（自身） | 按真实代码修正 upload closure 基线：枚举复数 imports/batches、retry/cancel/login/resume 与全部 route helper/application/store/index/task/maintenance 入口，冻结枚举、测试结构、Git revision、逐文件 hash 和 inventory digest；基线状态与实现后放行状态明确分离；未修改业务代码 |
| 2026-09-09 | 独立技术复审 / 架构师（自身） | 复审发现 lifespan 旧索引回填及四个 store 直接写 symbol 漏项；补入 `main.py`、`save_papers/remove_paper/update_chunker_state/mark_interrupted_tasks`，重算八文件 inventory digest，并新增启动期 fail-closed 测试门；未修改业务代码 |
| 2026-09-09 | 用户确认 / 架构师（自身） | 独立需求评审通过，技术设计门最终 `GO`；用户明确“继续开发…开始执行”，全库索引替换修订由 `待确认` 转为 `已确认` 并进入 `实施中`。仅放行 Task02A-D，Task04/06 实现门保持未放行 |
| 2026-09-09 | 用户优先级决策 / 架构师（自身） | 用户要求安全加固问题先留账、优先完成功能；Task02A/02B 改为分别记录功能门与生产切换安全门。已知安全债务不再阻塞 Task03–05，但全部转为 Task06 真实 Qdrant/`--confirm-replace` 前置硬门；不降低真实数据操作门禁 |
| 2026-09-10 | 用户授权 / 架构师（自身） | 真实 dry-run 确认 4 条 `status=failed`、42-byte、`PDF_EMPTY` 空壳原件无可恢复内容；用户明确授权一次性删除这些原件及对应 metadata 行。清理前必须备份并逐项核对固定 ID/大小/hash，其他数据范围不变 |
| 2026-09-10 | 用户 / 架构师（自身） | 用户澄清标题或原文块应只关联实际包含它的少数切片；运行时 53,120 条关系证实 `source-anchor-v1` 的任意模糊正分全连接为错误实现。用户确认改用 `source-anchor-v2` 真实来源区间稀疏映射；新增 Task 06E，在实现前落盘其范围、重建和验收约束。 |
| 2026-09-10 | 用户 / 架构师（自身） | 用户反馈无法上传新的 PDF。健康检查、去重上传和固定样本新文档上传均返回成功，但历史请求出现 400；新增 Task 06F，要求先复现实际失败条件，再修复 PDF 上传兼容性及前端错误可见性，不改变现有知识库数据。 |
| 2026-09-10 | 架构师（自身） | Task06F 已完成：真实服务验证常见 PDF multipart MIME 与新文档上传均返回 201，非法 PDF 返回稳定 400；前端错误显示已刷新为 `app.js?v=19`，探针文档已清理。 |
