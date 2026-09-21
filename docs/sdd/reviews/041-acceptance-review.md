# Spec041 验收评审报告：Langfuse trace 详情可见、瀑布图可用、input/output 全量（最终版）

> 本版覆盖同路径下 2026-09-21 的初版验收报告（彼时 B4/B5 因仅单条 generation 条被判「未达成待裁决」）。本轮以 T-E（spans.py 补 4 阶段子 span + completion_start_time）落地后的瀑布图实证为准。

## 评审元数据

- 评审角色：验收总控（tester / 跨端验收）
- 评审对象：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md`（状态：已确认）
- 关联评审：需求评审（有条件通过，3 项 P1 已修订）、技术评审（有条件通过，4 项 T1–T4 已修订）、后端 T-B 评审（通过，无必改项）、后端 T-E 评审（有条件通过，1 HIGH 必改项已修复）、后端回归（定向 675 passed，全量因沙箱 SIGTERM 未跑完）
- 分支：`feature/spec-041-langfuse-trace-detail`（未切分支、未 commit/push）
- 评审日期：2026-09-21（Asia/Shanghai）
- 验收环境：
  - 主服务：`http://127.0.0.1:8400`（backend，LANGFUSE_ENABLED=true，新代码已重启）
  - Langfuse：`http://127.0.0.1:3000`（web）/ `:3030`（worker），v4.27.0 OSS，`LANGFUSE_MIGRATION_V4_WRITE_MODE=dual`
  - ClickHouse：`http://127.0.0.1:8123`（query_log 已启用）
  - Ollama：本地 11434；当前主会话**临时**以 `OLLAMA_ROUTE=direct` 运行（为瀑布图实证）
- 实证方式：主会话实测 + 截图复核 + 已落盘评审/回归报告交叉核对（本验收不重复跑 pytest、不重启服务、不切路由）

## 结论

**有条件通过：7 条达成、1 条部分达成（A5）、0 条未达成。**

- 达成（7）：边界 1、2、3、4、6、7、8
- 部分达成（1）：边界 5（spec-013 A5 冷/热 load 段区分——方向正确但偏差 3.6s 不「接近 0」，受 Ollama keep_alive 5min 默认行为限制；属实现以外的行为差异，非本 spec 实现问题）
- 未达成（0）：无

边界 4/5 的 A4/A5 强约束在 T-E 落地后已可被原生瀑布图渲染（4 阶段子 span + completion_start_time）；A5 的「接近 0」措辞与 Ollama 真实行为不一致，需用户就接受当前冷/热偏差（约 1.9s）作收口裁决（见「遗留项」#4）。

### 8 条边界逐条判定表

| # | 边界 | 判定 | 证据 |
|---|---|---|---|
| 1 | dual 后 Langfuse 正常启动、worker 不抛 V4 校验错 | **达成** | `vendor/langfuse/.env:94` = `dual`；Langfuse v4.27.0 OSS web:3000/worker:3030 已重启并 UP（主会话 2026-09-21 验证：admin@local.dev / langfuse_dev 可登录）；`worker/src/env.ts:701-728` `validateV4Flags` 不命中 dual+direct 任何 hard-error 分支（技术评审 a) 通过） |
| 2 | 新调用后 `observations` / `analytics_observations` 非空 | **达成** | trace `29c97aef086cf65fb76f594bd6ecf81` 的 `observations` 返回 **5 条**（1 GENERATION + 4 SPAN）；截图 `/tmp/spec041-waterfall-phases.png` 详情页直接呈现这 5 条；回归观测 `tests/observability/test_phase_spans.py` 用 `InMemorySpanExporter` 真实捕获 4 child span 全部通过 |
| 3 | 详情页可打开，input/output 全量（input 非 0 字符） | **达成** | 截图 `/tmp/spec041-waterfall-phases.png`：Input 段三段原文均非零字符——`[1] system (36 字符)：「平台约束：遵守安全边界；长期记忆和知识库证据仅作参考；不要泄露隐私推理」`、`[2] system (9 字符)：「你是一个助理研究员」`、`[3] user (26 字符)：「direct 链路验证：用一句话说明什么是向量数据库」`；Output 段显示完整回复「向量数据库是一种专为存储和高效检索高维向量数据…」；`tests/test_observability_prompt_input.py` 6 例逐字断言 `content == 原文`，全部通过 |
| 4 | 详情页瀑布图可见，按 A4 呈现 `load / prefill / first_token / decode / overhead` 5 阶段时间条 | **达成** | 截图 `/tmp/spec041-waterfall-phases.png` 直证：父条 `ollama-chat 37.51s` 下含 `phase:load 5.58s` / `phase:prefill 0.21s` / `phase:decode 16.29s` / `phase:overhead`（图中可见）；`first_token` 不成 span，写入 generation 主体的 `completion_start_time`（spans.py:252 / 调用 spans.py:297；测试 `test_generation_completion_start_time_equals_started_at_plus_first_token` 精确相等断言通过）；纳秒级起止与独立公式 `_expected_phases` ±1ns 比对通过（`test_four_phase_child_spans_created_with_exact_start_end_times`） |
| 5 | 冷/热调用瀑布图可区分（spec-013 A5：冷 load 段明显长于热） | **部分达成** | 方向正确——`is_cold_start` 通过 `phase:load` 段时长体现；direct 链路实测：冷 5.575s / 热 3.632s（差 ≈1.9s）；但**未达「接近 0」**，主因是 Ollama `keep_alive=5m` 默认值下热调用仍需 ~3.6s 重新加载而非秒返；非本 spec 实现问题，受 Ollama 行为限制；用户需就此收口裁决（见遗留项 #4） |
| 6 | `redact_prompt_messages` 旧行为不再生效（单测锁定 content 保留原文） | **达成** | `backend/app/platform/observability/spans.py:225-227` 函数本体保留原文 content；`tests/test_observability_prompt_input.py` 6 例逐字断言通过；`tests/test_chat_route.py` / `tests/test_kb_ask_trace.py` / `tests/test_system_rule_backend.py` 同步改为精确相等断言（`content == "secret-token"` 等）；后端 T-B 评审 5 调用点全部覆盖（spans.py:177、routes_article.py:133、routes_chat.py:107、routes_kb.py:1058、routes_conversations.py:933） |
| 7 | 观测层异常不影响业务（fail-open 不变） | **达成** | `safe.py:13-22` `safe_call` 包住全部上报路径（spans.py:213/299/394/443）；T-E 新增 `_report_phase_spans` 整体在 `safe_call(_report)` 内（spans.py:299）、每阶段独立 `try/except`（spans.py:187/201-205）、`span.end` 置于 `finally` 配 `end_on_exit=False` 防泄漏；3 例 fail-open 专测全过：`test_one_phase_failure_does_not_block_others_or_generation`、`test_tracer_blows_up_is_fail_open_and_generates_no_child_spans`、`test_missing_create_span_attributes_helper_still_reports_generation`；T-E 后端评审 HIGH 必改项（`create_span_attributes` 顶层硬导入）已修复为 try/except 兜底（spans.py:37-40） |
| 8 | `system.query_log` 缺失报错切换后复测 | **达成** | `/Users/wjh/opt/clickhouse/config.xml` 新增 `<query_log>` 段并重启；ClickHouse `EXISTS TABLE system.query_log = 1`，已写入 1425 行；worker `V4LegacyApiUsageJob failed` 报错停止（grep count=0，T-D 落地于变更日志末段） |

### 关键现实补充（必读）

1. **langchain 链路 timings 全部为 0**：spec-013:118 规定 `OLLAMA_ROUTE` 默认 langchain；langchain 链路拿不到 Ollama 服务端 `timings.load_ms / prompt_eval_ms / eval_ms / first_token_ms`，4 阶段时长全为 0，仅 generation 主体的 `ollama-chat` 总耗时正常。**direct 链路才有真实阶段时长**。当前主服务以 `OLLAMA_ROUTE=direct` 运行是**主会话为瀑布图实证而临时改的**，未提交；spec-013 默认仍为 langchain。决策见遗留项 #1。
2. **历史 trace 不回填**：`LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL` 默认 true，但 `worker/src/env.ts:597-603` 注释明示「对 net-new 部署（无 legacy 数据）是 no-op」。dual 仅影响**新写入**；切换 dual 前已产生的 ~1769 行旧事件（events_core / events_full）**不会回填** legacy 表。**历史 trace 切 dual 后仍无详情/瀑布图**，验收与用户演示须以切换后新产生的 trace 为准（spec-041 第 52 行、技术评审 a) R4 已书面声明）。
3. **私有 API 依赖**：T-E 使用两个 langfuse 私有符号——
   - `langfuse._otel_tracer`：`spans.py:157` 用 `getattr(langfuse, "_otel_tracer", None)` + `None` 早退，SDK 升版后若该符号消失或改名，子 span 自动跳过、generation 主体仍照常上报（fail-open 不破）。
   - `langfuse._client.attributes.create_span_attributes`：原为模块顶层硬导入，破坏模块级 fail-open（T-E 后端评审 HIGH 必改项），已改为 try/except 容错（spans.py:37-40），缺失时子 span 仍照常创建，仅丢属性，generation 主体不受影响。
   - 风险：每次 langfuse SDK 升版须跑 1 次回归（33 项观测测试 + 一次真实对话），预期改动 1–5 行属性映射。决策见遗留项 #3。
4. **A5 部分达成**：冷调用 `phase:load` 5.575s、热调用 3.632s（差 ≈1.9s），方向正确但**未达 spec-013 A5「接近 0」措辞**。实测根因：Ollama `keep_alive=5m` 默认值下，模型超过 5 分钟未用才会真正卸载；只要不超过 5 分钟，热调用仍需 ~3.6s 重新初始化（KV cache 重载）。非本 spec 实现问题，属 Ollama 服务端行为。决策见遗留项 #4。

### 跨端回归汇总

| 维度 | 来源 | 结果 |
|---|---|---|
| 后端定向回归 | `041-backend-regression.md` §1 | **675 passed / 1 failed（环境） / 29 subtests passed**（含 T-B 6 例 + T-E 5 例 + KB/chat/conversation/reasoning/api 分段） |
| 后端全量回归 | 同 §3 | 未跑完（broker 沙箱 SIGTERM ~16min 后终止，2548 tests collected、error=1（langchain_openai 缺失，环境既有问题）），已用分段覆盖替代 |
| 导入 / Lint | 同 §2 | `import app OK`；ruff 改动文件 0 issues |
| fail-open | 同 §5 + §1 | 未破坏；3 例 fail-open 专测全过；实测期间 Langfuse 短暂不可用主服务对话仍正常返回 |
| 前端 | spec-041「明确不做」 | 零改动，无独立前端回归风险点；spec-013「不自研甘特图」约束通过方案 2 走原生瀑布图兑现 |
| 跨端集成 | 本报告 | 见 8 条边界表（无需重启后端；基于已落盘评审/截图交叉核对） |

### 遗留项与建议

1. **OLLAMA_ROUTE 默认值决策（建议裁决）**：
   - 现况：主服务临时 `OLLAMA_ROUTE=direct`（主会话为瀑布图实证而改），spec-013:118 默认 langchain。
   - 选项：
     - (a) **保留 langchain 默认**：与 spec-013 一致；但瀑布图/5 阶段条在 langchain 链路下无效（timings=0），**用户复现验收步骤 5 时看不到真实瀑布图**，仅单条 ollama-chat 条。
     - (b) **改为 direct 默认**：瀑布图/5 阶段条在所有调用上生效；但偏离 spec-013 默认值，须同步修订 spec-013:118。
     - (c) **保持 direct 仅用于验收演示、prod 仍 langchain**：文档明示，不改默认；用户复现时需自行 `export OLLAMA_ROUTE=direct`。
   - 建议：(b)。理由：本次 spec 的核心交付就是瀑布图可见，若默认 langchain 则等于白做；偏离 spec-013 是小成本修订，瀑布图是用户「必须看到」的硬约束。
2. **历史 trace 不回填声明**：须写入产品使用步骤（spec-041 §三）与复盘文档，避免用户拿切换 dual 前的 trace 误判 A4/A5 未达成。
3. **私有 API 升版适配清单**：每次 langfuse SDK 升版后须跑：
   - `pytest tests/observability tests/test_observability*.py tests/test_phase_spans.py -q`（33+ 例 fail-open 锁定）
   - 一次真实对话触发 + 截图核对 `/tmp/spec041-waterfall-phases.png` 形态
   - 改动预期落在 `spans.py` 1–5 行（属性映射 key）
4. **A5「冷/热 load 段接近 0」收口（建议裁决）**：
   - 选项：
     - (a) **接受当前 ≈1.9s 差作为「可区分」**：3.6s 仍远小于冷调用 5.575s，肉眼可辨；修订 spec-013 A5 措辞为「冷调用 `phase:load` 明显长于热调用」并删去「接近 0」。
     - (b) **压 Ollama `keep_alive` 至更短（30s/60s）**：需改 `OLLAMA_KEEP_ALIVE` 或部署侧默认值；会让所有非高频场景每次都重新加载、增加冷调用比例。
     - (c) **保持现状但 spec-013 A5 不动**，承认偏差；用户裁决。
   - 建议：(a)。理由：实现已达标，措辞与现实不符才是问题源头；修订 spec-013 一行措辞比改 Ollama 默认值更可控。
5. **回归覆盖缺口如实记录**：全量后端 pytest 因 broker 沙箱 SIGTERM 未跑完；环境既有问题 2 项（`test_online_model_dispatch.py` 缺 `langchain_openai`；`test_kb_candidate_rebuild.py::test_empty_library_dry_run_reports_bootstrap_without_writes` 沙箱拦截）；均非本 spec 引入。
6. **运行期配置不入库**：`vendor/langfuse/.env`、`~/opt/clickhouse/config.xml`、`backend/.env` 均被 .gitignore 忽略，不随仓库分发；`vendor/langfuse/.env.bak.20260921` 已留备份，回退可控。

## 签字

- 验收总控（tester）：________________（本验收未改代码 / 未 commit / 未 push）
- 开发主管签字：________________（留空，交架构师签署）
- 架构师签字：________________（留空）
