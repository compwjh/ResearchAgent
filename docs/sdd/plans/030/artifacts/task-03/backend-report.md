# Spec030 Task03 后端交接报告

## 结果状态和摘要

`PASS`。实现 `evidence-report-v1` 的 Claim、ClaimEvidence、ComparisonDimension 与 PaperComparisonCell 最小领域模型、ResearchStore 增量表及 owner/version 隔离；新增矩阵应用服务和 POST/GET `/api/research-tasks/{id}/evidence-matrix`。Evidence 严格校验枚举、ID 归属、摘要/全文 locator、页码和 SHA-256 provenance；全文必须复用 Spec029 EvidenceUpgrade，不可定位时 fail closed；无证据单元格显式为 `missing` 并进入 limitations。

## 改动文件

- `backend/app/research/domain/models.py`
- `backend/app/research/infrastructure/research_store.py`
- `backend/app/research/application/evidence_matrix.py`
- `backend/app/research/application/entry.py`
- `backend/app/api/routes_research.py`
- `tests/test_spec030_matrix.py`
- `docs/sdd/plans/030/artifacts/task-03/backend-report.md`

## 测试命令/退出码/结果

- `.venv/bin/python -m pytest -q tests/test_spec030_matrix.py` — 退出码 `0`，`3 passed`。
- `.venv/bin/python -m pytest -q tests/test_spec029_fulltext_evidence.py tests/test_spec029_reuse_gate.py tests/test_spec027_runtime_contract.py` — 退出码 `0`，`48 passed`。
- `.venv/bin/python -m py_compile backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py backend/app/research/application/evidence_matrix.py backend/app/research/application/entry.py backend/app/api/routes_research.py` — 退出码 `0`。
- `git diff --check` — 退出码 `0`。

## 产物路径

`docs/sdd/plans/030/artifacts/task-03/backend-report.md`

## 决策依据

- 复用既有 `ResearchStore`、目录 `research_paper_selections`、`research_document_links` 和 Spec029 `research_evidence_upgrades`，不复制论文元数据、不新建检索/embedding/chunker/下载器。
- 采用加性 SQLite 表并维持既有 schema marker；任务删除和 legacy cleanup 均先清理矩阵子表，保持外键 `RESTRICT`。
- 读投影遇到 unavailable/revalidation_required 时只降级当前 cell，保留历史 Evidence 记录。

## 风险阻塞

- Task04 仍需将该 canonical projection 接入不可覆盖报告版本与 citation manifest；本 Task 不实现报告生成或导出。
- 全文 `quote_digest` 必须由上游已定位原文提供；EvidenceUpgrade 当前只保存 locator provenance，不保存原文摘要，因此服务不会自行猜测 digest。
- 未运行全量回归、真实数据、网络或前端验证（按 Task03 范围）。

## 主 Agent 后续动作

读取本报告并复核后，执行后端评审/Task03 验收；将 Task03 状态与 `spec-status-changelog.md` 台账同步，再分派 Task04。收口时补跑全量回归、运行时启动验证与部署。

## 开始/结束/总耗时

- 开始：`2026-09-17T02:08+08:00`
- 结束：`2026-09-17T02:22+08:00`
- 总耗时：约 `14 分钟`

## 模型和工具统计

- 模型：Luna high（临时分派）
- 工具：文件读取、`apply_patch`、定向 pytest、`py_compile`、`git diff --check`
- 网络/真实数据：未使用
