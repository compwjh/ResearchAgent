# Spec032 Task06 统一来源合同交接

## 结果

- 状态：`GO_FOR_TASK07`
- 合同版本：`source-contract-v1`
- 范围：七个来源（`usenix`、`dblp`、`ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref`）
- 官网目录优先抓取、真实同步和 Worker Skill 仍留在 Task07–09。

## 固定字段与状态

`SourceResult` 统一包含 `schema_version`、`source_id`、`operation`、`status`、`scope`、`coverage`、`papers`、`error`、`artifact_handles`、`elapsed_ms`。来源失败使用稳定 `code/retryable/message`，不持久化异常 repr。

`ImportResult` 统一包含 `candidate_id`、`status`、`document_id`、`identity_verdict`、`attempts`、`error`、`artifact_handles`、`elapsed_ms`。`completed` 必须有 `document_id` 且不能同时带错误；`waiting/partial/failed` 可保留恢复信息。

## 来源 ID 与权威

- 规范 ID：`usenix`、`dblp`、`ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref`。
- 旧别名：`ieee-sp → ieee_sp`、`acm-ccs/acm_ccs → ccs`；旧 SQLite 行迁移时保留记录。
- authority 数值越小越权威：官方会议目录 10、官方 DOI 元数据 20、聚合书目 30。
- 当前三会议 Adapter 使用 Crossref DOI 元数据，直到 Task07 接入官网页面，不得冒充官方目录。

## 验证

主 Agent 复跑：

```text
.venv/bin/python -m pytest tests/test_spec032_task06_contract.py tests/test_spec032_ieee_sp_source.py tests/test_spec032_ccs_source.py tests/test_spec032_ndss_source.py tests/test_spec032_aggregate_sources.py tests/test_spec032_usenix_abstract_backfill.py tests/test_paper_discovery_store.py -q
206 passed in 0.90s，退出码 0
```

静态验证：ruff 退出码 0；compileall 退出码 0；`git diff --check` 退出码 0。

## 改动文件

- `backend/app/paper_discovery/domain/source_authority.py`
- `backend/app/paper_discovery/domain/source_contract.py`
- `backend/app/paper_discovery/infrastructure/aggregate_source_adapters.py`
- `backend/app/paper_discovery/infrastructure/source_registry.py`
- `backend/app/paper_discovery/infrastructure/paper_discovery_store.py`
- 五个 `*_publication_source.py` 统一薄包装
- `tests/test_spec032_task06_contract.py` 及三会议 authority 回归断言

## 剩余风险与下一步

- `POST /sync` 的真实执行、官方目录年度覆盖、来源 Worker Skill 和 UI 尚未接通。
- DBLP/USENIX 保留既有 typed search 流程，统一结果包装通过显式 `result()` 接入。
- Task07 应先以固定官方页面样本补齐 IEEE S&P、ACM CCS、NDSS，并保持字段 provenance 与 PDF 延迟验证边界。
