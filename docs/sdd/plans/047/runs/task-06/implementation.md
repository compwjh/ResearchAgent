# Spec047 Task 06（P2③）在线实时评测 + ADR0002 修订 — 实施报告

> 分支 `feature/spec-047-evaluation-p2-and-observability-fixes` ｜ 角色 `backend-dev` ｜ 顺序：② → ③（本报告为 ③，② 见 `runs/task-05/implementation.md`）

## 一句话结论

按定稿口径实现「**离线优先 + 显式开关默认关闭 + 仅对采样命中的已完成 trace 异步判官评分 + 不进 SSE 关键路径 + 同步链路零延迟增量**」的在线评测能力，并**同步追加式修订 ADR0002**。红绿契约测试 18 条通过、当前部署版本真实 E2E `verified`、开关测试后恢复默认关闭。不改 `LANGFUSE_SAMPLE_RATE`、不改观测上报、不改业务对话链路、不新增端点/SSE 事件类型、不改 `spans.py`。

## 改动清单

| 文件 | 类型 | 关键内容 |
|---|---|---|
| `backend/app/platform/config.py` | 追加（+35 行，纯新增、零删除） | `_env_unit_interval()`（[0,1] 越界/非法回退默认并告警）；`EVAL_ONLINE_ENABLED`（默认 `False`）、`EVAL_ONLINE_SAMPLE_RATE`（默认 `0.0`）、`EVAL_ONLINE_JUDGE_TIMEOUT_S`（30）、`EVAL_ONLINE_MAX_TRACES_PER_TICK`（20）、`EVAL_ONLINE_CIRCUIT_THRESHOLD`（3） |
| `backend/eval_042/online_eval.py` | 新增 | `OnlineEvalSettings` / `load_settings()`（L46/60）；`OnlineEvaluator`（L106）：`submit_completed_trace()` 非阻塞异步旁路、`poll_completed_traces()` 离线回放自动触发、后台有界队列 + worker/poller、`_evaluate_one()` 复用 `runner.run(export=...)`、独立超时 `_default_bounded_runner`（L72）、熔断、`UNAVAILABLE` 降级 |
| `tests/evaluation/test_online_evaluation.py` | 新增（文件名无 spec/task 编号） | 18 条契约测试 |
| `docs/adr/0002-*.md` | 追加式修订（+71/-1，唯一「-1」为关联行末尾补链接） | 状态补注 / 关联加 spec-047 / 决策 3 补注 / 备选表补注 / 后果补注 / 新增「修订记录」段 |
| `docs/sdd/plans/047/runs/task-06/online-eval-e2e.json` | 新增（真实 E2E 证据） | T0 默认关闭 / T1 受控窗口 / 真实 score id / traceId / 状态码 / 恢复确认 |

**未改动**：`spans.py`、`client.py`、`routes_chat.py`、`routes_kb.py`、`routes_article.py`（业务/SSE/观测链路全部零改）；`LANGFUSE_SAMPLE_RATE` / `LANGFUSE_SAMPLE_RATE_RAW` 保持原值；`runner.py` / `judge_client.py` / `report.py` / `cli.py` / `langfuse_export.py` / `human_gold.py`（全部复用、零改）；`.env`；`spec-042` 正文；spec/reviews/plans 正文（除本报告）；状态台账；045 已签字证据；`frontend/**`。

## 设计要点（对齐技术评审 §3 风险 4 / §4.3 / §5）

- **离线优先 + 默认关闭**：`EVAL_ONLINE_ENABLED=False` + 独立 `EVAL_ONLINE_SAMPLE_RATE=0.0`。关闭时 `submit_completed_trace()` 直接返回 `disabled`：不拉 trace、不启判官、不回写、不启线程（同步链路零增量）。独立采样率**绝不复用**观测上报的 `LANGFUSE_SAMPLE_RATE`。
- **触发落点（读代码后选最小落点）**：`client.py:enqueue_flush()` 是 045「flush 出 SSE」的既有后台有界队列范式；`routes_chat.py:191/214` 的 SSE 尾包是观测 flush 点，但改它会进业务/SSE 链路（禁止）。故选**自包含后台 poll/worker 旁路**：`poll_completed_traces()` 拉取 Langfuse 中**已完成 trace**（`list_ollama_chat_trace_ids` 离线回放），按独立采样触发，本质是 Q2=A 离线回放「自动触发」变体，非「每次对话都评」。不改 `spans.py` / 观测上报 / 业务链路 / 端点 / SSE 事件类型。
- **同步零增量 + 异步**：`submit_completed_trace()` 只做 `put_nowait`（O(1) 非阻塞），判官与回写全部在后台守护线程；队列满丢弃并告警，不阻塞业务。
- **全部复用 eval_042、不建第二套**：`_evaluate_one()` 通过 `runner.run(export=...)` 复用 `judge_client` 判官 / `ReportWriter` 报告 / `post_score_idempotent`（`post_score`+`find_score_by_id`）回写；未自建判官/评分/回写框架。
- **判官不可用 → UNAVAILABLE，绝不记 0 分、不冒泡**：runner 既有 `_judge_unavailable_record` 语义 + 本模块 `_interpret()`/`_unavailable()`（score=None，不写 score），任何异常 `try/except BaseException` 吞掉并记日志（fail-open）。
- **独立超时/熔断**：`EVAL_ONLINE_JUDGE_TIMEOUT_S` 由守护线程 `join(timeout)` 独立包裹单次评分；连续失败达 `EVAL_ONLINE_CIRCUIT_THRESHOLD` 打开熔断（冷却 30s），期间跳过评测并记日志。日志只记异常类型名，不落原始异常文本（回归清单 §14）。

## 红 → 绿（真实输出）

- RED①：`pytest tests/evaluation/test_online_evaluation.py -q` → `EXIT=2`，`ImportError: cannot import name 'online_eval' from 'backend.eval_042'`（模块/开关未实现）。
- RED②（追加 poller 自动触发）：`-k poller` → `2 failed`，`AttributeError: 'OnlineEvaluator' object has no attribute 'start_background_poller'`。
- GREEN：实现后 `16 passed`（初版）→ `18 passed in 0.36s`（含 poller），`EXIT=0`。
- 回归：`tests/evaluation/` → `206 passed in 1.03s`，`EXIT=0`。
- lint：改动 5 个 .py → `All checks passed!`（`EXIT=0`）；`py_compile` OK；`import backend.app` + eval_042 全模块导入 OK；CLI 默认输出形状 smoke 不变。

## 测试覆盖（4 类定稿口径 + 附加）

1. 默认关闭零评分：`test_default_off_produces_zero_scoring` / `test_disabled_never_enqueues_even_with_full_sampling`（判官零调用、队列空）。
2. 开关打开且采样命中异步写 score：`test_enabled_sampled_writes_score_via_existing_runner`（复用真实 runner 写 1 条 score）、`test_background_worker_is_async_and_submit_adds_no_sync_calls`（判官在后台线程、submit 立即返回）、`test_background_poller_auto_triggers_when_enabled`。
3. 判官失败不记 0 分且不冒泡：`test_judge_unavailable_never_writes_zero_and_never_bubbles`、`test_runner_exception_marks_unavailable_and_never_bubbles`、`test_independent_timeout_marks_unavailable_without_zero`。
4. 同步链路不增加调用：`test_synchronous_submit_never_invokes_runner`（只入队、零同步判官调用）。
5. 附加：配置默认值 + 边界回退（越界/NaN/非数字告警回退）、`LANGFUSE_SAMPLE_RATE_RAW` 未改、采样门、`load_settings` 鸭子类型、熔断、有界队列丢弃、`poll` 单批有界与默认关闭 noop、配置读取。

## ADR0002 追加式修订摘要（明确未改 spec-042）

- **状态行**追加「2026-11-09 由 spec-047 部分修订」；**关联 `:5`** 加 `spec-047` 链接（唯一「删除」行即为此行末尾补链接，原有 3 个链接逐字保留）。
- **决策 3 `:45-48`** 以引用补注追加 P2 三项承接（① gold 集/human_agree_rate ② 单向 quality_score→Langfuse score 映射 ③ 在线实时评测）及 ③ 的前提条件（默认关闭/异步/零延迟增量/不改 SAMPLE_RATE 与观测上报/不新增端点与 SSE 事件类型）；「顺序不能颠倒」已满足、默认仍关闭。原结论一字未改。
- **备选表 `:62`** 后补注：该行是 045 期判断（在该期范围内继续成立），047 期为「离线回放自动触发变体」有限开放；表格任何行未改。
- **后果 `:78-81`** 后补注：`human_agree_rate`（有真实 gold N≥20 时计算、否则恒 null）与两套分数改为**单向映射**（业务表不反写、不迁历史）部分解除；「双向统一留待后续」在双向范围内继续成立。
- **新增「修订记录（2026-11-09，spec-047 部分修订）」段**：写明**两处冲突**——① 本 ADR 决策 3（及备选表/后果）；② `spec-042:76` Q2=A 离线回放 / `:162` 不改业务链路·不改 `LANGFUSE_SAMPLE_RATE`·不改观测上报 / `:163` 第一期不做在线实时旁路评测（另列 `:299-304,344` 与 Q2 选项 C 被否决）；并给出**兼容论证**（数据来源仍是回放已完成 trace、仅放宽触发时机；默认关闭+异步+零同步增量满足 :163；独立采样率+只读既有 trace+不改 spans.py+不新增端点/SSE 类型满足 :162；复用 eval_042 不建第二套；UNAVAILABLE 不记 0 分）。
- **明确边界**：`spec-042` 正文 Q2/163 边界说明是否补注**未获本轮授权**，`spec-042` 正文保持原状（本任务未修改），兼容论证只由 ADR 修订记录段 + `047-tech-review.md` 承载；不翻 045 决策史、不改 045 已签字证据。修订为追加式，可整体回退。
- 核实：`git status` 显示 `docs/sdd/specs/042-*.md` 无改动；ADR `git diff` 仅 1 行「关联」原位补链接，其余 71 行为纯新增。

## 真实 E2E（当前部署 Langfuse :3000 + chat :8000）

产物：`docs/sdd/plans/047/runs/task-06/online-eval-e2e.json`（`final_status: verified`）。凭据取自 `.env`（`LANGFUSE_PUBLIC_KEY/SECRET_KEY`，仅注入本进程 `LANGFUSE_PK/SK` 环境变量，未打印、未改 `.env`）；**真实判官** `qwen3.5:9b`（真实 Ollama，无 fake judge）、**真实回写**（非 mock）；仅用 `offline_urlopen` 探针记录真实 `response.status`。

| 阶段 | 项 | 值 |
|---|---|---|
| T0 默认关闭 | 开关 | `EVAL_ONLINE_ENABLED=False`（默认，无 .env 改动 / 无服务重启） |
| T0 | 真实 chat | `POST /api/chat` → **200**，SSE 收到 `done` |
| T0 | `chat_quality` 评测分计数 | before 27 → after 27，**delta=0**（`bypass_submit_while_off=disabled`）；verdict `no_new_online_eval_score` |
| T0 | 全部 score 计数 | 1793 → 1800（+7 = `spans.py` 观测指标分，既有行为，非在线评测分，artifact 已注明） |
| T1 受控窗口 | 开关 | `EVAL_ONLINE_ENABLED=true` + `EVAL_ONLINE_SAMPLE_RATE=1.0`（进程内 env/config 属性，`try/finally` 恢复） |
| T1 | 真实已完成 traceId | `abfe474ba20272ba230a02327bf73024`（真实 `ollama-chat`，output 非空、status=scored） |
| T1 | 异步触发 | `submit_completed_trace()` → `queued`（非阻塞，无同步判官调用），后台 worker `scored=1`、`wait_idle=true` |
| T1 | 真实 score id | `eval042-a4375d60c269e404f0573286bc7d44b2`（`chat_quality`，NUMERIC，value=1） |
| T1 | 状态码 | exact-ID 先查 404 → `POST /api/public/scores` **200** → 回查 404…→ **200**（ingestion 延迟，runner 既有有界重试） |
| T1 | exact-ID 回查 | `GET /api/public/scores/{id}` → **200**，`id/name/value/dataType/traceId` 全部一致；`chat_quality` 总数 27→28（恰好 +1） |
| 恢复 | 默认关闭 | `EVAL_ONLINE_ENABLED=False` / `SAMPLE_RATE=0.0`；env 无 `EVAL_ONLINE_ENABLED`；`.env` 无 `EVAL_ONLINE*` 键；fresh process 复核默认关闭；verdict `restored` |

## 精确回归（真实命令 / 退出码 / 通过数）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `.venv/bin/python -m pytest tests/evaluation/ -q` | 206 passed in 1.03s | 0 |
| `.venv/bin/python -m pytest tests/system/test_bench_routes.py -q` | 7 passed | 0 |
| `.venv/bin/python -m pytest tests/system/test_benchmark_summary_card.py -q` | 9 passed | 0 |
| `.venv/bin/python -m pytest tests/observability/ -q` | 45 passed | 0 |
| `.venv/bin/python -m ruff check <5 个改动 .py>` | All checks passed! | 0 |
| `.venv/bin/python scripts/check_test_layout.py` | **EXIT=1**：4 条存量违规 | 1（非本任务引入） |
| `.venv/bin/python -m py_compile <3 个改动 .py>` | OK | 0 |
| `import backend.app` + eval_042 冒烟 / CLI 输出形状 | OK / 不变 | 0 |

**未跑全量回归**（按要求）。conftest 在本环境正常加载，无 `langchain_ollama` 报错，未使用 `--confcutdir`。

`check_test_layout.py` 存量违规（如实说明，均为已跟踪文件、本任务未改、与本次新增测试无关）：`tests/evaluation/test_task03_reproducibility.py`、`tests/evaluation/test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py`。本次新增的 `test_score_mapping.py`、`test_online_evaluation.py` 文件名不含 spec/task 编号，未引入新违规。

## 风险与阻塞

- **触发落点为自包含后台 poll/worker 旁路**，未硬接线进 SSE/业务/观测链路（这是「不改业务对话链路 / 不进 SSE / 同步零增量 / 不新增端点与 SSE 事件类型」的必然结果，亦符合技术评审「离线回放自动触发变体」定性）。开关默认关闭，开启需受控窗口显式驱动 `poll`/`submit`。
- **默认关闭恢复已确认**：开关仅以进程内受控窗口打开，`finally` 恢复；`.env` 未改、无服务重启；fresh process 复核 `EVAL_ONLINE_ENABLED=False`。
- 真实 E2E 使用真实判官与真实 Langfuse 回写；`offline_urlopen` 仅记录状态码，非 mock。T0 的 `all_scores` +7 为 `spans.py` 既观测指标分，已与在线评测分明确区分。
- `research_model_outcomes` 仍为 0 行，② 以等价只读样本验证；本任务专注 ③。
- 无阻塞；未越界（未碰 `frontend/**`、`spans.py`、观测上报、`human_gold.py`、`.env`、spec/reviews/plans 正文〔除本报告〕、状态台账、045 证据、`scripts/setup_langfuse_dashboards.py`）；未 git commit/push/合 main；未跑真实 `--force` 重跑。
