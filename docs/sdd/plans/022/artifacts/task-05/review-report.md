# Spec022 Task05 后端最终复审报告

## 结论

**GO（后端范围）**。本轮只复审当前修复后的工作树；未发现新的 P0/P1/P2 阻断项。上一轮指出的 canonical metadata、项目检索过滤和 citation identity 问题均已在当前代码中闭环，并由定向回归验证。

本结论不替代前端评审、跨端验收、最终全量回归或部署 smoke。

## 严重级别汇总

| 级别 | 数量 | 结论 |
|---|---:|---|
| P0 | 0 | 未发现 |
| P1 | 0 | 阻断项已关闭 |
| P2 | 0 | 本轮未发现新增项 |

## 关键复审证据

### 1. 关联/解除与旧 schema 状态 patch/reindex

- `backend/app/knowledge_base/application.py:570-627` 定义独立 `project-document-associations-v1` sidecar，并以临时文件、fsync、replace、目录 fsync 原子保存；未把关联字段写入 canonical `papers.json`。
- `backend/app/knowledge_base/application.py:642-699` 在既有 immutable lock 下仅变更 sidecar，返回对象中的 `project_id` 是 presentation overlay；canonical 文档 ID、hash、原件和 chunker 数据不变。
- `backend/app/knowledge_base/application.py:702-729` 的批量解绑只删除 sidecar 关系。`backend/app/api/routes_conversations.py:94-105` 删除项目时先解绑，随后调用既有项目仓储删除，没有调用知识库 source/manifest/vector 删除入口。
- `backend/app/knowledge_base/infrastructure/migration.py:223-239,376-390` 仍对 canonical 写路径严格校验闭合 schema；`backend/app/knowledge_base/infrastructure/store.py:736-774` 的 `update_chunker_state` 和 `backend/app/knowledge_base/application.py:802-850` 的 `submit_document_reindex` 继续复用该状态/索引路径。
- 测试 `tests/test_task05_backend.py:52-61` 验证关联后 canonical 不含 `project_id` 且 `patch_knowledge_document(status="indexed")` 成功。补充临时目录探针验证关联后 `submit_document_reindex(v1)` 在既有 generation resolver/index task 接缝下返回 `submitted={'v1': True}`，canonical 无 `project_id`、v1 状态为 `indexing`；未改变业务代码。

### 2. 项目检索在 top-k 前安全过滤

- `backend/app/knowledge_base/infrastructure/retrieve.py:139-149,186-206` 接受 canonical `document_ids`，构造一个 `query_filter`，同一 filter 对象传入 dense 和 sparse 两路 Qdrant 查询。
- `backend/app/knowledge_base/infrastructure/retrieve.py:208-225` 只在双路过滤完成后执行 RRF、reranker 和最终 top-k；`retrieve.py:513-550` 对显式空 allowlist fail-closed。
- `backend/app/api/routes_conversations.py:215-232` 和 `backend/app/api/routes_kb.py:954-965` 先读取 owner-scoped 项目文档 ID，再调用既有 `hybrid_search`；无 `project_id` 的 `/api/kb/ask` 仍走原有兼容调用。
- `tests/test_task05_backend.py:127-157` 验证 dense/sparse 使用同一 filter、allowlist 在查询前生效，并验证项目低分文档不会被全局高分文档挤出 top-k。

### 3. source/chunk/document/raw identity

- `backend/app/knowledge_base/infrastructure/prompts.py:54-72` 同时输出 `paper_id`/`document_id`、`source_url`、chunk 文本和 chunk 坐标；`chunk_id` 复用 `backend/app/knowledge_base/infrastructure/index.py:132-139` 的 canonical `point_id(document_id, chunk_index, chunker)`。
- `tests/test_task05_backend.py:119-124` 验证 v2 chunk 的 citation ID 与 canonical `point_id` 一致，source URL 指向既有原件安全读取入口。
- `backend/app/api/routes_kb.py:604-640` 的 project-scoped source/HEAD 先校验 owner 项目关联，再读取原件；无 project 参数时保留旧 source 读取兼容路径。

### 4. 上下文、progress、SSE 与单一实现边界

- `backend/app/chat/application/conversation_service.py:99-126` 对项目指令、长期记忆、RAG、历史使用独立预算，当前问题最后追加且不受 RAG 预算裁剪；RAG 文本作为参考而非新指令。
- `backend/app/api/routes_conversations.py:221-238` 的 `rag_retrieval` progress 只围绕真实 `hybrid_search` 调用；`routes_conversations.py:267-282` 在最后 token 和 generation completed 后才发送 `sources[:5]`，之后发送 `done`。
- processing/error 摘要经过固定短文及 `_redact_sensitive`（`routes_conversations.py:117-123`），不保存完整 prompt、Bearer 值或敏感工具参数。
- 未发现第二套 embedding、RRF、reranker、下载安全链路或 chunk store；项目检索、source 与引用均复用既有 KB application/retrieval/index/inspection facade。旧 `/api/kb/ask` SSE 的 `meta/stage/citations/token/done` 顺序保持。

## 测试与静态检查

| 检查 | 命令/探针 | 结果 |
|---|---|---|
| Task05 + 受影响后端回归 | `./.venv/bin/python -m pytest -q tests/test_task05_backend.py tests/test_kb_document_routes.py tests/test_kb_routes.py tests/test_kb_ask_trace.py tests/test_conversations_api.py tests/test_memory_repositories.py tests/test_chat_route.py tests/test_api.py` | 退出码 0；**130 passed in 16.24s** |
| Python 语法 | `./.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/retrieve.py backend/app/knowledge_base/infrastructure/prompts.py backend/app/api/routes_kb.py backend/app/api/routes_conversations.py backend/app/api/schemas.py backend/app/chat/application/conversation_service.py` | 退出码 0 |
| 差异检查 | `git diff --check` | 退出码 0；无输出 |
| 关联后 reindex 状态 | 临时目录 create → associate → `submit_document_reindex(v1)`，mock 既有 generation/index 外部接缝 | 通过；canonical schema 合法，状态更新为 indexing，任务 submitted |

按角色边界未运行全量 pytest、前端测试、部署或跨端 smoke。

## 非阻断风险与主 Agent 后续动作

1. 旧向量 payload 若缺少 canonical `document_id`，项目 allowlist 会安全排除这些点；需要通过既有 reindex 恢复，不应增加第二套兼容检索。该风险已记录在 Task05 实现报告，属于运维前置，不构成本轮 P0/P1/P2 阻断。
2. 主 Agent 可采用本报告 GO，继续前端评审及跨端验收整合；Task08 仍需执行最终全量回归、验收评审、部署和真实 smoke。
3. 前端继续按 `sources/citations` DTO 使用 canonical `document_id`/`chunk_id`/`source_url`；不要在前端自行重建 chunk identity。

## 运行信息

- 评审角色：backend-reviewer
- 模型：临时 Luna high（主 Agent 指定）
- 本轮开始：2026-09-11 07:08（Asia/Shanghai）
- 本轮结束：2026-09-11 约 07:19（Asia/Shanghai）
- 本轮耗时：约 11 分钟
- 模型 token 统计：运行时不可用
- 工具统计：运行时未提供精确调用数；使用定向文件读取/检索、pytest、py_compile、git diff check 和临时 reindex 状态探针
- 业务代码修改：无；仅更新本评审报告与本轮进度日志
- 进度日志：`.codebuddy/agent-logs/spec-022/task-05/backend-reviewer/20260911-070811.md`
