# Task10 后端定向测试报告

## 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task10_backend.py --tb=short` | 0 | 8 passed |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_chat_route.py tests/test_task05_backend.py --tb=short` | 1 | 7 passed, 2 legacy observation assertions failed in `test_chat_route.py`; Task05 backend remains compatible |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_task10_backend.py --tb=line` | 1 | 47 passed, 4 failed；2 个旧 prompt/观测断言与新脱敏 role 契约冲突，1 个旧 conversation prompt seam 断言冲突，1 个异步 worker timing 失败 |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=line` | 0 | 1 passed（说明该 worker timing 失败具有时序性） |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task10_backend.py --tb=short` | 0 | 8 passed |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_memory_repositories.py --tb=line` | 0 | 23 passed |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task05_backend.py --tb=line` | 0 | 7 passed |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_conversations_api.py tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_task10_backend.py tests/test_memory_repositories.py tests/test_task05_backend.py --tb=line` | 1 | 63 passed, 1 个异步 worker timing 失败；其余旧 prompt/观测/KB state 断言已按新 role-aware/脱敏契约更新并通过 |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=line` | 0 | 1 passed（组合运行中的 worker timing 失败可独立重跑通过，标记为时序性 flaky 证据） |
| `python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py backend/app/chat/application/chat_runner.py backend/app/chat/application/chat_graph.py backend/app/platform/ollama_direct.py backend/app/platform/observability/spans.py backend/app/platform/observability/__init__.py backend/app/api/schemas.py backend/app/api/routes_conversations.py backend/app/api/routes_chat.py backend/app/api/routes_article.py backend/app/api/routes_kb.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

人工 smoke 亦确认：新数据库 schema version=6；重复 initialize 保持 WAL；SystemRule 0/12,000/12,001 Unicode 边界、停用和清空；启用规则会话 SSE 先完成 `system_rule` 步骤且 fake run 捕获独立 `system`/`user`；读取失败返回 `SYSTEM_RULE_UNAVAILABLE` 且不调用模型。

## 未完成/阻塞

未运行全量 pytest（遵守 Task10 定向边界）。系统默认 Python 缺少 FastAPI；项目 CodeBuddy 虚拟环境可用。本轮已将历史 v1→v6 迁移断言从旧版本 5 更新为 6，并补充 reviewer P1 的 role/fail-closed/KB/global/schema 损坏测试；同时将 conversation/chat/KB 受影响旧断言更新为新 role-aware、脱敏观测和 user/system 分离契约。Task10 定向测试 8 passed，memory repository 23 passed；组合运行仍出现 1 个异步 worker timing 失败，独立重跑通过，保留为时序性 flaky 证据。

## 主 Agent 后续动作

先完成 backend reviewer 与跨端 acceptance，再在 Spec022 收口阶段运行全量回归、部署和真实运行时验证。
