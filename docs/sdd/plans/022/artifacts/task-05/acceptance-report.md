# Spec022 Task05 验收报告

## 结论

**PASS（Task05 受影响范围）**。后端定向测试、前端契约、JavaScript 语法、5 个 Node 合同及固定验收矩阵均通过；未发现 P0/P1/P2 阻塞项。未修改业务代码，未运行全量 pytest，未启动服务或执行浏览器点击验收。

## 执行信息

| 字段 | 结果 |
|---|---|
| 开始 | 2026-09-11 约 07:42 +0800 |
| 结束 | 2026-09-11 07:46 +0800 |
| 耗时 | 约 4 分钟 |
| 验收角色 | tester（Task05 双端验收总控） |
| 模型 | 临时 Luna high（按主 Agent 分派） |
| token / 工具统计 | 当前子代理运行时不可用 |
| 业务代码修改 | 无；仅新增本报告与 tester 进展日志 |
| 进展日志 | `.codebuddy/agent-logs/spec-022/task-05/tester/20260911-0745.md` |

## 定向命令与结果

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Task05 + 受影响后端 | `./.venv/bin/python -m pytest -q tests/test_task05_backend.py tests/test_conversations_api.py tests/test_memory_repositories.py tests/test_kb_document_routes.py tests/test_kb_routes.py tests/test_kb_ask_trace.py` | 0 | **114 passed in 13.43s** |
| 后端 Python 语法 | `./.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/retrieve.py backend/app/knowledge_base/infrastructure/prompts.py backend/app/api/routes_kb.py backend/app/api/routes_conversations.py backend/app/api/schemas.py backend/app/chat/application/conversation_service.py` | 0 | 通过 |
| 前端 Task02/03/05/论文契约 | `./.venv/bin/python -m pytest -q tests/test_frontend_conversation_contract.py tests/test_frontend_management_contract.py tests/test_frontend_paper_contract.py` | 0 | **44 passed in 0.03s** |
| JavaScript 语法 | `node --check frontend/app.js && node --check frontend/conversation-research.js` | 0 | 通过 |
| 5 个 Node 合同 | `for test_file in tests/test_frontend_conversation_research.js tests/test_frontend_kb_inspection_interaction.js tests/test_frontend_kb_inspection_pdf.js tests/test_frontend_kb_inspection_renderer.js tests/test_frontend_kb_inspection_runtime.js; do node "$test_file" || exit 1; done` | 0 | **5/5 PASS** |
| 差异空白检查 | `git diff --check` | 0 | 通过 |
| 敏感字段脱敏探针 | `./.venv/bin/python -c 'from backend.app.api.routes_conversations import _redact_sensitive; ...'` | 0 | token/Bearer/authorization/password/cookie 值均替换为 `[REDACTED]` |

未执行全量 pytest、部署、浏览器 E2E；符合 Task05 tester 范围。`git diff --check` 覆盖当前工作树差异且无输出。

## 固定验收矩阵

| 验收点 | 判定 | 证据 |
|---|---|---|
| project association sidecar 不改变原件、document ID、manifest/index | PASS | `tests/test_task05_backend.py` 关联/解绑测试验证 canonical `papers.json` 不含 `project_id`、ID/hash/chunker 与原件字节不变，sidecar 独立写入；实现 `backend/app/knowledge_base/application.py:570-699` 使用 `project-associations.json` 原子保存。关联后状态 patch/reindex 兼容由后端测试与已有复审报告覆盖。 |
| 删除项目只解除关联 | PASS（代码/定向测试） | `tests/test_task05_backend.py` 验证解除后原件仍存在、canonical ID/chunker 保留且 sidecar 关系清空；`backend/app/api/routes_conversations.py:94-105` 删除项目前先调用 `clear_project_document_associations`，再删除项目，不调用 source/manifest/index 删除入口。主 Agent 需在部署 smoke 中补真实项目删除流程。 |
| project retrieval pre-filter | PASS | 后端测试验证同一 canonical allowlist/filter 到达 dense 与 sparse 两路，并在 RRF/reranker/top-k 前过滤；`backend/app/knowledge_base/infrastructure/retrieve.py:186-225` 与 `backend/app/api/routes_conversations.py:215-232` 提供代码证据。 |
| sources 在 final token / generation completed 后显示，最多 5 条 | PASS | `tests/test_task05_backend.py::test_conversation_sources_follow_final_token_and_are_bounded` 通过（8 条命中裁为 5 条且晚于 token）；后端 `routes_conversations.py:271-280` 先保存 completed、发送 generation completed，再发 sources；前端 `app.js:858-878` 暂存 `pendingSources`，仅在 `generationCompleted` 后渲染；renderer `normalizeSources`/`slice(0, MAX_SOURCES)` 固定 0–5。 |
| sources 单项展开/二次点击收起 | PASS | `tests/test_frontend_conversation_research.js` 验证 5 个编号、一次只展开一个、再次点击收起；`frontend/conversation-research.js:101-139` 通过 `aria-expanded`、`hidden` 和 active index 管理互斥展开。 |
| processing steps 历史默认折叠 | PASS | 前端契约测试通过；`frontend/app.js:359-374` 从 `/api/messages/{id}/processing-steps` 安全恢复并在 hydrate 后调用 `collapseConversationProcessing`，失败时显示降级提示并折叠。 |
| processing EOF / Abort / reconnect 状态 | PASS（静态契约） | `tests/test_frontend_conversation_contract.py` EOF/Abort/reconnect 契约通过；`app.js:837-847,880-900` 对 reconnect/EOF 标记 skipped/failed/interrupted，AbortError 静默，清除来源并保留可见状态。未在浏览器现场断开连接。 |
| XSS 与敏感参数 | PASS | Node renderer 合同验证 hostile HTML 仅作为 `textContent`、外链 URL 受 allowlist 限制；前端 44 项契约验证处理步骤/来源 DOM 安全与资源版本；`app.js` Markdown 路径经 DOMPurify，来源 renderer 不使用 `innerHTML`。后端脱敏探针及 `routes_conversations.py:117-123,262-292` 验证工具失败/错误摘要不会泄露 token、Bearer、authorization、password、cookie 值。 |

## 非阻断限制与风险

1. tester 隔离环境访问 `http://127.0.0.1:8000/api/health` 返回 curl 退出码 7、HTTP 000（服务未运行/不可达）。按任务约定不将该环境限制判为产品失败；主 Agent 必须在可监听环境完成部署 health、项目文档关联/删除、项目会话 RAG SSE 及 sources smoke，并清理临时数据。
2. 本轮未进行独立浏览器点击与真实断流；静态契约、Node 合同和后端 TestClient 覆盖通过。真实 UI/网络竞态仍由主 Agent 的部署 smoke 或 Task08 收口验收补齐。
3. 旧向量 payload 若缺少 canonical `document_id`，allowlist 会安全排除，需按既有 reindex 恢复；不构成当前 Task05 阻塞。

## 主 Agent 后续动作

1. 在可监听环境启动当前工作树，完成 `/api/health`、OpenAPI、临时项目+文档关联/解绑/删除、项目会话 SSE（progress、sources、done）smoke，并确认原件和索引未被删除。
2. 将本报告与 Task05 backend/frontend implementation、test、review 交接，追加架构师签字。
3. Spec022 收口时执行全量 pytest、最终验收、部署运行时验证和状态台账更新；本报告不单独将 Spec 标记为完成。

## 签字

- 验收执行：tester（临时 Luna high）
- 架构师签字：待主 Agent 按收口流程确认
