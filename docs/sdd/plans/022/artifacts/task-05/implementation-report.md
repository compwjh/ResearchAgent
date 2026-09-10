# Spec022 Task05 后端实现报告

## 结果状态

**完成（后端范围，reviewer NO-GO 修复后）**。本轮只实现 Task05 后端增量，未修改前端、论文检索主链、原件内容或 git 状态。

## 改动文件

- `backend/app/knowledge_base/application.py`
- `backend/app/api/routes_kb.py`
- `backend/app/api/routes_conversations.py`
- `backend/app/api/schemas.py`
- `backend/app/chat/application/conversation_service.py`
- `backend/app/knowledge_base/infrastructure/prompts.py`
- `tests/test_task05_backend.py`

## 接口与数据契约

- canonical `knowledge-document-v1` 保持闭合 schema；新增独立、原子 `data/kb/project-associations.json`（测试路径为 `papers.json` 同目录）保存 owner/project/document 关系。新增 `PATCH /api/kb/documents/{document_id}`（body 必须含 `project_id`，可为 null），以及 `POST /api/kb/documents/{id}/project`、`POST .../associate` 和 `DELETE .../project` 兼容别名。
- `GET /api/kb/documents?project_id=...`、`GET /api/kb/papers?project_id=...` 和 source/HEAD 的可选 `project_id` 均做 owner-scoped 项目校验；项目作用域只读取显式关联文档，null 作用域只读取未关联文档。
- 项目删除先经 KB application facade 批量解除关联，再执行既有项目删除；不会删除 source 文件、document ID、chunker 状态、manifest 或 index generation。
- 会话消息在存在显式关联文档时复用 `hybrid_search`（dense+sparse/RRF/reranker），将 canonical `document_id` allowlist 在 dense/sparse 两路、RRF、reranker、top-k 之前统一过滤；证据最多 5 条并按独立 6000 字符预算装配，当前指令与当前问题保留优先级。
- 会话 SSE 新增真实 `rag_retrieval` processing step/progress；sources/citations 在最后一个 token 和 generation completed 后发送，来源 DTO 含 `document_id`、`chunk_id`、`source_url`、页/行、chunk 文本等。旧 `/api/kb/ask` 的既有 SSE 顺序保留以兼容 Task02/03。
- 工具失败 Raw event 与聊天错误摘要做敏感键/ Bearer 值脱敏和长度限制；processing steps 仍只保存真实阶段及短摘要。

## 决策依据

- 文档关联使用既有 KB application facade 与同域 immutable lock；sidecar 采用临时文件写入、fsync、replace、目录 fsync，且 owner 校验 fail-closed；不新增 embedding、RRF、reranker、下载、安全或 chunk store。
- 文档关系不进入 `papers` 的闭合 schema；关联/解除不会触碰 canonical document ID、原件、manifest、chunker 状态或 index generation，项目删除只解绑不删原件。
- `source → document → chunk → raw` 契约复用既有 `point_id(document_id, chunk_index, chunker)`，引用 DTO 的 `chunk_id` 与既有 manifest/index identity 对齐。
- project chat 不自动吸收未关联全局文档，避免项目间意外共享；旧 `/api/kb/ask` 无 project_id 时维持原行为。

## 风险与阻塞

- 旧向量 payload 若缺少 canonical `document_id` 会被既有检索过滤自然排除；需要通过既有 reindex 恢复，不在 Task05 增加第二套兼容检索。
- 未执行全量 pytest、前端测试、部署或跨端 smoke；属于主 Agent/Task08 收口范围。
- 模型与精确 token 统计由运行时不可用；本轮按主 Agent 指定使用临时 Luna high。

## 主 Agent 后续动作

1. 由 backend-reviewer 复核关联锁、项目删除失败语义、project source 读取隔离和 prompt 预算。
2. 由 backend-tester 复跑本报告定向命令并补 API source/project 与 progress 失败/重连探针。
3. 与 frontend-dev 对齐 `sources`/`citations` DTO 和 source_url 跳转；Task08 再执行全量回归与部署 smoke。

## 运行信息

- 开始：2026-09-11 约 06:15（Asia/Shanghai）
- 结束：2026-09-11 06:45（Asia/Shanghai）
- 耗时：约 30 分钟（含 reviewer 修复与定向回归）
- 模型：临时 Luna high
- token 统计：运行时不可用
- 工具统计：读取/补丁编辑、py_compile、pytest、空白检查；精确调用数运行时不可用
- 进展日志：`.codebuddy/agent-logs/spec-022/task-05/backend-dev/20260911-start.md`
