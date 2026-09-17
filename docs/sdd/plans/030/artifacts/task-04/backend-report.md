# Spec030 Task04 后端交接报告

## 结果状态和摘要

`PASS`。新增 `evidence-report-v1` 报告生成边界：从 Task03 已校验矩阵构造 Claim/Evidence/Cell 的 canonical JSON、numeric citation manifest、Markdown 与安全 HTML；证据缺口、未决 Claim、catalog-only 或不可用 Evidence 自动降级为 `partial`。报告以 task/version 唯一键写入新的只读 `research_reports` 投影，重复版本通过数据库约束拒绝覆盖；生成/渲染失败发生在持久化前，不发布半份报告。新增 JSON/Markdown/HTML 版本导出端点，所有格式从同一 canonical JSON 读取并附带下载头、安全响应头。

## 改动文件

- `backend/app/research/application/report_generation.py`
- `backend/app/research/application/report_synthesis.py`
- `backend/app/research/application/research_service.py`
- `backend/app/research/application/entry.py`
- `backend/app/research/domain/models.py`
- `backend/app/research/infrastructure/research_store.py`
- `backend/app/api/routes_research.py`
- `tests/test_spec030_report_generation.py`

## 测试命令/退出码/结果

- `.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py` — 退出码 `0`，`4 passed`。
- `.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py tests/test_spec030_matrix.py tests/test_spec030_contract.py tests/test_spec029_fulltext_evidence.py tests/test_spec029_reuse_gate.py tests/test_spec027_runtime_contract.py tests/test_spec034_task08_backend.py` — 退出码 `0`，`86 passed`。
- `.venv/bin/python -m pytest -q tests/test_spec030_report_generation.py tests/test_spec034_task08_backend.py tests/test_spec027_backend_research_slice.py` — 退出码 `0`，`89 passed, 5 subtests passed`。
- `python -m py_compile backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py backend/app/research/application/research_service.py backend/app/research/application/entry.py backend/app/api/routes_research.py` — 退出码 `0`。
- `git diff --check` — 退出码 `0`。

## 产物路径

`docs/sdd/plans/030/artifacts/task-04/backend-report.md`

## 决策依据

- 复用既有 `ReportSynthesizer` 的参数化入口和 `render_markdown_html`；renderer 只生成固定 DOM，原始 HTML/URI 不解释，numeric citation 转成 `data-citation-no`。
- Task03 矩阵是唯一事实来源；生成器不检索论文、不读取全文、不重建 locator/embedding，也不复制目录元数据。
- citation 按可用 Evidence 建立 `citation_no → paper_id/evidence_ids/claim_ids` 回查链；不可用 Evidence、missing cell 与 unresolved Claim 不进入 manifest，并进入 `limitations`。
- `research_reports` 使用 `(research_task_id, report_version)` 唯一约束和 INSERT-only 写入，历史版本保留；统一 JSON/Markdown/HTML 读取接口保证三格式来源一致。

## 风险阻塞

- 当前 Spec034 的 `ResearchArtifact`/`ReportDeliveryService` 仍服务既有 agent-run 报告链；Spec030 的无 agent-run 矩阵生成通过独立 `ResearchReport` canonical read model 持久化，后续若要把两条链完全合并，应在 Task06 评审时统一 artifact 事务边界。
- 未运行全量回归、前端验收、真实数据、网络或部署验证（按 Task04 范围）。

## 主 Agent 后续动作

读取本报告并复核 canonical 语义、版本不可覆盖和导出响应头；执行 Task04 后端评审/验收，更新 Task04 状态台账；随后分派 Task05 前端工作台，Task06 再做全量回归、启动与部署验证。

## 开始/结束/总耗时

- 开始：`2026-09-17T02:27+08:00`（约）
- 结束：`2026-09-17T02:35+08:00`
- 总耗时：约 `8 分钟`

## 模型和工具统计

- 模型：Luna high（临时分派）
- 工具：文件读取、`apply_patch`、定向 pytest、`py_compile`、`git diff --check`
- 网络/真实数据：未使用
