# Spec022 Task05 修复轮后端最终复审报告

## 结论

**GO（P1/P2 范围通过）**。最终补丁已关闭本轮 P1：处理步骤按稳定三元组原位收口；记忆分析在回答 SSE 外异步执行，job/item 持久化并支持分页/决策；claim、进度、终态以及记忆、证据、item 写入均受 lease token/version fencing；分类器异常会把 job 标记为 `failed`；项目快照和 scope 隔离未发现跨项目写入；原有聊天/RAG 路径定向回归通过。

仍有 3 项非阻塞 P2，主要是并发重复记忆的数据库级兜底、迁移完整性校验覆盖面以及分类模型 fallback。建议纳入后续硬化，不阻塞本 Task 修复轮验收。

## 评审范围与时间

- 开始：2026-09-11 12:04:00 CST
- 结束：2026-09-11 12:07:12 CST
- 耗时：约 3 分 12 秒
- 评审文件：Spec022、Task05 计划、`models.py`、`repository.py`、`conversation_service.py`、`routes_conversations.py`、`schemas.py`、`config.py` 及 Task05/会话/仓储定向测试。
- 约束：只读评审；未修改业务代码，未执行 Git 操作。

## P1

### P1 清零：processing_steps 原位更新和终态收口

- `backend/app/memory/repository.py:337-358` 的 v3→v4 迁移补齐 `logical_sequence`，清理旧的 running/terminal 重复行，并创建 `uq_steps_message_kind_sequence` 唯一索引。
- `repository.py:1223-1249` 以 `(message_id, kind, logical_sequence)` 查询已有行；running→terminal 更新同一 `step_id`，running→running 只更新摘要，不新建完成行。
- `repository.py:1260-1274` 禁止 terminal 回到 running；`repository.py:1251-1258` 将残留 running 一次性收口为 completed/failed/interrupted/skipped。
- `tests/test_task05_memory_analysis_repair.py:21-31` 已验证同一 `step_id`、唯一记录及 terminal 不能 reopen。

结论：满足 Spec022 `:132` 的稳定身份和“终态不可回到 running”要求。

### P1 清零：异步分析、持久化及 lease 副作用 fencing

- `backend/app/api/routes_conversations.py:301-319` 请求路径只创建 message-bound job 并 enqueue；分类和记忆写入由后台 worker 执行，返回回答 `StreamingResponse` 不等待分类模型。
- `backend/app/chat/application/conversation_service.py:29-98` 调用配置模型 `run_chat(..., think=False)`，解析结构化 JSON；`config.py:12-15` 将回答模型与独立 `MEMORY_ANALYSIS_MODEL` 分开配置。
- `repository.py:1075-1095` claim 使用旧 `updated_at` CAS、随机 `lease_token` 和递增 `lease_version`；`repository.py:1102-1117` progress/finish 只接受当前 token/version。
- `repository.py:1119-1140` 的 item 写入检查当前 running lease；`repository.py:1142-1172` 在同一事务内校验 lease，再写 memory、evidence 和 analysis item。旧 worker 即使继续执行，也不能写入新的 memory/item。
- `conversation_service.py:540-542` 分类结果带 `classification_error` 时写入 `failed` job；`conversation_service.py:572-590` 对候选保存异常写 failed item，并以 partial/failed 终止，而不是伪装为 completed。
- `tests/test_task05_memory_analysis_repair.py:54-63` 验证 JSON/分类异常导致 `failed/CLASSIFIER_FAILED`；`:147-175` 验证旧 token/version 不能 finish、写 memory 或写 item；`:85-99` 验证多 item、分页和重复调度幂等。
- `routes_conversations.py:422-437` 返回 job/analysis、items、next_cursor；`:491-512` 提供逐条与批量 decision，字段由 `schemas.py:65-75` 的决策契约约束。

结论：回答链路与分析链路解耦；job/item、分页/决策、旧租约副作用隔离均达到 P1 要求。

### P1 清零：项目 snapshot、全局/项目隔离、删除/中断/异常边界

- `repository.py:1045-1063` 在 job 创建时保存 `project_id_snapshot`，而不是在 worker 执行时重新读取会话项目。
- `conversation_service.py:470-512` 以 job snapshot 选择 project scope；`repository.py:1149-1153` 校验 global 不得带 project、project 必须存在；`repository.py:1019-1037` 对 evidence 的 conversation/message project 归属做一致性校验。
- `conversation_service.py:528-531` 快照项目已删除时以 `PROJECT_SNAPSHOT_GONE` 失败；会话移动不会将既有任务改写到新项目。
- `routes_conversations.py:454-488` 决策接口校验目标 project active、跨项目 evidence 时不写不匹配证据；普通聊天异常/中断仍在 `routes_conversations.py:252-280` 持久化 assistant 和步骤终态。

结论：未发现删除后写入其他项目、全局记忆带 project 或会话移动改变任务 scope 的 P1 缺陷。

### P1 清零：原有聊天/RAG 接口保持

- `routes_conversations.py:213-251` 仍复用既有上下文装配、RAG hits、`run_chat` token 流、sources/citations 和 done 顺序；记忆分析 enqueue 在 SSE 建立前仅做持久化排队。
- `tests/test_task05_backend.py:105-116` 验证 RAG 过滤、最多 5 个来源、token 后 sources 及 done；`tests/test_conversations_api.py:43-90,138-160,188-232` 验证普通聊天、记忆召回失败、中断和后台 worker 异常不阻断回答。

## P2（非阻塞）

### P2-1：跨不同 analysis job 的重复记忆仍是读后写竞态

证据：`conversation_service.py:448-454` 的 `_find_duplicate()` 在事务外扫描现有 memory；`repository.py:1159-1169` 的原子写只按同一 `analysis_id + statement` 复用 item，随后无条件 `INSERT INTO memories`。数据库 schema `repository.py:188-197` 只有 project/status 索引，没有按 owner/scope/project/规范化 statement 的唯一约束或 digest。

影响：同一分析任务的重复调度已幂等，但两个并发 analysis job 同时分析相同陈述时，可能都通过事务外 duplicate 检查并各插入一条 active memory，违反 Spec022 `:162-163` 的“完全重复不得新建记录”。

建议：增加规范化 statement digest（按 owner/scope/project 组合唯一）或在同一事务内执行原子 insert-or-existing；保留现有 lease fencing。此为低概率并发数据卫生问题，当前不构成 P1。

### P2-2：v4/v5 启动校验未验证分析表的外键和索引完整性

证据：`repository.py:395-410` 的 `_is_schema_v4()` 检查 processing-step 唯一索引、分析表存在及列集合，但没有检查 `memory_analysis_jobs.user_message_id`、`memory_analysis_items.analysis_id/memory_id` 的 FK，或 `idx_analysis_jobs_work`、`idx_analysis_items_page`；`repository.py:421-425` 的 v5 校验只额外检查 lease 两列。

影响：正常迁移创建的 schema 已包含所需 FK/index（`repository.py:359-392`），但一个被错误标记为 v4/v5、仅缺分析 FK/index 的数据库可能通过启动校验，直到运行时才暴露完整性或性能问题。

建议：在后续迁移硬化中用 `PRAGMA foreign_key_list`/`PRAGMA index_list` 补齐 fail-closed 检查，并增加“部分 schema 不可启动”的迁移测试。

### P2-3：未实现配置的小模型 fallback 尝试

证据：`config.py:15` 仅提供一个 `MEMORY_ANALYSIS_MODEL`；`conversation_service.py:49-51` 只调用传入/配置的一个模型，异常在 `:97-98` 直接转为 `CLASSIFIER_FAILED`，未发现候选小模型列表或顺序 fallback。

影响：符合当前“聊天继续、分析失败可见”的失败语义，但未完全实现 Spec022 `:194` 的“默认不可用时尝试模型库配置的其他小型分类模型”。

建议：后续配置化增加 fallback 列表，并仅在模型不可用/超时类错误时切换；解析失败不应盲目换模型。该项不影响回答链路和数据安全，列为 P2。

## 迁移、契约和边界结论

- **迁移兼容：通过，留 P2-2。** `SCHEMA_VERSION=5`（`repository.py:36`）；v3→v4 处理旧重复步骤及唯一索引，v4→v5 增加 lease 字段（`:413-425`）；不完整 processing-step schema 会 fail-closed。正常旧库升级路径未见破坏性覆盖。
- **API/前端契约：通过。** job payload（`routes_conversations.py:388-404`）包含状态、cursor、计数、error_code 和时间；item payload（`:407-419`）包含 item/decision/memory/rationale；分页与单条/批量决策端点（`:422-512`）和 schema（`schemas.py:65-75`）一致。
- **Project snapshot/全局与项目隔离：通过，留 P2-1。** 自动保存使用 snapshot；人工项目决策显式校验 active project；未绑定会话不会读取项目记忆的既有路径由定向会话测试覆盖。
- **ProcessingStep：通过。** 原位更新、唯一索引、terminal 不 reopen、异常/中断收口均有代码和测试证据。
- **RAG/聊天：通过。** 现有 SSE、sources/citations、项目文档 allowlist 和普通聊天错误语义未见回退。

## 定向验证

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Task05 后端定向回归 | `./.venv/bin/python -m pytest -q tests/test_task05_memory_analysis_repair.py tests/test_task05_backend.py tests/test_conversations_api.py tests/test_memory_repositories.py` | 0 | **53 passed in 2.18s** |
| Python 语法 | `./.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py backend/app/platform/config.py tests/test_task05_memory_analysis_repair.py tests/test_task05_backend.py tests/test_conversations_api.py tests/test_memory_repositories.py` | 0 | 通过 |

测试期间 exporter 尝试访问本机 `127.0.0.1:3000` 并重试，但未影响 pytest 退出码；未运行全量回归、前端测试或部署 smoke。本次复跑覆盖的 53 项与主 Agent 汇总的后端 69 项属于不同测试集合，不能将两者简单相加为本报告独立结果。

## 建议动作

1. 本轮以 **GO** 进入 Task05 后端验收/合并门禁；不需要因 P2 阻塞。
2. 后续优先补 P2-1 的数据库级规范化去重和并发回归测试。
3. 在下一轮迁移维护中补 P2-2 的 FK/index fail-closed 校验，并实现 P2-3 的配置化分类模型 fallback。
