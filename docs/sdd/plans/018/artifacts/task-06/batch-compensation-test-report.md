# Spec018 Task06：批量补偿独立后端验收报告

## 结论

**批量补偿隔离验收：PASS；Task06 总体：NO-GO。**

批次状态、SQLite 快照恢复、attempt owner/token 隔离、失败/取消/过期后的
`cleanup_pending`、补偿后重试以及 completed 防重跑均有测试覆盖。新增的真实
`KnowledgeBasePaperImportAdapter` 隔离集成样本也通过，且默认 composition root
能够绑定同一个 KB port 的 compensator。

Task06 不能整体签收的原因不是本轮批量测试失败：浏览器边界测试文件尚未存在，
闭环矩阵的 inventory hash 尚未由最终 diff 重算，且矩阵仍将若干导入/浏览器/生成
绑定项标为 pending。此前独立评审指出的真实生产补偿闭环与 browser/generation
binding 仍需由主 Agent 完成；本报告不替代最终验收签字。

## 测试范围与限制

- 只使用 pytest 临时目录、内存/临时 SQLite 和假的下载器/索引器。
- 未启动服务，未访问网络，未写入真实论文目录、Qdrant 或生产数据库。
- 未执行 `confirm-replace`、删除用户文件、提交或修改业务代码。
- 本报告只记录验收；测试期间没有改动业务代码。

## 命令结果

| 矩阵/范围 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| T-IMMUTABLE-CREATE | `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_kb_document_routes.py tests/test_paper_import.py -k 'immutable or dedupe or same_name or concurrent'` | 0 | 15 passed，0.66s |
| T-PAPER-IMPORT | `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py` | 0 | 14 passed，0.38s |
| T-IMPORT-COMPENSATION | `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py -k compensation` | 0 | 1 passed，13 deselected，0.35s |
| Batch integration + store/service/API | `.venv/bin/python -m pytest -q tests/test_paper_import_batch_integration.py tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | 0 | 32 passed，1.33s |
| KB/import 回归 | `.venv/bin/python -m pytest -q tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_kb_rebuild_cli.py tests/test_paper_import.py tests/test_import_compensation.py tests/test_paper_import_batch.py tests/test_paper_import_batch_integration.py` | 0 | 71 passed，0.82s |
| 代码质量 | `.venv/bin/ruff check backend/app/api/common.py backend/app/api/routes_paper.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/domain/paper_import_batch.py backend/app/paper_discovery/infrastructure/paper_import_batch_store.py tests/test_paper_import_batch.py tests/test_paper_import_batch_integration.py` | 0 | All checks passed |
| 语法 | `.venv/bin/python -m py_compile backend/app/api/common.py backend/app/api/routes_paper.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/domain/paper_import_batch.py backend/app/paper_discovery/infrastructure/paper_import_batch_store.py tests/test_paper_import_batch.py tests/test_paper_import_batch_integration.py` | 0 | 通过 |
| T-BROWSER-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_import_batch.py -k 'login or resume'` | 4 | **阻塞**：`tests/test_paper_browser.py` 不存在，未执行测试 |
| T-BACKGROUND-INVENTORY | `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py -k inventory` | 1 | **阻塞**：`routes_paper.py` 当前 SHA-256 与矩阵记录不一致，需最终 diff 后重算 inventory |

## 关键验收点

### 已通过

1. 批次为每次 attempt 保存独立 owner/token，lease owner 不复用为资源凭证；
   `PaperImportItem.to_dict()` 和 HTTP 批次 payload 不包含 token、capability、
   inode 或 lease owner。
2. candidate snapshot 以 canonical JSON + SHA-256 写入 SQLite，重启后可以恢复；
   篡改 snapshot 会稳定返回 `SNAPSHOT_REBUILD_REQUIRED`。
3. 索引失败后保存 capability 和 `cleanup_pending`，retry 先经过同 owner/token
   补偿，再重新导入；completed item 不会再次执行。
4. cancel 和 expired lease 保持 fail-closed 的 `cleanup_pending`，不会把未知结果
   猜测成成功。
5. 隔离集成测试验证真实 KB port compensator 的绑定和失败后重试；没有接触生产
   目录或 Qdrant。
6. 批量存储、服务、API、单篇导入以及核心知识库边界回归均通过。

### 未覆盖/仍阻塞

- `tests/test_paper_browser.py` 尚未创建，因此 login/resume 的 browser boundary
  尚未验收。
- 矩阵 inventory hash 是前一轮冻结值，当前 `routes_paper.py` 已改变；不能将
  T-BACKGROUND-INVENTORY 视为通过，需所有实现合并后重新生成 hash/digest。
- 真实 production composition 下的完整 source/metadata/vector 部分失败、
  owner/token mismatch 和 generation-bound collection 拓扑仍需最终隔离验收。
- schema 版本演进、cancel 只更新当前 attempt、内存 snapshot stale 风险是评审
  已指出的后续项，本轮只确认现有 contract tests 通过。

## 与矩阵的映射

- T-IMMUTABLE-CREATE：本轮命令通过；最终 evidence 仍需在矩阵更新后写入。
- T-PAPER-IMPORT：批量/单篇目标命令通过；真实 browser resume 仍受 T-BROWSER-BOUNDARY
  阻塞。
- T-IMPORT-COMPENSATION：最小 `-k compensation` 命令通过，集成样本通过；不能
  代替尚未完成的 browser/generation/全量真实补偿门禁。
- T-BROWSER-BOUNDARY：blocked（测试文件缺失）。
- T-BACKGROUND-INVENTORY：blocked（冻结 hash 过期）。

## 主 Agent 后续动作

1. 完成 browser boundary 测试与实现评审，再运行矩阵 exact command。
2. 在最终代码稳定后更新 `inventory_files`、`inventory_digest` 和证据路径，重新
   运行 inventory 检查。
3. 补完 generation-bound compensation 和真实 adapter 的 owner/token mismatch
   隔离场景后，重新做独立 reviewer/tester 验收。
4. 在全部矩阵项关闭前保持 Task06 和生产切换为 NO-GO。

## 运行记录

- 执行角色：独立 backend-tester。
- 模型：Luna high（仅本次任务）。
- 报告文件：`docs/sdd/plans/018/artifacts/task-06/batch-compensation-test-report.md`。
