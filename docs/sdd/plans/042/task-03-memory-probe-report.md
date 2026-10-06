> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ [Task 03 定义](./task-03-memory-probe.md) ｜ [Task 02 Go/No-Go](./task-02-gono-go-report.md)
> 依赖：任务 02（Go/No-Go = Go）；当前状态：**已完成**
> 评测日期：2026-09-23 ｜ 执行角色：backend-dev（本地 qwen3.5:9b / qwen3.8:27b，温度 0，每条重复 3 次）

# Task 03 — 专用记忆探针重测 `memory_correctness` 报告

## 0. 关于 gold 的真实性质（硬要求，先说清楚）

> **本报告的 gold 是「构造真值（constructed gold）」，由探针设计决定，绝非真实人工标注。**
> 它验证的是判官在 `memory_correctness` 维度上的**判别有效性下界**（lower bound of
> discrimination validity），**不代表判官与人类标注的一致率**。人类一致率（human_agree_rate）
> 仍未知，需 Task 04 注入真实记忆 trace 并人工标注后才能补算。任何门禁数值均如实记录，
> 未回填、未美化；unavailable 条目如实计数（本次 0 条）。

## 1. 收敛结论：Task 02 遗留项 L2 已解决

L2 根因为「输入不适定（ill-posed）」：Task 02 的 24 条样本无任何记忆探针信号，判官被迫四选一、
标签实质随机（跨判官一致率 0.5）。本 Task 用 **20 条专门构造的记忆探针**（prior context →
追问 → 回答，带构造 gold）重测，输入变为良定（well-posed），结论如下。

## 2. 三项门禁实测值（样本量 n=20 探针 × 2 判官 × 3 次 = 120 次判官调用）

| 门禁 | 判据 | 阈值 | 实测值 | 样本量 | 结论 |
|---|---|---|---|---|---|
| G1 自一致 | 同一判官 3 次标签完全一致（unavailable 计不一致） | ≥ 0.90 | **1.0** | 40 个（探针×判官）块 | ✅ |
| G2 判别有效性 | 多数标签 == gold（unavailable 计不匹配） | ≥ 0.80 | **0.975** | 40 个块 | ✅ |
| G3 跨判官一致 | 9b 多数标签 == 27b 多数标签（两者都有标签才入分母） | ≥ 0.80 | **0.95** | 20 对 | ✅ |

- unavailable：0 / 120（判官 100% 可用，无解析失败、无超时、无外网）。
- 全部 HTTP 调用经 `offline_guard.assert_loopback` 守卫，仅访问本机 Ollama(11434)，**无外网请求**。

## 3. 唯一 decision

**`adopt:qwen3.5:9b`**（沿用 Q8=A 裁决链：G1∧G2∧G3 全过 → 采用主用 9b）。

逐判官明细：

| 判官 | G1 自一致 | G2 判别有效性 |
|---|---|---|
| primary qwen3.5:9b | 1.0 | 0.95 |
| fallback qwen3.8:27b | 1.0 | 1.0 |

判据：primary_ok(1.0≥0.90 且 0.95≥0.80)=True 且 g3_ok(0.95≥0.80)=True → `adopt:qwen3.5:9b`。

## 4. 每 gold 类命中率表（以 primary 9b 多数标签计）

| gold 类 | n | 9b 命中 | 命中率 | 27b 命中率 |
|---|---|---|---|---|
| remembered | 5 | 5 | 1.0 | 1.0 |
| partially_remembered | 5 | 4 | 0.8 | 1.0 |
| forgotten | 5 | 5 | 1.0 | 1.0 |
| fabricated | 5 | 5 | 1.0 | 1.0 |

（注：per_gold_breakdown 按 primary 9b 的 gold_match 统计；27b 在全部 20 条上与 gold 一致。）

## 5. 判错最多的类别分析

- **唯一失分样本：mp-par-04**（gold = `partially_remembered`）。
  - prior：「我的预算是 5000 元以内，想买一台轻薄笔记本，**并且要 16G 内存**。」
  - 追问：「按我的条件推荐？」
  - 回答：「您预算 5000 元以内、想买轻薄笔记本，推荐这款轻薄本。」（漏掉了 16G 内存）
  - 9b 三次一致判 `forgotten`（认为漏掉关键项 = 没记住）；27b 三次一致判 `partially_remembered`（认为复述了但有遗漏）。
  - 这恰是两判官**唯一一次 cross 不一致**（G3 0.95 的缺口来源）。
- 分析：`partially_remembered` 与 `forgotten` 的边界在「给出通用推荐但未含某关键项」时天然模糊——
  设计意图是「复述了主线但遗漏细节 → 部分记住」，9b 则更严格地把遗漏关键项归为「未召回」。
  这是探针刻意构造的边界样本，判官分歧属预期内的合理分歧，**不构成判官失效**，仅说明该边界需人工准则进一步明确。
- 其余三类（remembered / forgotten / fabricated）两判官均 100% 命中，判别极其清晰。

## 6. 对 spec-042 的回写建议

1. **不要**把 `memory_correctness` 维度标注为「不可用」。本 Task 证明：只要输入良定（带 prior
   context 的记忆探针 + 三段式 `{ctx}/{q}/{a}` 判官 prompt），该维度可由 `qwen3.5:9b` 稳定判别
   （G1=1.0 / G2=0.975 / G3=0.95，全部过阈）。Task 02 的 L2 是**数据不适定**而非维度不可评。
2. **保留并采用新 prompt 与探针形态**：将 `config.memory_correctness.user_tmpl` 的三段式模板
   作为该维度标准判官模板；真实评测时输入须携带 prior context（如会话记忆摘要），否则退化为 Task 02 的随机态。
3. **gold 仍非人工标注**：本结论只证明「判官在构造真值上的判别有效性下界很高」，不证明「判官=人类」。
   spec-042 应明确：memory_correctness 的判官结论为**自动化判别有效**，但**人类一致率待 Task 04 真实 trace + 人工标注**补算；在获得人工标注前，该维度 score 仅作相对排序参考，不宜单独作为「记忆能力达标」的硬证据。
4. **输入前置条件写回 spec**：memory_correctness 评测要求样本必须含「先前陈述上下文」，缺失该上下文的样本应被分类为 skipped/不适用，不得强行四选一。

## 7. 产物文件

| 文件 | 说明 |
|---|---|
| `docs/sdd/plans/042/task-03-memory-probe-result.json` | 逐条明细（labels/majority/gold/gold_match/unavailable_count/cross_match）+ 汇总门禁 |
| `docs/sdd/plans/042/task-03-memory-probe-progress.ndjson` | 分批落盘进度（每完成一条 append 一行，防长跑中断丢数据） |
| `docs/sdd/plans/042/task-03-memory-probe-run.log` | 实跑 stdout（含最终 SUMMARY） |
| `backend/eval_042/memory_probe.py` | MemoryProbe / MEMORY_PROBES(20) / build_probe_dataset / run_probe（新增） |
| `backend/eval_042/config.py` | memory_correctness 三段式模板 + GOLD_ACC_THRESHOLD/CROSS_AGREE_THRESHOLD（修改，chat_quality 未动） |
| `backend/eval_042/judge_client.py` | judge_one/judge_repeats 增加可选 ctx，向后兼容（修改） |
| `backend/eval_042/test_memory_probe.py` | 纯函数单测（19 passed），无网络（新增） |

## 8. 复现实命令

```bash
cd backend && source ../.venv/bin/activate
python -m pytest eval_042/test_memory_probe.py -q        # 19 passed
python -c "from eval_042.memory_probe import run_probe; \
  run_probe('qwen3.5:9b','qwen3.8:27b',3, \
  '/abs/path/docs/sdd/plans/042/task-03-memory-probe-result.json', \
  progress_path='/abs/path/docs/sdd/plans/042/task-03-memory-probe-progress.ndjson')"
```

## 9. 风险与遗留

- **遗留（非阻断）**：gold 为构造真值，人类一致率未知（需 Task 04）。
- **提示**：`backend/eval_042/consistency.py:86` 存在 pre-existing ruff F841（`n = len(results)` 未使用），
  属 Task 02 遗留、不在本 Task 文件边界内，按最小改动原则未改，仅在此备案。
- 实跑中曾因前台命令超时产生孤儿进程并与后台进程并发写同一进度文件；已 KILL 并重跑得到上表干净结果。
