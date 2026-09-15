# Spec028 需求评审

- 评审对象：`docs/sdd/specs/028-research-task-durable-scheduling.md`
- 评审范围：Spec028 需求、Task02–06 交接报告、已实现 API/UI 的需求映射
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec028 最终评审子 Agent
- 角色：开发主管 / 需求评审
- 模型：Luna high
- 分派方式：由主 Agent 分派

## 结论

**通过（附文档收口条件）**。Spec028 的目标、范围、数据对象、状态/失败边界和明确不做项能够映射到已完成的 Task02–05 实现；Task06 又补齐了 `recover` API/UI 的安全检查闭环。需求层没有发现新增 P0/P1 矛盾。

本结论不等同于 Spec028 已完成：Spec 的“产品使用步骤”仍需由主 Agent 按最终实现回写为可操作旅程，且真实服务 smoke、部署和最终状态台账仍待主 Agent 完成。本文不把尚未运行的浏览器验证记为通过。

## 需求—证据核对

| 需求面 | 代码/报告证据 | 判定 |
|---|---|---|
| 多进程唯一执行权、租约到期接管、旧 owner 拒绝 | Task02 gate：临时 SQLite WAL、两个独立进程条件更新严格单赢家、过期接管和旧 token 心跳拒绝；Task03 报告确认生产实现使用 `BEGIN IMMEDIATE` 与 token/expiry CAS | 通过 |
| checkpoint 先落盘、摘要与计划版本校验、完成节点不重放 | Task02/03 报告：JSON SHA-256、plan/node/digest CAS 与终态保护均通过 | 通过 |
| 全局公平调度和资源不超卖 | Task02 固定合同、Task03 `ResearchScheduler` 与 durable reservation 定向测试通过；Task02 历史环境曾跳过可选探针，最终全量回归结果按下文如实记录 | 通过（留环境备注） |
| pause/resume/cancel 与终态不可逆 | Task04 报告：状态 CAS、暂停/恢复、取消时收敛活动 WorkItem；Task05/06 前端合同覆盖状态权限、失败/冲突和防重复 | 通过 |
| 计划版本与人工审批不覆盖历史 | Task04 报告：计划版本原子追加、旧版本回调返回 `PLAN_VERSION_STALE`、审批幂等键冲突稳定拒绝；Task05 报告覆盖 legacy approve 与 Session approval 入口 | 通过 |
| `/recover` 安全检查、checkpoint 校验、未知外部调用不自动重放 | Task06 `recovery-api-ui-report.md`：服务层/路由/前端入口已补齐；4 条 recovery 定向测试通过；实现明确不重开 `interrupted` 终态、不伪造未知结果 | 通过 |
| 不新增来源、下载、报告编辑器、跨机器调度或自动批准 | Task03–06 报告与代码边界均保持在调度、计划、审批、恢复和 UI；未引入第二套任务状态机 | 通过 |

## 产品使用旅程（供 Spec 回写）

以下是与现实现一致的最小用户旅程；这是需求评审依据，不代表本轮已完成浏览器实测：

1. 用户进入 Research Task 详情；在 `planning`/`running`/`waiting_approval` 状态可选择“暂停研究”，在 `paused` 状态可选择“继续研究”。
2. 任务进入 `waiting_approval` 时，用户可批准计划；补充范围应生成新计划版本，历史版本和已完成证据保持可审计。
3. 用户可取消尚未完成的任务；后端停止派发新节点并收敛活动 WorkItem，终态不回退。
4. 任务处于 `interrupted` 或 `recovery_required` 时，用户可点击“检查并恢复”；系统清理过期租约/预约并返回 checkpoint 与 WorkItem 摘要，不自动重放未知外部调用。
5. 用户根据恢复摘要提供受校验的 checkpoint/后续受控计划；若状态冲突或租约仍有效，界面显示稳定错误并要求刷新。

## 文档门禁与剩余条件

- 本需求评审本身已落盘，路径为 `docs/sdd/reviews/028-requirement-review.md`。
- `docs/sdd/specs/028-research-task-durable-scheduling.md` 的产品使用步骤仍是占位文本；主 Agent 应将上面旅程压缩回 Spec，并同步评审记录状态。
- Spec 当前仍为“实施中（Task06 最终评审、回归与部署）”；本评审不擅自修改 Spec 状态。
- 真实浏览器点击、窄屏可达性、服务启动后的 API/UI smoke 未在本轮运行，不能写成“浏览器验收通过”。

## 评审依据

- [`docs/sdd/plans/028/artifacts/task-02/durable-runtime-gate.md`](../plans/028/artifacts/task-02/durable-runtime-gate.md)
- [`docs/sdd/plans/028/artifacts/task-03/backend-report.md`](../plans/028/artifacts/task-03/backend-report.md)
- [`docs/sdd/plans/028/artifacts/task-04/backend-report.md`](../plans/028/artifacts/task-04/backend-report.md)
- [`docs/sdd/plans/028/artifacts/task-05/frontend-report.md`](../plans/028/artifacts/task-05/frontend-report.md)
- [`docs/sdd/plans/028/artifacts/task-06/recovery-api-ui-report.md`](../plans/028/artifacts/task-06/recovery-api-ui-report.md)

