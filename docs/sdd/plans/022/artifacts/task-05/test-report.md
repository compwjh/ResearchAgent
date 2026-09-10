# Spec022 Task05 后端测试报告

## 结论

**PASS（后端定向范围，reviewer NO-GO 修复后）**。Task05 新增文档关联/解除、project 读取隔离、检索前 document allowlist、上下文预算、sources 顺序/上限/DTO 和 Task02/03 受影响兼容测试均通过。

## 命令与结果

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Python 语法 | `./.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/retrieve.py backend/app/knowledge_base/infrastructure/prompts.py backend/app/api/routes_kb.py backend/app/api/routes_conversations.py backend/app/api/schemas.py backend/app/chat/application/conversation_service.py` | 0；通过 |
| Task05 + 受影响后端回归 | `./.venv/bin/python -m pytest -q tests/test_task05_backend.py tests/test_kb_document_routes.py tests/test_kb_routes.py tests/test_kb_ask_trace.py tests/test_conversations_api.py tests/test_memory_repositories.py tests/test_chat_route.py tests/test_api.py` | 0；**130 passed** |
| 空白检查 | `rg -n '[[:blank:]]+$' <改动后端/测试文件>` | 0；无尾随空白 |

## 覆盖项

- 关联与解除只写独立 sidecar store，canonical papers.json schema、原件、hash、document ID、chunker 状态保持不变；批量解除不删除 source 文件。
- project A 只能看到 A 文档；project B 与未绑定作用域不会读取 A 文档。
- project document allowlist 在 dense/sparse 两路召回前共用同一个 filter，global 高分文档不会占满项目 top-k；引用 chunk_id 等于既有 point_id。
- 当前指令与当前问题不被 RAG evidence 预算裁剪；RAG evidence 独立预算生效。
- 会话 sources 最多 5 条，包含 source/chunk/document/original source URL 信息；sources 位于 token 与 generation completed 之后、done 之前。
- 既有 `/api/kb/ask` citations 顺序、旧聊天 API、旧 KB API、memory/conversation 测试均无回归。

## 未执行/阻塞

- 未跑全量 pytest、前端契约/浏览器测试、部署或跨端 smoke；符合 backend-dev 单端 Task05 边界。
- `git diff --check` 未执行，因为本角色被明确禁止 git 操作；以等价尾随空白扫描替代并通过。

## 运行信息

- 开始：2026-09-11 约 06:15（Asia/Shanghai）
- 结束：2026-09-11 06:45（Asia/Shanghai）
- 耗时：约 30 分钟
- 模型：临时 Luna high；token/精确工具统计运行时不可用
- 业务代码与测试均在本角色范围内完成；无 git commit/push
- 进展日志：`.codebuddy/agent-logs/spec-022/task-05/backend-dev/20260911-start.md`
