# Spec029 Task02：复用审计与全文证据协议门

## 结论

```text
result=NO-GO
reuse_infrastructure=GO
research_task_bridge=NO-GO
fulltext_evidence_persistence=NO-GO
network_or_real_download=false
real_kb_or_qdrant_write=false
```

既有安全下载、单篇 KB 导入、批量状态机、知识库检索、切片检查和删除入口均可复用；本轮没有发现需要复制第二套下载器、PDF parser、chunker、embedding、reranker、Qdrant Collection 或导入状态机的理由。Task02 仍不能放行 Task03，原因是 Research Task 与这些既有能力之间缺少已冻结的持久化桥接合同，且当前报告/选集没有保存可验证的全文证据引用。

## 审计范围与约束

读取并对照了：

- `docs/sdd/specs/029-research-fulltext-acquisition.md`
- `docs/sdd/plans/029/task-02-reuse-and-evidence-gate.md`
- Spec015 Task05/06/13（安全下载、单篇/批量导入、登录续传和复用边界）
- Spec018 Task03/04/06（canonical document、manifest、source/chunk 定位、删除/补偿边界）
- Spec021 Task02/03（后台批量、单条重试、稳定错误码）
- `docs/sdd/plans/028/artifacts/task-03/backend-report.md`（durable lease/checkpoint 调度合同）

本轮只修改本报告和 `tests/test_spec029_reuse_gate.py`；测试使用 `tmp_path`、临时 SQLite 和 fake port/downloader，不访问外网、不使用真实凭据、不写用户 `data/kb` 或 Qdrant。

## 复用矩阵

| 能力 | 现有唯一入口 / 证据 | Task029 调用合同 | 判定 |
|---|---|---|---|
| 候选快照 → 安全下载 | `backend/app/paper_discovery/application/paper_import.py:418` 的 `import_candidate()`；Spec015 Task05；`tests/test_paper_download.py`、`tests/test_spec032_*_download.py` | 输入服务端候选快照和服务端 allowlist；下载器只产生受控本地 PDF；禁止客户端注入 URL；下载前/下载后经 `PaperImportPort.find_existing()` | **GO（复用）** |
| 单篇 KB 导入 | `backend/app/platform/ports.py:95-160` 的 `PaperImportRequest` / `PaperImportResult` / `PaperImportPort`；`backend/app/knowledge_base/application.py:1046` 的 `KnowledgeBasePaperImportAdapter` | `import_paper()` 接受 trusted local path，返回 `paper_id`（canonical `document_id` 语义）、stored name、index status、稳定错误码和内部 capability；论文发现不得读 KB store/index/Qdrant | **GO（复用）** |
| 不可变文档创建与去重 | `backend/app/knowledge_base/application.py:374` 的 `create_immutable_document()`；Spec018 Task03 application boundary | 由 KB 侧生成 document ID、独占 source、hash 去重；重复导入返回 existing/同一 document ID；失败补偿不能按 pathname 猜测所有权 | **GO（复用，需保持既有安全门）** |
| 批量导入、部分失败和单条重试 | `PaperImportBatchService.create_batch()`（`paper_import_batch_service.py:282`）、`submit_batch()`（:686）、`retry_item()`（:778）；Spec021 Task02/03；现有 batch API tests | Research Task 确认后只需把候选列表映射为既有 batch；后台单飞、lease/CAS、partial、failed/waiting_login 重试保持原语义 | **GO（通用 batch）；NO-GO（缺 Research Task 映射）** |
| 文档 → chunk/page citation | `backend/app/knowledge_base/infrastructure/retrieve.py:69,139` 的 `Hit`/`hybrid_search()`；`prompts.py:54` 的 `citation_payloads()`；`routes_kb.py:703,713` source/inspection GET；Spec018 Task04/06 | 只对 `document_ids` allowlist 检索；citation 至少保存 document/chunk/page（跨页 page_end）；需能通过 inspection/source API 回到真实切片 | **GO（只读定位复用）** |
| 文档删除、manifest tombstone 与证据失效 | `backend/app/knowledge_base/application.py:872` 的 `delete_document()`；Spec018 Task04 contract report；删除后 source/metadata 移除、manifest tombstone 写入、向量删除成功后才完成 | Research 报告历史正文保留；其全文 evidence 引用必须在文档删除后转为 unavailable，不能继续声称 fulltext | **NO-GO（Research 侧无 link/evidence 状态存储）** |
| Research 选集及 evidence level | `ResearchPaperSelection`（`research/domain/models.py:350`）、`ResearchStore.replace_selections/list_selections`（`research_store.py:4124/4158`）；`EVIDENCE_LEVELS` 含 `catalog/abstract/fulltext` | 需要 selection_version、候选确认快照、逐篇 document_id/import_item_id、claim_id/chunk_ids、from/to level 的可审计更新 | **NO-GO（当前仅 catalog 选集）** |
| Spec028 durable 调度 | `ResearchScheduler`、lease/checkpoint/reservation，见 Task03 backend report 与 `tests/test_spec028_scheduler_lease_recovery.py` | 可作为 Research WorkItem 的 durable runner；不应新建 acquisition lease 或第二套 scheduler | **GO（可复用，但与全文证据桥接尚未接线）** |

## 固定样本链路结果

### 已证明的链路

测试 `test_candidate_snapshot_reuses_secure_import_port_and_returns_document_id` 证明：

```text
PaperCandidate(server snapshot)
  -> import_candidate()
  -> trusted local PDF
  -> PaperImportPort.import_paper(PaperImportRequest)
  -> PaperImportResult.paper_id == canonical document_id
```

测试 `test_duplicate_candidate_reuses_existing_kb_document_before_download` 证明：重复候选在下载前命中 `find_existing()`，下载调用次数仍为 1，返回同一 document ID 且 `existing=True`。

测试 `test_batch_reuse_preserves_partial_failure_and_retries_only_failed_item` 证明：既有 batch 能保留一条 completed 与一条 failed；重试仅使失败条目再次执行，成功条目不会重跑。

测试 `test_existing_citation_contract_contains_document_chunk_and_page_locator` 证明：既有 citation DTO 携带 `document_id`、确定性 `chunk_id`、`chunk_index`、`page/page_end` 和 source URL。该证据是只读引用合同，不是新的检索实现。

测试 `test_document_delete_reuses_kb_boundary_and_removes_source_and_metadata` 证明：删除复用 KB application boundary；在隔离临时目录内，向量删除成功后 source/metadata 消失，后续 source read 返回 `DOCUMENT_NOT_FOUND`。

### 当前不能证明的链路

```text
ResearchTask selection
  -> user approval(selection_version)
  -> existing batch(batch_id/import_item_id)
  -> ResearchDocumentLink(document_id)
  -> fulltext RAG hit
  -> EvidenceUpgrade(claim_id, chunk_ids, page, status)
  -> delete/rebuild => evidence unavailable or revalidated
```

Research 侧原先只有 `research_paper_selections(research_task_id, catalog_paper_id, relevance, facets_json, evidence_level, created_at)` 和 `preliminary_reports`；Task03 已补齐审批、文档映射、事件与证据升级桥接表。后续 Task04 仍需把真实切片定位写入升级记录。

`Hit`/`citation_payloads()` 能把命中的 document/chunk/page 交给 UI，但不会把 source hash、manifest anchor fingerprint、索引 generation 或 claim_id 写回 Research 报告；因此不能把一次 RAG 命中直接当成可审计的 EvidenceUpgrade。删除后也没有 Research 记录可将全文证据降级为 `unavailable` 并保留原报告文字。

## 阻塞项与最小合同

1. **审批合同缺失（P0）**：新增/冻结 `AcquisitionApproval(task_id, selection_version, paper_ids, status)`，确认前不得提交 batch；重复确认必须按 selection version/idempotency key 稳定处理。
2. **导入映射缺失（P0）**：新增/冻结 `ResearchDocumentLink(task_id, catalog_paper_id, document_id, import_item_id)`，只存引用，不复制 KB 文档；批次响应必须能逐项映射已有、待下载、需登录、失败和 indexed 状态。
3. **事件投影缺失（P1）**：新增 `AcquisitionEvent(paper_id, phase, status, error_code)` 或明确复用既有 batch item 作为唯一事件源；不能创建平行状态机。
4. **全文证据升级缺失（P0）**：新增/冻结 `EvidenceUpgrade(claim_id, from_level, to_level, chunk_ids, status)`，并绑定 `document_id + chunk_id + page/page_end + source_sha256/manifest version`。没有定位切片时必须 fail closed，不能保存模型摘录冒充证据。
5. **删除/重建失效语义缺失（P0）**：文档删除、manifest tombstone、source hash 变化、generation rebuild 后，Research 引用必须变为 `unavailable` 或 `revalidation_required`；历史 Markdown 保留但不能继续标记 `fulltext`。
6. **命名语义需冻结（P1）**：现有跨域 DTO 名为 `paper_id`，canonical document 实际由 `document_id` 标识；Spec029 facade 应明确一次映射，避免 Research 误把 catalog paper ID 当 KB document ID。

Task03 已完成审批、文档映射和导入事件桥接；`evidence_level="fulltext"` 仍需 Task04 用真实切片证据升级后才可使用，不能用目录或摘要冒充全文证据。

## 合同测试与验证

命令：

```text
.venv/bin/python -m pytest -q tests/test_spec029_reuse_gate.py
git diff --check -- tests/test_spec029_reuse_gate.py
```

结果：

```text
5 passed in 0.63s
exit code: 0
```

桥接合同已由 Task03 实现并通过；测试仍只使用临时 SQLite、fake batch 和内存候选，没有修改真实 KB、Qdrant 或网络状态。

## 交接决策

- Task02 复用基础设施审计：**GO**。
- Task02 全文证据协议门：**NO-GO**，交给架构师先冻结上述桥接合同。
- Task03 最小前置：先补审批/批次映射、`document_id` link 和逐项状态投影；不得另写 downloader/import state machine。
- Task04 最小前置：只调用既有 `hybrid_search(document_ids=...)` 与 inspection/source 定位；新增的是 Research evidence projection/persistence，不是第二套 RAG/chunker。
- Task06 必须复核：真实公开 PDF、source hash、manifest/chunk 定位、删除后降级和重建后 revalidation；本报告不授权真实下载或部署。

## 变更范围

- 新增：`tests/test_spec029_reuse_gate.py`
- 新增：本报告
- 未修改：`backend/**`、`frontend/**`、用户 KB 数据、Qdrant、Git 历史
