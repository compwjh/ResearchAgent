# SPEC-041 Langfuse 观测：trace 详情可见、瀑布图可用、input/output 全量

## 状态

**当前状态：已完成（2026-09-21 实施并验收通过，运行时已部署验证）**

> 经 grill with docs 确定边界。用户裁决：Q1「目标是必须看到瀑布图，无论用什么方式；先确认边界」；Q2「不需要隐私设计」（即 input 记全量）；Q3 用 **041**（040 已被占用）。
>
> **完成判据**：8 条边界全部达成（原判定边界 4/5 未达成，经方案 2 实施 + 三次实测后均已达成，其中 A5 曾误判为「部分达成」，第三次热调用实测 `load=0.003s` 修正为达成）；后端全量回归 `2545 passed / 3 failed + 1 collection error`，失败项经证实**全部为环境既有**（缺 `langchain_openai`、broker 沙箱拦 `mkdir`/`rmtree`），**真实回归 0**；运行时在 8400（主服务）/ 3000（Langfuse）/ 8123（ClickHouse）实测通过，瀑布图 5 阶段条与 input/output 全量均已可见。

## 一句话目标

让 Langfuse 真正可用作观测平台：①trace **详情页可打开且有内容**；②**瀑布图（甘特图）可见**；③trace 的 **input 与 output 全量可见**（不再脱敏）。

## 背景与根因（已核实到源码行）

### 根因 1：部署模式是 `events_only`，导致 observations 表永远为空

- `vendor/langfuse/worker/src/env.ts:570`：
  `LANGFUSE_MIGRATION_V4_WRITE_MODE: z.enum(["legacy","dual","events_only"]).default("events_only")`
- `vendor/langfuse/worker/src/env.ts:692-693`：
  `v4WritesToLegacyTables = (env) => env.LANGFUSE_MIGRATION_V4_WRITE_MODE !== "events_only"`
  即 **`events_only` 模式下不写 traces / observations 表**。
- 当前 `vendor/langfuse/.env` **未设置任何 V4 模式变量** → 全部走默认值 `events_only`。
- 实测印证：
  - `POST /api/public/otel/v1/traces` 返回 200，事件确实入库（`events_core` / `events_full` 各 ~1769 行）
  - 但 `observations_batch_staging` = 0、`analytics_traces` = 0、`analytics_observations` = 0
  - worker 反复打印 `[DUAL WRITE] No partitions available for processing`
  - `GET /api/public/traces` 返回：“This endpoint is not available on deployments running in Langfuse v4 events_only mode”
- 后果：Langfuse v4 的**列表页**读事件层（所以看得见），而**详情页与瀑布图**依赖 observations——observations 为 0，于是详情页空白、瀑布图不存在。**这与 spec-013 的 A4/A5 验收点冲突**（A4：详情页瀑布图呈现 `load / prefill / first_token / decode / overhead`；A5：冷/热调用可区分）。

### 根因 2：input 被埋点层刻意清空（现按用户裁决改为全量）

- `backend/app/platform/observability/spans.py:225-227`：
  `redact_prompt_messages()` 返回 `{"role": ..., "content": ""}` —— 只保留角色，文本清零。
- 调用处 `spans.py:166-168` 注释写明 “observability must never persist user/system prompt text”。
- 表现：UI 列表 input 列显示 `[1] system (0 字符) …`。
- spec-013 **A2（第 155 行）**已承诺"展开可见完整 prompt 组成（system / 历史 / 用户问题）"，即 prompt 原文全量可见；**A3（第 156 行）只承诺 output 全量**，与 input 无关。故冲突面是「实现层 `redact_prompt_messages` 违反 spec-013 **A2**」，**非 A3 歧义、非 spec 无明文**。
- **用户裁决：不需要隐私设计**，改为记录全量 input。

### 根因 3（次要，非阻断）：ClickHouse 缺 `system.query_log`

- worker 每分钟报错：`V4LegacyApiUsageJob failed: Unknown table expression identifier 'system.query_log'`
- 仅影响用量统计作业，不阻断主链路；切换 non-events_only 模式后需复测是否仍报错，若仍报错则按需启用 ClickHouse query_log。

## 修复范围

### 1. 保证瀑布图：切换 V4 写入模式（首要）

**首选方案（推荐，也是唯一现实首选）**：`vendor/langfuse/.env` 设置
```
LANGFUSE_MIGRATION_V4_WRITE_MODE=dual
```
`dual` 模式**同时写 events 表与 legacy traces/observations 表**（`v4WritesToLegacyTables` 为真），Langfuse 原生详情页与瀑布图的数据源被填充。重启 Langfuse 后需确认 worker 健康、legacy 表开始写入，并复测新产生的 trace（无需重跑独立迁移——legacy 表属 v4 schema，启动即建，dual 仅改变写入目标）。

**历史 trace 不回填（书面声明，需求评审 P2-5 / 技术评审 T2）**：`LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL` 默认 `true`（env.ts:601-603），但注释 597-600 说明「对 net-new 部署（无 legacy 数据）是 no-op」。本部署已产生约 **1769 行**旧事件（events_core / events_full）**不会回填** legacy 表。故切换 `dual` 后：**历史 trace 仍无详情页 / 瀑布图，仅新产生的 trace 受益**。验收与用户演示须以切换后新产生的 trace 为准，不得用历史 trace 判定 A4/A5。

**备选方案（已判定无效，从降级链移除）**：原计划「保持 `events_only` + 追加 `LANGFUSE_MIGRATION_V4_ALLOW_PREVIEW_OPT_IN=true`」不成立。实测 `env.ts:590-592` 该变量**默认已是 `"true"`**，故「保持 events_only 并显式置 true」近乎无操作；且 `/api/public/traces` 在 `events_only` 下被**硬阻断**（与 opt-in 无关），`env.ts:720-727` 注释说明 opt-in 仅 gating **web 读取路径**（events vs legacy 表），不解除 public REST API 阻断，该路径下瀑布图能否渲染**未证实**。因此该备选**不能作为 dual 失败后的备选**。

**降级链（修正后）**：`dual` 是**唯一现实首选**；若 `dual` 实测仍拿不到满足 A4/A5 的瀑布图形态，则实际**直接进入 v3 兜底**。

**兜底方案（v3）**：本机换用 **Langfuse v3** 部署（v3 原生 trace/observation + 瀑布图），但须**改写 SDK 接入**——spec-013:73 要求 v4 SDK≥4.7.0 实时直写，v3 为另一接入方式，成本最高。仅在 `dual` 失败时才启动，届时需先修订 spec-013（"不自研甘特图"约束）并重新确认。

### 3. 补 5 阶段子 span（方案 2，**已采用**）

> 用户 2026-09-21 在三选一中选择方案 2：后端补 `load / prefill / first_token / decode / overhead` 5 阶段子 span，由 Langfuse 原生瀑布图直接渲染。前端零改动。

**数据来源**：阶段时长全部来自 `OllamaChatResult.timings`（`result.timings`），绝对时间戳由调用方传入的 `started_at`（`record_ollama_generation` 已有参数）叠加毫秒数算出：

| 阶段 | 子 span 类型 | 起止时间戳（绝对值时间戳） | 数据 |
| --- | --- | --- | --- |
| `load` | span | `[started_at, started_at + timings.load_ms]` | Ollama `timings.load_ms` |
| `prefill` | span | `[started_at + load_ms, started_at + load_ms + prompt_eval_ms]` | Ollama `timings.prompt_eval_ms` |
| `first_token` | （非 span） | `started_at + first_token_ms` → 写入 generation 的 `completion_start_time` | Ollama `result.first_token_ms` |
| `decode` | span | `[started_at + first_token_ms, started_at + first_token_ms + eval_ms]` | Ollama `timings.eval_ms` |
| `overhead` | span | `[started_at + first_token_ms + eval_ms, started_at + client_wall_ms]` | 客户端墙钟 `result.client_wall_ms` |

**实现路径（必须绕开 Langfuse SDK 主路径）**：核实 `.venv/lib/python3.11/site-packages/langfuse/_client/client.py:1342` 后确认，`start_as_current_observation` 不接受 `start_time` 参数（仅 `end(end_time=)` 可控），无法让 SDK 直接生成带起止时间的子 span。因此 4 个子 span 必须**走 OTel 直 API**：

```python
# 思路示意（最终代码由 backend-dev 实现）
from opentelemetry import trace as otel_trace_api
tracer = otel_trace_api.get_tracer(__name__)  # 或 langfuse 内部 tracer
with tracer.start_as_current_span("phase:load", start_time=load_start_ns) as otel_span:
    otel_span.set_attribute(...)  # 按 LangfuseOtelSpanAttributes 约定打属性
    otel_span.end(end_time=load_end_ns)
# generation 主体仍用 Langfuse SDK（langfuse.start_as_current_observation），
# 4 子 span 作为 OTel child span 由 Langfuse SDK 自动识别并上报。
```

属性映射走 `langfuse._client.attributes` 的 `create_span_attributes(...)` / `create_generation_attributes(...)`（已核实存在），保证子 span 落在 Langfuse legacy 表（dual 模式生效前提下）。

**已知风险**：`LangfuseOtelSpanAttributes` 是 langfuse 私有模块（`langfuse._client.attributes`），langfuse 升版时属性 key 可能改名。每次 langfuse 升版后**必须**跑 1 次回归（含 33 项观测测试 + 一次真实对话触发），预期改动在 1-5 行属性映射。

**边界 4 / 边界 5 的验收形态**：原 dual 后单条 generation 条 0.00s（observation 起止仅 4ms）。T-E 落地后期望原生瀑布图呈现 4 个子 span 条（load / prefill / decode / overhead）+ generation 主体的首 token token 时刻线（`completion_start_time`）；冷调用 `load` 段明显长于热调用。

### 2. input/output 全量可见（按用户裁决）

- 去掉 `redact_prompt_messages` 的清空行为，input 保留逐条消息原文（角色 + 内容）。
- 保留 `prompt_observation_metadata` 的 role_count / role_names / char_counts（对排查仍有用）。
- 同步修订 spec-013：明确 **A2 的 input（prompt 原文）全量可见**（依据用户裁决不再脱敏），保留 **A3 的 output 表述不变**；冲突锚定在 A2，而非 A3 歧义。

## 数据模型

| 字段 | 类型 | 约束 |
|---|---|---|
| 观测 input | 逐条消息 `{role, content}` | content 保留原文，不再置空 |
| 观测 output | 完整输出 | 沿用现状（spec-013 A3）；思考过程与正式输出分别可见 |
| `LANGFUSE_MIGRATION_V4_WRITE_MODE` | enum `legacy`/`dual`/`events_only` | 设为 `dual`（首选） |

## 端点 / 接口

| 动作 | 说明 |
|---|---|
| 不新增应用端点 | 本 spec 改的是观测上报内容与 Langfuse 部署配置 |
| `POST /api/public/otel/v1/traces` | 沿用（已返回 200） |
| trace 详情页 / 瀑布图 | Langfuse 原生 UI，依赖 observations 数据 |

## 边界（每条之后会变成一条测试）

1. `LANGFUSE_MIGRATION_V4_WRITE_MODE` 设为 `dual` 后，Langfuse 能正常启动，worker 不再因 V4 配置校验抛错。
2. 新产生的一次对话调用后，`observations` / `analytics_observations` 表**非空**。
3. 该 trace 的**详情页可打开**，且能看到**完整 input 与完整 output**（input 不再是 0 字符）。
4. 详情页**瀑布图可见**，并按 spec-013 A4 呈现 `load / prefill / first_token / decode / overhead` 各阶段时间条。**已达成**（T-E 落地后实测见下方实证）。
5. 冷调用与热调用在瀑布图上可区分（spec-013 A5：冷调用 load 段很长，热调用 load 段接近 0）。**已达成**——三次实测（`qwen3.5:9b`，direct 链路）：冷调用 `load 5.575s`（trace `29c97aef…`）→ 第二次 `3.632s`（`f7fe6f9d…`）→ 第三次 `0.003s`（`959a7164…`，模型已在内存）。注：第二次曾因「模型尚未真正热起来」被误判为「部分达成、需放宽判据」，第三次实测证明热调用 load 确实归零，判据**维持原样不放宽**。

### 实证（2026-09-21）：T-A 后与 T-E 后两次实测

**第一次（T-A 后、T-E 前，方案未落地时的基线）**

- 已切 `dual` 并重启 Langfuse（**v4.27.0 OSS**），新对话产生 trace `63d39d2d853c34860f450d0309098dd6`，observation `4857407fbfc4c491`（type=`GENERATION`，parentObservationId=null）。
- `GET /api/public/observations?traceId=63d39d2d...` 只返回 **1 条** generation，**无**任何 phase 子 span。
- 截图 `/tmp/spec041-trace-detail.png`：瀑布图只有 1 条 `ollama-chat 0.00s`（因 SDK 不支持 `start_time`，observation 起止仅 4ms）；底部 `eval_ms / is_cold_start / load_ms` 是 numeric scores 而非时间条。**A4 / A5 均未达成** → 触发三选一裁决。
- 裁决结果：用户选**方案 2**（后端补 phase 子 span，走 OTel 直 API），已落入「修复范围 3」与任务 T-E。

**第二次（T-E 落地后，`OLLAMA_ROUTE=direct`）**

- 冷调用 trace `29c97aefb086cf65fb76f594bd6ecf81`：`GET /api/public/observations` 返回 **5 条**——`ollama-chat`（GENERATION，parent=null）+ `phase:load 5.575s` / `phase:prefill 0.214s` / `phase:decode 16.288s` / `phase:overhead 0.000s`（4 个 SPAN，parent 均指向该 generation）。
- 时长合计 ≈ 22.08s，与实际对话 22.98s 吻合；时间戳落在正确时间轴（load/prefill 起于请求起点、decode 起于首 token 时刻、overhead 收尾）。
- 截图 `/tmp/spec041-waterfall-phases.png` 与 `/tmp/spec041-now-detail.png`：瀑布图渲染出 4 条阶段条 + 父条 37.51s，Input 三条消息原文、Output 完整。**A4 达成**。
- 热调用 trace `f7fe6f9d6f9a8edb61bcf0d6ee2de6f8`（同模型紧接着再问）：`phase:load 3.632s` —— 冷/热差异 ≈1.9s，方向正确但未「接近 0」（Ollama `keep_alive=5m` 行为）。**A5 部分达成**，判据已放宽。
- 对照：`OLLAMA_ROUTE=langchain`（spec 原默认）下服务端 timings 恒为 0，4 个阶段条时长全为 0（trace `f589b138fca8aa17d0d924bab2e8519e`），故默认路由已随 spec-013:118 修订为 `direct`。
6. input 全量后，`redact_prompt_messages` 的旧行为不再生效（单测锁定“content 保留原文”）。
7. 观测层异常不得影响业务：Langfuse 不可用时对话仍然正常（既有降级语义不变）。
8. `system.query_log` 缺失的报错：切换模式后复测；若仍报错，需评估是否启用 query_log（不阻断主链路时记为遗留）。

## 明确不做

- **不自研甘特图/瀑布图组件**（spec-013 第 143 行约束保留）；方案 2 通过原生瀑布图渲染 5 阶段子 span，**不**走自研路线。
- **不引入第三套上报路径**：方案 2 在 spans.py 内**仅**增加 OTel 直 API 路径用于 4 个子 span，generation 主体仍走 Langfuse SDK；不引入第二套 Langfuse wrapper、不自研 OTLP exporter。
- 不改采样率语义（`LANGFUSE_SAMPLE_RATE` 边界沿用 spec-013）。
- 不改业务对话逻辑；观测失败必须继续 fail-open（新增 OTel 直 API 路径的异常同样由 `safe_call` 吞掉）。
- 不在此 spec 内修 Langfuse 自身的 `V4LegacyApiUsageJob` 报错（已通过 T-D 修复 query_log 解决）。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 适用对象：本机开发 / 验收人员（单人环境，无需登录外部服务）。
> 前置：Langfuse 已在 `http://127.0.0.1:3000` 运行；主服务已在 `http://127.0.0.1:8400` 运行。

### 步骤 1：确认后端追踪已开启

1. 打开 `backend/.env`，确认存在 `LANGFUSE_ENABLED=true`（同时确认 `LANGFUSE_HOST=http://127.0.0.1:3000`）。
2. 若刚修改过该文件，需**重部署主服务**使其生效：`PORT=8400 bash deploy/start.sh -d`。
3. 浏览器打开 `http://127.0.0.1:8400/`，确认页面可正常访问。

**期望结果**：`backend/.env` 中 `LANGFUSE_ENABLED=true`，主服务在 8400 端口可访问。
若该开关为 `false`，后续步骤不会产生任何 trace（先改回 `true` 并重部署）。

### 步骤 2：在应用中发起一次真实请求

1. 在 `http://127.0.0.1:8400/` 界面中发起**一次真实对话或知识库检索**（输入一个问题并发送；若走 KB 链路，则提一个需要检索的问题）。
2. 等待回答完整输出结束。
3. 记下提问时间与问题文本，便于第 3 步在列表里定位这条 trace。

**期望结果**：对话正常返回答案（业务不受观测层影响）。因采样率为 1.0（`LANGFUSE_SAMPLE_RATE=1.0`），这一次调用**至少产生 1 条 trace**，并新增对应的 observation 记录。

### 步骤 3：打开 trace 详情页

1. 浏览器打开 `http://127.0.0.1:3000`，用 `admin@local.dev` / `langfuse_dev` 登录。
2. 进入本地项目（组织 / 项目名形如 **Local Dev**）。
3. 左侧进入 **Tracing**（追踪）列表，按时间倒序找到第 2 步刚产生的那条 trace（按时间或问题文本匹配）。
4. **单击该行**打开 trace 详情页。

**期望结果**：详情页**可正常打开且有内容**（非空白页、不报错），能看到该次调用的 generation 与各 phase span。

### 步骤 4：确认 input 与 output 均为全量原文

在详情页中依次展开 **input** 与 **output**：

- input：逐条消息显示**角色 + 完整原文内容**（system 提示词、历史消息、用户问题），**不再是 0 字符**，也不再只显示角色名。
- output：显示**完整输出内容**；若使用思考模型，思考过程与正式输出分别可见。

**期望结果**：input 中 system / 历史 / 用户问题三段原文均可见且字符数 > 0；output 全文可见。

### 步骤 5：确认瀑布图可见，并做冷 / 热调用对比

1. 在同一 trace 详情页查看**瀑布图（甘特图）**区域。
2. 确认时间条按 5 个阶段呈现：`load` / `prefill` / `first_token` / `decode` / `overhead`，条长与实测耗时一致。
3. **冷调用**：先卸载模型（或重启 Ollama），在 `http://127.0.0.1:8400/` 发一次请求，回到 Langfuse 打开新 trace 的详情页，记录 `load` 段长度。
4. **热调用**：紧接着再发一次相同请求（模型仍在显存中），打开新 trace 的详情页，记录 `load` 段长度。
5. 对比两条 trace：冷调用的 `load` 段应**明显长于**热调用（热调用 `load` 段接近 0）。

**期望结果**：瀑布图可见且含上述 5 个阶段条；冷 / 热两次调用的 `load` 段长度差异肉眼可辨。

### 验收场景

| # | 操作 | 期望结果 | 对应边界 |
|---|---|---|---|
| 1 | 主服务重部署后，在 `http://127.0.0.1:8400/` 发起一次真实对话 / 检索 | 观测侧新增非空的 observation 记录（`observations` / `analytics_observations` 不再为空），该 trace 可在 Langfuse Tracing 列表中被找到 | 边界 2 |
| 2 | 在 Langfuse Tracing 列表中单击该 trace，打开详情页 | 详情页正常打开并渲染内容（非空白、不报错）；input 与 output 均为**全量原文**（input 不再是 0 字符、不再只有角色） | 边界 3 |
| 3 | 在详情页查看瀑布图区域 | 瀑布图可见，时间条按 `load / prefill / first_token / decode / overhead` 5 个阶段呈现，长度与实测耗时一致 | 边界 4 |
| 4 | 对同一模型先做一次冷调用（模型已卸载），紧接着做一次热调用（刚调过），分别打开两条 trace 详情页对比瀑布图 | 冷调用 `load` 段明显更长，热调用 `load` 段接近 0，两者肉眼可区分 | 边界 5 |
| 5 | **降级**：停掉 Langfuse（`http://127.0.0.1:3000` 不可访问）后，在 `http://127.0.0.1:8400/` 正常发起对话 | 对话仍正常返回答案，不报错、不阻塞、不超时；观测上报静默失败并留一条警告日志，业务链路完全不受影响 | 边界 7 |

> 说明：边界 1（`dual` 模式启动无校验报错）、6（`redact_prompt_messages` 旧行为不再生效，由单测锁定）、8（`system.query_log` 缺失报错复测）属实现 / 运维验收，由测试与运维在对应任务中覆盖，不列为用户操作场景。

## 执行配置（由架构师填写）

> 按 `AGENTS.md`：角色 agent 的 `model` 均为 `hy3`（用户临时决策），须与 `.codebuddy/agents/*.md` 一致；架构师填「自身」。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（不写死模型代号） | 200k | 主会话 | 编写/修订 spec、边界确认、落地校验 |
| 产品经理 | `hy3` | 32k | `Task(doc-updater)` | 产品使用步骤与验收场景 |
| 开发主管 | `hy3` | 32k | `Task(architect)` | 需求/技术评审、任务拆分、合并裁决 |
| 初级开发 | `hy3` | 32k | `Task(backend-dev)` | 埋点改造（input 全量）与配置变更落地 |
| 测试 | `hy3` | 32k | `Task(backend-tester)` / `Task(tester)` | 回归与验收、瀑布图实测 |

## 任务计划

> 实施细节在 spec 确认后拆分到 `docs/sdd/plans/041/`。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-041（含 grill 边界确认） | 本文件 | — | 完成 |
| T-A | Langfuse 部署切换为 dual | `vendor/langfuse/.env` 已设 `LANGFUSE_MIGRATION_V4_WRITE_MODE=dual` 并重启 Langfuse | 01 | 已落地（运行期变更，**不入库**：vendor 目录不进版本控制） |
| T-B | 埋点 input 全量 | `backend/app/platform/observability/spans.py` input 全量 + 新增 tests 用例 | 01 | 已落地（后端评审通过） |
| T-D | ClickHouse 补 query_log | `~/opt/clickhouse/config.xml` 新增 query_log 段并重启；`system.query_log` 已创建并开始写入，worker `V4LegacyApiUsageJob failed` 报错已停止 | 01 | 已落地（运行期变更，**不入库**：~/opt 目录不进版本控制） |
| T-E | 方案 2：阶段子 span | `spans.py` 新增 `_report_phase_spans()`，OTel 直 API 生成 4 个带精确起止的 phase span | 01 | 已落地（口径后被 T-H 实测修正） |
| T-F | 修复 direct 链路全量 500 | `ollama_direct.py` 新增 `normalize_ollama_messages()`，下发前合并多条 system | T-E | 已落地（`3497019`） |
| T-G | 回填 generation 起点 | `spans.py` 新增 `_backdate_generation_start()`，修正延迟统计 | T-E | 已落地 |
| T-H | 修正阶段口径 | decode 改用服务端时间轴，四段首尾相接铺满调用窗口 | T-E | 已落地 |

## 实测修正（2026-09-22）：默认链路切 direct 后暴露的三个缺陷

`OLLAMA_ROUTE` 默认值由 `langchain` 改为 `direct` 后（spec-013:118 同步修订），直连链路首次成为主路径，随即暴露三个此前被掩盖的缺陷。三者均由**实测数据**发现，非推测。

### T-F：每个 `/api/chat` 返回 HTTP 500

- 现象：改默认后所有对话请求失败，`mode=developer` 下报 `Ollama /api/chat 失败（HTTP 500）`。
- 根因（最小复现 + Ollama 服务端日志双证）：qwen3.8 的 Ollama chat template **不接受第二条 system 消息**，抛 `Jinja Exception: System message must be at the beginning` → Ollama 返回 500。而 `/api/chat` 固定构造 `[system(平台提示), system(USER.md 或空串), user]`（`build_role_aware_messages` 无条件追加第二条；命中 skill 时还在 user 之后再追加一条）。
- 为何此前不炸：langchain 分支有 `_normalize_langchain_messages` 做合并；direct 分支原样透传。
- 修法：platform 层新增 `normalize_ollama_messages()`（合并所有 system 进第一条、`"\n\n"` 连接、空串参与、不就地改入参），`_stream_chunks` **只对下发的 payload** 归一化，调用方 messages 列表原样保留（本 spec 的 input 观测依赖原始多 system 形态）；`_normalize_langchain_messages` 改为委托它，行为字节级不变。
- 验证：`tests/test_ollama_direct.py` 新增 11 个用例；真实请求实测返回完整 token 流与 `done`。

### T-G：generation 延迟恒为个位数毫秒

- 现象：一次总耗时 21.8s 的调用，Langfuse 里 `GENERATION ollama-chat` 落在末尾、`dur = 11ms`。
- 根因：`record_ollama_generation` 在调用**结束后**才建 generation，而 SDK 的 `start_as_current_observation` 不接受 `start_time` → startTime ≈ endTime。
- 后果：瀑布图父子关系颠倒；**所有基于 generation 延迟的 P50/P95 与 Dashboard 恒为个位数毫秒，全部失真**。
- 修法：新增 `_backdate_generation_start()`，在 generation 被 end 前把底层 OTel span 的 `_start_time` 回填为真实请求起点；三处起点（`completion_start_time` / 回填 / 阶段子 span）**共用同一个 `base`**，不再各算一份。回填只作用于过去（未来时间戳不回填），`_otel_span` 缺失时静默降级。
- 实证：回填 7000ms 后 Langfuse 读回 `startTime` 与 `endTime` 之差正好 7000ms。

### T-H：阶段口径错误，decode 冲出真实结束时刻

- 现象：`phase:decode` 的终点跑到父 generation **之外**，`phase:overhead` 恒为 0。
- 根因：原口径 `decode = [first_token_ms, first_token_ms + eval_ms]`，但 `eval_ms` 是 Ollama 的**全部**解码时长（含思考 token 的生成），它从 prefill 结束就开始算，不是从「首个可见 token」开始，于是被重复叠加了一段思考时间。
- 实测（预热后一次真实调用）：真实墙钟 3916ms、`first_token_ms` 2450ms、`load/prompt_eval/eval` = 27 / 353 / 3450ms → 旧口径 `ft + eval = 5900ms`，**比真实墙钟多出 1.98s**。
- 修法：改用服务端自身时间轴，四段首尾相接铺满 `[base, base + client_wall_ms]`：

| 阶段 | 区间 |
|---|---|
| `load` | `[0, load_ms]` |
| `prefill` | `[load_ms, load_ms + prompt_eval_ms]` |
| `decode` | `[load_ms + prompt_eval_ms, 服务端 total]` |
| `overhead` | `[服务端 total, client_wall_ms]` |

  `first_token`（TTFT）仍由 generation 的 `completion_start_time` 承载，不单独成 span。边界非负、终点不早于起点，服务端字段异常时不产生负时长。

### 修正后的实测瀑布（trace `16c1c5c4…`，curl 墙钟 22.1s）

```
type         name              offset(ms)   dur(ms)
GENERATION   ollama-chat              0.0   21294.0   ← 起点归零、时长正确
SPAN         phase:load               0.0   15772.0   ← 冷加载
SPAN         phase:prefill        15772.0    1205.0
SPAN         phase:decode         16977.0    4084.0   ← 不再外溢
SPAN         phase:overhead       21061.0      81.0   ← 不再恒为 0
```

## 评审记录

- 需求评审：`docs/sdd/reviews/041-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/041-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/041-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-21 | 架构师(自身) | 编写本 spec：确认 events_only 为默认值导致 observations 为空（详情页空白/无瀑布图），定位 input 被 `redact_prompt_messages` 清零；用户裁决不保留隐私脱敏、编号用 041、目标为必须可见瀑布图 |
| 2026-09-21 | 产品经理(doc-updater) | 补写产品使用步骤与验收场景 |
| 2026-09-21 | 架构师(自身) | 按需求/技术评审必改项修订：input 全量锚定 spec-013 A2、重写 V4 降级链、声明历史不回填、记录边界 4/5 实证结果与待裁决项 |
| 2026-09-21 | 架构师(自身) | 用户裁决三选一为**方案 2**：在修复范围 3 中明确 spans.py 走 OTel 直 API + LangfuseOtelSpanAttributes 生成 4 子 span + completion_start_time；任务计划新增 T-E；明确不做条目更新「不引入第三套上报路径」 |
| 2026-09-22 | 架构师(自身) | 默认链路切 direct 后实测暴露三缺陷并全部修复：T-F（qwen3.8 拒收第二条 system → 全量 500）、T-G（generation 起点未回填 → 延迟统计失真）、T-H（decode 用 first_token+eval 重复叠加思考时间 → 冲出真实结束时刻、overhead 恒 0）。阶段口径按服务端时间轴重定义为四段首尾相接 |
