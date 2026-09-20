# Spec029 Task04 后端交接报告

## 结论

```text
result=IMPLEMENTED
allowlisted_fulltext_search=GO
evidence_locator_validation=GO
provenance_persistence=GO
delete_rebuild_revalidation=GO
network_or_real_download=false
real_kb_or_qdrant_write=false
```

## 已实现

- 新增 `EvidenceUpgradeService`，只调用既有 `knowledge_base.application.hybrid_search()`，并把 Research 已确认导入成功的 `document_id` 作为 `document_ids` allowlist 传入；客户端无法扩大检索范围。
- 命中升级前复用既有 inspection manifest：校验文档、chunker、确定性 `chunk_id`、manifest 中的真实 chunk 文本、页码和跨页 `page_end`；不保存模型摘录，无法定位时保持摘要级并返回 `insufficient`/`unavailable`。
- `EvidenceUpgrade` 持久化增加 `source_sha256`、`manifest_generation`、`manifest_fingerprint`、`chunker`；旧数据库通过加性 SQLite 列迁移兼容。
- 新增 ResearchStore 的 evidence projection 读取/list 方法及 `POST /api/research-tasks/{id}/evidence-upgrade` 端点；路由只负责 HTTP 校验，业务仍经 Research application facade。
- 新增 `revalidate()`：文档删除/manifest 缺失标记 `unavailable`，source hash、manifest fingerprint、索引 generation 或 chunk 定位变化标记 `revalidation_required`，不修改历史报告正文。

## 定向验证

```text
.venv/bin/python -m pytest -q tests/test_spec029_fulltext_evidence.py tests/test_spec029_acquisition_bridge.py tests/test_spec029_reuse_gate.py
12 passed

python -m py_compile \
  backend/app/research/domain/models.py \
  backend/app/research/infrastructure/research_store.py \
  backend/app/research/application/evidence_upgrade.py \
  backend/app/research/application/entry.py \
  backend/app/api/routes_research.py
exit=0

git diff --check -- backend tests/test_spec029_fulltext_evidence.py
exit=0
```

测试使用临时 SQLite、内存 Search/manifest double 和既有 `Hit` DTO；没有网络、真实 PDF 下载、真实知识库目录或 Qdrant 写入。

## 边界与后续

- Task04 只建立同步 EvidenceUpgrade application seam；没有新建 chunker、embedding、reranker、Qdrant collection、下载器或第二套 scheduler。
- `revalidate()` 由后续报告/任务流程调用；Task05/06 可把它接入索引完成、删除和报告刷新事件。
- 多文档 allowlist 检索允许多个 approved document 参与召回；单个 Claim 的既有 `EvidenceUpgrade` 合同仍以一个 canonical `document_id` 和其 chunk locator 集合落盘，避免复制/改造既有报告模型。
