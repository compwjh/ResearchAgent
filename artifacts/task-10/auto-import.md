# Spec032 Task10：批准计划内自动导入交接

## 范围与实现

本 Task 只改动 Research acquisition/orchestration 接缝与固定样本测试：

- `backend/app/research/application/acquisition.py`
  - 新增 `ApprovedPlanAutoImporter`，复用 `ResearchAcquisitionService.confirm()` 和既有 `PaperImportBatchService`。
  - 只读取服务端冻结的 `research_paper_selections`；`target_paper_count` 是自动导入上限。
  - 使用 `selection_version + plan_version + 选中 ID 摘要` 生成稳定幂等键；重复运行回到同一批准/批次。
  - 复用 `source_search_id` 分组和既有 durable candidate snapshot；状态读取时触发已有恢复/单飞批次提交。
  - 身份 `mismatch/wrong/invalid` 明确拒绝；`uncertain/unknown/pending` 留在 `waiting_identity`，写入 `ResearchDocumentLink` 与 `AcquisitionEvent`，不阻断其他候选。
- `backend/app/research/application/orchestrator.py`
  - 只在 `review_plan_first=true` 且存在 Spec034 `plan=approved` 或旧路径 `reason=plan_approved` 事件时调用自动导入。
  - 普通目录搜索和未批准/取消任务不进入该接缝；搜索 Worker 的 PDF 禁止边界保持不变。
  - 确定性搜索路径将真实 Worker 输出中的 `search_id` 写入 selection，禁止猜测任务级句柄。
- `tests/test_spec032_task10_auto_import.py`
  - 固定 fake 样本覆盖批准预算、未批准/普通搜索零调用、取消覆盖旧批准、错链 fail-closed 且同批其他候选继续、跨搜索快照分组、队列恢复单飞。

未新建下载器、PDF parser、KB collection、报告合成器或普通 CatalogSearchGraph 下载路径。

## 固定样本与状态流

1. `approved_plan=true` + selection snapshot → 取前 `target_paper_count` → `confirm()` → 既有 batch `queued/running/...`。
2. `approved_plan=false` → `PLAN_NOT_APPROVED`，不会调用 batch/import/download。
3. 明确身份 mismatch → `IDENTITY_MISMATCH`；身份无法核验 → `IDENTITY_UNCERTAIN`；二者均为 `waiting_identity`，其余候选继续进入既有 batch。
4. `waiting_login`、超时、无 PDF 等由既有 batch/import 状态机保留并可重试；本 Task 不把单项失败提升为全批失败。
5. 进程重启后的 batch status 读取复用 durable snapshot 和既有 `maybe_recover_batch/submit_batch` 单飞入口；不新增 KB 文件写入逻辑。

## 验证记录

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_spec032_task10_auto_import.py tests/test_spec029_acquisition_bridge.py tests/test_spec029_search_id_bridge.py` | 15 passed，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch_service.py tests/test_paper_import_identity.py tests/test_spec032_conference_pdf_download.py tests/test_spec029_acquisition_bridge.py tests/test_spec029_search_id_bridge.py tests/test_spec032_task06_contract.py` | 110 passed，退出码 0 |
| `python -m py_compile backend/app/research/application/acquisition.py backend/app/research/application/orchestrator.py backend/app/research/application/agent_runtime.py` | 通过，退出码 0 |
| `.venv/bin/ruff check backend/app/research/application/acquisition.py` | 通过，退出码 0 |
| `git diff --check -- backend/app/research/application/acquisition.py backend/app/research/application/orchestrator.py` | 通过，退出码 0 |

## 风险与主 Agent 下一步

- PDF 内容级标题/DOI 身份核验仍依赖既有安全导入/下载链提供的服务端快照；Task10 facade 对显式 mismatch/uncertain fail-closed，但不自行解析 PDF 字节。
- 自动导入接缝只接受 `review_plan_first=true` 的持久批准证据；任务进入 `cancelled`/`canceled` 后，旧批准也不会重新触发批次。
- 生产默认装配通过 Orchestrator 的惰性 provider 接缝取得已有 batch service；主 Agent 应复查当前工作树中其它 Spec 对 `Orchestrator` 构造参数、Task 状态事件和 provider override 的兼容性。
- 建议主 Agent 继续运行受影响的 batch/import、安全与身份测试，并确认普通搜索实际无 PDF 请求后再收口 Spec 状态。

执行结果：Task10 后端接线与固定样本完成，待主 Agent 集成评审。
