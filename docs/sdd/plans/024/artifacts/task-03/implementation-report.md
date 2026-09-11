# Spec024 Task03 后端实现报告

## 结果状态摘要

**条件完成（6 类 P1 已逐项修复，待主 Agent/独立 tester 收口）**。已在既有会话链路实现一致 SQLite v7 迁移快照与审计矩阵、真实 Ollama 能力 probe、统一 resolver、LangChain/direct 推理提取与 carry 过滤、SSE envelope/event_seq 状态保护、事务内 preference 和严格 observability allowlist。xhigh 现在仅在真实 HTTP `think=true` 且返回非空 thinking 时以 evidence_id 作为 probe-supported；无证据仍 pending/unavailable，不静默降档。server log 改为可选审计证据的政策建议待架构师同步正式文档。

## 改动文件

- `backend/app/chat/application/reasoning.py`
- `backend/app/chat/application/chat_graph.py`
- `backend/app/chat/application/chat_runner.py`
- `backend/app/platform/ollama.py`
- `backend/app/platform/ollama_direct.py`
- `backend/app/platform/observability/spans.py`
- `backend/app/memory/models.py`
- `backend/app/memory/repository.py`
- `backend/app/api/schemas.py`
- `backend/app/api/routes_conversations.py`
- `tests/test_spec024_backend.py`
- `tests/test_conversations_api.py`（更新 Task03 fake probe/effort 签名）

## 测试命令、退出码和结果

- `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_ollama_direct.py`：退出码 0，29 passed，1 skipped；`tests/test_spec024_backend.py` 为 9 passed，覆盖迁移 marker/restart、probe evidence、carry sanitizer、sequence gap、持久序列单调性与 allowlist。
- `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_conversations_api.py tests/test_ollama_direct.py`：退出码 0，40 passed，1 skipped。
- `PYTHONPATH=. .venv/bin/python -m py_compile ...`（全部改动 Python 文件）：退出码 0。
- `git diff --check`：退出码 0，无空白错误。
- `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_ollama_service.py`：退出码 1，10 passed、5 failed。失败均为既有环境/旧链路问题：默认数据文件被其他 Python 进程持有导致 `SYSTEM_RULE_UNAVAILABLE`，以及当前环境 `OLLAMA_BASE_URL` 为 `http://192.168.31.180:11434` 而旧断言固定 localhost；本 Task 未修改普通 `/api/chat` 或配置来源。
- `tests/test_memory_repositories.py tests/test_task09_conversation_filters.py`：28 passed、1 failed；旧测试仍断言 schema version 6，而 Spec024 已升级为 v7。

## 产物路径

- 实现报告：本文件
- 后端评审报告：`docs/sdd/plans/024/artifacts/task-03/backend-review-report.md`
- 后端测试报告：`docs/sdd/plans/024/artifacts/task-03/backend-test-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-024/task-03/backend-dev/20260912-task03.md`

## 决策依据

- 复用现有 `chat_runner`、`chat_graph`、`ollama_direct` 和 conversation SSE，不创建第二模型客户端/聊天链路。
- reasoning filter 统一 NFC、移除模板标记与不可显示控制字符，并按 Unicode code point 20,000 截断。
- `off` 发送 provider `false`；low/medium/high 发送原样字符串；xhigh 没有 Task02 server-log 证据，因此保持 unsupported/pending。
- 会话新增 reasoning effort，首条消息继承 owner 最近值；PATCH 变更同时更新 owner preference。
- 迁移在一次事务中增加 v7 字段，记录 marker/backup hash，清理会话及严格依赖，置空 MemoryEvidence 引用并保留长期数据。
- 观测层删除原始 thinking，仅保留 reasoning_present、reasoning_chars 与兼容计数字段。

## 风险与阻塞

- 生产库当前有外部 Python 进程持有锁，无法在本 Task 直接执行真实库迁移验证；未触碰生产数据。
- xhigh 仍缺受信 server-log 证据，不能宣称支持或设为默认。
- 旧 schema v6 测试需要由主 Agent/验收阶段更新为 v7 契约。
- `tests/test_conversations_api.py` 的 fake probe/effort 签名已同步；生产路径不再通过 TypeError 回退丢失本轮 effort。

## P1 修复记录

- 迁移：v6→v7 使用事务前 `Connection.backup()`（已有 v6 文件）或 `serialize()`（fresh path），全矩阵记录 before/after/action/FK，marker/CHECK/DDL 校验，重启幂等。
- 能力：逐档真实 `/api/chat` 5 秒 probe 与 5 分钟 model cache；xhigh HTTP evidence_id 政策建议为可支持条件，server log 仅可选审计。
- 路由/状态：direct off payload 固定为 `think=false`；移除 TypeError fallback；preference 读写同事务；持久 event seq 严格单调、gap/terminal guard；carry filter 防跨 chunk 模板泄漏。
- 观测：固定 allowlist，去除 timings/input/output/thinking_chars/session/tags 等额外字段，路由补阶段字段。

## 主 Agent 后续动作

1. 复核 `routes_conversations.py` 的 SSE 终态与迁移代码，并在可控的临时 v6 数据库上跑成功/回滚矩阵。
2. 让 backend-reviewer/backend-tester 按 Task03 白名单复核；确认是否需要把 stateless `/api/chat` 纳入后续任务。
3. 释放或隔离默认数据文件锁后重跑 `test_chat_route.py`；更新 schema v6 旧断言。
4. 补齐 xhigh server-log 证据后再决定是否开放 xhigh。

## 开始、结束、总耗时

- 开始：2026-09-12T00:15:00+08:00（约）
- 结束：2026-09-12T00:45:25+08:00
- 总耗时：约 30 分钟

## 模型/token/工具统计

- 模型：当前 Agent（临时 Luna high）
- token：运行时未提供精确统计，未估算
- 工具：只读 shell、apply_patch、pytest、py_compile；未执行 reset/stash/clean/push/merge
