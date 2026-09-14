# Spec034 Task10：WorkItem 依赖物化修复交接

## 结论

已修复计划批准时的 WorkItem 依赖命名空间错误。公开计划继续使用短 ID（如 `s1`、`e1`），但激活写入 `research_work_items` 时，依赖会与 WorkItem 主键统一物化为 `<research_task_id>:<short_id>`。因此 Orchestrator 在 Search Worker 完成后能够正确解析下游依赖并继续调度。

## 改动

- `backend/app/research/application/approval_service.py`
  - `_activate_task` 先建立计划短 ID 到任务作用域完整 ID 的映射。
  - `depends_on_json` 持久化前按该映射归一化；不改变会话计划中展示的短 ID。
- `tests/test_spec034_task10_backend.py`
  - 新增依赖前缀回归测试。
  - 验证相同幂等键重复批准只返回原决策，且 WorkItem 数量不重复。

## 验证

- 定向测试：`.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py` —— 通过。
- 语法检查：`.venv/bin/python -m py_compile backend/app/research/application/approval_service.py tests/test_spec034_task10_backend.py` —— 通过。
- Diff 检查：确认改动仅涉及 `backend/**`、`tests/test_spec034_task10_backend.py` 与本交接文档；未执行 reset、stash、clean、commit 或 push。

## 风险与边界

仓储 `activate_plan` 原有事务和幂等逻辑未改变；本修复仅改变新激活 WorkItem 的依赖持久化值。已存在的错误依赖数据不会被隐式迁移，需按任务重试/重新激活流程处理。
