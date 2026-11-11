# Spec 047 追加范围：评测台人工验收详情

生成时间：2026-11-10（Asia/Shanghai）｜分支：`feature/spec-047-evaluation-p2-and-observability-fixes`
状态：**已完成真实 API + 真实浏览器 E2E，等待用户人工验收**

> 归属：按用户要求「不新增 spec 号码，归为 047 的追加功能」，独立 Spec048 已删除，设计定稿写入
> `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 第 342–520 行（D7–D12）。
> 本文档只做验收编排，不含代码改动。

---

## 0. 一句话结论

现在可以在界面上**选策略 + 选模型 + 选评测集 → 点「开始评分」→ 看到每个维度独立的分数**：
RAG 的召回率@k / 准确率@k / MRR@k、意图识别准确率、回答质量均分。分数来自真实
`hybrid_search` / `detect_skill` / 被测模型实时生成 + 固定判官，**不是 mock、不是占位**。

真实浏览器已验证：`召回率@k=0.3333`、`准确率@k=0.0667`、`MRR@k=0.3333`、
`意图识别准确率=1.0000`；策略 `baseline → topk-10` 时 `召回率@k` 的真实 delta 为 **+0.6667**。

---

## 1. 打开服务

| 项 | 值 |
|---|---|
| 主应用 | <http://127.0.0.1:8000>（`/api/health` 实测 200） |
| **评测台直达** | <http://127.0.0.1:8000/#evaluation-view> |
| 静态资源 | `app.js?v=74`、`styles.css?v=71`（均实测 200） |
| 启动命令 | `cd /Users/wjh/ResearchAgent && ./deploy/start.sh -d` |
| 停止命令 | `./deploy/stop.sh` |
| 当前配置 | 主服务 PID 见 `deploy/run.pid`；Ollama `/api/tags` 可用；KB 64 篇 / 19905 chunks |

> Langfuse `:3000` 未启动。本范围打分落点是本地 run 产物 + 界面展示，Langfuse 仅作既有 score 可选落点，
> **不据此判定失败**。浏览器控制台里 4 条 `/api/conversations/{id}` 404 属于其它视图的历史会话数据，与评测无关。

---

## 2. 主案例：界面三选一 → 打分 → 看分维度分数

### 步骤 1 — 打开评测台

- **操作**：打开 <http://127.0.0.1:8000/#evaluation-view>（或左侧导航点「评测」）。
- **点击后的提示**：标题「评测」，说明文字「选择策略、被测模型与评测集，真实打分后逐维度查看分数、状态、样本数与明细」；状态栏显示「选项已加载：请选择策略、模型与评测集后点击『开始评分』。」
- **等待条件**：三个下拉都出现选项即就绪（数据来自 `GET /api/evaluation/options`，实测 4 策略 / 12 模型 / 3 评测集）。
- **下一步**：步骤 2。

### 步骤 2 — 选择策略 / 模型 / 评测集（RAG）

- **操作**：依次选
  - 策略 `基线（v1 / top_k=5 / reranker=off）`（值 `baseline`）
  - 模型 `qwen3.5:9b`
  - 评测集 `RAG 检索召回`（值 `rag-retrieval`）
- **点击后的提示**：下拉显示所选文本；「开始评分」按钮可用。
- **下一步**：步骤 3。

### 步骤 3 — 点「开始评分」

- **操作**：点击「开始评分」。
- **点击后的提示**：按钮进入禁用态 + spinner，状态栏显示「正在对 N 条样本真实打分」；**不出现「功能已降级 / 关闭」类隐藏态**。
- **等待条件**：等 `POST /api/evaluation/score` 返回 200（RAG 集走真实 KB 检索，通常数秒内）。超时按 `EVAL_SCORE_TIMEOUT` 提示，不无限等待；期间可查看已有运行历史。
- **下一步**：步骤 4。

### 步骤 4 — 看「每一部分的分数」

- **操作**：查看「分维度分数」区，逐张卡片核对。
- **点击后的提示**（本次真实浏览器读数，样本数 3）：

  | 卡片 | 数值 | 状态 | 明细要点 |
  |---|---:|---|---|
  | 召回率@k | `0.3333` | 已计算 computed | k=5 / chunker=v1 / reranker=off / matched_items=1 / first_relevant_ranks=[1,null,null] |
  | 准确率@k | `0.0667` | 已计算 computed | 同上，identity = paper_id,chunker,chunk_index |
  | MRR@k | `0.3333` | 已计算 computed | 同上 |

- **说明**：每张卡同时显示数值 / 状态 / 样本数 / 明细。非适用维度（如本集下的意图、回答质量）也**如实显示卡片**，
  标 `needs_ground_truth` 并给出 reason，不隐藏、不显示假 0。
- **下一步**：步骤 5（看策略提升）。

### 步骤 5 — 切换策略，看效果提升

- **操作**：策略改选 `扩大召回（v1 / top_k=10 / reranker=off）`（`topk-10`），模型与评测集不变，再点「开始评分」。
- **点击后的提示**：`召回率@k` 应升到 `1.0000`，`MRR@k` 约 `0.4306`，`准确率@k` 约 `0.1000`。
- **下一步**：在「两次对比」区，运行 A 选 baseline 那次、运行 B 选 topk-10 那次，点「对比」。
- **期望**：按维度显示 delta，例如 `召回率@k +0.6667`、`MRR@k +0.0972`；运行历史与比较下拉显示**可读策略名**（不是 `[object Object]`）。
- **注意**：不同评测集 / 不同判官的组合返回「不可比」且**不给 delta**，不是故障。

### 步骤 6 — 看意图识别准确率

- **操作**：评测集改选 `意图识别分类`（`intent-classification`），其余不变，点「开始评分」。
- **点击后的提示**：卡片「意图识别准确率」显示 `1.0000`、状态 computed、样本数 3，明细给出
  `detector=backend.app.skills.intent.detect_skill`、`prediction_sources=["rule","rule","rule"]`、`matched=3`。
- **下一步**：步骤 7（看模型差异）。

### 步骤 7 — 看「选模型」确实影响分数

- **操作**：评测集改选 `回答质量（既有判官轨迹）`（`chat-quality`），分别用
  `qwen3.5:9b` 与 `qwen3.8:27b-q4` 各打一次分，比较「回答质量（判官均分）」。
- **点击后的提示**：所选模型**实时生成回答**，再由固定判官 `qwen3.5:9b` 打分。实现自测两次分别得到
  `0.5` 与 `1.0`，`detail.answer_source=live_generation`、`generation_model_used=true`。
- **等待条件**：生成 + 判官比纯检索慢（默认 3 条，单条生成上限 60s，整次 300s 超时保护）；请等到状态栏回到完成态。
- **说明**：RAG 三维与意图维度**不使用所选模型**（固定 embedding / 模块固定识别链路），卡片明细里明确标
  `model_participates=false` + 原因。这是系统真实状态，不是隐藏功能。

### 步骤 8 — 失败恢复

| 现象 | 原因 | 恢复 |
|---|---|---|
| 下拉为空 / 选项不存在 | 后端或 `/api/models` 未就绪 | 确认 `/api/health` 200 后刷新页面；按 `EVAL_OPTION_NOT_FOUND` 提示重选 |
| 某张卡显示 `degraded` / `unavailable` + reason | 判官或所选模型生成超时（如本机 27b 大模型 60s 内未完成） | 换一个较小本地模型重试；**该维度不会编造数值、也不会回退冻结 output** |
| 选 `rerank-on` 后 RAG 三维 `degraded` | 当前 KB `reranker available=false(reason=connection)` | 如实降级 + 原因，不伪造收益；换 `baseline`/`topk-10` 继续验收 |
| 选 `chunker-v2` 后 RAG 三维 `needs_ground_truth` | 内置标注集只冻结了 v1 片段身份，无 v2 真值 | 换 `baseline`/`topk-10`；如需 v2 真值须另补标注集 |
| `memory_correctness` 恒 `needs_ground_truth` | 042 集 24 条无 `prior_context` / 记忆真值 | 属如实降级，非缺陷 |
| 对比显示「不可比」 | 跨 dataset / 跨判官 | 选两次同 dataset 的运行再对比 |
| 页面仍是旧版 | 浏览器缓存 | 刷新；活跃资源已是 `app.js?v=74` / `styles.css?v=71` |

---

## 3. 「为什么之前的指标打分都看不到」——答复

用户问「之前用了 openeval 或别的框架也做了一些指标打分，为什么现在都看不到」。核实结果：

1. **「openeval」是 Spec042 的标题，不是引入的框架**。全仓代码/依赖搜 `openeval|openevals` 零命中。
   042 的 Q9=C 设想用 Langfuse 内置 23 个 evaluators（含 Context Recall/Precision/Faithfulness），
   但被 `docs/sdd/specs/042-openeval-agent-evaluation.md:95-99` 的 F17 证伪：本机 Ollama `/v1`
   不支持 `response_format: json_schema`。最终落地的是**自建 LLM-as-judge，Langfuse 只作 score 落点**。
2. **真实实现只有 2 个判官 task**：`chat_quality` / `memory_correctness`（`backend/eval_042/runner.py:36`），
   每条只有一个枚举映射的单值分数。**没有召回率、准确率、意图识别准确率的计算函数**；
   唯一 RAG 相关性标注是 `docs/sdd/reviews/014-reranker-benchmark.md` 的 10 题 markdown 表（绑定历史 Qdrant 快照），
   唯一意图标注是 `docs/sdd/plans/023/.../probe_intent.py` 的 20 条旧 CASES（写死旧 IP 与过时技能名）。
3. **Langfuse 上那 7 个 score 是性能指标，不是质量分**：`ttft_ms/load_ms/prompt_eval_ms/eval_ms/overhead_ms/tokens_per_sec/is_cold_start`
   （`backend/app/platform/observability/spans.py:68-76`）；前端「受控基准摘要」四项也是性能基准。
4. **看不到的直接原因**：042/045/047 明确「不新增业务端点 / 不新增前端页面」；`backend/app/api/` 原无评测端点，
   产物只写本地 `--output-dir` 的 `report.json`，前端只有一个纯文本性能卡片。**没有任何界面暴露质量分**。

本次追加范围在用户授权下推翻了这些旧边界，新增 5 个只读/打分端点与第 9 个视图，
并把多维度指标做成可真实计算、逐卡可见的产品能力。

---

## 4. 分维度分数能力清单（如实标注）

| 维度 | 指标 | 是否真实出分 | 依赖 |
|---|---|---|---|
| RAG 检索 | `recall@k` / `precision@k` / `mrr@k` | 是 | 真实 `hybrid_search` + 内置标注集（`label_source: kb-derived:retrieval-rank`，8 条从当前 KB 真实文档派生） |
| 意图识别 | `intent_accuracy` | 是 | 真实 `detect_skill` 与 `expected_intent` 比对（技能名对齐当前注册表） |
| 回答质量 | `chat_quality` | 是 | 所选模型**实时生成回答** + 固定判官 `qwen3.5:9b` |
| 记忆一致性 | `memory_correctness` | 否（`needs_ground_truth` + reason） | 042 集无 `prior_context` / 记忆真值 |
| 重排策略 | RAG 三维 | 否（`degraded` + reason） | 当前 `reranker available=false` |
| 切分 v2 策略 | RAG 三维 | 否（`needs_ground_truth` + reason） | 标注集只有 v1 片段身份 |

> 内置标注集明确标 `source: builtin-fixture` / `synthetic: true` / `label_source`，
> **不冒充人工标注、不冒充真实业务数据**；014 十题因当前 KB 只剩 1 个 `paper_id` 而不适用，
> 对齐验证结论落盘在标注集的 `kb_alignment` 字段。

---

## 5. 产物路径速查

| 产物 | 内容 |
|---|---|
| `docs/sdd/plans/047/runs/task-10/evaluation-api-e2e.json` | 真实 API 请求 / 响应 / HTTP 码 / run_id / 分维度分数 / compare `deltas[]` |
| `docs/sdd/plans/047/runs/task-10/browser-e2e.json` | 真实浏览器 DOM 契约、两次打分的分维度分数、截图与快照路径 |
| `docs/sdd/plans/047/runs/task-08/http-selftest-part*.json` | 后端五端点真实 HTTP 取证 |
| `docs/sdd/plans/047/runs/task-08/implementation.md` | 后端实现交接 + 红绿测试 + 被测模型修复记录 |
| `docs/sdd/plans/047/runs/task-09/implementation.md` | 前端实现交接 + `?v=N` 契约 + `[object Object]` 修复记录 |
| `docs/sdd/plans/047/gold/builtin-*.json` | 三份内置标注评测集（含 `kb_alignment`） |
| `docs/sdd/plans/047/runs/evaluation/` | 每次打分的 run 产物 JSON |
| `docs/sdd/reviews/047-acceptance-review.md` | 追加范围验收结论 |
| `.playwright-cli/eval-scored.png` / `eval-scored.yaml` / `eval-intent.yaml` | 浏览器截图与快照 |

---

## 6. 已知限制（如实声明）

- 内置标注集是**合成/派生**的，不是真人标注；`human_agree_rate` 的真实值仍需用户提供 ≥20 条脱敏人工标注（反伪造红线不解除）。
- RAG / 意图维度不使用所选被测模型；只有 `chat_quality` 由所选模型实时生成。
- `reranker` 当前不可用、`chunker-v2` 无 v2 真值、`memory_correctness` 无记忆真值 —— 这些维度如实标状态 + 原因，不编造数值。
- `chat_quality` 用实时生成，分数可能随模型/采样波动；不同数据集或不同判官的运行**不可比**，接口返回 `EVAL_NOT_COMPARABLE` 且不含 delta。
- 本轮未改 `EVAL_ONLINE_*` 默认（在线旁路仍默认关闭）；P2 三项的「不再降级/关闭态」在本次体现为**评测台常驻可用、点一次跑一次、结果立即可见**，不是「每次对话自动评测」。
- 不 push、不合 main，`origin/main` 仍 `1b26c76c`。

---

## 7. 人工验收签字

| 项 | 填写 |
|---|---|
| 验收人 | ______________ |
| 验收日期 | ______________ |
| 主案例（步骤 1–5） | ☐ 通过　☐ 不通过 |
| 意图识别准确率（步骤 6） | ☐ 通过　☐ 不通过 |
| 选模型影响分数（步骤 7） | ☐ 通过　☐ 不通过 |
| 结论 | ☐ 通过　☐ 不通过（原因：______________） |
| 备注 | ______________ |
