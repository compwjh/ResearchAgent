# Task11 issue recovery handoff

## 实现状态

已完成后端最小闭环；前端不在本任务范围。具体候选的失败由候选稳定 ID 聚合为一个持久待处理项，跨 Research task 保留 `task_ids` 与尝试历史。

```text
queued/running
      |
      +--> waiting_login --login--> headed session --resume--> running
      |                                      |
      |                                      +--> session expired -> waiting_login
      +--> failed --------retry--------------> queued/running
      |
      +--> upload (identity confirmed only) -> KB indexed -> completed/resolved
```

`waiting_login` 的 actions 为 `login/resume/upload`，不会暴露 `retry`；`failed` 的 actions 为 `retry/upload`。明确身份冲突的上传在 KB 写入前被拒绝；身份不确定必须带人工确认，确认记录落入 `ManualResolution`，不保存密码或 Cookie。

## 持久模型与复用边界

- `ResearchStore` 加性创建 `research_acquisition_issues` 与 `research_manual_resolutions`，不复制 PaperImportBatch 或 PDF 文件库。
- `ResearchAcquisitionService._sync()` 继续只读取既有 `PaperImportBatchService` 状态，并投影 `ResearchDocumentLink` / `AcquisitionEvent`；失败与等待登录同时写入 issue。
- 登录、继续、重试端点分别调用现有 `/api/papers/import-items/{item_id}/login|resume|retry`；等待登录不会误走 retry。
- issue 上传端点调用既有 `/api/kb/documents/upload`，复用 MIME/大小/PDF magic-header/不可变源/索引检查；成功后按所有关联 task 更新 `ResearchDocumentLink`，保存人工确认并返回 `report_action=generate_new_version`。既有报告不更新，后续报告生成仍走 Spec030 的 `next_report_version`/不可变表。

## 端点样例

```text
GET  /api/papers/issues?task_id=<task>&status=open
POST /api/papers/issues/<issue_id>/login
POST /api/papers/issues/<issue_id>/resume
POST /api/papers/issues/<issue_id>/retry
POST /api/papers/issues/<issue_id>/upload?identity_verdict=confirmed
```

列表项至少包含 `issue_id/candidate_id/task_ids/reason_code/status/attempts/actions/resolution`；同一个候选跨两个 task 只返回一行。

## 身份判定

`mismatch/wrong/invalid/rejected` 直接返回 `400 IDENTITY_MISMATCH`；`uncertain/unknown/pending` 无 `identity_confirmed=true` 时返回 `409 IDENTITY_CONFIRMATION_REQUIRED`。确认上传后保存 `method=upload`、文档句柄、判定与文件摘要证据；不能确认的文件不会绑定任何 Research task。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec032_task11_issue_recovery.py` | 0 | 7 passed |
| `.venv/bin/python -m pytest -q tests/test_spec029_acquisition_bridge.py tests/test_spec029_reuse_gate.py tests/test_spec032_task10_auto_import.py tests/test_paper_import_batch_api.py` | 0 | 35 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_kb_document_routes.py` | 0 | 64 passed, 12 subtests passed |
| `.venv/bin/ruff check backend/app/api/routes_paper.py backend/app/research/application/acquisition.py backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py tests/test_spec032_task11_issue_recovery.py` | 0 | All checks passed |
| `.venv/bin/python -m compileall -q backend` | 0 | passed |
| `git diff --check` | 0 | passed |

## 改动文件

- `backend/app/research/domain/models.py`
- `backend/app/research/infrastructure/research_store.py`
- `backend/app/research/application/acquisition.py`
- `backend/app/research/application/entry.py`
- `backend/app/api/routes_paper.py`
- `tests/test_spec032_task11_issue_recovery.py`

## 风险与阻塞

- 本任务未做真实 ACM/IEEE headed-browser 或远程上传 smoke；仅验证离线持久化、既有 batch API、KB 路由和定向 Research 投影。
- 上传成功后报告不会自动生成（符合旧报告不可变边界），调用方需按 `report_action` 续跑受影响步骤并生成新版本。
- 工作树中存在其他 Agent 未提交修改；未执行 reset/stash/clean/checkout，也未覆盖无关文件。

## Recovery bridge follow-up（2026-09-20）

- 修正候选 issue 的 action 投影：动作跟随最新 `waiting_login` / `failed` 状态，历史动作仍保留在 `attempts`，避免失败条目继续暴露登录动作。
- 修正 `resolved_at` 持久化，并让 `resume` 人工操作在 `ManualResolution.method` 中保持原语义；已解决 issue 禁止重复上传。
- 定向测试扩展为 7 个用例，覆盖 issue route 的 login/resume/retry 复用、`waiting_login` 禁止 retry 和 resolved 上传保护。
