> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02（Go/No-Go 判定 **Go**）；当前状态：**已完成**（2026-09-23，[报告](./task-03-memory-probe-report.md)）

# Task 03 — 专用记忆探针重测 `memory_correctness`

## 一句话目标

用**专门构造的记忆探针**（带构造真值 gold 标签）重测 `memory_correctness` 维度，
把 Task 02 遗留项 **L2**（跨判官一致率 0.5、维度不适定）收敛为一个明确结论：
`adopt:qwen3.5:9b` / `fallback:qwen3.8:27b` / `no-go`（该维度退化为人工标注）。

## 背景与问题根因

- Task 02 结论：`chat_quality` 已 ✅（9b/27b 自一致 1.0、跨判官 1.0），`memory_correctness` ⚠️ Deferred。
- **根因（L2）**：`task-02-eval-dataset.json` 的 24 条样本全部来自真实 `ollama-chat` trace，
  **没有任何一条是「用户先陈述偏好/事实 → 后续追问是否记住」的记忆探针**。
  判官在没有记忆信号的普通对话上被迫四选一，标签实质随机 → 跨判官一致率仅 0.5（n=6）。
  即：**不是判官不行，是输入不适定（ill-posed）**。
- 另：Task 02 报告中 `human_agree_rate` 为 `null`（无法获取人工标注），
  因此**判官「打得对不对」从未被验证过**，只验证了「打得稳不稳」。

## 本 Task 的做法（关键设计）

1. **构造记忆探针集（合成，明确标记 `synthetic: true`，绝不冒充真实 trace）**
   - 每条探针 = `prior_context`（用户先前陈述的偏好/事实）+ `question`（追问）+ `answer`（agent 回答）+ `gold`（构造真值）。
   - `gold` 四类：`remembered` / `partially_remembered` / `forgotten` / `fabricated`，**每类 5 条，共 20 条**。
   - gold 由构造决定、客观可判（答案明确复述偏好=remembered；遗漏关键项=partially_remembered；
     未召回或答「不知道你的偏好」=forgotten；编造未陈述过的偏好=fabricated）。
   - **必须在报告中如实标注**：gold 是**构造真值（constructed gold）**，
     **不等于真实人工标注**；它验证的是判官在该维度上的**判别有效性下界**。
2. **判官 prompt 升级**：现有 `memory_correctness` 的 `user_tmpl` 只有 `{q}`/`{a}`，
   无法承载「先前陈述」与「追问」的区分。改为 `{ctx}`（prior context）+ `{q}`（追问）+ `{a}`（回答）。
   改后 Task 02 的 memory 结论作废（本就是 Deferred），**不影响已通过的 chat_quality**。
3. **三项门禁**（温度 0、每条重复 3 次；primary `qwen3.5:9b`、fallback `qwen3.8:27b` 各跑一遍）：

| 门禁 | 判据 | 阈值 |
|---|---|---|
| G1 自一致 | 同一判官 3 次标签完全一致 | ≥ 0.90 |
| G2 判别有效性 | 多数标签 == gold | ≥ 0.80 |
| G3 跨判官一致 | 9b 多数标签 == 27b 多数标签 | ≥ 0.80 |

4. **裁决链（沿用 Q8=A）**：G1∧G2∧G3 全过 → `adopt:qwen3.5:9b`；
   9b 不过而 27b 过 → `fallback:qwen3.8:27b`；两者均不过 → `no-go`
   （`memory_correctness` 维度退化为「仅导出 + 人工标注」，并在 spec 中明确标注该维度不可用）。

## 数据、配置与接口

- 只读本机 Ollama `POST /api/chat`（`http://localhost:11434`），**不触外网**。
- 本 Task **不读、不写 Langfuse**（探针为合成数据，无真实 traceId；回写留到 Task 04 真实探针）。
- 所有 HTTP 调用必须经 `backend/eval_042/offline_guard.py` 的 `assert_loopback` 守卫。

## 实施步骤与文件边界

### 步骤 1 — 探针集与评测器（仅新增/改 `backend/eval_042/**`）

1. 新增 `backend/eval_042/memory_probe.py`：
   - `MEMORY_PROBES: list[MemoryProbe]`（20 条，4 类各 5 条，含 `gold` 与 `synthetic: true`）；
   - `build_probe_dataset() -> list[dict]`（转成与 `EvalItem` 兼容的 dict，`task="memory_correctness"`）；
   - `run_probe(...)`：对每条探针用 primary/fallback 各 `REPEATS` 次评分，统计 G1/G2/G3 并按裁决链给出唯一 `decision`。
2. 修改 `backend/eval_042/config.py`：
   - `memory_correctness` 的 `user_tmpl` 改为含 `{ctx}`/`{q}`/`{a}` 的三段式（判官须先对照 prior context 再判回答）；
   - 新增 `PROBE_GOLD_ACC_THRESHOLD` / `CROSS_AGREE_THRESHOLD`（不自创阈值之外的隐藏门禁）。
3. 修改 `backend/eval_042/judge_client.py`：
   - `judge_one` / `judge_repeats` 增加可选 `ctx: str | None`，传入时用于 `memory_correctness` 模板渲染；
   - **保持向后兼容**（不传 ctx 时行为不变，避免影响 chat_quality 路径）。
4. 新增 `backend/eval_042/test_memory_probe.py`（pytest，纯函数级，不发网络请求）：
   - 探针集结构自检（20 条、4 类各 5 条、`gold` 合法、无重复 `probe_id`）；
   - `parse_r4` 对四类标签的解析正确；
   - `classify_output` 的 SKIPPED 边界不回归。

### 步骤 2 — 实跑并落盘

- 运行评测脚本，产物落盘 `docs/sdd/plans/042/task-03-memory-probe-result.json`（逐条明细 + 汇总）。
- **硬要求**：不得伪造/回填数值；判官 unavailable 的条目如实计为 unavailable 并在汇总中体现。

### 步骤 3 — 报告

- `docs/sdd/plans/042/task-03-memory-probe-report.md`：G1/G2/G3 实测值、唯一 decision、
  失败样本分析（哪些类判错最多）、对 spec-042 的回写建议。

## 子代理分派

- 角色：`backend-dev`（模型 `hy3`，上下文 32k）
- 最小上下文：本 task 文件 + `backend/eval_042/{config,judge_client,consistency,offline_guard}.py`
- 单次文件范围：仅 `backend/eval_042/**`（新增/修改评测脚本与单测）+ 运行产物落盘 `docs/sdd/plans/042/task-03-*`
- **不改业务代码、不改 Langfuse 配置、不写业务库**
- 回传后架构师读回校验：比对报告数值与 result JSON 原始记录

## 边界与明确不做

- 不伪造真实记忆 trace：探针一律 `synthetic: true`，并在报告中显著标注
- 不把构造 gold 说成「人工标注」
- 本 Task **不回写 Langfuse score**（无真实 traceId）
- 不修改 `chat_quality` 的 prompt 与已通过结论
- 不引入云端 judge、不新增业务端点

## 验收、风险与回滚

| 验收项 | 判据 |
|---|---|
| 探针集合规 | 20 条、4 类各 5 条、gold 合法、全部标记 synthetic |
| 三项门禁有实测值 | G1/G2/G3 均给出数值与样本量 n，非 null |
| decision 唯一 | 明确 `adopt` / `fallback` / `no-go` 三者之一，并给出依据 |
| 离线成立 | 全部调用经 loopback 守卫，无外网请求 |
| 单测通过 | `python -m pytest backend/eval_042/test_memory_probe.py` 退出码 0 |

**风险**：20 条 × 2 判官 × 3 次 = 120 次判官调用，27b 单次约 2–5s，预计 5–10 分钟；
若超时则先跑 9b 全量再跑 27b，分批落盘进度，不得中断后重跑丢数据。

**回滚**：本 Task 只新增评测脚本/单测/报告，无业务改动；回滚即删除这些文件。

## 产出物与变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-23 | 架构师(自身) | 创建本 task 文档，明确 L2 根因为「输入不适定」，设计带 gold 的合成探针方案与 G1/G2/G3 门禁 |
| 2026-09-23 | backend-dev(hy3) | 实现 `backend/eval_042/memory_probe.py`（20 条探针 + `run_probe`）与 `test_memory_probe.py`（19 passed）；改造 `config.py` 三段式模板与 `judge_client.py` 可选 `ctx`；实跑 120 次判官调用并落盘 result/progress/log + 报告 |
| 2026-09-23 | 架构师(自身) | 回读校验：result JSON 与报告数值自洽（G2=(19+20)/40=0.975、G3=19/20=0.95）；`pytest eval_042/test_memory_probe.py` 19 passed 退出码 0；`chat_quality` 判官路径实测 `scored/good/1.0` 无回归；回写 spec-042 边界 9 与数据模型两字段，任务置为已完成 |

## 执行结果（实测，2026-09-23）

| 门禁 | 阈值 | 实测 | n | 结论 |
|---|---|---|---|---|
| G1 自一致 | ≥0.90 | **1.0** | 40 块（探针×判官） | ✅ |
| G2 判别有效性（vs 构造 gold） | ≥0.80 | **0.975** | 40 块 | ✅ |
| G3 跨判官一致 | ≥0.80 | **0.95** | 20 对 | ✅ |

- **唯一 decision：`adopt:qwen3.5:9b`**（9b：G1=1.0/G2=0.95；27b：G1=1.0/G2=1.0；unavailable 0/120）。
- 唯一失分样本 `mp-par-04`（gold=`partially_remembered`，回答漏掉「16G 内存」）：9b 判 `forgotten`、27b 判 `partially_remembered`，两判官唯一一次分歧，属 `partial`/`forgotten` 天然边界模糊，不构成判官失效。
- **遗留（非阻断）**：gold 为**构造真值非人工标注**，人类一致率仍待后续真实记忆 trace + 人工标注补算。
- 遗留备案：`backend/eval_042/consistency.py:86` pre-existing ruff F841（`n = len(results)`），属 Task 02 文件、不在本 Task 边界内，未改。
