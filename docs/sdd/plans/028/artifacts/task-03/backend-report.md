# Spec028 Task03 后端交接报告

## 状态

**已完成（Task03 后端实现与定向验证通过）**

## 实现范围

- `backend/app/research/domain/models.py`
  - 新增不可变 `SchedulerLease`、`SchedulerCheckpoint`、`ResourceReservation` 读模型。
- `backend/app/research/infrastructure/research_store.py`
  - 增加惰性、幂等的 `scheduler_leases`、`scheduler_checkpoints`、`resource_reservations` 表及索引；惰性迁移保持 Task02 固定 probe 表兼容。
  - `claim_scheduler_lease` / `heartbeat_scheduler_lease` / `release_scheduler_lease` / `recover_expired_scheduler_leases` 使用 `BEGIN IMMEDIATE` 与 owner token/expiry CAS，支持跨进程唯一领取、过期接管和旧 owner 拒绝。
  - `claim_work_item` 在同一 SQLite 写事务中复用既有 `transition_workitem`，原子完成 queued→running 与 WorkItem lease claim。
  - `save_scheduler_checkpoint` / `get_scheduler_checkpoint` 校验 JSON SHA-256 摘要；`advance_work_item_from_checkpoint` 仅在 plan version、node id、digest 与可选 lease 均匹配时推进。
  - `reserve_resources` / `release_resource_reservation` / `list_resource_reservations` / `recover_expired_resource_reservations` 实现带过期时间的容量预约与释放。
  - 保留旧式简短别名（`claim_lease`、`heartbeat_lease`、`save_checkpoint`、`reserve_resource` 等），避免调用方迁移破坏兼容性。
- `backend/app/research/application/scheduler.py`
  - 新增 `ResearchScheduler`（别名 `SchedulerService`、`GlobalResearchScheduler`），按任务轮转选择依赖就绪的 queued WorkItem。
  - 默认构造时执行一次有界 durable lease/reservation recovery（可用 `recover_on_start=False` 关闭）。
  - 复用现有 `ResourceProbe`/`_GlobalWorkerScheduler`，将 durable reservation 与 fast Worker grant 配对；finish/recover 路径释放租约和预约。
- `tests/test_spec028_scheduler_lease_recovery.py`
  - 覆盖 token CAS、并发唯一领取、checkpoint 摘要与版本校验、任务轮转、公平预约和释放。

## 验证

```text
python -m pytest --noconftest -q tests/test_spec028_scheduler_lease_recovery.py tests/test_spec028_runtime_contract.py
```

结果：退出码 `0`，`9 passed, 1 skipped`。唯一跳过项仍是 Task02 已记录的可选 `langchain_ollama` 缺失探针。

```text
python -m py_compile backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py backend/app/research/application/scheduler.py
git diff --check
```

结果：退出码 `0`。

## 边界与后续

- 资源预约记录以 `worker_id` 为活动唯一占用者；过期记录在新预约或显式 recovery 时释放。
- 调度器不新增任务状态机或下载/来源实现；`ResearchStore` 与既有 domain state machine 仍是唯一状态写入口。
- Task04 可在此基础上接入 pause/cancel/approval 与计划版本；本 Task 未改 API 路由，也未运行全量回归、未 commit/push。
