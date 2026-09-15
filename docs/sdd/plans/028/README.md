# Spec 028 执行计划：可靠调度、计划版本与恢复

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md)
> 当前状态：实施中（Task04）。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-durable-runtime-gate.md) | 冻结租约、checkpoint、公平性与恢复合同 | Spec027、确认、双评审 | 待执行 |
| [03](./task-03-scheduler-lease-recovery.md) | 全局调度、租约、资源预约和自动恢复 | 02 | 待执行 |
| [04](./task-04-plan-version-hitl.md) | 计划版本、暂停、取消、审批和反馈 | 03 | 待执行 |
| [05](./task-05-recovery-approval-ui.md) | 恢复与等待确认交互 | 04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 02–05 | 待执行 |

## 统一规则

- 不修改 Spec027 已完成节点的历史事实。
- 单任务只跑定向测试；Task06 执行唯一一次全量回归。
- 产出写入 `docs/sdd/plans/028/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec028 创建。
