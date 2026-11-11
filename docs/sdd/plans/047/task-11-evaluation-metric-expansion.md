# 追加范围二 Task11：评测指标扩展（后端）

> 状态：**已完成** ｜ 关联 [spec-047 追加范围二](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引 [README](./README.md)
> 分派：`backend-dev` ｜ 依赖：需求评审 §14 + 技术评审「追加范围二」均通过（P0=0/P1=0）
> 调研底稿：[OpenEvals 可行性矩阵](../../notes/047-openevals-metric-feasibility.md)

## 1. 一句话目标

把 `POST /api/evaluation/score` 的 `metrics[]` 从 6 项扩到 **22 项**、每项带 `group`，全部真实出分，
不新增端点、不建第二套判官框架、不伪造任何数值。

## 2. 文件边界（严格遵守）

**只允许改**：`backend/app/evaluation/contracts.py`、`metrics.py`、`service.py`、
新建 `backend/app/evaluation/rubrics.py`、新增 `tests/evaluation/test_*.py`（按能力命名，**文件名禁含 spec/task 编号**）。

**禁止改**：`backend/eval_042/**`（既有判官与枚举映射）、`backend/app/api/routes_evaluation.py`、
`backend/app/evaluation/datasets.py` / `store.py`（除非发现 blocking bug，须回传说明）、
`backend/app/knowledge_base/**`、`frontend/**`、任何 `.env` / 配置 / 业务对话链路 / SSE 帧。

## 3. 数据模型

### 3.1 注册表（`contracts.py`）

- `METRIC_KEYS` 由 6 项扩到 **22 项**，顺序固定：先既有 6 项，再新增 16 项（保持既有 6 项顺序不变）。
- `METRIC_LABELS` 必须为全部 22 个 key 提供中文 label —— `build_metric:133` 直接取 `METRIC_LABELS[key]`，
  **漏一个即 `KeyError`**。
- 新增 `METRIC_GROUPS: dict[str, str]`，把 22 个 key 映射到
  `retrieval` / `intent` / `answer_quality` / `generation` / `safety`。
- `build_metric(...)` **内部**按 `METRIC_GROUPS.get(key, "other")` 写入 `group` 字段（不新增必填参数、
  不改 `:127-130` 的「非 computed 时 `value=None` + `detail.reason` 必填」约束）；`uncomputed_metric` 自动继承。
- `SCORE_TIMEOUT_SECONDS=300`、`DEFAULT_MAX_ITEMS=3`、`MAX_ITEMS=20`、`ERROR_SPECS`、策略注册表**全部不动**。

### 3.2 22 个 key 与分组

| 组 | key | 说明 |
|---|---|---|
| retrieval | `recall@k` / `precision@k` / `mrr@k` | 既有，计算逻辑不变 |
| retrieval | `hit_rate@k` | 至少命中 1 条相关片段的样本占比 |
| retrieval | `ndcg@k` | 二值相关性 DCG / 理想 DCG；理想 DCG=0 时不出分 + `reason`，不除零 |
| retrieval | `retrieval_relevance` | 固定判官对 question 与 top-k `Hit.text` 的相关性均分 |
| intent | `intent_accuracy` | 既有，逻辑不变 |
| intent | `intent_macro_f1` | 逐类 precision/recall 宏平均 F1；`detail.per_class` 给各类明细 |
| intent | `intent_confusion_count` | 预测 ≠ 标注的样本数 |
| answer_quality | `chat_quality` | **既有 `judge_majority` + `enum_to_score` 路径完全不动** |
| answer_quality | `memory_correctness` | 既有，仍因无真值 `needs_ground_truth` + `reason` |
| answer_quality | `answer_relevance` / `conciseness` / `helpfulness` / `groundedness` / `hallucination_free` | 联合判官 rubric |
| answer_quality | `answer_exact_match` | 实时回答 vs 冻结 `output` 完全相等比例 |
| answer_quality | `levenshtein_similarity` | 归一化编辑相似度均值 |
| generation | `generation_success_rate` | 实时生成成功数 / 样本数 |
| generation | `answer_length_avg` | 实时回答平均字符数（诊断量，不是质量分） |
| safety | `toxicity_free` / `pii_leakage_free` | 联合判官 rubric |

> 22 = 既有 6 + 检索 5 + 意图 2 + 回答质量 7 + 生成 2 + 安全 2。
> 所有新增 key **方向统一为「越高越好」**。
> `answer_exact_match` / `levenshtein_similarity` 的 `detail` 必带
> `reference="frozen-042-output"` 与 `note="字面一致性，不代表回答质量"`。

### 3.3 新增 `rubrics.py`（联合判官，唯一传输层）

- **唯一传输层**：`backend/eval_042/judge_client.py:154` 的 `call_ollama(model, messages, timeout=180) -> str`。
  不得自建 HTTP 客户端、不得改 `eval_042`、不得调用 `judge_majority`（它绑定单 `task`，不适合多 rubric）。
- `RUBRIC_KEYS = ("answer_relevance", "conciseness", "helpfulness", "groundedness", "hallucination_free", "toxicity_free", "pii_leakage_free")`。
- 一次 prompt 要求判官输出**严格 JSON object**：key 为上述 7 项，value 取 `good|mixed|poor`；
  `enum_maps` 映射 `good=1.0 / mixed=0.5 / poor=0.0`（对 `*_free` / `hallucination_free`，`good` 表示未发现该问题）。
- `parse_rubric_response(text) -> dict[str, float]`：容错剥离代码块围栏、只接受已知 key 与合法枚举；
  **任一关键字段缺失或整体无法解析 → 抛 `ValueError`**，由上层把整批新判官维度转 `degraded` + `reason`，
  绝不逐维度编造分数、绝不静默记 0。
- 判官模型固定 `contracts.JUDGE_MODEL`，`timeout` 不得超过剩余 deadline。

## 4. 实施步骤（`metrics.py`）

1. **纯函数可复算**（放在模块顶层，便于契约测试用 fixture 断言）：
   `hit_rate_from_ranks(ranks)`、`binary_ndcg(hit_keys, relevant_keys)`、`intent_macro_f1(predictions, expected)`、
   `levenshtein_similarity(a, b)`（归一化到 `[0,1]`，空串对空串记 1.0，单边空串记 0.0）。
2. `aggregate_retrieval` 在既有返回 dict 上**追加** `hit_rate` / `ndcg`，不改既有 `recall` / `precision` / `mrr` / 其它字段。
3. `intent_metrics` 在既有返回上追加 `intent_macro_f1` / `intent_confusion_count`（复用同一次 `detect_skill` 结果，
   **不重复调用**）。
4. 新增 `answer_quality_metrics(chat_items, max_items, under_test_model, deadline)`：
   - 复用既有 `_generate_live_answer`（`GENERATION_TIMEOUT_SECONDS=60`）**每条样本只生成一次**，answers 列表供所有新维度共用；
   - 生成失败：沿用既有「失败不伪造」原则，`chat_quality` 保持既有降级，**新判官维度整批 `degraded` + `reason`**；
     但 `generation_success_rate` / `answer_length_avg` 可基于真实成功数出分。
   - `groundedness` 的 context 取 `hybrid_search(question, top_k=...)` 返回的 `Hit.text` 拼接（截断到安全长度）；
     KB 不可用则该维度 `degraded` + `reason`，不伪造。
   - `answer_exact_match` / `levenshtein_similarity` 对 `chat_items[i]["output"]`（042 冻结参考）比对。
   - 返回 9 个新 key 的 metric dict（7 判官/规则 + 2 生成诊断），**不含** `chat_quality` / `memory_correctness`。
5. 新增 `retrieval_relevance_metrics(items, strategy, max_items)`：对 `rag-retrieval` 的 `question` 调
   `hybrid_search`，取 top-k `Hit.text` 与 question 交给固定判官做**一次批量**相关性打分；
   失败 `degraded` + `reason`。
6. `reranker_state()` / `_registry_skills()` / `_judge_score()` / `judge_metrics()` 的既有签名与语义**不改**
   （`chat_quality` 路径必须保持 `answer_source="live_generation"` 与 `generation_model_used=True`）。

## 5. `service.py` 编排

- `score()` 的 `computed` 字典收集全部 22 项；新增维度**必须共用同一个 `deadline`**，并纳入既有
  `_call_with_deadline(fn, remaining)`，不得新开无截止线程（技术评审强制项）。
- 跨 dataset 不出分的口径沿用既有：`_rag_metrics` / `_intent_metrics` / `_judge_metrics` 的
  `needs_ground_truth` + `reason` 分支扩展到新增同组 key；`rerank-on` / v2 的降级分支同样覆盖新检索 key。
- `compare()` 的 `deltas[]` 每项追加 `"group": METRIC_GROUPS.get(key, "other")`；
  缺 key 继续跳过，**历史 6 项 run 必须天然兼容**（`store.save_run` 不裁剪字段，实测已确认）。
- `run_document` 结构不变（仍是 `run_id / metrics / strategy / model / dataset / created_at / judge_model`）。

## 6. 测试（TDD：先写失败用例再实现）

新增 `tests/evaluation/` 下按能力命名的测试文件（**禁含 `spec047` / `task11` 等编号**），至少覆盖：

- 22 个 key 全部存在且各带合法 `group`；`METRIC_LABELS` 全覆盖、`build_metric` 不 `KeyError`。
- `hit_rate` / `ndcg` / 宏 F1 / `levenshtein_similarity` 用可控 fixture 可复算（含空集、理想 DCG=0、单边空串）。
- `parse_rubric_response` 正常 JSON / 带围栏 / 缺字段 / 非法枚举 / 非 JSON → 成功或抛 `ValueError`。
- 联合判官失败 → 7 个判官维度全 `degraded` 且 `value=null` + `reason`，不出现 0。
- 所选模型真实进入 `_generate_live_answer`（patch 断言），且不回退冻结 `output`。
- `compare` 对历史 6 项 run 不报错、新 22 项 run 的 `deltas[]` 带 `group`。
- 五端点错误码与路径穿越回归用例不受影响。

验收命令（回传真实输出）：
```
cd backend && ../.venv/bin/python -m pytest -q ../tests/evaluation
cd /Users/wjh/ResearchAgent && .venv/bin/python -m pytest -q tests/evaluation/test_evaluation_api_contract.py
.venv/bin/ruff check backend/app/evaluation
```

## 7. 明确不做 / 反伪造红线

- 不引入 `openevals` 依赖、不改 `backend/eval_042/**`、不新增端点 / DB 表 / 迁移 / SSE 事件。
- 缺真值的一律 `needs_ground_truth` / `degraded` / `unavailable`，`value=null` + `detail.reason` 必填；
  **绝不硬编码分数、绝不静默记 0、绝不把缺数据渲染成 0.0000**。
- B/C/D 档指标（correctness with reference、trajectory、task_completion、多轮模拟、代码沙箱等）不进注册表。
- 不把冻结 `output` 说成人工标准答案；内置集仍 `builtin-fixture` / `synthetic:true` / `label_source`。
- 不扩大 `max_items` 默认值、不突破 300s；不 push、不合 main。

## 8. 产出物 / 变更日志

- 代码：`contracts.py` / `metrics.py` / `service.py` / 新增 `rubrics.py`。
- 自测：定向 pytest 真实输出（命令 + 退出码 + passed 数）、`ruff check` 结果、`py_compile` 结果。
- 落盘交接：`docs/sdd/plans/047/runs/task-11/implementation.md`（改动文件、决策依据、风险、阻塞、主会话下一动作）。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-11/backend-dev/<YYYYmmdd-HHMMSS>.md`，每步「观察/判断/下一步/进度 X%」，回传必须给日志路径。
- 新建文件只能用 `Bash` heredoc（定界符加单引号），创建后 `Read` 读回校验。
