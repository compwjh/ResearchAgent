# Spec 022 执行计划：项目会话管理与自进化长期记忆

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md)
> 当前状态：`实施中`。Spec 已确认，Task02 已完成，当前进入 Task03。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-desktop-memory-mvp.md) | 交付可现场验证的桌面端项目记忆纵向 MVP | Spec 确认 | 已完成 |
| [03](./task-03-management-global-memory.md) | 完整项目/会话管理、全局记忆与治理 UI | 02 | 待执行 |
| [04](./task-04-memory-evolution-recall.md) | 异步候选、摘要、冲突和跨会话召回 | 03 | 待执行 |
| [05](./task-05-research-context-progress.md) | 项目文档、RAG 编号来源与完整处理过程 | 04 | 待执行 |
| [06](./task-06-mobile-experience.md) | 手机端项目、会话、记忆和研究交互 | 05 | 待执行 |
| [07](./task-07-capability-memory-proposals.md) | 能力方法记忆与只读 Skill 改进建议 | 04 | 待执行 |
| [08](./task-08-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 05、06、07 | 待执行 |

## 统一执行规则

- Task02 是第一开发任务，必须一次交付完整桌面纵向 MVP，不拆成只能看表或接口的半成品。
- 每个 Task 内可按后端、前端、测试拆子任务，但共享已冻结契约，主 Agent 负责集成。
- 开发过程只跑精确测试；Task 收口跑受影响领域；Task02/05/06 完成后部署 smoke；Task08 才启动全量回归并跑到最终通过。
- 一个 Task 集中评审一次；P0/P1 批量修复后集中复审一次。
- 固定更新 `implementation-report.md`、`test-report.md`、`review-report.md`，里程碑再增加 `acceptance-report.md`；不为每次修复创建新版本报告。
- 已确认范围内的小缺陷写入当前 Task；改变数据模型、公开接口、用户行为或范围时回到 Spec 修订。
- 下游只读 Spec、当前 Task、冻结契约和上一角色固定报告；Q67 已由现有最小上下文规则覆盖，不新增重复流程。

## 里程碑

- M1 / Task02：用户能在桌面浏览器验证跨会话项目记忆（已完成）。
- M2 / Task05：项目文档、RAG 来源和完整处理过程可验证。
- M3 / Task06：手机端核心路径可验证。
- M4 / Task08：全量回归、最终部署和 Spec 收口。

## 变更日志

- 2026-09-11：依据 Grill with Docs 共同理解创建 Task02–08；将原 12 个细粒度任务压缩为 7 个用户可见里程碑任务。
- 2026-09-11：Task02 通过精确测试与受控部署验收，放行 Task03；Task08 仍保留全量回归门禁。
