# Spec022 Task04 后端验收报告

## 结论

**PASS（Task04 后端定向验收）**。Task04 精确后端测试、Task02/03 受影响后端回归、旧聊天兼容回归、Python 语法检查和 diff 空白检查均通过；未发现 P0/P1 阻塞项。测试过程未修改业务代码。

本报告只覆盖后端验收边界，不替代 Spec022 收口阶段的全量回归、前端验收、部署或跨端 smoke。

## 执行信息

| 字段 | 结果 |
|---|---|
| 开始 | 2026-09-11 06:09 +0800（约） |
| 结束 | 2026-09-11 06:13:35 +0800 |
| 耗时 | 约 4 分 35 秒 |
| 验收角色 | backend-tester |
| 模型 | 临时 Luna high（按主 Agent 分派） |
| token 统计 | 运行时不可用 |
| 工具统计 | 运行时未提供精确计数；使用文件读取、pytest、py_compile、curl、git diff check |
| 业务代码修改 | 无；仅新增本验收报告与 backend-tester 进展日志 |
| 进展日志 | `.codebuddy/agent-logs/spec-022/task-04/backend-tester/20260911-acceptance.md` |

## 测试命令、退出码与数量

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Task04 精确后端测试 | `.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py` | 0 | **34 passed in 1.76s**（外层 real 2.28s） |
| Task02/03 受影响 + 旧聊天兼容 | `.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_api.py` | 0 | **50 passed in 5.60s**（外层 real 6.16s） |
| Python 语法 | `.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py` | 0 | 通过 |
| Diff 空白 | `git diff --check` | 0 | 通过 |

未运行全量 pytest、前端测试、浏览器 E2E 或部署命令，符合 backend-tester 单端验收边界。

## 验收矩阵

| 验收点 | 结果 | 证据 |
|---|---|---|
| Raw append-only、重复 trigger 幂等 | PASS | `test_raw_events_are_append_only_and_duplicate_trigger_is_idempotent`；重复 idempotency key 返回首事件，payload 不被后写入覆盖，未提供业务 update/delete 面 |
| Raw message/cursor/session 隔离 | PASS | `test_raw_event_message_and_cursor_must_belong_to_same_conversation`；message owner/conversation 不匹配和跨会话 cursor 均拒绝 |
| schema v3 migration、半成品 fail-closed | PASS | `test_v1_database_is_migrated_atomically_and_message_evidence_is_nullable`、`test_v1_migration_failure_rolls_back_and_fails_closed`、`test_v3_malformed_table_fails_closed_at_startup` |
| 1001+ Raw 分页完整消费 | PASS | `test_evolution_worker_consumes_more_than_1000_events_and_recovers`；checkpoint input count=1001，首/末 event cursor 与摘要 source event 一致 |
| checkpoint Map/Reduce、失败恢复、摘要幂等 | PASS | `test_evolution_checkpoint_restarts_and_retries_without_duplicate_summary`；批次游标/状态持久化，重启后 attempts 递增且仅一条摘要 |
| stale running lease 接管与重启 | PASS | `test_stale_running_checkpoint_is_taken_over_and_resumes`；旧 lease 被接管并保留已保存进度 |
| 同 session mutex、重复触发与 retry | PASS | `test_evolution_session_mutex_and_candidate_promotion_require_evidence`、checkpoint/worker tests；同 session 互斥，失败 checkpoint 可重试 |
| candidate evidence gate / 原子性 | PASS | `test_candidate_and_evidence_are_atomic`；无 evidence 的 promote 拒绝，有 evidence 才能升格，memory+evidence 失败整体回滚 |
| supersedes 与 project 不升 global | PASS | `test_correction_candidate_uses_superseded_chain_only_when_promoted`、`test_evolution_scope_isolation_conflict_supersedes_and_budgeted_recall`；纠正候选保留 `supersedes_id`，升格才 supersede 旧记录，project scope 不自动改 global |
| recall scope 与独立预算 | PASS | `test_evolution_scope_isolation_conflict_supersedes_and_budgeted_recall`；owner/global/current-project 隔离，memory/summary 独立字符/token 预算 |
| 无匹配 summary 返回空 | PASS | `test_summary_recall_without_match_is_empty`；有 query 且无匹配不回退注入全部摘要 |
| 当前问题不重复 history | PASS | `test_chat_prompt_does_not_duplicate_current_user_message`；compose prompt 中 current user message 只出现一次 |
| worker enqueue、初始化失败不阻塞 SSE | PASS | `test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse`、`test_worker_initialization_failure_does_not_block_sse`；worker/process/start 异常均保持 HTTP 200 与 `done=completed`，Raw durable append 保留 |
| API/SSE 及旧聊天兼容 | PASS | `tests/test_conversations_api.py` 全部通过；`tests/test_chat_route.py`、`tests/test_api.py` 纳入 50 项回归，旧路径无回归 |

## API/service smoke

- FastAPI API smoke 由受影响测试内的 TestClient 执行：项目/惰性会话、未绑定项目隔离、SSE durable raw append、worker eventually checkpoint/summary/candidate、worker 处理失败与初始化失败降级、当前问题去重均通过。
- MemoryEvolutionService/MemoryEvolutionWorker smoke 由 repository/service 测试执行：Map 分批、Reduce 摘要、checkpoint 重启、stale lease、1001+ 事件、candidate/evidence 与 scope/budget 均通过。
- 只读外部服务检查：`curl http://127.0.0.1:8000/api/health` 和 `/openapi.json` 均 HTTP 000（服务未运行）。随后尝试用临时 `MEMORY_DB_PATH` 在 8011 启动 uvicorn，应用初始化完成但当前 tester 沙箱禁止监听地址（`Errno 1 operation not permitted`）。因此没有将沙箱限制误判为产品失败；需由主 Agent 在可部署环境完成真实 health/OpenAPI/端点 smoke。

## 风险与阻塞

1. **P2（非阻塞）**：worker 当前由消息入口启动；服务重启后若没有新请求，durable raw/retry work 会等待下一次消息触发扫描。后续可在应用 lifespan 增加 best-effort worker 启动，但不能让异步整理成为聊天硬依赖。
2. 当前 tester 沙箱无法监听本机端口，外部服务 smoke 未完成；这是验收环境限制，不影响上述 50 项后端/API 测试结论。
3. 未执行全量回归、前端验收、部署和跨端 smoke；不得据本报告单独将 Spec022 标记为完成。

## 主 Agent 后续动作

1. 在可监听环境启动当前工作树，完成 `GET /api/health`、OpenAPI 路由核对及最小临时项目/API/SSE smoke，清理临时数据。
2. 汇总本报告与 frontend-tester/tester 报告，在 `docs/sdd/reviews/022-acceptance-review.md` 完成 Task04 及跨端验收章节和架构师签字。
3. Spec022 收口时按门禁执行全量 pytest、状态台账更新、部署与运行时验证；保留上述 P2 生命周期风险记录。
