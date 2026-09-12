# Task 10：会话级 Skill 粘性（sticky skill）

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 09（会话链路已接入 Skill）；当前状态：`待执行`

## 一句话目标

让 Skill 在**整个会话内持续生效**——命中一次后，后续轮次不再需要重复点名，
直到用户显式切换或退出。

## 背景与问题（用户实测）

会话链路接入 Skill 后仍「用不了」，根因是 **Skill 只在点名的那一轮生效**：

| 轮次 | 用户消息 | 结果 |
|---|---|---|
| 1 | 「帮我使用 skill usenix-catalog-orchestration 下载一篇关于 agent 的论文」 | ✅ `intent` 命中，真的检索了 |
| 2 | 「好的，就下载第一篇吧」 | ❌ **0 个 intent**，走 `run_chat`（不传 tools），模型手上没有工具 |

模型因此反馈：「我看不到它们出现在我当前可用的工具列表里……我每次调用都是在幻觉」。
这不是原生 function calling 的问题——实测模型能正确返回
`tool_calls: [{"name": "search_paper_catalog", "arguments": {"query": "agent", "source": "usenix"}}]`
——而是**第二轮压根没进入带工具的链路**。

`detect_skill` 的 LLM 兜底仅在「消息提及已知技能名」或「含动词+类技能名 token」时启动，
「就下载第一篇吧」两个条件都不满足，直接返回 `none`。

## 实现方案

### 状态存储（重要约束）

`Conversation`（`backend/app/memory/models.py:21`）是 **frozen dataclass**，无 metadata 字段；
改动其结构或 conversations 表会引入迁移风险（项目历史上出现过
`KnowledgeDocumentMigrationError`）。

**要求：新增一张独立轻量表**（例如 `conversation_active_skill`），
**不得修改既有表结构与 Conversation dataclass**。表在 repository 初始化时 ensure 创建。
字段建议：`conversation_id`（主键）、`owner_id`、`skill_name`、`updated_at`。

### 粘性规则

1. **激活**：某轮 `detect_skill` 命中可用 Skill → 写入/更新 `active_skill`。
2. **沿用**：后续轮次若**未点名任何 Skill**（识别结果为 `none`），
   则沿用 `active_skill`——注入其正文并携带 Tool，等价于当轮命中。
3. **切换**：用户点名**另一个** Skill → 更新 `active_skill`，本轮即刻生效。
4. **退出**：出现明确的结束语义（如「结束技能」「退出技能」「不用技能了」
   「回到普通对话」等）→ 清除 `active_skill`，本轮走原 `run_chat`。
   **退出词表要保守**，宁可不退出也别误退。
5. **失效清理**：`active_skill` 指向的 Skill 被禁用、被删除或不存在时，
   **清除状态并回退到无技能**，不得报错、不得沿用失效技能。
6. **从无到有**：从未点名的会话，行为与改动前**完全一致**。

### 作用范围

- 仅会话链路（`backend/app/api/routes_conversations.py`）。
- 普通聊天（`routes_chat.py`）无 conversation_id，**本次不实现**粘性（保持单轮识别）。

## 文件边界

允许改动：`backend/app/memory/repository.py`（新表与读写方法）、
`backend/app/api/routes_conversations.py`（粘性逻辑）、新增/更新测试。
**不要改** `routes_chat.py`、`intent.py`、`tool_executor.py`、
`backend/app/memory/models.py` 的既有 dataclass、任何 SKILL.md。

## 明确不做

- 不改既有表结构与 `Conversation` 模型（防迁移风险）。
- 不改普通聊天链路行为。
- 不做前端展示（如"当前技能"标签）——本次只做后端状态与生效逻辑。
- 不新增第二套 Skill 识别实现（继续复用 `detect_skill`）。

## 验收（每条都要有测试）

1. 第 1 轮点名 → `intent` 命中；第 2 轮不点名 → **仍产生 `intent` 且带工具**（核心验收）。
2. 点名另一个 Skill → 切换到新 Skill。
3. 明确退出语义 → 清除粘性，本轮走 `run_chat` 且无 `intent`。
4. `active_skill` 指向的 Skill 被禁用 → 清除并回退，**不报错**。
5. 从未点名的会话 → 行为完全不变（无 `intent`、走 `run_chat`）。
6. 既有 `tests/test_conversations_api.py`、`tests/test_conversation_skill.py`、
   `tests/test_skill_intent.py`、`tests/test_memory_repositories.py` 全绿（不得减少）。
7. `.venv/bin/ruff check` 对改动文件干净。
8. 真实链路复现：连续两轮对话，第二轮「就下载第一篇吧」能产生 `intent` 并携带工具。

## 产出物、执行结果与变更日志

> 待执行后填写：存储表名、粘性规则实现位置、测试与真实链路复现结果。
