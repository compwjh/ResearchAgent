# Task 04：实现后端文档 Manifest 与检查接口

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task03；被依赖：Task05、06；当前状态：`已完成（功能门 GO；生产切换债务留至 Task06）`

## 一句话目标

实现通用 PDF/Markdown 文档、原件安全读取、manifest 持久化和真实切片检查 API，并在全库重建完成前明确返回维护状态。

## 当前证据

- Task02A 已提供 PDF/Markdown provenance 与 `SourceProvenanceBundle`。
- Qdrant payload 可提供 v1/v2、chunk_index、text、page range、section 与向量结果。
- 旧索引不再自动升级；首次全库重建由 Task06 显式执行。

## 前置门禁

- Task03 schema、元数据迁移、CONTEXT/ADR 和 backend-reviewer 结论通过。
- API schema 与错误码先冻结再实现。

## 思维链（可审计执行设计）

1. 复用 Task02A provenance 和现有 index/application，不重写 parser、chunker 或 embedding。
2. manifest 只读取当前稳定 alias 中已经写入的真实 chunks；检查路径不 embedding。
3. 在首次全库 finalize 完成前，inspection 返回 `INDEX_REBUILD_REQUIRED`；若 `finalize_pending`，服务健康状态为 `INDEX_FINALIZE_REQUIRED`。
4. 原件只读且不可覆盖；删除通过 tombstone 清理全部派生物与元数据。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 内容 | 固定产物 |
|---|---|---|---|
| 04-A | backend-dev | source/chunk DTO 与 application 读取边界 | `source-chunk-report.md` |
| 04-B | backend-dev | manifest store、claim、FinalizeBundle staging/commit marker、原子写入、恢复与 tombstone | `manifest-store-report.md` |
| 04-C | backend-dev | documents/upload/source/inspection/reindex/delete、旧上传入口关闭、健康门禁与 API schema | `api-schema.json`、`upload-closure-matrix.json` |
| 04-D | backend-tester + backend-reviewer | 后端回归、逐 entry 关闭审计与交接 | `api-fixture-index.json`、`backend-contract-report.md` |

仅使用本地 Ollama 时，每个开发子任务最多修改 2 个已点名代码文件、目标约 150 行；线上 Agent 取消资源上限，但仍须遵守白名单和单一职责。

## API 固定契约

- `GET /api/kb/documents`：200 `{documents,next_cursor,total}`，支持 ETag、limit≤100、opaque cursor。
- `POST /api/kb/documents/upload`：201；只接受 PDF 与 UTF-8 Markdown；原件不可变，不提供 PUT/PATCH/同 ID 覆盖。
- `GET/HEAD /api/kb/documents/{id}/source`：完整读取 200、合法单 Range 206、匹配 ETag 304；HEAD 无 body。
- `GET /api/kb/documents/{id}/inspection`：ready/partial 返回真实 manifest；全库未重建为 409 `INDEX_REBUILD_REQUIRED`；正常新索引缺失/失效 manifest 才返回 202 `INSPECTION_BUILDING`。
- `POST /api/kb/documents/{id}/reindex`：只在首次全库 finalize 完成后接受 v1/v2/all 的显式单文档重建。
- `DELETE /api/kb/documents/{id}`：只有原件、元数据、manifest、当前 Collection vectors 均清理成功才返回 200；部分失败为 503 `DELETE_PENDING`。
- 服务发现 `finalize_pending` 时健康状态为 `INDEX_FINALIZE_REQUIRED`，不得进入正常请求服务。

统一错误体为 `{error_code,message,retryable,request_id,document_id?,chunker?,task_id?,details?}`。稳定错误码至少覆盖 `INDEX_REBUILD_REQUIRED`、`INDEX_FINALIZE_REQUIRED`、`SOURCE_HASH_MISMATCH`、`INDEX_NOT_READY`、`INDEX_FAILED`、`INDEX_ALREADY_RUNNING`、`INSPECTION_BUILDING`、`MANIFEST_FAILED`、`QDRANT_UNAVAILABLE`、`SOURCE_TIMEOUT` 和 `DELETE_PENDING`；禁止旧 `LEGACY_UPGRADE_*`、`SNAPSHOT_*` 升级错误。

## 固定 Prompt

```text
你是 Spec018 Task04 的 backend-dev。只读取 Spec018、Task02A/02B、Task03/04 固定交接物和 knowledge_base/paper_discovery 的受控 application 入口。允许修改分派清单点名的 backend 文件、对应后端测试和本 Task artifacts；禁止修改 frontend、用户 data/kb、真实 Qdrant、Git 历史。

实现通用 PDF/Markdown 导入、不可变原件安全读取、按当前 papers alias 中真实 payload 构造 ChunkSnapshot/anchors/manifest、FinalizeBundle staging/幂等提交、index-generation commit marker、documents/source/inspection/reindex/delete API 和全库 rebuild/finalize 健康门禁。必须复用 Task02A parser/provenance 与现有切分、embedding、Qdrant、异步任务、下载安全和论文导入能力。inspection/manifest 重建不得调用 embedding 或写 Qdrant；旧索引缺 provenance 只返回 INDEX_REBUILD_REQUIRED，不得自动升级或建立第二条索引链路。

必须迁移或关闭旧 upload 入口，证明任何路由都不能按调用方传入的已有 document_id 直接覆盖原件。固定测试覆盖同 ID、同 hash、同文件名和并发上传：同 ID 覆盖拒绝；重复 hash 沿用既有去重结果；同名不同内容创建安全的新 stored_name/document_id；成功后原件字节 SHA-256、metadata `source_sha256` 与 source ETag 三者一致。重建 Port 不得调用 upload/save_upload 或更新原件。

必须消费并更新固定基线 `upload-closure-matrix.json`，不得重新凭聊天记录发明入口清单。基线已绑定真实 inventory revision、八个文件（含 `main.py`）hash/digest，并枚举 `/api/kb/upload`、旧 reindex/delete、`/api/papers/imports`、`/api/papers/import-batches`、两条 retry 别名、cancel、login、resume、route helpers、store 的 source/metadata/task 直接写函数、index/task/application symbols、lifespan 旧索引回填与 rebuild CLI；单数 `/api/papers/import` 是已纠正的文档笔误。实现改变 inventory 后重新生成 hash/digest；每项写清 current/target behavior、allowed callers、forbidden calls、required test IDs 和关闭状态。04-D 放行要求所有 entry=`closed`、required test=`passed`、exit_code=0、证据路径非空且 review_status=`verified`；任一 entry 仍能覆盖已有 source、绕过 CandidateIndexPort 或未被 inventory 测试发现时必须打回。

验证路径穿越、Range/HEAD/ETag、Markdown 编码和 XSS 输入、并发 manifest、重启、partial、hash 失效、immutable source、删除 tombstone、分页、容量和稳定错误体。返回固定结果字段、测试退出码、产物、风险和主 Agent 后续动作。
```

## 子 Agent 必须返回

- 结果状态、摘要、改动文件和职责。
- API/schema/fixture/report 路径。
- `upload-closure-matrix.json` 的逐 entry 关闭状态与测试映射。
- 测试命令、退出码、数量与耗时。
- inspection 的 embedding、切分、Qdrant write 计数。
- 并发、损坏、重启、删除和健康门禁观测。
- 风险阻塞与主 Agent 后续动作。

## 主 Agent 校验

- API 只以受校验 `document_id` 解析服务器路径。
- inspection 的 embedding、切分、upsert/delete 均为 0。
- 旧索引只得到 `INDEX_REBUILD_REQUIRED`，不存在自动升级入口。
- 不存在同 ID 覆盖原件的接口。
- 旧 upload route 已迁移到同一不可变 application 入口或明确移除；并发/重复 hash/同名 fixture 有证据。
- 矩阵覆盖全部路由、store/index symbols、论文导入、CLI 与后台入口，且没有 `open/unknown` entry。
- 矩阵 inventory revision、逐文件 SHA-256 与 digest 已按实现后的代码重新计算；静态 inventory 测试能因新增未登记 route/helper/task symbol 而失败。
- manifest 使用临时文件、fsync 和原子替换，不留下半截 JSON。
- commit marker 之前 API/health 均拒绝正常读取；resume-finalize 可从每个文件/marker 故障点幂等完成。

## 实时监控

在线 Agent 正常运行时等待主动返回；仅在明确超时、错误、长期无返回或用户要求时读取日志。

## 测试与验收标准

- 固定 fixture 覆盖空库、未重建、finalize pending、非法媒体/编码/Range、容量/超时、202 manifest、409 状态、404、503、ETag/HEAD/cursor。
- finalize fixture 覆盖 metadata/每份 manifest/旧 manifest 清理/commit marker 前后故障；marker 缺失或 hash 不符不得返回 completed。
- block≤200,000、chunk≤100,000、anchor≤400,000、manifest≤256 MiB；上传≤50 MiB；inspection page_size≤500。
- 旧 KB、论文导入、问答、单文档重建和删除回归通过。

## 风险、停止条件与回滚

- 发现需要改变安全下载语义或引入第二套 embedding/Qdrant 流程时停止并更新 Spec。
- 测试不得修改用户 data 或真实 Qdrant。

## 产出物

- 后端实现、API schema、upload closure matrix、fixture、测试和评审报告。

## 执行结果

- 04-A～04-C 已实现通用 PDF/Markdown 文档读取、不可变原件、manifest claim/store、检查分页、ETag/Range/HEAD、重建与删除错误契约。
- 功能门最终验证：定向测试 `47 passed`，加 foundation 后 `54 passed`；相关 KB/paper 回归 `394 passed, 29 subtests`；Ruff、py_compile、JSON Schema、matrix hash 与 `git diff --check` 均 exit 0。
- backend-reviewer 对 Task05 功能门签字 `GO`，backend-tester 签字 `PASS`。
- `upload-closure-matrix.json` 保持真实状态 `baseline_frozen`：17/17 entry 仍 open、12/13 test 仍 pending。legacy 单文档 reindex、论文导入第二路径、startup recovery、CandidateIndexPort 收口与生产 cutover 继续阻塞 Task06，但不阻塞 Task05。
- 本 Task 未读写真实 `data/kb`，未访问真实 Qdrant，未执行任何 Collection/alias 变更。

## 变更日志

- 2026-09-08：创建 Task，并冻结 API/容量/PDF/Markdown 安全契约。
- 2026-09-09：移除首次打开 legacy upgrade、snapshot restore 和仅手动重试协议；改为全库 rebuild/finalize 门禁与不可变原件。
- 2026-09-09：根据独立技术复审 P1 增加逐路由/逐 symbol 的 `upload-closure-matrix.json`，作为 Task04/06 放行硬门。
- 2026-09-09：两轮独立测试/评审打回后，修复 inspection durable claim、分页/ETag/202、reindex source hash/404/400/409、DELETE_PENDING、Markdown MIME 与统一错误体；功能门最终通过，生产闭环债务显式移交 Task06。
