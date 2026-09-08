# Spec 018 任务索引：知识文档切片检查器

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md)
> 当前状态：`实施中`；自动重建修订需求/技术复审已通过且用户已确认。当前执行 Task02A；Task02B `GO` 前不得启动 Task03–07。

## 执行顺序

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-validate-source-anchor-feasibility.md) | 首轮来源锚点可行性审计 | 上一版 Spec 已确认 | 已完成（NO-GO） |
| [02A](./task-02a-production-provenance-foundation.md) | 生产级 PDF/Markdown provenance 与旧索引安全升级基础 | 修订版 Spec 已确认 | 实施中 |
| [02B](./task-02b-revalidate-source-anchor-feasibility.md) | 用正式实现重新验证来源锚点 | 02A | 待执行 |
| [03](./task-03-document-contract-and-migration.md) | 定义通用文档、清单和无损迁移协议 | 02B Go | 待执行 |
| [04](./task-04-backend-document-inspection-api.md) | 后端导入、原件和检查清单接口 | 03 | 待执行 |
| [05](./task-05-frontend-chunk-inspector.md) | 双栏/窄屏检查器与双向联动 | 04 | 待执行 |
| [06](./task-06-legacy-backfill-and-resilience.md) | 旧文档补建、恢复、安全和性能 | 04、05 | 待执行 |
| [07](./task-07-review-acceptance-deploy-retro.md) | 三道评审、部署、运行时验收和复盘 | 06 | 待执行 |

## 全局执行门禁

- Task02A 的重新需求/技术评审和用户确认已完成；Task02B 必须在 02A 实现、测试和评审通过后再启动。
- 下游只读取本目录 Task、Spec、指定代码和上游落盘结果，不依赖聊天历史。
- 后端与前端代码必须分别由对应角色 Agent 执行和评审。
- 不允许为检查器重复实现 embedding、Qdrant、PDF 下载、安全校验或索引任务。
- 每个 Task 的执行结果必须回填真实改动、命令、退出码、耗时、风险和后续动作。

## 需求评审修订轮门禁（2026-09-08）

- Spec 018 已把桌面/窄屏产品旅程、PDF/Markdown 固定样本、manifest/anchor 期望字段、旧 `paper_id → document_id` 补建矩阵、no-embedding/no-reslice spy、PDF.js/Markdown 网络安全、Range 状态码、双栏联动和 `scrollTop` 保留写入验收方式；需求评审结论为“通过”。
- Task02 首轮严格 `NO-GO` 后，自动重建修订需求复审通过；技术复审首轮打回四项 P0，补齐后通过。用户已确认，Task02A 已放行。
- 首轮 Task02 fixture、`*.expected.json` 和 `NO-GO` 报告不可改写。Task02A 产出正式 parser/provenance/升级恢复基础；Task02B 必须重新引用原件与 expected hash，并给出新的严格 Go/No-Go。
- Task 03–06 必须保留验收观测字段：embedding/切分/Qdrant 写操作调用次数、point ID/payload fingerprint、原件 hash、manifest 状态/进度、Range headers、浏览器网络请求、面板/焦点/滚动位置；实现或测试发现契约变化时先暂停并更新 Spec。
- Task 07 只能在后端/前端单端验收和跨端浏览器验收均能复现上述 oracle 后进入部署；评审文档必须引用实际 fixture、命令、退出码和观测值。

## 技术复评 P0-1～P0-4 冻结门禁（2026-09-08）

- **P0-1 / Task02A–02B 解阻门**：首轮 `artifacts/task-02/` 保持历史只读。02A 固定生产级 PDF block provenance、Markdown 行块、provenance-aware v1/v2、旧 points/vector 快照与失败恢复；02B 以原 fixture 精确重放。正常 PDF block bbox 最大误差 ≤0.005、Markdown 行号 100%、期望集合 100% 匹配才可 GO；word 坐标不再是硬门。Hostile 浏览器网络硬门移至 Task05。
- **P0-2 / Task 03 前置**：必须先冻结 `paper_id == document_id`、旧 payload 双读/别名与 payload-only 迁移，证明 point UUID/向量/数量/fingerprint 不变；JSON 迁移必须 versioned、备份、`fsync + replace`、损坏输入 fail-closed 且可恢复，旧索引 hash 只能记为 `legacy_unknown`。缺字段、重复/缺号或 hash 不可证明时不得猜测、覆盖或标记 `ready`。
- **P0-3 / Task 04 前置**：必须冻结 `.md/.markdown`、`text/markdown`、BOM/NUL/UTF-8/CRLF、流式 50 MiB 上限和 block/heading/line-range；v1/v2 只能消费各自真实 payload，Markdown `page/page_end=null` 在过滤、RRF、reranker、prompt、citation、排序和 UI 中不得转成页码 0，并保留行号定位。
- **P0-4 / Task 04–06 前置**：必须按 Spec 的 manifest 物理布局、同目录临时文件 `fsync + os.replace`、原子 claim/owner/attempt/recovery、schema fail-closed、原件 hash-before/after 与 Qdrant fingerprint-before/after 双检执行；删除必须先写 tombstone，部分失败返回 `DELETE_PENDING`/`Retry-After` 并可重试，不能以 200 掩盖孤儿向量或混合快照。
- 首轮技术冻结与评审已经完成，但随后 Task02 为 `NO-GO`。当前修订只落盘 Task02A/02B 新门禁；重新评审和用户确认前不得运行 Task02A，Task03–07 仍受 Task02B `GO` 约束。

## 技术复评 P0-5～P0-7 冻结门禁（2026-09-08）

- **P0-5 / API contract gate**：所有 documents/upload/source（含 GET/HEAD）/inspection/reindex/delete 端点必须先消费 Spec 的公开 API schema v1。成功体、统一错误体、稳定 `error_code`、202/409/404/416/413/415/503 优先级、`Location`、`Retry-After`、`ETag`、`Content-Range`、304、cursor、limit/page_size、50 MiB/8 MiB/数量/超时上限必须同时落盘在 `docs/sdd/plans/018/artifacts/task-04/api-schema.json` 与 `api-fixture-index.json`。schema 或状态码有歧义时 Task 04 停止，不能让前端自行解释。
- **P0-6 / renderer dependency gate**：Task 05 只允许本地 vendored `pdfjs-dist 4.10.38`，主库/worker 路径、SHA-256、`LICENSE`、`NOTICE`、query 版本和 display-only `getDocument` 配置必须落盘在 `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`。Markdown 必须按 `SourceBlock` DTO 经 Marked→DOMPurify→block container，图片只显示 textContent placeholder 且零网络请求；DOM/依赖/fixture 证据缺失时停止 Task 05–06。
- P0-5/P0-6 的实现只能消费上述 Task 04/05 机器可校验交接物；`INVALID_LIMIT` 与 `INVALID_CURSOR` 必须分离，PDF.js/worker/license/NOTICE/hash、display-only 配置和 `renderMarkdownBlock(SourceBlock)` DOM 绑定证据缺失或与 Spec 不一致时，不得由实现者自行解释或补写契约。
- **P0-7 / handoff gate**：Task02A、02B、03–05 必须按各 Task 文档串行交接。固定报告/schema/fixture 路径不存在、SHA-256/命令/退出码/观测字段缺失，或下游需依赖聊天摘要时，一律不放行。

### P0-7 A/B/C/D 交接矩阵（与 Spec 018 同步）

| Task | A → B → C → D | 固定 artifacts / 报告 | 交接门槛 |
|---|---|---|---|
| 02 | 首轮 fixture → probe → Go/No-Go | `docs/sdd/plans/018/artifacts/task-02/` | 历史 `NO-GO`，不改写 |
| 02A | PDF provenance → Markdown provenance → SourceProvenanceBundle → snapshot/operation/RAG exclusion | `docs/sdd/plans/018/artifacts/task-02a/implementation-contract.md`、`source-provenance-bundle.schema.json`、`reindex-snapshot.schema.json`、`backend-test-report.md` | 正式实现、round-trip、恢复与 dense+sparse 排除通过才进入 02B |
| 02B | 证据冻结 → fixture 重放 → hostile 后端安全 → Tech Lead Go/No-Go | `docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md` | 仅严格 `GO` 放行 Task03；浏览器网络证据留给 Task05 |
| 03 | DTO/schema → JSON migration → Qdrant/application → reviewer + Tech Lead | `docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`、`migration-report.md`、`qdrant-migration-report.md` | schema/fixture/report 完整且评审通过 |
| 04 | source/chunk DTO → manifest/upgrade store → routes/API schema → backend test/review | `docs/sdd/plans/018/artifacts/task-04/api-schema.json`、`api-fixture-index.json`、`backend-contract-report.md` | 新索引 inspection no-embedding；旧索引唯一升级、恢复和手动重试全通过 |
| 05 | vendored PDF.js → DOM skeleton → block renderer → interaction/contract review | `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md` | 依赖 hash、DOM 安全、图片零请求、键盘/窄屏联动全通过 |

每个本地 27B 子任务最多接收 2 个已点名代码/资源文件，目标约 150 行；Tech Lead 单步交接复核最低 64k、最终 Gate 签字使用 128k。缺少固定产物、报告、退出码或观测值时保持 `待执行/阻塞`，不得依赖聊天摘要或“实现后补文档”。

### 交接产物速查

| Task | 必须先存在的下游输入 | 负责人签字 |
|---|---|---|
| 02 | `artifacts/task-02/` 首轮固定证据 | 历史 `NO-GO`，只读 |
| 02A | `artifacts/task-02a/implementation-contract.md`、`source-provenance-bundle.schema.json`、`reindex-snapshot.schema.json`、`backend-test-report.md` | backend-reviewer + Tech Lead |
| 02B | `artifacts/task-02b/source-anchor-revalidation-report.md` | Tech Lead：仅 `GO` 放行 |
| 03 | `artifacts/task-03/knowledge-document.schema.json`、`inspection-manifest.schema.json`、`migration-report.md`、`qdrant-migration-report.md` | backend-reviewer + Tech Lead |
| 04 | `artifacts/task-04/api-schema.json`、`api-fixture-index.json`、`backend-contract-report.md` | backend-tester/backend-reviewer |
| 05 | `artifacts/task-05/pdfjs-vendor-manifest.json`、`dom-contract.schema.json`、`frontend-fixture-index.json`、`frontend-contract-report.md` | frontend-tester/frontend-reviewer |

缺少任一交接物、状态门、报告结论或固定观测值，必须保持对应 Task `待执行/阻塞`，不能以“实现后补文档”替代。

## Plan 变更日志

- 2026-09-08：根据技术评审 P0-5～P0-7 增加 API schema/容量与状态码门禁、PDF.js/Markdown 安全依赖门禁、Task 02–05 固定交接物和本地 27B 子任务粒度；技术复评前仍禁止运行 Task 02 或修改业务代码。
- 2026-09-08：修订 C 仅补强 P0-5/P0-6：要求 Task 04 artifact 逐端点冻结成功体、统一错误体、稳定 code、状态码优先级、headers、超时/数量/字节/分页上限；要求 Task 05 manifest 固定 `pdfjs-dist 4.10.38` 的四类 SHA-256、许可证/NOTICE、worker 和 display-only 配置，并冻结按 `SourceBlock` DTO 的 Marked→DOMPurify→block container 唯一路径及 textContent 图片占位。未产生代码变更。
- 2026-09-08：P0-5/P0-6 复核补丁修正 `INVALID_LIMIT`/`INVALID_CURSOR` 的逐端点映射，并将 Task 04/05 机器可校验 schema、fixture、依赖哈希与 DOM 绑定证据明确为唯一下游输入；未产生代码变更。
- 2026-09-08：P0-7 最终小修订将 Task 02–05 的 A/B/C/D 串行边界、固定 artifacts、报告/fixture 和 Tech Lead 64k/128k 预算汇总成表格；未产生代码变更。
- 2026-09-08：根据 Grill with Docs 决策保留首轮 Task02 `NO-GO`，新增 Task02A 正式实现与 Task02B 重新验证；冻结旧 PDF 首次自动升级、point/vector 快照、失败恢复、partial 切换、v2 不降级、仅手动重试和 Task05 浏览器安全门。本轮仅修订文档。
- 2026-09-08：按独立技术评审 P0 补齐现有 hybrid_search dense+sparse 排除桥、单线程 executor 文档级 operation 与启动恢复、reindex-snapshot-v1 机器 schema/round-trip，以及 SourceProvenanceBundle→Task03 manifest 的单向交接；重新提交技术复审。

## 技术复评修订 C：P0-5/P0-6 只读交接门禁（2026-09-08）

- **P0-5 / Task 04**：`api-schema.json` 必须逐一列出 documents/upload/source GET+HEAD/inspection/reindex/delete 的成功体字段类型、统一错误体字段、稳定 `error_code` 全集及 HTTP 映射；fixture index 必须记录 202/409/404/416/413/415/503 的 body 与 headers（含 `Location`、`Retry-After`、`ETag`、`Content-Range`、304、HEAD），以及请求格式→身份/原件→状态冲突→依赖不可用的优先级。文档、block、chunk、anchor、manifest 的数量/字节/超时/分页固定值必须与 Spec 一致，缺任何字段或存在歧义即阻塞 Task 04/05。
- **P0-6 / Task 05**：`pdfjs-vendor-manifest.json` 必须逐项保存 `pdfjs-dist:4.10.38`、主库/worker/LICENSE/NOTICE 路径和 SHA-256、query 版本、workerSrc、允许 public display API 及 `getDocument` display-only 配置；不得接受 CDN、私有 API、PDF 脚本、annotation/XFA/form/attachment 或远程 URL。`dom-contract.schema.json`/frontend fixture 必须证明每个 `SourceBlock` 走唯一 `renderMarkdownBlock`，Marked 后 DOMPurify 再入 block container，图片只以 textContent placeholder 出现且零网络请求；缺库只允许转义纯文本和 `RENDERER_UNAVAILABLE`。任一证据缺失，Task 05–06 保持 `待执行/阻塞`。
- 上一版已通过最终技术复审，但首轮 Task02 后续为 `NO-GO`；自动重建修订尚未重新评审，Spec 已回到 `待确认`，不得生成业务实现产物。
