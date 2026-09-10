# Task 06：cleanup_failed 成功状态错误码清理修复报告

## 结果状态

PASS。修复已完成，未触碰真实论文数据、Qdrant、网络或部署服务。

## 问题

`cleanup_failed` 在上一次 FSM 或动作失败后，即使已经确认候选索引不存在，或删除候选后再次观察确认删除成功，仍可能把旧的 `error_code`（例如 `FSM_INVALID_TRANSITION`）带入 `cleaned` 结果。这会让成功清理被错误显示为失败诊断。

## 修改

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 候选已不存在并通过拓扑安全检查时，先将 `self._state.error_code` 置为 `None`，再迁移到 `cleaned`。
  - 候选删除后新鲜拓扑确认候选已消失且未被别名引用时，先清空 `error_code`，再迁移到 `cleaned`。
  - 失败路径保持原有真实错误码，不做清空。
- `tests/test_kb_candidate_rebuild.py`
  - 为候选已不存在的幂等清理增加 `result["error_code"] is None` 与 `state.json` 为 `null` 的断言。
  - 注入历史 `FSM_INVALID_TRANSITION` 残留，覆盖此前生产症状。
  - 为删除后成功清理增加同样的结果和落盘状态断言。

## 验证

```text
./.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py -q
60 passed, 5 warnings

./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py
PASS

冲突标记扫描（candidate_rebuild.py、test_kb_candidate_rebuild.py）
PASS

git diff --check -- backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py
PASS
```

## 变更范围

仅修改指定的两个代码/测试文件；本报告为 Task 06 运行产物。没有删除、重命名或覆盖真实数据，也没有执行 Qdrant 写操作。

