# Task 02：验证租约、Checkpoint 与公平调度

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md) ｜ 索引：[README](./README.md)
> 依赖：Spec027 完成、Spec028 确认及双评审通过；被依赖：Task03–06；当前状态：`待执行`

## 一句话目标

用临时 SQLite 和多进程固定样本冻结唯一租约、checkpoint、计划版本、公平调度与恢复 Go/No-Go 合同。

## 执行范围

- 验证 CAS、租约到期、旧 owner 拒绝、进程强退、重复恢复和 checkpoint 摘要校验。
- 验证多任务公平轮转、资源不超卖和终态不可逆。
- 只允许修改 `tests/test_spec028_runtime_contract.py` 与 `docs/sdd/plans/028/artifacts/task-02/**`。

## 完整分派 Prompt

```text
角色：architect + backend-tester；读取 Spec028、本 Task、Spec027 数据/事件合同和现有 SQLite 事务模式。
目标：以临时库和多进程探针冻结可靠调度合同，给出 GO/NO-GO。
禁止业务代码、真实数据、外部调用、push/merge/reset/stash/clean。
验证：双领用、过期接管、旧 token、checkpoint 损坏、计划旧版本、取消竞态、公平性、git diff --check。
报告：artifacts/task-02/durable-runtime-gate.md。
返回：状态、文件、命令/退出码、产物、依据、风险、后续、时间和可用统计。
```

## 主 Agent 校验、风险与产出

- 复跑最小多进程测试；无法证明单 owner 或完成节点幂等则 NO-GO。
- 本 Task 无业务回滚；产出为合同测试和 gate 报告。执行结果待填写。

## 变更日志

- 2026-09-12：创建可靠运行时 gate。
