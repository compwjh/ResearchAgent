# Spec034 Task09 后端交付报告

状态：后端实现完成；Task09 后端定向合同与 Task02–08/Spec027/conversations 回归通过，待主 Agent 汇总双端验收。

## 改动文件

- `backend/app/api/routes_research.py`
  - 新增 `POST /api/research-sessions`，创建/复用会话时校验 owner、会话/项目归属，继承项目，生成 `深度研究：<主题>` 标题（新会话）和统一首条用户消息。
  - 以 `trigger_message_id`/`idempotency_key`（无 key 时使用安全请求指纹）做可重放去重，并在竞争重试中只保留一对 user/assistant 消息。
  - 新增 owner-scoped `GET /api/research-sessions`，支持 `project_id`、`status`、`cursor`、`limit` keyset 分页并返回 `next_cursor`。
  - 旧 `POST /api/research-tasks` 改为兼容适配器：只进入统一 Session → Intake，绝不直接调用旧 `ResearchService.create_task`、不启动 Orchestrator；计划批准后才由统一命令创建 Task。
  - Intake 响应仅投影安全字段，不返回 Skill 正文；表单字段、时间范围和 owner 隔离 fail-closed。
- `backend/app/research/infrastructure/research_store.py`
  - 增加 `research_legacy_cleanup_audits` 与 `research_session_create_requests` 加性审计/幂等表。
  - Session→Task 批准物化从已校验 conversation 保留 owner/project/conversation 绑定；缺失 conversation 或 owner 不一致 fail-closed。
  - 增加 `dry_run_legacy_cleanup` / `execute_legacy_cleanup`（别名 `legacy_cleanup_dry_run` / `cleanup_legacy_tasks`）：旧版判定严格要求空 conversation 绑定且无 Session 绑定；dry-run 输出 Task/children ID、计数、保护计数和阻塞原因。
  - execute 必须消费同 owner、同目标快照的 dry-run token；缺失、过期、无匹配或目标变化均拒绝。审计注入 sessions/catalog/kb 的 before/after 计数或 digest，无法提供时明确标记 `unverified`，不声称 unchanged。
  - execute 使用 `BEGIN IMMEDIATE`，按 Artifact、checkpoint、通知、Run、事件、计划等从属数据到 Task 的顺序删除；任何 owner/活跃状态/计数/外键校验或删除失败整体回滚，失败审计写入 `aborted`；不删除会话、目录、KB，不创建备份。
- `backend/app/research/application/intake.py`
  - 活跃 Session 检查改用 owner/conversation 精确查询，不受列表分页上限影响；竞争重试在写消息前即可返回 active conflict。
- `backend/scripts/cleanup_legacy_research_tasks.py`
  - 新增维护脚本，默认 dry-run；必须同时传 `--execute --confirm` 才执行确认删除。
- `tests/test_spec034_task09_backend.py`
  - 覆盖 dry-run children ID/计数与精确删除、绑定/owner isolation、活跃任务阻断无部分删除、旧 POST 进入 Intake 且不创建 Task、已存在 v3 research DB 的审计表补建，以及并发幂等、项目物化/mismatch、游标、dry-run token 和跨库审计。
- P1-5 跨库 fail-closed 修复
  - execute 仅在 sessions/catalog/kb 均为已验证且前后值一致时提交删除；任一快照不一致抛 `LEGACY_CLEANUP_CROSS_STORE_CHANGED`，未验证抛 `LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED`。
  - 两类失败均回滚 Task/children 删除，并在事务外写入 `status=aborted` 审计，包含 research before/after、cross-store before/after、`unchanged=false` 与失败状态。
  - Task09 合同新增跨库变化回滚和 unverified 回滚测试；成功路径显式注入 verified snapshot。
- `backend/app/memory/repository.py`
  - 增加基于稳定幂等键的事务内消息对创建/重放，避免 Session 重试写入重复 user/assistant 消息。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py` | 0 | 12 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py`（P1-5 修复后） | 0 | 14 passed；含 changed/unverified fail-closed 回滚与 aborted 审计字段断言 |
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py` | 0 | 176 passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/research/infrastructure/research_store.py backend/app/research/application/intake.py backend/app/research/application/approval_service.py backend/app/memory/repository.py backend/scripts/cleanup_legacy_research_tasks.py` | 0 | 通过 |
| `.venv/bin/ruff check [本轮后端文件及 Task09 测试] --output-format concise` | 0 | All checks passed |
| `git diff --check -- [本轮后端文件及 Task09 测试]` | 0 | 通过 |
| `.venv/bin/python backend/scripts/cleanup_legacy_research_tasks.py --help` | 0 | CLI 可直接运行；默认 dry-run，execute 需 confirm + dry-run-id |

### P1-5 修复验证

- 跨库 sessions/catalog/kb 任一值由 before 到 after 变化时，execute 返回稳定错误 `LEGACY_CLEANUP_CROSS_STORE_CHANGED`，目标 Task 与所有 children 保留，execute audit 为 `aborted`。
- 快照 provider 返回 `status=unverified`（或缺失 provider）时，execute 返回稳定错误 `LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED`，不执行删除并写入含 before/after/status 的 aborted audit。

## 决策依据与边界

- 复用既有 `ResearchIntakeCoordinator`、`ResearchStore`、`MemoryRepository` 和 Task04 统一 Session/Approval 边界；未创建第二套 Task 模型或 Orchestrator。
- 旧 Task 只有在 `conversation_id` 为空且没有 `research_sessions.research_task_id` 绑定时才进入候选；有 conversation、已绑定 Session、其他 owner 的 Task 一律保护。
- 活跃无绑定旧 Task 只在 dry-run 中报告为 `LEGACY_CLEANUP_ACTIVE_RESEARCH` 阻塞项；execute 任何目标一旦发现该项即中止，不删除同批终态 Task。
- 终态绑定研究的会话、Task、报告与 Artifact 不进入旧清理；旧未绑定 Task 的私有计划/WorkItem/Event/Selection/Report 等子数据才按维护范围删除。论文目录、知识库及会话库不被删除；审计会记录其 before/after 计数或 digest 以及 `unchanged`/`unverified` 状态。

## 风险 / 阻塞 / 后续动作

- 当前执行环境未进行真实 Ollama 调用；Task09 本身只验证 Session/Intake 与清理边界，不依赖模型网络。
- 新 Session 创建是既有 memory 库与 research 库之间的可重放 Saga；进程内并发由锁和幂等记录保护，若跨库第二步失败，保留可重放记录，不伪造 Task 已创建。
- CLI 默认不注入外部 catalog/KB provider 时审计为 `unverified`；部署维护任务应提供只读 snapshot provider 后才可将跨库 `unchanged` 判为 true。
- 主 Agent 应运行双端 Task09 合同、真实浏览器/服务 smoke，并在 Spec 收口时复核审计报告中的实际删除数量。

## 执行统计

- 执行时间：2026-09-13 14:15–15:40 CST，总计约 85 分钟（以进展日志首末时间戳计）。
- 模型：当前执行任务的 Agent（主 Agent 指定临时 Luna high）；未使用网络、子 Agent、commit、push、merge、reset、stash、clean。
- 工具：`apply_patch`、`exec_command`；命令执行均在工作区内完成。Task09 12/12 与定向回归 176/176 通过；focused Ruff、py_compile 与 CLI smoke 通过。

进展日志：`.codebuddy/agent-logs/spec-034/task-09/backend-dev/20260913-141500.md`。
