# 任务 04 — 实现语义排序与 Reranker 集成

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 03，且 spec-014 运行时可用
> 当前状态：`待执行`

## 一句话目标

把研究方向查询转换为稳定的语义初排，并调用 spec-014 对有限候选批量精排，使结果按可解释、可降级的最终相关度顺序返回。

## 背景与前置条件

- 输入是任务 03 已过滤、去重和补全的 `PaperCandidate`，最大 200 条。
- 复用现有 `bge-m3` embedding 与 spec-014 批量 rerank 客户端，不直接调用 Ollama Reranker chat。
- 本任务不改变知识库检索排序，也不持久化搜索 rerank 分数到 Qdrant。

## 数据、配置与接口

- 为搜索候选计算 `retrieval_score`、可空 `rerank_score`、`final_score` 和稳定 `rank`。
- 内部排序接口接收查询及有限候选，返回原候选 id 到分数/名次的映射。
- `/api/papers/search` 返回 `ranking_mode`、`rerank_degraded` 和不含敏感数据的 `warnings`。

## 实施步骤与文件边界

1. 冻结不少于 12 条方向查询、候选池和人工相关性标签；必须在查看最终 rerank 排名前落盘。
2. 以标题和摘要构造有限长度的候选文本；摘要缺失时不得虚构。
3. 复用 `bge-m3` 对查询和候选批量编码，计算有限余弦分数；空文本、NaN 和维度异常整体降级到词法初排。
4. 将初排前 N 条一次性发送给 spec-014；验证 index 唯一、范围合法、score 有限。
5. 明确最终排序：rerank 成功以 rerank 分数为主；失败时使用初排；同分保持原稳定顺序，再以年份和标题兜底。
6. 增加短时失败缓存，避免 Reranker 停机时每次搜索重复等待。
7. 为召回、embedding、rerank、降级和输出数量增加 spec-013 span，仅记录数量、耗时和原因。
8. 使用冻结集计算 nDCG@10，记录初排与最终排序，不允许事后修改标签制造通过。

## 子代理分派

- 分派 A（`junior-dev`）：语义初排服务及单元测试，最多 2 文件。
- 分派 B（`junior-dev`）：spec-014 适配与稳定排序，最多 2 文件。
- 分派 C（`junior-dev`）：搜索路由/观测最小接入及测试，最多 2 文件。
- `tester` 维护冻结集和指标脚本；`tech-lead` 复核排序契约与降级边界。

## 边界与明确不做

- 0/1 候选不调用 Reranker；候选多于上限先初排截断。
- embedding 或 rerank 连接、超时、格式、索引、分数异常均须有确定降级顺序。
- 不让大模型生成论文事实，不按会议声望覆盖语义相关度。
- 不暴露内部向量，不在前端允许手调权重，不写回知识库索引。

## 验收标准

- 研究方向查询的相关论文总体排在无关论文前，排序完全可重复。
- 一次搜索至多一次批量 rerank，请求只包含候选池上限内文本。
- Reranker 停服、超时、非法 JSON、重复/越界 index、NaN 分数均回退初排。
- 冻结集最终 nDCG@10 不低于初排，且无查询出现相关论文从前十全部消失。
- 观测包含阶段、数量、耗时和降级原因，不含完整查询/摘要。

## 风险、回滚与产出

- 风险：摘要缺失影响语义质量；使用标题初排并在 UI 明确摘要缺失。
- 回滚：关闭论文检索或切换到初排，知识库和 spec-014 原功能不受影响。
- 产出：语义排序服务、rerank 适配、冻结质量集、指标结果和测试。
- 执行结果：待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-04",
  "spec_id": "015",
  "title": "# 任务 04 — 实现语义排序与 Reranker 集成",
  "status": "pending",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-03",
    "spec-014-task-09"
  ],
  "required_gates": [
    "spec-015.legacy-resume-authorized"
  ],
  "agent_role": "backend-dev",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md",
    "backend/app/paper_discovery",
    "tests/paper_discovery",
    "docs/sdd/plans/015",
    "docs/sdd/reviews",
    "docs/sdd/specs/014-kb-reranker.md",
    "docs/sdd/specs/015-security-paper-discovery.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-015",
    "branch": "feature/spec-015-security-paper-discovery",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [
    "python3 -m pytest tests/paper_discovery"
  ],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-dev
Read: ["docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md", "backend/app/paper_discovery", "tests/paper_discovery", "docs/sdd/plans/015", "docs/sdd/reviews", "docs/sdd/specs/014-kb-reranker.md", "docs/sdd/specs/015-security-paper-discovery.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: ["python3 -m pytest tests/paper_discovery"]
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope. Frozen target/scope/acceptance: input is Task03 filtered, deduplicated and enriched PaperCandidate data (maximum 200); reuse bge-m3 and Spec014 batch reranking. Produce retrieval_score, optional rerank_score, final_score and stable rank; return ranking_mode, rerank_degraded and non-sensitive warnings. Freeze at least 12 direction queries and relevance labels before seeing final rankings. Keep KB ranking and Qdrant score persistence out of scope. Zero/one candidate skips reranking; all embedding/reranker errors have deterministic lexical fallback. Acceptance: stable relevant-before-irrelevant ordering; at most one bounded batch call; failures including timeout, malformed data, duplicate/out-of-range indexes and NaN degrade to initial ranking; frozen-set nDCG@10 is no worse than initial ranking and no query loses every relevant result from top 10; observability records stage/count/duration/reason without full query or abstract. Remaining work (verbatim from audit): 按 Task04 原范围实现语义排序与 Spec014 Reranker 接入；明确冻结质量集、排序指标/门槛、失败降级与定向/回归验收。Task03、Spec014 的既有完成结果作为依赖证据，不复做。 Acceptance: 原任务的全部验收标准均满足，并记录定向/回归证据；冻结质量集先于最终排序。 Release condition: Task03 与 Spec014 Task09 均完成，且 spec-015.legacy-resume-authorized 已有权威记录。
<!-- sdd-task-prompt:v1:end -->
