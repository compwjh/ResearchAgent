# Spec 025 — 会话上下文压缩与 Token 预算管理

## 状态

**当前状态：已完成**

> 本 spec 由占位文档升级而来。占位版本只登记缺陷，未冻结任何字段、表或接口；本版本冻结目标、阈值、数据结构、端点与边界。
> 2026-09-12：技术评审复审通过 → 用户确认 → Task02–Task06 全部完成，需求/技术/后端/前端/验收五份评审均落盘，全量回归 1345 passed（唯一失败为存量问题），服务已部署在 http://127.0.0.1:8000 并通过运行时 smoke。
> 遗留：本机 Ollama 无可用模型，"真实对话使占比达到 80% 自动压缩"的端到端路径由构造阈值的自动化测试覆盖，待 Ollama 可用后补验。

## 一句话目标

在单次模型调用的输入 token 达到装配预算 80% 时，用后台异步生成的分段摘要替换更早的历史，并把「上下文占预算比例」与「手动压缩」暴露到输入框，使长会话的首 token 延迟与输入成本稳定可控，同时保证历史原文不丢、可追溯。

## 背景与问题

- 当前上下文装配**完全按字符截断**，没有 token 概念：`history_budget_chars=6000`、历史取 `prior[-20:]`、每条 ≤2000 字符、RAG advisory 6000 字符、摘要 1500 字符、项目指令 5000 字符（`backend/app/chat/application/conversation_service.py:238-267`）。
- 全仓库**没有 token 计量函数**；唯一近似是 `backend/app/memory/repository.py:1608` 的 `token_budget*4`（英文口径，1 token≈4 字符），与中英混排的真实用量偏差可达 2 倍。
- 模型窗口为 262144（`docs/sdd/TOOLCALL_BENCHMARK.md:52`），当前单次装配约 4k 估算 token，**上下文溢出不会真实发生**。真实痛点是延迟与成本：Spec024 实测约 941 个输入 token 的预处理耗时约 7 秒（`docs/sdd/specs/024-visible-reasoning-controls.md:14`）。因此本 spec 的立项理由是**把输入 token 压在预算内以降低首 token 延迟与成本**，防溢出只是附带收益。
- 已有摘要能力只有 `conversation_summaries`（`repository.py:291`，每会话仅 1 条，UNIQUE(owner_id, conversation_id)），由非 LLM 的事件拼接产生并截断到 1200 字符（`conversation_service.py:471-511`）。它**只写库、不参与历史压缩**，只作为记忆段注入 prompt。
- 历史读取存在无效开销：`list_context_messages` 取 50 条（`repository.py:1238-1251`），装配只用 20 条。
- `context_pressure` 事件只写 `raw_events`（`routes_conversations.py:270-275`），**没有任何 GET 暴露，前端读不到**。
- 后端**没有 FastAPI BackgroundTasks、没有 asyncio**，异步统一使用 `threading` + `queue.Queue` 常驻 daemon worker（`conversation_service.py:521-533,589-600`）。
- 前端**没有任何上下文/token 占比 UI**，也没有触发后端动作的压缩入口；资源版本号当前为 `?v=33`（`frontend/index.html:8,492`）。
- 本缺陷由 Spec024 剥离登记（`024:138`）。Spec024 的一次性数据清理只删除开发测试数据，不构成本 spec 的冷数据，**本 spec 不修订 Spec024，也不与其耦合**（用户 2026-09-11 裁定）。

## 复用与替换边界

### 必须复用

- 复用 `backend/app/chat/application/chat_runner.py:33-45` 的唯一装配顺序与 `conversation_service.py:238-267` 的 `compose_chat_prompt` 作为唯一装配函数（含 dry-run）。
- 复用 `backend/app/memory/repository.py` 的 SQLite 单库与既有迁移机制（`SCHEMA_VERSION = 6`，`:38`；逐级事务迁移 `:127-193`）。
- 复用 `conversation_service.py:521-533` 的 `threading + queue.Queue` daemon worker 模式（含单例 `:798-810` 与队列去重 `:539-545`）承载异步压缩，**不引入 BackgroundTasks 或 asyncio**。
- 复用 `routes_conversations.py:489-504` 的 `memory_analysis_jobs` 状态端点模式作为压缩任务状态表达。
- 复用 Spec022 的 `Conversation / Message / 项目绑定 / SystemRule` 与已冻结的上下文优先级链（`docs/sdd/specs/022-project-conversation-memory.md:185-204`）。
- 复用前端既有百分比条结构 `div.kb-progress[role=progressbar][aria-valuenow] > .kb-progress-fill`（`frontend/app.js:3456-3470`、`styles.css:548-573`）与按钮 `disabled + try/finally` 模式（`app.js:3404-3419`）。

### 必须替换或扩展

- 新增全链路唯一的 `estimate_tokens()`，并收敛 `repository.py:1608` 的 `*4` 口径。
- 把散落的字符常量提升为命名配置项并统一由预算模块读取。
- 新增分段摘要表与压缩任务表；装配层改为「最近 K 条原文 + 更早分段摘要链」。
- 新增上下文用量端点与手动压缩端点。
- 前端输入框区域新增占比指示与一键压缩按钮。
- 改动 `app.js` / `styles.css` 必须同步 bump `?v=33 → ?v=34` 并更新契约测试断言（`tests/test_frontend_skill_tool_contract.py:81-83` 等）。

### 硬性禁止

- 禁止删除或改写 `messages` 表任何既有行（append-only 是硬约束）。
- 禁止复制第二套装配函数、第二套异步 worker 或第二套 token 估算实现。
- 禁止把摘要写入 `conversation_summaries`（该表属记忆演进，归 Spec022）。
- 禁止把 A 项目的摘要注入 B 项目或另一个会话。
- 禁止压缩平台安全约束与用户 SystemRule。
- 禁止常驻轮询前端占比，禁止为占比端点触发 RAG 检索或模型调用。

## 数据模型

### conversation_segments（新增，append-only）

| 字段 | 类型 | 约束 |
|---|---|---|
| segment_id | TEXT | 主键，uuid4 hex |
| owner_id | TEXT | 必填；与 conversation 归属一致 |
| conversation_id | TEXT | 必填；所属会话 |
| project_id | TEXT | 可空；未绑定项目的会话为 NULL |
| seq | INTEGER | 必填；同一会话内单调递增，从 1 起 |
| from_message_id | TEXT | 必填；本段覆盖的首条消息 |
| to_message_id | TEXT | 必填；本段覆盖的末条消息，与 from 构成闭区间且不重叠 |
| char_count | INTEGER | 必填；被覆盖原文字符数 |
| est_tokens | INTEGER | 必填；被覆盖原文的估算 token 数（`estimate_tokens`） |
| generator | TEXT | 必填，默认 `rule`；`rule` / `llm`，v1 只产生 `rule` |
| content_hash | TEXT | 必填；源文本指纹，用于重建与校验 |
| summary_text | TEXT | 必填；三段式正文 |
| created_at | TEXT | 必填，UTC ISO8601 |

- 纠正或重生成摘要时**新增一行新 seq**，不原位 UPDATE/DELETE。
- 唯一约束：`UNIQUE(conversation_id, seq)`，防并发重复写入。
- **区间接续算法**：同一会话内段区间按消息顺序（`(created_at, message_id)`）严格递增且**不重叠**。新段的 `from_message_id` = 「上一段 `to_message_id` 之后的**下一条**消息」；不存在上一段时，取该会话**最早**一条消息。`to_message_id` = 入队时冻结窗口的末条消息（见「装配消费契约与分段生成算法」）。已存在区间不因后续压缩被改写。
- 与 `conversation_summaries` **正交**：前者是**历史段摘要**（装配时注入历史区，本 spec 独占），后者是**记忆演进摘要**（属 Spec022，注入记忆区）。本 spec 只读前者注入历史，**不读、不写后者**，两者不得互相替代或双计。

### conversation_compaction_jobs（新增）

| 字段 | 类型 | 约束 |
|---|---|---|
| job_id | TEXT | 主键 |
| owner_id | TEXT | 必填 |
| conversation_id | TEXT | 必填 |
| status | TEXT | 必填；`queued` / `running` / `done` / `failed` |
| trigger | TEXT | 必填；`auto` / `manual` |
| est_tokens_before | INTEGER | 可空；入队时估算 |
| est_tokens_after | INTEGER | 可空；完成后估算 |
| error | TEXT | 可空；失败原因，成功为 NULL |
| created_at | TEXT | 必填，UTC ISO8601 |
| finished_at | TEXT | 可空 |

- 同一会话同一时刻只允许一个非终态 job（`queued`/`running`）。**去重必须在数据库层原子完成**：使用「部分唯一索引 `UNIQUE(conversation_id) WHERE status IN ('queued','running')`」或等价的单条条件 `UPDATE … WHERE …` 抢锁（类比既有 `try_session_lock` / `claim_evolution_checkpoint`）。**禁止应用层"先 SELECT 判重再 INSERT"**（违反 `regression-guard` #6 并发领用规则），并发冲突时返回 409 并复用既有 job。
- job 只记录状态，不承载历史正文；摘要正文只存 `conversation_segments`。

### messages（冻结）

- 表结构**不变**，语义冻结为 **append-only**：任何压缩路径都不得 UPDATE/DELETE 既有行。
- 历史原文是唯一真相源与冷数据；分段摘要是**可重建的派生数据**。

### conversation_summaries（不改动）

- 仍由 Spec022 的记忆演进流程独占，本 spec 不读写该表，避免两套摘要真相。

### 迁移

- 沿用 `repository.py:127-193` 的逐级事务迁移，新增 `_migrate_v6_to_task025` 与 `_is_task025_schema`（范式见 `:494`、`:520`），在 `:176-187` 原子应用，**不 bump `SCHEMA_VERSION`**（仍为 6），失败整体回滚。
- `_is_task025_schema` 必须**逐列校验**两张新表的全部字段，并显式校验 `UNIQUE(conversation_id, seq)` 与非终态 job 的部分唯一索引，校验强度等同 `_is_task07_schema`，防止部分迁移漏检。
- 迁移只建表与索引，不回填历史，不影响既有会话。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况（状态码） |
|---|---|---|---|
| `GET /api/conversations/{id}/context-usage` | 会话 id（当前用户） | `{used_tokens, budget_tokens, ratio, segment_count, compaction_status}` | 404 会话不存在或不属于当前用户 |
| `POST /api/conversations/{id}/compactions` | 会话 id（当前用户） | `{job_id, status, trigger:"manual"}` | 404 会话不存在；409 已有非终态 job；500 入队失败 |
| 自动压缩（内部，非公开端点） | 装配后 ratio ≥ 0.8 | 入队一个 `trigger:"auto"` 的 job，本次请求照常返回 | 入队失败仅记录观测，不影响本次回答 |
| `estimate_tokens(text)` | 文本 | 估算 token 数（int，向上取整） | 不适用（纯函数） |

### context-usage 响应契约

```json
{
  "used_tokens": 5200,
  "budget_tokens": 8000,
  "ratio": 0.65,
  "segment_count": 2,
  "compaction_status": "idle"
}
```

- `used_tokens` 由 `compose_chat_prompt` 的 **dry-run** 结果经 `estimate_tokens` 换算得到，**不调用模型、不触发 RAG 检索**；为避免开销，dry-run 只计算**历史段 + 记忆/摘要段**，不包含 RAG advisory。
- `ratio = used_tokens / budget_tokens`；`compaction_status` 直接映射该会话最新 job 的 `status`（`queued` / `running` / `done` / `failed`），无 job 时为 `idle`，用于支撑前端"压缩中"中态。
- 「dry-run 与真实装配一致」**只覆盖历史段与记忆/摘要段**（即 `used_tokens` 的口径），不覆盖 RAG advisory、SystemRule 与平台安全约束。

### 配置常量（沿用 `backend/app/platform/config.py` 的模块级常量 + `os.getenv` 写法）

```python
def estimate_tokens(text: str) -> int:
    """中英混排保守估算：chars / 1.6 向上取整；全链路唯一实现。"""

CHAT_TOTAL_TOKEN_BUDGET: int      # 默认 8000，单次调用硬上限
CHAT_COMPACT_TRIGGER_RATIO: float # 默认 0.8，达到即触发自动异步压缩
CHAT_RECENT_RAW_MESSAGES: int     # 默认 10，最近原文保留条数
CHAT_RAG_BUDGET_CHARS: int        # 默认 6000，沿用现状
CHAT_SUMMARY_BUDGET_CHARS: int    # 默认 1500，沿用现状
CHAT_PROJECT_INSTR_CHARS: int     # 默认 5000，沿用现状
```

- `repository.py:1608` 现有的 `token_budget*4` 必须改为复用 `estimate_tokens()`，全仓库不得并存两套换算。
- `CHAT_TOTAL_TOKEN_BUDGET` 与 `CHAT_COMPACT_TRIGGER_RATIO` 必须为正数；非法配置在启动时 fail-fast 或使用安全默认值，取其一并在实现时明确（默认 fail-fast）。

### 异步 worker 契约

- 复用 `conversation_service.py:521-533` 的 daemon worker 模式：请求路径只 enqueue，worker 线程消费队列生成分段摘要并写 `conversation_segments` + 更新 job 状态。
- 队列去重参考 `:539-545`，但**唯一可靠的去重在数据库层**（见 `conversation_compaction_jobs` 的部分唯一索引），队列去重只是减少无效唤醒。
- **入队即冻结窗口**：入队时必须把本次要覆盖的 `[from_message_id, to_message_id]` 落库（job 或段预占），worker 只处理冻结窗口内的消息；冻结之后新追加的消息不得被纳入本段，只能进入下一段。
- worker 内所有异常必须收敛为 `status="failed"` + `error`，不得让线程退出或阻塞对话。

## 装配消费契约与分段生成算法

### 装配层必须消费分段摘要（Task03 归属，不可悬空）

- `compose_chat_prompt`（`conversation_service.py:238-267`）的历史段必须改为：**最近 `CHAT_RECENT_RAW_MESSAGES` 条原文 + 更早部分用 `conversation_segments` 的摘要链按 `seq` 倒序填充**，直至历史预算用尽。
- 装配只从 `conversation_segments` 取当前会话（且 `project_id` 匹配）的段；**不读 `conversation_summaries`**。
- 历史段总预算仍受 `CHAT_TOTAL_TOKEN_BUDGET` 与其它各段预算的联合约束；装不下时从**最旧的摘要段**开始丢弃，最近 K 条原文优先保留。
- 未启用压缩或不存在任何段时，装配结果必须与改动前逐字符一致（等价回退）。

### 规则化分段摘要生成算法（`generator='rule'`）

对冻结窗口内的消息按 `(created_at, message_id)` 顺序扫描，产出三段式 `summary_text`：

1. **用户指令与约束**：取窗口内每条 user 消息的首个自然段；命中"必须 / 不要 / 禁止 / 只能 / 至少"等约束词的句子整句保留。
2. **已定决策与结论**：取每条 assistant 消息的首个自然段，并保留命中"决定 / 结论 / 采用 / 已确认 / 因此"的句子。
3. **关键实体与引用指针**：提取文件名、URL、路径、表名、标识符与数值型事实，去重后列出；每条附 `[message_id]` 指针以保可追溯。

- 每段按固定标题（`指令与约束` / `决策与结论` / `关键实体`）拼接，段落内按消息顺序，单条上限取 `CHAT_SUMMARY_BUDGET_CHARS` 的三分之一，超出截断并加省略标记。
- 该算法为启发式，**不调用模型**；输出必须稳定可复现（同一输入产生同一输出，便于单测与 `content_hash` 校验）。

## 边界（每条之后会变成一条测试）

- 装配后 `ratio < 0.8`：不触发任何压缩，`compaction_status` 保持 `idle`。
- 装配后 `ratio ≥ 0.8`：入队 `auto` job，**本次请求仍按现有字符截断装配并正常返回**，压缩结果从**下一条消息**起生效。
- 手动压缩：任何时刻可调用；已有非终态 job 时返回 409，不重复入队；返回后前端立即显示 `queued` 中态。
- 空会话 / 仅 1 条消息 / 全部消息都在最近 K 条内：手动压缩不产生空摘要段，返回 `done` 且 `segment_count` 不变。
- 压缩过程中生成中的那一轮使用**发送时冻结的快照**，压缩对其零影响；允许「生成中同时压缩」。
- 摘要生成失败或读取异常：回退到现有字符截断路径，绝不阻塞对话；job 标记 `failed` 并写入 `error`。
- `messages` 表在任何路径下都不被 UPDATE/DELETE；压缩后原文条数与内容不变（可断言 `COUNT(*)` 与内容哈希）。
- 跨项目隔离：`conversation_segments` 带 `owner_id / conversation_id / project_id`；装配只取当前会话的段，禁止跨会话或跨项目注入（未绑定项目的会话只能取 `project_id IS NULL` 的段）。
- 平台安全约束与用户 SystemRule **不占预算、永不压缩**，始终原样作为 system-role 注入。
- 各段预算互不挤占：历史、RAG advisory、摘要、项目指令各自独立上限；总量硬上限 `CHAT_TOTAL_TOKEN_BUDGET`。
- `estimate_tokens("")` 返回 0；`budget_tokens` 为 0 或负数时 `ratio` 不得除零（按 1.0 处理并记观测，禁止崩溃）。
- dry-run 与真实装配使用同一函数与同一配置；在**历史段与记忆/摘要段**口径上两者结果必须一致（不含 RAG advisory）；dry-run 不得触发 RAG 检索或模型调用。
- 段区间接续：同一会话的段按 `(created_at, message_id)` 严格递增且互不重叠；二次压缩的新段必须从「上一段 `to_message_id` 的下一条」开始，不得重复摘要已覆盖的消息（可断言区间并集无重叠、无遗漏）。
- 入队冻结窗口：压缩期间新追加的消息不得被纳入本次段；可断言段 `to_message_id` ≤ 入队时刻最后一条消息。
- 并发领用：同一会话并发两次压缩请求必须只产生一个非终态 job（DB 部分唯一索引/条件抢锁生效），第二个请求返回 409；可断言并发下 job 数与段数不翻倍。
- 装配消费：存在段时历史段必须包含摘要内容且最近 K 条原文保留；不存在段时装配输出与改动前逐字符一致。
- 历史读取条数与装配使用条数对齐（取 20 条、保留最近 10 条原文），消除 30 条白读。
- 重复点击压缩按钮：按钮 `disabled` + `try/finally` 复位 + 前端 in-flight 保护，不得产生两次请求。
- 前端占比条：`ratio` 仅取 `[0,1]` 区间渲染，`aria-valuenow` 与视觉宽度同源；动态文本只用 `textContent`。

## 明确不做

- 不做 LLM 生成的摘要；v1 只产生 `generator='rule'` 的规则化分段摘要（三段式：用户指令与约束、已定决策与结论、关键实体与引用指针）。
- 不引入 tiktoken 等 tokenizer 依赖；真 token 仅从 `platform/ollama_direct.py` 回读做观测与校准，不上线强依赖。
- 不删除、不改写 `messages` 任何行，不做物理归档或冷数据搬迁。
- 不修订 Spec024，不与其执行顺序耦合。
- 不做逐条勾选压缩、不做压缩程度选择、不做二次确认弹窗；手动压缩只有一档。
- 不做常驻轮询；占比只在「加载会话后」与「每轮消息完成后」两次刷新。
- 不做跨会话摘要召回（该能力属 Spec022）。
- 不做"建议用户新建会话"的引导。
- 不改动模型、Ollama 部署方式或上下文窗口配置（`num_ctx`）。
- 不修改知识库 RAG 的检索与注入逻辑。

## 验收方式

- 自动测试覆盖：`estimate_tokens` 换算与除零、`CHAT_COMPACT_TRIGGER_RATIO` 阈值边界（0.79 不触发 / 0.80 触发）、job 去重与 409、失败回退、`messages` 不变断言、跨项目隔离、dry-run 与真实装配一致性、迁移可重复执行且幂等。
- 前端契约测试：新 class 在 `styles.css` 存在、`?v=` 已递增、无 `innerHTML` 拼接用户输入、按钮 in-flight 保护存在。
- 真实 smoke：构造长会话使 ratio 越过 0.8，确认自动入队、本次回答不阻塞、下一条消息起使用摘要且占比下降；手动点击压缩按钮后占比下降且可重复触发。
- 回归：改动只涉及后端装配与前端输入框区域，全量回归在收口阶段执行一次；各 Task 只跑本 Task 相关测试。

## 产品使用步骤

> 本节由 doc-updater（产品经理视角）基于本 spec 已冻结事实扩写，作为前端/后端实现与验收的对照基准。所有数值与行为均来自冻结字段：装配预算 `CHAT_TOTAL_TOKEN_BUDGET=8000` 估算 token；自动触发阈值 `CHAT_COMPACT_TRIGGER_RATIO=0.8`（即 6400 估算 token）；占比数据来自 `GET /api/conversations/{id}/context-usage`，且**只在「加载会话后」与「每轮消息完成后」刷新，不做常驻轮询**。

### 一、用户旅程

> 普通会话与项目会话的**用户可见行为完全一致**：输入框占比、自动/手动压缩、中态、"压缩进行中"提示、失败仅提示等均相同。唯一差异在于项目会话带有项目指令与 SystemRule —— 这些与平台安全约束一样**永不压缩、始终原样保留**（见场景 9）。下方两条旅程并列给出，仅在第 4 步标注项目会话的额外不变量。

#### 普通会话旅程（按时间顺序）

1. **加载会话**：用户从会话列表打开一个普通会话。输入框区域出现「上下文 12%」形式的占比指示（数值来自加载会话后的一次 `context-usage` 读取）。界面无"压缩中"中态。
2. **连续对话**：用户逐轮发送消息。每轮消息完成后，占比指示刷新为新值（来自每轮消息完成后的一次 `context-usage` 读取）；随消息增多占比持续上升，期间无轮询或闪烁。
3. **触发自动压缩**：当某一轮装配后占比达到 80%（6400/8000），系统在该轮返回后后台异步入队 `auto` 压缩任务。**该轮回答按原样正常返回，用户无感知的阻塞或中断**。输入框区域短暂显示"压缩中"中态（对应 `compaction_status` 为 `queued`/`running`）。
4. **压缩生效**：后台压缩完成后，中态消失、占比回落到更低值。从**下一条**消息起，装配改用分段摘要，用户看到的回答质量无明显变化，但输入更省、延迟更低；早期原文仍在历史区可查。
5. **手动压缩**：用户在任意时刻（含自动压缩完成之后）点击输入框区域的「压缩」按钮，按钮立即禁用并显示中态；压缩完成后按钮恢复、占比刷新。
6. **失败兜底**：若某次压缩失败，界面仅给出失败提示，历史消息与既有回答均不受影响，对话可继续。

#### 项目会话旅程（按时间顺序，与普通会话并行对照）

1. **加载会话**：用户打开一个绑定项目的会话。输入框区域同样显示「上下文 X%」；会话顶栏/系统区完整展示项目指令与 SystemRule。
2. **连续对话**：同普通会话第 2 步，占比随消息上升、每轮完成后刷新、无常驻轮询。
3. **触发自动压缩**：同普通会话第 3 步，达到 80% 后台异步压缩，本轮回答不受影响，显示"压缩中"中态。
4. **压缩生效 + 不变量**：同普通会话第 4 步，占比下降、下条消息起用摘要；**同时，项目指令与 SystemRule 原样保留，不被任何压缩内容替代或占用预算**（与平台安全约束同等待遇）。
5. **手动压缩**：同普通会话第 5 步。
6. **失败兜底**：同普通会话第 6 步。

### 二、操作步骤

> 每一步统一按「入口位置 → 操作 → 可见反馈」描述；反馈均为输入框区域或会话区的可见变化，不涉及后台实现细节。

1. **入口：会话列表 / 顶栏会话切换 → 操作：点击打开或切换到任意会话 → 可见反馈：** 输入框区域读取一次 `context-usage` 并显示「上下文 X%」；会话历史完整加载，无"压缩中"中态（除非该会话确有进行中的 job）。
2. **入口：输入框 → 操作：输入并发送一条消息 → 可见反馈：** 消息进入生成；本轮回答正常返回后，占比指示刷新为新值（每轮消息完成后刷新一次），除本轮外不做任何额外刷新。
3. **入口：输入框区域「上下文 X%」指示 → 操作：持续对话使装配后占比达到 80%（6400/8000）→ 可见反馈：** 本轮回答照常返回、不被阻塞；系统自动后台入队 `auto` 压缩，输入框短暂显示"压缩中"（中态）；**下一条**消息起占比下降、装配改用摘要。
4. **入口：输入框区域「压缩」按钮 → 操作：点击手动压缩 → 可见反馈：** 按钮**立即禁用**并显示中态（防重复点击）；压缩完成后按钮恢复可用、占比刷新。手动压缩只有一档，无二次确认、无逐条勾选、无程度选择。
5. **入口：输入框区域「压缩」按钮（已显示"压缩中"）→ 操作：压缩进行中再次点击 → 可见反馈：** 按钮处于禁用态，前端不发送第二次请求；即便绕过禁用强行请求，后端对已有非终态 job 返回 409，前端提示「压缩进行中」。
6. **入口：输入框区域「压缩」按钮 → 操作：点击，恰逢后端压缩失败 → 可见反馈：** 仅显示失败提示；历史消息与本轮及既往回答均不受影响，占比与中态复位，对话可继续。
7. **入口：历史消息区（滚动查看）→ 操作：查看早期对话 → 可见反馈：** 压缩后早期原文仍在、逐条可查，内容未被改写或删除（`messages` append-only）。
8. **入口：会话顶栏 / SystemRule 区域 → 操作：查看平台安全约束与用户 SystemRule（项目会话还包括项目指令）→ 可见反馈：** 始终原样完整显示，不占预算、永不被压缩内容替代。
9. **入口：会话切换 → 操作：切到另一会话再切回 → 可见反馈：** 占比按目标会话重新加载（仅"加载会话后"刷新，无常驻轮询）；回到原会话时同样重新读取其 `context-usage`。

### 三、验收场景表

| 场景 | 操作步骤 | 期望结果 |
|---|---|---|
| 1. 占比随消息增长而上升 | 打开会话（步骤 1）→ 连续发送多条消息（步骤 2），观察「上下文 X%」 | 每轮消息完成后占比数值单调上升，且与 `context-usage` 的 `ratio` 同源；无轮询闪烁。 |
| 2. 达到 80% 自动压缩且不阻塞 | 持续对话直至装配后 `ratio ≥ 0.8`（6400/8000）（步骤 3） | 本轮回答正常返回、不被阻塞或中断；系统后台异步入队 `auto` job，输入框显示"压缩中"中态（`compaction_status` 为 `queued`/`running`）。 |
| 3. 压缩后下一条消息占比下降 | 场景 2 中态结束后发送下一条消息（步骤 2/3） | 中态消失、占比回落到更低值；该消息起装配使用分段摘要，回答正常。 |
| 4. 手动点击压缩 | 点击输入框区域「压缩」按钮（步骤 4） | 按钮立即禁用并显示中态；完成后按钮恢复、占比刷新；手动压缩只有一档、无确认/勾选/程度选择。 |
| 5. 重复点击只发一次请求 | 快速连续多次点击「压缩」按钮（步骤 4/5） | 按钮 `disabled` + 前端 in-flight 保护生效，仅发出一次 `POST /compactions` 请求；不产生重复 job。 |
| 6. 进行中再点提示 409 | 压缩进行中（显示"压缩中"）再次点击（步骤 5） | 前端不发送第二次请求（按钮禁用）；若强行请求，后端返回 409，前端提示「压缩进行中」。 |
| 7. 压缩失败仅提示 | 制造压缩失败并点击压缩（步骤 6） | 仅弹出/显示失败提示；历史消息与既有回答均不受影响，对话可继续。 |
| 8. 压缩后历史原文仍可查 | 压缩完成后滚动历史消息区（步骤 7） | 早期原文逐条仍在、内容未被改写或删除（`messages` append-only，可断言 `COUNT(*)` 与内容哈希不变）。 |
| 9. SystemRule/项目指令不受压缩影响 | 触发压缩后查看会话顶栏 / SystemRule 区域（步骤 8） | 平台安全约束与用户 SystemRule（项目会话含项目指令）始终原样完整显示，不占预算、永不被压缩内容替代。 |
| 10. 切换会话后占比重新加载 | 切到另一会话再切回（步骤 9） | 占比按目标会话重新读取 `context-usage`；无任何常驻轮询，仅在"加载会话后"与"每轮消息完成后"刷新。 |
| 11. 压缩期间发送消息不报错 | 在"压缩中"中态期间发送一条消息（步骤 2） | 本轮回答使用发送时冻结的快照，正常返回、不报错；压缩对其零影响，允许"生成中同时压缩"。 |
| 12. 空/单条会话手动压缩不产生空段 | 在仅有 0–1 条消息或全在最近 K 条内的会话点击「压缩」（步骤 4） | 返回 `done` 且 `segment_count` 不变，不写入空摘要段；占比稳定、不报错。 |

## 执行配置

> 2026-09-11 临时决策：本 spec 相关子代理分派改用 `hy3`（倍率 0.00），已同步临时修改对应 agent 的 `model:` 字段；架构师记「自身」，不写死代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Spec、边界、技术裁决与集成 |
| 产品经理 | hy3 | 32k | doc-updater | 产品步骤与验收场景 |
| 开发主管 | hy3 | 32k | architect | 需求/技术评审与合并裁决 |
| 后端开发 | hy3 | 64k | backend-dev | 计量、预算配置、表与迁移、异步 worker、端点 |
| 前端开发 | hy3 | 64k | frontend-dev | 占比指示、压缩按钮、版本号与契约 |
| 后端评审 | hy3 | 32k | backend-reviewer | 后端边界、迁移与并发评审 |
| 前端评审 | hy3 | 32k | frontend-reviewer | DOM、版本号、XSS、可访问性评审 |
| 后端回归 | hy3 | 32k | backend-tester | 后端定向与最终回归 |
| 前端回归 | hy3 | 32k | frontend-tester | 前端契约与静态检查 |
| 测试总控 | hy3 | 32k | tester | 跨端验收与最终全量回归汇总 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec 025 | 本文件 | — | 完成 |
| 02 | 统一 token 计量与预算配置 | [Task 02](../plans/025/task-02-token-budget-config.md) | 01、Spec 确认 | 已完成 |
| 03 | 分段摘要、装配消费改造与异步压缩 worker | [Task 03](../plans/025/task-03-segments-and-worker.md) | 02 | 已完成 |
| 04 | 上下文用量端点与压缩端点 | [Task 04](../plans/025/task-04-context-usage-api.md) | 03 | 已完成 |
| 05 | 前端占比指示与手动压缩按钮 | [Task 05](../plans/025/task-05-frontend-context-meter.md) | 04 | 已完成 |
| 06 | 评审、全量回归、部署与复盘 | [Task 06](../plans/025/task-06-review-regression-deploy.md) | 05 | 已完成 |

## 评审记录

- 需求评审：docs/sdd/reviews/025-requirement-review.md（通过（代行，非独立评审）；2026-09-12 回查 Grilling 十一条需求全部落地）
- 技术评审：docs/sdd/reviews/025-tech-review.md（通过（复审，2026-09-12）；首轮打回的 3 项 P0 与 6 项 P1 已全部修订并复审确认）
- 后端评审：docs/sdd/reviews/025-backend-review.md（GO（代行，非独立评审）；无 P0，P1 两项不阻塞）
- 前端评审：docs/sdd/reviews/025-frontend-review.md（GO（代行，非独立评审）；四项必守与 in-flight 保护均通过）
- 验收评审：docs/sdd/reviews/025-acceptance-review.md（通过（代行，非独立评审）；全量回归 1345 passed、运行时 smoke 通过，真实对话路径因 Ollama 无模型待补验）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 架构师（自身） | 登记会话上下文压缩与 token 预算缺陷；按用户要求仅占位，不实施。 |
| 2026-09-11 | 架构师（自身） | Grilling Round 1 确立目标改写、字符估算、读时装配、规则摘要四项决策；用户裁定不修订 Spec024。 |
| 2026-09-11 | 架构师（自身） | Grilling Round 2 确立 80% 阈值、异步不阻塞、手动压缩一档、占比端点与刷新时机、token 系数统一、竞态与隔离边界，并将前端 UI 纳入本 spec；重写占位文档为正式设计。 |
| 2026-09-11 | 开发主管（architect 代行） | 技术评审结论「打回」：P0-1 装配消费 segments 悬空、P0-2 分段区间接续算法未定义、P0-3 单 job 去重违反并发领用规则；P1 六项（dry-run 口径措辞、schema 逐列校验、compaction_status 中态、入队冻结窗口、rule 生成算法、两表正交澄清）。 |
| 2026-09-11 | 架构师（自身） | 按评审修订：新增「装配消费契约与分段生成算法」章节、段区间接续与入队冻结窗口、DB 部分唯一索引原子领用、`_is_task025_schema` 逐列校验、dry-run 一致性口径限定；Task03 归属装配消费改造。待复审。 |
| 2026-09-12 | 开发主管（architect 代行） | 复审结论「通过（复审，2026-09-12）」：P0×3、P1×6 共 9 项全部确认已解决，无新增 P0；附两项非阻塞提示——`used_tokens` 不含 RAG/SystemRule 使自动阈值主要在项目会话触及（Task04 需构造可触及阈值的会话）、`repository.py` 行号应为 1608。 |
| 2026-09-12 | 架构师（自身） | 采纳复审提示：修正 `repository.py:1607 → 1608` 三处引用；技术评审结论转为通过。 |
| 2026-09-12 | 架构师（自身） | 用户确认后进入实施：完成 Task02（计量与预算配置）、Task03（两表 + 迁移 + 装配消费改造 + 异步 worker）、Task04（context-usage / compactions 端点 + 80% 自动触发）、Task05（前端占比条与压缩按钮，`?v=33→34`）、Task06（评审 + 全量回归 1345 passed + 部署 smoke + 复盘）。新增测试 52 项，唯一失败为 git stash 复现的存量问题。 |
| 2026-09-12 | 架构师（自身） | 修正子代理越界改动：恢复 `build_role_aware_messages` 的 role-history 装配顺序（历史不再搬进 advisory），仅在有段时把最近原文收敛到 `CHAT_RECENT_RAW_MESSAGES` 条；修复两条测试夹具缺陷（历史顺序、`job` 未定义）。 |
