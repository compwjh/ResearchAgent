> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02（Go 判定）、任务 03（`memory_correctness` 判官可用）；当前状态：**已完成**（2026-09-23，[报告](./task-04-baseline-report.md)）

# Task 04 — `chat_quality` 常态化评测闭环与回归基线 + 补齐人工一致率

## 一句话目标

把 Task 02「已跑通但只走了 dry-run」的闭环**真实跑一遍**：对真实 trace 数据集用 `qwen3.5:9b`
判官打分 → **真实写回 Langfuse score** → **独立回查验证**，产出首份**回归基线**；
同时补齐 Task 02/03 中始终为 `null` 的 **`human_agree_rate`（人工一致率）**。

## 背景与待收敛的缺口

1. `task-02-eval-run-summary.json` 显示 `dry_run: true`、`written=2`、`verified_on_trace=0`
   —— 闭环**从未在真实数据集上完整跑过**，只验证了单次写回能力（score id `8f24dd05`）。
2. `JudgeConsistency.human_agree_rate` 在 Task 02、03 报告中**均为 `null`**，
   判官「打得对不对」至今只验证了「打得稳不稳」与「对得上构造 gold」。
3. Task 03 为 spec 新增的**边界 9** 尚未在代码侧落地：真实 trace 无 `prior_context` 时，
   `memory_correctness` 必须 `SKIPPED`，不得强行四选一。

## 本 Task 的做法

### A. 真实全量评测（非 dry-run）

- 数据集：`docs/sdd/plans/042/task-02-eval-dataset.json`（24 条：20 scored / 2 空 output / 2 合成 Intake）。
- 判官：`qwen3.5:9b`（Task 02/03 裁决 `adopt`），温度 0，`REPEATS=3`，取多数标签。
- 对 **20 条 scored** 真实写回 Langfuse score（name=`chat_quality`，value 由 `ENUM_MAPS` 映射，
  comment 承载 R4 范式 `Explanation: … Answer: <label>`）。
- 对 **4 条 skipped** 一律**不写任何 score**（禁止记 0 分），并在结果中记录 `skip_reason`。
- 写完后**独立回查**（`list_scores` 分页 + 重试克服最终一致竞态），统计 `verified_on_trace`。
- 落盘：`docs/sdd/plans/042/task-04-eval-run-summary.json`（逐条明细 + 汇总 + 基线分布）。

### B. 边界 9 落地（memory_correctness 对真实 trace）

- 在评测脚本中新增前置判定：`task == memory_correctness` 且样本**无 `prior_context`** →
  `status = skipped`、`skip_reason = no_prior_context`、**不调用判官、不写 score**。
- 对同一批 20 条真实 trace 以 `memory_correctness` 跑一遍，验证 **100% SKIPPED**，
  从代码侧坐实「Task 02 的 L2 是输入不适定」。

### C. 人工一致率（补齐 `human_agree_rate`）

- 由**架构师（人）**对本数据集人工标注 gold 标签（`good`/`partial`/`poor`），
  标注文件 `docs/sdd/plans/042/task-04-human-labels.json`（`{trace_id: label}`）。
- 脚本读取该文件，计算：判官多数标签 vs 人工 gold 的 `agree_rate`、`n`、
  **混淆矩阵**（3×3）与**逐条不一致明细**。
- **阈值约定（本 Task 新增，写回报告）**：
  - `agree_rate >= 0.70` → 判官可用，纳入回归基线；
  - `0.60 <= agree_rate < 0.70` → 判官**需校准**，报告标注告警并给出混淆分析；
  - `< 0.60` → 触发 **Q8 回退链复核**：用 `qwen3.8:27b` 在同一标注集上重跑一致率再判。
- **不得**用判官输出反推或回填人工标签；人工标注独立于判官结果产生。

### D. 回归基线

- 汇总首份基线：n、scored/skipped/unavailable 计数、标签分布、平均分、人工一致率、
  回写成功率（`verified_on_trace / written`）。供后续 Task 回归比对。

## 数据、配置与接口

- Langfuse public API：`POST /api/public/scores`、`GET /api/public/scores?traceId=…`（Basic auth pk/sk）。
- Ollama `POST /api/chat`（本机 11434）。
- 所有 HTTP 必须经 `backend/eval_042/offline_guard.py` 的 `assert_loopback`。

## 实施步骤与文件边界

仅改/新增 `backend/eval_042/**` + 落盘 `docs/sdd/plans/042/task-04-*`：

1. 新增 `backend/eval_042/eval_run.py`（把 `task-02-run-eval.py` 的脚本逻辑**收敛进模块**，
   由其保留为薄 CLI 入口或直接复用；不得出现第二套实现）：
   - `classify_for_task(item, task)`：先走 `classify_output`（空/Intake），
     再对 `memory_correctness` 追加 `no_prior_context` 判定（边界 9）；
   - `run(dataset, task, judge, repeats, write_back, reference_path)` → 逐条结果 + 汇总；
   - `human_agree(results, reference)` → `agree_rate` / 混淆矩阵 / 不一致明细。
2. `docs/sdd/plans/042/task-02-run-eval.py` 改为调用该模块（薄封装），保持既有 CLI 参数可用。
3. 新增 `backend/eval_042/test_eval_run.py`（pytest，纯函数无网络）：
   - `classify_for_task` 的四种分支（`scored` / `empty_output` / `intake_text` / `no_prior_context`）；
   - `human_agree` 的构造用例（全对 / 部分对 / 缺标注项不计入分母）。
4. 实跑 A、B、C 并落盘 summary + 报告。

## 子代理分派

- 角色：`backend-dev`（模型 `hy3`，上下文 32k）
- 最小上下文：本 task 文档 + `backend/eval_042/{config,judge_client,langfuse_export,offline_guard}.py`
  + `docs/sdd/plans/042/task-02-run-eval.py`
- 单次文件范围：`backend/eval_042/**` 与 `docs/sdd/plans/042/task-04-*`
- **不改 `backend/app/**`、不改 Langfuse 配置、不写业务库、不起主服务、不造真实对话**

## 边界与明确不做

- **不起主服务、不跑真实对话造数据**（spec 边界 8：评测过程不写业务库）；
  真实记忆探针需造业务数据，超出已确认范围，**不在本 Task 做**（如需，另立 spec 变更）。
- 不伪造人工标注；人工标注由架构师独立产出，脚本只消费不生成。
- 不合格项（判官 unavailable）如实计 `UNAVAILABLE`，不静默记 0。
- 不修改 `chat_quality` 判官 prompt 与已通过结论。

## 验收、风险与回滚

| 验收项 | 判据 |
|---|---|
| 真实闭环 | 20 条 scored 全部写回，`verified_on_trace == written == 20` |
| SKIPPED 不记分 | 4 条 skipped（2 空 + 2 合成）在 Langfuse 上无 `chat_quality` score |
| 边界 9 落地 | 同批真实 trace 以 `memory_correctness` 跑，100% `skipped/no_prior_context`、0 次判官调用 |
| 人工一致率有值 | `human_agree_rate` 非 null，含 n、混淆矩阵、不一致明细 |
| 离线 | 全部调用经 loopback 守卫 |
| 单测 | `python -m pytest backend/eval_042/ -q` 退出码 0（含 Task 03 的 19 条） |

**风险**：Langfuse score 写回为最终一致，回查需重试；27b 复核（若触发）耗时约 5–10 分钟。
**回滚**：本 Task 只新增/重构评测脚本与报告，无业务改动；回滚即删除文件。

## 产出物与变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-23 | 架构师(自身) | 人工**独立**标注 20 条 gold（`good` 17 / `partial` 1 / `poor` 2），标注时未查看判官输出，落盘 `task-04-human-labels.json` |
| 2026-09-23 | backend-dev(hy3) | 新增 `backend/eval_042/eval_run.py`（`classify_for_task` / `run` / `human_agree`）与 `test_eval_run.py`（12 条）；`task-02-run-eval.py` 收敛为薄封装；实跑 A/B 并落盘 summary/skip-check/日志/报告 |
| 2026-09-23 | 架构师(自身) | 回读校验：`pytest backend/eval_042/ -q` 31 passed 退出码 0；A 组 written=20 / verified=20 / agree=0.95 与 JSON 自洽；B 组 judge_calls=0；Langfuse 上 score 真实可见；人工标注文件未被生成或篡改。任务置为已完成 |

## 执行结果（实测，2026-09-23）

| 项 | 结果 |
|---|---|
| A. 真实闭环 | `written=20`、`skipped=4`（empty_output 2 + intake_text 2，均未写 score）、`unavailable=0`、**`verified_on_trace=20`（100%）** |
| A. 基线分布 | `label_distribution={good:18, poor:2}`、`mean_score=0.90` |
| A. 人工一致率 | **`agree_rate=0.95 (n=20)、verdict=ok`**；唯一不一致 `959a716…`（人工 partial / 判官 good，判官偏松） |
| B. 边界 9 | 20 条真实 trace **全部** `skipped/no_prior_context`，**判官调用 0 次**，0 次写回 |
| C. 回退链 | agree_rate 达阈值，**未触发** 27b 复核 |

**新发现（转 Task 05）**：同一 trace 因多次试跑堆积数十条同名 `chat_quality` score，写回缺幂等。
