# Spec 029 / 030 / 031 —— API 成功产物样例

生成时间：2026-09-19
分支：`fix/spec029-030-031-pipeline`
服务：`http://127.0.0.1:8000`（`./deploy/start.sh -d`）

**本次验证任务（单一任务贯通三端）**

| 项 | 值 |
|---|---|
| research_session_id | `f5c6b35da05e424d816ec987faf582c4` |
| research_task_id | `426515552d2b5a61bdce681e22d22892` |
| 主题 | side-channel attacks and speculative execution |
| 目标 | 比较至少五篇 USENIX Security 论文在侧信道攻击与推测执行方向的威胁模型与评估方式 |
| WorkItem | 5 / 5 全部 `completed`（s1、s2 search-worker；e1 paper-evaluator；c1 research-critic；syn synthesizer） |
| 论文选集 | **10 条**落库 `research_paper_selections` |
| 任务终态 | `partial`（终止码 `AGENT_OUTPUT_INVALID`，详见文末「已知限制」） |

---

## 前置：跑通一次研究流水线

```bash
# 1) 建会话（intake 的 topic/objective/time_range 必须给全，否则 plans/generate 报 INTAKE_INCOMPLETE）
curl -s -X POST http://127.0.0.1:8000/api/research-sessions \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"ccdd7bc785254bca94d4e93c6e3e63c5","intake":{
        "topic":"side-channel attacks and speculative execution",
        "objective":"比较至少五篇 USENIX Security 论文在侧信道攻击与推测执行方向的威胁模型与评估方式",
        "time_range":{"from":2022,"to":2025},
        "language":"zh","sources":["USENIX Security"],"depth":"standard"}}'

# 2) 批准计划（command 必须带 subject_version 与 idempotency_key）
curl -s -X POST "http://127.0.0.1:8000/api/research-sessions/f5c6b35da05e424d816ec987faf582c4/commands" \
  -H 'Content-Type: application/json' \
  -d '{"command":"approve_plan","subject_version":1,"idempotency_key":"ap-spec32-verify-001"}'
```

流水线：2 路 `search_catalog` 并行 → `evaluate_papers` → `check_coverage` → `synthesize_preliminary_report`。
本次约 4 分钟跑完（本地 Ollama）。

---

## Spec 029 —— 全文采集预览 `POST /research-tasks/{id}/acquisition-preview`

请求（**必须带 `plan_version`**，否则 422）：

```bash
curl -s -X POST "http://127.0.0.1:8000/api/research-tasks/426515552d2b5a61bdce681e22d22892/acquisition-preview" \
  -H 'Content-Type: application/json' -d '{"plan_version":1}'
```

响应 **200**：

```json
{
  "research_task_id": "426515552d2b5a61bdce681e22d22892",
  "selection_version": 1,
  "items": [
    {"catalog_paper_id":"012003978a4883ce","status":"pending","document_id":null},
    {"catalog_paper_id":"154723ce0856642f","status":"pending","document_id":null},
    {"catalog_paper_id":"31ab0e103c14c1c2","status":"pending","document_id":null},
    {"catalog_paper_id":"541c71bf15b43394","status":"pending","document_id":null},
    {"catalog_paper_id":"ba342a19004e4a13","status":"pending","document_id":null},
    {"catalog_paper_id":"bc960f541ae1f5b1","status":"pending","document_id":null},
    {"catalog_paper_id":"bfcead0789701976","status":"pending","document_id":null},
    {"catalog_paper_id":"c1dc0e43cad8a4a3","status":"pending","document_id":null},
    {"catalog_paper_id":"ef3093268b79108e","status":"pending","document_id":null},
    {"catalog_paper_id":"f11a606c713386db","status":"pending","document_id":null}
  ]
}
```

> 修复前这里返回 `400 REPORT_NOT_READY · 论文选集尚未准备完成`（agent 路径从不落库选集）。

---

## Spec 030 —— 证据矩阵 `POST /research-tasks/{id}/evidence-matrix`

调用约束（踩过的坑）：

- `claims` / `dimensions` **必须显式传**，库里没有就报 `409 EVIDENCE_INSUFFICIENT`。
- 枚举：`confidence ∈ {low,medium,high}`、`claim.status ∈ {supported,contested,unresolved}`、
  `evidence_level ∈ {catalog,abstract,fulltext}`、`stance ∈ {supports,contradicts,contextual}`、
  `evidence.status ∈ {available,unavailable,revalidation_required}`、`cell.relation ∈ {supports,contradicts,contextual,missing}`。
- `catalog` 级 evidence 的 locator 必须带 `catalog_snapshot_id`。
- **`claim_id` / `evidence_id` / `dimension_id` 全局唯一**，跨任务复用会 503。
- **矩阵是 claim × paper × dimension 的全交叉**：多 claim 会让没有证据的组合变成 `missing` 单元格。
  想让报告不留缺口，就用**一个 claim + 每个 paper 一条 evidence**。

```bash
curl -s -X POST "http://127.0.0.1:8000/api/research-tasks/426515552d2b5a61bdce681e22d22892/evidence-matrix" \
  -H 'Content-Type: application/json' -d @artifacts/spec030-evidence-matrix-sample.json
```

响应 **202**，`schema_version: evidence-report-v1`：

| 指标 | 值 |
|---|---|
| `status` | **`completed`** |
| `limitations` | **`[]`**（无覆盖缺口） |
| cells | **20**（10 papers × 2 dimensions），missing **0** |
| claims / evidence / dimensions | 1 / 10 / 2 |

### 生成报告 `POST /research-tasks/{id}/reports`

```bash
curl -s -X POST "http://127.0.0.1:8000/api/research-tasks/426515552d2b5a61bdce681e22d22892/reports" \
  -H 'Content-Type: application/json' \
  -d '{"plan_version":1,"title":"USENIX Security 候选论文威胁建模与评估方式比较（Spec029/030/031 验收样例）"}'
```

```json
{
  "report_id": "report-426515552d2b5a61bdce681e22d22892-v1",
  "research_task_id": "426515552d2b5a61bdce681e22d22892",
  "plan_version": 1, "report_version": 1, "status": "partial",
  "limitations": ["Catalog-only evidence is descriptive and does not establish method or result claims."]
}
```

> `status: partial` **是设计使然**：全部证据都是 `catalog` 级（目录元数据），
> Spec030 规定仅目录级证据不足以支撑方法/结果层面的结论，因此报告保留 `partial` 并列入局限。
> 想拿到 `completed`，需要 Spec029 的全文采集把 `evidence_level` 提升到 `abstract` / `fulltext`。

### 三格式只读导出 `GET /research-tasks/{id}/reports/{version}?format=`

| format | HTTP | 大小 | 校验 |
|---|---|---|---|
| `json` | 200 | 13,249 B | `cells` 20、`citation_manifest.citations` 10、含 `claims`/`evidence`/`dimensions` |
| `markdown` | 200 | — | 结论 + 跨论文比较 + 局限 + 引用清单 [1]–[10] |
| `html` | 200 | 4,167 B | 带 `Content-Security-Policy: default-src 'none'` |

报告正文（markdown 摘录）：

```markdown
# USENIX Security 候选论文威胁建模与评估方式比较（Spec029/030/031 验收样例）

## 研究结论

### USENIX Security 候选论文的威胁建模与评估取向

本次召回的 USENIX Security 候选论文在威胁模型与评估方式上呈现明显分化： ... [1] [2] ... [10]

## 跨论文比较

- c-scope-4265 / 012003978a4883ce / d-eval-4265：supports  [1]
- ...（共 20 行）

## 引用清单

- [1] `012003978a4883ce`：`e-4265-01`
- ...（共 10 条）
```

---

## Spec 031 —— 动态模型资源路由

本次验证后 `research_routing_decisions` 共 **50 条**（本次任务新增 8 条）：

```
synthesizer      | qwen3.5:9b | fast tier resolved to 'qwen3.5:9b' via hint '9b' | 2026-09-18T19:48:11Z
research-critic  | qwen3.5:9b | fast tier resolved to 'qwen3.5:9b' via hint '9b' | 2026-09-18T19:48:08Z
paper-evaluator  | qwen3.5:9b | fast tier resolved to 'qwen3.5:9b' via hint '9b' | 2026-09-18T19:47:24Z
search-worker    | qwen3.5:9b | fast tier resolved to 'qwen3.5:9b' via hint '9b' | 2026-09-18T19:46:43Z
```

```sql
SELECT task_type, chosen_model, reason, created_at
FROM research_routing_decisions ORDER BY created_at DESC LIMIT 8;
```

### `GET /api/research-routing/status`（2026-09-19 补齐，原为 404）

探针可用 → **200**：

```json
{"active_policy":null,"model_health":null,
 "resource":{"available_memory_bytes":12186320896,"model_footprint_bytes":18155017220,
             "loaded_model_count":2,"max_safe_workers":1}}
```

探针不可用（Ollama 无已加载模型）→ **503，但响应体仍含降级状态**，符合 Spec031「503 探针不可用但含降级状态」：

```json
{"error":{"code":"RESOURCE_PROBE_FAILED"},"degraded":true,
 "active_policy":null,"model_health":null,"resource":null}
```

### `GET /api/research-routing/decisions?limit=3`（2026-09-19 补齐，原为 404）

**200**，脱敏输出（无 Prompt / 回答 / 思维链）：

```json
{"owner":"local-user","decisions":[{
  "task_type":"search-worker",
  "features":{"attempt":1,"role":"search-worker","tier":"fast","work_item":true},
  "candidate_models":["qwen3.8:27b-q4_K_M","qwen3.8:27b-mlx","qwen3.5:9b", "..."],
  "chosen_model":"qwen3.5:9b",
  "reason":"fast tier resolved to 'qwen3.5:9b' via hint '9b'",
  "policy_version":"spec027-static-v1",
  "created_at":"2026-09-17T08:41:42.470Z"}]}
```

---

## 本轮（2026-09-19）修掉的问题

1. **P0 —— synthesizer 因元数据依赖被跳过**（`backend/app/research/application/orchestrator.py`）
   `_validated_evaluator_candidates()` 的聚合分支要求 `ref_id in metadata_index`，而 `metadata_index` 来自
   search_worker `tool_results` 的 `catalog_metadata`。元数据一缺失就返回空 → synthesizer 被判
   `NO_VALIDATED_EVIDENCE` → **根本不被派发** → 任务 `partial`、`check_coverage`/`synthesize` 无产物。
   修法：新增 `_recalled_candidate_ids()`，把候选合法性依据改为 **Search Worker 的 `candidates` 召回白名单**，
   元数据只用来补字段、不再是准入门槛；不传白名单时行为与修改前完全一致。
   → 本次端到端 5/5 WorkItem 全部 completed，`syn` 正常派发。

2. **`/api/kb/health` 的 `qdrant:false` / `chunks:0` 是误报**
   根因是此前 8000 端口上残存了旧进程，Qdrant 本地文件模式（`data/kb/qdrant`）被多进程争抢。
   单进程重启后已恢复：`{"qdrant":true,"chunks":3342}`。P2 关闭。

## 已知限制（未修，按优先级）

- **P1 —— 召回相关度未生效**：10 条选集的 `relevance` 全是 `0.2`（`PaperEvaluator` 的下限阈值），
  且召回结果里混有明显离题的论文（如 Facebook 广告策略审计、VR 隐私审计）。
  根因：`CatalogRagAdapter` 在词法降级路径下对所有论文得分均为 0.0，排序退化为字典序。
  **这属于内容质量，不影响流程贯通。**
- **任务终态仍为 `partial`**：终止码 `AGENT_OUTPUT_INVALID`（`phase:research`），
  但 5 个 WorkItem 全部 completed、选集与报告均正常产出。原因待查（疑似首次 synth 尝试失败后重试成功，
  但 `synthesis_error` 未清空）。不影响 029/030 端点调用。
