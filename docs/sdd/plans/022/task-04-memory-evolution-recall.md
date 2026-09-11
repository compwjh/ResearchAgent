# Task 04：异步整理、摘要与跨会话召回

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05、Task07；当前状态：`已完成`

## 一句话目标

建立有证据、可重试、不会阻塞聊天的记忆整理管线，把会话事件压缩成候选、摘要和可靠的跨会话召回上下文。

## 增量范围

- Raw 事件只追加；会话级摘要、候选记忆和过程状态按 checkpoint 异步生成。
- 触发信号：明确记忆、用户纠正、工具失败、上下文压力、会话闲置；定时任务只做漏跑兜底。
- 升格通道：用户明确长期要求、跨会话重复、工具失败后已验证修正。
- 新会话召回全局/项目长期记忆和少量相关摘要；当前执行只召回本会话过程状态。
- 冲突使用 superseded 链；推断记忆可降权，不自动物理删除。
- 召回受独立 token 预算限制，正文、论文证据和当前指令优先。

## 子 Agent 分派

- backend-dev：事件/checkpoint、异步 worker、摘要/候选、检索与上下文打包。
- backend-reviewer/tester：幂等、并发、断点、证据、污染防护和故障降级。
- 前端只在需要候选确认/状态补充时分派；不因纯后端改动跑前端回归。

## 边界与明确不做

- 不把整段 raw 历史直接塞入模型，不从 Langfuse、Agent logs 或浏览器 profile 抽取。
- 不允许无 evidence 的候选升格，不自动把项目经验提升为全局。
- 整理失败不得阻塞会话回复。

## 测试与验收

- Map/Reduce 分批、checkpoint 重启、重复触发幂等和单 session 互斥。
- 错误候选、冲突、撤销、证据丢失和长期未使用降权。
- 同任务带/不带记忆输出具有可观察差异，且注入内容可追溯。
- 超预算时稳定裁剪，不挤掉当前问题和知识库核心证据。

## 风险与回滚

- 出现静默污染、跨项目泄漏或不可追溯升格立即停止自动升格，只保留显式记忆。
- worker 可关闭，已确认记忆和会话主链继续可用。

## 产出物

- `artifacts/task-04/implementation-report.md`
- `artifacts/task-04/test-report.md`
- `artifacts/task-04/review-report.md`

## 执行结果

已完成。既有 memory SQLite 扩展到 v3，提供追加式 Raw event、会话摘要、候选记忆与 evolution checkpoint；本地 worker 支持 Map/Reduce、幂等、session 互斥、stale lease 接管和重启恢复。自动候选保持 candidate，只有带 evidence 才能升格，project 不自动升 global；召回按 global/project 隔离并受独立预算约束，整理/召回失败不阻塞聊天。

- Task04 精确测试：34 passed；Task02/03 及旧聊天兼容：50 passed。
- `py_compile`、`git diff --check` 均通过。
- backend-reviewer 最终 GO；backend-tester PASS；验收报告已追加至 `docs/sdd/reviews/022-acceptance-review.md`。
- 已知非阻塞 P2：worker 进程重启后需下一次消息入口触发 durable work 扫描，后续可在 Task05/Task07 的 worker 生命周期中优化。
- 全量回归未执行，按计划保留至 Task08。

## 变更日志

- 2026-09-11：创建记忆进化与跨会话召回 Task。
- 2026-09-11：Task03 已通过最终复审与验收，启动 Task04；本任务先实现后端异步整理与跨会话召回，前端按需追加。
- 2026-09-11：后端实现、P1 修复、复审和验收完成，状态更新为已完成；放行 Task05/Task07。
