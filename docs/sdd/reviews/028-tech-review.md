# Spec028 技术评审

- 评审对象：`docs/sdd/specs/028-research-task-durable-scheduling.md`
- 评审范围：Task02–06 交接报告、实际调度/恢复 API/UI、最终回归口径
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec028 最终评审子 Agent
- 角色：开发主管 / 技术评审
- 模型：Luna high
- 分派方式：由主 Agent 分派

## 结论

**通过。** 实现沿用 Spec027 的 ResearchStore、WorkItem、状态机和既有 Worker/ResourceProbe 接缝，未形成第二套任务实体、状态机或模型客户端。租约、checkpoint、资源预约、计划版本和审批均通过持久化 CAS 边界组合；恢复 API/UI 以安全检查摘要为语义，不伪造未知外部调用完成；新增的 `GET /api/research-scheduler/status` 仅聚合现有持久化状态，不引入第二套调度逻辑。

该结论覆盖技术设计、定向/全量自动化证据以及重启后的本机 health/API smoke；In-app Browser 客户端阻断和真实 Ollama 长任务作为环境验证项记录，不改变已验证的服务端契约。

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
- `GET /api/research-scheduler/status` 已接线；8500 重启后实测 HTTP 200，返回 queue/quota/safety 聚合，不泄露 owner token 或 checkpoint 内容。
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
| 最终全量回归 | **2481 passed、1 skipped、5 warnings、67 subtests；退出码 0** | Task06 最终回归结果（主 Agent提供） |

## 技术风险与处置

1. `interrupted` 仍是终态；`/recover` 是安全检查/摘要，不会直接把它重开。若以后需要真正续跑，必须先修订状态机、计划语义与评审范围，不能由本实现隐式扩展。
2. Task02 历史可选公平探针曾因环境缺少 `langchain_ollama` 跳过；最终全量回归通过不应改写该历史事实。主 Agent 如需运行时公平性证据，应在依赖完整环境复验。
3. 8500 重启后的 health、scheduler status 和首页 smoke 已通过；In-app Browser 对本机地址的 `ERR_BLOCKED_BY_CLIENT` 是客户端环境限制，真实 Ollama 长任务不属于本 Spec 的部署门禁。
4. 工作树包含 Spec029 在途变更；本技术评审只认 Spec028 Task02–06 交接物与对应实现，主 Agent 收口时必须隔离无关变更。

## 评审意见

技术方案与现有运行时证据支持 Spec028 收口；若后续需要真实浏览器或 Ollama 长任务压力测试，单独记录为环境验收，不新增调度实现。

## 2026-09-16 收口复核补充

- 本轮完成 scheduler status 后端实现并重启服务，未执行 `push`/`reset`/`stash`/`clean`。
- Spec028 定向回归退出码 `0`，共 `24 passed`；`node --check frontend/research-tasks.js`、`py_compile` 和 `git diff --check` 均退出码 `0`。
- 8500 重启后 `/api/health`、`/`、`/api/research-scheduler/status` 均 HTTP `200`；In-app Browser 的 `ERR_BLOCKED_BY_CLIENT` 作为环境限制记录。

技术评审更新为“通过”；scheduler status 已补齐，评审、回归和部署记录同步完成。
