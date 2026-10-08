# Spec032 Task14：全文证据恢复接缝修复候选

日期：2026-10-08（Asia/Shanghai）  
角色：backend-dev；状态：**候选实现，待 backend-reviewer 复审；未部署、未提交**

## 结论

已在现有 upload → document link → `EvidenceUpgradeService` → evidence matrix → `/reports` 契约内落下最小候选修复。它不会把上传成功宣称为全文已进入报告，也不会创建新 schema、公开 API、终态 reopen、第二套下载链或伪造 `AgentRun`。

当前 canonical `ResearchArtifact`、session `final_message_id` 和 notification 仍然阻塞：`POST /api/research-tasks/{task_id}/reports` 仍只生成持久化 `ResearchReport`，本轮没有扩大到 `ReportDeliveryService` 接线。

## 先红灯：修复前证据

命令：

```text
.venv/bin/python -m pytest -q tests/research/test_fulltext_evidence.py tests/research/test_report_generation.py tests/paper_discovery/test_paper_issue_recovery.py
```

结果：退出码 1，22 passed、3 failed。

三个失败分别固定了：

1. 既有上传链接为 `indexing` 时，全文升级被错误地当成 `DOCUMENT_NOT_APPROVED`；
2. 显式 `/reports` 生成前没有调用既有 `EvidenceUpgradeService.revalidate()`；
3. issue upload 无条件把 canonical KB 返回的 `indexing` 状态持久化为 `ResearchDocumentLink.status="completed"`。

## 候选改动

- `backend/app/api/routes_paper.py:1387-1399`：复用 KB upload 已返回的索引状态写入已有 document link；未知状态 fail-closed 为 `pending`，继续返回既有 `report_action="generate_new_version"`。上传事件仍表示上传动作完成，不被伪装成全文验证完成。
- `backend/app/research/application/evidence_upgrade.py:59-105`：将 `indexing`/`indexed_partial` 作为已确认候选链接交给现有升级流程；真实全文门禁仍由 source hash、manifest、generation、chunk 和检索命中校验决定，`pending`/`queued`/`failed` 不进入 allowlist。
- `backend/app/research/application/report_generation.py:224-233`：用户显式生成报告前复用 `EvidenceUpgradeService.revalidate()`；失败按既有 `REPORT_NOT_READY` 语义停止，不隐式生成、重开 task 或创建 AgentRun。
- `backend/app/research/application/evidence_matrix.py:254-286`：对现有 fulltext Evidence 再核对已持久化 upgrade 的状态、document、source hash、manifest provenance、chunker 和 chunk IDs；不匹配时只在当前报告投影中标记 `revalidation_required` 并将 cell 降级为 missing，不改写旧报告或历史 ClaimEvidence。

新增定向测试：

- `tests/research/test_fulltext_evidence.py`：indexing document link 只有 manifest 验证通过才可升级；
- `tests/paper_discovery/test_paper_issue_recovery.py`：upload 保留 canonical `indexing` link 状态且仍只返回生成新版本提示；
- `tests/research/test_report_generation.py`：revalidation 后全文 Evidence 不进入 citation manifest，报告变为 partial，cell 显式 missing。

## 验证

修复后定向命令：

```text
.venv/bin/python -m pytest -q tests/research/test_fulltext_evidence.py tests/research/test_report_generation.py tests/paper_discovery/test_paper_issue_recovery.py
```

结果：退出码 0，25 passed，1.20s。

编译检查：上述改动的 backend/tests 文件使用 `compileall`，退出码 0。

Ruff：本轮仅清理了候选新增的 `report_generation.py` 与报告测试 import 排序；重新检查退出码仍为 1，但只剩 5 项既有基线告警：`evidence_matrix.py` 的 unused `hashlib`，以及 `evidence_upgrade.py` 的 SIM105/SIM114。未修改这些基线告警。

## canonical artifact 状态与风险

- **canonical artifact：仍阻塞。** 本轮只保护 ResearchReport 的全文证据真实性；没有声称 session artifact/message/notification 已生成。
- **状态异步性：** 新手工上传通常先持久化为 `indexing`，待 KB manifest/generation/chunk 真正可验证后，用户仍须显式走既有 evidence upgrade 和 matrix 写入；没有新增轮询或自动升级。
- **fail-closed 影响：** KB manifest 缺失、generation 变化、source hash/fingerprint/chunk 不匹配时，显式 `/reports` 仍可按既有矩阵生成 partial 报告，但全文 cell/citation 会被降级并带 limitation，不再声称全文支持。
- **复审/部署门禁：** 本候选尚未由 backend-reviewer 签字，未启动或变更部署，未提交 git。应先复审四个 backend 生产模块与三组定向测试，再决定是否清理 import lint 并进入部署验收。

## 下一项最小 backend-reviewer 工作

只读复审上述四个生产文件和三组新增测试，确认：

1. upload link 状态没有改变 issue action 或 acquisition event 语义；
2. allowlist 放宽不会绕过 manifest/source/generation/chunk 门禁；
3. `/reports` 只做现有 upgrade revalidation 和当前投影降级，旧 `ResearchReport` 仍 immutable；
4. 没有 schema/API/AgentRun/终态状态机变化。

复审通过后再运行同范围 pytest；canonical artifact 仍需另行架构决策，不能作为本修复的通过条件。

耗时：约 20 分钟（含红灯、实现候选和 25 项定向回归）。
