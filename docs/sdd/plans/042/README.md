# 实施计划索引：spec-042 OpenEval 接入

> 关联：[spec-042 OpenEval 接入：本地离线 Agent 评测闭环](../../specs/042-openeval-agent-evaluation.md)
> Spec 当前状态：**已完成（root已完成最终状态收口）**。Task02 Go、Task03探针及Task04-A–E均已完成；候选 `145f9d6` 的真实 CLI/API E2E、headless Langfuse 只读核对和最终全量回归均已落盘。结果为 `3335 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`，验收准备度为 `9/10 + 1 N/A`，tester 已 `READY_FOR_USER`、architect 已 `GO`。用户人工验收尚不等同于文档/代码完成，不要求重复写 score；本范围没有新增 UI、自然语言入口或业务 API。早期 Grilling 与旧候选失败记录保留为历史证据。

## 目标（一句话）

在本机离线约束下建立「Langfuse trace → 本地模型判官评分 → 结果可回看」的最小评测闭环。

## 任务索引

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-042（含 grill with docs 分析） | [spec-042 本体](../../specs/042-openeval-agent-evaluation.md) | — | 已完成（2026-09-22确认） |
| 02 | Go/No-Go：验证最高风险前提 | [task-02-validate-feasibility.md](./task-02-validate-feasibility.md) | 01 | 已完成（判定 **Go**，[报告](./task-02-gono-go-report.md)） |
| 03 | 专用记忆探针重测 `memory_correctness`（收敛遗留 L2） | [task-03-memory-probe.md](./task-03-memory-probe.md) | 02 | 已完成（G1=1.0 / G2=0.975 / G3=0.95 → `adopt:qwen3.5:9b`，[报告](./task-03-memory-probe-report.md)） |
| 04 | 原范围离线评测交付与错误门禁 | [task-04-offline-evaluation-delivery.md](./task-04-offline-evaluation-delivery.md) | 02、03 | 已完成（04-A–E；`145f9d6` 真实 E2E、headless 核对、全量回归与双签 GO/READY） |

## 关键前置事实（取自 spec-042「背景与依据」）

- F2：观测数据已充足（一轮实验即 178 条 trace）
- F3：token 用量只在 **direct 路由**下为真实值
- F5：**历史矛盾点**——曾实测见 `route=langchain` 且 usage 为 0；Task 02 已完成复核并判定 Go，该证据仍保留供收口参考
- F6：硬约束——数据不出本机、零外网依赖
- F8：OpenEval 名字冲突（三个候选项目），接入前须复核目标项目是否可离线运行

## 门禁

- 需求评审 → 技术评审 → 用户确认 → 执行 → 验收（详见 `docs/sdd/SDD-GATE-CHECKLIST.md`）
- 历史条件：Task 02 若判定为 **No-Go**，则回到 spec-013 / spec-041 处理路由与埋点缺陷，并保持本 spec「待确认」；本轮 Task 02 已判定 **Go**，该条件不是当前状态。
- 当前收口结果：Task04-A–E、真实 API E2E、headless 只读核对、Spec 全量回归、验收双签和状态台账均已完成；真实报告位于 `docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/`，人工验收步骤位于 `docs/sdd/plans/042/manual-acceptance.md`。用户实际人工验收仍是后续用户动作，不因 `READY_FOR_USER` 自动视为已完成。
