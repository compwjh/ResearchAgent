# Task 04：实现后端文档检查清单与接口

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task 03；被依赖：Task 05、06；当前状态：`待执行`

## 一句话目标

在现有知识库流程上增加 PDF/Markdown 通用导入、原件安全读取、真实切片快照和可重建来源锚点接口。

## 当前证据

- 现有上传只认 PDF 魔数，索引流水线只接收按页文本。
- Qdrant payload 已含 v1/v2、chunk_index、text、page range、section。
- 现有异步索引队列和状态更新可复用。

## 前置门禁

- Task 03 协议、迁移与 backend-reviewer 结论通过。
- API schema 与状态码先写测试，再实现。

## 执行阶段

1. 增加 Markdown 安全读取和块级解析，接入现有 v1/v2 切分与索引。
2. 增加按文档、chunker scroll Qdrant 实际 payload 的 application 方法。
3. 生成 PDF bbox / Markdown lines 原文块并建立多对多锚点。
4. 实现清单原子保存、指纹失效、幂等并发构建和重启恢复。
5. 实现 documents、source、inspection、reindex、delete API。
6. 迁移现有调用方，不复制旧 papers 路由逻辑。

## 子 Agent 分派

- 实现：backend-dev；评审：backend-reviewer；回归：backend-tester。
- 允许修改：`backend/**` 与后端测试；禁止修改 frontend、用户 data 和 Qdrant 实例。

## 可交接子任务与固定产物（P0-5/P0-7）

Task 04 必须先冻结 API schema，再按 application、manifest、routes、tests 顺序交接。每个本地 `qwen3.8:27b-mlx` 子任务最多修改 2 个已点名代码文件、目标约 150 行；不能把 Markdown parser、Qdrant scroll、manifest store 和 routes 合并成一个任务。各子任务串行执行，前一步报告未落盘不得开始后一步。

| 子任务 | 执行者/上下文 | 允许范围 | 固定输出/验收 |
|---|---|---|---|
| 04-A source/chunk DTO + application | `backend-dev` / 27B / 32k | 最多 2 个 backend 文件 + 对应测试；只接入真实 payload、page-null 和 block locator | `docs/sdd/plans/018/artifacts/task-04/api-schema.json` 中 DTO/成功响应片段；`source-chunk-report.md` |
| 04-B manifest store/concurrency | `backend-dev` / 27B / 32k | 最多 2 个 backend 文件 + 对应测试；claim、临时文件、fsync/replace、hash/fingerprint 双检、recovery/tombstone | `manifest-store-report.md`；报告必须含并发/重启/损坏/删除 fixture 结果 |
| 04-C routes/error schema | `backend-dev` / 27B / 32k | 最多 2 个 route/schema 文件 + 对应测试；documents/upload/source/HEAD/inspection/reindex/delete | 更新 `api-schema.json` 的所有成功/错误体、202/409/404/416/413/415/503、Location/Retry-After/ETag/分页/容量/超时 |
| 04-D backend regression/review | `backend-tester` / `qwen3.5:9b` / 32k；`backend-reviewer` / 27B / 32k | 只跑测试/评审，不补业务实现 | `docs/sdd/plans/018/artifacts/task-04/backend-contract-report.md`、`api-fixture-index.json`；报告列命令、退出码、观测值和 blocking issue |

固定 fixture 位于 `docs/sdd/fixtures/spec-018/api/`，至少覆盖空库、非法媒体/编码/Range、50 MiB/8 MiB/数量/超时边界、202 构建、409 未就绪/重复任务、404、503 tombstone，以及 ETag/HEAD/cursor。API schema 必须定义统一错误体 `{error_code,message,retryable,request_id,document_id?,chunker?,task_id?,details?}`，禁止把自由文本 `detail` 当客户端契约。inspection 成功响应只能返回当前页 `manifest/blocks/chunks/anchors/next_cursor/total`，不得无限 JSON；检查路径 spy 的 embedding/切分/upsert/delete 必须为 0。

### 修订 C：API schema v1 精确冻结（P0-5）

`api-schema.json` 不得只写示例，必须把下列内容作为机器可校验字段落盘：

- `GET /api/kb/documents`：200 `{documents,next_cursor,total}`；summary 必填 `document_id/file_name/media_type/source_sha256/status/page_count/chunkers`，`limit=50`、最大 100、cursor≤512 bytes；`INVALID_LIMIT/INVALID_CURSOR`→400，响应带基于规范化 summary+cursor 的 ETag。
- `POST /api/kb/documents/upload`：201 `{document_id,media_type,file_name,source_sha256,status,chunkers,task_id}`；50 MiB 原件、64 KiB JSON 控制体和 60 秒累计超时；扩展名/MIME 失败→415 `UNSUPPORTED_MEDIA_TYPE`，编码/PDF 失败→400 `INVALID_ENCODING/INVALID_PDF`，大小或对象数量失败→413 `PAYLOAD_TOO_LARGE`，均不得写入半截原件、metadata 或 task。
- `GET/HEAD /api/kb/documents/{id}/source`：无 Range 200，合法单 Range 206；GET/HEAD 状态及 `ETag,Content-Type,Content-Length,Accept-Ranges` 一致，206 另带 `Content-Range`，HEAD 无 body；`If-None-Match` 命中→304；未知文档/原件→404 `DOCUMENT_NOT_FOUND/SOURCE_NOT_FOUND`；非法、越界、多 Range→416 `INVALID_RANGE` 且带 `Content-Range: bytes */total`；source 读取超时→503 `SOURCE_TIMEOUT`。
- `GET /api/kb/documents/{id}/inspection`：ready/partial 200 `{manifest,blocks,chunks,anchors,next_cursor,total}`，`page_size=200`、最大 500、单页 JSON≤8 MiB；缺失/失效清单→202 `INSPECTION_BUILDING`，必须有 `Location,Retry-After:2,task_id,status,progress`；未完成索引/failed/snapshot 冲突→409 `INDEX_NOT_READY/INDEX_FAILED/SNAPSHOT_CONFLICT`；构建依赖不可用或 300 秒超时→503 `MANIFEST_FAILED/MANIFEST_TIMEOUT/QDRANT_UNAVAILABLE`。
- `POST /api/kb/documents/{id}/reindex`：202 `{task_id,document_id,chunker,status,progress}`，`chunker` 仅 v1/v2/all，带 `Location` 与 `Retry-After:2`；重复执行→409 `INDEX_ALREADY_RUNNING`；原件缺失→404 `SOURCE_NOT_FOUND`；依赖不可用→503 `QDRANT_UNAVAILABLE`。
- `DELETE /api/kb/documents/{id}`：全目标完成才 200 `{document_id,status:"completed",deleted:{source,metadata,manifests,vectors}}`；部分失败只返回 503 `DELETE_PENDING`，带 tombstone 状态、同文档重试 `Location` 和 `Retry-After:10`，不得以 `vectors:false` 返回 200。

统一错误体固定为 `{error_code,message,retryable,request_id,document_id?,chunker?,task_id?,details?}`；稳定 code、状态映射和优先级必须与 Spec 修订 C 一致。`details` 只允许非敏感的 `limit_name/limit_value/observed_value/current_status/retry_after_seconds/allowed_range/current_etag`。所有 400/404/409/413/415/416/503 fixture 都必须比对 body 字段和 headers，不能只断言 status code。

### 修订 C：容量、超时和分项上限验收

fixture index 必须分别记录 document≤50 MiB、block≤200,000 且 text≤1 MiB/DTO≤2 MiB、chunk≤100,000 且 text≤256 KiB/DTO≤512 KiB、anchor≤400,000 且 DTO≤4 KiB、manifest≤256 MiB；还要记录 upload 60 秒、source/Qdrant page 30 秒、inspection 300 秒、manifest fsync 30 秒，以及 documents limit 100、inspection page_size 500、cursor 512 bytes。超过字节/数量返回 413 `PAYLOAD_TOO_LARGE`，超时返回对应 503；任何 partial 临时结果不得标记 ready。

### Task 04 放行门

仅当 `api-schema.json`、`api-fixture-index.json`、四份子任务报告和 reviewer 结论均落盘且通过，Task 05 才能读取 API。发现 schema 变化、状态码歧义、Range/缓存 header 缺失或检查路径写调用非 0，必须暂停并更新 Spec/本 Task 产物，不得把问题下放给前端。

### 固定 Prompt

```text
你是 Spec018 的 backend-dev。只读取 Spec018、Task03/04 结果和 knowledge_base/paper_discovery 的受控 application 入口。实现通用 PDF/Markdown 导入、原件安全读取、按真实 Qdrant payload 生成切片快照、来源锚点和可重建清单。必须复用现有切分、embedding、Qdrant、异步任务、下载安全和论文导入能力；不得重新 embedding 旧文档，不得新建第二套索引。仅修改 backend 与对应测试。验证路径穿越、Range、Markdown 编码/XSS 输入、并发构建、重启、partial 映射、hash 失效和旧 PDF。按固定结果字段回传，并给出开始结束与总耗时。
```

## 主 Agent 校验

- API 只能以 document_id 解析服务器路径，客户端不能传路径。
- 旧文档构建清单时 embedding mock 断言为 0 次。
- Qdrant 查询带 document_id + chunker 过滤。
- 清单写入使用临时文件 + 原子替换，不留下半截 JSON。

## 测试与验收

- 后端定向测试覆盖全部端点、状态码、媒体类型和边界。
- 旧 KB、论文导入、问答、重建和删除回归通过。

## 风险、停止与回滚

- 发现需要改变既有切片文本、point ID 或安全下载语义时停止并更新 Spec。

## 产出物

- 后端实现、schema、迁移和测试；评审与测试报告。

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-08：架构师创建 Task。
- 2026-09-08：根据 P0-5/P0-7 拆为 04-A DTO/application、04-B manifest store、04-C routes/schema、04-D 回归/评审；冻结 API schema、fixture-index、报告路径及每个本地 27B ≤2 文件/约 150 行约束。
- 2026-09-08：修订 C 补齐 API v1 每个端点的成功/错误体、稳定 code、状态码优先级、headers、容量/超时/分页和 fixture 逐字段断言；仅更新计划文档，未修改业务代码。
- 2026-09-08：P0-5 复核补丁明确 `limit` 的 `INVALID_LIMIT` 与 `cursor` 的 `INVALID_CURSOR` 分离；Task 04 只能以 `api-schema.json`/`api-fixture-index.json` 作为下游机器可校验契约，缺字段、header、优先级或退出码时保持阻塞，未修改业务代码。
- 2026-09-08：P0-7 最终小修订确认 04-A～04-D 串行交接，固定 API schema/fixture/单端报告路径；每个本地 27B 子任务最多 2 个代码文件、约 150 行，缺少 backend-tester/reviewer 结论不得放行 Task 05。
