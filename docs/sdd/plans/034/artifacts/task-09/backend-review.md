# Spec034 Task09 后端评审

评审角色：backend-reviewer（只读代码评审）  
评审范围：Task09 后端工作树、Task09 计划与 backend-report、Spec034 的 Research Tab/兼容入口/删除规则、Task02–08/Spec027/conversations 后端接缝。未修改业务代码，未 commit。

## 结论

**NO-GO。** 定向回归和静态检查均通过，但当前实现仍有多项 P1：已绑定项目在批准创建 Task 时丢失；Session 创建竞争/重试会留下重复消息；Session 列表缺少冻结的 cursor 分页；清理命令未强制先 dry-run；清理审计未记录会话/目录/KB 的前后计数。因此不能将 Task09 后端标记为 GO 或进入 Spec 收口。

P0：无。  
P1：5 项。  
P2：4 项。

## 通过项

- 旧 `POST /api/research-tasks` 已改为创建统一 Session/Intake，未调用 `ResearchService.create_task` 或 Orchestrator；缺少 goal/conversation 时返回稳定 400，Session/消息归属校验仍经 `OWNER_ID`：`backend/app/api/routes_research.py:766-792`、`:497-541`。
- 新 Session 的跨库外部引用在 `ResearchStore.create_session()` 内调用既有 MemoryRepository 校验 conversation、owner 和 user trigger message，Session/Draft 插入在一个 research DB 事务中；活跃唯一索引保留 CAS 保护：`backend/app/research/infrastructure/research_store.py:161-175`、`:1555-1608`、`:615-624`。
- Intake 字段有白名单、时间范围/长度/嵌套限制，响应去除 Skill 正文，仅投影固定 Skill 元数据：`backend/app/api/routes_research.py:417-480`。
- Legacy cleanup 仅选择空 `conversation_id` 且无 Session binding 的 Task；活跃未绑定旧 Task 阻断整批 execute，删除顺序覆盖当前私有子表并使用 `BEGIN IMMEDIATE`，子计数不符会回滚；active/owner isolation 基本合同通过：`backend/app/research/infrastructure/research_store.py:1051-1164`、`:1189-1279`。
- `research_legacy_cleanup_audits` 为加性表，现有 v3 库会补建；失败时删除事务回滚后另写 `aborted` 审计，不会把部分删除暴露为成功：`backend/app/research/infrastructure/research_store.py:496-512`、`:1258-1279`。

## 阻断问题（P1）

### P1-1：批准后物化 Task 丢失 Session 的 project 绑定；显式 project mismatch 也被静默忽略

Task09 要求表单继承当前项目、并保持 owner/project/conversation 的统一绑定。`POST /research-sessions` 校验了显式项目存在，但当已有 conversation 时不检查该项目是否等于 conversation.project_id，随后响应仍返回 conversation 原项目：`backend/app/api/routes_research.py:506-512`、`:547-550`。更严重的是批准计划物化 ResearchTask 时，`PlanApprovalService._activate_task()` 将 `project_id` 固定为 `None`，所以即使创建阶段绑定了项目，批准后 Task/Tab 的项目过滤与后续审计都会丢失该绑定：`backend/app/research/application/approval_service.py:281-288`。应在 Session→Task 接缝中从 owner 校验过的 conversation/project 解析并保存 project_id，并对显式 project mismatch fail-closed（稳定 404/400/409 之一，不能静默忽略）。

### P1-2：Session 创建没有幂等接缝，竞争请求先写重复消息再以 409 失败

同一既有会话的两个并发 `POST /api/research-sessions` 都先通过预检查，然后分别在 `:534-536` 写入 user/assistant message pair；只有之后 `begin_research_intake()` 的唯一活跃 Session 约束才挡住第二个请求，`active_conflict` 在 `:540-541` 转为 409。临时并发探针实际得到 1 个 Session、两个结果（intake/409），但 conversation 消息从原始 2 条变成 4 条。前端创建请求不发送 trigger/idempotency key（`frontend/research-tasks.js:1318-1328`），故网络重试也会留下重复 turn。违反 Spec034 “同一消息重放/竞争不创建重复 Session/消息副作用”。应以 trigger_message_id/idempotency key 做事务内去重，或在写消息前原子抢占 Session；失败竞争不得留下 orphan user/assistant pair。

### P1-3：`GET /api/research-sessions` 缺少 Spec 冻结的 cursor 分页

Spec034 接口表明确要求 Session list 输入 `project/status/cursor` 并返回稳定分页；实现只接受 `project_id/status/limit`，直接调用无 cursor 的 `ResearchStore.list_sessions()`，响应也没有 `next_cursor`：`backend/app/api/routes_research.py:709-727`、`backend/app/research/infrastructure/research_store.py:1725-1740`。超过 100 条后无法稳定翻页，Research Tab 只能拿固定前 N 条。应复用 `(created_at,research_session_id)` keyset 语义并在响应返回 next cursor，同时保持 owner/project 过滤在游标解码前后的一致性。

### P1-4：破坏性 cleanup 未强制“先 dry-run，再 execute --confirm”

虽然脚本默认 dry-run，且 `--execute` 要求 `--confirm`，但 `main()` 没有要求先存在对应 owner/目标快照的 dry-run 审计；`--execute --confirm` 可直接执行删除：`backend/scripts/cleanup_legacy_research_tasks.py:18-29`。Store 层 `execute_legacy_cleanup()` 也只检查布尔 `confirm`，不验证先前的 dry-run：`backend/app/research/infrastructure/research_store.py:1189-1211`。临时空库实跑 `RESEARCH_DB_PATH=<tmp> ... cleanup_legacy_research_tasks.py --execute --confirm` 直接返回 `status=completed`，证明没有前置 dry-run 门禁。应让 dry-run 生成带 owner/目标 ID/计数的 token 或 audit ID，execute 必须显式消费同一快照并在锁内重新校验；没有匹配 dry-run 时拒绝执行。

### P1-5：清理审计没有记录会话/目录/KB 前后计数，无法证明“不波及”约束

Spec034 删除规则要求删除前后会话、论文目录和 KB 的计数/内容一致，Task09 计划也要求用前后计数验证。当前 snapshot 只查询 research.sqlite3 的 Task、children、bound_tasks 和 active_sessions：`backend/app/research/infrastructure/research_store.py:1127-1164`；execute 的 `before/after` 也只是同一 snapshot：`:1246-1250`。没有 MemoryRepository 会话计数、论文目录计数/内容摘要或 KB 计数/内容摘要，也没有跨库校验结果字段。当前删除 SQL 未直接触碰这些库是必要但不充分的证据，审计产物不能证明约束满足。应由维护编排层注入只读计数/内容 digest，在 execute 同一锁定窗口可行范围内记录 before/after，并在不一致时 abort；至少报告明确的 `sessions/catalog/kb: unchanged/unverified` 状态，不能将未测量写成已验证。

## 非阻断问题（P2）

- Intake 激活失败无论原始错误是 `SKILL_DISABLED`/`CAPABILITY_NOT_AUTHORIZED` 还是依赖故障，都由 `create_research_session()` 统一转为 HTTP 503：`backend/app/api/routes_research.py:542-544`。这与 Spec034 对 disabled/unauthorized 的 403 错误矩阵不一致，建议保留稳定 code 并按 code 映射 HTTP 状态；同时 `_api_error()` 响应缺少统一错误体中的 retryable/subject_version/data 字段。
- Legacy adapter 只把 `goal` 映射为 Intake `topic`，丢弃旧请求的 `quality_profile`、`target_paper_count`、`language`、`review_plan_first`：`backend/app/api/routes_research.py:779-784`。若兼容客户端仍依赖这些字段，应转为受白名单约束的 depth/language/constraints；否则应在兼容文档明确其被忽略。
- `_intake_coordinator()` 在 provider 缺失时直接装配 Coordinator、SkillRegistry 和 ToolRegistry：`backend/app/api/routes_research.py:190-201`。这使 API 层拥有业务装配旁路并可能与启动时 provider 不同源；建议生产路径 fail-closed，仅在测试 fixture 显式注入 provider。
- `dry_run_legacy_cleanup()` 文档称“non-mutating”，实际会持久化 audit row：`backend/app/research/infrastructure/research_store.py:1166-1184`。这是合理的审计写入，但 CLI/运维文档应明确 dry-run 仍会新增审计记录，避免操作者误以为研究库完全无写入。

## 验证记录

| 检查 | 退出码/结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py` | 0；169 passed in 4.12s |
| `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/research/infrastructure/research_store.py backend/scripts/cleanup_legacy_research_tasks.py` | 0；通过 |
| `.venv/bin/ruff check backend/app/api/routes_research.py backend/app/research/infrastructure/research_store.py backend/scripts/cleanup_legacy_research_tasks.py tests/test_spec034_task09_backend.py --output-format concise` | 0；All checks passed |
| `git diff --check --`（Task09 后端文件/测试路径） | 0；通过 |
| 并发 `POST /api/research-sessions` 临时探针 | 1 Session，但既有 conversation 消息由 2 条增至 4 条；确认 P1-2 |
| 已有 conversation + 另一 owner 归属项目 ID 临时探针 | 请求成功，响应仍绑定 conversation 原 project；显式 project 被静默忽略；确认 P1-1 |
| `RESEARCH_DB_PATH=<tmp> ... cleanup_legacy_research_tasks.py --execute --confirm`（无先前 dry-run） | 直接 `status=completed`；确认 P1-4 |
| active legacy cleanup 临时探针 | `LEGACY_CLEANUP_ACTIVE_RESEARCH`，2 个 Task 均保留且审计为 `aborted`；active 阻断通过 |

## 评审决策

**NO-GO。** 现有 169 条回归和静态检查只证明基本适配、owner isolation、active 阻断与删除子表路径；在修复 P1-1 至 P1-5 并补充项目物化、并发/重放消息、cursor、前置 dry-run token、跨库不变计数测试前，不得将 Task09 后端报告改为 GO 或推进 Spec034 收口。

进展日志：`.codebuddy/agent-logs/spec-034/task-09/backend-reviewer/20260913-000000.md`。
