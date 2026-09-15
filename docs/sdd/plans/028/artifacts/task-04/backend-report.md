# Spec028 Task04 后端交接报告

## 状态

**已完成（Task04 后端实现与定向验证通过）**

## 实现范围

- `backend/app/research/domain/contracts.py`
  - 在既有 ResearchTask 状态机中加入 `paused`，允许 active → paused → running/cancelled；终态仍不可重开。
- `backend/app/research/infrastructure/research_store.py`
  - 新增 `update_task_status_cas`、`pause_task_cas`、`resume_task_cas` 和 `cancel_task_cas`；取消操作在单一 SQLite 写事务中同时收敛 queued/running WorkItem。
  - 新增 `create_plan_version_cas` 与 `create_session_plan_cas`，计划行和当前版本指针原子追加，旧版本回调返回 CAS 失败且不可覆盖历史。
  - Approval 相同幂等身份返回原记录；复用同一幂等键绑定不同审批身份时拒绝。
- `backend/app/research/application/research_service.py`
  - 接入 pause/resume/cancel CAS；暂停事件不会丢弃已完成证据或 queued 节点，恢复可校验可选 scheduler checkpoint。
  - 补充范围改为原子追加新 ResearchPlan 版本，旧版本竞态稳定返回 `PLAN_VERSION_STALE`。
- `backend/app/research/application/orchestrator.py`
  - 编排入口、阶段刷新和节点派发边界识别 paused；暂停后不派发新节点，恢复继续复用现有编排器。
- `backend/app/research/application/scheduler.py`
  - 暴露 `save_checkpoint` / `get_checkpoint` / `advance_from_checkpoint`（及兼容别名），持久化实现仍唯一归 ResearchStore。
- `backend/app/api/routes_research.py`
  - 接线 `POST /api/research-tasks/{id}/pause` 与 `POST /api/research-tasks/{id}/resume`，resume 支持可选 checkpoint envelope。
- `tests/test_spec028_hitl.py`
  - 覆盖 pause/cancel 单赢家 CAS、计划版本不可覆盖、ResearchService pause/resume、scheduler checkpoint 版本与摘要 CAS。

## 验证

```text
.venv/bin/python -m pytest --noconftest -q \
  tests/test_spec028_hitl.py \
  tests/test_spec034_task04_contract.py \
  tests/test_spec028_scheduler_lease_recovery.py \
  tests/test_spec028_runtime_contract.py
```

结果：退出码 `0`，`28 passed`。

```text
.venv/bin/python -m pytest --noconftest -q \
  tests/test_spec027_backend_research_slice.py \
  tests/test_spec034_task07_backend.py
```

结果：退出码 `0`，`66 passed, 5 subtests passed`。

```text
.venv/bin/python -m py_compile \
  backend/app/research/domain/contracts.py \
  backend/app/research/domain/state_machine.py \
  backend/app/research/infrastructure/research_store.py \
  backend/app/research/application/research_service.py \
  backend/app/research/application/approval_service.py \
  backend/app/research/application/scheduler.py \
  backend/app/research/application/orchestrator.py \
  backend/app/api/routes_research.py
git diff --check
```

结果：退出码 `0`。

## 边界与后续

- 未创建第二套状态机、Approval 表或 ResearchTask/Plan schema；所有状态转移继续经过既有 domain state machine 与 ResearchStore。
- 未运行全量回归，未执行部署，未 commit/push；Task06 需继续进行最终评审、全量回归与运行时验证。
