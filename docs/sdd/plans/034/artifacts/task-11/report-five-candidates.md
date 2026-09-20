# Task11 子任务报告：至少五篇候选保留

## 执行时间

- 开始：2026-09-16 02:47:00 CST
- 结束：2026-09-16 02:57:42 CST

## 结论

已完成最小后端实现。候选池本身不少于 5 篇时：

1. `Orchestrator._evaluate_papers` 不再因过低的 `target_paper_count` 截断到 5 篇以下，而是在既有 `max_selected=20` 硬上限内保留至少 5 篇。
2. `PaperEvaluator` 在阈值/软阈值后不足 5 篇时，从已提供的 catalog 快照按相关度分数、再按输入顺序稳定补足到 5 篇；每个补足项仍只使用原快照的 `catalog:<candidate_id>` 引用，并在 reason/diagnostics 中显式标记。
3. 候选池少于 5 篇时不填充、不伪造数量；没有新增下载、导入、网络或 PDF 路径。

## 改动文件

- `backend/app/research/application/orchestrator.py`
  - 新增最小报告候选下限常量。
  - 调整确定性选集容量并更新规则说明。
- `backend/app/research/application/search_catalog_adapter.py`
  - `PaperEvaluator` 增加 catalog-backed 五篇下限和可审计诊断字段。
- `tests/test_spec034_task06_contract.py`
  - 覆盖严格阈值下的五篇保留、引用绑定、reason/diagnostics，以及低目标数量的编排器选集下限。

## 验证

- `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py tests/test_spec027_backend_research_slice.py`
  - 退出码 0；`71 passed, 5 subtests passed`。
- `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task08_backend.py tests/test_spec034_task10_backend.py`
  - 退出码 0；`84 passed`。
- 后续在父任务并发加入目录元数据后，重新执行受影响后端集合（Task05/06/08 + Spec027）：退出码 0；`123 passed, 5 subtests passed`。
  单独复跑 Task10 元数据合同时，已有并发改动中的 `_catalog_evidence_view` summary 脱敏合同仍失败（URL 出现在 summary）；该失败不触及本次五篇下限代码，已报告给主 Agent。
- `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py backend/app/research/application/search_catalog_adapter.py`
  - 退出码 0。

## 风险与边界

- 五篇下限只作用于已有 catalog 候选/快照，不会把缺失快照、任意模型输出或论文全文当作证据；若实际候选少于 5 篇，仍保留真实数量。
- Agent Runner 的模型输出仍受既有候选、引用白名单和 fail-closed 报告校验约束；本子任务仅在至少五条已脱敏 catalog 元数据可用时，使用同一确定性评估器补足下游验证候选，未放宽无证据时的失败门禁，也未改报告正文内容字段。
- 工作树中已有的 Spec034 文档改动属于上游任务，本子任务未修改、未提交、未 push。
