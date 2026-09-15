# Task 05：实现恢复与审批界面

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md) ｜ 索引：[README](./README.md)
> 依赖：Task04；被依赖：Task06；当前状态：`已完成`

## 一句话目标

让用户看懂等待确认、暂停、取消、恢复和计划变更，并能安全执行对应操作。

## 完整分派 Prompt

```text
角色：frontend-dev；读取 Spec028、本 Task、Task04 API 报告和现有 research-tasks.js。
允许修改：frontend/research-tasks.js、frontend/styles.css、必要 index/app 接线、tests/test_spec028_frontend*；本地模型按两文件拆分。
禁止修改后端、原生 prompt/confirm、展示隐藏思维链、push/merge/reset/stash/clean。
完成状态：等待批准自动展开；其他终态稳定；暂停/继续/取消有确认、失败恢复和防重复提交。
验证：node --check、DOM/状态/重连合同、桌面手机 smoke、git diff --check。
报告：artifacts/task-05/frontend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 检查按钮权限、loading/disabled、焦点管理、菜单层级和窄屏可达性。
- 只跑前端定向测试；产出 UI、合同测试和报告。Task05 已完成，前端合同测试通过，待 Task06 收口。

## 变更日志

- 2026-09-12：创建恢复与审批 UI Task。
