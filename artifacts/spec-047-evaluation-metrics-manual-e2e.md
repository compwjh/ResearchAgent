# Spec-047 追加范围二：评测指标扩展 人工验收详情

> 生成时间：2026-11-10 ｜ 服务：`http://127.0.0.1:8000`（`RERANKER_ENABLED=false ./deploy/start.sh -d`）
> 前置：`/api/health` 返回 200；`app.js?v=75` / `styles.css?v=72` 已生效（硬刷新 `Cmd+Shift+R` 一次）
> 证据目录：`docs/sdd/plans/047/runs/task-13/`
> **代行留痕**：纯文档改动，由主会话代行；三处留痕为本文件头部、`spec-status-changelog.md` 收口条目、复盘文档。

## 你要验收什么

一次选择「策略 + 模型 + 评测集」后，评测台真实打分并按 **5 个分组展示 22 个维度**的分数；
切换策略再用「两次对比」看**按组、按维度**的提升。回答质量维度已从 2 项细化到 11 项真实出分。

## 逐步操作

### ① 打开评测台

- 左侧导航点「**▦ 评测**」（第 9 个视图）。
- **点击后提示**：页面顶部状态条显示「选项已加载：请选择策略、模型与评测集后点击「开始评分」」；三个下拉分别显示策略、模型、评测集列表。
- 若提示「评测选项加载失败」，见「失败恢复」。
- 产物：`docs/sdd/plans/047/runs/task-13/eval-initial.yaml`（初始快照）。

### ② 三选一并打分（回答质量组）

- 策略选 `baseline`，模型选 `qwen3.5:9b`（或 `GET /api/evaluation/options` 返回的任一可用本地模型），
  评测集选 **`chat-quality`**。
- 点「**开始评分**」。
- **点击后提示**：按钮变「评分中…」并禁用，状态条显示「正在对 N 条样本真实打分（多维打分可能耗时数分钟，请稍候）」。
- **等待条件与提示**：这一步会**用所选模型实时生成回答，再由固定判官 `qwen3.5:9b` 打分**，
  实测约 **127 秒**（2 条样本）。期间不要刷新页面；可切到「运行历史」看已完成的 run。
  完成后状态条变成「评分完成：`<run_id>`」，按钮恢复可用。
- **下一步**：看指标卡片区，应出现 5 个分组标题：
  **检索质量 / 意图识别 / 回答质量 / 生成可用性 / 安全**。
  其中「回答质量」组应看到 11 项真实数值，例如：
  回答切题度 `0.5000`、简洁度 `1.0000`、有用性 `0.5000`、有据性 `0.0000`、无幻觉比例 `1.0000`、
  字面完全一致率 `0.0000`、编辑相似度 `0.0662`、生成成功率 `1.0000`、平均字符数 `281.5000`、
  无有害内容 `1.0000`、无个人信息泄漏 `1.0000`。
  鼠标悬停任意卡片可看样本数与明细（含字面指标的「不代表回答质量」说明）。
- **重要预期**：`chat-quality` 集下，检索组与意图组显示「缺少标注（`needs_ground_truth`）」并带原因，
  `memory_correctness` 同样带原因。**这不是功能关闭**——卡片照常显示、原因照常可见，只是本集没有对应标注，
  系统不会伪造分数，也不会把 `null` 显示成 `0`。

### ③ 看检索与意图组（切换评测集）

- 把评测集切到 **`rag-retrieval`**，策略保持 `baseline`，再点「开始评分」（实测约 45–60 秒）。
  检索组应出现 6 项：召回率@k、准确率@k、MRR@k、命中率@k、nDCG@k、检索片段相关性。
- 再把评测集切到 **`intent-classification`**，再点「开始评分」（实测 < 1 秒）。
  意图组应出现 3 项：意图识别准确率、意图宏平均 F1、意图混淆数，本次实测 `1.0000 / 1.0000 / 0.0000`。
- 想快速回看，直接在「**运行历史**」点任意 run 即可，无需重新打分。
- 产物：`docs/sdd/plans/047/runs/task-13/eval-scored.yaml`、`eval-scored.png`。

### ④ 两次对比，看策略带来的逐维度提升

- 在「两次对比」区：A 选 `baseline` + `rag-retrieval` 的 run，B 选 `topk-10` + `rag-retrieval` 的 run，
  点「**对比**」。
- **点击后提示**：按 5 个分组列出逐维度 `delta`，例如：
  召回率@k `+0.5000`、准确率@k `+0.0000`、MRR@k `+0.0833`、命中率@k `+0.5000`、
  nDCG@k `+0.1781`、检索片段相关性 `-0.5000`。
- 无可比数值的维度显示 `—`（不是 `0`）；跨不同评测集 / 判官轨迹的两次 run 会提示「不可比」且不返回 delta。
- 产物：`docs/sdd/plans/047/runs/task-13/eval-final.yaml`、`evaluation-metrics-api-e2e.json`。

## 失败恢复

| 现象 | 原因 | 恢复动作 |
|---|---|---|
| 「评测选项加载失败」 | 服务未起或端口不对 | `curl http://127.0.0.1:8000/api/health`；非 200 则 `RERANKER_ENABLED=false ./deploy/start.sh -d`，再硬刷新 |
| 「评测服务不可用」 | Ollama 未启动 / 模型缺失 | `ollama list` 确认 `qwen3.5:9b` 存在；`ollama serve`；判官维度如实显示 `degraded` + 原因，其余维度照常出分 |
| 「评分超时」 | 多维打分含实时生成，单模型负载高 | 重试一次；或先选 `intent-classification`（<1s）确认链路，再跑 `chat-quality`；前端超时已与服务端 300s 对齐 |
| 某维度显示「缺少标注」 | 所选评测集没有该组标注 | 按第 ③ 步切换到对应评测集；卡片始终可见、原因始终可读 |
| `rerank-on` 显示 `degraded` | 本地 reranker `available=false` | 如实降级，不是故障；选 `baseline` / `topk-10` 即可看正常出分 |
| 对比报「不可比」 | 两次 run 的 dataset 或判官轨迹不同 | 改选同 dataset 的两次 run |
| Langfuse `:3000` 打不开 | 本次未启动 | 不判失败；本范围产物落本地 run 与界面 |

## 产物查看路径

| 想看什么 | 路径 |
|---|---|
| 真实 API 请求 / 响应 / HTTP 码 / 22 维度分数 | `docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json` |
| 浏览器初始 / 评分后 / 最终快照 | `docs/sdd/plans/047/runs/task-13/eval-{initial,scored,final}.yaml` |
| 浏览器截图 | `docs/sdd/plans/047/runs/task-13/eval-scored.png` |
| 逐次 run 原始产物 | `docs/sdd/plans/047/runs/evaluation/{run_id}.json` |
| 后端 / 前端评审与 P1 复审 | `docs/sdd/reviews/047-{backend,frontend}-metrics-review.md` |
| 验收评审签字 | `docs/sdd/reviews/047-acceptance-review.md` §14 |
| 全量回归输出 | `docs/sdd/plans/047/runs/task-13/full-regression.txt` |
| 复盘 | `docs/sdd/retro/2026-11-10-spec047-evaluation-metrics-expansion-closure.md` |

## 已知非阻塞项

- 全仓 1 个与本次无关的手势性能阈值 wall-clock flaky（`test_frontend_map_feasibility.py`，阈值 1000ms、
  实测约 1013ms、间歇 PASS），如实记录、未擅自放宽阈值。
- 浏览器控制台 4 个 `/api/conversations/{id}` 404 来自其它视图的历史会话列表，与评测台无关。
- Langfuse `:3000` 未启动，按 spec 不判失败。

## 验收签字

| 项 | 结论 | 签字 |
|---|---|---|
| 需求/技术评审 | 通过（P0=0/P1=0） | `architect` |
| 后端 / 前端评审 + P1 集中复审 | 通过（P0=0/P1=0） | `backend-reviewer` / `frontend-reviewer` |
| 真实 API E2E + 浏览器 E2E | 见 `047-acceptance-review.md` §14 | `tester` |
| 全量回归 / 部署验证 | 见 `047-acceptance-review.md` §14 | `tester` |
| 架构师合并裁决 | 见 `047-acceptance-review.md` §14 | `architect` |
