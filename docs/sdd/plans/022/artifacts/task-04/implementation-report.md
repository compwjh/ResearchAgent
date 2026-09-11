# Spec022 Task04 后端实现报告

## 状态摘要

**已完成（后端范围）**。在 Task03 的单一 `MemoryRepository`、SQLite WAL/事务和 owner scope 上完成 schema v3 的 Raw 事件、会话摘要、进化 checkpoint 与可重启 Map/Reduce service；聊天 SSE 保持兼容，整理失败不会阻塞回答。

## 改动文件

- `backend/app/memory/models.py`：新增 `RawEvent`、`ConversationSummary`、`EvolutionCheckpoint` DTO。
- `backend/app/memory/repository.py`：schema v2→v3 幂等迁移；Raw 事件追加/幂等读取；摘要 upsert/召回；checkpoint claim/progress/finish；带独立预算的 scoped recall；带 evidence 门禁且不改 scope 的 `promote_memory`。
- `backend/app/chat/application/conversation_service.py`：新增 `MemoryEvolutionService`；本地 session mutex、trigger 记录、批处理/断点恢复、摘要 Reduce、候选生成、correction superseded 链；扩展 prompt 注入相关摘要并保留旧签名兼容。
- `backend/app/api/routes_conversations.py`：聊天流 best-effort 追加 `user_message`、明确记忆、用户纠正、上下文压力、工具失败 Raw 事件；召回独立记忆/摘要预算并注入 prompt。
- `tests/test_memory_repositories.py`、`tests/test_conversations_api.py`：Task04 定向覆盖。

## 数据/接口契约

- `SCHEMA_VERSION=3`，新增 `raw_events`（append-only，`owner_id + conversation_id + idempotency_key` 幂等）、`conversation_summaries`（每会话一条 active 摘要）、`evolution_checkpoints`（每会话/阶段唯一、状态/批次/游标/attempts/state_json/error）。均复用现有 FK、WAL、事务和 owner 校验；项目删除按既有级联规则清理会话派生数据。
- `MemoryRepository.append_raw_event/list_raw_events` 是唯一 Raw 写入/读取面；不存在 update/delete 业务入口。
- `MemoryEvolutionService.record_trigger/process_session` 为本地线程 worker/显式 service API。允许 `explicit_memory`、`user_correction`、`tool_failure`、`context_pressure`、`idle`、`retry`；同 session 进程互斥，checkpoint 在每个 Map 批次后持久化，失败可重启后续跑。
- 自动提取只产生 `candidate`；`promote_memory` 无 evidence 拒绝，有 evidence 才能升格，并保留 global/project scope。候选不会把 project 自动提升为 global；correction 候选可带 `supersedes_id`，升格时原记录标记 `superseded`。
- `list_recall_context` 独立控制 `memory_char_budget`、`summary_char_budget`，并支持 token 预算换算；召回仅限 owner 的 global + 当前 project，摘要按项目相关性筛选。prompt 顺序仍为项目明确指令、长期记忆/摘要、历史、当前问题，正文和当前指令不被摘要预算挤掉。
- 聊天端点未新增公开入口，原 SSE `meta/progress/memory/token/error/done` 保持；Raw 追加和召回整理均为 best-effort，失败转为空/跳过而不阻塞聊天。

## Reviewer NO-GO 修复轮次

- P1-1：`_is_schema_v3` 逐表核对列、FK、唯一约束和关键索引；version=3 半成品直接 fail-closed，避免启动后才在聊天路径报错。
- P1-2：Raw append 在同一事务校验 message owner/conversation；after cursor 同时限定 owner 与 conversation，跨 session 一律 `ValueError`。
- P1-3：running checkpoint 使用 300 秒 `updated_at` lease；stale 时原子接管、attempts+1，并保留已保存 cursor/state。
- P1-4：worker 通过 after cursor 分页读取全部 Raw event，不再受 1000 条默认上限影响；checkpoint state 记录首/末 event ID 与完整输入计数。
- P1-5：新增受控 daemon `MemoryEvolutionWorker`；聊天只 durable append，流结束后 enqueue，worker 失败吞吐并留 checkpoint；worker 启动扫描 raw/retry work，支持重启恢复。完成 checkpoint 遇到新 Raw 输入时会重新 claim，避免竞态丢事件。
- 最终复审修复：`_start_message` 的 worker 启动/扫描改为 warning + best-effort；任何初始化异常不影响 `StreamingResponse`，流结束仍再次尝试 enqueue。Raw event 已先持久化，可由后续 worker 启动扫描恢复。
- P2-1：候选创建与 evidence 插入合并到同一 repository transaction，失败整体回滚。
- P2-2：摘要 query 无匹配时返回空，不回退注入全部摘要。
- P2-3：prompt history 排除当前 user message，避免当前指令重复。

## 决策依据与契约不足处

- Task04 计划只冻结行为目标，未提供字段名、公开 URL 或 worker 调度协议；因此选择最小可验证的 repository/service API，不新增外部队列、基础设施或第二套 memory store。字段、状态和方法均可由后续 Task05/07 在同一 v3 上扩展。
- Task03 的手工 `confirm_memory` 保持原语义，Task04 自动路径独立使用 evidence-gated `promote_memory`，避免破坏已确认的管理端点兼容性。

## 风险/阻塞

- worker 是进程内 daemon、不是外部队列；服务重启会扫描 raw/retry work，stale checkpoint 由 lease 接管。它不承诺跨进程共享内存状态，SQLite checkpoint 是唯一恢复依据。
- worker 初始化失败仅影响异步整理，不影响聊天主链；失败初始化测试验证 SSE 仍返回 `done=completed`，正向 wiring 测试验证消息后 eventually 生成 checkpoint/summary/candidate。
- 摘要为本地确定性压缩，不调用模型；后续如接入模型必须继续只保存用户可见摘要，不能写入隐藏思维链。
- 未运行全量回归、前端测试、部署或跨端验收；属于主 Agent/Task08 范围。

## 主 Agent 后续动作

1. 分派 `backend-reviewer` 检查 v3 migration 原子性、并发 claim、候选污染和 prompt 预算边界。
2. 分派 `backend-tester` 按 Task04 验收矩阵复跑本报告命令，并补线程并发探针/重启 smoke。
3. 与后续 Task05 对齐摘要与研究上下文 token 预算，最终由 Task08 执行全量回归、验收和部署。

## 产物与运行信息

- 测试报告：`docs/sdd/plans/022/artifacts/task-04/test-report.md`
- 进度日志：`.codebuddy/agent-logs/spec-022/task-04/backend-dev/20260911-task04.md`
- 初轮开始：2026-09-11 05:32（Asia/Shanghai，约）
- 初轮结束：2026-09-11 05:43（Asia/Shanghai）
- 修复轮开始：2026-09-11 05:50（Asia/Shanghai，约）
- 修复轮结束：2026-09-11 05:57（Asia/Shanghai）
- 最终复审修复结束：2026-09-11 06:05（Asia/Shanghai）
- 累计总耗时：约 25 分钟
- 模型：临时 Luna high（按主 Agent 分派）
- token 统计：运行时不可用
- 工具统计：运行时未提供精确计数；使用文件读取、补丁编辑、py_compile、pytest、diff check
