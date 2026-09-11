# Task 02：冻结推理能力、数据清理与事件协议

> 关联：[Spec 024](../../specs/024-visible-reasoning-controls.md) ｜ 索引：[README](./README.md)
> 依赖：Spec024 用户确认、需求/技术复审通过；被依赖：Task03、Task04；当前状态：已完成（条件 GO）

## 一句话目标

在不写业务实现的前提下，用真实局域网 Ollama 与临时数据库验证五档推理可行性，并把一次性清理、schema v7、历史字段和带 event_seq 的 SSE 状态机冻结成可测试合同。

## 当前证据

- 2026-09-11 已通过局域网 Ollama 实测确认 qwen3.8:27b-mlx、qwen3.8:27b 与 qwen3.5:9b 存在。
- task1245 日志显示默认 xhigh 推理约产生 800 个不可见 token 后才出现正文。
- backend/app/chat/application/chat_graph.py 当前只读取正文 content。
- backend/app/platform/ollama.py 已有 reasoning 参数接缝，应扩展而非新增客户端。
- Spec022 数据库包含项目、会话、消息、处理步骤、记忆分析和记忆证据；清理旧会话时必须保留项目和长期记忆。
- 当前派生表还包括 raw_events、conversation_summaries、evolution_checkpoints、skill_improvement_proposals 和 system_rules；必须逐表输出删除/保留/置空矩阵。
- 当前观测 backend/app/platform/observability/spans.py 会写入 thinking，必须在 Task03 前冻结为不含原始 reasoning 的指标合同。

## 前置门禁

- Spec024 状态已转为已确认。
- 记录当前 commit、工作树、数据库 schema 版本及各相关表行数。
- 数据探针只能操作临时数据库；不得在本 Task 删除真实用户会话。

## 思维链（执行阶段、观察点与决策依据）

1. 读取现有模型适配器和会话 schema，列出可复用接缝。
2. 对真实 Ollama 逐档发送最小请求，记录 off、low、medium、high、xhigh 的接受情况和响应字段。
3. 在临时数据库演练旧会话清理，核对保留表行数与引用置空。
4. 用合同测试冻结事件偏序、event_seq 去重、乱序丢弃和终态不可逆。
5. 演练一次性清理矩阵及中途失败回滚。
6. provider 层档位无法表达，或清理会删除长期数据时给出 NO-GO；仅因应用接缝尚未实现或 xhigh 受证据环境限制时，记录条件 GO 与后续门槛，不阻塞 Task03。

## 冻结合同

### 能力探针

- 按 model 分别探测 qwen3.8:27b-mlx、qwen3.8:27b 和当前系统默认模型。
- 每档记录脱敏请求值、HTTP 状态、响应字段和 LangChain/direct 路径。
- off 使用 think=false；low/medium/high 只有 provider 与 adapter 同时接受字符串才标记支持；xhigh 只有显式 think=true 被模型模板实测解释为 xhigh 才标记支持。
- 报告固定返回 model、supported_efforts、default_effort、source、cached_at；能力读取失败为 MODEL_CAPABILITIES_UNAVAILABLE。
- 固定请求为 GET /api/chat/reasoning-options?model=<urlencoded-model>；统一错误 JSON 为 error.code、error.message、error.retryable。逐档报告必须包含 provider_value、route_payload、response_field、evidence_id。
- LangChain/direct 的统一 adapter 方法签名为 resolve_reasoning_effort(model, requested_effort, route) -> requested_effort/provider_value/route_payload/evidence_id；chat_graph 的 chunk extraction 需明确从 additional_kwargs.reasoning_content 或等价字段生成 thinking 事件。
- 固定五档矩阵：off→think=false；low/medium/high→think 为同名字符串；xhigh→think=true 且必须有非空 message.thinking 与 evidence_id，server 日志为可选审计证据。未知/未探明值统一 unsupported/pending。

### 迁移矩阵与事务

schema_version 6 → 7，marker 为 conversation_history_reset_v1。删除 conversations、messages、processing_steps、raw_events、conversation_summaries、evolution_checkpoints、memory_analysis_jobs、memory_analysis_items；保留 projects、memories、system_rules、skill_improvement_proposals、UserChatPreference、知识库和论文库；memory_evidence 保留正文并将旧会话/消息引用置 null。全表按外键顺序执行，记录迁移前后行数和备份标识；注入异常后 schema 与所有计数恢复。
- marker 存入 migration_markers(marker PRIMARY KEY, applied_at, before_counts_json, backup_id)；UserChatPreference 为 owner_id PRIMARY KEY、last_reasoning_effort CHECK、updated_at；conversations/messages 新增推理列和 last_event_seq。执行顺序与回滚断言必须按 Spec024 的 schema v7 合同逐项记录。
- 证据表固定列为 table_name、before_count、after_count、action、foreign_key_result；backup_id 为 SQLite backup API 生成的摘要。测试必须在每个删除阶段注入一次异常，断言 marker、schema_version、所有表计数和 preference DDL 完整恢复。

### SSE 与历史字段

- 每条事件带 message_id、event_seq、UTC RFC3339 timestamp；同一 message_id + event_seq 幂等，所有 meta/progress/memory/sources 也带 envelope。
- 首条消息固定走 `POST /api/conversations/messages`，既有会话固定走 `POST /api/conversations/{conversation_id}/messages`；请求允许 `content`、既有别名 `question`/`message`、`project_id`、`model`、`mode` 和可选 `reasoning_effort`。两条路径建立 HTTP 200 SSE 后，首个事件必须是完整 `meta`：`project_id`、`conversation_id`、`user_message_id`、`assistant_message_id`、`model`、`mode`、`reasoning_effort`、`capabilities_source`。能力/项目校验失败在创建会话前返回统一 `error` body，不创建空会话。
- 状态只允许 created → reasoning_running → reasoning_completed → answering → completed，或 failed/interrupted 终止；终态后事件丢弃。
- event_seq 缺口、重复和旧序号的处理规则固定；GET 历史消息返回六个推理字段、reasoning_truncated 和 reasoning_chars。
- `reasoning_completed.duration_ms` 和 `done.reasoning_duration_ms` 是 reasoning_started→reasoning_completed；`done.answer_duration_ms` 是本次 SSE stream start→done；`done.duration_ms` 必须作为兼容别名等于 `answer_duration_ms`，推理未启动时 reasoning 时长为 null。started 后失败、completed 后首 token 前失败、取消/断线的唯一序列必须落盘。
- 既有字段冻结为：meta（project_id/conversation_id/user_message_id/assistant_message_id/model/mode/reasoning_effort/capabilities_source）、progress（step_id/kind/label/status/summary）、memory（status/memory_id/scope/project_id/statement，可选 message）、sources（sources/citations）、token（content）、error（code/message/retryable）、done（status/duration_ms/reasoning_duration_ms/answer_duration_ms）。
- 逐事件 JSON 样本必须覆盖 started、delta、completed、token、done、error、meta、progress、memory、sources，并包含 message_id、event_seq、timestamp；event_seq 缺口以 EVENT_SEQUENCE_GAP 终止。
- 取消/断线若连接可写，序列固定为 `error(STREAM_INTERRUPTED,retryable=true)`→`done(interrupted)`；若已不可写，只持久化 interrupted。模型异常固定为 `error(CHAT_FAILED)`→`done(failed)`；done 为最后逻辑事件，终态后事件全部丢弃。

### 隔离

LangChain/direct 都必须输出 thinking 事件；fake worker 捕获记忆分析输入、raw_events、RAG/embedding 参数和 observability metadata，断言不含原始 reasoning 片段，只含存在标志、过滤后字符数和耗时。
- observability metadata allowlist 固定为 model、route、reasoning_present、reasoning_chars、reasoning_status、reasoning_duration_ms、answer_duration_ms 和稳定错误码；logger 捕获范围覆盖 backend.app.platform.observability 与会话路由 handler。

## 子任务与子 Agent

- architect：只读调研、协议冻结、Go/No-Go。
- backend-tester：运行真实能力探针和临时数据库迁移测试。
- 不分派 backend-dev；本 Task 不写业务代码。

## 完整分派 Prompt

~~~text
角色：architect，使用 Spec024 执行配置中的开发主管模型。
目标：验证并冻结 Spec024 的推理能力、数据清理和 SSE 合同，不实现业务代码。
只需读取：
1. docs/sdd/specs/024-visible-reasoning-controls.md
2. docs/sdd/plans/024/task-02-reasoning-protocol-and-migration.md
3. backend/app/platform/ollama.py
4. backend/app/chat/application/chat_graph.py
5. backend/app/chat/application/chat_runner.py
6. backend/app/api/routes_conversations.py
7. 当前会话/记忆 repository 与迁移定义
8. backend/app/platform/ollama_direct.py
9. backend/app/platform/observability/spans.py
允许修改：
- docs/sdd/plans/024/artifacts/task-02/protocol-report.md
- tests/test_spec024_protocol.py（仅本 Task 新增/修改）
禁止：
- 修改 backend/app 或 frontend 业务代码
- 删除真实数据库数据
- 修改 Ollama 部署、模型或 .env
- reset、stash、clean、push、合并 main
完成后的可观察状态：
- 五档能力矩阵有真实请求证据
- 清理保留矩阵有临时数据库证据
- schema 与事件合同无歧义
- 给出 GO 或 NO-GO
必须验证：
- 对局域网 Ollama 的最小五档探针
- 临时数据库迁移/回滚探针
- 重复/乱序 event_seq 与终态回退探针
- LangChain/direct 双路径和观测隔离探针
- 固定跨 chunk 过滤向量、Unicode NFC/code point 截断向量
- git diff --check
结果写入：
docs/sdd/plans/024/artifacts/task-02/protocol-report.md
固定返回字段：
结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
信息不足时标记阻塞，不得自行扩展设计。
~~~

## 主 Agent 校验

- 读回报告和实际 diff，确认没有业务代码改动。
- 重跑最小模型能力探针，核对真实响应字段而非仅看模型声明。
- 在临时数据库核对项目、记忆、SystemRule、知识库均未被清理。
- 确认事件合同兼容现有 token/done/error，不建立第二条流式链路。
- 确认报告列出 raw_events、conversation_summaries、evolution_checkpoints、memory_analysis_*、skill_improvement_proposals 的动作。

## 实时监控

- 线上子 Agent 正常运行时只等待其主动返回。
- 真实 Ollama 探针可观察服务日志，但不得持续轮询；超时后只读取一次相关时间段。

## 验收标准

- 五档中每档的支持/不支持均有真实证据；不支持时定义 409 且模型未被调用。
- 清理合同明确列出当前所有派生表的删除、置空和保留动作、schema v7、marker 和执行顺序。
- 临时迁移中任一步失败会事务回滚。
- 事件顺序、event_seq 去重、终态不可逆和关闭推理行为可写成自动测试。
- Langfuse、普通日志和记忆分析输入只包含推理存在标志、字符数、耗时和状态，不包含原始文本。

## 风险、停止条件与回滚

- provider 层 low/medium/high 可行性已确认；单模型拒绝的档位按模型级 unsupported。xhigh 无 server-log 证据时保持 pending-evidence，不标记 supported/default。
- 现有外键无法在保留 MemoryRecord 的同时删除会话：NO-GO，先调整清理设计。
- 本 Task 仅新增文档/合同测试，回滚为撤销本 Task 文件，不触碰用户数据。

## 产出物

- artifacts/task-02/protocol-report.md

## 执行结果

条件 GO。真实局域网探针、临时 SQLite v7 清理/8 阶段回滚、event_seq/过滤参考测试均完成；xhigh 仍为 pending-evidence，`qwen3.8:27b` 的 high 为模型级 unsupported。报告见 `artifacts/task-02/protocol-report.md`，定向测试 13 passed + 2 passed。

## 变更日志

- 2026-09-11：根据共同理解创建 Go/No-Go 协议任务。
