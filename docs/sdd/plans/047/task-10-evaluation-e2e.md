# task-10 评测台真实 E2E / 部署 / 验收

> 关联：[spec-047 追加范围](../../specs/047-evaluation-p2-and-observability-fixes.md)（2026-11-10 用户授权，D7–D12，尤其 D12 验收口径）
> 索引：[README.md](./README.md) ｜ 依据：[需求评审 §13](../../reviews/047-requirement-review.md) / [技术评审「追加范围技术评审」](../../reviews/047-tech-review.md)
> 依赖：task-08（后端端点）+ task-09（前端视图）完成；本任务为追加范围收口

## 状态
**已完成**（2026-11-10 收口：真实 API E2E + 真实浏览器 E2E 均通过；验收评审 §13 通过 17/17、准备度 9/10、P0=0/P1=0，架构师已签字）

## 一句话目标
在**当前部署版本**上跑通「界面三选一 → 真实打分 → 看到分维度分数 → 至少一次策略切换 delta」的完整人工验收主案例，落盘真实请求/响应/HTTP 码/`run_id`/产物路径，产出验收结论（准备度 ≥9/10、无 P0/P1）。

## 前置条件
- 主服务 `/api/health` 200、`/api/kb/health` `qdrant:true/embedding:true`（主会话 2026-11-10 实测 papers:64 / chunks:19905 / `reranker:false(available:false)`）、`/api/models` 与 Ollama `/api/tags` 可用；E2E 前复核。
- **Langfuse 3000 当前未启动不得据此判定失败**：本追加范围打分不依赖 Langfuse UI，Langfuse 仅作既有 score 落点；判官不可用/超时按 `degraded` 或 `EVAL_BACKEND_UNAVAILABLE` 如实返回，不视为验收失败。
- `reranker` 当前 `available=false`：选 `rerank-on` 预设须如实标 `degraded` 并说明原因，**不得伪造收益**。
- 模型实时生成耗时：`POST /api/evaluation/score` 须用 `max_items` 上限约束（D11 / 技术评审风险项），避免超时。

## 文件边界（唯一可改）
- `docs/sdd/plans/047/runs/task-10/`：真实 E2E 证据（请求体 / 响应体 / HTTP 码 / `run_id` / 产物路径 / 分维度分数 / delta / 人工验收详情）。
- `docs/sdd/reviews/047-acceptance-review.md`：追加范围验收结论（由 `tester` 产出、`architect` 签字）——若主会话另行指定路径则从之。
- `deploy/` 启停仅为取证（不改脚本内容）；**不改**业务代码 / 测试 / 配置 / `.env`、不写 `spec-status-changelog.md`（主会话）、不改 ADR0002 正文（实现阶段同批追加）、不新建 spec 编号。

## 分派角色
`tester`（汇总单端报告 + 当前部署版本真实 API E2E + 验收结论）+ **主会话**（部署启停、状态台账、`origin/main` 核对、收口）。

## 验收（D12 硬口径）
- **当前部署版本真实 `POST /api/evaluation/score` 成功案例**：请求 / 响应 / HTTP 码 / `run_id` / 产物路径全部落盘。
- **RAG 与意图两个维度真实出分**（非 mock、非占位）：`rag-retrieval` 集出 `recall@k`/`precision@k`/`mrr@k`，`intent-classification` 集出 `intent_accuracy`，可看到分维度分数。
- 界面主案例走通：三个下拉选 `strategy_id`+`model`+`dataset_id` → 点「开始评分」→ 看到每维度独立分数卡（数值/状态/样本数/明细）。
- 至少一次**策略切换**产生按维度 `delta`（看得到每种策略导致的效果提升）；不可比组合返回 `EVAL_NOT_COMPARABLE` 且不含 delta。
- 准备度 ≥9/10、无 P0/P1；全量回归 `cd backend && python -m pytest -q` 无回归、前端静态契约通过。
- **不 push、不合 main**，`origin/main` 仍 `1b26c76c`（收口后核对）。

## 回滚
- 本任务只产出证据与文档，不改运行时实现；如需撤回，删除 `runs/task-10/` 证据与验收追加段即可，业务功能与端点不受影响。若 E2E 暴露实现缺陷，退回 task-08/09 修复后重跑，不伪造通过。

## 产出物
- `docs/sdd/plans/047/runs/task-10/`（真实 E2E 证据 JSON + 人工验收详情 md：逐步点击、点击后提示、等待条件、下一步、失败恢复、产物路径）、`docs/sdd/reviews/047-acceptance-review.md` 追加范围验收段（准备度 / P0 / P1 / 签字栏）。
