# Spec 029 / 030 / 031 —— API 成功产物样例

生成时间：2026-09-18
服务：`http://127.0.0.1:8000`（uvicorn，仓库 venv）
验证任务：
- 任务 A `a12d43bf1bf759789535a2ff6305a4d8`（用于 030 证据矩阵 + 报告）
- 任务 B `859a926a3b5c5b8a98da21fbefe9b4f4`（用于 029 采集预览 → 030 证据矩阵）

研究主题：比较至少五篇公开论文在访问控制方面的研究方法（USENIX Security 2022–2025）

---

## 前置：跑通一次研究流水线

```bash
# 1) 建会话（intake 必须给全 topic/objective/time_range，否则 plans/generate 报 INTAKE_INCOMPLETE）
curl -s -X POST http://127.0.0.1:8000/api/research-sessions \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"7451383e897c4d0a9c3905eac9aa2846","intake":{
        "topic":"访问控制 access control 研究方法",
        "objective":"比较至少五篇公开论文在访问控制方面的研究方法",
        "time_range":{"from":2022,"to":2025},
        "language":"zh","sources":["USENIX Security"],"depth":"standard"}}'

# 2) 批准计划（command 必须带 subject_version 与 idempotency_key）
curl -s -X POST "http://127.0.0.1:8000/api/research-sessions/<SID>/commands" \
  -H 'Content-Type: application/json' \
  -d '{"command":"approve_plan","subject_version":1,"idempotency_key":"ap-<唯一键>"}'
```

流水线：2–3 路 `search_catalog` 并行 → `evaluate_papers` → `check_coverage` → `synthesize_preliminary_report`。
约 6–8 分钟跑完（本地 Ollama）。

---

## Spec 029 —— 全文采集预览 `POST /research-tasks/{id}/acquisition-preview`

请求（**必须带 `plan_version`**，否则 422）：

```bash
curl -s -X POST "http://127.0.0.1:8000/api/research-tasks/859a926a3b5c5b8a98da21fbefe9b4f4/acquisition-preview" \
  -H 'Content-Type: application/json' -d '{"plan_version":1}'
```

响应 `200`：

```json
{
  "research_task_id": "859a926a3b5c5b8a98da21fbefe9b4f4",
  "selection_version": 1,
  "items": [
    { "catalog_paper_id": "b839eca81d1c3e4d", "status": "pending", "document_id": null }
  ]
}
```

> 修复前这里返回 `400 REPORT_NOT_READY · 论文选集尚未准备完成`。

---

## Spec 030 —— 证据矩阵 `POST /research-tasks/{id}/evidence-matrix`

`claims` / `dimensions` 必须由调用方显式给出（库里没有就报 `409 EVIDENCE_INSUFFICIENT`）。
枚举取值：`confidence ∈ {low,medium,high}`、`claim.status ∈ {supported,contested,unresolved}`、
`evidence_level ∈ {catalog,abstract,fulltext}`、`stance ∈ {supports,contradicts,contextual}`、
`evidence.status ∈ {available,unavailable,revalidation_required}`、`cell.relation ∈ {supports,contradicts,contextual,missing}`。
`catalog` 级 evidence 的 locator 必须有 `catalog_snapshot_id`。
**`claim_id` / `evidence_id` / `dimension_id` 全局唯一**，跨任务复用会报 `evidence_id already exists with different identity`。

```bash
curl -s -X POST "http://127.0.0.1:8000/api/research-tasks/859a926a3b5c5b8a98da21fbefe9b4f4/evidence-matrix" \
  -H 'Content-Type: application/json' -d '{
    "plan_version": 1,
    "dimensions": [{"dimension_id":"d-threat-model-859a","label":"威胁模型","definition":"论文所建模的攻击者能力与信任边界","display_order":0}],
    "claims": [{"claim_id":"c-overgrant-859a","topic":"访问控制研究方法","statement":"日志与权限授予机制的过度授予是访问控制失配的主要研究切入点","confidence":"low","status":"supported","evidence_ids":["e-logging-859a"]}],
    "evidence": [{"evidence_id":"e-logging-859a","claim_id":"c-overgrant-859a","paper_id":"b839eca81d1c3e4d","evidence_level":"catalog","stance":"supports","status":"available","quote_digest":"","locator":{"catalog_snapshot_id":"b839eca81d1c3e4d"}}],
    "cells": [{"claim_id":"c-overgrant-859a","paper_id":"b839eca81d1c3e4d","dimension_id":"d-threat-model-859a","relation":"supports","evidence_ids":["e-logging-859a"],"summary":"Improving Logging to Reduce Permission Over-Grant：以日志改进降低权限过度授予。"}]
  }'
```

响应 `202`，`schema_version: evidence-report-v1`，落库结果：

| 表 | 行数（任务 A） |
|---|---|
| `research_claims` | 1 |
| `research_claim_evidence` | 2 |
| `research_comparison_cells` | 4 |
| `research_comparison_dimensions` | 2 |

### 生成报告 `POST /research-tasks/{id}/reports`

```bash
curl -s -X POST "http://127.0.0.1:8000/api/research-tasks/a12d43bf1bf759789535a2ff6305a4d8/reports" \
  -H 'Content-Type: application/json' \
  -d '{"plan_version":1,"title":"访问控制研究方法比较（USENIX Security 2022-2025）"}'
```

```json
{
  "report_id": "report-a12d43bf1bf759789535a2ff6305a4d8-v1",
  "plan_version": 1, "report_version": 1, "status": "partial",
  "limitations": [
    "c-access-control-methods/b839eca81d1c3e4d/d-evaluation: 仅有目录级证据，缺摘要/全文支撑评估方式维度",
    "c-access-control-methods/d06c306d9f414582/d-evaluation: 仅有目录级证据，缺摘要/全文支撑评估方式维度",
    "Catalog-only evidence is descriptive and does not establish method or result claims."
  ]
}
```

`GET /research-tasks/{id}/reports/1` 返回完整结构化报告：`cells` + `citation_manifest` + `claims` + `dimensions`。

---

## Spec 031 —— 动态模型资源路由

无独立 HTTP 端点；能力在流水线内部生效，决策写入 `research_routing_decisions`（本次验证后 34 条）。

```sql
SELECT task_type, chosen_model, reason, created_at
FROM research_routing_decisions ORDER BY rowid DESC LIMIT 3;
```

```
synthesizer    | qwen3.5:9b        | fast tier resolved to 'qwen3.5:9b' via hint '9b'          | 2026-09-17T19:37:15Z
research-critic| qwen3.5:9b        | fast tier resolved to 'qwen3.5:9b' via hint '9b'          | 2026-09-17T19:37:10Z
paper-evaluator| qwen3.8:27b-q4_K_M| strong tier resolved to 'qwen3.8:27b-q4_K_M' via hint '27b'| 2026-09-17T19:01:18Z
```

即：fast 档 → `qwen3.5:9b`；strong 档（重试升级后）→ `qwen3.8:27b-q4_K_M`。

---

## 本轮修掉的两个 bug

1. **`backend/app/skills/tool_dispatch.py`** —— `search_paper_catalog` 在外部实时源（DBLP / USENIX accepted）0 命中时
   没有任何本地目录兜底，直接把 0 条当成功返回。新增 `_search_catalog_local_fallback()`，
   经 `CatalogSearchAdapter`（Spec027 复用接缝的唯一出口）检索本地已索引目录并回填真实元数据。
2. **`backend/app/research/application/orchestrator.py`** —— agent 路径 `_run_agent_work_items()` 从不调用
   `replace_selections()`（`research_paper_selections` 恒为空），导致 Spec029 永远 `REPORT_NOT_READY`。
   新增 `_persist_agent_selections()`，在 evaluator completed 后落库，只接受 Search Worker 召回白名单内的 ID。

### 已知未修（下一轮内容优化）

- 中文 query 命中英文目录时，`CatalogRagAdapter` 词法降级对所有论文得分均为 0.0，排序实际退化为字典序。
  需要多语言 embedding（Qdrant 当前不可用）或查询改写才能改善。
- `/api/kb/health` 仍报 `qdrant:false`、`chunks:0`，主集合 `papers` 不存在，向量检索走的是降级路径。
- agent 路径在 3 路 search + 长 evaluator 的组合下，`check_coverage` / `synthesize_preliminary_report`
  可能被跳过（任务以 `partial` 收尾，终止码 `UPSTREAM_WORK_ITEM_FAILED`）。2 路 search 时能全部跑完。
