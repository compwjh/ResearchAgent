# task-01 修复 B：两处观测口径（phase:overhead + 7-score 可用性标记）

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：spec-047 已确认；当前状态：`已完成`（红→绿 62 passed，报告 `runs/task-01/implementation.md`） ｜ 对应 spec 表编号 02 ｜ 决策 D3

## 状态与一句话目标

`待执行`。只改**上报层**：把 `timings_available=False` 时吃满墙钟的 `phase:overhead` 改为零长/明确「不可分解」标记，并给 7 个 numeric score 加可用性区分；**不动** 0 契约 / diff / 7-score 数量 / 19.735 证据。

## 背景与前置条件

- 复核证据见[技术评审 §3 风险 1](../../reviews/047-tech-review.md)与只读调查 B 节：`spans.py:252-260`（`phase:overhead=[0,client_wall_ms]`）与 `:107-109`（`overhead_ms=0`）自相矛盾；`:391-396` 无条件上报 `SCORE_METRICS`(`:67-76`) 7 项、无可用性标记。
- 前置：spec-047 已确认、D3 已拍板「保留 0 契约 + 上报层可用性标记 + 本期不排除样本」。
- 先 `source .venv/bin/activate`（依赖在仓库根 `.venv`）。

## 数据 / 配置 / 接口增量

- **不改**数据模型 / 端点 / 环境变量；`SCORE_METRICS` 7 个 score 名与数量不变。
- 新增（不进 metadata、不增减 score）：`phase:overhead` 子 span 的 OTel **attribute** `metrics.available`(bool) 与 `metrics.overhead_basis="not_decomposable"`；7 个 score 各附稳定 `comment` 标记（`metrics_available=true|false`）。

## 实施步骤与文件边界

**唯一可改文件**：`backend/app/platform/observability/spans.py`；`tests/observability/test_phase_spans.py`；`tests/system/test_observability.py`；`tests/observability/test_kb_trace_attribution.py`。

1. **红**：新增 `timings_available=False` 用例（现 `test_phase_spans.py:44` 全 True，是覆盖缺口）——断言 `phase:overhead` 零长（start==end）+ span attribute `metrics.available==False`；断言不可用样本的 7 个 score 均带 `metrics_available=false` comment。
2. **绿**：
   - `spans.py:256-261` boundaries：`timings_available=False` 时把 overhead 改为 `(end_ms, end_ms)` 零长；经既有 `_set_phase_span_attributes`(`:193-204`) 打独立 OTel attribute（**不是** `_build_metadata` 的 metadata dict）。
   - `spans.py:391-396`：保留 7 次 `generation.score(name, value, data_type="NUMERIC")` 调用与 `metrics.get(name,0.0)` 值不变，追加稳定 `comment` 字符串标记。若当前 Langfuse SDK `generation.score()` 不接受 `comment` 参数，退化为「4 个 phase span 统一挂 `metrics.available` attribute」，仍不碰 metadata / score 数量。
   - 4 个 phase span 名与数量保持 4 个。
3. **保持不动**：`derive_metrics`(`:98-124`)、`_build_metadata`(`:127-147`) allowlist、`benchmark_summary.py`、`scripts/bench_ollama_routes.py`、`tests/system/test_bench_routes.py`。

## 子代理分派

- 后端改动 → `Task(backend-dev)`（只改 `backend/**` + `tests/**`），最小上下文 = 技术评审 §3 风险 1 + 本任务 + 上述 `文件:行号`；「先给完整代码片段、再给说明」，片段同步写入进展日志；回传后架构师读真实文件做最小增量修改并校验。
- 单端回归 → `Task(backend-tester)`（只跑后端 pytest）。

## 边界与明确不做

- **不把 `timings_available` 或任何新键写进 metadata**（撞 `test_observability.py:227-228` / `:218-230` Spec024 allowlist）。
- **不减少 / 不新增 score**（撞 `test_kb_trace_attribution.py:263` `len==7`）。
- 不动 `derive_metrics` 0 契约、不改 `diff = langchain - direct`、不跳过 score、本期不排除 `benchmark_summary` 样本（保 19.735）。
- 不重构 SDK 接入方式、不引入第二套观测实现。
- 不 push、不合 main；不写状态台账；不改 `.env`。

## 验收、风险与回滚

- 红→绿用例通过；`test_phase_spans.py:156-160/:182-201/:236-241`（True 样本）断言不变；`test_observability.py:227-228`（metadata 未污染）、`test_kb_trace_attribution.py:260-264`（len==7）**保持原样通过**。
- 精确回归：`tests/observability/test_phase_spans.py`、`tests/observability/test_kb_trace_attribution.py`、`tests/system/test_observability.py`、`tests/system/test_bench_routes.py`、`tests/system/test_benchmark_summary_card.py`、`scripts/bench_ollama_routes.py`。
- 当前部署版本真实 E2E：真实 chat `completed` 后核对 Langfuse 该 trace 7 score 齐全 + 不可用样本带标记 + `phase:overhead` 不再吃满墙钟；记录真实 trace ID / 截图路径，等 ingestion 约 8s 再下结论。
- 风险：SDK `comment` 参数兼容性（见实施步骤退化路径）。回滚：回退 `spans.py` 上报层改动（不动 derive_metrics）。

## 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/047/runs/task-01/*.json`（红绿记录 + 真实 trace 证据）。
- 执行结果：待执行后填写（真实命令、pytest 结果、trace ID）。
- 变更日志：待执行后填写。

