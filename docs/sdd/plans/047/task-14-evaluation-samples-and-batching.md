# 追加范围三 Task14：≥100 条真实样本 + 批量化 + Go/No-Go 基准（后端）

> 状态：**已完成**（Go/No-Go 最终部署版本 GO / 596.084s；共享生成修复与集中复审通过） ｜ 关联 [spec-047 追加范围三](../../specs/047-evaluation-p2-and-observability-fixes.md)（§2/§4/§6/§9/**§13 裁决**） ｜ 索引 [README](./README.md)
> 分派：`backend-dev`（独立一次）｜ 依赖：需求评审 [§15](../../reviews/047-requirement-review.md)「通过」+ 技术评审 [「追加范围三」](../../reviews/047-tech-review.md)「通过」（P0=0/P1=4）
> **唯一裁决口径**：spec §13.1 的 4 项 P1 裁决优先于上文 §2.1/§2.2/§4/§7 的历史表述，逐条实现，不改用户目标 / 公开接口 / 用户行为。

## 1. 一句话目标

三份内置集各扩到 ≥100 条真实派生样本，把逐样本生成/逐样本判官改成批量链路，
让 `POST /api/evaluation/score` 在 900s 内对 **100 条真实出分**、22 项 `sample_count` 与实际计算条数严格一致，
并用真实 100 条基准判定 Go/No-Go。

## 2. 文件边界（严格遵守）

**只允许改**：
- 新建 `scripts/generate_evaluation_samples.py`
- `docs/sdd/plans/047/gold/builtin-rag-retrieval.json`、`builtin-intent-classification.json`、`builtin-chat-quality.json`
- `backend/app/evaluation/contracts.py`、`datasets.py`、`service.py`、`metrics.py`、`rubrics.py`
- `backend/eval_042/judge_client.py`（**仅**加可选 `num_predict` 形参，见 §4.3）
- 新增 `tests/evaluation/test_*.py`（按能力命名，**文件名禁含 spec/task 编号**）
- 新建 `docs/sdd/plans/047/runs/task-14/implementation.md` 与基准产物

**禁止改**：`frontend/**`（前端由 task-15 独立分派）、`backend/app/api/routes_evaluation.py`、
`backend/eval_042/config.py` 的 `ENUM_MAPS` / `PROMPTS`、`backend/eval_042/runner.py` 的 `KNOWN_TASKS`、
`backend/app/evaluation/store.py`、`backend/app/knowledge_base/**`、任何 `.env` / 配置 / 业务对话链路 / SSE 帧、
`docs/sdd/specs/**` / `docs/sdd/reviews/**` / `docs/sdd/spec-status-changelog.md`（主会话负责）。

## 3. 样本生成脚本（先做，可复跑幂等）

`scripts/generate_evaluation_samples.py`：**只读 KB，只写三份 gold 文件**，确定性（固定问题列表 / 固定排序 / 不依赖当前时间生成随机内容），
复跑后三份文件逐字节一致（可用 `sha256sum` 前后对比取证）；不含任何分数字段、不写死 `value` / `score`。

三份集**保持现有 schema**（`dataset_id` / `schema_version` / `source:"builtin-fixture"` / `synthetic:true` /
`label_source` / `label_source_note` / `derivation_rule` / `items`），`load_dataset` 校验规则不变；
每份补 `generated_at` / `generator`（脚本路径）/ `item_count = len(items)` / 更新后的 `derivation_rule`。

| 集 | 现有 | 目标 | 派生口径（真实性硬约束） |
|---|---|---|---|
| `rag-retrieval` | 8 | **≥100（建议 120）** | 沿用 `kb-derived:retrieval-rank`：从**当前 KB 真实文档/chunk** 构造 `question`，`relevant_doc_ids` 取真实 `hybrid_search` 命中身份 `(paper_id, chunker, chunk_index, page)`，`derived_chunk_excerpt` 来自真实 `Hit.text`。**不编造 `paper_id` / `chunk_index`**；现有 8 条连同 `kb_alignment` 结论保留 |
| `intent-classification` | 16 | **≥100（建议 120）** | 沿用 `registry-derived`：从 `backend/app/skills/registry.py::build_default_tool_registry()` 的 **7 个真实 Tool 名**派生 `message`，覆盖每技能、易混淆表达、否定式与无关表达；`expected_intent` 只用真实技能名 / `none`。不复用过时 USENIX 技能名、不造不存在的技能 |
| `chat-quality` | `items=[]`（复用 042 的 20 条） | **≥100（建议 120）** | 见 §4.1 唯一数据源裁决：20 条 042 冻结 trace + ≥80 条 KB 派生，`items` 实打实落盘 |

KB 读取方式：优先通过**运行中的主服务只读 HTTP**（`POST /api/kb/ask` 的 `citations` 事件 / `GET /api/kb/*`），
与现有 8 条的 `derivation_rule` 口径一致；Qdrant 为本地文件模式、**必须单进程**，不要在服务运行时另起进程内 `hybrid_search`。
服务不可用就如实回传阻塞，**绝不编造 chunk 身份**。

## 4. 四项 P1 裁决（spec §13.1，逐条落地）

### 4.1 P1-4 chat 集唯一数据源与两层 `synthetic` 口径

- `gold/builtin-chat-quality.json` 的 `items` 数组**实打实 ≥100 条**：
  - 20 条来自 `docs/sdd/plans/042/task-02-eval-dataset.json`（`status=="scored" && synthetic is False`、`input`/`output` 非空字符串），
    条目级保留 `synthetic:false`、`reference_source:"frozen-042-trace"`；
  - ≥80 条从 KB 真实 chunk 构造 `input`，以真实 chunk 摘要作 `output`，条目级 `synthetic:true`、`reference_source:"kb-chunk"`；
  - 每条必须有 `status:"scored"`、`input`、`output` 且 `output.strip()` 非空。
- **文档级** `synthetic:true` 表示内置 fixture 集（`load_dataset` 强制校验、不冒充人工标注）；
  **条目级** `synthetic` 只表示来源，二者层级不同、不矛盾。`label_source` 明示「KB 派生 + 冻结 trace」。
- `datasets.load_chat_items()` 改为从 `gold/builtin-chat-quality.json` 加载并做上述字段校验，
  **不再读 042 文件、不再按条目级 `synthetic` 过滤**；`service.py:194/229` 的打分对象随之同源。
- `datasets.list_datasets()` 的 `chat-quality` 分支删除「取文档 `item_count` 的写死值」，
  统一 `item_count = len(document["items"])`；`item_count` / `scoreable_item_count` 与 `items` 严格一致。
- `CHAT_DATASET_PATH` 常量若不再使用则移除；`safe_dataset_path` 白名单与路径穿越校验**不变**。
- `memory_correctness` 仍因无 `prior_context` / 标注保持 `needs_ground_truth` + `reason`（不改文案里的「24 条」为不实数字，可改为实际条数）。
- 跨 dataset 早退（`service._answer_quality_metrics` 的 `dataset_id != "chat-quality"` 分支、`_judge_metrics` 同）**逐字保留**，零外部调用。

### 4.2 P1-2 超时与 `max_items` 常量（单一真源）

- `contracts.py`：`DEFAULT_MAX_ITEMS 3 → 100`、`MAX_ITEMS 20 → 200`、`SCORE_TIMEOUT_SECONDS 300.0 → 900.0`。
- `service.py:37` 的 `SCORE_TIMEOUT_SECONDS = 300.0` 是 `score():257` 实际生效真源 → **删除该重复定义**，
  在顶部 `from .contracts import (...)` 中导入 `SCORE_TIMEOUT_SECONDS`，收敛为单一真源。
- `_clamp_max_items` 边界语义不变（bool / ≤0 / 非 int 回落默认 100，`>200` 截断 200）。
- 补一条一致性契约测试：`service.SCORE_TIMEOUT_SECONDS is contracts.SCORE_TIMEOUT_SECONDS == 900.0`。

### 4.3 P1-3 `call_ollama` 输出上限（唯一例外）

- `backend/eval_042/judge_client.py:154` `call_ollama(model, messages, timeout=180)` 增加**可选**形参
  `num_predict: int | None = None`：`None` 时 body 的 `options.num_predict` **仍为 160**（默认行为逐字不变）；
  显式传值时覆盖。仅批量生成 / 批量判官调用显式传入更大值（按批大小估算，B=20 建议 ≥2048）。
- **不改** `ENUM_MAPS` / `PROMPTS` / `KNOWN_TASKS` / `judge_one` / `judge_majority` 的行为，不新建客户端或第二套框架。
- 补「不传参时 body 仍为 160」的默认行为回归测试；此例外须写入 `runs/task-14/implementation.md`。

### 4.4 P1-1 Go/No-Go 硬判据

**硬判据**：真实 100 条打分总耗时 ≤ **900s**、22 项 `computed` 维度 `sample_count ≥ 100` 且 `value` 非 `null`。
**300s 仅为优化目标线，不是失败线**。不达标先调批次大小 / 预算重试；**仍不达标立即回传阻塞**，
由主会话回到 spec 修订并再次请求确认，**不得静默降采样、不得靠 `degraded` 收场、不得改写判据**。

## 5. 批量化实现（唯一传输层 `eval_042.judge_client.call_ollama`）

1. **批量实时生成**：新增「一次 `call_ollama` 回答一批 B 条问题（严格 JSON 数组，索引 `"0".."B-1"`）」，
   B 默认 20，100 条 = 5 次调用；显式传 `num_predict`。回答仍由**所选被测模型实时生成**，
   保留 `answer_source="live_generation"` / `generation_model_used=True` / `under_test_model`；
   某批解析失败或空回答 → 该批如实计入 `generation_failures`，**不回退冻结 `output`**、不静默记 0。
2. **批量 7-rubric 判官**：扩展 `rubrics.py`（参照既有 `build_retrieval_relevance_messages` 的「索引 → 枚举」模式），
   一次判 B 条 × `RUBRIC_KEYS` 7 项；解析失败**整批 7 维度 `degraded` + `reason`**，不逐维度编造分数。
3. **`chat_quality` 批量化**：`judge_metrics` 的逐条 `_judge_score` 改为按批判官枚举，
   分数仍走 `backend/eval_042/config.py::ENUM_MAPS[chat_quality]` + `enum_to_score` 映射，
   `score_mapping` 字段与 `KNOWN_TASKS` 注册不变；`detail.judge_mode` 如实标注批量枚举（**不得声称仍是多数投票**）。
   若能在 900s 内保留多数投票语义则优先保留，同样须如实标注。
4. **无 LLM 维度全量真实计算**：检索 6 项、意图 3 项、字面一致性 2 项、生成诊断 2 项对**全部 100 条**计算，
   `sample_count=100`；`hybrid_search` / `detect_skill` 结果不得缓存成假值。
5. **共用 deadline**：所有批次纳入既有 `service._call_with_deadline` 与 `score()` 的**同一个 `deadline`**，
   每批前 `_check_deadline`，不新开无截止线程。
6. **诚实标注**：判官类 `detail` 新增 `judge_sample_count` / `batch_count` / `total_items`；
   若因预算/失败只完成 K 条判官，`sample_count` 写 `K`、`judge_sample_count=K`、`total_items=100`、
   `reason` 说明缺口；**绝不写 100 冒充、绝不只跑 3 条还显示大数**。
7. **反伪造红线**：所有 metric 仍经 `build_metric`（`status != computed → value=None` 且 `detail.reason` 必填）；
   非 computed 一律 `degraded` / `needs_ground_truth` / `unavailable` + `reason`，不隐藏卡片、不把 `null` 当 0。
8. **接口不变**：五端点路径 / 请求体字段 / `metrics[]` 22 key + `group` / 稳定错误码 / `compare.deltas[]` 全部不变；
   历史 6 项与 22 项旧 run 在详情、历史、compare 中继续兼容（缺 `judge_sample_count` 不报错）。

## 6. Go/No-Go 真实基准（前置，不 mock）

- 写 `docs/sdd/plans/047/runs/task-14/benchmark_100.py`：对**重启后加载新代码的服务**发真实
  `POST /api/evaluation/score`（`{"strategy_id":"baseline","model":<本地可用模型>,"dataset_id":"chat-quality","max_items":100}`），
  记录 HTTP 状态码、`run_id`、总耗时、各阶段耗时、22 项 `status` / `sample_count` / `value` / `detail.reason`。
- 重启用标准脚本 `RERANKER_ENABLED=false ./deploy/stop.sh` + `./deploy/start.sh -d`（先同步 `deploy/run.pid`），
  `/api/health` 200 后才开跑；生产目录禁止裸 `kill`。
- 产物落 `docs/sdd/plans/047/runs/task-14/go-no-go.json` 与 `go-no-go.log`（原始响应逐字保留），
  `implementation.md` 写明 Go / No-Go 结论与依据。**内部函数 / mock / 仅脚本调用不能替代真实 API E2E**（task-16 会再验一次）。

## 7. 测试（TDD：先写失败用例再实现）

新增 `tests/evaluation/` 下按能力命名用例，至少覆盖：

- 三份 gold 集各 ≥100 条、schema 合法、`synthetic:true` / `label_source` 非空、`item_count == len(items)`；
  `relevant_doc_ids` 的 `paper_id` / `chunk_index` 能在当前 KB 命中；chat 集 20 条冻结 trace + KB 派生条目字段齐全。
- 生成脚本复跑幂等（两次运行后 sha256 一致）；畸形文档仍返回 `EVAL_DATASET_INVALID`。
- `DEFAULT_MAX_ITEMS=100` / `MAX_ITEMS=200` / `SCORE_TIMEOUT_SECONDS=900.0`；`service` 与 `contracts` 单一真源；
  `max_items` 为 0 / 负数 / `true` / 字符串 / 99999 的收敛；集少于 100 条时 `sample_count` 如实写实际条数。
- `call_ollama` 不传 `num_predict` 时 body 仍为 160、传值才覆盖；`judge_one` / `judge_majority` 行为不回归。
- 批量生成 / 批量 rubric 解析：正常 JSON、带围栏、缺字段、非法枚举、非 JSON → 成功或整批 `degraded` + `reason`，
  不出现逐维度编造分数、不出现 0。
- `chat_quality` 批量分数仍走 `ENUM_MAPS[chat_quality]` + `enum_to_score`；`judge_mode` 如实标注。
- `sample_count` 与实际计算条数一致；失败批次只影响该批维度、其余照常出分；跨 dataset 早退零外部调用。
- 历史 6 项 / 22 项无新字段的 run 在 `runs` / `runs/{id}` / `compare` 正常显示；五端点错误码回归。

验收命令（回传真实输出：命令 + 退出码 + 通过数）：
```
cd /Users/wjh/ResearchAgent && .venv/bin/ruff check backend/app/evaluation backend/eval_042/judge_client.py scripts/generate_evaluation_samples.py
.venv/bin/python -m pytest -q tests/evaluation
.venv/bin/python -m py_compile backend/app/evaluation/*.py scripts/generate_evaluation_samples.py
```

## 8. 明确不做 / 反伪造红线

- 不新增第 23 个指标、不改 `METRIC_KEYS` / `METRIC_GROUPS`、不新增端点 / DB 表 / 迁移 / SSE 事件。
- 不引入 `openevals` 依赖、不新建判官客户端 / 第二套评测框架；除 §4.3 的唯一例外外不改 `backend/eval_042/**`。
- 不伪造样本、不冒充人工标注 / 真实业务数据、不写死分数；不把 100 条缩成 3 条还显示 100。
- 不把 `degraded` / `needs_ground_truth` 卡片隐藏成关闭态；不把 `value=null` 显示成 0。
- 不静默降采样、不靠 `degraded` 收场、不改写 Go/No-Go 硬判据。
- 不改原六块与追加范围二的历史结论；不 push、不合 main。

## 9. 产出物 / 变更日志

- 代码与三份 gold 集、生成脚本、契约测试、Go/No-Go 基准产物。
- 落盘交接：`docs/sdd/plans/047/runs/task-14/implementation.md`（改动文件、4 项 P1 逐条落地证据、Go/No-Go 结论、命令/退出码、风险与阻塞、主会话下一动作）。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-14/backend-dev/<YYYYmmdd-HHMMSS>.md`，每步「观察 / 判断 / 下一步 / 进度 X%」，回传必须给日志路径。
- 新建文件只能用 `Bash` heredoc（定界符加单引号），创建后 `Read` 读回校验。
- 回传请 concise：改动清单 + 定向测试真实输出 + Go/No-Go 结论 + 阻塞项 + 日志路径；**不要粘贴大段代码**。
