# Task09 — Research Tab 复用、旧入口与旧数据清理

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task04、Task07、Task08；当前状态：`已完成`

## 一句话目标

让 Research Tab 使用统一 Session 流程和共享树/审批/报告组件，移除普通会话旁的丑陋研究按钮，并精确删除旧版未绑定 ResearchTask。

## 背景与前置条件

- 必读 Spec034 的 Tab、表单自动建会话、兼容接口和删除规则。
- 旧 POST `/research-tasks` 只保留兼容适配器，不再直接启动。

## 数据、配置与接口

- 表单调用 `/research-sessions`，创建自然语言首消息和 `深度研究：<主题>` 会话标题。
- Session 列表展示绑定会话、阶段、进度、审批、耗时和 Agent/Tool 摘要。
- 清理条件必须是旧版且无 conversation 绑定的 Task；删除其从属数据，不备份。
- 清理前必须 dry-run 输出旧版判定、目标 Task/children ID 与计数；任一校验/删除步骤失败即中止，不做部分删除。

## 实施步骤与文件边界

1. 复用 Task04/07/08 组件改造 Tab，不创建第二套树或审批 UI。
2. 实现创建后自动打开会话、继承项目和“打开对应会话”。
3. 删除每个普通会话旁的研究按钮，保留 Tab 创建表单。
4. 以迁移/维护步骤直接清理旧未绑定 Task，并用前后计数验证未波及其他库。

## 子代理分派

- `frontend-dev` 主责 Tab 与旧按钮；`backend-dev` 主责适配器和精确清理。
- 双端 reviewer/tester 分别检查；`tester` 做创建→会话→Tab 往返 smoke。

## 边界与明确不做

- 不删除 Tab 表单，不删除已绑定 Task，不删除会话、目录或 KB。
- 会话活跃研究时不允许删除；终态后只解绑，报告保留。
- 清理不做备份，这是用户明确裁决。

## 验收、风险与回滚

- 表单和聊天创建均进入同一 Intake/Plan/Approval；不存在直接运行旁路。
- 普通会话列表无独立研究按钮；Tab 的任务卡和调试能力保留。
- 清理前后断言只减少目标 Task 及其 children，目录/KB/会话计数和内容不变。
- 产出必须记录 dry-run 与确认后的删除数量、失败中止证据；不得删除已绑定 Task、会话、目录或 KB。

## 产出物、执行结果与变更日志

- 产出：Tab 改造、兼容适配、旧入口移除、清理测试与双端报告。
- 执行结果：已完成。后端/前端最终复审均 GO；Task09 后端定向测试 14 passed，相关后端回归 178 passed，前端 Task09 合同 8 passed、相关 Task04/07/08 合同 20 passed，Node 合同、py_compile、Ruff 与 diff-check 通过。跨库清理在快照变化或无法验证时 fail-closed、回滚并写入 aborted 审计；真实浏览器/Ollama smoke 留 Task10。
- 变更日志：2026-09-13 启动 Research Tab 统一 Session/树/报告组件、旧研究按钮移除与未绑定旧 Task dry-run 清理；2026-09-15 修复项目物化、创建幂等、游标分页、dry-run token、跨库不变性、真实会话标题及 Agent/Tool 摘要，并经双端最终复审 GO；不触碰会话、目录或 KB。
