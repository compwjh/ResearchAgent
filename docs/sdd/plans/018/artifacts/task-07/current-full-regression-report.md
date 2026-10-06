# Spec018 Task07 当前全仓回归报告

## 执行信息

- 时间：2026-10-06
- 执行环境：项目 `.venv`，`pytest-cov 7.1.0`
- 命令：

  ```text
  .venv/bin/python -m pytest tests --cov=backend --cov-report=term --cov-report=json:/private/tmp/researchagent-integration-coverage.json -q
  ```

- 原始日志：`/private/tmp/researchagent-integration-regression.log`
- 覆盖率 JSON：`/private/tmp/researchagent-integration-coverage.json`
- 退出码：`1`
- 总耗时：`257.81s (0:04:17)`

## 结果摘要

- `2872 passed`
- `10 failed`
- `3 skipped`
- `67 subtests passed`
- `5 warnings`
- 总覆盖率：`81.79397010911724%`（报告四舍五入为 `82%`）
- 语句数：`38674`
- 已覆盖：`31633`
- 未覆盖：`7041`
- 覆盖率 JSON 已成功生成；总体覆盖率达到 verification-loop 的 80% 目标，但测试套件未通过，不能签署 PASS。

## 失败分类与精确修复任务

### 1. 来源同步入口缺失保护（1 个失败）

失败：`tests/paper_discovery/test_paper_sources_api.py::test_sync_without_entrypoint_is_409`

证据：测试将 `routes_paper._SOURCE_SYNC_ENTRYPOINTS` 置空后，`POST /api/papers/sources/usenix/sync` 返回 `202`；当前实现只在响应中用 `source_registry.adapter` 兜底，没有在创建 `SearchJob`/进度前拒绝缺失入口。

修复任务：在同步请求的受控入口检查阶段对缺失入口返回 `409 SYNC_ENTRYPOINT_UNAVAILABLE`，并确保该失败路径不创建 job、进度或调度任务；补跑该测试及来源 API 领域测试。

### 2. FinalizeBundleStore 根路径契约不一致（1 个失败）

失败：`tests/research/test_fulltext_evidence.py::test_default_generation_reader_uses_published_finalize_store`

证据：测试期望 `FinalizeBundleStore(evidence_upgrade.KB_DIR.parents[2])`，实际调用记录为 `KB_DIR.parents[1]`。当前 `backend/app/main.py` 也使用 `KB_DIR.parents[1]`，因此这是生产代码、测试和路径契约之间的不一致，不应直接盲改其中一侧。

修复任务：确认 Spec018/FinalizeBundleV1 的 canonical root（包括 `data/kb` 与 `.sdd/runtime/spec-018/rebuild` 的相对位置），统一 `evidence_upgrade`、启动路径和测试；补跑 full-text evidence 与 generation gate 测试。

### 3. Evaluator allowlist 参数名漂移（5 个失败）

失败：

- `test_b_aggregate_without_metadata_but_in_allowlist_still_expands`
- `test_c_aggregate_without_metadata_and_id_not_in_allowlist_is_empty`
- `test_d_non_catalog_refs_are_ignored`
- `test_e_no_allowlist_behaves_identical_to_before`
- `test_allowlist_prefers_allowlist_over_metadata_gap`

证据：上述测试传 `allowed_candidate_ids=`，当前 `_validated_evaluator_candidates` 只接受 `recall_allowlist=`；因此均在调用阶段抛 `TypeError`，尚未执行行为断言。当前生产调用点、回归文档和其他测试均使用 `recall_allowlist`。

修复任务：以已记录的 `recall_allowlist` 作为 canonical 名称，统一这 5 个测试（或在确有兼容性要求时提供明确、非歧义的别名）；随后单独运行 `tests/research/test_validated_evaluator_candidates.py` 与相关 metadata-backfill 测试，确认 fail-closed 行为仍成立。

### 4. Worker discovery 测试 double 不满足持久化契约（1 个失败）

失败：`tests/skills/test_paper_worker_tools.py::test_usenix_and_ieee_use_same_result_validator`

证据：测试 `_Store` 只提供 `list_conferences`；当前 USENIX/DBLP discovery 会调用 `_persist_legacy_candidates`，要求 store 提供 `save_fetch_unit` 及目录持久化能力，异常后结果为 failed，`provenance` 为空。

修复任务：保留 server-owned catalog identity 与持久化门禁，更新测试 double 以实现最小可用的 catalog persistence contract，或改用不需要 legacy persistence 的受控来源 fixture；不得为通过测试而移除持久化要求。

### 5. Worker import 测试 double 缺少目录查找契约（1 个失败）

失败：`tests/skills/test_paper_worker_tools.py::test_worker_preserves_actionable_download_error_and_candidate_id`

证据：测试 `_Store` 没有 `get_catalog_paper` / `get_catalog_source_kinds`，生产代码在到达 monkeypatched `PaperDownloadError` 导入路径之前返回 `CATALOG_UNAVAILABLE`。

修复任务：补齐测试 double 的 server-owned catalog paper/source lookup，使 candidate 通过目录与来源校验后再触发 monkeypatched download error；保留 `CATALOG_UNAVAILABLE` fail-closed 行为和 candidate ID 保留断言。

### 6. API 直接依赖 infrastructure（1 个失败）

失败：`tests/system/test_api_module_boundaries.py::test_api_does_not_import_infrastructure`

证据：`backend/app/api/routes_paper.py:59` 直接导入 `backend.app.paper_discovery.infrastructure.semantic_scholar_metadata`。

修复任务：通过 `backend.app.paper_discovery.application.entry` 提供受控导出，改 API 只从 application entry 导入；重新运行 system boundary 测试，确认没有新增跨上下文 infrastructure 直连。

## 覆盖率不足记录

总体覆盖率为 81.79%，但共有 43 个文件低于 80%，不能将总体数字解读为每个领域均达标。关键低覆盖文件包括：

- `backend/app/api/routes_research.py`：62.17%
- `backend/app/api/routes_kb.py`：71.15%
- `backend/app/api/routes_paper.py`：73.43%
- `backend/app/research/application/orchestrator.py`：72.68%
- `backend/app/research/application/research_service.py`：72.63%
- `backend/app/paper_discovery/application/worker_tool.py`：78.94%
- `backend/app/research/application/evidence_upgrade.py`：79.35%
- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`：79.81%
- `backend/app/platform/settings/settings_repository.py`：46.51%
- `backend/eval_042/consistency.py`：0%
- `backend/eval_042/langfuse_export.py`：30.56%
- `backend/eval_042/memory_probe.py`：28.41%

完整逐文件数据以 `/private/tmp/researchagent-integration-coverage.json` 为准。

## 当前结论与后续门禁

结论：`NOT READY`。本次完整回归真实失败 10 项；未修改代码、测试或运行数据。

主会话另行告知：真实 API 验证发现 `auto_requeued_chunkers` 新增 metadata 与 Spec018 strict schema 漂移，PDF/Markdown 上传返回 400，相关修复正在进行。该运行时阻塞不包含在本次 pytest 统计中，但在修复并通过真实 API E2E 前不得签署 Spec018 PASS。

修复上述失败并完成运行时 schema 修复后，必须重新执行同一完整命令，重新保存日志与 coverage JSON，再更新本报告的最终候选结果。

## 最终候选 9a9733f 重跑（2026-10-06 当前结果）

本节追加记录最终候选，不覆盖上文首次回归的真实 `10 failed` 历史。

- 候选：`HEAD 9a9733f`
- 命令：

  ```text
  .venv/bin/python -m pytest tests --cov=backend --cov-report=term --cov-report=json:/private/tmp/researchagent-integration-final-coverage.json -q
  ```

- 原始日志：`/private/tmp/researchagent-integration-final-regression.log`
- 覆盖率 JSON：`/private/tmp/researchagent-integration-final-coverage.json`
- 退出码：`0`
- 结果：`2893 passed, 3 skipped, 5 warnings, 67 subtests passed`
- 总耗时：`237.14s (0:03:57)`
- 总覆盖率：`81.79139962786851%`（报告四舍五入为 `82%`）
- 语句数：`38696`
- 已覆盖：`31650`
- 未覆盖：`7046`
- 低于 80% 的文件数：`43`

本次最终候选全仓 pytest 回归通过；覆盖率总体超过 80%，但 43 个文件仍低于 80%，不能将总体数字解释为逐文件达标。运行期间另有 OpenTelemetry 向 `127.0.0.1:3000` 导出失败重试/超时日志，不影响 pytest 退出码，但属于环境告警，应在运行时验收中单独记录。

本节只证明当前测试套件与 coverage 结果；真实 API 上传、索引、inspection、真实 Qdrant generation/alias 及前端人工验收仍需依照 Spec018 门禁使用独立证据，不由本次 pytest 代替。
