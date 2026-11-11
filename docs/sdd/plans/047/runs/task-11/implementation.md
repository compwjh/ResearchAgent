# Spec047 追加范围二 Task11 后端实现交接（backend-dev / TDD）

> 执行日期：2026-11-10 ｜ 角色：`backend-dev` ｜ 范围：**仅 backend/** + 后端测试**，未碰 `frontend/**`。
> 任务卡：[`../../task-11-evaluation-metric-expansion.md`](../../task-11-evaluation-metric-expansion.md)
> 关联：spec 追加范围二 §2.2–§2.5、调研底稿 §5/§6。
> 进展日志：[`.codebuddy/agent-logs/spec-047/task-11/backend-dev/20261110-062702.md`](../../../../.codebuddy/agent-logs/spec-047/task-11/backend-dev/20261110-062702.md)

## 1. 一句话结论

`POST /api/evaluation/score` 的 `metrics[]` 已由 6 项扩到 **22 项**，每项带 `group`；
`compare.deltas[]` 每项带 `group`；新增 16 项全部真实出分或如实降级，无硬编码分数、无假 0。
五端点路径 / 请求体 / 五个稳定错误码 / `SCORE_TIMEOUT_SECONDS=300` / 默认 `max_items=3` 全部不变。

## 2. 改动文件清单

| 文件 | 类型 | 行数（`git diff --stat` 增删 / 新文件 `wc -l`） | 内容 |
|---|---|---|---|
| `backend/app/evaluation/contracts.py` | 改 | +63 / -0（现 205 行） | `METRIC_KEYS` 6→22、`METRIC_LABELS` 22 个中文 label、新增 `METRIC_GROUPS` / `RUBRIC_ENUM_MAPS`；`build_metric` 返回体加 `group` |
| `backend/app/evaluation/rubrics.py` | **新建** | 139 行（heredoc 创建 + Read 读回校验） | 联合判官解析 / 唯一传输层复用 / 批量检索相关性判官 |
| `backend/app/evaluation/metrics.py` | 改 | +410 / -7（现 730 行） | 4 个纯函数、`aggregate_retrieval` 追加 4 字段、`retrieval_metrics` 3→5、`intent_metrics` 1→3、新增 `retrieval_relevance_metrics` 与 `answer_quality_metrics` |
| `backend/app/evaluation/service.py` | 改 | +53 / -4（现 333 行） | 22 项编排、共用 deadline、`compare` 加 group、注册表缺项稳定 503 护栏 |
| `tests/evaluation/test_metric_registry.py` | **新建** | 129 行 | 22 key / label / group / build_metric 约束 / 常量未扩 |
| `tests/evaluation/test_metric_math_extensions.py` | **新建** | 107 行 | hit_rate / nDCG / 宏 F1 / 编辑相似度可复算 + 既有 6 项语义不变 |
| `tests/evaluation/test_rubric_judge.py` | **新建** | 140 行 | JSON 容错、非法输入 ValueError、唯一传输层、解析失败整批降级 |
| `tests/evaluation/test_expanded_metrics.py` | **新建** | 247 行 | 三组指标真实计算、生成一次/样本、KB 降级、既有 chat_quality 路径 |
| `tests/evaluation/test_score_grouping.py` | **新建** | 262 行 | 22 项按组出分、共用 deadline、历史 run 兼容、错误码与穿越回归 |
| `tests/evaluation/test_evaluation_api_contract.py` | 改（**最小**） | +5 / -9 | 仅 2 处形状断言 + 1 行 import，见 §6 |

未改：`backend/eval_042/**`、`routes_evaluation.py`、`datasets.py`、`store.py`、`knowledge_base/**`、
`frontend/**`、`.env`、任何配置 / DB / 迁移 / SSE 事件 / 业务对话链路。未 git commit / push / 合 main。

## 3. 22 个 key 与 group 映射（唯一源 `contracts.METRIC_KEYS` / `METRIC_GROUPS`）

注册表顺序固定：先既有 6 项（顺序不变），再新增 16 项。

| # | key | group | 计算 / 状态来源 |
|---|---|---|---|
| 1 | `recall@k` | retrieval | 既有，逻辑不变 |
| 2 | `precision@k` | retrieval | 既有，逻辑不变 |
| 3 | `mrr@k` | retrieval | 既有，逻辑不变 |
| 4 | `intent_accuracy` | intent | 既有，逻辑不变 |
| 5 | `chat_quality` | answer_quality | 既有 `judge_majority` + `enum_to_score`，路径逐字保留 |
| 6 | `memory_correctness` | answer_quality | 既有 `needs_ground_truth` + reason |
| 7 | `hit_rate@k` | retrieval | `hit_rate_from_ranks(first_relevant_ranks)` |
| 8 | `ndcg@k` | retrieval | `binary_ndcg`；理想 DCG=0 时 degraded + reason，不除零 |
| 9 | `retrieval_relevance` | retrieval | 整批 question + `Hit.text`，一次判官 |
| 10 | `intent_macro_f1` | intent | `_intent_confusion` 宏平均，`detail.per_class` 逐类明细 |
| 11 | `intent_confusion_count` | intent | 预测 ≠ 标注样本数（复用同一次 `detect_skill`） |
| 12 | `answer_relevance` | answer_quality | 联合判官 rubric |
| 13 | `conciseness` | answer_quality | 联合判官 rubric |
| 14 | `helpfulness` | answer_quality | 联合判官 rubric |
| 15 | `groundedness` | answer_quality | 联合判官 rubric + 真实 `Hit.text` context |
| 16 | `hallucination_free` | answer_quality | 联合判官 rubric |
| 17 | `answer_exact_match` | answer_quality | 实时回答 vs 042 冻结 `output`（规则） |
| 18 | `levenshtein_similarity` | answer_quality | 归一化编辑相似度均值（规则） |
| 19 | `generation_success_rate` | generation | 真实成功数 / 样本数 |
| 20 | `answer_length_avg` | generation | 实时回答平均字符数（诊断量） |
| 21 | `toxicity_free` | safety | 联合判官 rubric |
| 22 | `pii_leakage_free` | safety | 联合判官 rubric |

分组计数：retrieval 6 / intent 3 / answer_quality 9 / generation 2 / safety 2 = 22。
新增 16 项方向统一「越高越好」；B/C/D 档（correctness with reference、trajectory、task_completion、
多轮模拟、代码沙箱、json_match 等）**未进注册表**。

## 4. rubrics.py 解析容错与反伪造

- 唯一传输层：`backend/eval_042/judge_client.py::call_ollama(model, messages, timeout=180) -> str`。
  `judge_rubrics` / `judge_retrieval_relevance` 默认 `transport=call_ollama`，未自建 HTTP、未改 `eval_042`、
  未调用 `judge_majority`。`transport` 注入参数只为让既有契约测试的 `monkeypatch(metrics.call_ollama)`
  能拦截新判官调用（避免测试触网），生产路径仍是同一个 `call_ollama`。
- `RUBRIC_KEYS` 恰 7 项；`RUBRIC_ENUM_MAPS = {good:1.0, mixed:0.5, poor:0.0}` 登记在 `contracts.py`。
  对 `*_free` / `hallucination_free`，`good` 表示未发现该问题。
- `parse_rubric_response(text, keys=RUBRIC_KEYS)`：剥离 ``` / ```json 围栏、取最外层 `{...}`（容忍前后说明文字）、
  `json.loads` → 必须是 dict → 逐个期望 key 取字符串枚举并查表。**缺任一关键字段 / 非法枚举 / 非字符串 /
  非 JSON / 空文本 / 非 object 一律 `ValueError`**；批量检索相关性用 `keys=("0","1",...)` 复用同一解析器。
- `ValueError` 由 `metrics.answer_quality_metrics` 捕获后把**整批 7 个判官维度**转 `degraded` +
  `value=null` + `detail.reason`，不逐维度编造分数、不静默记 0。`retrieval_relevance` 解析失败同样整批降级。
- 生成失败：7 判官维度 + 2 字面规则维度降级；`generation_success_rate` 基于真实成功数出分（0.0 是真实比率，
  不是伪造），`answer_length_avg` 降级 + reason。KB 不可用时**仅** `groundedness` 降级，其余 6 维照常出分。
- 字面指标 `detail` 必带 `reference="frozen-042-output"` 与 `note="字面一致性，不代表回答质量"`；
  `reference_note` 明注「042 冻结参考输出仅作字面比对基线，不是质量真值」，未冒充人工标准答案。
- 新增回答维度的数据来源为内置 042 chat traces（三选一选 rag / intent 时同样真实出分），
  `detail.reference_fixture="builtin-042-chat-traces"`、`answer_source="live_generation"` 明示来源；
  所选被测模型真实进入 `_generate_live_answer`，不回退冻结 `output`。

## 5. deadline / 复用 / 向后兼容

- `service.score()` 沿用 `deadline = time.monotonic() + SCORE_TIMEOUT_SECONDS(300)`，
  `_rag_metrics` / `_intent_metrics` / `_judge_metrics` / `_answer_quality_metrics` 依次 `_check_deadline(deadline)`。
- 新增 `retrieval_relevance_metrics`（含 `hybrid_search` + 判官）与 `answer_quality_metrics`
  （含实时生成 + `hybrid_search` 取 context + 联合判官）**都**经既有
  `_call_with_deadline(fn, deadline - time.monotonic())`，未新开无截止线程；函数内部再用
  `_bounded_timeout(deadline, cap)` 把每次 `call_ollama` 的 `timeout` 收紧到剩余预算
  （生成 cap 60s、判官 cap 180s），超时转稳定 `EVAL_SCORE_TIMEOUT`。测试 `test_new_external_calls_share_one_deadline_through_call_with_deadline`
  用 spy 断言各次 `remaining` 单调不增且均 ≤ 300。
- 复用既有符号：`_generate_live_answer` / `call_ollama` / `judge_majority` / `enum_to_score` / `KNOWN_TASKS`、
  `hybrid_search` / `reranker_health` / `Hit.text`、`detect_skill` / `_registry_skills`、
  `datasets.load_chat_items` / `store.save_run`、`build_metric` / `uncomputed_metric` / `_call_with_deadline`。
  无第二套下载 / 安全 / 导入 / 批任务 / 身份 / embedding / 判官实现。
- `compare()` 仍按 `METRIC_KEYS` 遍历并跳过缺 key；历史 6 项、无 `group` 的 run 可正常读 / 比
  （`store.save_run` 整文档写入不裁剪字段，本轮实测）。`deltas[]` 每项 `group = METRIC_GROUPS.get(key,"other")`，
  历史 run 无 `group` 由前端兜底 `other`。
- 跨 dataset / `rerank-on` / `chunker-v2` 降级分支扩展到同组全部新 key（6 检索 / 3 意图），
  均 `value=null` + `detail.reason`；其余组照常真实出分。

## 6. 既有 6 项语义未变的证据

1. `git diff -- backend/app/evaluation/metrics.py` 中 `judge_metrics` / `_judge_score` /
   `_generate_live_answer` / `reranker_state` / `_registry_skills` / `judge_average` **零删改行**
   （唯一新增的 `answer_source` 行属于新维度 `common_detail`）；`chat_quality` 仍是
   `answer_source="live_generation"`、`generation_model_used=True`、
   `score_mapping="backend/eval_042/config.py::ENUM_MAPS[chat_quality]"`。
2. `test_expanded_metrics.py::test_existing_chat_quality_path_keeps_judge_majority_and_enum_to_score`
   用 spy 断言 `judge_majority` 被调用且 `enum_to_score` 映射 `good→1.0`；
   `test_metric_math_extensions.py::test_aggregate_retrieval_appends_two_keys_without_changing_legacy_results`
   用与既有基线同一 fixture 断言 recall=2/3、precision=2/9、mrr=(1+1/3)/3、first_relevant_ranks=[1,3,None]。
3. 既有三类基线测试 `test_evaluation_api_contract.py` / `test_evaluation_metrics_math.py` /
   `test_evaluation_live_generation.py` → **33 passed**（改动前同为 33 passed，逐字对照）。
4. `test_evaluation_api_contract.py` 的**唯一改动**是把 `:295` 的「恰好 6 个 key」与 `:305` 的
   「恰好 6 个字段」两处**形状断言**升级为 spec §2.3 强制的 22 项 + `group`（并新增一行 import）。
   这是 spec 明确改变的响应形状，无法与旧断言同时成立；其余错误码、路径穿越、数值复算、
   冻结 output 不回退、run 产物一致、compare delta、超时等断言**逐字未动**，且加强了
   `group == METRIC_GROUPS[key]` 的新断言。已在日志与本节留痕。
5. `contracts.py:127-130` 非 computed 约束（`value=None` + `detail.reason` 必填）逐字保留；
   `ERROR_SPECS` / `STRATEGIES` / `SCORE_TIMEOUT_SECONDS` / `DEFAULT_MAX_ITEMS` / `MAX_ITEMS` 未动。

## 7. 验证命令与真实输出（仓库根 `/Users/wjh/ResearchAgent`，`.venv`）

```
# 用户指定验收三连（最终一轮，cwd=/Users/wjh/ResearchAgent）
$ .venv/bin/python -m pytest -q tests/evaluation
290 passed in 3.33s                                     # EXIT=0（复跑 290 passed in 3.03s）

$ .venv/bin/ruff check backend/app/evaluation
All checks passed!                                      # EXIT=0

$ .venv/bin/python -m py_compile backend/app/evaluation/*.py
（无输出）                                              # EXIT=0

# 补充验证
$ .venv/bin/python -m pytest -q tests/evaluation/test_evaluation_api_contract.py \
      tests/evaluation/test_evaluation_metrics_math.py tests/evaluation/test_evaluation_live_generation.py
33 passed in 1.66s                                      # EXIT=0（改动前基线 33 passed in 1.62s）

$ .venv/bin/python -m pytest -q <5 个新增测试文件>
51 passed in 1.02s                                      # EXIT=0（RED 阶段：14 failed + 3 collection error）

$ .venv/bin/ruff check backend/app/evaluation <6 个相关测试文件>
All checks passed!                                      # EXIT=0（修掉 4 处 C420 后）

$ .venv/bin/python -m pytest -q tests/frontend/test_evaluation_view_contract.py
7 passed in 0.24s                                       # EXIT=0（前端既有静态契约未回归）

$ .venv/bin/python -c "from backend.app.evaluation.contracts import ..."
keys= 22 labels= 22 groups= 22
counts= {'retrieval': 6, 'intent': 3, 'answer_quality': 9, 'generation': 2, 'safety': 2}
enums= {'good': 1.0, 'mixed': 0.5, 'poor': 0.0}
missing_labels= []  missing_groups= []
```

TDD 记录：先写 5 个新测试文件 → 跑出 RED（14 failed + 3 `ImportError: cannot import name 'rubrics'` +
既有契约测试 `ImportError: METRIC_GROUPS`）→ 实现 → 首轮 `1 failed, 50 passed`
（失败项为**测试手写宏 F1 oracle 算错**：b 类应为 fp=0/fn=1 → f1=2/3，宏平均 7/9；实现值正确），
修正 oracle（不改实现、不放宽断言）→ `51 passed`。

## 8. 风险 / 阻塞 / 需主会话决策

1. **跨端阻塞（task-12，非本范围）**：`tests/frontend/test_evaluation_metric_grouping.py`
   （工作区里他人并行创建的未跟踪文件）当前 `13 failed, 9 passed`，原因是 `frontend/app.js` /
   `styles.css` / `index.html` 尚未实现按 6 组（含 `other` 兜底）渲染、`?v=N` 升级到 75/72、
   客户端打分超时与服务端 300s 对齐（技术评审 R1(b)）。**我未碰 `frontend/**`**，请主会话转派
   `frontend-dev`（task-12）后再跑该用例。`tests/frontend/test_evaluation_view_contract.py` 已绿。
2. **任务卡 §4.4 计数口径**：任务卡写 `answer_quality_metrics` 「返回 9 个新 key（7 判官/规则 + 2 生成诊断）」，
   但 22 项注册表要求本函数交出 **11** 个（7 联合判官 + 2 字面规则 + 2 生成诊断），
   6 检索 + 3 意图 + 2 既有回答 = 11，11+11=22。以注册表为准实现并在本节留痕，请评审确认。
3. **既有契约测试两处形状断言被 spec 强制升级**（见 §6.4）：若主会话坚持「既有测试文件一字不改」，
   则与 spec §2.3「22 项 + group」不可同时成立，需裁决；当前处置是最小改动并加强断言。
4. **耗时预算**：`chat-quality` 单次 score 现在有既有 `judge_metrics` 的 3 次生成 + 新 `answer_quality_metrics`
   的 3 次生成/3 次 joint 判官/3 次 `hybrid_search`，全部由同一个 300s deadline 兜底；
   真实耗时未在本机压测（评审 R1(b)），以 task-13 真实 API E2E 取证为准。前端 120s 客户端超时需同步。
5. 全仓 `pytest -q tests/`（4305 collected）执行被命令超时中断，**未取得完整结果**；
   定向 `tests/evaluation`（290）+ 相关前端契约（7）已全绿。
6. `answer_quality_metrics` 对 rag / intent 数据集也用内置 042 chat traces 出分（detail 已明示来源），
   与既有 `chat_quality` 在跨 dataset 时 `needs_ground_truth` 的口径并存。若产品要求「非 chat-quality
   数据集的回答质量组也统一降级」，需产品确认后另开范围，本期按 spec §2.4「其余维度照常真实出分」实现。

## 9. 主会话下一步动作

1. 复核 §6.4 与 §8.2 两处口径裁决（注册表 11 项、既有测试两处形状断言）。
2. 转派 `frontend-dev` 执行 task-12（分组渲染 / `?v=N` / 120s→300s 对齐 / `value=null` 不渲染成 0），
   再跑 `tests/frontend/test_evaluation_metric_grouping.py`。
3. 转派 `tester` 执行 task-13：当前部署版本至少 3 次 `POST /api/evaluation/score` 200 + 一次
   `compare` 200，落盘 22 维度数值与按组 delta、真实浏览器截图、追加评审 §14 与架构师签字。
4. 收口前跑全量回归与 `ruff check .`；本次未 commit / push / 合 main。

## 10. 补充验证记录（2026-11-10 收口）

```
$ cd backend && ../.venv/bin/python -m pytest -q ../tests/evaluation
290 passed in 3.32s                                     # EXIT=0（任务卡 §6 的 cwd 变体）

$ cd backend && ../.venv/bin/ruff check app/evaluation
All checks passed!                                      # EXIT=0

$ .venv/bin/python -c "from backend.app.evaluation import contracts, metrics, rubrics, service ..."
IMPORT_OK 22 7                                          # EXIT=0

$ .venv/bin/ruff check .
Found 185 errors.                                       # EXIT=1，全仓存量
$ .venv/bin/ruff check . --output-format concise | grep -c '<本次 10 个改动文件>'
0                                                       # 185 条全部落在其它文件，与本次改动无关
```

说明：技能文档里的 `cd backend && python -c "import app"` 冒烟在本仓不成立（包为
`backend.app`，且 `service.py` 在 HEAD 版本就已有 `from backend.app.api import routes_models` 绝对导入，
见 `git show HEAD:backend/app/evaluation/service.py:15`），属既有工程结构，非本次回归；
正确的导入冒烟为仓库根执行 `from backend.app.evaluation import ...`，已通过。
全仓 `ruff check .` 的 185 条为存量问题，按「最小改动、不扩大范围」未处理。

## 11. P1 修复记录（2026-11-10，跨 dataset 回答质量维度误用 042 轨迹出分）

> 角色：`backend-dev` ｜ 触发：主会话验收裁决（P1，已确认范围内小缺陷，不扩范围）
> 进展日志：`.codebuddy/agent-logs/spec-047/task-11/backend-dev/20261110-071541-p1fix.md`

### 11.1 缺陷

`service.py::_answer_quality_metrics(*, max_items, model, deadline)` 没有 `dataset_id` 参数，且**无条件**
调用 `datasets.load_chat_items()`；`score()` 编排处也未传 dataset。因此用户选 `rag-retrieval` /
`intent-classification` 时，回答质量 / 生成 / 安全的 11 个新维度仍拿**内置 042 chat 轨迹**真实生成 + 联合判官出分。
这违反任务卡 [`task-11-evaluation-metric-expansion.md`](../../task-11-evaluation-metric-expansion.md) §5
「**跨 dataset 不出分的口径沿用既有**：`_rag_metrics` / `_intent_metrics` / `_judge_metrics` 的
`needs_ground_truth` + `reason` 分支**扩展到新增同组 key**」，也违背用户「我选取了…评测集之后，评测系统可以**对此**打分」——
所选评测集必须真实决定评分对象，不能拿另一个集的轨迹冒充。§8.6 记录的「rag / intent 也用 042 traces 出分」即本缺陷，
原「按 §2.4 实现」的判断被主会话裁决推翻，本轮修正。

### 11.2 主会话裁决（明确口径，未自行发挥）

- 追加范围二 §2.4「其余维度照常真实出分」指**同一 dataset 内**其它维度，**不是**允许跨 dataset 用别的集出分。
- 产品使用步骤 §2.6 要求「切到 `intent-classification` 看意图组、切到 `chat-quality` 看回答质量组」；
  追加范围一已验收的口径也是跨 dataset `needs_ground_truth` + reason。
- 对照既有正确实现：`_judge_metrics` / `_rag_metrics` / `_intent_metrics` 在非本组 dataset 时一律早退；
  `_answer_quality_metrics` 必须与三者一致。

### 11.3 改动（最小增量，仅 2 个代码/测试文件）

| 文件 | 改动 |
|---|---|
| `backend/app/evaluation/service.py` | ① 新增模块常量 `_NO_ANSWER_QUALITY_TRACES`（:42，文案：「所选评测集不含 042 判官轨迹，请切换到 chat-quality 评测集查看回答质量维度」）；② `_answer_quality_metrics` 增加 `dataset_id: str` 参数，函数内 11 个新 key 的 `keys` 元组 + `if dataset_id != "chat-quality": return {key: uncomputed_metric(key, NEEDS_GROUND_TRUTH, ...) for key in keys}` 早退（:202-234），**不加载 042、不启动任何生成/判官、不新开线程、不消耗 deadline**；`chat-quality` 分支的 `load_chat_items` + `_call_with_deadline` + `metrics.answer_quality_metrics` 逐字保留；③ `score()` :275-279 传 `dataset_id=dataset_id`。 |
| `tests/evaluation/test_score_grouping.py` | 追加 3 个契约用例：`@pytest.mark.parametrize(RAG, INTENT)` 断言 11 项 `needs_ground_truth` / `value is None` / reason 逐字相等 / `metrics[]` 仍 22 项且每项 `group` 正确 / spy 断言 `load_chat_items`、`answer_quality_metrics`、`judge_metrics` 一次都没调用；chat-quality 用例用 fake `call_ollama` 桩断言 11 项仍 `computed` 且有真实数值、`chat_quality` 仍 computed。另把 3 处**隐含旧口径**的既有用例（`len(timeouts)>=2`、slow_metrics 超时桩、rerank-on 的 `generation_success_rate == computed`）场景从 RAG 迁到 CHAT，**断言逐字未动、强度不降**。 |

**一律未动**：既有 6 项 `metrics[]`、`compare` 的 `deltas[]` / `group`、五端点、五个稳定错误码、
`build_metric` 约束、`contracts.py` / `metrics.py` / `rubrics.py` / `datasets.py` / `store.py` /
`routes_evaluation.py` / `backend/eval_042/**` / `frontend/**` / spec / 台账。
复用既有符号：`uncomputed_metric`、`NEEDS_GROUND_TRUTH`、`_call_with_deadline`、
`datasets.load_chat_items`、`metrics.answer_quality_metrics`，无第二套实现。

### 11.4 验证结果（仓库根 `/Users/wjh/ResearchAgent`，`.venv`）

```
$ .venv/bin/python -m pytest -q tests/evaluation --tb=short
293 passed in 2.66s                                     # PYTEST_EXIT=0（基线 290，+3 新用例，无回退）

$ .venv/bin/ruff check backend/app/evaluation
All checks passed!                                      # RUFF_EXIT=0

# 补充
$ .venv/bin/ruff check tests/evaluation/test_score_grouping.py
All checks passed!                                      # RUFF_TESTS_EXIT=0
$ .venv/bin/python -m pytest -q tests/evaluation/test_score_grouping.py \
      -k "cross_dataset_new_dimensions or chat_quality_dataset_keeps_11" -v
3 passed, 10 deselected in 0.98s                       # EXIT=0
```

TDD 记录：先追加契约用例 → RED `2 failed, 291 passed in 3.06s`（short traceback：
`EVAL_BACKEND_UNAVAILABLE` + `evaluation metric registry incomplete: 11 keys`，恰证明当前实现跨 dataset 仍
无条件调用 `answer_quality_metrics`）→ 最小实现 → GREEN `293 passed in 2.97s`。
3 个迁移场景与其余 290 项在 RED/GREEN 两轮均通过。

**11 项跨 dataset 状态证据**（内联脚本以 `AssertionError` 桩替换 `load_chat_items` 与
`answer_quality_metrics`，未抛错即证明零生成/零判官；`rag-retrieval` 与 `intent-classification` 输出一致）：

```
dataset=rag-retrieval       key_count=11  no_generation_no_judge=True
dataset=intent-classification key_count=11  no_generation_no_judge=True
answer_relevance / conciseness / helpfulness / groundedness / hallucination_free /
answer_exact_match / levenshtein_similarity                status=needs_ground_truth value=None group=answer_quality
generation_success_rate / answer_length_avg                status=needs_ground_truth value=None group=generation
toxicity_free / pii_leakage_free                           status=needs_ground_truth value=None group=safety
detail.reason = 所选评测集不含 042 判官轨迹，请切换到 chat-quality 评测集查看回答质量维度
```

### 11.5 风险 / 留痕

1. 无新增外部依赖、无 DB / 迁移 / SSE / 端点 / 错误码变化；跨 dataset 早退反而省去 3 次生成 +
   3 次联合判官 + 3 次 `hybrid_search`，缩短非 chat-quality 打分耗时。
2. 既有 3 个用例的场景迁移是口径变更的必要调整，**只改 `_body()` 的 dataset 参数与一处注释**，
   未放宽或删除任何断言（regression-guard 第 12 条）。
3. 前端需按 `status == "needs_ground_truth"` 渲染 `value=null` 而非 0.0000（task-12 范围）；本轮**未碰 `frontend/**`**。
4. 未 git commit / push / 合 main；未改 spec / 台账。
