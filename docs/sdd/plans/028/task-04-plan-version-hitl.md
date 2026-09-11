# Task 04：实现计划版本、暂停取消与审批

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05–06；当前状态：`待执行`

## 一句话目标

实现不可覆盖的计划版本、补充范围反馈、暂停/继续/取消和幂等审批状态机。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec028、本 Task、Task03 报告和 Spec027 Planner Schema。
允许修改：backend/app/research/**、routes_research.py、对应 tests/test_spec028_hitl*.py；本地模型每次最多两代码文件。
禁止改写已完成节点、自动批准副作用、修改前端、push/merge/reset/stash/clean。
完成状态：旧 plan 可审计，反馈只生成新版本；重复批准、暂停/取消竞态和过期 approval 有稳定结果。
验证：状态矩阵、并发 CAS、权限/项目删除、定向 pytest、git diff --check。
报告：artifacts/task-04/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 核对旧计划/事件不可覆盖，终态不回退，取消后不再派新节点。
- 不跑全量；产出接口、状态测试和报告。执行结果待填写。

## 变更日志

- 2026-09-12：创建计划版本与 HITL Task。
