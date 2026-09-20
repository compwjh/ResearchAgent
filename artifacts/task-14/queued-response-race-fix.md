# Spec032 Task14：批量导入创建响应竞态修复

> 日期：2026-09-21（Asia/Shanghai）
> 范围：Task10 批准计划自动导入 / Task14 收口回归

## 根因

`POST /api/papers/imports` 在持久化批次后立即提交后台 runner，再从数据库读取响应。导入器足够快时，runner 会在 HTTP 响应构造前把条目推进到 `downloading` 或 `completed`，违反“创建接口立即返回 `queued`、客户端随后轮询”的接口合同。

## 修复

`backend/app/api/routes_paper.py` 现在先以 `auto_run=False` 创建批次，读取并冻结 queued 响应快照，再调用既有 `PaperImportBatchService.submit_batch()` 启动后台执行。下载、校验、索引、租约和恢复状态机保持原实现，没有新增旁路导入器。

## 验证

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/ruff check backend/app/api/routes_paper.py tests/paper_discovery/test_paper_import_batch_api.py` | 通过 |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_api.py tests/paper_discovery/test_paper_import_batch_service.py` | `45 passed` |
| `.venv/bin/python -m pytest -q tests/paper_discovery tests/research tests/skills tests/api` | 运行至 `1554 passed` 后因已有后台线程未退出而手动中断；未发现新的测试失败，完整结果不作为收口通过证据 |

## 交接结论

创建响应竞态已修复并提交为 `921bc74`（`fix(spec032): preserve queued import acknowledgement`）。Task14 仍需按既定门禁完成全量回归、真实来源覆盖、受控导入/恢复 smoke、独立评审签字和部署验证，不能因本修复单独标记 Spec032 完成。
