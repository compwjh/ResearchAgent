# Spec 038 — 记忆层改造：对齐 Hermes 三层记忆模型

## 状态

**当前状态：`已实现（P1/P2/P3 阶段均通过回归）· 架构签字已落盘`**

> 本 spec 是在 **实现已落地之后再补写并签字** 的（P1 文件记忆 → P2 会话检索 → P3 上下文窗口管理）。
> 三个阶段的代码均已合入 `feature/spec-038-memory-layer` 分支并通过回归。本文件的作用是
> **把实现事实固化为可审文档**，并对四个关键边界做架构裁决。
> 与 035 的流程偏离（先实现后评审）一致，本 spec 的需求/技术评审以本文档「评审记录」小节登记。

## 一句话目标

把记忆体系重构为对齐 **Hermes 三层记忆模型** 的结构 —— **L1 内建文件记忆（`USER.md` / `MEMORY.md` / `projects/<id>.md`，Markdown 即真相源，始终启用、不依赖外部服务）**、**L2 会话持久化 + FTS5 全文检索 + `session_search` 工具（Agent 可主动翻旧账）**、**L3 上下文窗口管理（压缩前 `flush_memories` + 工具输出预裁剪 + LLM 重构摘要）** —— 并借此删除旧记忆体系（`memories` / `memory_evidence` / `system_rules` 三表与 v1→v7 迁移链），使记忆的写入、召回、修正、遗忘全部落在**一套**可被用户直接编辑的文件真相源上。

## 背景与问题

### 被本 spec 改造的两份前作

| 前作 | 定位 | 本 spec 对其处置 |
|---|---|---|
| **spec-022** `022-project-conversation-memory.md` | 建立「项目/会话/消息/**DB 记忆**」四层模型，`memories` + `memory_evidence` + `system_rules` 三表，v1→v7 迁移链，异步记忆分析 | **重构记忆载体**：记忆真相源由 DB 迁到 MD；`system_rules` 功能并入 `USER.md`；三表停用 |
| **spec-025** `025-conversation-context-compaction.md` | 规则式会话压缩（`conversation_segments` / 规则摘要） | **增强压缩链**：新增 LLM 重构摘要（保留规则摘要作降级）、工具输出预裁剪、压缩前 `flush_memories` |

### 改造前的结构性问题（已核实）

| 现状 | 位置 | 影响 |
|---|---|---|
| 记忆真相源在 SQLite（`memories` / `memory_evidence`） | `backend/app/memory/repository.py` | 用户**看不到也改不了**自己的长期记忆；只能经 API 治理 |
| `system_rules` 与普通记忆割裂，全局画像只有一条 | 同上（spec-022 Task10） | 用户画像与系统规则两套概念，注入链分叉 |
| 全库**没有会话历史检索能力** | 唯一「检索」是 Python 子串过滤且发生在 SQL `LIMIT` 之后 | Agent 无法主动翻旧账；候选集在过滤前已被截断 |
| v1→v7 迁移链累计约 **800 行** | `backend/app/memory/migration.py` | 维护成本高，且历史补丁已无数据意义 |
| 摘要为**规则式拼接**，压缩前无记忆落盘机会 | `context_compaction.build_rule_summary` | 窗口超限时重要信息可能被压缩掉、写不进记忆 |
| 注入预算偏小（total 8000 / rag 6000 / summary 1500） | `backend/app/platform/config.py` | L1 全量快照 + RAG 证据难以同时容纳 |

## Hermes 三层对照与差距

| 层 | Hermes 模型 | 本项目改造前 | 本项目改造后（本 spec） | 差距闭合点 |
|---|---|---|---|---|
| **L1 内建文件记忆** | `USER.md` + `MEMORY.md` + 项目记忆文件，会话启动快照注入，始终可用 | DB 三表，需 API 治理，非文件 | `MarkdownMemoryStore` 直读写 MD；`USER.md`/`MEMORY.md`/`projects/<id>.md`；快照注入系统提示词 | Q1/Q2/Q6/Q7 |
| **L2 会话持久化 + 过程记忆** | 完整对话持久化 + 全文检索 | SQLite 有 `messages`，无 FTS，无检索工具 | FTS5 虚表 `session_search_index`（jieba 分词）+ `session_search` 工具 | Q3 |
| **L3 上下文窗口管理** | 超限时压缩 + 压缩前把重要信息落 L1 | 规则式压缩，无 flush、无工具裁剪 | `CompactionWorker` + 压缩前 `flush_memories` + `collapse_tool_outputs` + LLM 重构摘要 | Q4/Q10/Q11 |

## 设计决策记录（Q1–Q13 与开放项）

> 以下决策均已落盘并经用户裁决，是**实现硬约束**。

| # | 决策点 | 结论 |
|---|---|---|
| **Q1** | 记忆真相源 | **MD 为真相源**（`USER.md`/`MEMORY.md`/`projects/<id>.md`）；真实文件在 `data/memory/`，经 `.gitignore` 忽略，**仓库只提交 `USER.example.md` / `MEMORY.example.md`** |
| **Q2** | 作用域模型 | **全局 + 项目双作用域**；抽取时区分 scope；**不默认塞进项目记忆**（无依据不做项目归属） |
| **Q3** | 会话检索 | **FTS5 虚表 + `session_search` 工具**，让 Agent 主动检索历史对话与记忆笔记 |
| **Q4** | L3 完整度 | **完整 L3**：LLM 重构摘要 + 工具输出裁剪 + 压缩前 `flush_memories`，三者齐备 |
| **Q5** | 数据迁移前提 | **无生产数据，可删库重建**；因此采用新基线，而非继续维护迁移链 |
| **Q6** | 快照注入 | **全量快照注入**，但**上限可配**（`CHAT_SUMMARY_BUDGET_CHARS`）；`USER.md` 优先全量、不参与截断 |
| **Q7** | 文件布局 | **目录化布局**：`data/memory/{USER.md,MEMORY.md,PENDING.md,projects/<id>.md}` |
| **Q8** | worker 写入路径 | **worker 直写 MD**，DB **只留审计流水**（`memory_analysis_jobs`/`items`、`raw_events`） |
| **Q9** | scope 不明确 | **走 pending**（写 `PENDING.md` 待确认），不静默落盘 |
| **Q10** | 摘要降级 | LLM 摘要**任何异常回落规则摘要**（`build_llm_summary` → `build_rule_summary`） |
| **Q11** | 工具输出 | **结构化塌缩**：旧步骤压成「工具名/标签 [状态]：摘要首行」单行，最近 N 步留原文 |
| **Q12** | 迁移链 | **删除 v1→v7 迁移链**，保留**备份**能力（详见「数据迁移与隐私边界」） |
| **Q13** | 注入预算默认值 | `CHAT_TOTAL_TOKEN_BUDGET` 8000→**20000**；`CHAT_RAG_BUDGET_CHARS` 6000→**12000**；`CHAT_SUMMARY_BUDGET_CHARS` 1500→**3000**；`CHAT_COMPACT_TRIGGER_RATIO` 保持 **0.8**；全部 env 可配 |

### 开放项裁决（本次架构师结论）

| 开放项 | 裁决 |
|---|---|
| FTS5 是否同时索引 messages 与 MD | **同时索引**。只索引 messages 是错的：Agent 需要一次检索同时翻旧对话与自己的笔记。会话/owner 过滤对 MD 行放行（`conversation_id IS NULL` / `owner_id IS NULL`） |
| 高置信度直写 vs 低置信度提议 | **置信度分级**：`intent=="explicit"` 且 `confidence>=0.9` 且 scope 明确 → Agent 直写 MD；否则 → `pending_confirmation` |
| `conversation_summaries` 与 `capability_methods` 的去留 | **保留 `conversation_summaries`**（P3 起改由 LLM 摘要写入，表结构不变）；**`capability_methods` 并入 MD**（作为记忆条目，不再单列枚举类别） |
| 新增 seed 脚本 | **采纳**：提供 `USER.example.md` / `MEMORY.example.md` 作为可复制种子 |
| 分支基线 | **先从 `main` 合入 spec-035 再开本分支**（避免 035 与 038 在 platform 层并发改动冲突） |

## 三层设计与实现要点

### L1 内建文件记忆（基石）

**模块：`backend/app/memory/markdown_store.py`（新增）**

| 文件 | 语义 | 注入方式 |
|---|---|---|
| `USER.md` | 用户画像（最重要、通常很短） | 快照**优先全量注入**，不参与预算截断 |
| `MEMORY.md` | 全局长期笔记 | 快照在预算内注入，全局优先于项目 |
| `projects/<project_id>.md` | 项目级记忆 | 快照在预算内注入（**仅当会话绑定项目**） |
| `PENDING.md` | 待确认项（scope 不明确时暂存） | **不注入**、**不参与检索** |

实现要点（均为硬约束）：

1. **MD 即真相源**：本模块只负责读写与快照装配，**不引入第二套存储**；待确认项同样落 `PENDING.md`（而非复用审计表），保持「MD 即真相源」一致，并允许用户直接编辑该文件。
2. **并发安全**：进程内按**解析后绝对路径**取 `threading.RLock` 做文件级互斥；落盘走「临时文件 + `fsync` + `os.replace()`」**原子替换**，读者永不见半截文件。
3. **条目边界**：以行首 `- `（或 `* ` / `## `）为条目界；`append_memory` 追加 `- <content>` 单行；`load_snapshot` 超预算时**保留较新的条目**（文件末尾视为最新），从最旧（头部）丢弃。
4. **路径安全（防路径遍历）**：`project_id` 白名单 `[A-Za-z0-9_-]+`；外加 `realpath` 必须仍位于 `projects` 目录内，**双重防线**（显式拒绝 `.` 与 `/`，故 `..`、`a/../b` 全被挡）。
5. **容错（fail-open）**：文件缺失按空处理并自动初始化父目录；读取异常一律静默降级为空串，本模块位于会话装配关键路径，**绝不向上抛异常**。
6. **注入接缝**：`read_user_memory_or_empty()` 被 4 处路由（`routes_chat`/`routes_kb`/`routes_article`/`routes_conversations`）调用，替代旧的 `get_system_rule(OWNER_ID)`。

### L2 会话持久化 + 过程记忆

**模块：`backend/app/memory/session_search.py`（新增）**

1. **FTS5 虚表** `session_search_index`（在 `migration` 新基线中建出）：`index_text`（分词后索引列）+ `content`（原始文本，`UNINDEXED`）+ `source_kind`/`ref_id`/`conversation_id`/`owner_id`/`role`/`created_at`（均 `UNINDEXED`）。统一索引 **历史消息** 与 **MD 记忆笔记** 两类来源。
2. **中文分词方案**：索引列存 `embed.tokenize`（jieba）分词后空格连接的文本，查询侧用同一函数切词再以 `AND` 连接 —— **不用 `tokenize='trigram'`**。理由：trigram 对 2 字中文词（如「检索」「偏好」）无法建立有效 token，中文查询会静默搜不到；jieba 与知识库稀疏检索**复用同一套中文处理**，行为一致可复现（项目已有唯一实现，禁止第二套分词）。
3. **同步方式：显式写入函数**（`index_message` / `index_memory_document` / `reindex_all` / `reindex_memories`），**不用 SQL 触发器**。理由：① MD 笔记不在 SQLite 里，触发器无法覆盖；② 索引需 jieba 分词，触发器做不到（不引入自定义 UDF）；③ 显式函数可被单测直接驱动、可控可回放。
4. **写入钩子**：`repository.create_message` / `update_message` —— **仅内容变更或进入终态**才索引，避免流式写放大；`markdown_store` 各写入路径（`write_user`/`append_memory`）写完后同步索引。钩子均**方法内延迟导入** `session_search`（顶层互导会成环）+ `safe_call` fail-open，受 `MEMORY_FTS_ENABLED` 控制。
5. **查询转义**：每个 token 先剥离非字母数字与中文的字符，再用双引号包成 **FTS5 字符串字面量**，token 间以 `AND` 连接。使操作符关键字（`near`/`and`）降级为普通词、连字符不再被解析成列名；清洗后 token 全空 → 直接返回空结果，绝不进 SQL。
6. **检索入口** `search_sessions(query, limit, conversation_id, owner_id)`：返回 `{ok, count, output, hits[, error]}`，`ok` 恒为 `True`（检索无结果是正常情况），任何 SQL 异常记日志后降级为 `[]`，**绝不向上抛**（位于 Agent 工具调用链上）。

### L3 上下文窗口管理

**模块：`backend/app/chat/application/context_compaction.py`（增强）**

1. **LLM 重构摘要**：新增 `build_llm_summary`（用 `MEMORY_ANALYSIS_MODEL`），`build_rule_summary` 保留为**降级路径**。`build_compaction_summary` 按 `COMPACTION_SUMMARY_MODE`：`rule` 直接规则；`llm` 先试 LLM，**任何异常（Ollama 不可达/超时/输出为空）回落规则摘要**（Q10）。
2. **压缩前 `flush_memories`**：挂在 `CompactionWorker._process` 之前，给 Agent 一次把重要信息写入 L1 的机会。复用 `MemoryAnalysisWorker` 的同一条分类链路（`classify_memory_intent` + `decide_memory_write`），**不新建第二套抽取实现**。**三层 fail-open**：① `FLUSH_MEMORIES_ENABLED` 开关；② `llm_available()` 可达性探测（不可达直接跳过，不做数十秒重试）；③ `COMPACTION_FLUSH_TIMEOUT` 限时。且经 `_dispatch_flush` 甩到**独立 daemon 线程**执行，压缩主流程只做 dispatch，**不阻塞**。
3. **工具输出预裁剪**：`collapse_tool_outputs(steps, keep_recent)`，旧步骤塌缩为「工具名/标签 [状态]：摘要首行」单行，最近 `CHAT_TOOL_OUTPUT_KEEP_RECENT`（默认 3）步保留原文。塌缩逻辑**单点**在此，`routes_conversations` 仅调用不重复实现。
4. **记忆抽取策略（置信度分级）**：`decide_memory_write()` —— `intent=="explicit"` 且 `confidence>=0.9`（`MEMORY_AUTO_WRITE_MIN_CONFIDENCE`）且 scope 明确 → **Agent 直写 MD**；否则 → `pending_confirmation`（写 `PENDING.md`）。**不默认塞进项目记忆**：有显式全局意图 → global；有项目上下文 → 该项目；否则退回 global，不做无依据的项目归属。唯一写入出口 `write_memory_candidate`，被 `flush_memories` 与两个 worker 共用；MD 写入抛异常时退化为待确认（fail-open）。

## 数据迁移与隐私边界

### 新基线（替代 v1→v7 迁移链）

**模块：`backend/app/memory/migration.py`（重写）**

- **`SCHEMA_VERSION = 8`**：刻意大于历史链的 7，用以区分「本次基线建库」（写入 8）与「旧 v1→v7 库残留」（缺少该值 → 拒绝）。
- **删除 v1→v7 约 800 行迁移链**，改为 `create_baseline_schema(connection, owner_id)` 直接建表。理由：Q5「无生产数据可删库重建」。
- **建表纪律**：所有语句 `CREATE ... IF NOT EXISTS`（幂等）；`initialize()` 用 **`BEGIN IMMEDIATE` 单事务**包住全部 DDL，失败整体回滚；版本号写入与 DDL 同事务。
- **fail-closed**：`schema_version` 高于基线 → 拒绝启动；低于基线且非本次新建（老库残留）→ 同样拒绝，避免在半旧 schema 上写入。

**表取舍**：

| 处置 | 表 |
|---|---|
| **保留**（照搬原 schema，不顺手改动无关表） | `schema_version`、`projects`、`conversations`、`messages`、`processing_steps`、`raw_events`、`conversation_summaries`、`evolution_checkpoints`、`memory_analysis_jobs`、`memory_analysis_items`、`skill_improvement_proposals`、`user_chat_preferences`、`conversation_segments`、`conversation_compaction_jobs`、`conversation_active_skill` |
| **停用**（语义已迁 MD） | `memories`（→ `MEMORY.md`/`projects/<id>.md`）、`memory_evidence`（→ 证据随条目落 MD）、`system_rules`（→ `USER.md`） |
| **新增** | `session_search_index`（FTS5 虚表） |

> `memory_analysis_items.memory_id` 与 `skill_improvement_proposals.source_memory_id` 原为 `REFERENCES memories(...)`，表停用后该外键无法保留，新基线中保留为**普通 TEXT 列**（语义不变：指向被采纳的记忆），不破坏历史契约。

- **默认偏好行播种**：`create_baseline_schema` 需 `INSERT OR IGNORE` 一条默认 `xhigh` 偏好（原 v6→v7 迁移行为），否则 `update_conversation_reasoning` 会走 INSERT 分支、把「effort 未变」误判成偏好变更。
- **数据保全（删表前）**：`backend/app/memory/preserve.py` 把旧 `system_rules` 内容迁入 `USER.md`（**唯一需保留的用户数据**；`memories` 内容已由 MD 层接管）。**幂等**：表不存在/无记录 → 空操作；`USER.md` 已有内容 → **不覆盖**，视为用户已在编辑 MD，仅记跳过；异常不得让 `initialize()` 崩溃。

### 隐私边界

| 项 | 处置 |
|---|---|
| 真实 MD 位置 | `data/memory/`（不提交 git） |
| `.gitignore` | 已有 `data/memory/` / `data/memory/*.md` / `data/memory/projects/` 规则 |
| 仓库只提交 | `USER.example.md` / `MEMORY.example.md`（可复制种子） |
| 记忆内容 | 只作上下文数据，**不得直接触发**下载/删除/执行命令或绕过工具安全边界 |
| 敏感数据 | 不保存或展示隐藏思维链、完整 Prompt、Cookie、Token、完整向量或敏感工具参数 |

## 配置变更清单

| 配置项 | 旧默认 | 新默认 | 环境变量可配 | 说明 |
|---|---|---|---|---|
| `CHAT_TOTAL_TOKEN_BUDGET` | 8000 | **20000** | 是 | 单次模型调用输入 token 硬上限 |
| `CHAT_RAG_BUDGET_CHARS` | 6000 | **12000** | 是 | 知识库证据注入字符预算 |
| `CHAT_SUMMARY_BUDGET_CHARS` | 1500 | **3000** | 是 | 记忆/摘要段注入字符预算（L1 快照亦受此项约束） |
| `CHAT_COMPACT_TRIGGER_RATIO` | 0.8 | **0.8（不变）** | 是 | 装配后 used/budget ≥ 该比例即触发后台异步压缩 |
| `CHAT_TOOL_OUTPUT_KEEP_RECENT` | —（新增） | **3** | 是 | 保留原文的最近工具步骤数 |
| `MEMORY_DIR` | —（新增） | `data/memory` | 是 | 记忆文件根目录 |
| `MEMORY_FTS_ENABLED` | —（新增） | **True** | 是 | 写入时是否同步维护 FTS5 索引 |
| `MEMORY_ANALYSIS_MODEL` | `qwen3.5:9b` | **不变** | 是 | 记忆分类/摘要模型；业务代码不硬编码 |
| `COMPACTION_SUMMARY_MODE` | —（新增） | `llm` | 是 | `llm`（回落规则）/ `rule` |
| `COMPACTION_SUMMARY_TIMEOUT` | —（新增） | 30.0s | 是 | LLM 摘要单次超时 |
| `COMPACTION_FLUSH_TIMEOUT` | —（新增） | 20.0s | 是 | `flush_memories` 整体超时 |
| `FLUSH_MEMORIES_ENABLED` | —（新增） | 见 config | 是 | 压缩前 flush 总开关 |

## 测试与验收

### 边界（每条之后会变成一条测试）

1. `USER.md` 缺失 → 注入为空、接口不报错；写入后下次会话可见。
2. `load_snapshot` 超预算 → 保留较新条目、从最旧丢弃；`USER.md` 不参与截断。
3. `project_id` 非法（`../x`、`a/b`、`proj.a`）→ 抛 `ValueError`，**不产生越界文件**。
4. 并发 `append_memory`（多线程）→ 条目**不丢失**、文件**不半截**。
5. `PENDING.md` 中的待确认项 → **不注入快照**、**不参与检索**。
6. `session_search` 中文查询（2 字词如「检索」）→ **能命中**（jieba 方案）。
7. `session_search` 查询含 `"*()-:^` 与 `near`/`and` → **不抛 SQL 异常**，降级为可读结果。
8. `session_search` 空查询/纯符号 → 返回空结果提示，不报错。
9. `search_sessions` 任一 SQL 异常 → `ok=True`、`output` 可读、`hits=[]`，**不向上抛**。
10. `decide_memory_write`：`explicit`+`≥0.9`+scope 明确 → `auto_saved`；其余 → `pending_confirmation`。
11. 无项目上下文且无显式全局意图 → 退回 `global`，**不写进任何项目文件**。
12. `MD 写入抛异常` → 退化为待确认，不冒泡、不假写正式记忆。
13. `flush_memories` 超时/分类器不可达 → **不阻断压缩**；`FLUSH_MEMORIES_ENABLED=false` → 直接跳过。
14. `COMPACTION_SUMMARY_MODE=llm` 且 LLM 不可达 → **回落规则摘要**，压缩仍完成。
15. `collapse_tool_outputs` → 旧步骤单行塌缩、最近 3 步保留原文。
16. `MEMORY_FTS_ENABLED=false` → 写记忆**不报错**、不索引。
17. `reindex_all` → 消息与 MD 两侧行数稳定可复现；外部手改 `MEMORY.md` 后重建可被检索到。
18. 老库残留（`schema_version` < 8 且非本次新建）→ **fail-closed 拒绝启动**；旧 `system_rules` 内容被迁入 `USER.md`。
19. `initialize()` 重复执行 → 幂等无副作用；DDL 失败整体回滚。
20. `.gitignore` → `data/memory/` 下真实文件不入库，仅 example 可提交。

### 验收方式

- **L1**：手工编辑 `USER.md`/`MEMORY.md`，新会话注入生效；越界 `project_id` 被拒；并发写不丢条。
- **L2**：`session_search` 用中文 2 字词检索历史对话与记忆笔记均命中；特殊字符查询不崩。
- **L3**：制造超限窗口 → 触发压缩，压缩前 `flush_memories` 落盘；LLM 关掉后规则摘要兜底；工具输出被塌缩。
- **迁移**：在旧库上启动 → fail-closed；`system_rules` 内容出现在 `USER.md`。
- **隐私**：`git status` 确认 `data/memory/` 未入库。

## 风险与后续项

### 已知遗留风险（基线既有，本次未改）

| 项 | 描述 | 处置建议 |
|---|---|---|
| `MemoryAnalysisWorker` 阻塞 | Ollama 不可达时会阻塞约 **75 秒**（基线既有，本次未改，`flush_memories` 已有可达性快筛与限时，但每消息分析链路仍存在） | 后续独立 spec 补齐可达性快筛/超时收敛 |
| 基线既有 ruff 问题 | `repository.py` / `conversation_service.py` 存在基线既有 ruff 告警未清理 | 后续单独清理，避免与功能改动混杂 |
| 单 owner 无多租户 | `OWNER_ID=local-user` 固定单用户；MD 无 owner 概念（索引行 `owner_id IS NULL`） | 多租户为后续独立 spec；届时需为 MD 引入 owner 维度 |

### 本 spec 引入的需关注点

- **并发一致性（见架构签字 A2）**：文件锁为**进程内**，多进程部署下不互斥。
- **FTS5 与 messages/MD 的耦合（见架构签字 A3）**：单一虚表承载两类来源，任一来源 schema 变更牵动检索逻辑。
- **删除迁移链的风险敞口（见架构签字 A4）**：仅 Q5 前提（无生产数据）成立时才安全。

## 架构签字

> 本节为架构师对本 spec 四个关键边界的**明确裁决**。下游角色以本节结论为准。

### A1 · MD 真相源 vs DB 真相源的边界 —— **通过**

**裁决**：**MD 是记忆的唯一真相源；DB 只保留审计流水**（`memory_analysis_jobs`/`memory_analysis_items` 记抽取过程，`raw_events` 记事件）。理由：

1. 记忆的**用户价值是「可见、可改、可带走」**，文件天然满足；DB 行只有 API 可及。
2. 审计与真相**职责分离清晰**：审计表记录「曾抽取出什么、决定了什么」，MD 记录「当前生效的记忆」，两者不混。
3. 「worker 直写 MD，DB 只留审计」（Q8）避免了双写不一致 —— DB 永不是记忆的权威副本，故**不存在**「DB 与 MD 谁的更新为准」的同步难题。
4. 唯一的历史遗留是 `memory_analysis_items.memory_id` / `skill_improvement_proposals.source_memory_id` 作为**弱引用（普通 TEXT）**保留；这在语义上是「指向曾采纳的记忆」，不构成第二真相源，**可接受**。

**结论：通过。前提是下游不得再引入任何「以 DB 行为准」的记忆读取路径。**

### A2 · 多 worker 并发写 MD 的一致性 —— **有条件通过（单进程成立，多进程需补文件系统锁）**

**裁决**：当前实现的「**进程内 `threading.RLock` 文件级互斥 + 临时文件 `os.replace()` 原子写**」在**单进程多线程**（本项目当前部署形态：`MemoryAnalysisWorker` / `MemoryEvolutionWorker` / `CompactionWorker` 均为**同进程 daemon 线程**）下**足以**保证：
- **不丢条目**：`_append_entry` 在锁内「读-追加-原子写」，交叉覆盖被串行化；
- **不读半截**：`os.replace` 原子替换，读者永远看到完整旧文件或完整新文件。

**风险敞口（须记录）**：`threading.RLock` **不跨进程**。若未来：
- 以多进程（多 worker / 多实例）部署同一 `MEMORY_DIR`，或
- 用户手动编辑 MD 与进程写入并发（无锁保护的外部写）

则**仍存在丢更新风险**（read-modify-write 交错）。

**约束与后续项**：
1. 本 spec 范围内**部署形态为单进程**，A2 结论成立；**若改变部署形态，必须先补跨进程文件锁（`fcntl.flock` / 独立 lock 文件）**，此为**发布阻断项**。
2. 用户手工编辑属「文档级」操作，建议在文档中提示「编辑前避免正在生成回答」；这属产品提示，非代码缺陷。
3. `os.replace` 依赖**同文件系统** —— 已通过「临时文件与目标同目录」保证；跨文件系统（如 tmpfs 挂载差异）须复核。

**结论：单进程部署下通过；多进程部署前必须补跨进程锁，否则不得上线。**

### A3 · FTS5 同时索引 messages 与 MD 的耦合 —— **通过（可接受）**

**裁决**：**同时索引两类来源可接受**，理由与约束如下：

1. **产品语义正确**：Agent 一次检索应能同时拿到「旧对话」与「自己的笔记」，只索引 messages 是功能缺失。
2. **耦合面被收敛在显式写入函数**：`source_kind` / `ref_id` 是明确的判别列，检索侧用 `conversation_id IS NULL` / `owner_id IS NULL` 放行 MD 行 —— 耦合是**数据级**而非**逻辑级**，不产生分支蔓延。
3. **无需 SQL 触发器**：因 MD 在文件系统、分词在 Python，触发器本就不可能覆盖；显式函数反而让两类来源走**同一条** upsert 路径（`DELETE + INSERT`），一致性更好。
4. **失败面隔离**：MD 索引失败与消息索引失败均 fail-open（`safe_call`），互不影响；外部手改 MD 由 `reindex_all` 兜底重建。

**须记录的约束**：
- 单一虚表意味着**任一来源的 schema 演进都牵动检索 SQL**；后续扩展必须**同时**更新 `_upsert` 的列集合与 `search` 的过滤条件，并在 `reindex_all` 中保持两类来源计数稳定。
- `content` 保留原文、`index_text` 存分词，二者必须**同事务**写入，禁止只更其一（否则回显与命中不一致）。

**结论：通过。**

### A4 · 删除 v1→v7 迁移链的风险敞口 —— **通过（附前置条件）**

**裁决**：**通过**，但**仅以 Q5「无生产数据、可删库重建」为唯一成立前提**：

1. **敞口是明确的**：删除迁移链后，任何**真实存在的旧库**（`schema_version < 8` 且非本次新建）将被 `fail-closed` **拒绝启动** —— 这是**设计意图**，用「拒绝」替代「静默在半旧 schema 上写入」。
2. **数据保全是补丁而非兜底**：`preserve.py` 只搬 `system_rules`（唯一需保留的用户数据）；`memories` 的内容由 P1 前半段 MD 层接管。**若未来出现 v1→v7 真实库且含未迁移的 `memories` 数据，本 spec 不提供自动迁移** —— 必须走人工导出。
3. **fail-closed 优于 fail-open**：拒绝启动（`Q12`）避免在结构不匹配的库上写入造成更难恢复的数据损坏。

**前置条件（发布阻断项）**：
- 确认目标环境**不存在** `schema_version < 8` 的真实库；**若存在，须先备份 DB 再重建**（Q12 保留备份能力）。
- 备份与重建步骤须写入运维说明（本 spec 记录要求，具体脚本由后续 task 交付）。

**结论：通过，前提是无存量旧库；有旧库必须先备份再重建。**

## 明确不做（划出范围，防 AI 自由发挥）

1. **不做多用户/多租户**：`OWNER_ID=local-user` 固定单用户；MD 无 owner 维度（多租户为后续独立 spec）。
2. **不引入第二套存储/分词/抽取/塌缩实现**：MD 读写单点 = `MarkdownMemoryStore`；分词单点 = `embed.tokenize`；抽取单点 = `extract_memory_candidates`；写入单点 = `write_memory_candidate`；塌缩单点 = `collapse_tool_outputs`。
3. **不补 `MemoryAnalysisWorker` 的 75 秒阻塞**（基线既有，独立 spec 处置）。
4. **不清理基线既有 ruff 告警**（独立处置，避免与功能改动混杂）。
5. **不做跨进程文件锁**（当前单进程部署；改变部署形态前必须补，作为发布阻断项）。
6. **不做向量语义检索**：L2 只用 FTS5 全文检索，不引入 embedding 召回（复用既有 KB 检索链路，记忆不写 `papers` collection）。
7. **不做 MD 与 DB 的双向同步**：DB 只留审计，永不是记忆权威副本。
8. **不自动修改 Skill / 代码 / 项目规则**：记忆与能力建议只生成待审查内容。
9. **不展示隐藏思维链**，不保存完整 Prompt、Cookie、Token 或敏感工具参数。

## 产品使用步骤

1. 用户首次使用时，从 `USER.example.md` / `MEMORY.example.md` 复制出 `USER.md` / `MEMORY.md`，编辑自己的画像与长期笔记。
2. 用户打开会话 → 系统把 `USER.md`（全量）+ `MEMORY.md` + 当前项目记忆（预算内）注入系统提示词。
3. 用户说「记住：以后先给结论」→ Agent 高置信度直写对应 MD 文件；模糊表达 → 写入 `PENDING.md` 待确认，**不静默落盘**。
4. Agent 需要翻旧账时主动调用 `session_search` 工具 → 同时返回历史对话片段与记忆笔记命中。
5. 会话窗口超限 → 后台压缩：先 `flush_memories` 把重要信息写入 L1，再生成 LLM 重构摘要，并把旧工具输出塌缩为单行。
6. 用户可直接用编辑器修改 `USER.md` / `MEMORY.md`；下次 `reindex_all` 后修改内容可被检索。

- 验收场景 A：编辑 `USER.md` → 新会话注入生效。
- 验收场景 B：中文 2 字词 `session_search` → 同时命中旧对话与笔记。
- 验收场景 C：制造超限窗口 → flush + LLM 摘要 + 工具塌缩均按预期发生。
- 验收场景 D：旧库启动 → fail-closed；`system_rules` 内容出现在 `USER.md`。
- 验收场景 E：`git status` → `data/memory/` 真实文件未入库。

## 执行配置

> 依据 `AGENTS.md`「角色模型分配表」与 `.codebuddy/agents/*.md` 的 `model:` 字段保持一致。
> 架构师行填「自身」，不写死模型代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | **自身**（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、架构裁决、落地校验 |
| 产品经理 | `Deepseek-V4.1-Flash` | 128k | `Task(doc-updater)` | 定稿产品使用步骤与验收场景 |
| 开发主管 | `Deepseek-V4.1-Flash` | 128k | `Task(architect)` | 需求/技术评审、任务拆分、合并裁决 |
| 后端开发 | `Deepseek-V4.1-Flash` | 128k | `Task(backend-dev)` | MD 存储、FTS5、压缩链、迁移实现 |
| 测试 | `Deepseek-V4.1-Flash` | 128k | `Task(backend-tester)` / `Task(tester)` | 定向与全量回归、跨阶段验收 |

## 任务计划

> 本 spec 对应已落地的 P1/P2/P3 三阶段。任务文档后续补建于 `docs/sdd/plans/038/`。

| 编号 | 任务 | 依赖 | 状态 |
|---|---|---|---|
| 01 | 编写 spec-038 与架构签字 | — | 完成 |
| 02 | **P1** L1 文件记忆层（`markdown_store.py` / `migration.py` 新基线 / `preserve.py`） | 01 | 已实现并回归 |
| 03 | **P2** L2 会话检索（FTS5 虚表 + `session_search.py` + 写入钩子） | 02 | 已实现并回归 |
| 04 | **P3** L3 上下文窗口管理（LLM 摘要 + 工具裁剪 + `flush_memories` + 预算上调） | 03 | 已实现并回归 |
| 05 | 后续项：`MemoryAnalysisWorker` 阻塞收敛、ruff 清理、多租户（独立 spec） | 04 | 待排期 |

## 评审记录

- 需求评审：待补充（本 spec 为**实现后补写**，需求事实以「背景与问题」+ 决策记录为准）
- 技术评审：待补充
- 架构签字：**本文件「架构签字」小节**（A1 通过 / A2 有条件通过 / A3 通过 / A4 通过，由 `architect` 执行）
- 回归：P1/P2/P3 三阶段均已通过回归（详见各阶段提交记录）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-14 | 架构师（自身） | 依据已落地的 P1/P2/P3 实现事实补写本 spec；固化 Q1–Q13 与开放项裁决；落盘四个关键边界的架构签字（A1–A4）；登记三项已知遗留风险 |

---

**六条自检**：
① 每条规则能否写成测试？→「测试与验收·边界」20 条均可直接映射为用例。
② spec 是否只描述需求、task 承载实施细节？→ 是，实施细节在 `plans/038/`（待补建），本文只描述设计事实与裁决。
③ 所有 task 链接是否真实存在且依赖无环？→ 02→03→04→05，无环；plans 文档待补建（本 spec 为补写，实现已先落地）。
④ 范围划死了吗？→「明确不做」9 条。
⑤ 执行配置五行齐全？→ 是（含"自身"）。
⑥ 产品使用步骤可映射到验收点？→ 场景 A–E 与边界 1/6/13/18/20 对应。
