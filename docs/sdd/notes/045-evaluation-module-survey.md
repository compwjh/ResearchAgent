# Spec-045 调研记录（一）：测评 / 评测模块

> 调研方式：只读检索（code-explorer 子代理 66 次工具调用 + 主会话交叉验证）。
> 调研日期：2026-11-08。本文是 spec-045「背景与依据」F 系列事实的证据底稿，不做推测。
> 代行留痕：本文件为纯文档改动，由主会话代行（符合 `AGENTS.md:127` 唯一允许的代行条件），
> 三处留痕分别为本文头部、`spec-status-changelog.md` 的 045 条目、spec-045 的「代行记录」小节。

## 1. 入口

**HTTP 触发端点不存在。** 对 `backend/app/api/` 全量搜索 `bench|eval|score` 只命中无关词
（`routes_literature_maps.py:789` 的 `revalidate`、`routes_tools.py:84` 注释里的「不 eval」）；
对整个 `backend/` 搜 `bench` 返回 0 结果。`docs/sdd/specs/042-openeval-agent-evaluation.md:142,166`
与 `docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:26` 明确「不新增主服务业务端点」。

唯一与「打分」沾边的 HTTP 入口是路由策略质量门禁，不是评测：

- `backend/app/api/routes_research_routing.py:41-65` — `POST /research-routing/policies/{version}/evidence`，
  请求体 `min_quality_score / min_samples / min_schema_valid_rate`，服务端从已存 outcomes 汇总签发不透明 `evidence_id`。
- 同文件 `:67-88` 激活策略、`:104-166` 只读 status、`:169-225` 决策分页查询。

**CLI / 脚本（真正入口）**

- 主入口 `python -m backend.eval_042.cli`：`backend/eval_042/cli.py:64-87`
  （`--dataset` 与 `--export` 互斥、必填 `--output-dir`、`--task/--primary/--fallback/--repeats/--max-items`）、
  `:190-227` 调用 `runner.run` 并只输出一行脱敏 JSON。
- 历史兼容包装 `docs/sdd/plans/042/task-02-run-eval.py:1-18,53-95` — 把旧 `--out` 翻译成
  `--output-dir` 后委托 canonical CLI，注释明确「no longer owns a second evaluation implementation」。
- 旁路统计 CLI：`backend/eval_042/consistency.py:117-150`（判官自一致/跨判官一致/Go-No-Go）、
  `backend/eval_042/langfuse_export.py:373-405`（导出数据集到默认
  `docs/sdd/plans/042/task-02-eval-dataset.json`）、`backend/eval_042/memory_probe.py:231-361`（20 条合成探针门禁）。
- 性能基准：`scripts/bench_ollama_routes.py:139-176`（`--runs/--routes/--json`）、
  `docs/sdd/plans/031/artifacts/task-02/ollama-topology-benchmark.py:1-38`
  （1–4 Worker 冷/热拓扑基准，自述「This is an artifact, not production code」）。

**前端视图与交互**

- `frontend/index.html:318-323` — `<details class="research-benchmark-card" id="research-benchmark-section" open hidden>`，
  仅 3 个只读节点（state / policy / metrics），**没有任何按钮或触发评测的交互**；样式 `frontend/styles.css:3664-3701`。
- `frontend/research-tasks.js:108-120` 指标白名单（`median_ttft_ms` / `throughput` /
  `peak_memory_bytes` / `failure_rate` 及别名与数值上下界）；`:564-602`
  `normalizeBenchmarkSummary` / `benchmarkSummaryFromState` 只从 `state.selectedTask.benchmark_summary`、
  事件 `payload.benchmark_summary` 读；`:1527-1564` `renderBenchmarkSummary` 纯展示，
  无数据时写死「当前任务没有受控基准指标。」；调用点 `:2536,3360`。
- **主会话交叉验证结论**：`backend/` 中 `benchmark_summary|median_ttft|peak_memory_bytes` 搜索 **0 命中**，
  即后端没有生产该字段的入口，这个卡片在真实运行中恒为空态。

## 2. 核心实现

关键文件（`backend/eval_042/`，10 个）：`cli.py`（参数/脱敏）、`config.py`（常量）、
`runner.py`（编排，760 行）、`judge_client.py`（判官调用与解析）、
`langfuse_export.py`（trace→EvalItem、score 读写）、`offline_guard.py`（受控 HTTP）、
`report.py`（JSON+MD 落盘）、`consistency.py`、`memory_probe.py`。

**打分逻辑 = 本地 LLM-as-judge + 规则映射，不是规则打分，也不是人工标注**

- 硬编码分数表 `backend/eval_042/config.py:33-41`：
  `chat_quality {good:1.0, partial:0.5, poor:0.0}`、
  `memory_correctness {remembered:1.0, partially_remembered:0.6, forgotten:0.2, fabricated:0.0}`；
  `:43-81` 两段 R4 范式 prompt，强制输出 `Explanation: …` / `Answer: <枚举>`，
  注释直言「判官只输出枚举，分数由本脚本映射，避免弱模型打数值分」（`:33`）。
- `backend/eval_042/judge_client.py:37-57` `parse_r4` 正则抽取并校验枚举、
  `:60-76` POST `{OLLAMA_BASE}/api/chat`，`think:False / temperature:0 / num_predict:160 / stream:False`，
  timeout=180；`:79-115` 单次与 `repeats` 次调用，任何异常/解析失败返回 `status=unavailable`，**不记 0 分**。
- `backend/eval_042/runner.py:471-515` — 3 次标签全部 scored 且分数在 0..1 才继续，
  `Counter(...).most_common(1)` 多数投票 → `enum_to_score` → 记录 label/score/explanation。
- 一致性门禁：`backend/eval_042/consistency.py:71-114`
  （自一致率 ≥0.90 → adopt 9b，否则 fallback 27b，否则 no-go）；
  `backend/eval_042/memory_probe.py:278-321`（G1/G2/G3 三门禁 + 裁决链）。
- 明确承认**无人工标注**：`backend/eval_042/report.py:225-233` 强制
  `human_agree_rate=None / constructed_gold_only=True`；
  `backend/eval_042/consistency.py:136-142` 注释「需架构师标注 N 条 gold 标签后回填 reference
  文件再算；本自动跑不伪造人工一致率」；`memory_probe.py:354-356` 构造 gold 非人工标注。
- 性能基准另有一套纯规则指标：`scripts/bench_ollama_routes.py:41-68` 对 `derive_metrics`
  结果取均值、固定 `diff = langchain - direct`（`DIFF_KEYS=ttft_ms/client_wall_ms/overhead_ms/total_ms`）。

**测试用例 / 数据集来源**

- 主数据源是 Langfuse 真实 trace（只读 public API）：`langfuse_export.py:263-280`
  按 `name=ollama-chat&orderBy=timestamp.desc` 分页拉最多 200 条；`:283-365`
  默认 `n_scoreable=20 / n_blank_samples=2 / n_intake_fixtures=0`，按 output 长度倒序优先长回答（`:319`），
  空输出/Intake 文案/缺 prior_context 归入 skipped（`:161-187`）。
- 冻结的本地数据集 `docs/sdd/plans/042/task-02-eval-dataset.json:1-45` — 真实 trace 导出的 JSON 数组，
  字段 `trace_id/task/input/output/reference/trajectory/status/skip_reason/synthetic`，
  里面含完整 system prompt、历史对话、长期记忆原文（隐私敏感）。
- 硬编码合成数据：`backend/eval_042/memory_probe.py:41-186` 20 条中文记忆探针（四类 gold 各 5 条）；
  `langfuse_export.py:355-363` 合成 Intake 文案 fixture（须显式 `include_synthetic=True`）。
  `runner.py:208-211,684-687` 拒绝「纯 synthetic」数据集，防止冒充真实导出。
- 门禁指标来源：`docs/sdd/plans/031/artifacts/task-02/benchmark-raw.json` + `benchmark-report.md:28-35`；
  reranker 质量集是人工冻结的 10 题（`docs/sdd/reviews/014-reranker-benchmark.md:11-30`），与 eval_042 无代码关联。

**结果持久化**

- ① Langfuse score（一等落点）：`langfuse_export.py:65-78` POST `/api/public/scores`，
  body `name / value / traceId / comment / observationId(可选)`，响应必须含非空 `id`；
  `:113-135` 用 exact-ID `GET /api/public/scores/{id}` 回查（404 = 尚未可见）。
  项目自身不建 score 表，表在 vendor Langfuse。
- ② 本地权威产物 `report.json` + `report.md`（`report.py:22-24,431-517`）：
  `schema_version=agent-evaluation-report-v1 / status / started_at / finished_at / metadata / summary / items / errors`，
  item 含 `trace_id, task, status, judge_model, label, score, explanation, score_id, requested,
  expected_value, written, post_status, verified, verified_value, verification_status, errors`；
  Markdown 由同一 sanitize 模型渲染（`:269-365`），spec 要求「不保存 trace 原文/prompt/raw completion/凭据」
  （`docs/sdd/specs/042-openeval-agent-evaluation.md:236`）。
- ③ 非评测但同名打分字段的业务 SQLite 表：
  `backend/app/research/infrastructure/research_store.py:846-857`
  `research_model_outcomes(decision_id, owner_id, schema_valid, quality_score, ttft, duration, tokens, error_code, created_at)`；
  `:879-889` `research_routing_gate_evidence(...)`。写入口
  `backend/app/research/application/routing_observation.py:381-407` `record_outcome`、
  `:464-514` `issue_activation_evidence`。评测**不写业务库**
  （spec 边界 8，`docs/sdd/specs/042-openeval-agent-evaluation.md:154`）。

## 3. 端到端数据流（一次离线评测）

1. 触发 `python -m backend.eval_042.cli --dataset … | --export --output-dir …`（`cli.py:69-87,190-215`）；
   `--export` 才走 `langfuse_export.collect_eval_items(task=…)` 的 lambda（`:205`）。
2. `runner.run` 先建 `ReportWriter` 并**立即写 running 骨架**（`report.py:434-441`），保证坏输入也有产物；
   `metadata` 只记 task/judge/fallback/repeats/max_items/source（`runner.py:658-666`）。
3. `_load_source` → `_validate_items`（`runner.py:215-228,171-212`）：校验必填 6 字段、
   task 白名单 `KNOWN_TASKS={chat_quality, memory_correctness}`（`:26`）、
   status 只能 scored/skipped、拒绝全 synthetic。
4. 逐条串行（`runner.py:689-740`）：memory 缺 `prior_context` → `SKIPPED/no_prior_context`；
   `classify_output` 空/Intake → SKIPPED；`synthetic=True` → 一律 `SKIPPED/synthetic_fixture`（`:708-716`）。
   SKIPPED 不调 judge、不写 score。
5. `_score_item`（`:449-575`）：`judge_repeats(primary, task, q, a, repeats, ctx=…)` ×3 → 全 scored
   且分数合法 → 多数标签 → `enum_to_score` → checkpoint 记录 `requested/expected_value` →
   **POST score 恰好一次**（`:530-541`）→ `_verify_score_details` 最多 6 次、退避 1/2/3/4/5s，
   精确比对 `id/traceId/name/value`（`:364-430,557-574`）→ 写回
   `written/verified/post_status/verification_status`。
6. 任一 `unavailable/failed` 置 `overall_failed=True`（`:728-739`），最终
   `writer.finish("completed"|"failed")`（`:742-745`），`_result` 映射
   `exit_code = 0 if completed else 1`（`:578-596`）；CLI `_emit_result` 打印一行 JSON 并返回退出码
   （`cli.py:162-187`）。
7. 旁路依赖链：业务请求经 `backend.app.platform.observability` 埋点 → Langfuse trace
   （`scripts/gen_observability_samples.py:40-47` 生成样本）→ 上面的导出；
   `scripts/bench_ollama_routes.py:31` 直接 import `derive_metrics` 从同模块取性能指标。
   前端 benchmark 卡片只看 task/event payload 的 `benchmark_summary`（`research-tasks.js:591-602`），
   后端无生产端。

## 4. 现有测试覆盖与明显缺口

| 文件 | 关键断言 |
|---|---|
| `tests/evaluation/test_agent_evaluation.py:11-74` | 空/Intake → SKIPPED、真实短回答仍 scored、R4 解析大小写/尾点/非法标签、枚举→分数、loopback 白名单拒绝 `8.8.8.8`/`api.openai.com` |
| `tests/evaluation/test_memory_probe.py:20-120` | 20 条探针、4 类各 5、probe_id 唯一、`synthetic=True`、build_probe_dataset 与 EvalItem 兼容、chat_quality prompt 未引入 `{ctx}`、三个阈值恰为 0.80/0.80/0.90 |
| `tests/evaluation/test_evaluation_cli.py:59-243` | 旧 `--out` 缺值/参数非法/坏 JSON 均非零且落双报告；未知参数不回显 `sk-*` token 与 URL 密码；两个 CLI 从任意 cwd `--help` 可用；legacy 脚本不触发 runner/post |
| `tests/evaluation/test_offline_transport.py:95-510` | 非 HTTP/non-loopback/userinfo 在 opener 之前被拒；环境 proxy 不生效且不改全局 opener；300/301/302/303/307/308 全拒绝；GET 仅瞬态错误最多 3 次；**score POST 恰好一次且不重试**；prior_context 只读显式字段；空真实导出不被 synthetic 掩盖；exact-ID GET 而非列表；404 视为不可见 |
| `tests/evaluation/test_evaluation_report.py:41-351` | running 骨架、双投影字段一致、finish 终态、写失败回滚且清理 tmp、二次 replace 失败恢复 pair、敏感字段/嵌套 metadata 冒充人工标注被过滤、Markdown 转义、`human_agree_rate` 恒 null |
| `tests/evaluation/test_evaluation_runner.py:75-896` | 成功路径 POST 一次 + exact 四字段核验 + summary 精确值；延迟可见性 3 次退避 `[1,2]`；永久 404/非可见性错误快速失败；ctx 传递不猜上下文；缺 ctx/空输出 skip 且不调 judge/post；explanation 源文回显脱敏；逐条 checkpoint；部分 judge 失败 → UNAVAILABLE 不记 0；post 失败/缺 score_id/字段 mismatch 均非零并保留本地报告 |
| `tests/system/test_bench_routes.py:91-181` | 默认 langchain+direct、2 轮各 2 样本、avg 含 4 指标、`diff` 严格等于 langchain−direct、langchain 无 timings 时 overhead=0、缺 total 如实为 0、单 route 抛异常记 errors 但另一 route 仍有结果（注释「禁止真实调用 Ollama」，`:3-5`） |
| `tests/research/test_routing_benchmark_contract.py:18-75` | 离线校验 031 artifact 的 schema/worker_counts=[1,2,3,4]/provenance/固定 prompt sha256，并断言 harness 源码字符串契约（`trust_env=False`、`"think": False`、`"backend.app" not in source`）——即只测历史产物，不跑基准 |

**明显没覆盖的边界**

- 真实 Ollama / Langfuse E2E：全部用 mock/内存 response；
  `docs/sdd/specs/042-openeval-agent-evaluation.md:238` 自认「当前未实测 Langfuse UI 的具体 selector…仍标记待验证」，
  `docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:92` 明确「测试只使用 mock/fake transport」。
- `runner.run` 的 **fallback 从不生效**：`fallback` 只写进 metadata（`runner.py:637,662`），
  `_score_item` 只接 `primary`（`:452,718-726`）；没有任何测试断言判官不可用时会切到 27b。
- `consistency.run`、`memory_probe.run_probe`、`langfuse_export.collect_eval_items` 的编排逻辑几乎无测试，
  三个门禁阈值无回归护栏。
- 并发/多进程同 `--output-dir`、报告文件锁、score 幂等与重复写入、POST 后结果未知的恢复路径
  （spec 只让人肉核对，`docs/sdd/specs/042-openeval-agent-evaluation.md:226`）。
- judge 超时（180s）、超长/非 UTF-8 input、分页 >200 条 trace、`list_scores` 多页、
  模型版本漂移、多数投票平票。
- 前端 benchmark 卡片的真实数据渲染（后端无数据入口，也没有契约测试）；
  `scripts/bench_ollama_routes.py` 的真实 `run_chat`（测试明确禁止真实 Ollama）。

主会话量化：`tests/evaluation/` 下 `def test_` 计数 **85**。

## 5. 代码中可见的问题

**硬编码常量（集中在 config，散落各处）**

- `backend/eval_042/config.py:11-14` 明文 dev 凭据 `pk-lf-local-dev-0001 / sk-lf-local-dev-0001`
  与 loopback 端点；`:20-31` 模型名 `qwen3.5:9b` / `qwen3.8:27b`、`REPEATS=3`、
  三个阈值 0.90/0.80/0.80；`:33-41` 分数映射；`:83-85` `INTAKE_MARKERS`、`MIN_ANSWER_CHARS=1`。
- `judge_client.py:60-67` timeout=180、`num_predict=160`；`offline_guard.py:143-144` 3 次 / 0.05–0.1s；
  `runner.py:28-29` 6 次 / 1–5s；`langfuse_export.py:263-285` limit 100/200、默认 20/0/2；
  `scripts/bench_ollama_routes.py:33-38` 默认问题、routes、`_ROUND=3`；
  `memory_probe.py:41-186` 20 条中文探针全硬编码。

**重复实现**

- 脱敏正则三套：`cli.py:30-39`、`runner.py:30-49`、`report.py:112-126`
  （同一 `_URL_USERINFO_RE`/`_SECRET_ASSIGNMENT_RE` 各写一遍）。
- skip 判定两处：`langfuse_export.py:161-187` `classify_output` 与 `runner.py:698-717`
  的 `_skip_record` + 二次判断。
- judge 编排/一致性统计三套：`consistency.run`（`:35-114`）、`memory_probe.run_probe`（`:231-361`）、
  `runner._score_item`（`:449-575`），且门禁裁决逻辑在 `consistency.py:103-108`
  与 `memory_probe.py:300-321` 重复但 runner 不用。
- 两套 CLI（canonical + `task-02-run-eval.py:53-89` 参数翻译）、
  两套 benchmark harness（`scripts/bench_ollama_routes.py` 与 031 artifact 的 `ollama-topology-benchmark.py`）。

**同步阻塞 / 缺超时与重试 / 无取消**

- 全链路同步 urllib：`judge_client.py:68-73` → `offline_guard.py:126-140`；
  `runner.py:689-740`、`consistency.py:44-56`、`memory_probe.py:248-276`、
  `bench_ollama_routes.py:83-100` 全是串行 for 循环。每条最坏 =
  3×180s judge + 6×(30s+5s) 验证，20 条无全局 deadline、无进度 UI
  （`docs/sdd/specs/042-openeval-agent-evaluation.md:221` 承认「CLI 当前没有额外进度 UI；以终端进程退出为完成信号」）。
- judge POST 有 180s 超时但**零重试**；`offline_guard.py:199-218` 的 POST 不重试是刻意的
  （注释「未知写入结果必须交给上层报告为失败，不能自动重放造成重复 score」），
  但 judge 调用复用同一 `http_post_json`，网络抖动即整条 UNAVAILABLE。
  GET 有 3 次重试但 timeout 固定 30。唯一并发实现是 031 harness 的 `concurrent.futures`。

**并发安全 / 结果可复现性**

- `report.py:443-503` 用 `os.replace` 原子写单文件 + 有界回滚，但**无文件锁**：
  多进程共用 `--output-dir` 时，回滚基于自己读到的快照，会覆盖对方已发布的文件。
- Langfuse score 无幂等键、无「先查后写」；重跑同一 trace 会产生重复 score。
- 可复现性只做到 `temperature:0 / think:False / num_predict:160`（`judge_client.py:62-66`），
  **没有 `seed`**；报告 metadata 不记录模型 digest、prompt hash、数据集 hash（`runner.py:658-666`）；
  导出按 `timestamp.desc` + output 长度倒序（`langfuse_export.py:267-268,319`），
  运行中业务持续产生新 trace 会让数据集漂移；多数投票用 `Counter.most_common(1)`，
  平票依赖 dict 插入顺序（`runner.py:490`）；报告刻意不保存 q/a/raw，无法离线复算。

**与观测模块的耦合**

- 评测完全寄生 Langfuse：`config.py:11-13` 硬编码地址/凭据，`langfuse_export.py:267`
  依赖 trace 名 `ollama-chat`、`post_score` 依赖 `/api/public/scores` 的响应 `id`（`:74-77`）；
  `docs/sdd/specs/042-openeval-agent-evaluation.md:97` 承认内置 evaluator 在本机 Ollama
  因不支持 `response_format: json_schema` 而不可用（F17），才被迫自建判官。
- `scripts/bench_ollama_routes.py:31` 直接 import `backend.app.platform.observability.derive_metrics`；
  `scripts/gen_observability_samples.py:40-47` 依赖
  `start_trace/end_trace/record_ollama_generation/derive_metrics`。
  观测字段或采样变更会同时打断基准与评测。
- 业务 `quality_score`（`research_model_outcomes`）与 Langfuse score 是两套互不相认的分数口径，无映射代码。

**文档承认的局限**

- `docs/sdd/specs/042-openeval-agent-evaluation.md:7`：「旁路 token 与真实人工标注仍属已声明后续边界，
  `human_agree_rate` 未评估」；`:155` 承认 Task02 遗留 L2 跨判官一致率 0.5 是「输入不适定」；
  `:163-165` 第一期不做在线实时评测、不追求绝对分数对齐。
- `docs/sdd/retro/2026-10-23-spec042-offline-evaluation.md:12`：首次真实运行因 v1 score 列表
  不支持 `traceId` 过滤导致验证失败，改用 exact-ID 读取；`:22` 构造 gold 不作人工标注。
- `docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:29`「不建立真实人工标注平台」；
  `docs/sdd/reviews/014-reranker-benchmark.md:8` 标注部分验证未执行；
  `docs/sdd/plans/031/artifacts/task-02/benchmark-report.md:11,41` 多实例 NO-GO / blocked。
- `docs/sdd/TOOLCALL_BENCHMARK.md:7` 自述探针脚本「一次性，不入库」，即工具调用能力基准从未进入自动化测试。

## 6. 主会话交叉验证（2026-11-08）

| 断言 | 验证方式与结果 |
|---|---|
| 前端基准卡片恒为空态 | `grep -rIl 'benchmark_summary' backend/` 命中文件数 **0** |
| `--fallback` 不生效 | `grep -n fallback backend/eval_042/runner.py` 仅 `:637`（签名）与 `:662`（metadata） |
| 评测与观测测试规模 | `tests/evaluation` 85 个 `def test_`；观测侧约 54 个 |
| 业务 outcome 链路未跑通 | 实测 `research_routing_decisions` 20 行，`research_model_outcomes` **0** 行、`research_routing_gate_evidence` **0** 行 |
| Langfuse 当前关闭 | `backend/app/platform/config.py:122` 默认 false；根 `.env` 无 `LANGFUSE_*`；运行进程环境无该变量 |

## 7. 最值得改进的 5 点（调研方建议，供 grill 裁决）

1. **冻结可复现基线**：数据集改用固定时间窗+稳定 ID 排序并计算 SHA256，判官请求加 `seed`，
   报告 metadata 写入模型 digest / prompt hash / 数据集 hash。理由：当前
   `timestamp.desc` + 按输出长度排序、无 seed、`most_common(1)` 平票不定，
   而 spec 目标正是「建立相对回归基线」，跨运行根本不可比。
2. **让 fallback 真正生效并合并三套 judge 编排**：规格与实现不一致，且三份编排重复维护，
   最容易产生行为漂移。
3. **报告目录加锁 + score 幂等/去重**：并行跑多任务评测会互相破坏报告；
   重跑产生重复 Langfuse score，而 spec 已把「避免重复写入」推给人工核对。
4. **补真实 E2E / 并发 / 超时取消测试，并给 judge 加全局 deadline 与有界重试**：
   85+ 用例全为 mock；串行 20 条 × 3 judge × 180s + 6 次验证无 deadline、无进度反馈。
5. **打通或删除前端 benchmark 卡片，并统一分数口径**：造了 UI 却没有生产数据入口；
   同时业务 `research_model_outcomes.quality_score` 与 Langfuse score 两套分数无任何映射。
