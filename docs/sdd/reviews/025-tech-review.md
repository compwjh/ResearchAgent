# 评审结论：Spec 025 技术评审（需求 + 技术）

## 结论：通过（复审，2026-09-12）

上一轮 3 项 P0 与 6 项 P1 已在 Spec 025 与 Task02–06 中修订到位（见下方「复审记录」）。本轮复审判定：可确认、可进入实施。无新增 P0；仅记录 2 个非阻塞观察项，供 Task04 实施时关注。

## P0 清单
- **P0-1 装配消费 segments 的核心逻辑悬空**：grep 确认 backend 无任何 `conversation_segments` 消费者，`compose_chat_messages`(conversation_service.py:193) 与 `list_context_messages` 调用点(routes:270) 均未把分段摘要注入历史段、替换更早原文。Task02–05 都未显式归属"修改装配层消费 segments"，核心验收"下一条消息起使用摘要且占比下降"无 owner。
- **P0-2 分段窗口/区间接续算法未定义**：二次 compaction 时新段 `from_message_id` 如何接续上一段 `to_message_id`、如何避免重叠/重复摘要，spec 与 task 均未写清，可能违反"区间不重叠"并产生双计。
- **P0-3 单 job 去重违反并发领用规则**：去重为应用层"读-判-写"（端点判重 + 队列去重），违反 `regression-guard` #6（须单条条件 `UPDATE…WHERE…RETURNING` 抢锁）。须改用 DB claim 锁（类比 `try_session_lock` / `claim_evolution_checkpoint`），否则并发可建两个非终态 job 并双压缩。

## P1 清单
- **P1-1** dry-run"不含 RAG"与边界"dry-run 与真实装配一致性"措辞矛盾，须限定一致性仅覆盖历史/记忆/摘要部分。
- **P1-2** `_is_task025_schema` 须逐列 + `UNIQUE(conversation_id,seq)` 校验，等同 `_is_task07_schema`，否则部分迁移漏检。
- **P1-3** `compaction_status` 须覆盖 `queued/running` 以支撑前端"压缩中"中态（现仅说"终态映射/无 job 为 idle"）。
- **P1-4** worker 须在入队时冻结窗口(from/to)，否则并发追加消息被误纳入段。
- **P1-5** rule 三段式生成器只给输出格式、未给提取算法，需明确启发式或接受拼接+分段标题。
- **P1-6** 澄清 `conversation_segments`(历史段) 与 `conversation_summaries`(记忆段) 正交：装配只注入前者到历史、不读后者，避免"两套真相"误解与双计。

## 逐项核对结论表
| 重点 | 结论 | 依据 |
|---|---|---|
| 1 两新表 vs conversation_summaries | 不重叠(正交)，需 P1-6 澄清 | spec:101-104；repository.py:291；022:185-204 |
| 2 迁移范式/幂等/fail-closed | 范式正确(仿 Task07)，缺 P1-2 校验强度 | repository.py:176-193,494,520 |
| 3 异步语义/竞态 | 3 处缺陷 → P0-2/P0-3/P1-4 | spec:151-156,159-172；conversation_service.py:474,539-545 |
| 4 边界可测性 | 基本可测，P1-1 自相矛盾 | spec:157-173 |
| 5 与 Spec022/024 一致/越界 | 一致、未越界 | spec:185-204,46-54；routes:270-275 |
| 6 Task02-06 无环/覆盖 | 无环，缺 P0-1 归属；?v 同步点已定位 | plans/025/*.md；test_frontend_skill_tool_contract.py:81-83 |

## 依据索引
- Spec025：docs/sdd/specs/025-conversation-context-compaction.md
- 模板六自检：docs/sdd/00-sdd-spec-template.md:113
- 迁移范式：backend/app/memory/repository.py:38,127-193,291,494,520
- 装配/worker：backend/app/chat/application/conversation_service.py:193,238-267,474,521-545
- 路由/触发：backend/app/api/routes_conversations.py:270-275,489-504
- 前端契约：frontend/index.html:8,492；tests/test_frontend_skill_tool_contract.py:81-83
- 回归护栏：.codebuddy/skills/regression-guard/SKILL.md:509(#6)

---

## 复审记录（2026-09-12，architect 代行）

> 复审范围：核查上一轮 3 项 P0 + 6 项 P1 是否已真正修订到位；核对 spec 引用的代码事实是否真实；扫描上一轮未提出的新增问题。本轮**只改评审结论与本节**，未改动 Spec 025 与 Task 文件。

### 一、逐项核查结论（9/9 已解决）

| 项 | 结论 | 依据（spec 行号 / 文件:行号） |
|---|---|---|
| **P0-1** 装配消费 segments 悬空 | 已解决 | spec:162-169 新增「装配消费契约与分段生成算法」；:164 标题明确"Task03 归属，不可悬空"；:166 改写 `compose_chat_prompt` 历史段为"最近 `CHAT_RECENT_RAW_MESSAGES` 条原文 + 更早 `conversation_segments` 摘要链按 `seq` 倒序填充"；task-03.md:8,31 显式归属装配消费改造，并含"无段时输出与改动前逐字符一致"。 |
| **P0-2** 分段区间接续 | 已解决 | spec:77 区间接续算法：新段 `from` = 上一段 `to` 的下一条，无上一段取最早，`to` = 入队冻结窗口末条，区间不重叠；spec:196 边界"可断言区间并集无重叠、无遗漏"，可测。 |
| **P0-3** 单 job 去重 | 已解决 | spec:95 明确"DB 层原子：部分唯一索引 `UNIQUE(conversation_id) WHERE status IN ('queued','running')` 或等价单条条件 `UPDATE…WHERE…` 抢锁；禁止先 SELECT 判重再 INSERT"，并点名 `regression-guard` #6；task-03.md:29 落实为"按部分唯一索引原子领用 job、冲突由 DB 约束产生并返回 409"；类比 `try_session_lock`/`claim_evolution_checkpoint`（conversation_service.py:474,483）。 |
| **P1-1** dry-run 一致性口径 | 已解决 | spec:134（dry-run 只算历史段 + 记忆/摘要段，不含 RAG advisory）、:136（"一致性只覆盖历史段与记忆/摘要段"，明确排除 RAG advisory / SystemRule / 平台安全约束）、:195（边界再次锁定同口径）。原"矛盾"已消解。 |
| **P1-2** `_is_task025_schema` 逐列校验 | 已解决 | spec:110 逐列校验两表全部字段 + 显式校验 `UNIQUE(conversation_id,seq)` 与非终态 job 部分唯一索引，强度等同 `_is_task07_schema`；task-03.md:28 落实；范式 `_is_task07_schema` 真实存在于 repository.py:520（含 `expected_columns` 逐列列表）。 |
| **P1-3** `compaction_status` 覆盖 queued/running | 已解决 | spec:135 直接映射最新 job `status`（queued / running / done / failed），无 job 为 `idle`；:184 边界"保持 idle"、:186 手动压缩返回 `queued` 中态，前端"压缩中"中态有支撑。 |
| **P1-4** 入队冻结窗口 | 已解决 | spec:159 入队即冻结 `[from_message_id, to_message_id]` 落库，worker 只处理冻结窗口内消息；:197 边界"可断言段 `to_message_id` ≤ 入队时刻最后一条消息"；task-03.md:32 落实。 |
| **P1-5** rule 三段式生成算法 | 已解决 | spec:171-180 给出三段式（用户指令与约束 / 已定决策与结论 / 关键实体与引用指针）的启发式提取步骤与"稳定可复现"约束，非仅格式。 |
| **P1-6** 两表正交 | 已解决 | spec:78 明确 `conversation_segments`（历史段，本 spec 独占历史区）与 `conversation_summaries`（记忆演进，Spec022 注入记忆区）正交，"本 spec 只读前者注入历史，不读、不写后者"；:167 装配只从前者取；参考 022:185-196 优先级链。 |

### 二、代码事实核对（spec 引用真实，未悬空）

- `SCHEMA_VERSION = 6`（repository.py:38）✓；Task07 增量迁移范式 `_migrate_v6_to_task07`(:494) / `_is_task07_schema`(:520) 在 :176-187 原子应用、不 bump 版本 ✓。
- `conversation_summaries`(:291)、`list_context_messages` 默认 `limit=50`(:1238-1251) ✓。
- `compose_chat_prompt`(:238-267)、`compose_chat_messages`(:193) ✓；`MemoryEvolutionWorker` daemon(:514-573)、队列(:521)、去重(:539-545)、daemon 线程(:533)、`try_session_lock`/`claim_evolution_checkpoint`(:474,:483) ✓。
- `memory_analysis_jobs` 状态端点模式(:489-504)、`context_pressure` 事件(:270-275) ✓；022 优先级链(:185-196) ✓。
- **行号精度偏差（非阻塞）**：spec/task 写 `repository.py:1607` 的 `token_budget*4`，实际 `* 4` 在 **:1608**（`list_recall_context`），同属给定范围 1600-1615，语义无误。

### 三、新增问题扫描（上一轮未提）

未发现新增 **P0**。记录 2 个非阻塞观察项，供 Task04 实施与验收时关注：

- **观察 1（建议 Task04 处理）**：`used_tokens` 口径 = 历史段 + 记忆/摘要段（+项目指令），明确排除 RAG advisory / SystemRule / 平台安全约束（spec:134-136）。在**非项目**长会话中，仅 `history`(≤6000 字符≈3750 token) + `summary`(≤1500 字符≈937 token) 难以触及 `0.8×8000=6400` 的自动触发阈值，自动压缩或主要依赖**项目会话**（含 5000 字符项目指令）或更长的历史才触发；手动压缩为始终可用路径（spec:186）。Task04 验收"0.79 不触发 / 0.80 触发"（task-04.md:59）须用可触及阈值的会话构造，否则自动触发路径在验收中不被覆盖。建议开发主管在 Task04 明确 `used_tokens` 是否纳入项目指令，并在 smoke 中验证自动触发可达性。
- **观察 2（行号精度）**：见上文 `repository.py:1607→1608`，非阻塞。

### 四、最终结论

**通过（复审，2026-09-12）** —— 上一轮 3 项 P0 与 6 项 P1 全部已解决，修订落到 spec 文本与 Task 归属两层且代码事实基础真实；无新增 P0。可确认 Spec 025 并进入实施。
