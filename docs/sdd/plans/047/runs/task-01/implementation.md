# Spec047 Task-01 交接报告（backend-dev）

> 分支 `feature/spec-047-evaluation-p2-and-observability-fixes` ｜ 角色 backend-dev ｜ 2026-11-09
> 关联：[task-01 计划](../../task-01-observability-metrics-fix.md) ｜ [047-tech-review §3 风险1](../../../../reviews/047-tech-review.md) D3 定稿 ｜ 只读调查 B 节
> 纪律：TDD 先红后绿；只改上报层；不改 0 契约 / diff / 7-score 数量 / 19.735 证据 / SSE / 公开接口。

## 一、结论

按【已定稿的 D3 方案】4 点严格落地，**红→绿通过**，未走退化路径（SDK 实测支持 `comment`）。
只改 3 个文件：`backend/app/platform/observability/spans.py` + 2 个既有测试文件；无前端 / scripts / .env / spec 正文 / 状态台账改动。

## 二、D3 定稿方案落地逐条对照

| # | 定稿要求 | 落地 |
|---|---|---|
| 1 | `timings_available===False` 时 `phase:overhead` 改零长 `(end_ms,end_ms)`；True 时四段边界公式逐字节不变 | `spans.py` boundaries 列表定义**逐字未动**；仅在其后 `metrics_available = result.timings_available is not False`，`if not metrics_available: boundaries[-1]=("phase:overhead", end_ms, end_ms)`。True 分支不进入 if，公式零改动 |
| 2 | 经既有 helper 打独立 OTel span attribute `metrics.available=true\|false`；禁止写进 metadata | 扩展既有 `_set_phase_span_attributes`（原 :193-204）加第 3 参 `metrics_available: bool`，内部 `span.set_attribute("metrics.available", metrics_available)`。4 个 phase span 统一携带；`_build_metadata` 未碰 |
| 3 | 7 个 `generation.score` 名字/数量/值全不变，只附稳定 `comment` | score 循环 `name/value/data_type/SCORE_METRICS` 逐字未动，仅新增 `comment=score_comment`（`metrics_available=true\|false`）。SDK 支持 comment → 主路径 |
| 4 | 不改 `derive_metrics` 0 契约 / diff / benchmark_summary / SSE / 公开接口 / `SCORE_METRICS` | 全部逐字未动（见 §六 git diff） |

## 三、改动清单（路径 + 关键行）

- `backend/app/platform/observability/spans.py`（+25/-1，diff stat 25 行变更）
  - `:193-209` `_set_phase_span_attributes(span, phase_name, metrics_available)`：新增 `span.set_attribute("metrics.available", ...)`。
  - `:267-273` `_report_phase_spans`：新增 `metrics_available` 判定 + False 时 overhead 覆写零长。
  - `:292` helper 调用同步传参。
  - `:403-417` score 循环：新增 `score_comment` + 每个 score 附 `comment=`。
- `tests/observability/test_phase_spans.py`（+61）：新增 `PhaseSpanCaptureTests.test_overhead_zero_length_when_timings_unavailable`（False 样本：overhead 零长 / 4 span 名 / 首段及全部段不超墙钟 / `metrics.available=False` / metadata 未污染）。**现有全部 True 用例逐字未动。**
- `tests/system/test_observability.py`（+68）：`:232-234` 后追加 7-score 数量与 `comment` 断言；新增 `ReportingContentTests.test_unavailable_scores_carry_metrics_unavailable_comment`（False 样本 7 score 名字集合/数量不变 + 各带 `metrics_available=false` + metadata 未污染）。`:227` 的 `assertNotIn("timings_available", metadata)` **原样保留**。

未改：`tests/observability/test_kb_trace_attribution.py`（`len(scores)==7` 守门，仅作回归）、`tests/system/test_bench_routes.py`、`tests/system/test_benchmark_summary_card.py`、`scripts/bench_ollama_routes.py`、`backend/app/platform/benchmark_summary.py`。

## 四、红→绿真实输出

### Baseline（改动前，确认存量绿 + 解释器正确）
```
$ .venv/bin/python -m pytest -q <精确 5 文件>
60 passed in 2.19s            PYTEST_EXIT=0
$ .venv/bin/python scripts/check_test_layout.py
LAYOUT_EXIT=1   # 仅 4 项存量违规：test_task03_reproducibility / test_task04_idempotency /
                # test_task05_decoupling / test_task06_identity_redaction（非本轮新建/改动）
```

### RED（先写测试，真实失败）
```
$ .venv/bin/python -m pytest -q tests/observability/test_phase_spans.py tests/system/test_observability.py
3 failed, 39 passed in 0.39s    RED_EXIT=1
FAILED ...PhaseSpanCaptureTests::test_overhead_zero_length_when_timings_unavailable
    AssertionError: 1767225600000000000 != 1767225639490000128 :
    phase:overhead 必须零长，实际 start=1767225600000000000 end=1767225639490000128
FAILED ...ReportingContentTests::test_reports_generation_with_scores_and_metadata
    AssertionError: False is not true : 可用样本 7 个 score 均须带 metrics_available=true comment
    （实际 scores 无 comment 键）
FAILED ...ReportingContentTests::test_unavailable_scores_carry_metrics_unavailable_comment
    AssertionError: False is not true : 不可用样本 7 个 score 均须带 metrics_available=false comment
    （实际 7 score 名 = 7 项、value 全 0.0、无 comment）
```
3 个失败精确对应 D3 三处缺口，非恒真 / 非静默失效。

### GREEN（实现后）
```
$ .venv/bin/python -m pytest -q <精确 5 文件>
62 passed in 1.35s            GREEN_EXIT=0
$ .venv/bin/python -m ruff check backend/app/platform/observability/spans.py \
    tests/observability/test_phase_spans.py tests/system/test_observability.py
All checks passed!            RUFF_EXIT=0
$ .venv/bin/python scripts/check_test_layout.py
LAYOUT_EXIT=1   # 与 baseline 完全相同的 4 项存量违规，无新增
```
62 = baseline 60 + 新增 2 个 False 用例（test_phase_spans 1 + test_observability 1），数目自洽。

> **精确回归命令（一条，退出码 0）**：
> ```
> .venv/bin/python -m pytest -q tests/observability/test_phase_spans.py \
>   tests/observability/test_kb_trace_attribution.py tests/system/test_observability.py \
>   tests/system/test_bench_routes.py tests/system/test_benchmark_summary_card.py
> → 62 passed in 1.35s, exit 0
> ```
> 按分派要求**不跑全量回归**（`cd backend && python -m pytest -q` 未执行）。

## 五、phase:overhead 修复前后对照（真实运行，False 样本 client_wall_ms=39490.0 ≈ 39.49s）

| | 修复前（RED 实测） | 修复后（GREEN 实测） |
|---|---|---|
| `phase:overhead` start | `1767225600000000000`（= base，从 0 起） | `1767225639490000128`（= end_ms） |
| `phase:overhead` end | `1767225639490000128`（= wall_end） | `1767225639490000128`（= end_ms） |
| 时长 | **39490ms，吃满整段墙钟**，与同名 score `overhead_ms=0` 自相矛盾 | **0.000ms 零长**，落在真实结束时刻 |
| 4 段 span 名 | 4 个 | 4 个（不变） |
| `metrics.available` | 无此属性 | `False`（4 段统一，独立 OTel attribute） |

修复后四段真实输出：
```
phase:decode     start=...000 end=...000 dur_ms=0.000 metrics.available=False
phase:load       start=...000 end=...000 dur_ms=0.000 metrics.available=False
phase:overhead   start=...9490000128 end=...9490000128 dur_ms=0.000 metrics.available=False
phase:prefill    start=...000 end=...000 dur_ms=0.000 metrics.available=False
=> overhead 零长: True; 落在 end_ms: True
```
True 样本对照（证明四段边界公式逐字节不变）：`load 7000ms / prefill 300ms / decode 1100ms / overhead 100ms`，`metrics.available=True`，7 score 全带 `metrics_available=true`。

## 六、7-score 契约未破坏的证据

1. **精确回归**：`tests/observability/test_kb_trace_attribution.py` 的 `assert len(recorder.scores) == 7`（:263）、`phase_names==4`（:262）在 62 passed 中通过；该文件本轮**逐字未改**。
2. **新增反向断言**：`test_observability.py` 显式断言 score 数量 `==7`、不可用样本 7 个名字集合
   `{ttft_ms, load_ms, prompt_eval_ms, eval_ms, overhead_ms, tokens_per_sec, is_cold_start}` 不变。
3. **真实运行**（False 样本）：7 个 score `value` 全 `0.0`（derive_metrics 0 契约保持），各带
   `comment='metrics_available=false'`，无第 8 个 score：
   ```
   ttft_ms / load_ms / prompt_eval_ms / eval_ms / overhead_ms / tokens_per_sec / is_cold_start
   全部 value=0.0 comment='metrics_available=false'
   ```
4. **git diff 逐字核对**：`SCORE_METRICS`(:67-76)、`derive_metrics`(:98-124)、`_build_metadata`(:127-147)
   均无任何 diff；score 循环仅新增 `comment=`，`name/value/data_type` 三行原样。
5. `scripts/bench_ollama_routes.py:56-68` diff 口径、`benchmark_summary.py`、19.735 证据文件均未触碰
   （`test_bench_routes.py` / `test_benchmark_summary_card.py` 回归通过）。

## 七、SDK `comment` 支持结论（实测，非猜测）

**结论：支持，未走退化路径。**
- `.venv/lib/python3.11/site-packages/langfuse`（`langfuse==4.15.1`）：`as_type="generation"` 返回
  `LangfuseGeneration`，继承 `LangfuseObservationWrapper`；其 `score()` 定义在 `_client/span.py:330-341`，
  签名含 `comment: Optional[str] = None`，方法体 `:382` 把 `comment=comment` 透传给 `create_score`。
- 受控运行时实测（打桩 `_langfuse_client`，绑定真实 `LangfuseObservationWrapper.score` 方法体）：
  ```
  LangfuseGeneration.score signature: (self, *, name, value, score_id=None, data_type=None,
      comment=None, config_id=None, timestamp=None, metadata=None) -> None
  has 'comment' param: True
  create_score called: True / comment passed through: 'metrics_available=false'
  RESULT: generation.score(..., comment=...) SUPPORTED, no TypeError
  ```
- 因此 7 个 score 均附带 `comment`，同时 4 个 phase span 仍统一挂 `metrics.available`（双保险，
  非二选一）。若未来 SDK 升版移除 `comment`，按定稿退化路径：去掉 `comment=`、保留 span attribute 即可，
  score 数量不变。

## 八、复用的既有符号（未引入第二套实现）

- `_set_phase_span_attributes`（既有 OTel span attribute 通道）— 扩展参数，未新建 helper。
- `_report_phase_spans` 既有 `boundaries` / `phases` / fail-open 单阶段 try — 只加条件覆写。
- `SCORE_METRICS`、`derive_metrics`、`_build_metadata`、`generation.score`、`safe_call`、`sdk_compat` 全部原样复用。
- 指标 0 契约、diff 口径、benchmark_summary、SSE、公开接口均无新增/平行实现。

## 九、边界自查 / 越界风险

- **本轮实际写入仅 3 个代码/测试文件 + 1 份本报告 + 进展日志**：
  `backend/app/platform/observability/spans.py`、`tests/observability/test_phase_spans.py`、
  `tests/system/test_observability.py`、`docs/sdd/plans/047/runs/task-01/implementation.md`、
  `.codebuddy/agent-logs/spec-047/task-01/backend-dev/*.md`。
- 未碰 `frontend/**`、`scripts/**`（含 `setup_langfuse_dashboards.py`、`bench_ollama_routes.py`）、
  `.env`、状态台账、`docs/sdd/specs|reviews|plans` 正文、SSE 协议、公开接口。
- 未 git commit / push / 合 main / 重启服务 / 真实 `--force` 重跑。
- **工作区既有改动提示（非本轮所改）**：`git status --short` 在启动时即显示
  `docs/sdd/spec-status-changelog.md`、`docs/sdd/specs/013-*`、`045-*`、
  `scripts/setup_langfuse_dashboards.py`、`.env.bak.spec047.*`、`tests/system/test_langfuse_dashboard_force_idempotency.py`
  等为 modified/untracked。这些属主会话 / Task-02 并行产物，**本 backend-dev 全程未读写这些路径**，
  `git diff --stat` 中它们的改动不在本轮改动清单内，特此说明避免混淆。
- **测试布局门禁**：`check_test_layout.py` 返回 1，但 4 项违规均为**存量**文件名含 task 编号
  （`test_task03/04/05/06_*`），与本轮无关；本轮新增/改动的 2 个测试文件名
  `test_phase_spans.py` / `test_observability.py` 均不含 spec/task 编号，未新增违规。
- 单次一事：本轮为「编码 + 配套红绿测试 + 交接报告」，未跨前端；如需前端改动应停下转派 `frontend-dev`。

## 十、剩余风险

1. **真实 Langfuse E2E 未在本轮执行**（分派未授权重启/真实服务取证）：本轮证据为单元测试 +
   真实 SDK 方法签名/受控调用实测。定稿验收的「真实 chat `completed` 后核对 trace 7 score +
   `phase:overhead` 不再吃满墙钟 + 真实 trace ID / 截图」需由 Task-07 集成验收在当前部署版本
   （D5 路由修复重启后）补做，等 ingestion 约 8s 再下结论。
2. **`comment` 是 per-score 而非 trace 级**：Langfuse Dashboard 若按 comment 过滤需在 score 表上聚合；
   本期仅要求「可用性区分可查」，未改 dashboard/脚本（属 Task-02 边界）。
3. **零长 overhead 的语义**：False 样本下 4 段中 load/prefill/decode 亦为零长（服务端 timings 全 0），
   仅 overhead 位置移到 end_ms；这是「不可分解」的最小表达，未改 0 契约，符合定稿。
4. **Langfuse SDK 升版**：`comment` / `_create_span_attributes` / `_otel_tracer` 均为 SDK 私有或半私有符号；
   修复点已收拢 `sdk_compat.py` + `spans.py` 上报层，升版时按 fail-open 退化并告警。
5. 未跑全量回归（`cd backend && python -m pytest -q`），按分派要求只做精确单端回归；
   全量回归由收口阶段（Task-07）执行。

## 十一、快速复核命令

```bash
cd /Users/wjh/ResearchAgent
.venv/bin/python -m pytest -q \
  tests/observability/test_phase_spans.py \
  tests/observability/test_kb_trace_attribution.py \
  tests/system/test_observability.py \
  tests/system/test_bench_routes.py \
  tests/system/test_benchmark_summary_card.py
.venv/bin/python -m ruff check backend/app/platform/observability/spans.py \
  tests/observability/test_phase_spans.py tests/system/test_observability.py
git --no-pager diff -- backend/app/platform/observability/spans.py
```
