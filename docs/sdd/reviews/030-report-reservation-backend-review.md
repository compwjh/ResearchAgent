# Spec 030 Task 08 后端评审：报告版本预留

- 评审者：`/root/report_reservation_review`
- 角色：Backend Reviewer
- 模型：Luna xhigh（本次指定）
- 评审范围：仅 `backend/app/research/infrastructure/research_store.py` 相对 `a702a070` 的 reservation 改动，以及 `tests/research/test_report_version_reservation.py`；按 Task 08 预留计划与报告质量合同核对。未评审并行质量实现。

## 结论：通过（PASS）

未发现本切片中可信度超过 80% 的缺陷。版本最大值（ResearchReport 与 ResearchArtifact）读取、request-key 查找、WorkItem 绑定和 generating 报告插入在同一 `BEGIN IMMEDIATE` 事务内；同 key 的历史 reservation 在 active-generation 冲突检查前读取，payload/plan 不匹配会返回类型化冲突。Owner 查询受 task owner 约束。只复用当前 plan 下未绑定的 queued synthesizer；running、已绑定和终态 WorkItem 不被改写，必要时创建同类型 queued row。ResearchTask 状态不随 reservation 改动。

持久化失败路径会回滚 report 和 WorkItem 的绑定/插入；同 key 并发返回同一 reservation，不同 key 竞争只允许一个版本。终态 reservation 查询与重放保留既有 report/version/WorkItem 身份。

## 验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_version_reservation.py`：退出码 0；17 passed（0.43s）。默认仓库 fixture 正常加载。
- `git diff --check a702a070 -- backend/app/research/infrastructure/research_store.py`：退出码 0；无补丁格式问题。

## Task 08 集成签字

**Backend Reviewer：PASS（仅报告 reservation 存储切片）。** 集成时须保留 canonical report JSON 的 `generation.request_key/work_item_id/report_version` 与 WorkItem input 的 `report_generation` 绑定；本评审不覆盖其他后端模块、端到端运行或 Task 08 整体验收，也不表示报告质量缺陷已修复。
