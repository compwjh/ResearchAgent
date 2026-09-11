# Spec 022 执行计划：项目会话管理与自进化长期记忆

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md)
> 当前状态：`实施中（Task10 已完成）`。Task02–Task05、Task09–Task10 已完成；Task06–Task08 继续等待。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-desktop-memory-mvp.md) | 交付可现场验证的桌面端项目记忆纵向 MVP | Spec 确认 | 已完成 |
| [03](./task-03-management-global-memory.md) | 完整项目/会话管理、全局记忆与治理 UI | 02 | 已完成 |
| [04](./task-04-memory-evolution-recall.md) | 异步候选、摘要、冲突和跨会话召回 | 03 | 已完成 |
| [05](./task-05-research-context-progress.md) | 项目文档、RAG、处理过程与桌面缺陷修复轮 | 04、Spec 变更确认 | 已完成（修复轮） |
| [06](./task-06-mobile-experience.md) | 手机端项目、会话、记忆和研究交互 | 05、09、10 | 待执行 |
| [07](./task-07-capability-memory-proposals.md) | 能力方法记忆与只读 Skill 改进建议 | 04 | 待执行 |
| [08](./task-08-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 05、06、07、09、10 | 待执行 |
| [09](./task-09-desktop-project-tree-sidebar.md) | 桌面项目树、会话归属、浮层菜单与统一弹窗 | 05、范围确认 | 已完成 |
| [10](./task-10-system-rule-project-memory-navigation.md) | 系统规则、项目优先记忆与桌面导航修复 | 09、增量确认 | 已完成 |

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
- M2 / Task05：项目文档、RAG、桌面 turn、处理过程、异步记忆结果和侧栏修复轮已完成。
- M2.5 / Task09：按 ChatGPT 项目树参考修正桌面侧栏信息架构和项目绑定体验（已完成）。
- M2.6 / Task10：修复管理页会话直达和项目图标/布局，交付项目优先记忆与唯一用户系统规则（已完成）。
- M3 / Task06：手机端核心路径可验证。
- M4 / Task08：全量回归、最终部署和 Spec 收口。

## 变更日志

- 2026-09-11：依据 Grill with Docs 共同理解创建 Task02–08；将原 12 个细粒度任务压缩为 7 个用户可见里程碑任务。
- 2026-09-11：Task02 通过精确测试与受控部署验收，放行 Task03；Task08 仍保留全量回归门禁。
- 2026-09-11：Task03 通过后端/前端复审、跨端验收和 API smoke，放行 Task04；Task08 仍保留全量回归门禁。
- 2026-09-11：Task04 通过后端复审、精确测试和验收，放行 Task05/Task07；Task08 仍保留全量回归门禁。
- 2026-09-11：Task05 通过双端复审、跨端验收和针对性测试，放行 Task06；Task08 仍保留全量回归门禁。
- 2026-09-11：部署反馈暴露桌面消息顺序、处理步骤终态/折叠和侧栏体验缺陷；经 Grilling 确认异步记忆分析与平铺侧栏方案，Spec/Task05 退回待确认，暂停 Task06。
- 2026-09-11：Task05 修复轮通过后端/前端复审、跨端验收和主环境部署 smoke；定向测试 121 passed，Task05 收口，Task06 仍待启动。
- 2026-09-11：用户现场验证发现 Task05 侧栏仍不符合预期；经 Grilling 将唯一项目标题、嵌套会话、悬浮菜单、统一弹窗及归档视图拆为独立 Task09，等待确认，Task06 暂停。
- 2026-09-11：Task09 需求/技术评审均 GO，用户确认实施；项目 API 的最近活动排序和 cursor 同键约束已冻结，开始后端/前端并行开发。
- 2026-09-11：Task09 现场验证后，经 Grilling 确认会话直达、项目文件夹状态图标、project-first 记忆和独立用户系统规则，拆为 Task10；先落盘并暂停业务实现。
- 2026-09-11：Task10 后端/前端实现、双端复审、64 项后端与 44 项前端定向验收、5 个 Node 合同及受控部署/Chromium DOM smoke 通过；Task10 收口，Task06–Task08 继续等待。
