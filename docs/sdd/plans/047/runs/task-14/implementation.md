# spec-047 / task-14 后端交接：≥100 条真实样本 + 批量化 + Go/No-Go 基准

> 角色：`backend-dev` ｜ 状态：**代码与定向测试完成；100 条 Go/No-Go 基准交主会话执行**
> 唯一裁决口径：spec §13.1 四项 P1（P1-1 硬判据 900s / P1-2 常量单一真源 / P1-3 `num_predict` 唯一例外 / P1-4 chat 唯一数据源）。

## 1. 改动清单（均在允许边界内）

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/generate_evaluation_samples.py` | 新建（525 行） | 只读 KB、只写三份 gold、确定性幂等；`build_documents` 为纯函数 |
| `docs/sdd/plans/047/gold/builtin-rag-retrieval.json` | 改 | 8 → **128** 条（保留冻结 8 条 + `kb_alignment` 结论） |
| `docs/sdd/plans/047/gold/builtin-intent-classification.json` | 改 | 16 → **120** 条（7 个真实 Tool 名 × 14 模板 + 负例） |
| `docs/sdd/plans/047/gold/builtin-chat-quality.json` | 改 | `items: []` → **120** 条（20 冻结 trace + 100 KB 派生，1:5 交错） |
| `backend/app/evaluation/contracts.py` | 改 | `3→100` / `20→200` / `300.0→900.0` |
| `backend/app/evaluation/datasets.py` | 改 | P1-4 唯一数据源、`item_count=len(items)` 同源 |
| `backend/app/evaluation/service.py` | 改 | 删除重复 `SCORE_TIMEOUT_SECONDS`，改从 contracts import；`judge_metrics` 传共用 deadline |
| `backend/eval_042/judge_client.py` | 改 | **仅**加可选 `num_predict`（默认 160 逐字不变） |
| `backend/app/evaluation/rubrics.py` | 改 | 新增三类批量 JSON 协议（生成 / 7-rubric / chat_quality 枚举） |
| `backend/app/evaluation/metrics.py` | 改 | 批量生成 + 批量判官 + 失败批隔离 + 诚实 detail；`BATCH_SIZE=20`、`BATCH_NUM_PREDICT=2048`、`MAX_QUESTION_CHARS=600` |
| `tests/evaluation/test_gold_dataset_contracts.py` | 新建 | 三份集 ≥100、schema、两层 synthetic、KB 身份、幂等 |
| `tests/evaluation/test_score_budget_contracts.py` | 新建 | 常量单一真源、clamp 边界、chat 唯一数据源、白名单 |
| `tests/evaluation/test_judge_client_num_predict.py` | 新建 | P1-3 默认 160 回归、`judge_one`/`judge_majority`/`KNOWN_TASKS` 不回归 |
| `tests/evaluation/test_batch_judge_protocols.py` | 新建 | 批量解析：正常/围栏/缺字段/非法枚举/非 JSON 一律诚实失败 |
| `tests/evaluation/test_batch_metrics_honesty.py` | 新建 | 100 条 5 批、sample_count、失败批隔离、共用 deadline、跨 dataset 早退 |
| `tests/evaluation/batch_transport_doubles.py` | 新建 | 共享批量协议离线替身（按能力命名，无编号） |
| `tests/evaluation/{test_metric_registry,test_score_grouping,test_evaluation_api_contract,test_evaluation_live_generation,test_expanded_metrics,test_rubric_judge}.py` | 改 | 跟随新契约最小修复（常量断言、sandbox chat items 同源、桩适配批量协议） |
| `docs/sdd/plans/047/runs/task-14/benchmark_100.py` | 新建 | 真实 HTTP 100 条 Go/No-Go 基准脚本 |
| `docs/sdd/plans/047/runs/task-14/smoke_2.{request.json,json,status}` | 新建 | 小样本真实 API 冒烟产物 |

**未触碰**：`frontend/**`、`backend/app/api/routes_evaluation.py`、`store.py`、`eval_042/config.py` 的 `ENUM_MAPS`/`PROMPTS`、`eval_042/runner.py` 的 `KNOWN_TASKS`、`docs/sdd/specs/**`、`reviews/**`、状态台账、`.env`。工作区中这些文件的 diff 来自并行分派的其他角色，非本次改动。

## 2. 四项 P1 逐条落地证据

### P1-1 Go/No-Go 硬判据（900s，不是 300s）
- `benchmark_100.py`：`HARD_LIMIT_SECONDS=900.0`，`OPTIMIZATION_TARGET_SECONDS=300.0` 仅作记录；判定只检查「总耗时 ≤900s」「所有 `status=computed` 维度 `sample_count≥100` 且 `value` 非 null」「HTTP 200 / 22 key / run_id」。
- 离线判定回归：`GO baseline`→GO、`over 900s`→NO_GO、`300s is NOT a failure line (500s)`→**GO**、`http 504`→NO_GO、`computed sample_count<100`→NO_GO，5/5 通过。
- `memory_correctness` 按 P1-4 保持 `needs_ground_truth`（非 computed，不在判据内），脚本如实打印非 computed 维度名单，不隐藏卡片、不把 null 当 0。
- 未降采样、未靠 degraded 收场、未改写判据。

### P1-2 超时与 max_items 单一真源
- `contracts.py:17-19` → `DEFAULT_MAX_ITEMS=100` / `MAX_ITEMS=200` / `SCORE_TIMEOUT_SECONDS=900.0`。
- `service.py` 删除 `SCORE_TIMEOUT_SECONDS = 300.0`，在顶部 `from .contracts import (... SCORE_TIMEOUT_SECONDS ...)`；`score()` 仍用该名字，单一真源。
- 契约测试 `test_service_shares_the_single_timeout_source_with_contracts`：`service.SCORE_TIMEOUT_SECONDS is contracts.SCORE_TIMEOUT_SECONDS == 900.0` 且源码中不再有两处重定义；clamp 边界 0/负/bool/字符串/99999 全量覆盖。

### P1-3 `call_ollama` 唯一例外
- `judge_client.py:154` 签名加 `num_predict: int | None = None`；body 为 `160 if num_predict is None else num_predict`，**不传参时仍为 160**。
- `ENUM_MAPS` / `PROMPTS` / `KNOWN_TASKS` / `judge_one` / `judge_majority` 行为未改；`test_judge_client_num_predict.py` 与既有 `test_task03_reproducibility.py:253`（仍断言 160）双覆盖。
- 仅批量生成 / 批量判官显式传 `BATCH_NUM_PREDICT=2048`（任务卡 §4.3 建议 ≥2048）。

### P1-4 chat 集唯一数据源与两层 synthetic
- `builtin-chat-quality.json` 的 `items` 实打实 120 条：20 条 042 冻结 trace（`status=scored && synthetic=false`，`synthetic:false` + `reference_source:"frozen-042-trace"`）+ 100 条 KB 派生（`synthetic:true` + `reference_source:"kb-chunk"` + `kb_source` 真实身份）；文档级 `synthetic:true` 保持（内置 fixture，不冒充人工标注）。
- `datasets.load_chat_items()` 改从 `builtin-chat-quality.json` 加载，只校验 `status=="scored"` 与 `input`/`output` 非空字符串，**不再读 042 文件、不再按条目级 synthetic 过滤**；`CHAT_DATASET_PATH` 仅留作溯源/历史 fixture 兼容，加载逻辑不再引用。
- `list_datasets()` 删除取文档 `item_count` 的写死分支，统一 `item_count = len(document["items"])`；`load_dataset` 白名单/路径穿越校验逐字不变。
- `memory_correctness` 的 reason 改为实际条数（不再写「24 条」）；跨 dataset 早退（`service._answer_quality_metrics` / `_judge_metrics`）逐字保留、零外部调用，有定向用例。
- 证据：重启后 `GET /api/evaluation/options` 返回 `(rag-retrieval,128) (intent-classification,120) (chat-quality,120)`。

## 3. 批量化与反伪造

- **唯一传输层**仍是 `backend/eval_042/judge_client.py::call_ollama`，未新建 HTTP 客户端 / 第二套判官框架。
- `rubrics.py` 新增 `build/parse_batch_generation_response`、`build/parse_batch_rubric_response`、`build/parse_batch_chat_quality_response`：索引字符串 → 值的严格 JSON object，任一字段缺失/非法枚举/非 JSON 抛 `ValueError`。
- `metrics.py`：`generate_live_answers` 按 B=20 批量实时生成（显式 `num_predict`）；7-rubric 与 `chat_quality` 均按批判官；`chat_quality` 分数仍走 `ENUM_MAPS[chat_quality]` + `enum_to_score`，`judge_mode="batch-enumeration-single-pass"` **如实标注非多数投票**；`retrieval_relevance` 也按批并显式 `num_predict`。
- 判官类 `detail` 新增 `judge_sample_count` / `batch_count` / `total_items`；部分批次失败时其余批照常出分、`sample_count` 写实际 K 条、`reason` 说明缺口；全失败则 7 维 `degraded` + `value=null` + `reason`。所有 metric 仍经 `build_metric`。
- 所有批次共用 `score()` 的**同一个 deadline**，每批前 `_bounded_timeout`（内部 `_check_deadline` 语义）收紧，不新开无截止线程。
- 无 LLM 维度（检索 6 / 意图 3 / 字面 2 / 生成诊断 2）对全部样本真实计算；`hybrid_search` / `detect_skill` 结果不缓存成假值。
- 五端点 / 22 key / `group` / 稳定错误码 / `compare` 历史 6 项与 22 项 run 兼容未变（既有 346 个用例覆盖）。

## 4. 生成脚本数据源决策（诚实留痕）

- 首次试过「`POST /api/kb/ask` 的 SSE `citations` 事件逐题派生」：提前断开 SSE 后服务端仍会跑完整生成，120 次调用会拖垮 Ollama 队列并导致工具超时；随后试过 `GET /api/kb/documents/{id}/inspection`，发现该端点在 manifest 缺失时会**触发 `submit_document_reindex`（写副作用）**且状态不稳定（15 篇里可用数从 9 篇跌到 2 篇），违反「只读 KB」硬约束，已放弃。
- 最终方案：首次生成时由 `citations`（`hybrid_search` 真实命中身份）派生并**冻结在 gold**；复跑只用纯只读 `GET /api/kb/health` + `GET /api/kb/papers` 校验每份身份的 `paper_id` 仍属于当前 KB，不重新检索、不触发写副作用。冻结集缺失时才以少量 citations 从零派生。KB 不可用 / 身份失效 → 打印 `BLOCKED` 并退出码 2，**不写任何 gold、绝不编造 `paper_id`/`chunk_index`**。
- `generated_at` 取 042 冻结集文件的 UTC mtime（只读输入的确定性属性），不依赖当前时间。实地取证：连跑 3 次，三份文件 sha256 完全一致；交错改造后又连跑 2 次，`chat-quality` sha256 一致。
- `rag-retrieval` 全部 128 条的 `relevant_doc_ids[].paper_id` 均能命中当前 KB（64 papers）；`chat-quality` 的 100 条 `kb_source.paper_id` 同样命中。

## 5. 验证命令与真实输出

在仓库根目录、`.venv` 已激活：

```
.venv/bin/ruff check backend/app/evaluation backend/eval_042/judge_client.py scripts/generate_evaluation_samples.py
→ All checks passed!
.venv/bin/python -m py_compile backend/app/evaluation/*.py backend/eval_042/judge_client.py scripts/generate_evaluation_samples.py
→ PY_COMPILE OK
.venv/bin/python -m pytest -q tests/evaluation
→ 346 passed in 4.07s     （基线 293 passed；TDD RED 时 45 failed / 8 passed）
.venv/bin/python scripts/generate_evaluation_samples.py --check
→ rag-retrieval items=128 sha256=bf0cbc8f… / intent-classification items=120 sha256=5d8bbc38… / chat-quality items=120 sha256=a8a606fc… / --check: 未写文件
```

补充：`cd backend && ../.venv/bin/ruff check .` 会报 **57 个既有债务**（`report.writer` 等其它模块），已确认 `grep -E "app/evaluation/|eval_042/judge_client"` 输出为空，即与本次改动文件无关；任务卡指定范围的 ruff 全绿。

新增用例按能力命名、文件名不含 spec/task 编号；既有 6 个测试文件仅做契约跟随的最小修复（未删除用例、未弱化断言意图）。

## 6. 小样本真实 API 冒烟（重启后，非 mock）

- 重启：`RERANKER_ENABLED=false ./deploy/stop.sh` → `RERANKER_ENABLED=false ./deploy/start.sh -d`（`deploy/run.pid` 与 8000 监听进程一致，无需手工同步；新 PID 31710），`/api/health` 200 后才测；**未使用裸 kill**。
- 请求：`POST /api/evaluation/score` `{"strategy_id":"baseline","model":"qwen3.5:9b","dataset_id":"chat-quality","max_items":2}`。
- 结果（`smoke_2.status`）：**HTTP 200 / 65.073531s**；`run_id=eval-ca2657062094459696c2364a977b7bc7`，22 项齐全。
- 状态分布：**12 computed / 10 needs_ground_truth / 0 degraded**。computed 含 `chat_quality(value=1.0,n=2)`、7 个 rubric（`answer_relevance=0.75`、`groundedness=0.5` 等，均为真实枚举映射）、2 个字面、2 个诊断；10 个 `needs_ground_truth` 是 chat-quality 集对检索/意图维度的跨 dataset 早退（逐字保留、零外部调用），每个都带 `reason` 且 `value=null`。
- `chat_quality.detail`：`judge_mode=batch-enumeration-single-pass`、`judge_sample_count=2`、`batch_count=1`、`total_items=2`、`question_max_chars=600`，`score_mapping` 仍指向 `ENUM_MAPS[chat_quality]`。

**第一次冒烟（优化前）的诚实留痕**：同样的 2 条请求曾耗时 **243.25s** 且返回 11 项 `degraded` / `generation_success_rate=0.0`——根因是 042 冻结 trace 的 `input` 是 2000~4776 字符的完整多轮对话记录，超长 prompt 使本地 9b 模型无法稳定输出批量 JSON（`ValueError`）。诊断证实「短问题批量协议 4.5s 正确返回严格 JSON」，故做了三处范围内修复：① 送入模型与真实检索的 question 取尾部最新用户问题（上限 600 字符，`detail.question_max_chars` 如实标注）；② `BATCH_NUM_PREDICT` 4096→2048；③ chat 集按「1 冻结 + 5 KB」交错，避免 B=20 首批全是超长冻结文本。修复后重跑即得到上面的 65s / 12 computed / 0 degraded。

## 7. Go/No-Go 100 条基准（交主会话执行）

脚本：`docs/sdd/plans/047/runs/task-14/benchmark_100.py`（`--check` 判定逻辑已离线 5/5 验证）。

```
# 服务已按 §6 重启、/api/health 200 后：
.venv/bin/python docs/sdd/plans/047/runs/task-14/benchmark_100.py \
    --max-items 100 \
    --output docs/sdd/plans/047/runs/task-14/go-no-go.json \
    --log    docs/sdd/plans/047/runs/task-14/go-no-go.log
# 退出码 GO=0 / NO_GO=1 / 服务不可用=2
# 可选：--model qwen3.5:9b（默认取 /api/evaluation/options 第一个本地模型）
#       --dataset-id chat-quality（默认）；--timeout 960（须大于 900s 硬判据）
```

- 产物 `go-no-go.json`：状态码、`run_id`、总耗时、22 项 `status`/`sample_count`/`value`/`reason`/`judge_sample_count`/`batch_count`/`total_items`、violations、`verdict`；`go-no-go.log` 逐字保留原始响应与请求。
- 硬判据（P1-1）：总耗时 ≤900s、所有 computed 维度 `sample_count≥100` 且 `value` 非 null、HTTP 200、22 key；**300s 只是优化目标线，不是失败线**。

### 已知耗时风险（务必先看，不要静默降采样）
- 2 条真实请求 65.07s；100 条按批次数外推：生成 10 次（judge/answer_quality 各 5 批）+ chat 判官 5 次 + rubric 判官 5 次 + 约 100 次真实 `hybrid_search`（groundedness 上下文）。每批 20 条的 prompt/输出都大于 2 条批次，**总耗时有可能逼近或超过 900s**，Go/No-Go 需由真实基准判定，本报告不预判 GO。
- 若主会话实测 >900s 或任一 computed 维度 `sample_count<100`：按 P1-1 先调批次大小 / 预算（例如让 `judge_metrics` 与 `answer_quality_metrics` 共用同一次批量生成以减半生成调用、或换更快的本地被测模型），**仍不达标立即回传阻塞，回到 spec 修订并再次请求确认**；不得静默降采样、不得靠 `degraded` 收场、不得改写判据。
- `memory_correctness` 按 P1-4 永久 `needs_ground_truth`，不参与 computed 判据；这是 spec 既有约定，不是本次降级。

## 8. 风险与阻塞

1. **Go/No-Go 未由本分派执行**（任务卡明确交主会话）：本分派只完成脚本、小样本冒烟与判定逻辑离线验证；`go-no-go.json` / `go-no-go.log` 尚未生成，主会话勿误读为已有结论。
2. **100 条耗时风险**见 §7，未做任何降采样或判据放宽。
3. `backend` 全量 ruff 的 57 个既有债务不在本次范围，未顺手修复（最小改动原则）。
4. 工作区中 `frontend/**`、`reviews/**`、`specs/**`、状态台账的 diff 来自并行分派的其他角色，本分派未触碰，未 push、未合 main。

## 9. 主会话下一动作

1. 保持当前已重启服务（PID 31710、新代码 + 新 gold 均已加载），确认 `/api/health` 200。
2. 执行 `benchmark_100.py --max-items 100`，落盘 `go-no-go.json` / `go-no-go.log`，按 §7 判据给出 Go/No-Go 结论；不达标按 P1-1 处置并回传阻塞。
3. 之后按 spec §11 交给 task-15（前端紧凑卡片，独立分派）与 task-16（真实 API / 浏览器 E2E、验收签字）。
4. 若需要复核生成脚本幂等：连跑两次 `python scripts/generate_evaluation_samples.py` 后 `shasum -a 256 docs/sdd/plans/047/gold/builtin-*.json` 对比（本报告已取证 3 次一致）。

## 10. Go/No-Go NO_GO 后的共享生成修复（范围内性能缺陷 · 不新增 spec）

### 触发事实（首轮证据逐字保留，未改写 / 未删除）
- `go-no-go.json`：`qwen3.8:27b-q4_K_M` / `chat-quality` / `max_items=100` → `http_status=504`、`total_elapsed_seconds=900.016`、`verdict=NO_GO`；`go-no-go.log` 稳定错误体 `EVAL_SCORE_TIMEOUT`。
- 根因：`judge_metrics` 与 `answer_quality_metrics` 各自调用一次 `generate_live_answers`，100 条被所选被测模型实时生成两遍（10 批而非 5 批）；§7 已把「让两者共用同一次批量生成以减半生成调用」列为允许的优化建议。按 spec §13.1 P1-1，NO_GO 后先做范围内缺陷修复：不降采样、不靠 degraded 收场、不改写 900s 硬判据。

### 改动点（仅 3 个文件，最小增量）
| 文件:行号 | 改动 |
| --- | --- |
| `backend/app/evaluation/metrics.py:492-510` | `judge_metrics` 新增可选 kw `live=(answers, failure_types)`；`live=None` 时仍自行调用既有 `generate_live_answers`（直接调用行为不变）。判官、`ENUM_MAPS[chat_quality]` + `enum_to_score`、detail 文案逐字不动。 |
| `backend/app/evaluation/metrics.py:704-727` | `answer_quality_metrics` 同款 `live` 注入，11 个维度共用同一批 answers 与 failure_types。 |
| `backend/app/evaluation/service.py:184-205` / `:208-247` | `_judge_metrics` / `_answer_quality_metrics` 新增可选 `chat_items` / `live` 透传；跨 dataset `needs_ground_truth` 早退分支逐字保留、零外部调用；不传时仍各自 `load_chat_items()` + 实时生成。 |
| `backend/app/evaluation/service.py:286-308` | `score()` 在 `dataset_id=="chat-quality"` 时只加载一次 chat 集、只调用一次 `metrics.generate_live_answers`，把同一份 `chat_items` 与同一 `live` 分发给两族；生成调用纳入既有 `_call_with_deadline(fn, deadline-time.monotonic())`，仍共用**同一个 deadline**、每批前 `_bounded_timeout`。 |
| `tests/evaluation/test_shared_live_generation.py:1-233` | 新增 5 条契约测试（按能力命名、无编号），复用既有 `batch_transport_doubles.batch_transport` 替身。 |

不变项：22 key / `METRIC_KEYS` / `METRIC_GROUPS` / 五端点 / 请求响应字段 / 稳定错误码 / `BATCH_SIZE=20` / `call_ollama` 默认 `num_predict=160`（批量仍显式 `BATCH_NUM_PREDICT=2048`）/ `backend/eval_042/**` 的 `ENUM_MAPS`、`PROMPTS`、`KNOWN_TASKS`。反伪造红线逐字保留：answers 仍由所选被测模型实时生成（`answer_source="live_generation"`、`generation_model_used=True`），失败批次如实 `generation_failures` + `degraded` + `reason`，不回退冻结 `output`、不缓存假值、不静默记 0；`sample_count` / `judge_sample_count` / `batch_count` / `total_items` 与实际条数严格一致。

### 验证（全部离线；未重启服务、未杀进程、未跑真实 HTTP）
| 命令 | 退出码 | 真实输出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/evaluation`（修复前基线） | 0 | `346 passed in 4.49s` |
| `.venv/bin/python -m pytest -q tests/evaluation/test_shared_live_generation.py`（RED） | 1 | `3 failed, 2 passed in 2.95s`（`assert 10 == 5`、`assert 2 == 1`） |
| 同上（GREEN） | 0 | `5 passed in 2.31s` |
| `.venv/bin/python -m pytest -q tests/evaluation`（全量回归） | 0 | `351 passed in 5.70s` |
| `.venv/bin/ruff check backend/app/evaluation/metrics.py backend/app/evaluation/service.py tests/evaluation/test_shared_live_generation.py` | 0 | `All checks passed!` |
| `cd backend && ../.venv/bin/ruff check .` | 1 | `Found 57 errors`，与 §8.3 记录的既有 57 个债务数字一致，**无一条指向 `app/evaluation/*`**，本次未引入新 lint |
| `.venv/bin/python -m py_compile` 三个改动文件 | 0 | 无输出 |

注：本机 `source .venv/bin/activate` 被 PATH 覆盖落到系统 anaconda（缺 fastapi，首次基线 4 个 collection error），故统一用 `.venv/bin/python`（3.11.16 / fastapi 0.141.1 / pytest 9.1.1 / ruff 0.16.6）绝对路径。

**一次生成断言的实测结果**：`test_one_score_request_runs_a_single_five_batch_generation_sequence` 修复前 `BATCH GENERATION` 调用 **10 次**（RED `assert 10 == 5`），修复后 **5 次 × 20 条**，全部 `model=fake-model`、`num_predict=2048`、`timeout>0`；`test_judge_and_answer_quality_receive_the_same_live_answers` 修复前 `generate_live_answers` 调用 **2 次**（RED `assert 2 == 1`），修复后 **1 次**，且两族收到的 `live` tuple 与 `answers` 列表均为**同一个对象**（`is` 断言通过）；生成失败路径仍只尝试 5 批，两族 `generation_failures=100`、`degraded` + `reason` 如实，不回退冻结 output。

### 预期耗时收益
- 生成侧：100 条由 **10 批降为 5 批**（减少 5 批 27B 模型批量实时生成），命中首轮 900.016s 超时的主要耗时来源；判官侧 chat 5 批 + 7-rubric 5 批、约 100 次真实 `hybrid_search` 均不变。
- 不降采样、不改 `max_items`、不靠 `degraded` 收场、不改写 900s 硬判据；**是否达标须由主会话重跑真实 100 条基准判定**，本分派不预判 GO。

### 剩余风险 / 未做项
1. **可选合批未做**：「7-rubric 批量判官 + chat_quality 批量判官合并为一次调用（8 标签 × B 条）」需新增一整套批量 prompt / parser、改动 `judge_mode` 标注与既有批量协议契约测试，风险高且超出最小改动；按任务卡「若风险高就不做，不要为此引入新协议缺陷」执行。若复测仍 >900s，这是 P1-1 的下一个候选。
2. **未跑真实 HTTP**：后台基准 PID 42620 正在运行，本分派严禁重启 / 杀进程；当前服务进程仍加载旧代码，新代码需主会话在基准结束后重启、再重跑 100 条基准才生效。`go-no-go*` / `benchmark_100.py` 逐字未改。
3. 直接调用 `metrics.judge_metrics` / `answer_quality_metrics`（不经 `score()`）时 `live=None`，仍各自生成一遍 —— 为兼容既有单测（`test_batch_metrics_honesty.py` 直接调两函数断言 generation 共 10 批）而保留；生产唯一入口 `service.score()` 已共享。若将来新增第二个调用方，须显式传 `live`。
4. 判官侧 10 批与检索上下文调用未压缩，是 900s 内的主要剩余耗时；未做任何降采样或判据放宽。
5. 工作区其它 diff（`frontend/**`、`backend/eval_042/judge_client.py`、`gold/**`、reviews / spec / 状态台账）来自在途的其它分派，本分派未触碰；未 push、未合 main。
