# Task 08 评测台后端：实现交接与自测取证

> 角色：`backend-dev` ｜ 落盘时间：2026-11-10 ｜ 范围：`backend/**`、后端契约测试、`docs/sdd/plans/047/gold/builtin-*.json`、`docs/sdd/plans/047/runs/evaluation/`、本交接目录。
> 依据：`docs/sdd/plans/047/task-08-evaluation-backend.md`、`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 第 342–520 行（D7–D12）。
> 不改：原六块业务代码 / 测试 / 配置 / `.env`、`frontend/**`（交 `frontend-dev`）、`docs/sdd/specs/*`、`spec-status-changelog.md`、ADR0002；未 git commit / push / 合 main。

## 1. 改动文件清单（新增为主，仅 1 个既有文件追加 2 行）

| 文件 | 行数 | 作用 |
|---|---:|---|
| `backend/app/evaluation/__init__.py` | 1 | 新包 |
| `backend/app/evaluation/contracts.py` | 142 | 稳定错误码 / 错误体、策略预设注册表、指标构造器（`status≠computed` 强制 `value=null` + `reason`） |
| `backend/app/evaluation/datasets.py` | 93 | 内置标注集只读加载、白名单 + 防穿越校验、042 集只读引用 |
| `backend/app/evaluation/metrics.py` | 268 | 真实计算：recall/precision/mrr/intent_accuracy 纯数学函数 + 既有 hybrid_search / detect_skill / eval_042 判官编排 |
| `backend/app/evaluation/store.py` | 71 | run 产物本地 JSON、白名单 + 防穿越、原子替换 |
| `backend/app/evaluation/service.py` | 284 | 三选一编排、超时截止、run 历史、按维度 delta |
| `backend/app/api/routes_evaluation.py` | 62 | 五个端点；所有依赖调用包 `try/except`，稳定错误体、不裸 500、不放 `str(exc)` |
| `backend/app/api/routes.py` | 37（**+2**） | 按既有风格 `include_router(routes_evaluation.router)` |
| `tests/evaluation/test_evaluation_metrics_math.py` | 81 | 可控 fixture 复算 recall/precision/mrr/accuracy/均分 |
| `tests/evaluation/test_evaluation_api_contract.py` | 429 | 五端点契约、五错误码、穿越、不可比无 delta、degraded、真实计算、重复 run_id、产物一致、delta、max_items |
| `docs/sdd/plans/047/gold/builtin-rag-retrieval.json` | 111 | 8 条当前 KB 真实 chunk 身份 + `kb_alignment` |
| `docs/sdd/plans/047/gold/builtin-intent-classification.json` | 37 | 16 条对齐 `registry.py` 的 Tool 名 |
| `docs/sdd/plans/047/gold/builtin-chat-quality.json` | 20 | 只读引用 042 的 24 条 trace |
| `docs/sdd/plans/047/runs/evaluation/*.json` | 6 个产物 | 每次 `POST /api/evaluation/score` 的 run 产物（字段与 200 响应完全一致） |
| `docs/sdd/plans/047/runs/task-08/http-selftest-part{1,2,3}.json` | 3 个 | 真实 HTTP 请求/响应取证 |

**无 DB 表、无迁移、无外键、无并发领用**；回滚 = 删除新增文件 + 移除 `routes.py` 两行注册。

## 2. 端点契约（前端 task-09 直接按此对接）

- `GET /api/evaluation/options` → `200 {strategies:[{id,label,chunker,top_k,reranker}], models:[string], datasets:[{id,label,item_count,source,synthetic,label_source}]}`；`models` 复用 `backend.app.api.routes_models._build_local_models/_build_online_models`（与 `/api/models` 同一数据源），不自建第二套清单。
- `POST /api/evaluation/score` → body `{strategy_id, model, dataset_id, max_items?}` → `200 {run_id, metrics[], strategy, model, dataset, created_at, judge_model}`。`created_at` 为 UTC（`…Z`）；`judge_model` 恒为 `qwen3.5:9b`（判官），`model` 为被测模型，二者不混淆。
- `metrics[]` 固定 6 项、顺序：`recall@k` / `precision@k` / `mrr@k` / `intent_accuracy` / `chat_quality` / `memory_correctness`；每项 `{key,label,value,status,sample_count,detail}`，`status∈computed|degraded|needs_ground_truth|unavailable`，**仅 computed 有真实数值**，其余 `value=null` 且 `detail.reason` 必填。
- `GET /api/evaluation/runs` → `200 {runs:[{run_id,strategy,model,dataset,judge_model,created_at}]}`（按 mtime 倒序）。
- `GET /api/evaluation/runs/{run_id}` → `200` 完整 run（与 POST 200 逐字一致）；不存在 → `404 EVAL_OPTION_NOT_FOUND`。
- `GET /api/evaluation/compare?a=&b=` → 同 dataset + 同判官 → `200 {a,b,dataset,judge_model,deltas:[{key,label,value_a,value_b,delta,status_a,status_b}]}`；跨 dataset / 跨判官 / `a==b` → `409 EVAL_NOT_COMPARABLE`，**响应不含 delta / deltas**。

**稳定错误体**（所有错误均此形状，不裸 500、不含原始异常文本）：

```json
{
  "error_code": "EVAL_OPTION_NOT_FOUND",
  "message": "评测选项不存在",
  "retryable": false,
  "request_id": "<X-Request-ID 或 uuid4 hex>",
  "error": {"code": "EVAL_OPTION_NOT_FOUND", "message": "评测选项不存在"}
}
```

| code | HTTP | 触发 |
|---|---:|---|
| `EVAL_OPTION_NOT_FOUND` | 404 | 三选一为空 / 未知策略或模型 / run 不存在 / compare 缺 a、b |
| `EVAL_DATASET_INVALID` | 400 | 未知 dataset_id、含 `../` 或绝对路径、gold 文件损坏、run_id 穿越 |
| `EVAL_BACKEND_UNAVAILABLE` | 503 | 模型清单 / 检索 / 判官 / 产物读写等外部依赖异常（带 `Retry-After: 10`） |
| `EVAL_SCORE_TIMEOUT` | 504 | 判官实时生成超过服务端截止（带 `Retry-After: 10`） |
| `EVAL_NOT_COMPARABLE` | 409 | 跨 dataset / 跨判官 / `a==b` |

## 3. 复用的既有符号（禁止第二套实现）

- `backend.app.knowledge_base.infrastructure.retrieve.hybrid_search`、`Hit`、`reranker_health`（RAG 真实检索 + reranker 真实就绪探测）
- `backend.app.skills.intent.detect_skill`、`SkillDecision`、`backend.app.skills.registry.build_default_tool_registry`、`backend.app.skills.models.SkillSummary`
- `backend.app.api.routes_models._build_local_models` / `_build_online_models` / `_resolve_current` 同源数据（经模块引用调用）
- `backend.eval_042.config.PRIMARY_JUDGE` / `ENUM_MAPS`，`backend.eval_042.judge_client.judge_majority` / `enum_to_score`，`backend.eval_042.runner.KNOWN_TASKS`（`_judge_score` 用它校验 task 白名单，真实复用 runner.py 的唯一 task 注册表）
- `docs/sdd/plans/042/task-02-eval-dataset.json` 的 24 条冻结 trace（只读）
- 错误体形状沿用 `routes_kb._document_error`（`error_code/message/retryable/request_id`），并补 `error.code` 便于前端按码映射。

**策略参数真实作用**：`chunker` / `top_k` 逐次真实传入 `hybrid_search`；`reranker` 不是 per-call 形参（既有 `hybrid_search` 由 `RERANKER_ENABLED` 控制），实现用 `reranker_health()` 真实探测；当前 `available=false (reason=connection)` → `rerank-on` 的 RAG 三维一律 `degraded` + reason，**不伪造收益**。`chunker-v2` 因标注集只有 v1 身份 → `needs_ground_truth` + reason，不编造跨版本数值。

## 4. 三份内置标注集与反伪造口径

- 统一 `source:"builtin-fixture"`、`synthetic:true`、`schema_version:"builtin-evaluation-dataset-v1"`、`label_source`，**不冒充人工标注、不冒充真实业务数据、无 `human_label`**。
- `rag-retrieval`：`label_source="kb-derived:retrieval-rank"`，8 条 `relevant_doc_ids` 的 `(paper_id,chunker=v1,chunk_index,page)` 全部来自当前 KB 真实 chunk（只读 `POST /api/kb/ask` 的 citations 事件，内部即 `hybrid_search(top_k=10,chunker='v1')`）；每题取固定 `derivation_rank` 作为唯一相关片段并写明派生规则。该标签是**检索派生**，不是人工相关性判断，仅用于机制回归与可复算指标。
- `intent-classification`：`label_source="registry-derived"`，16 条 `expected_intent` 对齐 `backend/app/skills/registry.py::build_default_tool_registry()` 的 7 个当前 Tool 名（正例 8 / `none` 负例 8），**不复用 023 的过时 USENIX 技能名**；消息构造成 `detect_skill` 的确定性规则第一跳，避免评测时触发 LLM。
- `chat-quality`：`label_source="frozen-trace-reference"`，只读引用 `docs/sdd/plans/042/task-02-eval-dataset.json` 的 24 条（20 条 `status=scored && synthetic=false` 可评分）；无 `relevant_doc_ids` / `expected_intent` / `human_label`。

### `kb_alignment` 实际结论（只读核实，非假设）

- `GET /api/kb/health`：`qdrant=true, embedding=true, reranker.available=false(reason=connection), papers=64, chunks=19905`。
- `docs/sdd/reviews/014-reranker-benchmark.md` 的 5 个冻结 `paper_id` 中，只有 `d4dfd2a620384ad5bece27320661f8f0` 仍存在于当前 KB；其余 4 个 `GET /api/kb/documents/{id}/inspection` 均为 `404 DOCUMENT_NOT_FOUND`。
- **014 十题不适用**（`applicable_questions=0`）：4/5 paper_id 不存在，且 10 题目标片段 SHA256 绑定 2026-09-02 历史 Qdrant 快照，未做逐 chunk 哈希复核，不复用其人工冻结标签。
- 最终从当前 KB 真实文档派生 8 条，实际对齐 `aligned_items=8`、`aligned_paper_ids`：
  `d4dfd2a620384ad5bece27320661f8f0`、`f3227d067b734e6cbc8fb3a9ce886191`、`7dfec772f919481aad9fc3bcbcf96041`、`88ef66bf9c7547148d843d6a1e8270bd`、`4aee4ac6675241ebabb70b60ddb6bb8c`、`388ff16ff0594a08ad30a35e9d4b59ea`、`1a3c542b31734c45a541896a01d71528`、`277758154feb492081ef84d33c5fcab3`。**没有任何捏造的 paper_id**。

## 5. 真实 HTTP 自测（重启主服务后，端口 8000，被测模型 `qwen3.5:9b`）

> 主服务原进程未带 `--reload`，为加载新路由以同一命令重启（`docs/sdd/plans/047/runs/task-08/uvicorn-restart.log`），重启后 `/api/health` 200。Langfuse `:3000` 未启动，按 spec 不作为失败依据。

| 端点 / 场景 | HTTP | 关键返回 |
|---|---:|---|
| `GET /api/evaluation/options` | 200 | `strategies=[baseline,chunker-v2,topk-10,rerank-on]`、`models` 12 项（复用 `/api/models`）、`datasets` 3 项 |
| `POST /api/evaluation/score` rag / `baseline` / max_items=8 | 200 | `run_id=eval-37e5d6d4636544f7962a1d1597f4e764`；**`recall@k=0.5`、`precision@k=0.1`、`mrr@k≈0.2604166667`**（8 样本，真实 hybrid_search join）；其余 3 维 `needs_ground_truth` + reason |
| `POST /api/evaluation/score` rag / `topk-10` / max_items=8 | 200 | `run_id=eval-fc99c427d5d840e485ea51131d4dbdeb`；**`recall@k=1.0`、`precision@k≈0.1`、`mrr@k≈0.3286210317`**（真实策略切换产生 delta） |
| `POST /api/evaluation/score` intent / `baseline` / max_items=16 | 200 | `run_id=eval-f89b5aa12e6549f58fe5309d17285f64`；**`intent_accuracy=1.0`**（16 样本，真实 `detect_skill` 与 `expected_intent` 逐条比对） |
| `POST /api/evaluation/score` chat / `baseline` / max_items=1 | 200 | `run_id=eval-71356d31f1ed4ba3b9eebd5003461277`；**`chat_quality=1.0`**（真实 `qwen3.5:9b` 判官 27.47s，分数由 `ENUM_MAPS` 映射）；`memory_correctness=needs_ground_truth` + reason |
| `POST /api/evaluation/score` rag / `rerank-on` | 200 | RAG 三维 `degraded`、`value=null`、reason 含 `available=false (reason=connection)`，**不伪造收益** |
| `POST /api/evaluation/score` rag / `chunker-v2` | 200 | RAG 三维 `needs_ground_truth`、`value=null` + reason（v2 无对应真值） |
| `GET /api/evaluation/runs` | 200 | 6 条运行历史 |
| `GET /api/evaluation/runs/{run_id}` | 200 | 与 POST 200 **逐字一致**；`created_at=2026-11-09T18:22:22.715183Z`（UTC）、`judge_model=qwen3.5:9b` |
| `GET /api/evaluation/compare?a=<baseline>&b=<topk-10>` | 200 | `recall@k delta=+0.5`、`mrr@k delta≈+0.0682`、`precision@k delta≈0`（浮点误差）；非 computed 维度 `delta=null` |
| `GET /api/evaluation/compare?a=<rag>&b=<intent>` | 409 | `EVAL_NOT_COMPARABLE`，响应**不含 delta/deltas** |
| 未知 strategy / model / 空三选一 | 404 | `EVAL_OPTION_NOT_FOUND` 稳定错误体 |
| 未知 dataset / `../gold/...` 穿越 | 400 | `EVAL_DATASET_INVALID` 稳定错误体 |
| 不存在的 run | 404 | `EVAL_OPTION_NOT_FOUND` |
| `GET /api/evaluation/runs/..` | 400 | `EVAL_DATASET_INVALID`；`%2F` 穿越路径不匹配路由返回 404，无白名单外文件读取 |

`EVAL_BACKEND_UNAVAILABLE`（503）与 `EVAL_SCORE_TIMEOUT`（504）在契约测试中以 monkeypatch 依赖抛异常 / 判官超时验证；真实服务未人为制造依赖故障。所有错误响应中不含 `str(exc)`。

## 6. 反伪造红线与诚实降级

- 产品代码**无 mock 分数、无硬编码分数**：所有 `value` 来自 `aggregate_retrieval` / `intent_accuracy` / `judge_average` 的真实计算；测试里的 fake 仅用于隔离外部依赖。
- `memory_correctness`：042 集 24 条全为 `chat_quality` 且无 `prior_context` → 只能 `needs_ground_truth` + reason，**不占位出分**。
- `chat_quality` 的判官对象是内置集内冻结的 `output`，不是所选被测模型实时生成；`detail.answer_source` / `answer_source_note` 已明确标注，`model` 仅作运行元数据，`judge_model` 固定 `qwen3.5:9b`。
- RAG / 意图指标不调用生成模型，`model` 同样只作运行元数据；判官与被测分离。
- `reranker available=false` 时 `rerank-on` 相关维度如实 `degraded`，`chunker-v2` 缺少 v2 真值如实 `needs_ground_truth`；功能不隐藏，但绝不编造数值。
- `max_items`：默认 3、上限 20；≤0 / 非整数收敛到默认，超上限收敛到上限；判官实时生成受整体截止（300s）约束，超时返回 `EVAL_SCORE_TIMEOUT`。

## 7. 验证命令与真实输出

- RED 门禁：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/evaluation/test_evaluation_metrics_math.py tests/evaluation/test_evaluation_api_contract.py` → `2 errors in 0.60s`（`ModuleNotFoundError: No module named 'backend.app.evaluation'`），退出码 2。
- GREEN：同命令 → `29 passed in 1.80s`，退出码 0。
- 新增文件 lint：`.venv/bin/python -m ruff check backend/app/evaluation/ backend/app/api/routes_evaluation.py backend/app/api/routes.py tests/evaluation/test_evaluation_*.py` → `All checks passed!`，退出码 0。
- 全仓 backend lint：`cd backend && ../.venv/bin/python -m ruff check .` → 57 条**存量**告警（集中在既有 `backend/eval_042/runner.py` 等文件），grep `evaluation|routes_evaluation` 无命中；本次新增文件 0 命中（单独执行 `ruff check app/evaluation app/api/routes_evaluation.py app/api/routes.py` → `All checks passed!`）。
- 导入冒烟：`cd backend && ../.venv/bin/python -c "import app; print('IMPORT_OK')"` → `IMPORT_OK`。
- `cd backend && ../.venv/bin/python -m pytest -q` → `no tests ran in 0.02s` / 退出码 5：本仓 `tests/` 在仓库根，`backend/` 下没有 pytest 配置；全量回归须在仓库根执行 `.venv/bin/python -m pytest -q`（见下节与 `pytest-full.log` / `pytest-full-no-spa.log`）。

## 8. 风险 / 阻塞 / 交接

- **全量 pytest 的环境性挂起（非本改动引入）**：仓库根 `.venv/bin/python -m pytest -q` 收集 4230 条；跑到 98% 时卡在 `tests/system/test_spa_fallback.py`（该测试用 `with TestClient(app)` 触发 lifespan 启动，在主服务占用本地 Qdrant 时挂起）。单独执行该文件也超过 90s 未完成；该文件未改动、本任务也未改 `main.py` / lifespan。以 `--ignore=tests/system/test_spa_fallback.py` 重跑结果见 `pytest-full-no-spa.log` 与下方追加记录。
- 全量运行中 11% 处出现的唯一 `F` 为 `tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（浏览器手势耗时阈值 `maxGestureWallMs < 1000`），属机器负载敏感的前端性能用例；早先 `pytest -q tests/frontend/` 全量 `479 passed in 158.90s`（含该用例）通过，详见第 9 节。与后端改动无关。
- 判官单次调用实测 27–38s，`chat-quality` 默认 `max_items=3` 时约 1–2 分钟；前端应展示「评分中」并按 `EVAL_SCORE_TIMEOUT` 提示。
- 给 `frontend-dev`（task-09）的契约：按第 2 节渲染 9 视图；三个下拉取自 `options`；每维度独立卡片显示 `value/status/sample_count/detail.reason`；比较只用同 dataset 的两次 run；错误按 `error_code`（或 `error.code`）映射文案；后端文本一律 `textContent` / `createElement`，禁 `innerHTML`。
- 日志：`.codebuddy/agent-logs/spec-047/task-08/backend-dev/20261110-013552.md`。

## 9. 全量回归最终结果（补记，2026-11-10）

- 命令（仓库根）：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q --ignore=tests/system/test_spa_fallback.py --tb=short`
- 真实输出：`1 failed, 4224 passed, 2 skipped, 5 warnings, 67 subtests passed in 661.81s (0:11:01)`，退出码 1。
- 唯一失败：`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` —— 浏览器性能阈值断言 `maxGestureWallMs < 1000`，实测 1030.1ms（单独复跑 1015.5ms）。这是**前端静态/浏览器性能用例的机器负载敏感阈值**，与本任务后端改动无关：早先 `pytest -q tests/frontend/` 全量 `479 passed in 158.90s`（含该用例）通过；本轮并发跑全量 + 重启主服务 + 其他 agent 活动使 headless 浏览器手势耗时越界。
- `tests/system/test_spa_fallback.py` 的 3 个用例因 `with TestClient(app)` 触发 lifespan 且主服务占用本地 Qdrant 而挂起（单独执行 >90s 未完成），以 `--ignore` 排除；该文件与 `main.py` / lifespan 均未改动。
- 日志尾部 `Failed to export span batch ... 127.0.0.1:3000 Connection refused` 为 Langfuse `:3000` 未启动，按 spec「不得据此判定失败」。
- 本次新增 29 条契约测试全部包含在上述 `4224 passed` 中；`EVAL_BACKEND_UNAVAILABLE` / `EVAL_SCORE_TIMEOUT` 两个错误码由契约测试以依赖故障 / 判官超时稳定验证。
- 未改动文件核对：`git status --porcelain` 中的 `frontend/**`、`docs/sdd/specs/*`、`spec-status-changelog.md`、评审文档等均为其他角色/主会话的既有改动，本 agent 未触碰。
- 收口前补充复用 `backend/eval_042/runner.py::KNOWN_TASKS` 后重跑：新增文件 `ruff check` → `All checks passed!`；两个新测试文件 → `29 passed in 1.80s`；`python -c "import backend.app.main"` → `IMPORT_OK ['chat_quality','memory_correctness']`；重启主服务后 `GET /api/evaluation/options` → 200（4/12/3），`POST /score(chat-quality,max_items=1)` → 200 且 `chat_quality=computed,1.0`。主服务保持运行。

## 10. P1 缺陷修复记录（本次增量修复）：`model` 假开关 → 被测模型真实参与 `chat_quality`

> 本节为**追加记录**，不改写第 1–9 节原文。特别说明：第 6 节「`chat_quality` 的判官对象是内置集内冻结的 `output`，不是所选被测模型实时生成」与第 5 节表格里对应的旧行为描述，**已被本次修复取代**；修复后评分对象由所选被测模型实时生成。Langfuse `:3000` 未启动，日志里的 OTEL export refused 按 spec 不作为失败依据。

### 10.1 缺陷与修复范围

- 缺陷：`metrics.judge_metrics` 只把 `under_test_model` 写进 detail（`answer_source=frozen_fixture_output`），判官打的是冻结 `item["output"]`；`service.py:177` 虽把 `model` 传入但未用于任何生成/分类调用 → 换任何模型所有维度分数不变，与 D8（`model`=被测模型、判官固定 `qwen3.5:9b`）不符。
- 修复（最小增量）：
  - `metrics.py` 复用既有 `backend.eval_042.judge_client.call_ollama`（其内部即 `offline_guard.http_post_json` + Ollama `/api/chat`，`think:false` / `temperature:0` / `num_predict:160` / `stream:false`），新增 `_generate_live_answer(model, question, timeout)` 薄封装；**未新建第二套客户端/框架**。`GENERATION_TIMEOUT_SECONDS=60.0` 作为单条生成硬超时，整批仍由 `service._call_with_deadline(SCORE_TIMEOUT_SECONDS=300)` 兜底；`DEFAULT_MAX_ITEMS=3` / `MAX_ITEMS=20` 未改。
  - `judge_metrics` 对前 `max_items` 条的 `input` 用所选模型实时生成回答，再交 `_judge_score` / `judge_majority`（**逐字未改**）由固定判官打分。detail 改为 `answer_source=live_generation`、`generation_model_used=true`、`under_test_model`、`judge_model=qwen3.5:9b`、`generated_count` / `generation_failures`，`answer_source_note` 改成如实表述「评分对象由所选被测模型实时生成」；删除与事实相反的旧 note。
  - 生成失败 / 线上模型本地不可生成 / 超时 / 空回答 / 部分失败 → `chat_quality` `status=degraded`、`value=null`、reason 写明真实失败类型（仅异常类型名，不含 `str(exc)`，符合 regression 第 14 条），**不回退冻结 output、不静默记 0、不拿部分成功假装出分**（失败时判官完全不被调用）。
  - `intent_accuracy` / RAG 三维 detail 增 `model_participates=false` + `model_participates_reason`（意图走 `detect_skill` 规则优先 + 模块固定 LLM 兜底；检索走固定 embedding 的 `hybrid_search`）；**业务识别链路未改**。
  - `service.py` **0 行改动**（`model` 早已传入 `judge_metrics`，仅此前未被使用）。端点契约/错误码/策略注册表/标注集/前端/spec/台账/ADR/原六块均未改。

### 10.2 TDD 与验证命令（真实输出 / 退出码）

| 命令 | 真实输出 | 退出码 |
|---|---|---:|
| RED：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/evaluation/test_evaluation_live_generation.py tests/evaluation/test_evaluation_api_contract.py tests/evaluation/test_evaluation_metrics_math.py` | `4 failed, 29 passed in 2.08s`（新测试分别挂在生成调用次数=0 / `answer_source=frozen_fixture_output` / `KeyError: model_participates`；29 个原有用例全绿） | 1 |
| GREEN：同命令 | `33 passed in 1.87s` | 0 |
| 收口复跑（重启服务后）：同命令 | `33 passed in 1.40s` | 0 |
| lint：`/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/evaluation/metrics.py tests/evaluation/test_evaluation_live_generation.py tests/evaluation/test_evaluation_api_contract.py` | `All checks passed!` | 0 |
| 导入冒烟：`/Users/wjh/ResearchAgent/.venv/bin/python -c "import backend.app.evaluation.metrics as m; print('IMPORT_OK GENERATION_TIMEOUT_SECONDS=', m.GENERATION_TIMEOUT_SECONDS)"` | `IMPORT_OK GENERATION_TIMEOUT_SECONDS= 60.0` | 0 |

新增契约文件 `tests/evaluation/test_evaluation_live_generation.py`（按能力命名、无编号）4 个用例：被测模型名进入生成调用且次数=样本数、判官收到实时生成文本而非冻结 output、生成失败/部分失败 degraded 且不回退冻结 output、intent/RAG `model_participates=false`。既有 29 个用例零回归（`test_evaluation_api_contract.py` 的 `sandbox` fixture 仅补一行 `call_ollama` fake 隔离新增外部依赖，用例断言未改）。注：RED / GREEN 两次在仓库根以 `cd /Users/wjh/ResearchAgent && .venv/bin/python -m pytest -q ...` 执行（与表中绝对路径为同一解释器），收口复跑与 lint / 导入冒烟使用表中列出的绝对路径命令。

### 10.3 真实 HTTP 自测（重启主服务后，端口 8000）

> 服务原进程无 `--reload`，kill 旧 PID 9071 后以 `start_new_session=True` 脱离会话重启（首次 `nohup ... &` 被工具 shell 退出信号打断，见日志 step-6），新 PID 15069，`/api/health` 200。`GET /api/evaluation/options` 200，`models` 含 `qwen3.5:9b` / `qwen3.8:27b` / `qwen3.8:27b-q4`。

| 所选被测模型 | `chat_quality.value` | `status` | `detail.answer_source` | `detail.under_test_model` | `generated_count` / `generation_failures` | run_id |
|---|---:|---|---|---|---|---|
| `qwen3.5:9b` | **0.5** | computed | `live_generation` | `qwen3.5:9b` | 1 / 0 | `eval-7bb5da044d40420c993ca0e5f2e012a5` |
| `qwen3.8:27b` | **null** | degraded | `live_generation` | `qwen3.8:27b` | 0 / 1 | `eval-5064c132930a4fca82ae61cf5c35fd66`、`eval-f6e799ae03494733b2f84e18807721d8`（重试） |
| `qwen3.8:27b-q4` | **1.0** | computed | `live_generation` | `qwen3.8:27b-q4` | 1 / 0 | `eval-3a5b5eee42f14bfb9ee2474713229a52` |

- **选模型不再是假开关**：两个不同本地模型对同一 `chat-quality` 集（`max_items=1`）得到不同分数 `0.5` vs `1.0`，两次 `answer_source=live_generation`、`generated_count=1`；detail 中的 `under_test_model` 与判官 `judge_model=qwen3.5:9b` 分离。契约测试另以 fake 断言生成调用收到的 model 名与调用次数。
- `qwen3.8:27b` 本机生成超过单条 60s 硬超时（两次均 `TimeoutError`，排除冷启动），如实 `degraded` + `value=null` + `reason=被测模型实时生成失败 1/1 条（错误类型：TimeoutError）；按失败不伪造原则不出分，不回退评测集冻结 output`，**未伪造回答、未退回冻结 output**；按任务「若后者不可用换 `/api/evaluation/options` 里另一个本地模型」的指示，改用 `qwen3.8:27b-q4` 完成第二个模型的出分对比。
- **rag / intent 未被破坏**：`rag-retrieval` `baseline` `max_items=3` → `recall@k≈0.3333`、`precision@k≈0.0667`、`mrr@k≈0.3333`，三维均 `computed` 且 `model_participates=false`（run `eval-7f2d1cc764ae42feb994e313b706a81c`）；`intent-classification` `baseline` `max_items=3` → `intent_accuracy=1.0` `computed`、`model_participates=false` + reason（run `eval-3f4604a791974712b7c034b51b4db385`）。

### 10.4 仍无法让被测模型参与的维度（如实说明）

- `recall@k` / `precision@k` / `mrr@k`：检索指标由 `hybrid_search`（固定 embedding + Qdrant）与标注集身份 join 得出，与生成模型无关 → `model_participates=false`。
- `intent_accuracy`：走 `backend.app.skills.intent.detect_skill` 的真实行为（规则优先 + 模块固定 `config.MODEL_NAME` 的 LLM 兜底），按任务要求**不为凑「模型生效」改动业务意图识别链路** → `model_participates=false`。
- `memory_correctness`：内置 042 集 24 条全为 `chat_quality` 且无 `prior_context` / 记忆真值 → 仍 `needs_ground_truth`，不出分。
- `chat_quality` 是唯一由所选被测模型真实生成回答的维度；选到线上模型（`source=online`，本地 Ollama 无该模型）或本机生成超时的模型时会如实降级，不会伪造分数。

### 10.5 改动文件与行数 / 边界

- `backend/app/evaluation/metrics.py`：`wc -l` 271 → 327 行（净 +56；import 1 行、常量 4 行、RAG/intent detail 各 2 行、`_generate_live_answer` + `judge_metrics` 重写段 21 删 / 69 增；文件末行无换行符，Read 行号为 272 → 328）。
- `backend/app/evaluation/service.py`：**0 行改动**。
- `tests/evaluation/test_evaluation_live_generation.py`：新建 145 行（4 用例）。
- `tests/evaluation/test_evaluation_api_contract.py`：+7 行（sandbox fixture 补 fake）。
- `docs/sdd/plans/047/runs/task-08/implementation.md`：本第 10 节追加（不改写第 1–9 节）。
- 未 commit；未触碰 `frontend/**`、spec、台账、ADR、端点契约、错误码、策略注册表、标注集。
- 日志：`.codebuddy/agent-logs/spec-047/task-08/backend-dev/20261110-013552.md`。
