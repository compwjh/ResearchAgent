# Spec-045 调研记录（二）：可观测性模块

> 调研方式：只读检索（code-explorer 子代理 97 次工具调用 + 主会话交叉验证）。
> 调研日期：2026-11-08。本文是 spec-045「背景与依据」F 系列事实的证据底稿，不做推测。
> 代行留痕：本文件为纯文档改动，由主会话代行（符合 `AGENTS.md:127` 唯一允许的代行条件），
> 三处留痕分别为本文头部、`spec-status-changelog.md` 的 045 条目、spec-045 的「代行记录」小节。

## 0. 总览：三套并存的体系

- **A. Langfuse LLM 观测**：`backend/app/platform/observability/` + Python SDK 上报，外部自托管 UI/看板。
- **B. 自建 SQLite 事件/处理步骤/审计**：`backend/app/memory/migration.py` 的
  `raw_events` / `processing_steps` + `backend/app/research/infrastructure/research_store.py`
  的 `research_events`，经 SSE 推给前端。
- **C. 路由观测**：`backend/app/research/application/routing_observation.py`，同时写 SQLite 与 Langfuse。

## 1. 采集点、字段、是否记录完整提示词/响应

**没有全局 HTTP middleware 埋点**（全 `backend/` 搜索
`@app.middleware|add_middleware|BaseHTTPMiddleware|request.state` 零命中），全部是路由/应用层手工调用。

| 链路 | 埋点位置 | 采集内容 |
|---|---|---|
| chat SSE | `backend/app/api/routes_chat.py:75` `started=utc_now()`；`:107-110` 组装 `observation_messages`；`:169-182` 失败上报；`:193-206` 成功上报并 `flush()` | prompt 消息、模型、route、耗时、token、scores |
| agent 链路 | `backend/app/api/routes_article.py:129-171` | 同上，tags 为 `chat/agent` |
| KB 问答 | `backend/app/api/routes_kb.py:1017-1024` `started` + `start_trace("kb-ask")`；`:1076/1093` generation；`:1088/1103` `flush()`；`:1114` `end_trace()` | RAG 多阶段归入同一 trace |
| KB 阶段 | `backend/app/knowledge_base/infrastructure/embed.py:102-113`（`kb.embedding`）、`retrieve.py:170-180,231-250`（`kb.retrieval`）、`:503-507`（`kb.rerank`） | `model/text_count/top_k/chunker/hit_count/reranker_enabled/status/error_type/duration_ms`，均用 `safe_call` 包裹 |
| 会话流（自建事件） | `backend/app/api/routes_conversations.py:1248` `append_raw_event("user_message", {"content": ...})`；`:1250,1287,1401,1414,1470,1564,1615,1729,1737` 等 `create_processing_step`/`finalize_processing_steps`；`:1639` `tool_failure` 带 `_redact_sensitive` | 步骤状态/摘要、原始用户消息、工具错误 |
| research 事件 | `backend/app/research/application/orchestrator.py:6686-6714` `_emit → append_event + processing_projector`；`agent_runtime.py:1864`；`research_service.py:192,419,452,...` | 任务/计划/工作项/终态事件 |
| 路由观测 | `backend/app/research/application/entry.py:218-220` 注入 `record_routing_observation`；`routing_observation.py:338-379` | 红名单后的决策 + outcome（无 prompt/answer） |
| SSE 推送 | `backend/app/api/routes_research.py:1824-1849`（`/events`）、`:1863-1915`（含 `processing_step` 增量帧与 `TRACE_PROJECTION_FAILED` 重试帧）、`:1227-1268`（通知 SSE）；`backend/app/api/common.py:368-370` `stream_event` | 只推 `safe_payload`，不推原文 |

**Langfuse 上报字段**：`backend/app/platform/observability/spans.py:65-74`
（7 个 numeric score：ttft/load/prompt_eval/eval/overhead/tokens_per_sec/is_cold_start）、
`:96-122`（派生指标）、`:341-380`（input/output/usage_details/metadata/completion_start_time/scores）、
`:427-460`（通用 `record_event`）。

**是否记录完整提示词/响应**：

- **是，且明确不脱敏**：`spans.py:338-341` 注释「spec-041 用户裁决『无需隐私设计，input 与 output 全量可见』」；
  `:401-411` `redact_prompt_messages` 保留原文 content；
  `docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md:7,39,97-101` 为决策依据。
- 但**按字符截断**：`spans.py:360,374` 用 `OBS_MAX_INPUT_CHARS/OBS_MAX_OUTPUT_CHARS`，
  默认各 20000（`backend/app/platform/config.py:143-144`）。
- `raw_events` 记录**完整用户消息文本**且 payload 无截断
  （`routes_conversations.py:1248`、`backend/app/memory/repository.py:1158`）。
- `research_events` **不记录** prompt/answer：白名单 + 值级脱敏
  （`research_store.py:116-169`，URL/Bearer/token 替换为 `[REDACTED]`，字符串截 1000）。
- **规格偏差**：`docs/sdd/specs/013-llm-observability-platform.md:101` 要求 `thinking` 与 content
  分开上报，但 `spans.py:137-138` 只记 `reasoning_present/reasoning_chars`，
  generation 的 output 只有 `result.content`（`:374`），**思考过程正文实际未上报**。

## 2. 存储：表、写入路径、保留策略、并发保护

**Schema（SQLite）**

- `backend/app/memory/migration.py:97-113` `processing_steps`
  （含 `parent_step_id/node_key/detail_json/source_event_id/research_session_id` + 3 个唯一索引，保证 SSE 重连幂等）；
  `:114-122` `processing_step_projection_retries`；`:124-135` `raw_events`
  （`UNIQUE(owner_id, conversation_id, idempotency_key)` + 时间索引）；`:81-95` `messages` 带 `reasoning_*` 时间戳。
- `backend/app/research/infrastructure/research_store.py:544-552` `research_events`
  （PK `(research_task_id,event_seq)`，`safe_payload_json`）；
  `:1165-1176` `research_notifications`、`research_projection_retries`；
  `:833-879` routing decisions/outcomes/policies 等。

**写入路径**

- `backend/app/memory/repository.py:1142-1168` `append_raw_event`（事务 + 幂等键冲突回读）；
  `:1623-1679` `create/update/finalize/list_processing_steps`
  （稳定身份 `(message_id,kind,logical_sequence)`）；`:1170-1185` `list_raw_events`
  （游标 `after` + limit 夹到 1..5000）。
- `backend/app/research/infrastructure/research_store.py:4712-4751` `append_event`：
  同一 `BEGIN IMMEDIATE` 事务内先 `UPDATE last_event_seq+1` 领号再 INSERT；
  `:4753-4761` `list_events`（`after_seq` + limit 夹到 1..1000）。
- 跨库投影 `backend/app/research/application/processing_projector.py:1-6,36-50`
  （`detail_json` 二次白名单，上限 4000 字符），失败由重试表 +
  `routes_research.py:1867,1887-1905` 补偿。

**并发写入保护（有）**

- `backend/app/memory/repository.py:49` `threading.RLock()`、`:197-201`
  `timeout=5s`/`PRAGMA busy_timeout=5000`/`journal_mode=WAL`、
  `:208-213` `with _write_lock` + `BEGIN IMMEDIATE`。
- `backend/app/research/infrastructure/research_store.py:103-105` 全局 `RLock`、
  `:1251-1255` `timeout=30s`/WAL/`busy_timeout=30000`、`:4721-4723` 锁内 `BEGIN IMMEDIATE`。

**保留策略（缺失）**

- 在 `memory/repository.py` 中搜 `retention|清理|DELETE FROM raw_events|DELETE FROM processing_steps`
  **零命中**；`research_events` 只在删除任务时显式级联清除
  （`research_store.py:1651-1684`、`:1686-1719`），
  **没有基于时间/行数的保留、归档或 VACUUM 策略**。Langfuse 侧由自托管 ClickHouse/PG 自身管理，
  项目内也无清理脚本。
- 主会话实测数据量（2026-11-08）：`raw_events` 12 行、`processing_steps` 74 行、
  `research_events` 66 行；`data/memory/memory.sqlite3` 492KB、`data/research/research.sqlite3` 1108KB。
  **属未来风险，不是当前痛点**，不得在 spec 中夸大为现有故障。

## 3. 读取与展示：API、前端、分页/聚合/时间范围

**API 端点**

- `backend/app/api/routes_research.py:1824-1860` `GET /api/research-tasks/{id}/events`
  （SSE，`after_seq` + `Last-Event-ID` 优先，心跳 15s，`_EVENT_BATCH_LIMIT` 批量）；
  `:1227-1268` `GET /api/research-notifications/events`（`polls` 1..120，主动发 `stream_end`）。
- `backend/app/api/routes_conversations.py:2329-2337` `GET /api/messages/{id}/processing-steps`
  （**无分页，一次全量**）；`:2287` 会话消息列表。
- `backend/app/api/routes_research_routing.py:169-225` `GET /research-routing/decisions`
  （keyset `cursor`、`limit` 1..100、`task`/`filter`、脱敏 `public()`）；`:104-166` `/status`；
  `:49-88` evidence/activate。任务列表/详情带 `runtime_observability`
  （`tests/platform/test_retry_observability.py:68-106` 锁定形状）。

**前端视图**

- `frontend/processing-tree.js:180-202` 处理树 + `trace_syncing` 状态；
  `frontend/index.html:247` 容器；`frontend/app.js:2482` 拉取 processing-steps、`:3647` 处理 `TRACE_PROJECTION_FAILED`。
- `frontend/research-tasks.js:12` EVENT_TYPES、`:109-115` BENCHMARK_METRICS、`:350` 报告质量、
  `:422` retryInsight、`:548` routingInsight、`:1537-1562` 基准指标面板、
  `:3252-3267` EventSource 断线重连、`:836-850` 通知流；
  `frontend/index.html:318-334` 对应 DOM。
- Langfuse 原生 UI 在 `http://127.0.0.1:3000`
  （`spec-013:123`、`spec-041:157-180`）；`artifacts/langfuse-waterfall.html:18-21` 只是静态快照，非产品视图。

**分页/聚合/时间范围**

- 自建 API **只有游标/seq 分页**，无按时间范围查询、无服务端聚合端点
  （benchmark/routing 摘要是从事件/任务字段投影，见 `research-tasks.js:564-598,1527-1562`）。
- 聚合集中在 Langfuse 原生看板：`scripts/setup_langfuse_dashboards.py:95-196`
  六组看板（avg/p50/p95/p99/max、`LINE_TIME_SERIES`），但 widget **未设置显式时间过滤**，
  依赖 UI 默认时间范围；脚本 `:13-19,:290-292` 明确承认原生看板无法做真散点、
  阶段甘特、自定义 metadata 聚合。
- 离线聚合样本见 `artifacts/observability-samples.json:11-45`
  与 `scripts/generate_observability_fixtures.py:263-273`。

## 4. Langfuse 集成

**接入方式：自托管 + Python SDK，不是业务层 HTTP 直推**

- `deploy/langfuse/start-langfuse.sh:15-17,42-51,67-85`：非 Docker，
  硬编码 `/Users/wjh/ResearchAgent/vendor/langfuse`、Node 24，
  依赖 ClickHouse 8123 / PostgreSQL 5432 / Redis 6379 / MinIO 9002；
  `deploy/langfuse/env.example:84-87` 固定 `pk-lf-local-dev-0001` / `sk-lf-local-dev-0001`；
  `docs/sdd/HANDOFF-2026-09-21-deploy-langfuse.md:34-37,97-103`（明文 `.env` 凭据）；
  `docs/sdd/MEASUREMENT-langfuse-2026-09-22.md:30-31` 为 v4.27.0。
- SDK：`requirements.txt:15-17` `langfuse>=4.7.0`、`requirements.lock.txt:32` `langfuse==4.15.1`；
  `backend/app/platform/observability/client.py:39-47` `Langfuse(public_key, secret_key, host, timeout=5)`；
  配置在 `backend/app/platform/config.py:120-144`
  （`LANGFUSE_ENABLED` 默认 **false**、`LANGFUSE_HOST=127.0.0.1:3000`、`LANGFUSE_SAMPLE_RATE=1.0`）。
  SDK 走 OTLP 到 `/api/public/otel/v1/traces`（`spec-041:26,116`）。
- HTTP 直推只出现在辅助脚本：`scripts/setup_langfuse_dashboards.py:199-247`
  （httpx 打 `/api/public/unstable` 建看板）、`backend/eval_042/langfuse_export.py:40-77`
  （Basic Auth 读 trace / 回写 score）。

**trace/span 结构**

- `backend/app/platform/observability/trace.py:28-32,66-109`：`ContextVar` 保存 trace_id，
  `start_trace` 建根 span，`end_trace` 用 token 复位；
  `spans.py:77-86` `_trace_context()` 让子 observation 挂到同一 trace。
- `spans.py:356-384`：一个 `generation` 主体
  （`input`=格式化 prompt、`output`=正式输出、`completion_start_time`=TTFT、
  `usage_details`、metadata、7 个 score）+ 4 个 `phase:load/prefill/decode/overhead` 子 span；
  `:206-286` 用**私有** `langfuse._otel_tracer` 精确设置起止时间；
  `:153-183` 进一步改私有 `_otel_span._start_time` 回填 generation 起点。
  结构定义见 `spec-013:80-93`、`spec-041:68-91`。
- 已知限制：`spans.py:15-18,33-36,153-166`（SDK `start_as_current_observation`
  不接受 `start_time`，导致 startTime≈endTime）、`:226-232`（decode 口径被实测推翻后修正）；
  `spec-041:93`（私有属性升版必须回归）、`:17-30,50-56`
  （默认 `events_only` 模式不写 observations，需改 `dual`，历史 trace 不回填）。

**私有 SDK 符号的具体形态（主会话核实）**

- `spans.py:18` `langfuse._otel_tracer`；`:35-36,168-181` `generation._otel_span._start_time`；
  `:47` `from langfuse._client.attributes import create_span_attributes`。
- `spans.py:165-169`：找不到 `_otel_span` 或 `_start_time` 即 fail-open 跳过；
  `backend/app/platform/observability/safe.py:13-22` 吞掉所有异常 →
  **升版后瀑布图静默失真且不报错**，只留 warning 日志。
- `spec-041:93` 原文已知风险：「`LangfuseOtelSpanAttributes` 是 langfuse 私有模块
  （`langfuse._client.attributes`），langfuse 升版时属性 key 可能改名。每次 langfuse 升版后
  **必须**跑 1 次回归（含 33 项观测测试 + 一次真实对话触发），预期改动在 1-5 行属性映射。」
- `tests/observability/test_phase_spans.py:111-116` 用自造的假 tracer
  （`self._otel_tracer = tracer`），真 SDK 变化测不出来。

**两个造样本脚本**

- `scripts/generate_observability_fixtures.py`：`:1-13` 默认 dry-run，`--send` 才导入 SDK；
  `:191-242` 固定 **20 条样本矩阵**（冷/热 × 短/长 × chat/kb 各重复 2 次 + 4 条失败）；
  `:97-124` metadata 契约；`:276-310` 用 SDK 上报 generation + 7 score + `flush()`；
  用途是给 Task 06 原生看板提供可复现验证数据。
- `scripts/gen_observability_samples.py:1-15,83-95`：另一套**真实跑 Ollama/KB** 的造样本脚本，
  会 `keep_alive:0` 卸载模型制造冷启动，产物 `artifacts/observability-samples.json:8-10`
  自认「已用 --skip-cold，冷样本实际不是冷启动」。
- `scripts/setup_langfuse_dashboards.py:1-19,95-196,250-293`：通过 public API 幂等创建
  6 组原生 Dashboard（`--force` 重建），并书面列出 3 类做不到的事项。

## 5. 现有测试覆盖与明显缺口

**覆盖较充分的部分**

- `tests/system/test_observability.py:38-64`（采样/配置边界）、`:72-97`（metrics）、
  `:100-171`（no-op/fail-open/flush/route 回退）、`:174-235`（score/metadata/output）、
  `:237-269`（输出截断）、`:272-...`（trace 上下文）、`:371,430`（char_counts/thinking_chars）、
  `:453-479`（失败 `success/error_type`）、`:553-572`（chain_type）。
- `tests/observability/test_phase_spans.py:152-475`：13 个测试锁住 4 阶段精确时间戳、
  连续性、decode 口径、单阶段/tracer/helper 缺失 fail-open、generation 起点回填、未来时间不回填。
- `tests/observability/test_prompt_input.py:57-147`：6 个测试锁定「input 原文不清空、格式化异常被吞」。
- `tests/system/test_observability_fixtures.py:17-57`：矩阵维度、metadata、时间戳、dry-run。
- `tests/kb/test_kb_observability.py:38-160`：embedding/retrieval/rerank 成功、空集合、失败、
  遥测异常不改结果。
- `tests/platform/test_retry_observability.py` 与
  `tests/frontend/test_retry_observability_frontend.py`：白名单形状、脱敏、畸形数据安全、前端文案。
- 另有大量间接契约测试（`tests/research/test_processing_tree_backend_contract.py`、
  `test_intake_stream_terminal_events.py`、`test_research_storage_contract.py`、
  `test_routing_shadow_observation.py` 等）。

主会话量化：`tests/observability` 19 + `tests/system/test_observability.py` 27 +
`tests/kb/test_kb_observability.py` 8 ≈ **54** 个用例。

**明显缺口**

1. Langfuse 测试**全部 mock SDK**（`test_observability.py:129-130,240-255` 用假 client），
   无真实 SDK/自托管集成与升版回归——而 `spec-041:93` 明确要求每次升版跑回归。
2. 无并发/流式中断下的 `ContextVar` 隔离测试，尽管
   `docs/sdd/plans/013/task-05-instrument-chat-kb.md:80` 写明「测试必须覆盖流中断和并发请求」。
3. 无 `flush()` 落在 SSE 关键路径的性能/超时测试（`LANGFUSE_TIMEOUT=5s`）。
4. 无 retention/表增长/清理测试，也无 `setup_langfuse_dashboards.py`、
   `gen_observability_samples.py` 的测试；fixture 只测 dry-run，`--send` 无覆盖。
5. 无「input 全量后 prompt 内含 API key/凭据」的隐私回归；脱敏测试只覆盖 routing 与 research 事件。
6. 无测试发现「thinking 正文未上报」与 `spec-013:101` 的偏差。

## 6. 代码中可见的问题与风险

**性能（请求关键路径）**

- `record_ollama_generation()` 与 **`flush()` 同步写在 SSE 生成器内**：
  主会话核实 `flush` 为函数式导入而非方法调用，实际位置
  `backend/app/api/routes_chat.py:182,204`、`routes_kb.py:1088,1103`、
  `routes_article.py:154,169`；`backend/app/platform/observability/client.py:56-64`
  的 `flush()` 是同步等待批量发送，配合 `config.py:129` `LANGFUSE_TIMEOUT=5`，
  Langfuse 变慢/不可达会拖住响应尾包——`safe.py:13-22` 只吞异常，**不消除阻塞**。
- 同步 SQLite 写也在 SSE 关键路径：`routes_conversations.py:1248-1251`
  （每轮 `append_raw_event` + `create_processing_step`）、
  `orchestrator.py:6701`（每条事件一次 `BEGIN IMMEDIATE` + 投影），无批量/异步。
  默认采样率 1.0（`config.py:127`）意味着全量上报。
- **重要前提**：当前部署 Langfuse **默认关闭**（`config.py:122` 默认 false，
  根 `.env` 未配置 `LANGFUSE_*`，运行进程环境亦无），因此上述阻塞**尚未发生**，
  属于「一启用就踩」的条件性风险，不得在 spec 中描述为现有故障。

**采样/限流**

- `backend/app/platform/observability/config.py:40-53` `should_sample()` 是
  **每次调用独立 `random.random()`**（主会话核实原文），
  `record_event` 与 `record_ollama_generation` 各自判断（`spans.py:320,439`）：
  同一 trace 内不同阶段可能采样不一致，造成瀑布图缺段、统计偏差；
  `start_trace` 只看 `enabled()`（`config.py:79`），不参与采样决策。
- 无速率限制/背压/队列上限；SQLite 侧事件流完全无采样，
  `raw_events.payload` 无大小上限（`repository.py:1158`）。

**隐私与脱敏（两套口径冲突）**

- Langfuse 一路明确「无隐私设计」：`spans.py:338-341,401-411`、`spec-041:7,39,97-101`；
  prompt 含 `USER.md` 全局画像、技能正文、检索片段（`routes_chat.py:99-106`），
  用户若粘贴 API key 会明文进 Langfuse。
- `raw_events` 明文存完整用户消息（`routes_conversations.py:1248`），
  `tool_failure` 才做 `_redact_sensitive`（`:1639`）；
  而 `research_events` 有严格白名单（`research_store.py:130-161`）、
  `processing_projector.py:36-50` 二次白名单，
  `routing_observation.py:27-38,484-505` 甚至有 key 级 + 值级凭据正则。
  同一项目内脱敏标准不统一。
- 凭据本身：`deploy/langfuse/env.example:86-87` 与
  `HANDOFF-2026-09-21-deploy-langfuse.md:97-103` 是硬编码明文 pk/sk
  （本地单人环境，但仍是明文）。

**失败时的影响：多数 fail-open，个别 fail-closed**

- Langfuse 全链路 fail-open：`safe.py:13-22`、`client.py:26-52`、
  `spans.py:28,234-236,282-286`、`routes_chat.py:183-184,205-206`、
  `routes_kb.py:1021-1026,1112-1117`。
- `raw_events`/processing steps 用 `contextlib.suppress(Exception)` 静默丢事件
  （`routes_conversations.py:1245-1248`）——不阻断主链路但会**静默丢数据**。
- `research_events.append_event` 是 fail-closed：`research_store.py:4718-4750`
  会抛 `ValueError`/`ResearchTaskNotFound` 并回滚；memory schema 初始化也 fail-closed
  （`memory/migration.py:39-40`）。跨库投影失败靠重试表 + `TRACE_PROJECTION_FAILED` 帧补偿
  （`routes_research.py:1887-1905`）。
- `client.py:22,35-38`：SDK 初始化**失败一次后本次运行不再重试**，
  Langfuse 恢复后必须重启主服务才恢复上报。

**数据一致性**

- 跨库投影非同一事务，存在短时不一致窗口（`processing_projector.py:1-6`）；
  `trace.py:28-32,88-89,117-125` 把 trace_id 与 reset token 分开存，
  异常路径可能残留 ContextVar。
- 部署模式影响数据完整性：`spec-041:17-30,50-56`
  （`events_only` 下 observations 为空、详情页/瀑布图不可用；改 `dual` 后历史 trace 不回填）。
- 路由差异：`spans.py:105-107`、`spec-013:142`、`MEASUREMENT:66-72` 指出
  `langchain` 链路 timings/token 恒为 0，观测失效；`config.py:134` 默认已改 `direct`。
- 口径被实测推翻过：`spans.py:226-232` 记录 decode 原来从 first_token 起算会超出父 generation。

**注释里承认的局限**

- `scripts/setup_langfuse_dashboards.py:13-19,290-292`：原生看板无真散点、
  无单次阶段甘特、自定义 metadata 不可聚合。
- `spec-041:93`：私有 OTel 属性（`langfuse._client.attributes`、`_otel_tracer`、
  `_otel_span._start_time`）升版易碎，需人工回归。
- `docs/sdd/plans/013/task-04-ollama-direct.md:147`：SDK 不支持虚拟 start_time，
  精确甘特交给 Task 07；`task-05-instrument-chat-kb.md:80`：跨线程/流式上下文丢失风险；
  `task-06-stats-native.md:97-98`：路径 A 缺口清单。
- `docs/sdd/MEASUREMENT-langfuse-2026-09-22.md:149-154`：Langfuse trace 结构与评测数据集
  不通用、需导出器；`scripts/gen_observability_samples.py:15` 自承会真实卸载模型、勿用 27B。
- `docs/sdd/HANDOFF-2026-09-21-deploy-langfuse.md:30-31,144`：`.env` 缺失即默认关闭、可随时回退。

## 7. 最值得改进的 5 点（调研方建议，供 grill 裁决）

1. **把 Langfuse 上报/`flush()` 移出 SSE 关键路径**（后台队列 + 异步批量 flush，
   设置队列上限与超时熔断）。理由：`routes_chat.py:204`、`routes_kb.py:1103`
   在生成器内同步 `flush()`，`client.py:62` 是阻塞调用且 timeout 5s，
   Langfuse 故障会直接转化为用户可见的尾包延迟，当前 fail-open 只保证不抛异常、不保证低延迟。
2. **采样改为 trace/请求级一致，并给 SQLite 事件加 retention**。理由：
   `config.py:53` 每次独立随机采样会撕碎同一 trace 的瀑布图；
   `raw_events`/`processing_steps`/`research_events` 只随任务删除而清除，
   无任何时间/容量保留策略，长期单机使用必然无限膨胀。
3. **统一脱敏口径并恢复可配置的 prompt 脱敏开关**。理由：
   Langfuse 明文全量 prompt（`spans.py:401-411`）与 `research_store.py:130-161` 的凭据级脱敏、
   `routing_observation.py:27-38` 的 allowlist 相互矛盾；
   至少应对 key/token 做值级过滤并给 `raw_events.payload` 加大小上限。
4. **补齐 thinking 正文上报 + 统一请求/trace 上下文（含 middleware request_id）**，
   并补并发/流中断测试。理由：`spec-013:101` 承诺思考过程可见但实现只留了字符数
   （`spans.py:137-138`）；`task-05:80` 自己要求的并发/流中断测试至今缺失，
   ContextVar 在 SSE/线程切换下有残留风险。
5. **增加真实 SDK 集成/升版冒烟与 `--send`、dashboard 脚本契约测试，
   并封装私有 OTel 符号为兼容层**。理由：现有观测测试全部 mock SDK，
   而 `spec-041:93` 明确承认依赖 `langfuse._otel_tracer` / `_otel_span._start_time`
   等私有符号，升版会静默破坏瀑布图却无任何测试能发现。

> 补充更正（grill 裁决阶段）：第 5 点的「封装」**不保证不退化**。
> 私有符号消失后精确时间轴仍会退化；封装保证的是「退化可发现（显式降级 + 告警）」
> 与「修复点唯一（一个文件）」。真正根治需 SDK 公开支持设置 `start_time`
> （不由本项目控制）或放弃精确瀑布图（产品降级）。
