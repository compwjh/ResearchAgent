# Spec028 技术评审

- 评审对象：`docs/sdd/specs/028-research-task-durable-scheduling.md`
- 评审范围：Task02–06 交接报告、实际调度/恢复 API/UI、最终回归口径
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec028 最终评审子 Agent
- 角色：开发主管 / 技术评审
- 模型：Luna high
- 分派方式：由主 Agent 分派

## 结论

**通过（附运行时门禁条件）**。实现沿用 Spec027 的 ResearchStore、WorkItem、状态机和既有 Worker/ResourceProbe 接缝，未形成第二套任务实体、状态机或模型客户端。租约、checkpoint、资源预约、计划版本和审批均通过持久化 CAS 边界组合；恢复 API/UI 以安全检查摘要为语义，不伪造未知外部调用完成。代码与 Task02–06 报告及定向验证相互一致。

该结论只覆盖技术设计与自动化证据，不代替真实服务启动、浏览器 smoke、强退恢复和部署验证。主 Agent 完成这些动作并确认无回归后，才可进行 Spec 状态收口。

## 技术复用与边界

| 接缝 | 复用事实 | 评审结论 |
|---|---|---|
| 持久化 | `ResearchStore` 统一承载 scheduler lease/checkpoint/reservation、任务/WorkItem 与计划版本；惰性幂等建表兼容 Task02 probe | 通过 |
| 并发与所有权 | `BEGIN IMMEDIATE`、owner token、expiry CAS；`claim_work_item` 在同一写事务内完成状态转移和租约领取 | 通过 |
| 调度 | `ResearchScheduler` 复用既有 `_GlobalWorkerScheduler`/`ResourceProbe`，以 durable reservation 配对 fast Worker grant；按任务轮转 | 通过 |
| 状态机 | Task04 复用既有 ResearchTask/domain state machine；终态拒绝重新进入 running；取消在事务内收敛 queued/running WorkItem | 通过 |
| 计划与审批 | 计划只追加新版本，旧版本不可覆盖；Approval 以幂等身份处理重复提交和身份冲突 | 通过 |
| 恢复 | `/recover` 复用 `ResearchScheduler.recover()` 和 `_validate_resume_checkpoint()`；有效租约冲突返回稳定 409 | 通过 |
| 前端 | `research-tasks.js` 复用既有详情/SSE 状态投影；操作权限集中 allowlist，按钮统一确认、loading/disabled 和错误冲突态 | 通过 |
| 范围控制 | 未新增来源、下载/导入、报告编辑器、跨机器分布式调度或自动批准 | 通过 |

## 接口与不变量核对

- `POST /pause`、`/resume`、`/cancel`、`/recover` 均经过服务层 CAS；`resume` 可接受 checkpoint envelope，`recover` 返回 bounded summary。
- 计划审批继续使用既有 `/feedback` 与 Session command 接缝，不能用前端乐观状态覆盖服务端版本。
- checkpoint 的输入摘要和 plan version 必须匹配；外部调用结果不确定时维持 `recovery_required`/中断语义，不重放。
- 资源预约有 worker 维度活动占用、容量检查和过期回收；恢复入口归 `ResearchScheduler` 单一负责。
- 前端 `recover` 仅在 `interrupted`/`recovery_required` 可见，动作失败显示冲突/重试，不把检查结果渲染成已恢复运行。

## 验证证据

| 验证 | 结果 | 证据 |
|---|---|---|
| Task02 runtime contract | `5 passed, 1 skipped`；skip 是历史环境缺少 `langchain_ollama` 的可选公平探针 | Task02 gate 报告 |
| Task03 scheduler/lease 定向 | `9 passed, 1 skipped`；py_compile、diff check 通过 | Task03 报告 |
| Task04 HITL 与受影响 Spec027 集合 | `28 passed`；受影响集合 `66 passed, 5 subtests passed`；py_compile、diff check 通过 | Task04 报告 |
| Task05 前端合同 | Python `31 passed`；Node 合同 2/2 PASS；node check/diff check 通过 | Task05 报告 |
| Task06 recovery API/UI | recovery `4 passed`；前端 recovery 合同 `3 passed`；既有 028 定向 `14 passed`；node check/diff check 通过 | Task06 recovery 报告 |
| 最终全量回归 | **2450 passed、1 skipped、5 warnings、67 subtests；退出码 0** | Task06 最终回归结果（主 Agent提供） |

## 技术风险与处置

1. `interrupted` 仍是终态；`/recover` 是安全检查/摘要，不会直接把它重开。若以后需要真正续跑，必须先修订状态机、计划语义与评审范围，不能由本实现隐式扩展。
2. Task02 历史可选公平探针曾因环境缺少 `langchain_ollama` 跳过；最终全量回归通过不应改写该历史事实。主 Agent 如需运行时公平性证据，应在依赖完整环境复验。
3. 真实服务 smoke、浏览器交互和强退后恢复尚未由本评审执行；这仍是 Gate 5/部署门禁，而非自动化测试已覆盖的事实。
4. 工作树包含 Spec029 在途变更；本技术评审只认 Spec028 Task02–06 交接物与对应实现，主 Agent 收口时必须隔离无关变更。

## 评审意见

技术方案可进入最终运行时验收。不得在完成 health/API、浏览器 recovery/pause/resume/cancel/approval smoke 及部署记录前，把本报告的“通过”解释为 Spec028 已完成。

