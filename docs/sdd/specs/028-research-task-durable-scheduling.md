# Spec 028 — Research Task 可靠调度、计划版本与恢复

## 状态

**当前状态：实施中（Task05）**

## 一句话目标

让 Spec027 的 Research Task 在多任务竞争、暂停、批准、取消、服务重启和 Worker 中断后仍能保持唯一执行权、可恢复计划和真实终态。

## 背景与依赖

- Spec027 只保证页面刷新/SSE 重连恢复；服务崩溃时任务收敛为 interrupted。
- 长时科研任务必须跨页面和进程生命周期运行，不能依赖进程内 Future 或队列。
- 本 Spec 依赖 Spec027 已完成的数据模型和受控 WorkItem，不扩大论文来源或全文能力。

## 数据模型

| 实体/字段 | 类型 | 约束 |
|---|---|---|
| SchedulerLease | task_id、owner_token、expires_at、heartbeat_at | 同一 WorkItem 同时最多一个有效租约 |
| SchedulerCheckpoint | task_id、plan_version、node_id、state_json、input_digest | checkpoint 先落盘再推进节点 |
| ApprovalRequest | approval_id、type、payload、status、expires_at | pending / approved / rejected / expired |
| PlanMutation | from_version、to_version、added/cancelled/replaced ids、reason | 只能修改未执行节点 |
| ResourceReservation | worker_id、model_tier、estimated_bytes、expires_at | 由全局调度器统一持有 |

## 状态与接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| POST /api/research-tasks/{id}/pause | 空 | paused 或 pause_pending | 409 终态 |
| POST /api/research-tasks/{id}/resume | 可选 checkpoint | queued/running | 409 无可恢复点 |
| POST /api/research-tasks/{id}/approvals/{approval_id} | approve/reject + 可选修改 | 新 plan version 或继续 | 404；409 已处理 |
| POST /api/research-tasks/{id}/recover | 空 | 恢复摘要 | 409 有有效 owner；503 store |
| GET /api/research-scheduler/status | 无 | 队列、额度和安全摘要 | 503 |

- 状态转换使用事务 CAS；终态不可返回 running。
- cancel 停止调度新节点并尽力中断当前调用，保留已完成证据。
- 默认搜索和摘要评估不等待批准；用户启用 review_plan_first 或后续出现下载等副作用时进入 waiting_approval。
- 多任务由全局公平队列轮转，不能由单任务独占全部 fast Worker。

## 边界与失败场景

- 租约过期、心跳中断、进程强退、重复 resume、审批重复提交、旧 plan 回调、checkpoint 损坏。
- 恢复时重新校验计划 Schema、预算和输入摘要；不盲目执行旧工具调用。
- 已完成 WorkItem 不重复执行；外部调用无法证明完成时进入 `recovery_required`，不得伪造成功。
- 项目被删除、任务被取消或权限失效时，所有未开始节点取消并释放资源。

## 明确不做

- 不新增论文来源、下载实现、报告编辑器或模型自学习路由。
- 不做跨机器分布式调度；v1 仅单机多进程恢复。
- 不自动批准下载、导入或扩大预算。

## 验收方式

- 两个进程不能重复领取同一 WorkItem；租约过期后只能有一个恢复者成功。
- pause/cancel/approve/reject/resume 和计划版本均通过并发测试。
- 强制终止服务后可以从 checkpoint 继续，完成节点不重复执行。
- 多任务公平性与资源预约不超卖；开发 Task 定向测试，最终 Task 一次全量回归和部署。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待确认后补充暂停、批准、继续、取消和恢复旅程。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | 调度与恢复边界 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | HITL 与恢复旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 并发、事务和恢复评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | `Task(backend-dev)` / `Task(frontend-dev)` | 分端实现 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 并发与恢复验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec028 | 本文件 | — | 完成 |
| 02 | 验证租约、checkpoint 与公平调度 | [`task-02-durable-runtime-gate.md`](../plans/028/task-02-durable-runtime-gate.md) | Spec027、确认、双评审 | 已完成（GO） |
| 03 | 实现全局调度、租约与恢复 | [`task-03-scheduler-lease-recovery.md`](../plans/028/task-03-scheduler-lease-recovery.md) | 02 | 已完成 |
| 04 | 实现计划版本、暂停取消与审批 | [`task-04-plan-version-hitl.md`](../plans/028/task-04-plan-version-hitl.md) | 03 | 已完成 |
| 05 | 实现恢复与审批界面 | [`task-05-recovery-approval-ui.md`](../plans/028/task-05-recovery-approval-ui.md) | 04 | 待执行 |
| 06 | 最终评审、回归、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/028/task-06-review-regression-deploy.md) | 02–05 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/028-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/028-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/028-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建可靠调度、计划版本和恢复 Spec |
