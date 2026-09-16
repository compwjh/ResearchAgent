# Spec028 需求评审

- 评审对象：`docs/sdd/specs/028-research-task-durable-scheduling.md`
- 评审范围：Spec028 需求、Task02–06 交接报告、已实现 API/UI 的需求映射
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec028 最终评审子 Agent
- 角色：开发主管 / 需求评审
- 模型：Luna high
- 分派方式：由主 Agent 分派

## 结论

**通过。** Spec028 的目标、范围、数据对象、状态/失败边界和明确不做项能够映射到 Task02–06 实现；Task06 已补齐 `recover` API/UI 与 `GET /api/research-scheduler/status` 调度状态摘要，需求验收条件满足。

本结论与 Spec028 的产品使用步骤、自动化回归和本机部署 smoke 一致；In-app Browser 对本机地址的客户端阻断作为环境限制单独记录，不改变服务端需求验收结论。

## 需求—证据核对

| 需求面 | 代码/报告证据 | 判定 |
|---|---|---|
| 多进程唯一执行权、租约到期接管、旧 owner 拒绝 | Task02 gate：临时 SQLite WAL、两个独立进程条件更新严格单赢家、过期接管和旧 token 心跳拒绝；Task03 报告确认生产实现使用 `BEGIN IMMEDIATE` 与 token/expiry CAS | 通过 |
| checkpoint 先落盘、摘要与计划版本校验、完成节点不重放 | Task02/03 报告：JSON SHA-256、plan/node/digest CAS 与终态保护均通过 | 通过 |
| 全局公平调度和资源不超卖 | Task02 固定合同、Task03 `ResearchScheduler` 与 durable reservation 定向测试通过；Task02 历史环境曾跳过可选探针，最终全量回归结果按下文如实记录 | 通过（留环境备注） |
| pause/resume/cancel 与终态不可逆 | Task04 报告：状态 CAS、暂停/恢复、取消时收敛活动 WorkItem；Task05/06 前端合同覆盖状态权限、失败/冲突和防重复 | 通过 |
| 计划版本与人工审批不覆盖历史 | Task04 报告：计划版本原子追加、旧版本回调返回 `PLAN_VERSION_STALE`、审批幂等键冲突稳定拒绝；Task05 报告覆盖 legacy approve 与 Session approval 入口 | 通过 |
| `/recover` 安全检查、checkpoint 校验、未知外部调用不自动重放 | Task06 `recovery-api-ui-report.md`：服务层/路由/前端入口已补齐；4 条 recovery 定向测试通过；实现明确不重开 `interrupted` 终态、不伪造未知结果 | 通过 |
| `GET /api/research-scheduler/status` 调度状态摘要 | 已接线并由 ResearchScheduler 聚合现有任务、租约和资源预约；8500 实测 HTTP 200 | 通过 |
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
- `docs/sdd/specs/028-research-task-durable-scheduling.md` 已回写暂停、审批、取消、恢复和重启后检查的产品步骤。
- Spec 状态已由主 Agent同步为“已完成”；定向/全量回归与部署 smoke 证据已落盘。
- In-app Browser 的本机地址阻断不等同于服务端接口失败；前端状态合同与错误/防重复行为由 Task05/06 测试覆盖。

## 评审依据

- [`docs/sdd/plans/028/artifacts/task-02/durable-runtime-gate.md`](../plans/028/artifacts/task-02/durable-runtime-gate.md)
- [`docs/sdd/plans/028/artifacts/task-03/backend-report.md`](../plans/028/artifacts/task-03/backend-report.md)
- [`docs/sdd/plans/028/artifacts/task-04/backend-report.md`](../plans/028/artifacts/task-04/backend-report.md)
- [`docs/sdd/plans/028/artifacts/task-05/frontend-report.md`](../plans/028/artifacts/task-05/frontend-report.md)
- [`docs/sdd/plans/028/artifacts/task-06/recovery-api-ui-report.md`](../plans/028/artifacts/task-06/recovery-api-ui-report.md)

## 2026-09-16 收口复核补充

- 本轮完成 scheduler status 后端实现与文档收口，并执行重启后的定向验证。
- 定向命令：`.venv/bin/python -m pytest --noconftest -q tests/test_spec028_scheduler_status.py tests/test_spec028_runtime_contract.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec028_hitl.py tests/test_spec028_recovery_api_ui.py tests/test_frontend_spec028_task05_contract.py`；退出码 `0`，`24 passed`。
- `node --check frontend/research-tasks.js` 与 `git diff --check` 均退出码 `0`。
- 重启后只读服务复核：`/api/health`、`/`、`/api/research-scheduler/status` 均 HTTP `200`、退出码 `0`；scheduler 返回 queue/quota/safety 聚合且不含租约 token。In-app Browser 对本机地址可能返回 `ERR_BLOCKED_BY_CLIENT`，属客户端环境限制。

复核结论更新为通过：scheduler status 已补齐，产品步骤、测试结果、部署 smoke 和状态台账均已同步。
