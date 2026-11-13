# task-05 P2② `quality_score` 与 Langfuse score 口径映射

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04；当前状态：`已完成`（22 passed；真实 score id 写入并 exact-ID 回查 verified） ｜ 对应 spec 表编号 06 ｜ 决策 D2②

## 状态与一句话目标

`待执行`。实现**单向**映射：业务 `research_model_outcomes.quality_score` → Langfuse score `research_quality_score`（复用既有 `post_score`），不反向覆盖业务表、不新增端点/映射表、不迁历史数据。

## 背景与前置条件

- [技术评审 §4.2](../../reviews/047-tech-review.md) 为口径定稿；F17 / `spec-045:56`：两套分数互不相认，`research_model_outcomes` 实测 0 行；落点 `research_store.py:846-857,879-889`（建表 889-900 / 写 5004-5031 / 读 4875-4879 / 聚合 3134-3147）、`langfuse_export.py:66-86` `post_score`、`:121-139` `find_score_by_id`、`/api/public/scores`。
- 前置：task-04 完成。

## 数据 / 配置 / 接口增量

- **方向：单向**（quality_score → Langfuse score）；**不反向覆盖** `quality_score`、不改 `save_model_outcome`(research_store.py:5004-5031) 写入逻辑。
- **目标 score name**：`research_quality_score`，`data_type="NUMERIC"`，`value` = 0..1 的 quality_score，`comment` 记来源 `decision_id` + 映射版本，`traceId` 用该决策关联 trace。
- **不新增映射表**：映射关系是固定常量（name + 来源前缀），不落库；**不新增业务端点**（`spec-045:187`）；不动 `POST /api/research-routing/policies/{v}/evidence`（`spec-045:193`）。
- **不迁历史**：只对新样本生效（以映射上线后 `created_at` 为界或仅处理本次运行新产出 outcome）；不回填历史 trace / 历史 Langfuse score。
- **幂等**：复用 `post_score` 的确定性 `score_id`（由 `decision_id` 派生）+ `post_score_idempotent` 先查后写，重跑不产生重复 score（对齐 045 加固项 08）。

## 实施步骤与文件边界

**唯一可改文件**：`backend/app/research/infrastructure/research_store.py`（**只读** quality_score）；`backend/eval_042/langfuse_export.py`（复用 `post_score`）；新增映射薄函数（可由 `eval_042` CLI / 报告阶段调用）+ 契约测试；`runs/task-05/` 证据。

1. **红**：给定一条 `quality_score` + 一条 trace，断言应产生 `name=research_quality_score` 的 Langfuse score（当前无映射 → 红）。
2. **绿**：实现薄映射函数（读 `ModelOutcome` → 调用 `post_score`）；`value` 一致、幂等重跑不重复、反向 `quality_score` 未被改写、历史 outcome 不迁移。
3. 分层：读走 `research_store.py` 既有方法、写走 `eval_042` 既有回写，不跨层直调、不新建端点。

## 子代理分派

- 后端改动 → `Task(backend-dev)`（最小上下文：技术评审 §4.2 + 本任务 + `文件:行号`）；回传片段 + 读回校验。
- 回归 → `Task(backend-tester)`。

## 边界与明确不做

- 不反向写业务表、不改 `quality_score` 原值、不新建映射表 / 业务端点。
- 不迁历史 trace / 历史 score；不回填 `research_model_outcomes` 0 行以外的历史数据。
- 不建第二套 score 回写、不改 `spans.py` 7 numeric score、`research_quality_score` 不混入 045 的 7-score 计数契约。
- 映射失败只记日志、不冒泡（fail-open，端点稳定错误体纪律）。
- 不 push、不合 main；不写状态台账；不改 `.env`。

## 验收、风险与回滚

- 红→绿契约测试通过；反向断言（业务表未改写）+ 幂等断言（重跑 score delta=0）+ 历史不迁移断言。
- **当前部署版本真实 E2E**：真实 `POST /api/public/scores` → 记录**真实 score id + traceId + HTTP 状态码 + `GET /api/public/scores/{id}` exact-ID 回查结果 + 产物路径**（`runs/task-05/score-mapping-*.json`）；ingestion 约 8s 后再下结论；**不 mock 冒充真实回写**。
- 风险：outcome 与 trace 无关联（须记 skip，不伪造 traceId）；Langfuse 不可达（fail-open）。回滚：回退映射薄函数，`post_score` 保持既有行为。

## 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/047/runs/task-05/score-mapping-*.json`（真实 score id / traceId / 回查结果）。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。

