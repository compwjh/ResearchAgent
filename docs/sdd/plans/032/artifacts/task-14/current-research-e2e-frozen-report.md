# Spec032 Task14 真实自然语言研究 E2E（frozen run）

结论：**BLOCKED（真实运行到 partial；未冒充成功）**。

本轮在当前部署 `HEAD 4b61c3f`、端口 `8000`、重启会话 `61488` 上创建了全新的 conversation/run。`GET /api/ready` 返回 HTTP 200 且 `ready=true`。请求级模型为 `qwen3.5:9b`、`reasoning_effort=off`；服务公开的全局当前模型仍为 `qwen3.8:27b`，没有修改全局模型、阈值、环境变量或旧任务数据。

## Run identity

- run_id：`spec032-task14-frozen-20261008T202830Z`
- conversation_id：`70986d07888844dc9eb7de256ddadc27`
- user_message_id：`9519bd4a14e44275b1145c03d99ca8d0`
- assistant_message_id：`9e5cc7acb4194cb0b06f69a27b3f2f16`
- research_session_id：`c129b90b6b2246258de471713ae0bf0b`
- intake_draft_id：`ee408db2e6b7498185482602e426d55f`
- research_task_id：`659d5279ac4b5574ab317c6368a6527c`
- search_id（s1）：`882a91d62bdf4b28add6d5f6fbaf8a8e`
- search_id（s2）：`8d2c71df62b949e8b45ca229dd81d21f`
- 任务实际开始/终止：`2026-10-08T20:28:30Z` → `2026-10-08T20:33:30Z`

自然语言请求原文：

> 请进行一次深度研究。主题是USENIX Security 2024中的security/privacy方法，目标是比较至少5篇方法与局限，并且最少选择5篇论文，最多选择5篇论文，目标论文数: 5，来源限定为USENIX Security，输出中文Markdown报告并使用行内引用。时间范围是2024-2024。

## Intake、计划和批准门禁

本 run 的 SSE 返回 `plan_pending_approval`。在批准前核对到：

- plan/subject version：`1/1`
- output hash：`f7cdc582002b1c9ddbf086fe029a00bf55652d80168a218e2e39e3c7d28adcb8`
- constraints：`min_paper_count=5`、`max_paper_count=5`、`target_paper_count=5`
- plan budget：`target_paper_count=5`
- s1/s2 `max_results=5`
- source：`usenix`；time range：`2024..2024`

随后只发送一次既有 `approve_plan` command：

```json
{
  "command": "approve_plan",
  "subject_version": 1,
  "scope_json": {
    "plan_version": 1,
    "output_hash": "f7cdc582002b1c9ddbf086fe029a00bf55652d80168a218e2e39e3c7d28adcb8"
  },
  "idempotency_key": "plan-approval:c129b90b6b2246258de471713ae0bf0b:1"
}
```

HTTP 200，approval 为 `approved`，创建 task `659d5279ac4b5574ab317c6368a6527c`，初始状态 `planning`，`target_paper_count=5`，`review_plan_first=true`。

同一验收轮的另一个全新 conversation 只作为失败证据保留：它的自然语言补答导致计划 `min=5` 但预算和搜索上限为 `12`（plan hash `1358bd2202eca1a8abf843aef17afad917317fcbaaf3dadd4be4c0e8e5cf1640`），因此没有批准、没有创建 task。本轮没有用 approval scope 修饰该错误计划，也没有重试旧 task。

## 异步真实阶段

按约 20 秒边界读取 task、events、acquisitions、matrix 和 artifacts，最终安全事件为 `event_seq=27`：`status=partial`、`selected_count=5`、`error_code=MATRIX_NOT_READY`。阶段事实如下：

1. s1、s2 `search_catalog` 均完成，真实 USENIX Security 2024 官方目录候选快照可追溯；
2. e1 `evaluate_papers` 完成；
3. c1 `check_coverage` 完成；
4. syn `synthesize_preliminary_report` 完成，随后任务进入 partial；
5. 自动导入批次 5/5 完成，但 evidence matrix 和 canonical ResearchReport 没有 ready。

fast worker/evaluator 的完成事件解析为 `qwen3.5:9b`；c1/syn 的启动事件出现 `qwen3.8:27b-q4_K_M`，对应完成事件解析为 `qwen3.5:9b`。这里原样保留事件事实，不将请求级模型声明扩大解释为所有角色的运行时保证。事件中曾出现 retryable `TRACE_PROJECTION_FAILED` 投影帧，但 task 的最终错误不是该帧，而是明确的 `MATRIX_NOT_READY`。

## 五篇选择与自动导入

任务 GET HTTP 200，终态为 `partial`，`target_paper_count=5`，`search_id=882a91d62bdf4b28add6d5f6fbaf8a8e`，runtime 未报告 retry/error。acquisition GET HTTP 200，`batch_id=2f3a1e04-f929-41c1-9e6c-63dbac2bfd02`、`selection_version=4`、`approval_status=completed`，items/links 各 5 个，全部 `completed`。`research_document_links` 只读记录给出以下真实映射：

- candidate `4e6322a23b92a271dbec9906c51fe0ab` → paper `a151fcff09944e7cbd1f4086376ae914` → document `a151fcff09944e7cbd1f4086376ae914`，导入项 `d324a2dc-d22c-4afb-96f8-b639ec66912e`，`GhostRace...pdf`；
- candidate `57e0402f82fe2ce354bea423b201fde3` → paper `527fe0c1515d48c78adec8f4eb7f4979` → document `527fe0c1515d48c78adec8f4eb7f4979`，导入项 `5507977a-6314-433a-9165-3021b9ddfb19`，`DNN-GP...pdf`；
- candidate `bb826cac3486a295d93eb9b6cea0a6f8` → paper `fa82faf63802431da803e1a99ce1411b` → document `fa82faf63802431da803e1a99ce1411b`，导入项 `71339c71-2888-44f4-981d-7c25da2d79a2`，`DARKFLEECE...pdf`；
- candidate `c74fdf1babb53a9cbcb6a6ac9fa5cd0e` → paper `2f002c403d4e49e79b4d2781fea38fc6` → document `2f002c403d4e49e79b4d2781fea38fc6`，导入项 `c0783591-4e92-4a4f-85e3-d8ed8bf70344`，`Batch-PIR...pdf`；
- candidate `ef9e0846844e5b02834163586ea6ddc9` → paper `56fc315e952342158e5ae2f5ef6f01a0` → document `56fc315e952342158e5ae2f5ef6f01a0`，导入项 `95528e91-4d3e-43b2-86e0-d4878a582b88`，`Stop-Don't-Click...pdf`。

上限严格保持为 5；本轮没有下载第 6 篇、删除文档、重建索引或重试旧 batch。

## Artifact 与 canonical report 边界

现有候选报告端点 `GET /api/research-tasks/659d5279ac4b5574ab317c6368a6527c/report` 返回 HTTP 200，但它明确是 `status=partial`、`report_id=artifact:64bdca35859e43c2b813a06c5c2a581a` 的 artifact-backed 投影：标题 `# 深度研究报告`，Markdown 15,563 字符/17,311 UTF-8 bytes，5 个 selections，5 个唯一 `catalog:` 行内引用，`limitations.artifact_backed=true`。这只能证明候选报告 artifact 非空，不能冒充 canonical ResearchReport。

session artifact 列表 HTTP 200，包含 report version 1 的三项元数据；只读下载均 HTTP 200：

- citation manifest `d2b3e09d409f45e79058dd93ed563fe3`：551 bytes，5 条 candidate→citation 映射，hash `62e7286793c9347a0019ad4fd3420ed29e7ff5027fa4ec52e17a8ca39f43109`；
- HTML `ee513fbebb264683a79ae9c512dc6b7b`：18,362 bytes（DB content 16,464 字符），hash `37a520edbf319ec7560dedb031165dfe538d77f4cd4a7d068ebc6e80ca84e4a2`；
- Markdown `64bdca35859e43c2b813a06c5c2a581a`：17,311 bytes（DB content 15,563 字符），hash `2935e855081931eeead84a2176aa2f1660653e2b69cd478604209b564b7d2cae`。

canonical 版本端点均未 ready：

- `/api/research-tasks/659d5279ac4b5574ab317c6368a6527c/reports/1?format=json` → HTTP 404，`REPORT_NOT_READY`；
- 同路径 `format=markdown` → HTTP 404，`REPORT_NOT_READY`；
- 同路径 `format=html` → HTTP 404，`REPORT_NOT_READY`。

Evidence matrix `GET /api/research-tasks/659d5279ac4b5574ab317c6368a6527c/evidence-matrix` → HTTP 409，`MATRIX_NOT_READY`。因此最终 canonical 报告查看路径不存在；可查看的仅是候选 artifact 下载路径，不能以其元数据替代 canonical JSON/Markdown/HTML。

## Synthesizer 输入/输出差异（非隐藏推理）

只读 `research_work_items`/`research_agent_runs` 当前 `syn` 行，未保存完整 prompt 或隐藏推理：

- 输入 top-level 有 `citation_allowlist`、`evidence_level`、`goal`、`language`、`matrix_context`、`report_version`、`validated_candidates`；`matrix_context` 明确含 5 个 `allowed_paper_ids`、5 个 candidates 和 2 个 dimensions（`facet-1`,`facet-2`），并与 5 个 validated candidate IDs/5 条 citation allowlist 一致；
- 完成输出 top-level 有 `artifact_ids`、`citation_manifest`、`output_hash`、`report_version`、`safe_summary`、`schema_version`、`sections`、`source_refs`，两项 sections 均覆盖同一 5 个 candidate IDs，5 个 `source_refs` 与 allowlist 一致；
- 完成输出**没有** `evidence_matrix`；`artifact_ids` 为空，实际 artifact 由既有投影链生成；AgentRun output hash 为 `5858468a1d885a92c177b4fce0fff04c2eb05056d7257a5cc7a4c56a7133b13f`。

所以本次 live 阻塞的可复核差异是：矩阵上下文已经进入 synth 输入，合法的五篇/五引用输出却没有返回 `evidence_matrix`，随后终态为 `MATRIX_NOT_READY`。建议 backend-dev 只检查现有 synthesizer 输出 schema/validator 与 matrix assembly/错误传播，确保同一冻结 5 项集合能进入现有矩阵和 canonical report 链；不要以 artifact 路径或前端按钮绕过该门禁。

## 验收准备度（10 项）

1. 当前部署 ready：**PASS**；
2. 自然语言入口新 run：**PASS**；
3. Intake 与计划 `min=max=target=5`：**PASS**；
4. version/hash 绑定批准：**PASS**；
5. 检索、评估、coverage 阶段有真实状态：**PASS**；
6. 选择集严格 5 且有 candidate/paper/document ID：**PASS**；
7. 受控公开论文导入 5/5 完成：**PASS**；
8. evidence matrix 非空并可读取：**FAIL**（HTTP 409 `MATRIX_NOT_READY`）；
9. canonical JSON/Markdown/HTML 报告可读且非空：**FAIL**（均 HTTP 404 `REPORT_NOT_READY`；候选 artifact 不替代）；
10. 可复现人工验收查看路径与成功恢复：**BLOCKED**（canonical 路径不存在，不能提供成功步骤）。

准备度为 7/10（70%），低于 90% 门槛；存在 live P1 级核心产物阻塞，不能交付人工验收，不能将本轮称为 Spec E2E 全部通过。完整脱敏请求、响应状态、实体 ID、产物长度/哈希与精确 synth 差异见同目录 `current-research-e2e-frozen-evidence.json`。此前失败 evidence/report 文件均保留，未覆盖。
