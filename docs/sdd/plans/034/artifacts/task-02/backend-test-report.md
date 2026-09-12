# Spec034 Task02 后端验收报告

## 结论

**GO（后端验收通过）**。Task02 合同测试、相关后端回归、目标文件编译检查和隔离临时数据库运行时探针均通过。

唯一保留项是目标文件集中的 14 个既有 Ruff 诊断（P2，不在本次新增 hunk，且已有 backend-review 明确不阻塞）；本轮未修改业务代码、测试代码或 Spec。

## 验收范围

- ResearchStore schema v2 初始化/重复迁移、Session/Task/WorkItem/AgentRun owner 绑定与 fail-closed。
- ProcessingStep v2 additive projection、同 kind sibling、父链深度/幂等。
- Notification `(owner_id, idempotency_key)` 完整业务身份幂等及 event sequence 边界。
- ResearchStore 与 MemoryRepository canonical `research-event:{task}:{seq}` replay、parent-first 排序与 retry seam。

## 命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task02_contract.py` | 0 | **12 passed**（0.35s） |
| `.venv/bin/python -m pytest -q tests/test_spec034_task02_contract.py tests/test_memory_repositories.py tests/test_memory_analysis_repair.py tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py` | 0 | **146 passed，5 subtests passed**（4.66s） |
| `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task02_contract.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_research.py tests/test_spec034_task02_contract.py --output-format concise` | 1 | 14 个既有诊断；均在 `backend/app/memory/repository.py` 既有行，未在本次新增 hunk |

## 运行时探针

命令：

```bash
TMPDIR=/private/tmp .venv/bin/python - <<'PY'
# 使用 tempfile.TemporaryDirectory 创建 research.sqlite3/memory.sqlite3，
# 执行下列断言后输出 PASS 行
PY
```

退出码：**0**。

通过断言：

1. Session 创建缺少既有 `MemoryRepository` 时 fail-closed；跨 owner 读取不可见。
2. 未批准 Session 的 worker Run 被拒绝；绑定后 owner 不匹配、未知 WorkItem 均被拒绝；正确 Task/WorkItem 绑定成功。
3. 同一 parent 下两个 `kind=tool` 的 v2 sibling 成功写入且 `step_id` 不同。
4. 同 owner/idempotency key 的完全相同通知请求（payload JSON 空白差异、event_seq 不同）返回原记录；kind 变化返回 `NOTIFICATION_IDEMPOTENCY_CONFLICT`。
5. ResearchStore 与 MemoryRepository replay 均按 parent-first/event_seq 排序；非 canonical source ID 被拒绝。

说明：探针首轮曾因断言顺序先于 session Task 绑定而错误期待 WorkItem 错误；调整探针顺序后重跑退出码 0，属于测试夹具问题，不是实现失败。

## 阻塞与遗留

- **无 P0/P1 阻塞**。
- P2：Ruff 14 个既有诊断（`C420`、`E731`、`C405`、`SIM118`），位置集中于 `backend/app/memory/repository.py:661,676,696,710,1044-1048`。与 backend-report/backend-review 的基线结论一致，本 Task02 不处理无关 lint 技术债。
- 未运行全量 pytest；遵循 Task02 单端定向验收范围。

## 进展日志

`.codebuddy/agent-logs/spec-034/task-02/backend-tester/20260913-000001.md`
