# Spec032 Task14：全文证据恢复候选独立后端复审

日期：2026-10-08（Asia/Shanghai）  
角色：backend-reviewer  
复审对象：`current-fulltext-recovery-fix.md` 及其当前工作树实际 diff  
范围：仅 `routes_paper.py`、`evidence_upgrade.py`、`evidence_matrix.py`、`report_generation.py` 与三组对应后端测试；未评审同一工作树中其他 agent 的 batchservice、source registry、NDSS 或报告架构文档改动。

## 结论

```text
P0=0
P1=0（就本候选 diff 的既定范围）
scoped_review=PASS
deploy_recommendation=可进入本切片下一门禁/候选部署（本轮未部署）
spec032_closure=NO-GO（canonical artifact/session final message/notification 仍是交接报告明确的独立缺口）
business_code_modified_by_reviewer=false
```

本候选没有发现把上传误报为已验证全文、绕过全文 EvidenceUpgrade 门禁、篡改旧报告、伪造 `AgentRun` 或重新打开终态任务的 P0/P1。结论只适用于“上传状态保真 + 已有全文证据重验证 + 显式 `/reports` 生成 `ResearchReport` 新版本”这条接缝，不能扩展为 Spec032 全生命周期或 canonical session artifact 已完成。

## 逐项核对

### 1. DocumentLink 状态与 issue 语义：通过

- `routes_paper.py:1387-1399` 现在把 canonical KB upload 的 `status` 规范化后写入已有 `ResearchDocumentLink`；允许 `indexing`、`indexed_partial` 等真实状态，未知值收敛为 `pending`，不再无条件写成 `completed`。
- `pending`、`queued`、`failed` 不会进入 `EvidenceUpgradeService._FULLTEXT_LINK_STATUSES`；`completed`、`indexed`、`available`、`indexing`、`indexed_partial` 只是候选 allowlist，不等于全文已验证。
- upload 仍记录既有 `AcquisitionEvent(phase="upload", status="completed")`，该事件表达上传动作完成，不被改写成全文索引完成；issue 仍返回既有 `report_action="generate_new_version"` 提示，不隐式生成报告。
- 新测试验证 canonical `indexing` 状态被保留且 action 不变：`test_upload_projects_canonical_indexing_status_to_document_link`。

### 2. EvidenceUpgrade 全文门禁：通过

`indexing`/`indexed_partial` 放宽只改变 document-link allowlist，未改变后续真实性门禁。`EvidenceUpgradeService` 仍要求：

- 已关联任务且状态在 allowlist 中的 `document_id`；请求文档不能扩大 allowlist。
- 发布 generation 可读；manifest 的 document ID、source hash、`indexed_source_sha256 == source_sha256`、`source_hash_state="verified"` 通过校验。
- manifest 不处于 `failed`/`building`/`indexing`，命中必须匹配 manifest 中的精确 chunk 文本、chunker、非负 chunk index 和有效页码，并由确定性 `point_id` 形成 locator。
- 持久化的 upgrade 仍带 source hash、manifest generation/fingerprint、chunker 与 chunk IDs；没有把检索文本直接保存为证据。

定向测试 `test_indexing_document_link_is_allowed_only_when_manifest_is_verified` 通过；未见新下载器、Qdrant collection、schema 或第二套全文链路。

### 3. 显式 `/reports` 重验证与旧版保护：通过

- `ReportGenerationService.generate()` 在任务 owner 校验后、读取矩阵前调用现有 `EvidenceUpgradeService.revalidate()`（`report_generation.py:224-233`）。重验证异常按既有 `REPORT_NOT_READY` 语义停止。
- `EvidenceMatrixService.read_matrix()` 对当前 upgrade 不再匹配的 fulltext Evidence 只做本次投影：标记 `revalidation_required`、清空受影响 cell 的 evidence IDs 并降级为 `missing`，追加 limitation；不改写旧 `ResearchReport`、历史 ClaimEvidence 或任务终态。
- report version 仍通过既有 `next_report_version()` 与 insert-only `save_research_report()` 生成；`ResearchReportRequest`、`POST /{task_id}/reports` 的请求/响应契约没有变化。
- 新测试验证 revalidation 后报告为 `partial`、全文 Evidence 不进入 citation manifest、cell 为 `missing`，且已有 immutable report 保护测试仍通过。

### 4. schema/API/AgentRun/终态边界：通过

当前实际生产 diff 仅新增上述状态投影、allowlist、矩阵 fail-closed 投影和 report 前置重验证；没有 `domain/models.py`、ResearchStore schema/migration、`ResearchReportRequest`、公开 endpoint、`AgentRun`、状态迁移或终态 reopen 变更。`ReportDeliveryService`/canonical artifact 接线也没有被伪造或偷偷新增。

## 定向验证记录

以下命令均在当前工作树执行，未启动服务、未写入生产数据、未运行全量回归：

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_issue_recovery.py tests/research/test_fulltext_evidence.py tests/research/test_report_generation.py` | 0 | **25 passed**（1.35s） |
| `.venv/bin/python -m compileall -q`（四个生产文件 + 三个测试文件） | 0 | 通过 |
| `git diff --check --`（上述七个文件） | 0 | 通过 |
| `.venv/bin/ruff check`（上述七个文件） | 1 | 5 项既有基线告警 |

Ruff 的 5 项全部位于未由本候选新增的代码：

- `evidence_matrix.py:11`：既有未使用 `hashlib`（baseline 单文件检查同样 1 项）。
- `evidence_upgrade.py` 的 `SIM105` 及 3 项 `SIM114`：均在 baseline `HEAD` 中已存在（baseline 单文件检查同样 4 项）。

当前候选新增/重排的 `report_generation.py` 导入及三个测试文件没有新增 Ruff 告警；本复审没有用自动修复改动基线告警。

## 保留边界与后续门禁

1. 本切片的 `report_action` 仍只是用户显式点击既有 `/reports` 的提示。`/reports` 当前持久化的是 `ResearchReport`，不自动调用 `ReportDeliveryService`，因此不能据此宣称 session `ResearchArtifact`、`final_message_id` 或 notification 已产生。
2. 本轮没有执行真实 PDF 上传、真实 KB generation/manifest/Qdrant 运行时验证，也没有重启候选服务；25 项是定向合同测试证据。Spec032 仍需另行完成真实 API E2E、artifact 交付与最终验收门禁。
3. 旧版报告按设计保持只读；若未来要把 canonical artifact 纳入 `/reports`，必须复用真实 synthesizer `AgentRun` 与既有 delivery contract，由架构/spec 单独确认，不能在此 diff 上直接扩展。
4. 基线观察（不归因于本候选、当前不计 P1）：`_manifest()` 对 schema-valid 的 `pending` manifest 没有显式 allowlist；这类 manifest 若同时带 verified hash/chunks，升级端点理论上可能返回空 fingerprint 的 `upgraded`，但现有 `EvidenceMatrix` 的 fulltext locator 校验要求 fingerprint 为 SHA-256，因此不能进入当前报告 citation。若后续要收紧“升级端点成功”语义，应单独只允许 `ready`/`partial` 并补 pending/failed 定向测试。

复审结论：**本候选后端 diff P0=0、P1=0，全文恢复接缝 scoped PASS；业务代码未修改。**
