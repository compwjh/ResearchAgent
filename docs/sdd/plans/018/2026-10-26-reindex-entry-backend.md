# Spec018 reindex-entry 后端接缝修复交接

- 日期：2026-10-26
- 角色：backend-dev
- 范围：只修复单文档+单 chunker 的旧点清理传播和 manifest 发布前 point 快照一致性；不执行真实生产 reindex，不启动/部署服务，不调用模型或网络，不修改主数据/Qdrant live 文件。
- 上游诊断：[`2026-10-26-reindex-entry-range-diagnosis.md`](2026-10-26-reindex-entry-range-diagnosis.md)
- 进展日志：`.codebuddy/agent-logs/spec-018/task-reindex-entry/backend-dev/20261026-015256.md`

## 实现结论

已修改 [`backend/app/knowledge_base/infrastructure/index.py`](../../../backend/app/knowledge_base/infrastructure/index.py)：

1. `delete_paper_chunker()` 仍只按当前 `paper_id + chunker` 过滤；删除异常不再被吞掉。删除/Qdrant 未知异常进入稳定 `QDRANT_UNAVAILABLE` 失败态，后续不会执行 upsert，也不会发布 ready/partial。
2. canonical 文档在 manifest 发布前读取显式 `destination_collection` 的当前 point 集合，范围严格限定为当前文档+chunker；在写锁下核对：
   - upsert 返回数量与待发布 chunks 数量；
   - point id 与 `point_id(paper_id, chunk_index, chunker)` 一致；
   - chunk index 集合精确为连续 `0..N-1`，无重复/尾点；
   - `document_id`、`source_sha256`、`chunker`、`text`、`page`、`page_end`、`section` 与待发布 manifest payload 完全一致，`is_citation` 类型合法。
3. point 集合或 payload 不一致时 fail-closed 为 `INDEX_FINALIZE_REQUIRED`，不调用 manifest/ready/partial 发布；一致时使用核对后的实际 payload 构建 manifest，避免待写 chunks 与实际索引漂移。
4. `SOURCE_RANGE_UNRESOLVED` 不被改变：合法 partial bundle 仍可通过 point 快照门禁并按原状态发布；没有 fuzzy anchor、LLM 或 chunker 改动。无关文档和另一 chunker 不在删除/核对范围内。

真实 Qdrant client 提供 `scroll`，因此生产 canonical 路径始终执行上述门禁。旧的 write-only compatibility test double 没有 read API，仍保留原兼容路径；新增隔离测试使用带 scroll 的 fake client 覆盖真实门禁行为。

## 隔离测试与结果

新增 [`tests/kb/test_kb_index_publication_contract.py`](../../../tests/kb/test_kb_index_publication_contract.py)，测试按能力命名，覆盖：

- 5→3 缩容时清掉当前文档+v2 的旧尾点，并保留其他文档及同文档 v1；
- 删除失败时无 upsert、无 manifest 发布，失败码为 `QDRANT_UNAVAILABLE`；
- upsert 后注入额外 point 时不发布 ready/partial，失败码为 `INDEX_FINALIZE_REQUIRED`；
- mapped/unmapped 合法 partial bundle 仍到达发布接缝。

执行结果：

```text
source .venv/bin/activate; hash -r; .venv/bin/python -m pytest --noconftest \
  tests/kb/test_kb_index_publication_contract.py \
  tests/kb/test_kb_tasks.py \
  tests/kb/test_kb_pdf_safety_publication.py \
  tests/kb/test_kb_document_reindex.py -q
exit 0 — 50 passed, 5 warnings

source .venv/bin/activate; hash -r; .venv/bin/python -m pytest --noconftest \
  tests/kb/test_kb_services.py \
  tests/kb/test_kb_application_boundary.py \
  tests/kb/test_kb_document_boundary.py -q
exit 0 — 99 passed, 4 subtests passed, 5 warnings

source .venv/bin/activate; hash -r; .venv/bin/python -m py_compile \
  backend/app/knowledge_base/infrastructure/index.py \
  tests/kb/test_kb_index_publication_contract.py
exit 0

.venv/bin/ruff check \
  backend/app/knowledge_base/infrastructure/index.py \
  tests/kb/test_kb_index_publication_contract.py
exit 0 — All checks passed
```

仓库默认 `conftest.py` 的测试入口在当前环境因 `langchain_ollama` 未安装而无法收集；未安装依赖、未绕过安全门禁，故以上定向结果使用 `--noconftest` 并明确列为环境限制。第二组测试产生的 OTEL localhost 发送重试属于测试进程已有观测器，未执行产品网络调用，也未影响退出码。

## 交接边界

此交接只说明后端代码与隔离测试完成，不能替代独立 backend review、服务重启或父会话安排的一次有界真实 v2 重建验证。旧的历史全量回归数字不在本次范围内，也未被重新计入；当前真实文档仍不得标记为全量成功，须由后续受控验证确认 297 manifest 与实际 point 集合一致。
