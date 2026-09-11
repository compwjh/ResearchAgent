# Task 08：最终评审、全量回归、部署与复盘

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task05、Task06、Task07、Task09；当前状态：`待执行`

## 一句话目标

在所有实现 Task 完成后集中完成独立评审、最终全量回归、真实部署、用户路径验收和复盘，并据此决定 Spec022 是否可标记为已完成。

## 前置门禁

- Task02–07、Task09 状态、固定报告和缺陷闭环真实一致。
- MVP、研究集成和手机里程碑均已部署 smoke。
- 工作树不含用户数据、日志、Cookie、Token、数据库或无关修改。

## 执行顺序

1. backend/frontend reviewer 分别进行最终范围审计；问题集中修复并只跑相关测试。
2. 单端 tester 汇总受影响领域报告；跨端 tester 执行一次最终候选全量回归。
3. 若全量失败，回到责任 Task 用定向测试修复；生成新的最终候选后重新执行全量，直到通过或真实阻塞。
4. 部署服务，执行桌面、手机、重启恢复、项目隔离、记忆治理、RAG 和 processing smoke。
5. 完成验收报告、复盘、Spec/README/Task/状态台账、本地提交；不 push、不合并 main。

## 最终验收范围

- 项目/会话/消息持久化、两屏历史分页、流式失败与恢复。
- 项目与全局记忆、优先级、冲突、候选、摘要、召回、治理与删除规则。
- 项目文档关联不删除原件；RAG 正文后最多 5 个编号来源并正确展开。
- 处理过程真实、持久化、失败/降级明确、动画可关闭。
- 桌面和手机核心路径、键盘/触控/滚动、XSS 和跨项目隔离。
- 产品运行时不能修改 Skill、规则或代码。
- 现有知识库、论文检索/下载、文章助手和普通聊天全部回归。

## 子 Agent 分派

- backend-reviewer / frontend-reviewer：各自范围最终审计。
- backend-tester / frontend-tester：单端证据。
- tester：跨端、全量和部署验收，写 `docs/sdd/reviews/022-acceptance-review.md`。
- 架构师（自身）：签字、状态更新、复盘、本地提交和部署核验。

## 边界与停止条件

- 任一 P0/P1、全量失败、用户数据风险、跨项目泄漏或假 progress 未关闭，Spec 保持实施中。
- 不用未运行、局部运行或历史测试冒充最终全量通过。
- 不 push、不合并 main、不清理用户无关修改。

## 产出物

- `docs/sdd/reviews/022-acceptance-review.md`
- `docs/sdd/retro/2026-xx-xx-spec-022-memory-retro.md`
- 本地原子提交与部署证据。

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：创建最终收口 Task；全量回归只在本阶段启动，但失败修复后必须对最终候选重新运行直至通过。
