# Spec029 技术评审：Research Task 全文获取与知识库联动

- 评审对象：[`docs/sdd/specs/029-research-fulltext-acquisition.md`](../specs/029-research-fulltext-acquisition.md)
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec029 最终评审文档子 Agent
- 评审角色：开发主管视角的技术门禁审阅
- 评审模型：Luna high（本次分派）
- 分派方式：主 Agent 分派的 Task06 文档评审子任务；代码事实来自当前 diff、Task02–05 交接报告和相关合同测试

## 结论：通过（附运行时收口条件）

静态架构与合同测试表明，Task03–05 沿既有下载/导入/知识库边界接线，没有发现 P0 级重复实现、客户端扩大检索范围、确认前下载或无定位全文证据写入。技术评审可通过；但真实下载和浏览器运行时验证尚未执行，必须在验收门禁完成前保持 Spec029 为实施中，不能据此转已完成。

## 技术核对矩阵

| 技术点 | 判定 | 代码/报告事实 |
|---|---|---|
| 既有下载与导入复用 | GO | Task03 的 `ResearchAcquisitionService` 只调用 `PaperImportBatchService.create_batch()`（`backend/app/research/application/acquisition.py:74-138`）；Task02 固定样本证明安全导入、重复候选去重和失败项单独重试。 |
| 审批幂等与 fail-closed | GO | ResearchStore 对 `(research_task_id, selection_version)` 和 `(research_task_id, idempotency_key)` 建唯一约束（`backend/app/research/infrastructure/research_store.py:558-581`）；服务校验当前选集版本、候选归属和 `search_id`（`acquisition.py:56-115`）。 |
| 状态投影与部分失败 | GO | `ResearchDocumentLink`/`AcquisitionEvent` 由既有 batch item 的 `candidate_id`、`item_id`、`paper_id`、`status`、`error_code` 投影（`acquisition.py:140-185`），没有建立平行状态机；Task03 报告覆盖 completed/failed/waiting_login/partial 语义。 |
| 全文检索隔离 | GO | `EvidenceUpgradeService` 先从 Research links 取得已完成文档白名单，再把 `document_ids` 传入既有 `hybrid_search`（`backend/app/research/application/evidence_upgrade.py:86-100,196-205`）；未批准文档返回 `DOCUMENT_NOT_APPROVED`。 |
| 证据定位与 provenance | GO | 服务复用 inspection manifest 验证来源 hash、索引状态、manifest 文本、chunk index、页码和 `page_end`；只保存 `document_id/chunk_ids/page/page_end` 及 source hash、generation、fingerprint、chunker，不保存模型摘录（`evidence_upgrade.py:116-177,215-240`）。 |
| 删除/重建语义 | GO（合同级） | `revalidate()` 对 manifest 缺失标记 `unavailable`，对来源 hash、manifest fingerprint、generation 或 chunk 定位变化标记 `revalidation_required`，不修改报告正文（`evidence_upgrade.py:242-277`）；Task04 单测覆盖重建与删除 double。真实 KB 删除后的运行时行为尚未执行。 |
| SQLite 迁移 | GO | Spec029 schema 使用加性 `CREATE TABLE IF NOT EXISTS` 和 evidence provenance 列检查/`ALTER TABLE`（`research_store.py:551-629`），保留 Task03 数据可读性；删除/legacy cleanup 同步清理 Research 私有桥接行，不级联共享 KB。 |
| 前端接缝与安全 | GO（静态） | UI 只在预览后由显式确认按钮提交，重试复用 `/api/papers/import-items/{item_id}/retry`，用户文本使用 `textContent`，没有新增 `innerHTML` 拼接；Task05 静态合同和 `node --check` 通过，资源版本已升至 `research-tasks.js?v=3`、styles `v=51`。 |

## P0/P1 结果

### P0

无。当前证据未发现以下高风险退化：第二套 downloader/import state machine、未确认即下载、客户端注入候选 URL/快照、未批准文档参与全文检索、无 manifest 定位仍写 `fulltext`、或把共享 KB 文档复制到 Research 表。

### P1（不阻塞技术评审，但阻塞最终收口）

1. **真实环境证据缺口**：所有 Task02–05 测试都使用临时 SQLite、fake batch、内存 manifest/`Hit` 或静态 DOM，报告明确 `network_or_real_download=false`、`real_kb_or_qdrant_write=false`。必须用公开 PDF 验证下载安全、canonical document、manifest/chunk/page 定位和证据升级。
2. **浏览器主链路未跑**：Task05 报告明确 `runtime_smoke=NOT_RUN_BY_SUBAGENT`，并指出真实切片跳转尚未验证；需要在服务实际启动后检查预览不下载、点击确认才启动批次、waiting_login/failed/retry/partial 恢复和“打开原文切片”。
3. **跨刷新证据投影**：当前 `GET .../acquisitions` 返回 links/events，前端也可消费报告中 `evidence_upgrades/evidence`；Task05 指出没有独立 evidence-upgrade GET。若最终产品要求跨刷新展示全部升级记录，应在收口前由现有投影补齐或明确采用报告投影；不得另建检索实现。
4. **`search_id` 可达性**：确认契约要求服务端搜索快照句柄；前端找不到该句柄时安全禁止确认。需在真实任务详情中确认该字段稳定返回；若缺失，应回到 Spec/Task 契约修订，不得猜造 ID。

## 回归证据

- Task02 合同测试：5 passed；证明既有安全导入、重复去重、批量部分失败/重试、citation locator、删除边界。
- Task03 定向验证：`py_compile` 通过；Spec029 acquisition bridge 3 passed；与 Spec027 相关集合 60 passed、5 subtests passed。
- Task04 定向验证：全文证据、acquisition bridge、reuse gate 合计 12 passed；`py_compile` 与 `git diff --check` 通过。
- Task05 定向验证：前端专项 4 passed；相关前端合同 11 passed；`node --check frontend/research-tasks.js` 通过；`git diff --check` 通过。
- 最终全量回归交接摘要：**2450 passed / 1 skipped / 5 warnings / 67 subtests**。本评审不补写未提供的退出码，也未重新执行该命令。

## 技术评审收口条件

在验收评审签字前，必须补充真实公开 PDF、真实 KB/manifest/chunk 定位和浏览器 smoke 证据；若任一链路失败，应记录真实错误与复验步骤，并保持 Spec029 实施中。除非真实环境发现超出当前合同的缺陷，不需要新增 downloader、PDF parser、chunker、embedding、reranker 或 Qdrant collection。

