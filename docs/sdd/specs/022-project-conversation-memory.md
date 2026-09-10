# Spec 022 — 项目会话管理与自进化长期记忆

## 状态

**当前状态：`待确认`**

## 一句话目标

让用户像使用 ChatGPT 一样管理项目和持久会话，并让绑定项目的新会话可靠召回经过授权的项目记忆；后续在同一套可追溯、可修正、可遗忘的协议上扩展全局记忆、自动整理、项目文档、处理过程和移动端。

## 背景与问题

- 当前首页聊天是单轮请求，没有稳定的项目、会话、消息历史或 LangGraph checkpoint；刷新或换会话后上下文不能恢复。
- 当前论文检索 `search_session`、文章任务、知识库、Langfuse trace、SDD Task ledger 和 Agent logs 各有独立职责，均不能充当用户长期记忆。
- 参考 Hermes/CoALA 的分层思路，记忆系统必须同时覆盖写入、修正、遗忘和召回，而不能只增加一个向量检索入口。
- 用户需要全局用户记忆、项目记忆和当前会话三层上下文；未绑定项目的会话不得读取项目记忆。
- 用户需要看到真实处理步骤与简短决策摘要，但不得保存或展示模型隐藏的完整内部思维链。

## 回滚点

- 实施前记录分支、commit、工作树、现有聊天端点、SSE 契约和本地数据状态。
- 新会话入口通过 application facade 复用现有 Agent 编排；失败时可关闭新入口并退回当前无持久会话的聊天路径，不迁移或覆盖知识库原件。
- SQLite schema 采用版本化迁移；迁移前备份数据库。禁止 `reset`、`stash`、`clean`、自动 push 或覆盖用户修改。
- 项目、会话和记忆数据库与论文知识库、论文目录、文章任务数据库完全隔离。

## 现有实现复用与替换边界（实现硬约束）

### 原样或抽象后复用

- 复用 `frontend/index.html` 现有侧栏、聊天区和输入框；复用 `frontend/app.js` 的安全 Markdown、流式 token 写入和消息 DOM。
- 复用现有 `/api/agent/run` 背后的意图识别、论文任务和普通聊天编排能力，但由新的唯一会话 application 入口调用。
- 复用 `platform.bootstrap.ProviderRegistry` 的依赖注入方式、SQLite WAL/事务/迁移方式、UTC 时间和稳定错误体约定。
- 复用知识库 application facade、dense+sparse/RRF/reranker 和安全引用能力；记忆不得写入 `papers` collection。
- 复用观测的 `session_id` / `user_id` 接缝，但只记录脱敏 ID、命中数量、延迟和状态，不把 trace 当记忆事实源。

### 必须新增或替换

- 新增独立 `projects / conversations / messages / memories / memory_evidence / processing_steps` 领域模型和 SQLite repository。
- 首页发送行为迁移到唯一会话消息入口；浏览器不回传完整历史，服务端按 conversation ID 装配上下文。
- 当前“新建对话”只清空 DOM 的行为替换为惰性草稿：第一条有效消息时才原子创建会话。
- 当前没有历史分页、稳定会话 URL、流式中断持久化和记忆使用证据，必须补齐。

### 硬性禁止

- 不复用论文检索 `search_session`、文章任务 SQLite、知识库 metadata/Qdrant、浏览器 profile、Langfuse trace、SDD Task ledger 或 Agent logs 作为记忆库。
- 不保存或展示隐藏思维链、完整 Prompt、Cookie、Token、浏览器 Profile、完整向量或敏感工具参数。
- 运行时不得自动修改 `.agents/skills/`、`AGENTS.md`、Prompt 模板或项目代码；只能生成待审查的 Skill 改进建议。
- 记忆只作为上下文数据，不得直接触发下载、删除、执行命令或绕过工具安全边界。

## 领域与数据模型

### `Project`

| 字段 | 类型 | 约束 |
|---|---|---|
| `project_id` | str | 服务端生成、全局唯一、不可变 |
| `owner_id` | str | v1 固定本地用户值，预留多用户迁移 |
| `name` | str | 必填、去首尾空白、长度受限 |
| `instructions` | str/null | 项目明确指令；MVP 可为空 |
| `status` | enum | `active / archived / deleted` |
| `created_at / updated_at` | UTC datetime | 必填 |

### `Conversation`

| 字段 | 类型 | 约束 |
|---|---|---|
| `conversation_id` | str | 服务端生成、稳定 URL 使用 |
| `owner_id` | str | v1 固定本地用户值 |
| `project_id` | str/null | null 表示未绑定；一次只属于一个项目 |
| `title` | str | 首条消息生成，可后续重命名 |
| `status` | enum | `active / archived / deleted` |
| `memory_history_policy` | enum | `from_binding / include_prior_history` |
| `created_at / updated_at` | UTC datetime | `updated_at` 用于最近会话排序 |

### `Message`

| 字段 | 类型 | 约束 |
|---|---|---|
| `message_id` | str | 服务端生成、全局唯一 |
| `conversation_id` | str | 必填，外键 |
| `parent_message_id` | str/null | 预留回复关系；v1 保持线性 |
| `role` | enum | `user / assistant / tool` |
| `content` | str | 仅保存用户可见内容或脱敏工具摘要 |
| `status` | enum | `pending / streaming / completed / interrupted / failed` |
| `model / mode` | str/null | 可观察执行配置，不含密钥 |
| `created_at / completed_at` | UTC datetime | 必填/可空 |

### `MemoryRecord`

| 字段 | 类型 | 约束 |
|---|---|---|
| `memory_id` | str | 稳定 ID |
| `owner_id` | str | 必填 |
| `scope` | enum | `global / project` |
| `project_id` | str/null | project scope 必填，global 必须为空 |
| `category` | enum | `user_preference / stable_fact / project_rule / capability_method` |
| `statement` | str | 脱离原会话仍可理解；不能存整段对话 |
| `source_kind` | enum | `explicit / repeated / verified_failure / manual` |
| `status` | enum | `candidate / active / superseded / disabled / deleted` |
| `confidence` | float | 0–1；显式写入也保留来源而非盲信 |
| `supersedes_id` | str/null | 新记忆替代旧记忆时指向旧记录 |
| `created_at / updated_at / last_used_at` | UTC datetime | 可审计 |

### `MemoryEvidence`

| 字段 | 类型 | 约束 |
|---|---|---|
| `memory_id` | str | 外键 |
| `conversation_id / message_id` | str/null | 可追溯来源；删除单会话不联动记忆 |
| `evidence_type` | enum | `user_statement / repeated_sessions / tool_failure / manual` |
| `excerpt` | str/null | 脱敏短摘录，不复制完整消息 |

### `ProcessingStep`

| 字段 | 类型 | 约束 |
|---|---|---|
| `step_id` | str | 唯一 |
| `message_id` | str | 对应 assistant 消息 |
| `kind / label` | str | 真实阶段或工具事件，不是隐藏思维链 |
| `status` | enum | `running / completed / failed / skipped` |
| `summary` | str/null | 脱敏简短结果 |
| `started_at / completed_at` | UTC datetime | 用于耗时 |

## 上下文与优先级

```text
平台安全与系统约束
→ 用户当前明确指令
→ 项目明确指令
→ 用户全局记忆
→ 项目长期记忆
→ 相关历史会话摘要
```

- 未绑定项目的会话只能召回全局记忆；MVP 尚未开放全局记忆写入时等价于不召回长期记忆。
- 单项目经验不得自动升格为全局记忆。跨项目重复只能产生候选，需用户确认。
- 用户明确纠正时创建新记录并将旧记录标为 `superseded`；不原位覆盖审计证据。
- 用户显式全局记忆不自动过期；推断记忆可因长期未使用而降权，但不自动物理删除。

## 记忆意图契约

模型对当前用户消息输出结构化结果：

- `explicit`：明确表达长期记忆意图，保存抽取后的独立陈述。
- `ambiguous`：可能是长期偏好，询问用户是否保存，不直接写入。
- `none`：普通内容，不产生记忆。

结果同时包含 `statement`、`scope`、`confidence` 和去除记忆表达后的 `current_task`。一条消息同时包含记忆和任务时，先保存明确记忆，再继续执行任务。未绑定会话要求保存项目记忆时，引导用户选择项目或仅在本会话使用；MVP 不静默保存为全局记忆。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `POST /api/projects` | `name` | Project，201 | 400/409 |
| `GET /api/projects` | cursor/limit | 项目列表 | 400 |
| `POST /api/conversations/messages` | 首条消息、可选 project/model/mode | 创建会话并返回 SSE | 400/404/503 |
| `POST /api/conversations/{id}/messages` | 新消息、model/mode | 保存消息并返回 SSE | 400/404/409/503 |
| `GET /api/conversations` | project_id/null、cursor/limit | 最近会话列表 | 400/404 |
| `GET /api/conversations/{id}/messages` | before cursor、`target_chars` | 从新到旧满足字符预算的完整消息批次 | 400/404 |
| `PATCH /api/conversations/{id}` | title/project/status/history policy | Conversation | 400/404/409 |
| `DELETE /api/conversations/{id}` | id | 204；不联动记忆 | 404/409 |
| `GET/POST/PATCH/DELETE /api/memories` | scope/project/filter/body | 记忆或列表 | 400/404/409 |
| `GET /api/messages/{id}/processing-steps` | message ID | 最终步骤列表 | 404 |

首页使用稳定会话 URL `/c/{conversation_id}`。SSE 至少包含：

- `meta`：project/conversation/user_message/assistant_message/model/mode。
- `progress`：step ID、真实 label、status、脱敏 summary。
- `memory`：本次使用或新增的 memory ID、scope、可见 statement。
- `token`：回答正文增量。
- `error`：稳定 code、message、retryable。
- `done`：conversation/message/status。

## 消息与会话分页

- 左侧会话列表按 `updated_at` 倒序，首批 20 条，向下滚动按稳定游标每次继续加载 20 条。
- 打开会话时，前端根据聊天区域宽度、高度、字号和行高估算约两屏文字量，通过 `target_chars` 请求最新消息。
- 后端从最新消息向前累计显示字符数，达到预算后完整包含最后一条，不截断单条消息；每批最多 50 条。
- 向上滚动使用稳定 `before` 游标加载更早消息，插入后保持当前阅读位置；到达最早消息显示完成状态。

## 处理过程展示

- UI 名称为“处理过程”，只展示真实阶段、工具状态、数量、耗时和简短决策摘要。
- 运行中为浅紫到亮紫的海浪渐变；完成为静态低饱和紫色；失败为红色；跳过/降级为灰色。
- 支持 `prefers-reduced-motion`：关闭动画但保留状态。
- 生成时实时展示；完成后持久化最终步骤并默认折叠。不得把编造的阶段冒充真实事件。

## RAG 来源展示

- 流式回答期间不提前铺开切片；回答正文 `done` 后才显示来源。
- 默认最多显示 5 个紧凑编号方块 `1`–`5`；不足 5 个只显示实际数量。
- 点击编号展开对应大段切片内容；同时只展开一个，二次点击收起。
- 展开内容包含来源标题、位置和切片正文；可跳转到知识库原文。引用仍使用现有知识库安全读取链路。

## 边界与失败场景

- 首条消息校验失败不得创建空会话；模型失败时保留会话、用户消息和 `failed` assistant 消息。
- 流式连接中断时保存已生成部分并标为 `interrupted`；切换会话必须取消旧流，禁止 token 写入新会话。
- project/conversation 不匹配、已删除、跨项目移动冲突和非法 cursor 必须返回稳定错误。
- 绑定已有会话时默认从绑定后开始参与项目记忆；选择纳入旧历史必须显式确认。
- 删除单个会话不联动记忆。删除项目事务性删除项目、所属会话和项目记忆；全局记忆保留；知识库文档仅解除关联。
- 记忆分类模型不可用时聊天仍可继续，但必须提示“记忆未保存/未分析”并允许重试。
- 记忆召回失败不得阻断普通聊天；必须产生真实 `skipped/failed` 处理步骤。
- SQLite 损坏、迁移失败或锁冲突时 fail-closed，不以浏览器 localStorage 冒充权威会话库。

## Task 02 MVP 硬门

第一个开发 Task 必须交付可运行的桌面端纵向闭环：项目创建、惰性会话创建、消息持久化、历史继续、两屏消息分页、模型识别明确/模糊/无记忆意图、项目记忆写入、新项目会话召回、记忆使用提示、最小处理过程、未绑定负例和服务重启恢复。缺任一项均不得将 MVP 标记完成。

固定演示：

1. 创建项目“记忆测试”。
2. 会话 A 表达“以后回答时先给结论，再补充解释”。
3. 系统保存项目记忆并显示新增记录。
4. 同项目新会话 B 普通提问，回答遵循记忆并显示使用记录。
5. 未绑定会话提出同一问题，不召回该项目记忆。
6. 刷新和重启服务后，会话、消息和记忆仍在。

## 明确不做

- 不做多用户登录/权限、云同步、跨设备同步或团队共享项目。
- Task02 不做手机端；手机端必须在 Task06 完成。
- 不展示隐藏思维链，不保存完整 Prompt 或敏感运行参数。
- 不把全部 raw 历史自动塞入上下文，不把普通陈述自动升格为长期记忆。
- 不自动修改 Skill、代码或项目规则，不让记忆绕过工具权限和安全校验。
- 不重写论文下载、安全校验、知识库索引、RAG 或现有 Agent 编排实现。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待确认后补充完整用户旅程、桌面/手机操作步骤和验收场景。

## 开发与验证策略

- 开发中只跑精确测试；Task 收口跑受影响领域测试与静态检查。
- Task02、Task05、Task06 作为用户可见里程碑，完成后直接部署并执行真实 smoke。
- 全量回归只在 Spec 收口阶段启动，并必须在最终候选版本上通过；失败后先用定向测试修复，再重新运行全量回归。
- 一个 Task 在定向测试稳定后集中评审一次；P0/P1 批量修复后集中复审一次，不为每个微小修复重启完整门禁。
- 每个 Task 固定复用少量报告并追加修复轮次，不生成 `final-v2-recheck-final` 式重复文件。
- 已确认范围内的小缺陷追加到当前 Task，只有数据模型、公开接口、用户行为或范围变化才回到 Spec 重新确认。
- Task02 冻结 ID/schema version、游标、唯一消息入口、SSE、记忆注入和迁移机制；后续只做版本化扩展。

## 验收方式

- 用固定演示证明同项目跨会话记忆生效、未绑定会话隔离、重启后持久化。
- 验证 `explicit / ambiguous / none`，以及分类模型不可用时聊天可继续且不假写记忆。
- 验证消息两屏加载、向上分页、滚动位置稳定、左侧会话游标和流式中断恢复。
- 验证全局/项目优先级、跨项目移动、项目删除级联、单会话删除不联动记忆。
- 验证 RAG 正文完成后才出现最多 5 个编号来源，单项展开大段切片。
- 验证桌面和手机端、减少动态效果、处理步骤真实持久化、错误/降级显示。
- 验证知识库、论文检索/下载、文章任务和聊天回归；最终执行全量回归与真实部署。

## 执行配置

本机模型已于 2026-09-11 通过 `ollama list` 核实。模型名不写入业务代码。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Spec、领域边界、契约冻结和合并裁决 |
| 产品经理 | `qwen3.5:9b` | 32k | `doc-updater` | 确认后补产品步骤与验收场景 |
| 后端开发 | `qwen3.8:27b-mlx` | 64k | `backend-dev` | SQLite、application、API、SSE、记忆编排 |
| 前端开发 | `qwen3.8:27b-mlx` | 64k | `frontend-dev` | 桌面/移动会话 UI、进度、RAG 展示 |
| 后端评审 | `qwen3.8:27b-mlx` | 64k | `backend-reviewer` | 数据一致性、并发、迁移和边界评审 |
| 前端评审 | `qwen3.8:27b-mlx` | 64k | `frontend-reviewer` | DOM、流式竞态、可访问性和 XSS 评审 |
| 后端测试 | `qwen3.5:9b` | 32k | `backend-tester` | 后端定向与领域回归 |
| 前端测试 | `qwen3.5:9b` | 32k | `frontend-tester` | 前端契约、浏览器和移动端验证 |
| 测试总控 | `qwen3.5:9b` | 64k | `tester` | 里程碑 smoke、最终全量与验收报告 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec022 与任务计划 | 本文件 | — | 完成 |
| 02 | 桌面端项目、会话与项目记忆 MVP | [`task-02-desktop-memory-mvp.md`](../plans/022/task-02-desktop-memory-mvp.md) | 01、Spec 确认 | 待执行 |
| 03 | 完整管理、全局记忆与治理界面 | [`task-03-management-global-memory.md`](../plans/022/task-03-management-global-memory.md) | 02 | 待执行 |
| 04 | 异步整理、摘要与跨会话召回 | [`task-04-memory-evolution-recall.md`](../plans/022/task-04-memory-evolution-recall.md) | 03 | 待执行 |
| 05 | 项目文档、RAG 来源与完整处理过程 | [`task-05-research-context-progress.md`](../plans/022/task-05-research-context-progress.md) | 04 | 待执行 |
| 06 | 手机端适配 | [`task-06-mobile-experience.md`](../plans/022/task-06-mobile-experience.md) | 05 | 待执行 |
| 07 | 能力方法记忆与 Skill 改进建议 | [`task-07-capability-memory-proposals.md`](../plans/022/task-07-capability-memory-proposals.md) | 04 | 待执行 |
| 08 | 最终评审、全量回归、部署与复盘 | [`task-08-review-regression-deploy.md`](../plans/022/task-08-review-regression-deploy.md) | 05、06、07 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/022-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/022-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/022-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 用户 / 架构师（自身） | 通过 Grill with Docs 确认项目—会话—消息—记忆层级、惰性会话、项目隔离、两屏消息分页、处理过程、RAG 编号展开、手机端后置和 MVP 优先交付边界；编号指定为 Spec022 |
