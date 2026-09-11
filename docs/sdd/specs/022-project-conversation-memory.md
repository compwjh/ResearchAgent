# Spec 022 — 项目会话管理与自进化长期记忆

## 状态

**当前状态：`实施中`**

## 一句话目标

让用户像使用 ChatGPT 一样管理项目和持久会话，并让绑定项目的新会话可靠召回经过授权的项目记忆；后续在同一套可追溯、可修正、可遗忘的协议上扩展全局记忆、自动整理、项目文档、处理过程和移动端。

## 背景与问题

- 当前首页聊天是单轮请求，没有稳定的项目、会话、消息历史或 LangGraph checkpoint；刷新或换会话后上下文不能恢复。
- 当前论文检索 `search_session`、文章任务、知识库、Langfuse trace、SDD Task ledger 和 Agent logs 各有独立职责，均不能充当用户长期记忆。
- 参考 Hermes/CoALA 的分层思路，记忆系统必须同时覆盖写入、修正、遗忘和召回，而不能只增加一个向量检索入口。
- 用户需要全局用户记忆、项目记忆和当前会话三层上下文；未绑定项目的会话不得读取项目记忆。
- 用户需要看到真实处理步骤与简短决策摘要，但不得保存或展示模型隐藏的完整内部思维链。
- Task05 部署验证暴露桌面端交互缺陷：实时/历史消息可能失去用户—回答配对顺序，处理过程位于回答之后、无法真正折叠，且同一逻辑步骤的 `running/completed` 被写成不同记录，导致重复步骤和永久动画。
- 当前项目区域仍采用下拉框、常驻创建表单和常驻治理按钮，不符合已确认的 ChatGPT 式项目/会话管理体验。
- 当前“记忆分析”同步阻塞回答且依赖关键词；它应改为不影响本次回答的异步语义分类，并在回答后的独立记忆结果区完成自动保存或用户确认。

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
- 同一轮消息必须以用户消息和其 `parent_message_id` 指向的 assistant 消息组成稳定 turn；实时流和历史重载都不得仅依赖时间戳猜测顺序。
- 当前同步关键词记忆分类替换为持久化异步语义分析；回答 SSE 不等待该任务，前端通过消息级结果接口恢复进度与结果。
- 项目下拉框、侧栏常驻创建表单和常驻治理按钮替换为项目/会话平铺列表、悬停/聚焦菜单和弹窗创建流程。

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

- 每个 assistant 消息必须通过 `parent_message_id` 指向触发它的 user 消息；前端以该关系组装 turn，顺序恒为 user → assistant。

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
| `step_id` | str | 同一逻辑步骤全生命周期稳定且唯一 |
| `message_id` | str | 对应 assistant 消息 |
| `kind / label` | str | 真实阶段或工具事件，不是隐藏思维链 |
| `status` | enum | `running / completed / failed / skipped / interrupted`；终态不可回到 running |
| `summary` | str/null | 脱敏简短结果 |
| `started_at / completed_at` | UTC datetime | 用于耗时 |

`(message_id, kind, logical_sequence)` 唯一。同一步骤开始时创建，后续状态必须原位更新；禁止用新的 `step_id` 写第二条完成记录。

### `MemoryAnalysisJob`

| 字段 | 类型 | 约束 |
|---|---|---|
| `analysis_id` | str | 服务端生成、稳定 ID |
| `user_message_id` | str | 唯一绑定触发分析的用户消息 |
| `owner_id` | str | 必填 |
| `project_id_snapshot` | str/null | 消息发送时的项目快照，完成时不得跟随会话移动 |
| `status` | enum | `pending / running / completed / partial / failed` |
| `model` | str/null | 实际分类模型；不含密钥 |
| `cursor / batch_no` | str/int/null | 无固定条数上限时的续处理 checkpoint |
| `saved_count / pending_count / failed_count` | int | 结果摘要 |
| `error_code` | str/null | 稳定、脱敏错误码 |
| `created_at / updated_at / completed_at` | UTC datetime | 可恢复、可审计 |

### `MemoryAnalysisItem`

| 字段 | 类型 | 约束 |
|---|---|---|
| `item_id` | str | 稳定 ID；用于逐条与批量决策 |
| `analysis_id` | str | 外键 |
| `statement` | str | 一条独立、脱离原会话仍可理解的记忆 |
| `suggested_scope` | enum | `global / project` |
| `confidence / rationale_summary` | float/str | 仅可见简短依据，不含隐藏思维链 |
| `decision_status` | enum | `auto_saved / pending_confirmation / duplicate / superseded / ignored / failed` |
| `memory_id` | str/null | 已保存或已存在的目标记录 |
| `created_at / decided_at` | UTC datetime | 必填/可空 |

- 不设置每条用户消息的业务条数上限；在消息长度和模型上下文允许范围内抽取所有独立记忆，必要时按 checkpoint 分批继续。
- 完全重复不得新建记录；用户明确纠正可创建新版本并 supersede 旧记录；推断冲突和跨 scope 升格必须等待确认。

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

## 记忆意图与异步分析契约

独立记忆分类模型异步分析当前用户消息，输出零到多条结构化结果：

- `explicit`：明确表达长期记忆意图，保存抽取后的独立陈述。
- `ambiguous`：可能是长期偏好，询问用户是否保存，不直接写入。
- `none`：普通内容，不产生记忆。

每条结果包含 `statement`、`scope`、`confidence` 和脱敏简短依据。回答生成不等待分析完成；记忆召回仍在回答前执行，因为它使用的是此前已经确认的记忆。

- 只有用户明确要求记住、范围明确且高置信度的结果可自动保存。
- 推测偏好、低置信度、与已有记忆冲突或可能改变 scope 的结果进入 `pending_confirmation`。
- 无需记忆时不产生结果项；分类失败不阻断回答且不假写记忆。
- 分析默认使用独立可配置的小模型，当前默认 `qwen3.5:9b`；业务代码不得硬编码模型名。默认不可用时尝试模型库配置的其他小型分类模型，仍失败则终止本次分析，不占用回答模型。
- 多轮消息的分析任务可并行、互不覆盖；刷新、切换会话和进程重启后可从持久化 checkpoint 恢复。

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
| `GET /api/messages/{user_message_id}/memory-analysis` | cursor/limit（默认 10） | job 摘要、结果项、next_cursor | 400/404 |
| `POST /api/memory-analysis/items/{item_id}/decision` | `save_project / save_global / ignore`、可选 project_id | 单项最终状态 | 400/404/409 |
| `POST /api/messages/{user_message_id}/memory-analysis/decisions` | 批量按建议保存或全部忽略 | 各项成功/失败摘要 | 400/404/409 |

首页使用稳定会话 URL `/c/{conversation_id}`。SSE 至少包含：

- `meta`：project/conversation/user_message/assistant_message/model/mode。
- `progress`：step ID、真实 label、status、脱敏 summary。
- `memory`：本次回答实际召回使用的 memory ID、scope、可见 statement；当前消息的异步分析结果不阻塞或延长回答 SSE。
- `token`：回答正文增量。
- `error`：稳定 code、message、retryable。
- `done`：conversation/message/status。

## 消息与会话分页

- 左侧会话列表按 `updated_at` 倒序，首批 20 条，向下滚动按稳定游标每次继续加载 20 条。
- 打开会话时，前端根据聊天区域宽度、高度、字号和行高估算约两屏文字量，通过 `target_chars` 请求最新消息。
- 后端从最新消息向前累计显示字符数，达到预算后完整包含最后一条，不截断单条消息；每批最多 50 条。
- 向上滚动使用稳定 `before` 游标加载更早消息，插入后保持当前阅读位置；到达最早消息显示完成状态。
- 实时与历史消息均按 turn 渲染：先放 user，再放其 child assistant；创建 assistant 空壳后只更新该节点，禁止异步重载把回答插到问题上方。

## 处理过程展示

- UI 名称为“处理过程”，只展示真实阶段、工具状态、数量、耗时和简短决策摘要。
- 仅包含影响本次回答的步骤：已有记忆召回、项目文档检索、回答生成及真实工具步骤；“判断当前消息是否需要记住”属于回答后的异步记忆结果，不进入此列表。
- 步骤收到真实开始事件后才逐条出现；可选步骤未执行时不显示，不预铺固定占位清单。
- 运行中为浅紫到亮紫的海浪渐变；完成为静态低饱和紫色；失败为红色；跳过/降级为灰色。
- 支持 `prefers-reduced-motion`：关闭动画但保留状态。
- 运行时默认展开，用户可手动折叠且新步骤不得强制展开；回答结束后自动折叠，历史默认折叠，用户可再次展开。
- `done/error/abort` 到达时必须把所有残留 running 步骤转为真实终态并停止动画。折叠必须有实际 DOM 可见性效果，不得被 CSS 覆盖。
- 生成时实时展示；完成后持久化最终步骤。不得把编造的阶段冒充真实事件。

## 异步记忆结果展示

- 位于同一 turn 的回答正文之后、RAG 来源之前；数据绑定 user message，视觉上归入其 assistant 回答。
- 分析中显示紧凑的“正在判断是否需要记住…”；不占用回答输入状态，用户可继续发送下一条消息。
- 自动保存、重复或更新成功时默认折叠，标题显示数量；无需记忆时提示自动消失。
- 存在不确定或冲突项时自动展开，支持逐条 `保存到当前项目 / 保存为全局 / 不保存`；未绑定项目时项目动作改为选择项目后保存。
- 支持“按建议保存全部”和“全部不保存”；单项失败不回滚其他成功项，标题持续显示成功、待确认和失败数量。
- 结果项默认每批 10 条，继续滚动或“加载更多”获取下一批；抽取总数无固定上限。
- 分析最终失败时显示默认折叠的灰色提示；后台可有限重试，本轮不提供手动重试按钮。

## 项目与会话侧栏

- 采用 ChatGPT 式平铺结构：上方项目列表，下方最近会话列表；移除项目下拉框、常驻创建表单和聊天头部常驻治理按钮。
- “项目”标题右侧 `＋ / ⋯` 只在 hover 或 `focus-within` 时显示；`＋` 打开只要求名称的创建弹窗，成功后进入新项目。
- 项目标题菜单提供“最近更新 / 名称 A–Z”排序和归档项目入口；排序选择保存在浏览器本地，不新增后端排序字段或拖拽排序。
- 每个项目行的 `⋯` 提供重命名、归档、删除；每个会话行的 `⋯` 提供重命名、移动到项目、移出项目、归档、删除。
- 归档项目和会话默认不混入主列表，分别从对应标题菜单进入归档视图并支持恢复或删除。
- 首页默认无项目上下文，新会话不绑定项目；点击项目后只显示该项目会话，此时新会话自动绑定当前项目；点击“对话”主导航返回全部最近会话并清除项目上下文。
- 桌面端鼠标悬停和键盘聚焦都能发现操作；手机端不依赖 hover 的菜单交互留在 Task06 完成。

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
- 异步分析完成前项目被删除时不得写入其他项目；按消息发送时快照终止为失败。会话移动不能改变已在运行任务的 scope。
- 分析输出截断或批次中断时保持 `partial` 与 checkpoint，不得把部分结果伪装为完整；重复调度必须幂等。
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
- 不做后端持久化的手动项目排序、项目拖拽排序或跨设备同步排序。
- 本轮不在记忆确认卡片中提供正文编辑器；保存后通过既有“记忆治理”页面修订。

## 产品使用步骤

### Task02 桌面端 MVP

1. 用户创建项目“记忆测试”，在侧栏看到项目和新会话入口。
2. 用户在绑定该项目的会话 A 表达“以后回答时先给结论，再补充解释”，系统保存为项目记忆并显示新增记忆提示。
3. 用户从同一项目打开会话 B 并提问，回答遵循该记忆，同时显示本次使用的记忆记录。
4. 用户打开未绑定项目的新会话提问，系统不读取“记忆测试”的项目记忆。
5. 用户刷新页面或重启服务，重新打开稳定会话 URL，确认项目、消息和项目记忆仍在。
6. 用户表达模糊偏好或普通陈述，系统分别提示待确认或不写入；记忆分类不可用时仍完成普通聊天并提示未分析。

### 后续 Task

- Task03–Task07 分别补充管理、演化召回、研究上下文、手机端和能力建议步骤；Task08 统一执行最终全量验收。

### Task05 桌面缺陷修复轮

1. 用户发送“你是谁”，页面立即在问题下方创建回答容器，处理过程先于正文出现；回答和刷新后顺序均不颠倒。
2. 处理步骤按真实事件逐条出现，同一步骤原地完成；回答结束后动画停止并自动折叠，用户可重新展开。
3. 回答完成后，异步分类模型继续判断当前消息是否值得记住；输入框已经可继续发送，不等待分析。
4. 明确记忆自动保存并显示折叠摘要；不确定或冲突结果自动展开供确认；普通消息的分析提示最终消失。
5. 一条消息可产生任意数量的独立记忆，结果区每次展示 10 条并支持逐条和批量决策。
6. 用户通过侧栏项目/会话行的悬停菜单完成创建、排序、重命名、移动、归档、恢复和删除；常驻表单及按钮不再占据页面。

## 开发与验证策略

- 开发中只跑精确测试；Task 收口跑受影响领域测试与静态检查。
- Task02、Task05、Task06 作为用户可见里程碑，完成后直接部署并执行真实 smoke。
- 全量回归只在 Spec 收口阶段启动，并必须在最终候选版本上通过；失败后先用定向测试修复，再重新运行全量回归。
- 一个 Task 在定向测试稳定后集中评审一次；P0/P1 批量修复后集中复审一次，不为每个微小修复重启完整门禁。
- 每个 Task 固定复用少量报告并追加修复轮次，不生成 `final-v2-recheck-final` 式重复文件。
- 已确认范围内的小缺陷追加到当前 Task；本次异步分析数据模型、结果接口和侧栏行为变化已回到 Spec 待确认，确认前不得修改业务代码。
- Task02 冻结 ID/schema version、游标、唯一消息入口、SSE、记忆注入和迁移机制；后续只做版本化扩展。

## 验收方式

- 用固定演示证明同项目跨会话记忆生效、未绑定会话隔离、重启后持久化。
- 验证 `explicit / ambiguous / none`，以及分类模型不可用时聊天可继续且不假写记忆。
- 验证消息两屏加载、向上分页、滚动位置稳定、左侧会话游标和流式中断恢复。
- 验证全局/项目优先级、跨项目移动、项目删除级联、单会话删除不联动记忆。
- 验证 RAG 正文完成后才出现最多 5 个编号来源，单项展开大段切片。
- 验证桌面和手机端、减少动态效果、处理步骤真实持久化、错误/降级显示。
- 验证用户—回答 turn 在实时、历史、刷新和游标分页中顺序稳定；处理步骤无重复 ID、无永久 running、折叠真实有效。
- 验证异步记忆分析不延迟回答和下一次发送；自动保存、重复、纠正、冲突确认、无限条目分批、partial checkpoint、项目快照和重启恢复正确。
- 验证项目/会话平铺侧栏、悬停与键盘菜单、创建弹窗、两种排序、归档视图、会话移动和项目上下文新会话。
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

运行时记忆分类使用独立配置角色，默认模型已通过本次 `ollama list` 核实为 `qwen3.5:9b`；该默认值写入配置或模型注册映射，不写死在业务逻辑中。

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec022 与任务计划 | 本文件 | — | 完成 |
| 02 | 桌面端项目、会话与项目记忆 MVP | [`task-02-desktop-memory-mvp.md`](../plans/022/task-02-desktop-memory-mvp.md) | 01、Spec 确认 | 已完成 |
| 03 | 完整管理、全局记忆与治理界面 | [`task-03-management-global-memory.md`](../plans/022/task-03-management-global-memory.md) | 02 | 已完成 |
| 04 | 异步整理、摘要与跨会话召回 | [`task-04-memory-evolution-recall.md`](../plans/022/task-04-memory-evolution-recall.md) | 03 | 已完成 |
| 05 | 项目文档、RAG、处理过程与桌面缺陷修复轮 | [`task-05-research-context-progress.md`](../plans/022/task-05-research-context-progress.md) | 04、Spec 变更确认 | 已完成（修复轮） |
| 06 | 手机端适配 | [`task-06-mobile-experience.md`](../plans/022/task-06-mobile-experience.md) | 05 | 待执行 |
| 07 | 能力方法记忆与 Skill 改进建议 | [`task-07-capability-memory-proposals.md`](../plans/022/task-07-capability-memory-proposals.md) | 04 | 待执行 |
| 08 | 最终评审、全量回归、部署与复盘 | [`task-08-review-regression-deploy.md`](../plans/022/task-08-review-regression-deploy.md) | 05、06、07 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/022-requirement-review.md`（原轮次已通过；本次变更待补充评审）
- 技术评审：`docs/sdd/reviews/022-tech-review.md`（原轮次已通过；本次变更待补充评审）
- 验收评审：`docs/sdd/reviews/022-acceptance-review.md`（Task05 原轮次与缺陷修复轮均通过；修复轮已由 tester 验收、架构师签字）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 用户 / 架构师（自身） | 通过 Grill with Docs 确认项目—会话—消息—记忆层级、惰性会话、项目隔离、两屏消息分页、处理过程、RAG 编号展开、手机端后置和 MVP 优先交付边界；编号指定为 Spec022 |
| 2026-09-11 | 用户 / 架构师（自身） | Task05 部署后通过 Grilling 完成桌面缺陷修复共同理解：稳定 turn 顺序、真实步骤状态机、异步无限条目记忆分析、9B 默认分类模型、记忆结果确认区和 ChatGPT 式项目/会话侧栏；Spec 退回待确认，业务代码暂停。 |
| 2026-09-11 | 架构师（自身） | Task05 修复轮完成：后端 lease fencing/异步记忆分析、前端稳定 turn/真实处理步骤/折叠与侧栏菜单通过双端复审和跨端验收；主环境部署 smoke 通过，Task06 继续等待。 |
