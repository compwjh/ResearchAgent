# Task 03：完整管理、全局记忆与治理界面

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task02；被依赖：Task04；当前状态：`待执行`

## 一句话目标

在 MVP 契约上补齐项目/会话生命周期、全局用户记忆、作用域优先级和可操作的记忆管理界面。

## 当前证据与前置门禁

- Task02 必须已通过真实 MVP 验收，冻结 schema、SSE、游标和唯一消息入口。
- 只允许版本化扩展 Task02 数据模型，不得创建第二套 session/memory store。

## 增量范围

- 项目/会话重命名、移动、归档、删除和稳定 URL 恢复。
- 绑定旧会话时选择 `from_binding / include_prior_history`；跨项目移动清理旧项目运行上下文。
- 全局记忆写入、召回和优先级；单项目经验不得自动升格全局。
- 记忆列表、查看来源、确认候选、编辑、停用、删除和撤销刚写入。
- 删除会话不联动记忆；删除项目事务性删除项目、所属会话和项目记忆，全局记忆保留。

## 子 Agent 分派与文件边界

- backend-dev：版本化 migration、管理 application/API、删除事务和 scope 优先级。
- frontend-dev：项目/会话管理操作和记忆治理页。
- reviewer/tester：分别验证事务、DOM/XSS、权限作用域和用户旅程；只跑受影响领域。
- 每次分派只读 Spec、Task02 固定报告、本 Task 和点名文件；返回字段沿用 Task02。

## 边界与明确不做

- 不做自动候选抽取、会话摘要、项目文档、手机端或 Skill 修改。
- 删除项目不得删除知识库原件；本 Task 尚未建立文档关联时不得猜测路径。
- 编辑记忆必须新建版本或保留 superseded 审计，不原位抹去来源。

## 测试与验收

- 全局/项目/当前指令优先级与跨项目隔离。
- 项目删除级联和全局记忆保留；单会话删除不联动记忆。
- 历史绑定选择、移动确认、归档/恢复、重复名称和并发修改。
- 记忆治理 UI 可查看、确认、编辑、停用、删除和追溯来源。

## 风险与回滚

- 删除事务或作用域隔离失败即停止；从 migration 备份恢复。
- 任何全局记忆静默来源不明或覆盖当前指令均判失败。

## 产出物

- `artifacts/task-03/implementation-report.md`
- `artifacts/task-03/test-report.md`
- `artifacts/task-03/review-report.md`

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：创建完整管理与全局记忆 Task。

