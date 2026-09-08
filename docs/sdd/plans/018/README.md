# Spec 018 任务索引：知识文档切片检查器

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md)
> 当前状态：`实施中`；需求评审与技术复审已通过，用户已明确要求开始 Spec018；当前只执行 Task02 Go/No-Go，未通过前不得修改业务代码。

## 执行顺序

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-validate-source-anchor-feasibility.md) | 验证 PDF/Markdown 来源锚点与既有切片对齐 | Spec 已确认 | 实施中 |
| [03](./task-03-document-contract-and-migration.md) | 定义通用文档、清单和无损迁移协议 | 02 Go | 待执行 |
| [04](./task-04-backend-document-inspection-api.md) | 后端导入、原件和检查清单接口 | 03 | 待执行 |
| [05](./task-05-frontend-chunk-inspector.md) | 双栏/窄屏检查器与双向联动 | 04 | 待执行 |
| [06](./task-06-legacy-backfill-and-resilience.md) | 旧文档补建、恢复、安全和性能 | 04、05 | 待执行 |
| [07](./task-07-review-acceptance-deploy-retro.md) | 三道评审、部署、运行时验收和复盘 | 06 | 待执行 |

## 全局执行门禁

- Task 02 前必须完成 018 需求评审、技术评审和 Spec 状态确认。
- 下游只读取本目录 Task、Spec、指定代码和上游落盘结果，不依赖聊天历史。
- 后端与前端代码必须分别由对应角色 Agent 执行和评审。
- 不允许为检查器重复实现 embedding、Qdrant、PDF 下载、安全校验或索引任务。
- 每个 Task 的执行结果必须回填真实改动、命令、退出码、耗时、风险和后续动作。

## 需求评审修订轮门禁（2026-09-08）

- Spec 018 已把桌面/窄屏产品旅程、PDF/Markdown 固定样本、manifest/anchor 期望字段、旧 `paper_id → document_id` 补建矩阵、no-embedding/no-reslice spy、PDF.js/Markdown 网络安全、Range 状态码、双栏联动和 `scrollTop` 保留写入验收方式；需求评审结论为“通过”。
- 技术复审已通过；用户已明确确认 Spec，状态已进入 `实施中`。Task 02 仅允许执行来源锚点验证，不得提前修改业务代码；No-Go 自动回退 Spec 状态并停止后续任务。
- Task 02 必须把固定样本与 `*.expected.json` 落盘到 `docs/sdd/fixtures/spec-018/`，并对 `source_sha256`、`index_fingerprint`、映射对、primary、bbox/行号误差和 `partial` 判定给出 Go/No-Go 结果；不得只以口头结论替代样本。
- Task 03–06 必须保留验收观测字段：embedding/切分/Qdrant 写操作调用次数、point ID/payload fingerprint、原件 hash、manifest 状态/进度、Range headers、浏览器网络请求、面板/焦点/滚动位置；实现或测试发现契约变化时先暂停并更新 Spec。
- Task 07 只能在后端/前端单端验收和跨端浏览器验收均能复现上述 oracle 后进入部署；评审文档必须引用实际 fixture、命令、退出码和观测值。

## 技术复评 P0-1～P0-4 冻结门禁（2026-09-08）

- **P0-1 / Task 02 硬门**：只认 `artifacts/task-02/source-anchor-feasibility-report.md`、`fixture-index.json`、`provenance-dto.schema.json` 三个命名产物；fixture 必须位于 `docs/sdd/fixtures/spec-018/`，逐样本保存原件/expected/DTO SHA-256、版本、命令/退出码、provenance 统计、映射率、bbox/行号误差、Qdrant point/调用次数和 `GO|NO-GO`。正常 PDF bbox 最大误差 ≤0.005、Markdown 行号 100% 精确、期望集合 100% 匹配且检查路径写/embedding/切分调用为 0 才能 GO；否则 Task 02 标记 `阻塞/需修订`，Spec 保持或退回 `待确认`，停止 Task 03–07 与全部业务代码任务。
- **P0-2 / Task 03 前置**：必须先冻结 `paper_id == document_id`、旧 payload 双读/别名与 payload-only 迁移，证明 point UUID/向量/数量/fingerprint 不变；JSON 迁移必须 versioned、备份、`fsync + replace`、损坏输入 fail-closed 且可恢复，旧索引 hash 只能记为 `legacy_unknown`。缺字段、重复/缺号或 hash 不可证明时不得猜测、覆盖或标记 `ready`。
- **P0-3 / Task 04 前置**：必须冻结 `.md/.markdown`、`text/markdown`、BOM/NUL/UTF-8/CRLF、流式 50 MiB 上限和 block/heading/line-range；v1/v2 只能消费各自真实 payload，Markdown `page/page_end=null` 在过滤、RRF、reranker、prompt、citation、排序和 UI 中不得转成页码 0，并保留行号定位。
- **P0-4 / Task 04–06 前置**：必须按 Spec 的 manifest 物理布局、同目录临时文件 `fsync + os.replace`、原子 claim/owner/attempt/recovery、schema fail-closed、原件 hash-before/after 与 Qdrant fingerprint-before/after 双检执行；删除必须先写 tombstone，部分失败返回 `DELETE_PENDING`/`Retry-After` 并可重试，不能以 200 掩盖孤儿向量或混合快照。
- 本轮完成 Spec/Plan/Task 02–05 的协议冻结与技术复审；当前只允许运行 Task 02 的只读/固定样本 Go/No-Go。Task 03–07 和业务代码修改仍受 Task 02 `GO` 门禁约束。

## 技术复评 P0-5～P0-7 冻结门禁（2026-09-08）

- **P0-5 / API contract gate**：所有 documents/upload/source（含 GET/HEAD）/inspection/reindex/delete 端点必须先消费 Spec 的公开 API schema v1。成功体、统一错误体、稳定 `error_code`、202/409/404/416/413/415/503 优先级、`Location`、`Retry-After`、`ETag`、`Content-Range`、304、cursor、limit/page_size、50 MiB/8 MiB/数量/超时上限必须同时落盘在 `docs/sdd/plans/018/artifacts/task-04/api-schema.json` 与 `api-fixture-index.json`。schema 或状态码有歧义时 Task 04 停止，不能让前端自行解释。
- **P0-6 / renderer dependency gate**：Task 05 只允许本地 vendored `pdfjs-dist 4.10.38`，主库/worker 路径、SHA-256、`LICENSE`、`NOTICE`、query 版本和 display-only `getDocument` 配置必须落盘在 `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`。Markdown 必须按 `SourceBlock` DTO 经 Marked→DOMPurify→block container，图片只显示 textContent placeholder 且零网络请求；DOM/依赖/fixture 证据缺失时停止 Task 05–06。
- P0-5/P0-6 的实现只能消费上述 Task 04/05 机器可校验交接物；`INVALID_LIMIT` 与 `INVALID_CURSOR` 必须分离，PDF.js/worker/license/NOTICE/hash、display-only 配置和 `renderMarkdownBlock(SourceBlock)` DOM 绑定证据缺失或与 Spec 不一致时，不得由实现者自行解释或补写契约。
- **P0-7 / handoff gate**：Task 02–05 必须按各 Task 文档的 A/B/C/D 子任务串行交接。每个本地 27B 子任务 dispatch manifest 最多列 2 个代码/资源文件、目标约 150 行；超出必须冻结当前 schema 后另拆子任务。固定报告/schema/fixture 路径不存在、SHA-256/命令/退出码/观测字段缺失，或下游需依赖聊天摘要时，一律不放行。

### P0-7 A/B/C/D 交接矩阵（与 Spec 018 同步）

| Task | A → B → C → D | 固定 artifacts / 报告 | 交接门槛 |
|---|---|---|---|
| 02 | fixture → provenance/mapping → Tech Lead Go/No-Go → handoff closure | `docs/sdd/plans/018/artifacts/task-02/source-anchor-feasibility-report.md`、`fixture-index.json`、`provenance-dto.schema.json` | 仅 `GO` 放行；D 只读核验，不补实现 |
| 03 | DTO/schema → JSON migration → Qdrant/application → reviewer + Tech Lead | `docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`、`migration-report.md`、`qdrant-migration-report.md` | schema/fixture/report 完整且评审通过 |
| 04 | source/chunk DTO → manifest store → routes/API schema → backend test/review | `docs/sdd/plans/018/artifacts/task-04/api-schema.json`、`api-fixture-index.json`、`backend-contract-report.md` | body/code/header/容量/超时和 no-embedding oracle 全通过 |
| 05 | vendored PDF.js → DOM skeleton → block renderer → interaction/contract review | `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md` | 依赖 hash、DOM 安全、图片零请求、键盘/窄屏联动全通过 |

每个本地 27B 子任务最多接收 2 个已点名代码/资源文件，目标约 150 行；Tech Lead 单步交接复核最低 64k、最终 Gate 签字使用 128k。缺少固定产物、报告、退出码或观测值时保持 `待执行/阻塞`，不得依赖聊天摘要或“实现后补文档”。

### 交接产物速查

| Task | 必须先存在的下游输入 | 负责人签字 |
|---|---|---|
| 02 | `artifacts/task-02/source-anchor-feasibility-report.md`、`fixture-index.json`、`provenance-dto.schema.json` | Tech Lead：仅 `GO` 放行 |
| 03 | `artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`、`migration-report.md`、`qdrant-migration-report.md` | backend-reviewer + Tech Lead |
| 04 | `artifacts/task-04/api-schema.json`、`api-fixture-index.json`、`backend-contract-report.md` | backend-tester/backend-reviewer |
| 05 | `artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md` | frontend-tester/frontend-reviewer |

缺少任一交接物、状态门、报告结论或固定观测值，必须保持对应 Task `待执行/阻塞`，不能以“实现后补文档”替代。

## Plan 变更日志

- 2026-09-08：根据技术评审 P0-5～P0-7 增加 API schema/容量与状态码门禁、PDF.js/Markdown 安全依赖门禁、Task 02–05 固定交接物和本地 27B 子任务粒度；技术复评前仍禁止运行 Task 02 或修改业务代码。
- 2026-09-08：修订 C 仅补强 P0-5/P0-6：要求 Task 04 artifact 逐端点冻结成功体、统一错误体、稳定 code、状态码优先级、headers、超时/数量/字节/分页上限；要求 Task 05 manifest 固定 `pdfjs-dist 4.10.38` 的四类 SHA-256、许可证/NOTICE、worker 和 display-only 配置，并冻结按 `SourceBlock` DTO 的 Marked→DOMPurify→block container 唯一路径及 textContent 图片占位。未产生代码变更。
- 2026-09-08：P0-5/P0-6 复核补丁修正 `INVALID_LIMIT`/`INVALID_CURSOR` 的逐端点映射，并将 Task 04/05 机器可校验 schema、fixture、依赖哈希与 DOM 绑定证据明确为唯一下游输入；未产生代码变更。
- 2026-09-08：P0-7 最终小修订将 Task 02–05 的 A/B/C/D 串行边界、固定 artifacts、报告/fixture 和 Tech Lead 64k/128k 预算汇总成表格；未产生代码变更。

## 技术复评修订 C：P0-5/P0-6 只读交接门禁（2026-09-08）

- **P0-5 / Task 04**：`api-schema.json` 必须逐一列出 documents/upload/source GET+HEAD/inspection/reindex/delete 的成功体字段类型、统一错误体字段、稳定 `error_code` 全集及 HTTP 映射；fixture index 必须记录 202/409/404/416/413/415/503 的 body 与 headers（含 `Location`、`Retry-After`、`ETag`、`Content-Range`、304、HEAD），以及请求格式→身份/原件→状态冲突→依赖不可用的优先级。文档、block、chunk、anchor、manifest 的数量/字节/超时/分页固定值必须与 Spec 一致，缺任何字段或存在歧义即阻塞 Task 04/05。
- **P0-6 / Task 05**：`pdfjs-vendor-manifest.json` 必须逐项保存 `pdfjs-dist:4.10.38`、主库/worker/LICENSE/NOTICE 路径和 SHA-256、query 版本、workerSrc、允许 public display API 及 `getDocument` display-only 配置；不得接受 CDN、私有 API、PDF 脚本、annotation/XFA/form/attachment 或远程 URL。`dom-contract.schema.json`/frontend fixture 必须证明每个 `SourceBlock` 走唯一 `renderMarkdownBlock`，Marked 后 DOMPurify 再入 block container，图片只以 textContent placeholder 出现且零网络请求；缺库只允许转义纯文本和 `RENDERER_UNAVAILABLE`。任一证据缺失，Task 05–06 保持 `待执行/阻塞`。
- 本修订已通过最终技术复审；Spec 已进入 `实施中`，但 Task 02 未形成 `GO` 证据前不得生成业务实现产物或运行后续任务。
