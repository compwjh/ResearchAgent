# Spec 024 最终技术复审：可见推理过程与会话级推理档位

## 评审结论

**GO（最终复审通过，允许用户确认 Spec 后进入 Task02）。**

本轮为前两轮 NO-GO 后的最终技术复审。复审只读检查了修订后的 Spec024、plans/024 README、Task02–05、Spec025 占位、现有实现接缝及工作树范围；未修改业务代码、未执行真实数据库迁移、未调用真实 Ollama、未启动服务，未执行 reset/stash/clean/push。此前 P0/P1 阻塞点均已在当前合同中闭合；Task02 仍必须先用真实 Ollama 与临时数据库产生 protocol-report，Task03 不得越过该依赖直接启动。

## 复审范围、实际章节与代码路径

### 规范与计划

- `docs/sdd/specs/024-visible-reasoning-controls.md`：端点/SSE/event envelope（「端点与事件接口」90–122）；过滤、隔离与观测（135–141）；能力探测、五档映射、xhigh 证据（143–176）；历史消息（178–183）；一次性清理矩阵、schema v7、marker、偏好并发（185–220）；过滤向量/Unicode 边界（226–233）；产品验收观察点与 Task 依赖（252–303）。
- `docs/sdd/plans/024/README.md`：M1–M4、Task 依赖及统一执行规则。
- `docs/sdd/plans/024/task-02-reasoning-protocol-and-migration.md`：冻结合同、真实探针、临时迁移/回滚、事件样本、隔离断言及测试白名单。
- `docs/sdd/plans/024/task-03-backend-reasoning-stream.md`：后端实现边界、双路径、过滤向量、观测 allowlist 和后端测试白名单。
- `docs/sdd/plans/024/task-04-frontend-reasoning-panel.md`：前端 event_seq 消费、终态、DOM/XSS/资源版本及前端测试白名单。
- `docs/sdd/plans/024/task-05-review-regression-deploy.md`：最终回归、部署 smoke、故障 fixture 和报告依赖。
- `docs/sdd/specs/025-conversation-context-compaction.md`：仍为“待确认/占位待调研”，无 `docs/sdd/plans/025/`，未成为 Spec024 依赖。

### 实现接缝（实施前基线）

- `backend/app/platform/ollama.py:35-55`：当前 LangChain 创建接缝仍为布尔 `reasoning`；Task03 必须接入统一 effort resolver。
- `backend/app/platform/ollama_direct.py:50-84,116-132`：当前 direct payload 使用布尔 `think`，并从 `message.thinking` 产出 thinking 事件；Task03 必须改为消费 resolver 的 route payload。
- `backend/app/chat/application/chat_runner.py:67-155`：当前两条路径仍按布尔值分支；合同已冻结统一解析结果和双路径一致性。
- `backend/app/chat/application/chat_graph.py:8-19`：当前只读 `chunk.content`；Task03 合同已明确补充 LangChain reasoning 字段 extraction，并与 direct 事件形状统一。
- `backend/app/api/common.py:322-324`：当前 `stream_event` 无 envelope/序号；Task03 需扩展既有唯一 SSE 序列化入口。
- `backend/app/api/routes_conversations.py:182-347`：当前流仅有既有 meta/progress/memory/token/sources/done/error；Task03 需在该唯一会话流加入 reasoning 事件和状态/序号持久化。
- `backend/app/api/schemas.py:25-41`：当前消息/会话请求尚无 reasoning 字段；Task03 需按 Spec 端点合同扩展。
- `backend/app/memory/repository.py:38,118-191,207-245,257-319,393-426`：当前 schema 基线为 v6，既有表和 FK 形状已作为 v7 迁移依据。
- `backend/app/memory/models.py:20-47`：当前 Conversation/Message 尚无新增推理字段；Task03 需与 DDL、历史返回合同同步。
- `backend/app/platform/observability/spans.py:97-129,132-225`：当前 metadata 仍含旧 `thinking` 和宽字段；Task03 合同已冻结 allowlist 并要求移除原始 reasoning。
- `frontend/app.js:1451-1505`：当前前端按既有事件处理，尚无 reasoning panel/`last_event_seq`；Task04 已冻结新增范围。

## 逐项复审结论

### 1. 五档、xhigh 与 LangChain/direct 双路径：已闭合

- Spec024 固定 `off/low/medium/high/xhigh`，并明确 `off → think=false`、低中高以同名字符串原样传递、xhigh 仅在显式 `think=true` 有模型模板解释证据时支持（Spec024:149–155、164–176）。
- 统一 resolver 签名已冻结为 `resolve_reasoning_effort(model, requested_effort, route) -> requested_effort/provider_value/route_payload/evidence_id`；LangChain/direct 必须消费同一解析结果（Spec024:166；Task02:43–45）。
- xhigh 的证据格式已固定为同时具备 `message.thinking`、server 日志中的 `xhigh` 和 `evidence_id`；逐档报告还必须记录脱敏请求值、HTTP 状态、响应字段、路由和 `provider_value/route_payload/response_field/evidence_id`（Spec024:166–176；Task02:39–45）。
- 能力接口请求、缓存、未知模型 404、探针失败 503、未支持档位 409 及“创建会话/调用模型前校验”均已冻结（Spec024:145–162）。
- LangChain 的 reasoning extraction 来源要求已落到 `additional_kwargs.reasoning_content` 或实际等价字段，并要求与 direct 的 `message.thinking` 输出同一 thinking 事件形状；Task02 的真实探针/响应字段报告是 Task03 的前置证据。

结论：协议层闭合；真实支持集合仍按设计留给 Task02 探针，不得在探针前宣称任何待测档位支持。

### 2. schema v7、marker、偏好 DDL、FK/计数/备份/回滚：已闭合

- marker 表、主键及列已明确：`migration_markers(marker TEXT PRIMARY KEY, applied_at TEXT NOT NULL, before_counts_json TEXT NOT NULL, backup_id TEXT NOT NULL)`。
- UserChatPreference DDL 已明确：`user_chat_preferences(owner_id TEXT PRIMARY KEY, last_reasoning_effort TEXT NOT NULL DEFAULT 'xhigh' CHECK(...), updated_at TEXT NOT NULL)`；缺失记录同一事务初始化为 xhigh，值不变时不更新时间。
- conversations/messages 新列及 CHECK、推理字段、`reasoning_truncated`、`reasoning_chars`、`last_event_seq` 均已列明。
- 事务顺序已固定：`BEGIN IMMEDIATE → 校验 schema=6 → 创建 marker/preference → 增列并校验 → SQLite backup API 生成 backup_id 与 before_counts_json → 按清理矩阵执行删除/置空 → 写 marker → schema_version=7 → COMMIT`；任一步失败 `ROLLBACK`，marker/schema/counts/preference DDL 恢复。
- 清理矩阵逐表覆盖 conversations、messages、processing_steps、raw_events、conversation_summaries、evolution_checkpoints、memory_analysis_jobs/items、memory_evidence、projects、memories、system_rules、skill_improvement_proposals、UserChatPreference，以及论文/知识库/Task ledger 独立库。
- Task02 进一步固定证据表列 `table_name/before_count/after_count/action/foreign_key_result`，并要求每个删除阶段注入异常，断言 marker、schema_version、所有计数和偏好 DDL 完整回滚（Spec024:185–215；Task02:47–51）。

结论：不再存在“marker 存放位置、Preference DDL、顺序、计数/备份载体或回滚断言”缺口。真实库仍禁止在 Task02 临时库证据和备份落盘前执行。

### 3. 逐事件 JSON、event_seq 缺口/重复/终态映射：已闭合

- 所有既有事件和 reasoning 事件共用 envelope：`type/message_id/event_seq/timestamp(UTC RFC3339)/业务字段`；reasoning_started/delta/completed、token、done、error 的附加字段均已列明，meta/progress/memory/sources 也强制携带 envelope（Spec024:90–109；Task02:53–59）。
- `event_seq` 作用域已明确为单个 assistant message 的全事件流，从 1 开始连续递增；服务端持久化/发送顺序唯一，同一 `message_id + event_seq` 不重复，不以 content 去重。
- 重复/旧序号丢弃；收到大于 `last_event_seq+1` 的缺口即 `EVENT_SEQUENCE_GAP`、终止本轮，不自行补序；终态后所有事件丢弃。Task02 要求逐事件 JSON 样本覆盖 started/delta/completed/token/done/error/meta/progress/memory/sources 及缺口终止场景。
- 状态映射已冻结：协议 `created/reasoning_running/reasoning_completed/answering/completed/failed/interrupted` 与持久 `Message.status` 的 `pending/streaming/completed/failed/interrupted` 映射明确；`reasoning_status` 仅记录推理子阶段。
- 失败/断线序列已给出：started 无 delta 正常完成、started 后模型失败、reasoning_completed 后首 token 前失败、正文开始后断线；`error` 先于 `done`，`done.status` 与持久状态一致。

结论：逐事件字段、序号作用域、缺口/重复/旧序号、状态映射和终态不可逆均可直接写成合同测试。

### 4. 过滤向量与 Unicode 算法：已闭合

- 固定丢弃 ASCII/C1 控制字符（保留换行、制表）、`<think>`、`</think>`、`<|im_start|>`、`<|im_end|>`、`[INST]`、`[/INST]`、system/user/assistant 角色分隔符和协议标记；跨 chunk 保留最长标记前缀（Spec024:226–233）。
- 输入先 NFC 规范化，再按 Python Unicode code point 计数；超 20,000 使用 `[…中间思考已省略…]`，首尾平均保留且最终 code point 不超过 20,000；过滤后为空只显示运行状态。
- Task03 已固定跨 chunk 向量 `abc<|im_` + `start|>def`、emoji/组合字符及 20,001 code point 向量，要求无协议标记、无乱码、长度上限满足（Task03:26–33）。

结论：字符集合、跨 chunk 行为、规范化、计数单位、截断标记和边界向量均已冻结。

### 5. 阶段时钟真值：已闭合

- `duration_ms` 使用服务端 `time.monotonic()`；推理时长为 reasoning_started 到 reasoning_completed，回答时长为 reasoning_completed（或 request start）到 done；UTC 字段只用于展示/审计（Spec024:113）。
- off 的推理时间字段和 duration 为 null；空 delta、started 后失败、completed 后首 token 前失败、正文后断线分别有明确事件序列和持久化终态（Spec024:114–118）。
- Task02/Task05 均要求把阶段时间点和事件序列落盘，且不对真实模型耗时做错误的固定比例假设。

结论：不再由实现者自行选择墙钟/UTC 差值或 off/失败真值。

### 6. 测试白名单与任务边界：已闭合

- Task02 仅允许 `tests/test_spec024_protocol.py` 新增/修改，并仅落盘 `artifacts/task-02/protocol-report.md`；不改 backend/frontend、不删真实库。
- Task03 仅允许后端既有会话/模型/观测接缝及 `tests/test_spec024_backend.py` 的 Spec024 后端定向测试；列出的既有测试均为运行白名单，不是任意修改范围。
- Task04 仅允许 `frontend/index.html/app.js/styles.css`、`tests/test_spec024_frontend_contract.py`、`tests/test_spec024_frontend.js` 和固定报告；不改 backend、不猜测/重排 event_seq。
- Task05 仅修改三份评审/验收/复盘产物，负责唯一一次全量回归、部署和运行时 smoke。

结论：各角色的修改边界、可运行测试与报告产出可审计，未发现跨端或测试污染的 P0/P1 缺口。

### 7. observability allowlist 与 LangChain/direct extraction：已闭合

- 观测 allowlist 已固定为：`model`、`route`、`reasoning_present`、`reasoning_chars`、`reasoning_status`、`reasoning_duration_ms`、`answer_duration_ms` 和稳定错误码；原始 reasoning 文本、片段、完整 Prompt 不得进入 Langfuse、普通日志、RAG/embedding 或 memory worker（Spec024:135–141；Task02:61–64；Task03:104–109）。
- logger 捕获范围覆盖 `backend.app.platform.observability` 与会话路由 handler；Task02/Task03 将“捕获任何原始 reasoning 片段”定义为失败。
- LangChain 图从 reasoning 字段 extraction 产出 thinking 事件，direct 从 `message.thinking` 产出同形事件；两路共用 effort resolver、能力探针和隔离断言，不允许一条路径静默丢 reasoning。

结论：观测字段白名单、日志边界、记忆/RAG 隔离和双路径 extraction 均有固定证据要求。

## 非阻塞 P2 建议

以下不阻塞 GO，但应在 Task02 protocol-report 的逐事件样本和能力证据表中顺手固化：

1. 明确 `done.duration_ms` 与 `answer_duration_ms` 的字段别名/取值关系，避免前端显示时把回答阶段时长误解为整轮时长。
2. 将“首尾平均保留”补成奇数预算下 head/tail 的确定性分配（例如多出的一个 code point 固定给 head），并在固定向量中记录输出全文。
3. 为 `evidence_id` 记录稳定生成规则（如 model、route、effort、probe timestamp 的脱敏摘要），便于后续审计而不泄露 prompt。

## 改动文件

- 覆盖写入：`docs/sdd/reviews/024-tech-review.md`（本报告）。
- 未修改：`backend/**`、`frontend/**`、数据库、部署配置及其他业务文件。

## 检查命令、退出码和结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `git diff --check -- docs/sdd/specs/024-visible-reasoning-controls.md docs/sdd/plans/024 docs/sdd/reviews/024-tech-review.md` | 0 | 通过，无空白错误。 |
| `rg -n '^<<<<<<<|^=======|^>>>>>>>' docs/sdd/specs/024-visible-reasoning-controls.md docs/sdd/plans/024 docs/sdd/reviews/024-tech-review.md` | 1 | 无冲突标记；无匹配时的预期退出码。 |
| `node --check frontend/app.js` | 0 | 现有前端基线语法通过。 |
| 合同关键词/章节核对（五档、resolver、marker、Preference、EVENT_SEQUENCE_GAP、monotonic、NFC、测试白名单、allowlist） | 0 | 全部命中；未发现修订内容缺失。 |
| `git status --short --branch` | 0 | 工作树仅见父任务正在编辑的 docs/sdd 规范/计划/评审文档；无 backend/frontend/数据库变更。 |

未运行 pytest、真实 Ollama、数据库迁移、服务启动或浏览器 smoke：这些属于 Task02/Task03/Task04/Task05 的后续验证，不是实施前技术复审的替代证据。

## 产物路径

- 最终技术复审报告：`docs/sdd/reviews/024-tech-review.md`

## 决策依据

修订后的合同已经把前两轮的关键阻塞逐一落到可执行条款：

1. 五档 provider 值、xhigh 双证据、统一 resolver、能力 endpoint 错误体和 LangChain/direct 同路径。
2. schema v7 marker、UserChatPreference DDL、迁移顺序、外键清理矩阵、SQLite backup/count 证据及逐阶段回滚断言。
3. 所有 SSE 事件的 JSON envelope、全流 event_seq、缺口/重复/旧序号、终态丢弃和 Message 状态映射。
4. 固定过滤向量、NFC/code point 截断和 20,000 上限。
5. monotonic 阶段时钟、off/失败/断线真值序列。
6. Task02–05 的文件/测试白名单和 observability allowlist/日志捕获边界。

因此技术门禁可通过，但 GO 的范围仅是“合同允许进入 Task02”。真实模型能力、临时迁移安全和双路径 extraction 必须由 Task02 protocol-report 取得证据后，才能放行 Task03。

## 风险与阻塞

- 当前实现仍处于 Spec024 实施前基线，`ollama.py`/`chat_runner.py` 仍是布尔参数、`chat_graph.py` 仍只读正文、`stream_event` 仍无 envelope、`spans.py` 仍含旧 thinking；这是已登记的 Task03 改动接缝，不是本轮合同阻塞。
- 当前尚无真实五档探针或临时迁移报告；按依赖关系必须由用户确认 Spec 后执行 Task02，任何待测档位不得提前标成 supported。
- Ollama 可能拒绝 low/medium/high 字符串或无法证明 xhigh；若真实证据不满足 Spec，Task02 必须给出 NO-GO，禁止静默降档。
- P2 建议见上节，不阻塞本轮技术 GO。

## 主 Agent 后续动作

1. 保持 Spec024 为“待确认”，等待用户明确确认 spec；不要因技术 GO 自动进入实现。
2. 将本报告视为最终技术门禁产物；确认后只启动 Task02，并按白名单写入 `docs/sdd/plans/024/artifacts/task-02/protocol-report.md`。
3. Task02 必须在临时数据库运行 v7/回滚注入、在真实 Ollama 记录逐档证据和逐事件样本；若任一档位/清理/双路径隔离不成立，回报 NO-GO 并退回 Spec。
4. 只有 Task02 protocol-report GO 后，才分派 Task03；随后按 Task03 → Task04 → Task05 依赖执行，最终回归和部署仍只在 Task05。
5. 将本次最终复审状态按项目规则同步到 `docs/sdd/spec-status-changelog.md`，但不要在未获用户确认前把 Spec 状态改为“已确认”。

## 开始、结束和总耗时

- **开始**：2026-09-11 约 23:45 +0800（收到主 Agent 分派后）
- **结束**：2026-09-12 约 00:04 +0800（本报告覆盖写入后）
- **总耗时**：约 19 分钟

## 模型、token 和工具统计

- **模型**：临时 Luna high（按主 Agent 分派要求）
- **Token**：当前运行环境未提供可靠 token 计数，未编造数值
- **工具调用**：约 8 次只读命令/文件检查，1 次复审报告写入；未调用破坏性命令、真实迁移、真实 Ollama、reset/stash/clean/push 或部署
