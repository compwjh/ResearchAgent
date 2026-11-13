# Spec047 Task 05（P2②）单向分数映射 — 实施报告

> 分支 `feature/spec-047-evaluation-p2-and-observability-fixes` ｜ 角色 `backend-dev` ｜ 顺序：② → ③（本报告为 ②）

## 一句话结论

按定稿口径实现**单向**映射 `research_model_outcomes.quality_score` → Langfuse score `research_quality_score`（NUMERIC），
红绿契约测试 22 条通过、当前部署版本真实 Langfuse E2E `verified`。未改任何既有业务/评测文件，零反向写、零历史迁移、零新增端点/映射表。

## 改动清单

| 文件 | 类型 | 关键内容 |
|---|---|---|
| `backend/eval_042/score_mapping.py` | 新增（单一职责模块） | `SCORE_NAME="research_quality_score"` / `MAPPING_VERSION`；`normalize_quality_score`（L43）、`build_score_comment`（L56）、`map_quality_score`（L85，薄映射）、`map_decision_quality_score`（L149，读侧适配器）。默认 writer = `langfuse_export.post_score_idempotent` |
| `tests/evaluation/test_score_mapping.py` | 新增（文件名不含 spec/task 编号） | 22 条契约测试，覆盖 5 类口径 + 3 条附加 |
| `docs/sdd/plans/047/runs/task-05/score-mapping-e2e.json` | 新增（真实 E2E 证据） | 真实 score id / traceId / 状态码 / 回查 / 幂等 / 绑定 |

**未改动（② 范围内）**：`langfuse_export.py`、`runner.py`、`cli.py`、`report.py`、`human_gold.py`、`research_store.py`、`spans.py`、`config.py`、`.env`、`frontend/**`、spec/reviews/plans 正文、状态台账、045 已签字证据。（注：`config.py` 在后续 ③/Task06 由同一后端角色追加只读开关，属 ③ 范围，见 `runs/task-06/implementation.md`；② 未触碰。）

## 设计要点（对齐技术评审 §4.2）

- **单向**：`map_quality_score` 只读 `outcome.quality_score`/`decision_id`，只写 Langfuse；模块不持有任何业务 store/DB 连接，结构上无法反向覆盖业务表。读侧经 `map_decision_quality_score` 走既有 `get_model_outcome(decision_id, owner_id=...)`（只读），不调用任何写方法。
- **复用、不建第二套**：写侧直接复用 `post_score_idempotent`（其内部 = `post_score` + `find_score_by_id` 的「先 exact-ID 回查 → 确定性 `score_id` 写入」幂等组合）。确定性键由 `decision_id` 经 `extra=` 派生，重跑 delta=0。不改 `post_score` 的四字段 body，因此不触碰 045 已签字幂等键 / 五类指纹 / CLI 默认输出形状 / `human_agree_rate` 降级态。
- **NUMERIC**：value 传 Python `float`，Langfuse 依据数值型 value 推断 `dataType=NUMERIC`（真实部署实测回查确认）。
- **只对新样本、不迁历史**：映射函数只处理调用方传入的单条 outcome；不扫表、不回填历史 trace/score。
- **fail-open**：quality_score 缺失/非法（None/bool/str/NaN/inf/越界）、trace 缺失（不伪造 traceId）、任意写入异常 → 只记日志返回 `skipped`/`failed`，绝不抛异常、不冒泡。日志只记异常类型名，不落原始异常文本（回归清单 §14）。

## 红 → 绿（真实输出）

- RED：`.venv/bin/python -m pytest tests/evaluation/test_score_mapping.py -q` → `EXIT=2`，`1 error`：`ImportError: cannot import name 'score_mapping' from 'backend.eval_042'`（模块未实现）。
- GREEN：实现后同命令 → `22 passed in 0.25s`，`EXIT=0`。
- 回归：`tests/evaluation/` → `188 passed in 0.97s`（基线 166 + 新增 22），`EXIT=0`。
- lint：`ruff check backend/eval_042/score_mapping.py tests/evaluation/test_score_mapping.py` → `All checks passed!`，`EXIT=0`。

## 测试覆盖（5 类口径 + 附加）

1. 映射方向单向：`test_mapping_direction_is_single_way_outcome_to_langfuse`（outcome 前后快照一致 + 只 1 条 Langfuse 写）。
2. NUMERIC 值与 traceId 绑定：`test_numeric_value_is_bound_to_trace_id`（float 非 bool、`name`、`traceId`、`comment` 含 decision_id+版本、确定性 id）。
3. score 幂等重跑 delta=0：`test_rerun_is_idempotent_delta_zero`（两次映射仅 1 次 POST，`find_score_by_id` 被调用）。
4. 业务表未被反写：`test_business_outcome_table_is_never_written_back`（真实 `ResearchStore` 临时库逐行快照前后一致 + monkeypatch 写方法为抛错守卫）；`test_read_adapter_maps_from_store_and_never_writes_back`。
5. quality_score 缺失/非法不写不抛：`test_invalid_quality_score_writes_nothing_and_never_raises`（10 组 parametrize）+ `test_missing_quality_score_key_...`。
6. 附加：不伪造 traceId（3 组）、写入失败 fail-open 不冒泡、读侧适配器缺失/读失败 fail-open。

## 真实 E2E（当前部署版本 Langfuse `http://127.0.0.1:3000`）

产物：`docs/sdd/plans/047/runs/task-05/score-mapping-e2e.json`（`final_status: verified`）。凭据取自 `.env`（`LANGFUSE_PUBLIC_KEY/SECRET_KEY`，未打印、未改 `.env`）；仅用探针包装 `offline_urlopen` 记录真实 `response.status`，真实 HTTP 请求不变、无 mock/fake transport。

| 项 | 值 |
|---|---|
| 真实 traceId | `abfe474ba20272ba230a02327bf73024`（真实 `ollama-chat` 已完成 trace） |
| 真实 score id | `eval042-8bd8fce03feaf51667ffec5bf44876e1` |
| 首次写入 | `POST /api/public/scores` → **200**；先 `GET /api/public/scores/{dedupe_id}` → 404（尚未可见） |
| exact-ID 回查 | `GET /api/public/scores/eval042-8bd8...` → **200**，`dataType=NUMERIC`，`value=0.8`，`name=research_quality_score`，`traceId` 绑定一致 |
| 幂等重跑 | 第二次映射 `delta_posts=0`，复用同一 score_id（先 exact-ID 命中，不再 POST） |
| 绑定计数 | 该 trace 上 `research_quality_score` 恰好 1 条 |
| 8000 健康检查 | `/api/health` → 200（真实取证主要打 3000，不依赖 8000） |

## 风险与阻塞

- `research_model_outcomes` 业务表实测 0 行，本期以「等价只读样本」验证映射链路，未迁历史、未回填（与 F17 / 045:56 一致）。
- E2E 用 `offline_urlopen` 探针记录状态码，属只读观测包装，非 mock；真实 POST/GET 均发生且由既有 `post_score`/`find_score_by_id` 发出。
- 无阻塞；未越界（未碰 `frontend/**`、`spans.py`、`human_gold.py`、`.env`、spec/reviews/plans 正文、状态台账、045 证据）。
