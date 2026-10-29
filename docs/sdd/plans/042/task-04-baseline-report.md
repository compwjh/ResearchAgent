> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ 任务定义：[task-04-chat-quality-baseline](./task-04-chat-quality-baseline.md) ｜ 边界 9 来源：[task-03-memory-probe-report](./task-03-memory-probe-report.md)
> 执行角色：backend-dev（模型 hy3）；判官 `qwen3.5:9b`（温度 0，REPEATS=3，多数投票）；所有 HTTP 经 `offline_guard.assert_loopback`（仅本机 Ollama 11434 / Langfuse 3000）
> 评测日期：2026-09-23

# Task 04 — `chat_quality` 常态化评测闭环与回归基线报告

## 0. 交付与闭环结论（一句话）

把 Task 02「只走过 dry-run」的闭环在**真实数据集**上完整跑通：20 条 scored 真实写回 Langfuse score → 独立回查 20/20 命中（回写成功率 100%）→ 补齐人工一致率 **0.95（ok）**，并坐实边界 9（memory_correctness 对无 prior_context 的真实 trace 100% SKIPPED、判官 0 次调用）。

---

## 1. A. 真实全量评测闭环（chat_quality，非 dry-run）

数据集：`docs/sdd/plans/042/task-02-eval-dataset.json`（24 条 = 20 scored + 2 空 output + 2 合成 Intake）。
判官：`qwen3.5:9b`，`repeats=3`，`write_back=True`，`reference=task-04-human-labels.json`。
落盘：`docs/sdd/plans/042/task-04-eval-run-summary.json`（`task-04-eval-run-summary.ndjson` 为分批进度）。

| 指标 | 值 | 验收判据 |
|---|---|---|
| n_items | 24 | — |
| written（真实写回 Langfuse 的 score 数） | **20** | == 20 ✅ |
| skipped（不记分，按 reason 计数） | `empty_output:2` + `intake_text:2` = 4 | 4 条 skipped，无 score 写回 ✅ |
| unavailable（判官全不可用） | 0 | 绝不静默记 0 分 ✅ |
| write_errors（写回异常） | 0 | — |
| verified_on_trace（独立回查命中） | **20** | == written == 20 ✅ |
| 回写成功率 | 20/20 = **100%** | — |
| judge_calls（判官调用次数） | 20 | — |

> 说明：4 条 skipped（2 空 output + 2 合成 Intake）在 Langfuse 上**无任何 `chat_quality` score**，符合「失败/空 trace 不记 0 分」。合成 Intake 条目 `synthetic=True` 延续既有 `skipped`（intake_text）处理，未写回真实 Langfuse。

---

## 2. 首份回归基线表

| 维度 | 值 |
|---|---|
| n（scored 样本量） | 20 |
| 标签分布（判官多数标签） | `good: 18`, `poor: 2`（注：本轮无 partial） |
| mean_score（仅 scored 数值分均值） | **0.90**（QUALITY_ENUMS: good=1.0 / partial=0.5 / poor=0.0） |
| 人工一致率 agree_rate | **0.95** |
| 人工一致率 verdict | **ok**（≥0.70） |
| 混淆矩阵（行=人工 gold，列=判官多数标签） | 见下 |

**混淆矩阵（3×3，good/partial/poor）**

| 人工 \ 判官 | good | partial | poor |
|---|---|---|---|
| **good** (17) | 17 | 0 | 0 |
| **partial** (1) | 1 | 0 | 0 |
| **poor** (2) | 0 | 0 | 2 |

（人工 gold 分布：good=17、partial=1、poor=2，共 20；判官标签：good=18、poor=2。）

---

## 3. 人工一致率 verdict 与不一致逐条分析

- **verdict = `ok`**（agree_rate 0.95 ≥ 0.70），判官 `qwen3.5:9b` 在 `chat_quality` 维度与人类标注高度一致，纳入回归基线。
- **不一致 1 条**（占 1/20 = 5%）：
  - `trace_id = 959a71648d40b20278008adc9a8a597a`
  - 人工 gold = **partial**，判官多数标签 = **good**
  - 判官理由（comment）：`Explanation: The answer accurately defines tracking in a single sentence as requested by the user prompt. Answer: good`
  - 分析：**判官偏松**——该条回答（幂等性的一句定义）被判官判为「完整相关（good）」，而人工标注认为仍属「部分（partial）」。属单条边界差异，不改变 ok 结论；若后续要收紧，可在 `chat_quality` prompt 中强化「定义正确但缺乏代价/依据即判 partial」的细则（与本栈 long-context 系统提示「建议必含代价、事实需依据」对齐）。
- 其余 19 条判官标签与人工 gold 完全一致（17 good + 2 poor 全中）。人工标注文件 `task-04-human-labels.json` 由架构师独立产出，**本脚本只消费、绝不生成/回填/反推**，未触碰该文件。

---

## 4. 边界 9 验证结论（memory_correctness 对真实 trace）

数据集同 A（24 条），`task=memory_correctness`，`write_back=False`。
落盘：`docs/sdd/plans/042/task-04-memory-skip-check.json`。

| 指标 | 值 |
|---|---|
| n_items | 24 |
| written | 0 |
| skipped（按 reason） | `no_prior_context: 20` + `empty_output: 2` + `intake_text: 2` |
| **judge_calls（判官调用次数）** | **0** ✅ |
| unavailable | 0 |

结论：同一批 20 条真实 trace 因**均无 `prior_context`**，在 `memory_correctness` 下被新前置判定 `skipped/no_prior_context`，**判官 0 次调用、0 条 score 写回**。从代码侧坐实 Task 03 结论——Task 02 的 L2 是「输入不适定（ill-posed）」，而非「维度不可评」。该维度评测要求样本必须携带先前陈述上下文，缺失即 SKIPPED，不得强行四选一。

---

## 5. C. 回退链复核（条件触发）

- 触发条件：`human_agree.verdict == trigger_fallback_review`（agree_rate < 0.60）。
- **实测 A 的 verdict = `ok`（agree_rate 0.95），未触发**。按任务定义**不跑** `qwen3.8:27b` 复核。
- 若未来某次评测 agree_rate 落入 <0.60，再执行：`--task chat_quality --judge qwen3.8:27b --repeats 3 --reference task-04-human-labels.json --out task-04-fallback-27b.json`（落盘 `task-04-fallback-27b.json`），复用同一 `eval_run.run`，不新增实现。

---

## 6. 实现收敛与代码变更

- 新增 `backend/eval_042/eval_run.py`（模块）：`classify_for_task`（四分支：scored / empty_output / intake_text / no_prior_context）、`run`（逐条判官→写回→独立回查→分批 NDJSON 落盘→人工一致率并入）、`human_agree`（3×3 混淆矩阵 + 阈值 verdict）。全部复用 `judge_client` / `langfuse_export` / `config`，**未引入第二套评分/写回实现**。
- 改造 `docs/sdd/plans/042/task-02-run-eval.py` 为**薄封装**：仅加载数据集 + 调用 `eval_run.run` + 落盘 summary；保留 `--dataset/--out/--max-items/--dry-run` 语义（`--dry-run` 走 `classify_for_task` 纯分类路径、零网络），扩展 `--task/--judge/--repeats/--reference/--progress/--no-write-back` 供 A/B/C。
- 新增 `backend/eval_042/test_eval_run.py`（12 条纯函数单测，无网络）：覆盖 `classify_for_task` 四分支（含 memory_correctness 有 prior_context 应 scored）、`human_agree` 全对/部分对/缺标注不计入分母/混淆矩阵维度。
- Task 03 既有 19 条 `test_memory_probe.py` 不受影响，`pytest backend/eval_042/ -q` 共 **31 passed（12 新 + 19 既有），退出码 0**。

### ⚠️ 回查环节一处实测修复（非静默降级，特此记录）
首轮实跑 A 的 `verified_on_trace` 曾为 0，根因为 `_verify_written` 向 Langfuse public scores API 传了 `limit=200`，而该 API 的 `limit` 上限为 **100**，超限返回 **400 Bad Request**，每次回查被 `except` 吞成空列表 → 全部判「未验证」。写回本身成功（20 条均拿到 `score_id`、`write_errors=0`）。修复：将回查 `limit` 改为 100（API 上限），已用单测确认能回查到刚写回的 score（`name`/`traceId` 匹配逻辑正确），并重跑 A 得到 `verified_on_trace=20`。报告所有 verified 数值均为重跑后真实回查结果。

---

## 7. 遗留项与下一步建议

1. **判官偏松边界**：单条不一致（959a7164）提示 `chat_quality` prompt 对「定义正确但缺代价/依据」的回答偏松。建议在 prompt 中强化 partial 细则（与系统提示「建议必含代价、事实需依据」对齐），后续回归基线应复测该边界。
2. **边界 9 仅覆盖 recall 侧**：当前仅验证「无 prior_context → SKIPPED」。建议后续补充「有 prior_context 的真实 memory trace」评测，才能真正跑通 memory_correctness 的 scored 路径（Task 03 用的是合成探针，非真实 trace）。
3. **score 幂等**：A 为验证修复重跑一次，同一 trace 上现挂 2 条 `chat_quality` score；当前回查为「存在性」校验，不幂等去重。若需精确基线，可清理早期重复 score 或在写回前先 `list_scores` 去重（需谨慎，避免误删历史）。
4. **回写重试**：`post_score` 当前单次调用，失败如实记录 `write_error`；若未来 Langfuse 偶发抖动，可加指数退避重试（仍须如实记 verified=false，不得静默降级）。
5. **回归基线固化**：建议将本节第 2 节基线表作为 `task-04-baseline-report` 的基线值，后续 Task 评测须不低于本 baseline 的 agree_rate（0.95）与 verified_on_trace 比率（100%）。

---

## 8. 复现实命令

```bash
# 前置：激活 .venv
cd /Users/wjh/ResearchAgent_codebuddy && source .venv/bin/activate

# A. chat_quality 全量写回 + 人工一致率
python docs/sdd/plans/042/task-02-run-eval.py \
  --dataset docs/sdd/plans/042/task-02-eval-dataset.json \
  --out docs/sdd/plans/042/task-04-eval-run-summary.json \
  --task chat_quality --judge qwen3.5:9b --repeats 3 \
  --reference docs/sdd/plans/042/task-04-human-labels.json \
  --progress docs/sdd/plans/042/task-04-eval-run-summary.ndjson

# B. memory_correctness 边界 9（不写回）
python docs/sdd/plans/042/task-02-run-eval.py \
  --dataset docs/sdd/plans/042/task-02-eval-dataset.json \
  --out docs/sdd/plans/042/task-04-memory-skip-check.json \
  --task memory_correctness --judge qwen3.5:9b --repeats 3 --no-write-back \
  --progress docs/sdd/plans/042/task-04-memory-skip-check.ndjson

# 单测（31 passed，含 Task 03 的 19 条）
cd backend && python -m pytest eval_042/ -q
```

## 9. 产物清单

| 文件 | 说明 |
|---|---|
| `backend/eval_042/eval_run.py` | 新增：闭环模块（classify_for_task / run / human_agree） |
| `backend/eval_042/test_eval_run.py` | 新增：12 条纯函数单测 |
| `docs/sdd/plans/042/task-02-run-eval.py` | 改造：薄封装入口（仅调用 eval_run.run） |
| `docs/sdd/plans/042/task-04-eval-run-summary.json` | A 实跑 summary（written=20 / verified=20 / agree=0.95） |
| `docs/sdd/plans/042/task-04-eval-run-summary.ndjson` | A 分批进度（首轮，limit bug 前） |
| `docs/sdd/plans/042/task-04-eval-run-summary-r2.ndjson` | A 重跑分批进度（修复后） |
| `docs/sdd/plans/042/task-04-memory-skip-check.json` | B 边界 9 验证（judge_calls=0） |
| `docs/sdd/plans/042/task-04-memory-skip-check.ndjson` | B 分批进度 |
| `docs/sdd/plans/042/task-04-run-a.log` / `task-04-run-a-r2.log` | A 两轮 stdout 日志 |
| `docs/sdd/plans/042/task-04-baseline-report.md` | 本报告 |
| `task-04-human-labels.json` | 人工标注（**未改动**，仅消费） |
