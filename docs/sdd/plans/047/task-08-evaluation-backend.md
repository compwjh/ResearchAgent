# task-08 评测台后端：指标注册表 / 内置标注集 / 端点 / 契约测试

> 关联：[spec-047 追加范围](../../specs/047-evaluation-p2-and-observability-fixes.md)（2026-11-10 用户授权，D7–D12）
> 索引：[README.md](./README.md) ｜ 依据：[需求评审 §13](../../reviews/047-requirement-review.md) / [技术评审「追加范围技术评审」](../../reviews/047-tech-review.md)
> 依赖：原六块（task-01..07）已收口，保持历史原样、不翻案；本任务为追加范围后端，前置于 task-09（前端）/ task-10（E2E）

## 状态
**已完成**（2026-11-10 收口：五端点 / 三份标注集 / 多维度真实指标 / 33 passed 契约测试；被测模型假开关 P1 已修复为实时生成）

## 一句话目标
在 `backend/` 内新增评测台：三选一（策略/被测模型/评测集）触发真实多维度打分，RAG `recall@k`/`precision@k`/`mrr@k`、意图 `intent_accuracy`、回答质量 `chat_quality`/`memory_correctness` 各自独立出分，复用既有实现、绝不 mock 数值，提供 `/api/evaluation/*` 五个端点与稳定错误体。

## 前置条件
- spec-047 追加范围章节与两份追加评审已落盘（下游只认落盘文档）；`origin/main` 仍 `1b26c76c`。
- 运行前 `source .venv/bin/activate`（依赖在仓库根 `.venv`，`backend-patterns` Addendum）。
- 主服务 `/api/health` 200、`/api/kb/health` 的 `qdrant:true/embedding:true`、`/api/models` 可用、Ollama `/api/tags` 可用（主会话 2026-11-10 实测；E2E 阶段复核）。
- 复用点均为只读：`backend/app/knowledge_base/infrastructure/retrieve.py`、`backend/app/skills/intent.py`、`backend/app/skills/registry.py`、`backend/app/api/routes_models.py`、`backend/eval_042/{judge_client,runner,config}.py`。

## 文件边界（唯一可改；均为实现阶段**拟新建/复用**，当前尚未创建，不得当作已实现）
- 拟新建 `backend/app/api/routes_evaluation.py`（五个端点，API 层只做校验与编排）。
- 拟新建 `backend/app/evaluation/`（service 层：策略预设注册表、多维指标注册表、标注集加载与校验、run 产物读写；具体文件名由实现阶段定名）。
- 拟新建内置标注集 `docs/sdd/plans/047/gold/builtin-{rag-retrieval,intent-classification,chat-quality}.json`（D10；路径为设计建议，实现阶段可微调但须在白名单目录内）。
- 拟新建 run 产物目录（只读白名单，如 `docs/sdd/plans/047/runs/evaluation/`），`report.json` 风格落盘。
- 复用（只读，禁止修改、禁止第二套）：`retrieve.py::hybrid_search`、`intent.py::detect_skill` / `SkillDecision`、`registry.py` 技能名、`routes_models.py` 数据源、`eval_042` 既有判官 `judge_client.py`/`runner.py`/`config.py`。
- 新增契约测试（后端 pytest，路径随现有 `tests/` 约定）：三选一校验、各错误码稳定错误体、路径穿越、不可比差值、degraded/needs_ground_truth 不出假数值、指标真实计算可复算。
- **不改**：原六块任何业务代码 / 测试 / 配置 / `.env`、`frontend/`（归 task-09）、`spec-status-changelog.md`（主会话）、`ADR0002`（实现阶段同批追加）、`docs/sdd/specs/*`（本轮已由架构师定稿）。

## 分派角色
`backend-dev`（实现 + 红绿测试 + 契约测试）；`backend-tester` 单端回归。

## 验收
- `GET /api/evaluation/options` 返回 `{strategies, models, datasets}`，`models` 复用 `/api/models` 数据源；策略预设至少 `baseline`/`chunker-v2`/`topk-10`/`rerank-on`。
- `POST /api/evaluation/score` 真实返回含 `run_id` 与 `metrics[]`；`chat-quality` 集复用既有判官出分；`rag-retrieval` 集经 `hybrid_search` 与 `relevant_doc_ids` 身份 join 真实出 `recall@k`/`precision@k`/`mrr@k`；`intent-classification` 集经 `detect_skill` 与 `expected_intent` 比对真实出 `intent_accuracy`（D12：非 mock、非占位）。
- 每个指标独立 `{key,label,value,status,sample_count,detail}`，`status∈computed|degraded|needs_ground_truth|unavailable`；不可用必带 `reason`，`reranker` 不可用如实 `degraded` 不伪造收益。
- 错误码 `EVAL_OPTION_NOT_FOUND`/`EVAL_DATASET_INVALID`/`EVAL_BACKEND_UNAVAILABLE`/`EVAL_SCORE_TIMEOUT`/`EVAL_NOT_COMPARABLE` 全部稳定错误体、不裸 500（回归清单第 11 条：端点内外部依赖调用纳入 `try/except`）；只读白名单目录、防路径穿越。
- 标注集明确标 `source:"builtin-fixture"`、`synthetic:true`、`label_source`；RAG 集落盘与 014 十题 / 当前 KB 的对齐验证结果（当前 KB 是否含那些 `paper_id` 由实现阶段核实并落盘）；意图集技能名对齐 `registry.py`；不冒充人工标注/真实业务数据（沿用 `spec-042:236,245`、`backend/eval_042/human_gold.py` 反伪造红线）。
- 红绿测试通过；`cd backend && python -m pytest -q` 无回归；`ruff check .`；`python -c "import app"` 导入冒烟。

## 回滚
- 新增端点/包/标注集/测试均为追加式，整体删除新增文件并移除路由注册即回到追加前状态；不影响原六块与既有 7-score 契约。
- run 产物为本地 JSON，删除不影响业务库（本追加范围**不新增表、无 DB 迁移 / 外键 / 事务 / 并发领用**）。

## 产出物
- `backend/app/api/routes_evaluation.py`、`backend/app/evaluation/`、三份内置标注集 JSON、契约测试、`docs/sdd/plans/047/runs/task-08/`（实现交接 `implementation.md` + 契约测试输出）。
