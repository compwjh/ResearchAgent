> 关联：[spec-025](../../specs/025-conversation-context-compaction.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`

# Task 03 — 分段摘要、装配消费改造与异步压缩 worker

## 1. 状态与一句话目标

`已完成`。交付 `conversation_segments` 与 `conversation_compaction_jobs` 两张表及其迁移，**改造装配层消费分段摘要**，并提供一个不阻塞对话的后台压缩 worker 与规则化分段摘要生成器。

## 2. 背景与前置条件

- Spec025「数据模型」与「异步 worker 契约」两节为唯一依据。
- `messages` 表 append-only；`conversation_summaries`（`repository.py:291`）属 Spec022 记忆演进，**本 Task 不读写**。
- 迁移机制：`backend/app/memory/repository.py:38` `SCHEMA_VERSION = 6`，逐级事务迁移 `:127-193`，新增表范式 `:494` `_migrate_v6_to_task07` 与 `:520` `_is_task07_schema`，在 `:176-187` 原子应用且不 bump 版本号。
- 异步模式：复用 `conversation_service.py:521-533` 的 `threading + queue.Queue` daemon worker（单例 `:798-810`，队列去重 `:539-545`）。**禁止 BackgroundTasks / asyncio**。
- 规则化摘要参考既有的非 LLM 事件拼接 `conversation_service.py:471-511`。

## 3. 数据、配置与接口

- 建表 DDL 与字段约束见 Spec025「数据模型」，本 Task 不另立字段。
- `conversation_segments`：append-only，纠正走新增 `seq`，`UNIQUE(conversation_id, seq)`。
- `conversation_compaction_jobs`：`status ∈ {queued, running, done, failed}`，`trigger ∈ {auto, manual}`；同会话只允许一个非终态 job。
- 摘要正文三段式：用户指令与约束 / 已定决策与结论 / 关键实体与引用指针（消息 id）。
- `generator='rule'`，本 Task 不产出 `llm` 段。

## 4. 实施步骤与文件边界

1. `repository.py` 新增 `_migrate_v6_to_task025` + `_is_task025_schema`，在事务链中原子应用；`_is_task025_schema` **逐列校验**并校验 `UNIQUE(conversation_id, seq)` 与非终态 job 的部分唯一索引；重复启动幂等。
2. 仓储层新增两张表的读写方法（写入段、按会话取段、**按部分唯一索引原子领用 job**、查询/更新 job）。**禁止"先 SELECT 判重再 INSERT"**，冲突由数据库约束产生并返回 409。
3. 新增规则化分段摘要生成函数：按 Spec025「装配消费契约与分段生成算法」的三段式启发式实现，输出稳定可复现；新段 `from_message_id` 接续上一段 `to_message_id` 的下一条消息，区间不重叠。
4. **改造装配层消费 segments**：`compose_chat_prompt`（`conversation_service.py:238-267`）历史段改为「最近 `CHAT_RECENT_RAW_MESSAGES` 条原文 + 更早的 `conversation_segments` 摘要链按 `seq` 倒序填充，装不下时从最旧摘要段开始丢弃」；无段时输出与改动前逐字符一致。
5. 新增 daemon worker：消费队列 → 置 `running` → 生成段 → 写表 → 置 `done`；异常收敛为 `failed` + `error`。**入队即冻结 `[from_message_id, to_message_id]` 窗口**，worker 只处理窗口内消息。
6. 历史读取条数与装配使用条数对齐（取 20 条、保留最近 10 条原文，消除 `repository.py:1238` 的 30 条白读）。

可观察结果：迁移重复执行幂等；入队后由 worker 线程写表；主线程调用不被阻塞；**装配在有段时使用摘要、无段时行为不变**。

## 5. 子代理分派

- `backend-dev`（hy3，64k）：一次只产出仓储层或 worker 层之一，避免单次输出过大超时；回传后架构师读回校验锁范围与异常收敛。
- `backend-tester`（hy3，32k）：只跑本 Task 相关 pytest。

## 6. 边界与明确不做

- 不做 LLM 摘要，不引 tokenizer。
- 不删改 `messages`，不做物理归档。
- 不做跨会话摘要召回，不读写 `conversation_summaries`。
- 不改 `frontend/**`，不新增公开 HTTP 端点（端点属 Task04）。

## 7. 验收、风险与回滚

- 验收：迁移幂等（连续两次启动 schema 校验通过，含索引校验）；job 去重（同会话连续入队只产生一个 job，并发两次请求不翻倍）；worker 异常被捕获并置 `failed`；压缩前后 `messages` 的 `COUNT(*)` 与内容哈希不变；跨项目隔离（A 会话取不到 B 会话/其它项目的段）；**装配消费（有段时用摘要、无段时逐字符等价）**；段区间不重叠且二次压缩接续正确；冻结窗口外的消息不被纳入本段。
- 风险：daemon 线程异常退出导致队列堆积——必须有兜底 `try/except` 与状态回写。
- 回滚：迁移只建新表，回滚即删除新表或 revert 提交，不影响既有数据。

## 8. 产出物、执行结果与变更日志

- `repository.py`（+316/−1）：两表 DDL + 两个索引（含非终态 job 部分唯一索引）、`_migrate_v6_to_task025`/`_is_task025_schema`（不 bump SCHEMA_VERSION）、`ConversationSegment`/`CompactionJob` dataclass、7 个仓储方法。
- `context_compaction.py`（新增）：`build_rule_summary` 三段式规则摘要、`CompactionWorker`（threading+queue daemon，入队冻结窗口）、`get_compaction_worker` 单例。
- `conversation_service.py`：`compose_chat_prompt` 新增 `segments` 参数与 `_build_history_section`；`compose_chat_messages` 有段时把最近原文收敛到 `CHAT_RECENT_RAW_MESSAGES` 条（**已修正子代理越界：history 仍以 role 消息注入，不搬进 advisory**）。
- `routes_conversations.py`：发消息链路接入 `list_conversation_segments`。
- 测试：`tests/test_spec025_compaction_store.py` → 7 passed；`tests/test_spec025_context_compaction.py` → 14 passed（退出码 0）。
