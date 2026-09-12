# Spec 024 — 可见推理过程与会话级推理档位

## 状态

**当前状态：已完成（环境延期）**

## 一句话目标

让普通会话和项目会话在模型长时间推理时立即给出可理解的实时反馈，并允许用户按会话选择关闭、低、中、高或极高推理档位。

## 背景与问题

- 当前普通会话默认开启推理，qwen3.8:27b 的模板会把未显式指定的推理强度设为 xhigh。
- 2026-09-11 的 task1245 运行日志显示：约 941 个输入 token 的预处理约 7 秒，随后模型生成约 800 个前端不可见的推理 token，用户约 1 分钟后才看到正文首 token。
- 后端当前只把可见正文作为 token 事件发送；模型返回的 reasoning_content 没有进入会话事件协议。
- 前端无法区分“模型仍在思考”“模型无响应”和“连接失败”，形成长时间空白等待。
- 用户仍希望研究型问题默认使用 xhigh，同时需要随时切换到更低档位以换取速度。

## 回滚点与数据清理

- 实施前记录分支、commit、工作树、当前会话数据库 schema 版本和待删除会话/消息数量。
- schema 升级使用一次性事务迁移：删除所有旧会话、消息及其严格依赖的处理步骤、分析任务和临时结果；保留项目、项目记忆、全局记忆、系统规则和个人知识库数据。
- 删除前将 MemoryEvidence 中指向旧会话或消息的引用安全置空，记忆正文继续保留。
- 不保留旧消息格式兼容代码，不长期暴露数据清理入口。
- 迁移失败必须整体回滚；不得执行 git reset、stash、clean，亦不得覆盖用户其他修改。

## 现有实现复用与替换边界

### 必须复用

- 复用 backend/app/chat/application/chat_runner.py 与 chat_graph.py 的唯一聊天编排链路。
- 复用 backend/app/platform/ollama.py 的 LangChain/Ollama 适配器，不在路由旁新增第二套模型客户端。
- 复用 backend/app/api/routes_conversations.py 的持久会话 SSE 入口和稳定错误体。
- 复用 Spec022 的 Conversation、Message、ProcessingStep、项目绑定、SystemRule 和异步记忆分析能力。
- 复用 frontend/app.js 的消息 turn、流式写入和处理过程折叠结构。

### 必须替换或扩展

- 将仅有正文 token 的流协议扩展为推理开始、推理增量、推理结束、正文增量和完成/失败事件。
- 会话保存推理档位；新会话继承用户最近一次选择，之后可独立修改。
- assistant 消息保存经过过滤的可见推理草稿、推理状态和阶段耗时。
- 前端新增紧凑推理档位选择器和独立推理面板，不把推理文本混入回答正文或 ProcessingStep。

### 硬性禁止

- 不把 reasoning_content 写入长期记忆、RAG、embedding、Langfuse 完整 Prompt 或普通日志。
- 不让异步记忆分类继承用户选择的回答推理档位。
- 不静默降低不受支持的档位，不因失败自动换档重试。
- 不复制聊天、队列、模型客户端或记忆分析实现。

## 数据模型

### Conversation 增量

| 字段 | 类型 | 约束 |
|---|---|---|
| reasoning_effort | enum | off / low / medium / high / xhigh；默认 xhigh |

### UserChatPreference

| 字段 | 类型 | 约束 |
|---|---|---|
| owner_id | str | 每个本地用户唯一 |
| last_reasoning_effort | enum | 新会话继承值，初始 xhigh |
| updated_at | UTC datetime | 每次选择变更时更新 |

### Message 增量（仅 assistant）

| 字段 | 类型 | 约束 |
|---|---|---|
| reasoning_content | str/null | 仅保存过滤后的用户可见草稿，最多 20,000 个 Unicode 字符 |
| reasoning_status | enum/null | running / completed / interrupted / failed |
| reasoning_started_at | UTC datetime/null | 收到推理阶段开始时记录 |
| reasoning_completed_at | UTC datetime/null | 进入正文或失败时记录 |
| first_reasoning_at | UTC datetime/null | 首段真实推理内容到达时间 |
| first_answer_token_at | UTC datetime/null | 正文首 token 到达时间 |

- 超过 20,000 字符时保存开头与结尾，并插入明确的省略标记；原始超长内容不得另存。
- 推理关闭时上述推理字段保持 null，不创建空思考记录。

## 端点与事件接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| GET /api/chat/reasoning-options | 当前模型 | 支持档位、默认值、当前模型 | 模型能力不可读取时返回稳定错误 |
| PATCH /api/conversations/{id}/reasoning | reasoning_effort | 更新后的会话档位和用户最近选择 | 400 非法档位；409 模型不支持；404 会话不存在 |
| POST /api/conversations/messages | `{"content":"...","project_id":null,"model":"...","mode":"normal","reasoning_effort":"off|low|medium|high|xhigh"}`；`reasoning_effort` 可省略，`question`/`message` 是既有别名 | `text/event-stream`；首个可写事件必须是 `meta`，包含 `conversation_id`、`user_message_id`、`assistant_message_id`、`model`、`mode`、最终 `reasoning_effort`、`capabilities_source` | 400/404/409/503 统一 error body；能力校验或项目校验失败时不创建空会话、不调用模型 |
| POST /api/conversations/{conversation_id}/messages | 与首条消息相同，`content`/`question`/`message` 至少一个非空 | `text/event-stream`；首个事件同为完整 `meta`，随后按同一 SSE 合同发送 | 会话不存在、能力不支持或输入非法时不产生回答 token |

首条消息和既有会话使用同一流式合同：HTTP 200 建立后，服务端先发送完整 `meta`，再发送 `progress`/`memory`/`reasoning_*`/`token`/`sources`，最终发送 `done`。能力、模型和项目校验发生在会话持久化前；失败使用统一错误体并不建立空会话。`meta` 的 `reasoning_effort` 是本轮冻结值，`capabilities_source` 为 `ollama_probe`、`cache` 或 `unavailable`；其余事件继承相同 `message_id`、`event_seq` 和 `timestamp` envelope。旧请求字段仍按既有优先级解析，但不再形成第二条接口或事件链。

### SSE 事件

| 事件 | 关键字段 | 语义 |
|---|---|---|
| reasoning_started | message_id、effort、started_at | 推理阶段开始 |
| reasoning_delta | message_id、content | 经过过滤的可见推理增量 |
| reasoning_completed | message_id、status、duration_ms | 推理终态；正文开始前必须出现 |
| token | message_id、content | 保留现有正文 token 事件名以减少无关破坏 |
| done | message_id、status、`duration_ms`、`reasoning_duration_ms`、`answer_duration_ms` | 本轮终态；`duration_ms` 为兼容别名，固定等于 `answer_duration_ms` |
| error | message_id、code、message | 稳定失败；不得永久保持动画 |

- 每个 assistant 流生成一个从 1 开始、单调递增的 event_seq；同一 message_id + event_seq 只能出现一次。
- event_seq 是服务端持久化/发送顺序，不使用 content 去重；客户端只接受大于 last_event_seq 的事件，重复或更旧事件丢弃。
- 合法状态：created → reasoning_running → reasoning_completed → answering → completed；failed、interrupted 是终态，终态后任何事件均丢弃。
- off：不发送 reasoning_started、reasoning_delta、reasoning_completed，reasoning_content 和 reasoning_status 保持 null，直接进入 answering。
- reasoning_started 后无有效 delta 仍必须发送 reasoning_completed，status 为 completed 或 failed；正文前断线发送 interrupted。
- error 必须先于 done；done.status 与持久化 Message.status 一致。取消为 interrupted，模型异常为 failed。
- 原有 meta、progress、memory、token、sources、done、error 事件继续兼容；reasoning 事件仅扩展既有唯一会话 SSE。

每个事件共享以下 envelope：{"type":"...","message_id":"...","event_seq":1,"timestamp":"UTC RFC3339",...业务字段...}。`meta` 额外固定带 `project_id`、`conversation_id`、`user_message_id`、`assistant_message_id`、`model`、`mode`、`reasoning_effort`、`capabilities_source`；`progress` 带 `step_id`、`kind`、`label`、`status`、`summary`；`memory` 带 `status`、`memory_id`、`scope`、`project_id`、`statement`（可选 `message`）；`sources` 带 `sources` 和 `citations`；`reasoning_started` 带 `effort`、`started_at`；`reasoning_delta` 带 `content`；`reasoning_completed` 带 `status`、`duration_ms`、`completed_at`；`token` 带 `content`；`done` 带 `status`、`duration_ms`、`reasoning_duration_ms`、`answer_duration_ms`；`error` 带 `code`、`message`、`retryable`。`event_seq` 缺口视为 EVENT_SEQUENCE_GAP 并终止本轮，不尝试猜测或补发。

event_seq 属于单个 assistant message 的全事件流，不只属于 reasoning。服务端只发送连续序号；客户端收到大于 last_event_seq+1 的事件立即停止应用并显示“事件流中断”，等待 done/error，不自行补序。服务端持久化 last_event_seq 和 Message.status；pending/streaming/completed/failed/interrupted 的映射分别为 created/answering、answering、completed、failed、interrupted；reasoning_status 只记录推理子阶段。

- `reasoning_completed.duration_ms` 与 `done.reasoning_duration_ms` 使用服务端 `time.monotonic()` 计算 reasoning_started 到 reasoning_completed；推理未启动时为 null。`done.answer_duration_ms` 使用同一时钟计算本次 SSE 流建立（request stream start）到 done，`done.duration_ms` 是为旧客户端保留的同值别名。UTC 字段只用于展示和审计，不能用于耗时计算。
- off：所有推理时间字段和 `reasoning_duration_ms` 为 null；`done.duration_ms`/`answer_duration_ms` 仍记录整条 SSE 流耗时；正文前失败只有 error → done(failed)。
- started 后无 delta 正常完成：reasoning_completed(completed, duration_ms) → token* → done(completed)。
- started 后模型失败：reasoning_completed(failed, duration_ms) → error(CHAT_FAILED) → done(failed)。
- reasoning_completed(completed) 后首 token 前模型失败：不重复发送 completed，直接 error(CHAT_FAILED) → done(failed)，Message.reasoning_status 保持 completed、Message.status 为 failed。
- 用户取消或客户端断线：若连接仍可写，唯一序列为 `error(STREAM_INTERRUPTED,retryable=true)` → `done(interrupted)`；若连接已关闭，不能补发 SSE，但服务端必须持久化 `Message.status=interrupted`、推理状态和已生成正文。正文开始后断线同样只允许该中止终态；终态后的 token/reasoning/error/done 全部丢弃。
- 模型失败序列固定为 `error(CHAT_FAILED)` → `done(failed)`；`done` 是最后一个逻辑事件，连接关闭时可不可达不改变持久化终态。

- 界面顺序固定为用户消息、思考面板、模型正文。
- 一旦正文首 token 到达，推理阶段必须完成；后续内容不得回写到推理面板。
- 页面刷新不做 token 级断点续传，只读取已持久化的阶段、内容和终态。

## 用户体验

- 输入框附近提供“思考：极高”的紧凑下拉按钮，选项为关闭、低、中、高、极高。
- 默认极高；每个会话独立保存，新会话继承用户上次选择。
- 发送后 500ms 内显示本地状态“模型正在准备”；收到 reasoning_started 后自动展开思考面板。
- reasoning_delta 流式显示经过基础过滤的模型思考草稿，并标注“思考草稿可能不准确”。
- 正文开始时思考面板自动折叠；完成后显示“思考完成 · 用时 X 秒”，用户可重新展开。
- 关闭推理时不显示空面板，只在正文前显示“正在生成回答”。
- 失败、中止或断线时立即停止动画并保留明确终态；部分推理草稿可见但不得标成完成。
- 切换档位只影响下一条及后续消息，不重新生成历史回答。

## 推理内容过滤与隔离

- 丢弃空增量、不可显示控制字符、已知模板角色分隔符和协议标记。
- 保存和展示的都是过滤后内容；不另存原始 reasoning_content。
- 过滤器不得把平台系统消息、用户 SystemRule 或完整 Prompt拼入推理面板。
- 推理草稿不进入记忆分析输入；记忆分析继续使用独立小模型和既有异步流程。
- 观测层只允许记录 reasoning_present、过滤后字符数、阶段耗时和状态；不得记录原始 reasoning 文本、片段或完整 Prompt。

## 能力探测与模型映射

能力接口固定返回 model、supported_efforts、default_effort、source、cached_at 字段，例如：

    {"model":"qwen3.8:27b","supported_efforts":["off","low","medium","high","xhigh"],"default_effort":"xhigh","source":"ollama_probe","cached_at":"UTC RFC3339"}

- GET /api/chat/reasoning-options 的 model 参数来自现有会话模型选择；缺失时使用系统当前模型。Ollama 探测超时 5 秒，结果按 model 缓存 5 分钟；刷新失败返回 503 MODEL_CAPABILITIES_UNAVAILABLE，不伪造支持集合。
- off 映射为显式 think=false。
- low、medium、high 仅在真实探针和当前 adapter 均接受对应字符串时标记支持，并原样发送。
- xhigh 只有在当前模型对显式 `think=true` 返回非空 reasoning、并保存请求/响应 `evidence_id` 时才标记支持；可读取的 Ollama server 日志作为可选审计证据，不再作为唯一硬阻塞。省略 think 不得自动等价于 xhigh；没有响应证据时保持 pending/unavailable。
- 只有 boolean thinking 的模型最多返回 off 与 xhigh（xhigh 必须有证据）；完全不支持 thinking 的模型只返回 off。
- PATCH 或首条消息在创建会话前完成能力校验；不支持时返回 409 REASONING_EFFORT_UNSUPPORTED，不创建空会话、不调用模型。
- LangChain 与 direct 两条已有路径必须运行同一能力探针和映射，不允许一条路径静默丢失 reasoning。

### 能力接口请求与错误体

- 请求为 GET /api/chat/reasoning-options?model=<urlencoded-model>；model 缺失或空白时使用系统当前模型。未知模型返回 404，探针失败返回 503。
- 成功响应为上述 JSON；PATCH /api/conversations/{id}/reasoning 的请求为 {"reasoning_effort":"off|low|medium|high|xhigh"}，响应为 {"conversation_id":"...","reasoning_effort":"...","last_reasoning_effort":"...","updated_at":"UTC RFC3339"}。值未变化时 `updated_at` 保持原值，值变化时与 preference 更新事务使用同一时间戳。
- 首条消息可带可选 reasoning_effort；优先级为本次显式值、会话已保存值、UserChatPreference.last_reasoning_effort、xhigh。能力校验在创建会话前完成。
- 所有失败均使用 {"error":{"code":"...","message":"...","retryable":true|false}}：400 INVALID_REASONING_EFFORT、404 MODEL_NOT_FOUND 或 CONVERSATION_NOT_FOUND、409 REASONING_EFFORT_UNSUPPORTED、503 MODEL_CAPABILITIES_UNAVAILABLE。409/400 均不调用模型；首条消息失败不创建空会话。

### 五档解析合同

内部解析函数接收 ReasoningEffort 与 model，返回 requested_effort、provider_value、route_payload、evidence_id；LangChain 与 direct 必须消费同一解析结果。xhigh 的 provider_value 为 true，只有在探针响应返回非空 reasoning 并保存 evidence_id 时才支持；server 日志可作为补充审计证据。其余档位必须原样传递字符串并由探针证明。没有响应证据的档位为 unsupported/pending，不得省略字段或静默改成 true。

| requested_effort | provider_value | request body field | response evidence |
|---|---|---|---|
| off | false | think=false | 无 message.thinking；只允许 token |
| low | "low" | think="low" | message.thinking 或模型拒绝 |
| medium | "medium" | think="medium" | message.thinking 或模型拒绝 |
| high | "high" | think="high" | message.thinking 或模型拒绝 |
| xhigh | true | think=true | 必须有非空 message.thinking 与 evidence_id；server 日志为可选审计证据 |

Task02 逐模型填充 support、HTTP 状态、响应字段和 evidence_id；未完成探针前不把任何待测档位写成已支持。

## 历史消息返回合同

GET /api/conversations/{id}/messages 的 assistant 消息额外返回 reasoning_content、reasoning_status、reasoning_started_at、reasoning_completed_at、first_reasoning_at、first_answer_token_at、reasoning_truncated、reasoning_chars 字段。

- 时间字段为 UTC RFC3339 或 null；reasoning_status 只能是 running、completed、interrupted、failed 或 null。
- off 或旧消息返回 null、false、0，不渲染空面板；历史终态只读，不重新播放动画。

## 一次性旧会话清理矩阵

schema 从 6 升至 7，并写入一次性 migration marker conversation_history_reset_v1。迁移只执行一次，失败整体回滚，应用重启不得重复删除。

| 表 | 动作 | 依据 |
|---|---|---|
| conversations | 物理删除 active、archived、deleted 全部旧会话 | 不兼容旧消息 |
| messages | 物理删除全部旧消息 | 严格依赖 conversations |
| processing_steps | 物理删除 | 依赖旧 message |
| raw_events | 物理删除 | 依赖旧 conversation |
| conversation_summaries | 物理删除 | 依赖旧 conversation；不等同于 Spec025 压缩 |
| evolution_checkpoints | 物理删除 | 依赖旧 conversation |
| memory_analysis_jobs | 物理删除 | 依赖旧 user message |
| memory_analysis_items | 物理删除；已落库 MemoryRecord 不删除 | 依赖旧 analysis job |
| memory_evidence | 保留正文；conversation_id、message_id 置 null | 长期记忆继续保留 |
| projects | 保留 | 不属于旧会话 |
| memories | 保留 | 用户明确要求保留 |
| system_rules | 保留 | 最高优先级规则 |
| skill_improvement_proposals | 保留；来源引用为空则保持 proposal | 不属于旧会话 |
| UserChatPreference | 保留；不存在则以 xhigh 初始化 | 跨会话最近选择 |
| 论文、知识库、Task ledger 数据库 | 不触碰 | 独立数据域 |

迁移前后必须记录每张表行数和数据库备份标识；临时数据库注入中途失败后所有行数和 schema_version 必须恢复原值。

### schema v7 DDL 与执行顺序

- 新增 migration_markers(marker TEXT PRIMARY KEY, applied_at TEXT NOT NULL, before_counts_json TEXT NOT NULL, backup_id TEXT NOT NULL)。
- 新增 user_chat_preferences(owner_id TEXT PRIMARY KEY, last_reasoning_effort TEXT NOT NULL DEFAULT 'xhigh' CHECK(last_reasoning_effort IN ('off','low','medium','high','xhigh')), updated_at TEXT NOT NULL)。
- conversations 增加 reasoning_effort TEXT NOT NULL DEFAULT 'xhigh' 并使用同一 CHECK；messages 增加 reasoning_content TEXT、reasoning_status TEXT、reasoning_started_at TEXT、reasoning_completed_at TEXT、first_reasoning_at TEXT、first_answer_token_at TEXT、reasoning_truncated INTEGER NOT NULL DEFAULT 0、reasoning_chars INTEGER NOT NULL DEFAULT 0、last_event_seq INTEGER NOT NULL DEFAULT 0。
- v7 迁移顺序固定为：BEGIN IMMEDIATE → 读取并校验 schema=6 → 创建 marker/preference → 为 conversations/messages 增列并校验 → 生成 backup_id 与 before_counts_json → 按矩阵删除/置空 → 写 marker → 写 schema_version=7 → COMMIT。任一步失败 ROLLBACK，marker 和 schema_version 不得改变。
- backup_id 是迁移前 SQLite backup API 生成的文件摘要；before_counts_json 必须包含矩阵中每张表的行数。真实库执行前只允许在备份存在且计数已落盘时继续。

### UserChatPreference 并发与优先级

- owner_id 是主键，缺失记录在同一事务中插入 xhigh；显式首条消息值优先于会话值，PATCH 与消息发送同时发生时以消息请求冻结值为本轮值，PATCH 只更新下一轮和 last_reasoning_effort。
- updated_at 只有值实际变化时更新；PATCH 返回 conversation_id、reasoning_effort、last_reasoning_effort 和 updated_at。

## 边界与失败场景

- 模型不支持思考、只支持开关但不支持细分档位、能力读取失败。
- 用户在生成期间切换档位；当前轮使用发送时冻结值，下一轮使用新值。
- 推理只有空白或模板标记；面板可显示运行状态，但不得伪造具体内容。
- reasoning_started 后直接失败、正文首 token 前断线、正文开始后连接中断。
- 重复或乱序事件不得重复追加内容或让终态回到 running。
- 过滤器固定丢弃 ASCII/C1 控制字符（保留换行、制表）、<think>、</think>、<|im_start|>、<|im_end|>、[INST]、[/INST]、system/user/assistant 角色分隔符和协议标记；跨 chunk 用最长标记前缀状态保留。
- 输入先做 NFC 规范化，再按 Python Unicode code point 计数。超过 20,000 时使用省略标记“[…中间思考已省略…]”，首尾平均保留，最终 code point 数不超过 20,000；过滤后为空则只显示运行状态。
- 20,000 字符截断必须按 Unicode 字符处理，不能产生乱码。
- 旧会话清理必须保留项目、长期记忆、SystemRule 和知识库。

## 明确不做

- 不切换 MLX、默认模型或 Ollama 部署方式。
- 不实现模型自动装卸、显存调度或并发资源治理。
- 不修改知识库 RAG 问答界面。
- 不实现会话上下文压缩、历史摘要替换或 token 预算管理；该缺陷登记为 Spec025。
- 不让推理内容进入长期记忆或 RAG。
- 不做跨刷新 token 级断点续传。
- 不重写现有项目、会话和记忆体系。

## 验收方式

- 自动测试验证五档参数、模型能力校验、事件顺序、状态终结、20,000 字符边界、推理隔离和一次性清理事务，不对真实模型耗时写硬断言。
- 普通会话与项目会话必须呈现相同行为；历史数据清理后不保留旧会话空壳。
- xhigh、low 和 off 各完成一次真实 Ollama smoke；off 不产生推理正文，low 与 xhigh 的实际耗时只记录不比较固定比例。
- 在 Ollama 模型已预热且服务健康的固定问题下，xhigh 最迟 20 秒内出现第一段真实推理内容。冷启动、模型未加载或 Ollama 正忙须单独记录环境，不直接判实现失败。
- 刷新后能读取已保存的推理内容；失败、中止和断线不会永久显示动画。
- 最终收口时运行一次全量回归；各开发 Task 只运行本 Task 相关测试。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

1. 打开普通新会话，读取当前模型可用档位，选择 low、xhigh 或 off。
2. 发送固定问题“请用三点解释什么是向量数据库”；500ms 内出现准备状态，收到有效 reasoning_delta 后面板展开，正文首 token 后自动折叠。
3. 进入绑定项目会话，重复同一问题，确认使用同一 SSE 事件和面板行为。
4. 生成期间切换档位；本轮事件中的 effort 保持发送时快照，下一轮使用新档位。
5. 刷新并重新打开历史会话，确认能展开已保存的过滤草稿、状态和耗时。
6. 分别覆盖 off、模型失败、用户中止、连接断线和无有效 delta，确认无永久动画。

验收观察点：能力接口 JSON、SSE event_seq 偏序、assistant message 字段、reasoning_status 终态、Langfuse metadata 无 reasoning 文本、记忆分析 worker 输入无 reasoning 片段。

## 执行配置

> 2026-09-11 已通过局域网地址实际运行 ollama list，确认 qwen3.8:27b-mlx 与 qwen3.5:9b 可用。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Spec、边界、技术裁决与集成 |
| 产品经理 | qwen3.5:9b | 32k | doc-updater | 产品步骤与验收场景 |
| 开发主管 | qwen3.8:27b-mlx | 32k | architect | 需求/技术评审与合并裁决 |
| 后端开发 | qwen3.8:27b-mlx | 32k | backend-dev | schema、能力接口、流事件和持久化 |
| 前端开发 | qwen3.8:27b-mlx | 32k | frontend-dev | 档位选择、推理面板和状态机 |
| 后端评审 | qwen3.8:27b-mlx | 32k | backend-reviewer | 后端边界与迁移评审 |
| 前端评审 | qwen3.8:27b-mlx | 32k | frontend-reviewer | DOM、流事件、可访问性和 XSS 评审 |
| 后端回归 | qwen3.5:9b | 32k | backend-tester | 后端定向与最终回归 |
| 前端回归 | qwen3.5:9b | 32k | frontend-tester | 前端合同与浏览器检查 |
| 测试总控 | qwen3.5:9b | 32k | tester | 跨端验收与最终全量回归汇总 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec 024 | 本文件 | — | 完成 |
| 02 | 冻结能力、数据清理与事件协议 | [Task 02](../plans/024/task-02-reasoning-protocol-and-migration.md) | 01、Spec 确认 | 已完成（条件 GO） |
| 03 | 实现后端推理流与持久化 | [Task 03](../plans/024/task-03-backend-reasoning-stream.md) | 02 条件 GO、报告齐全 | 已完成（条件通过） |
| 04 | 实现前端档位与推理面板 | [Task 04](../plans/024/task-04-frontend-reasoning-panel.md) | 03 实现/测试/评审报告 | 已完成（定向通过） |
| 05 | 评审、全量回归、部署与复盘 | [Task 05](../plans/024/task-05-review-regression-deploy.md) | 02、03、04 评审报告 | 已完成（环境延期） |

## 评审记录

- 需求评审：docs/sdd/reviews/024-requirement-review.md（通过：最终复审 P0/P1/P2=0）
- 技术评审：docs/sdd/reviews/024-tech-review.md（通过：P0/P1=0；Task02 仍需真实运行时证据）
- 验收评审：docs/sdd/reviews/024-acceptance-review.md（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-11 | 架构师（自身） | 根据 Grilling 共同理解建立 Spec；默认 xhigh、支持五档、可见推理流、删除旧会话，并将上下文压缩拆至 Spec025。 |
| 2026-09-11 | 架构师（自身） | 需求/技术评审打回后补充产品旅程、能力映射、event_seq 状态机、历史字段、schema v7 清理矩阵、LangChain/direct 一致性和观测隔离合同，等待复审。 |
| 2026-09-12 | 架构师（自身） | 补齐首条消息双路径请求/响应、首个 meta、SSE 逐事件字段、耗时别名、取消/断线终态和 PATCH updated_at 合同；需求与技术复审均通过。用户明确要求 pull 后继续开发，Spec024 转为实施中并启动 Task02 门禁。 |
| 2026-09-12 | 架构师（自身） | 合同登记修订：用户报出三个可见缺陷（发送后无卡片、不支持档位仍能选并报 409、错误一律显示「连接失败」），移交 Spec 026 修复。024 仅在本表登记一条口径变更——§能力接口请求与错误体中「探针失败返回 503」被 026 修订为「返回 200 且 source 为 stale/unknown」；024 其余合同（五档取值、SSE 协议、409/400/404 语义、不静默降级用户显式选择）全部保持不变。 |
