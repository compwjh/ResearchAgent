# Spec029 Task03 后端交接报告

## 结论

```text
result=IMPLEMENTED
research_bridge=GO
existing_batch_reuse=GO
network_or_real_download=false
real_kb_or_qdrant_write=false
```

## 已实现

- 在 ResearchStore 增加独立的 selection version 计数，不改变既有 `ResearchPaperSelection` 字段契约。
- 新增 `AcquisitionApproval`、`ResearchDocumentLink`、`AcquisitionEvent`、`EvidenceUpgrade` DTO 及最小 SQLite 持久化表/读写方法。
- 确认按 `(research_task_id, selection_version)` 和 `idempotency_key` 双重幂等；版本过期或确认清单不属于当前选集时 fail closed。
- 新增 `ResearchAcquisitionService`：确认后只调用既有 `PaperImportBatchService.create_batch()`，不复制下载器、导入状态机或 KB 文档。
- 按既有 batch item 的 `candidate_id → import_item_id/paper_id/status/error_code` 投影逐项文档 link 和 acquisition event；批次的 `partial_success`、`failed`、`waiting_login` 等状态原样保留，后续重试再次同步。
- 暴露 `acquisition-preview`、`acquisitions POST/GET` Research 路由；preview 只读服务端候选快照，不下载、不写 KB。
- Research task/project 删除和 legacy cleanup 已包含新增私有桥接行，不影响共享目录/知识库。

## 定向验证

```text
.venv/bin/python -m py_compile \
  backend/app/research/domain/models.py \
  backend/app/research/infrastructure/research_store.py \
  backend/app/research/application/acquisition.py \
  backend/app/research/application/entry.py \
  backend/app/api/routes_research.py
exit=0

.venv/bin/python -m pytest -q tests/test_spec029_acquisition_bridge.py
3 passed

.venv/bin/python -m pytest -q tests/test_spec029_acquisition_bridge.py tests/test_spec027_backend_research_slice.py
60 passed, 5 subtests passed
```

Task02 的桥接缺口测试已在实现完成后移除严格 `xfail` 标记，并与本 Task 定向集合共同通过。

## 边界

- 测试只使用 `tmp_path` SQLite、fake batch service 和内存候选；没有外网、真实用户凭据、真实 `data/kb` 或 Qdrant 写入。
- `document_id` 仅保存既有导入结果返回的 canonical ID；Research 不复制 PDF、source、chunk 或索引状态机。
- `search_id` 作为服务端搜索快照句柄由确认请求带入；客户端不能提交候选 URL 或快照内容。
