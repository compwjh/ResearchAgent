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

## 重启后运行时检查（2026-09-21）

- `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh`：启动成功，Uvicorn PID `58295`。
- `GET /api/health`：HTTP `200`，`paper_discovery_enabled=true`。
- `GET /api/ready`：HTTP `200`，jieba、Ollama、embedding、Qdrant 均为 `ready`。
- `GET /api/papers/sources`：HTTP `200`，7 个受控来源可读；USENIX 已验证 2022–2026，IEEE S&P/NDSS 当前仅验证 2024，CCS 仍未验证，未把参数范围冒充覆盖证明。

## 定向 Spec032 回归（2026-09-21）

- 来源、目录、导入、研究 Worker、Skill、问题队列和前端研究契约集合：`556 passed, 5 warnings`，退出码 `0`。
- 该集合覆盖本轮竞态修复的批量导入 API；完整 Spec 收口仍按 Task14 单独执行，不把定向回归数字当作全量通过。
- 受控缓存 smoke：`POST /api/papers/sources/usenix/sync`（2024）返回 `202/queued`，同步句柄 `sync-usenix-0395990926f8495b` 随后稳定进入 `completed`；两个 2024 官方页面单元均出现在 `cached_units` 与 `completed_units`，`paper_count=227`，未触发 PDF 下载。
