# Task 03：实现全局调度、租约与恢复

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 GO；被依赖：Task04–06；当前状态：`已完成`

## 一句话目标

实现单机全局公平队列、WorkItem 唯一租约、资源预约、checkpoint 和服务重启后的自动恢复。

## 实施范围

- 复用 Research Task repository，新增 lease/checkpoint/reservation 表和调度服务。
- 本地模型每次分派最多两个代码文件；不新增第二套任务实体。
- 完成节点不重放；未知外部结果进入 recovery_required。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec028、Task02 报告、Spec027 repository/orchestrator 和 backend-patterns。
允许修改：backend/app/research/**、必要迁移、tests/test_spec028_scheduler*.py；本地模型按两文件拆分。
禁止前端、新来源/下载/报告功能、真实用户库、push/merge/reset/stash/clean。
验证：并发领取、心跳、到期恢复、崩溃、幂等、公平队列、资源释放、定向 pytest、git diff --check。
报告：artifacts/task-03/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 读回锁范围，确认外部模型/网络调用不在 SQLite 事务或锁内。
- 重跑定向并发测试，不跑全量；产出后端代码、测试和报告。Task03 已完成，`10 passed`。

## 变更日志

- 2026-09-12：创建调度与租约实现 Task。
