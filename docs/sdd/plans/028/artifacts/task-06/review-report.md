# Spec028 Task06 收口审查报告

## 当前结论

**GO。** Task02–05 的实现和交接物已完成，Task06 已关闭 recovery API/UI 与 scheduler status P1 缺口；定向测试、最终全量回归和 8500 本机部署 smoke 均通过，Spec028 可以标记为“已完成”。

本报告记录 Spec028 收口证据；scheduler status 的业务实现与定向测试已由 backend-dev 完成，部署由主 Agent执行。

## 文档门禁

- 已生成：`docs/sdd/reviews/028-requirement-review.md`、`028-tech-review.md`、`028-acceptance-review.md`。
- 需求评审结论：通过。
- 技术评审结论：通过。
- 验收评审结论：GO。
- Spec 的“产品使用步骤”、评审记录状态和最终状态台账已同步。
- `plans/028/README.md` 已记录 scheduler status 补缺、回归与部署结果。

## 技术复用审查

| 领域 | 已核对事实 | 结论 |
|---|---|---|
| 存储与迁移 | ResearchStore 统一承载 lease/checkpoint/reservation、WorkItem 和 plan version；惰性幂等表/索引兼容 Task02 probe | 通过 |
| 并发与恢复 | `BEGIN IMMEDIATE` + owner/expiry CAS；过期 lease/reservation 由 `ResearchScheduler.recover()` 单一负责 | 通过 |
| 调度与资源 | ResearchScheduler 复用既有 `_GlobalWorkerScheduler`/ResourceProbe，按任务轮转并配对 durable reservation | 通过 |
| 计划与状态 | 复用既有状态机；计划只追加新版本；终态不可回 running；取消收敛活动 WorkItem | 通过 |
| API/UI | `/pause`、`/resume`、`/cancel`、`/recover`、`/api/research-scheduler/status` 与既有 `/feedback` 接线；前端使用状态 allowlist、确认、loading/冲突态和 SSE 重连 | 通过 |
| 范围约束 | 未新增来源、下载、报告编辑器、跨机器调度、自动批准或第二套任务实体/状态机 | 通过 |

## 验收证据

### Task02–05 交接物

- Task02：`5 passed, 1 skipped`；skip 是缺少 `langchain_ollama` 的可选公平调度探针。WAL、跨进程单赢家、租约接管、checkpoint 摘要和终态保护通过。
- Task03：`9 passed, 1 skipped`；租约、checkpoint、资源预约、轮转调度和幂等释放通过；py_compile/diff check 通过。
- Task04：`28 passed`；受影响 Spec027 集合 `66 passed, 5 subtests passed`；pause/resume/cancel、计划版本和审批幂等通过。
- Task05：Python 合同 `31 passed`；Node 合同 2/2 PASS；前端 node check/diff check 通过。

### Task06 recovery API/UI 补缺

`docs/sdd/plans/028/artifacts/task-06/recovery-api-ui-report.md` 记录：

- `tests/test_spec028_recovery_api_ui.py`：`4 passed`，退出码 0。
- `tests/test_frontend_spec028_task05_contract.py`：`3 passed`，退出码 0。
- 既有 028 HITL/scheduler/runtime 定向集合：`14 passed`，退出码 0。
- `node --check frontend/research-tasks.js` 与 `git diff --check`：退出码 0。
- `/recover` 返回受限恢复摘要；有效租约返回冲突；checkpoint 可校验；未知外部调用不自动重放；`interrupted` 不被伪造为 running。

### 最终全量回归

最终候选全量结果：**2481 passed、1 skipped、5 warnings、67 subtests，退出码 0**。

该统计只证明当前最终候选的自动化回归结果。1 个 skip 和 5 个 warnings 均原样记录；不能将历史 Task02 的可选探针 skip 改写成真实运行通过。

## 运行时与部署门禁

主 Agent已在重启后完成 health、首页、scheduler status 和未知 API 负路径 smoke；持久化 lease/checkpoint 恢复、不重复执行和状态机边界由 Task02/03/04/06 定向测试覆盖。In-app Browser 对本机地址可能返回 `ERR_BLOCKED_BY_CLIENT`，真实 Ollama 长任务不属于本 Spec 的部署门禁。

## 剩余风险与收口动作

- `/recover` 是安全检查/摘要，不直接重开 `interrupted`；真正续跑需求需另行修订状态机和 Spec。
- Task02 曾受可选依赖影响而跳过公平探针；如运行时环境可用，应由主 Agent复验并记录实际结果。
- Spec029 的在途变更未纳入本次 Spec028 提交；文件范围已在提交前复核。
- Spec/README/Task 状态、`spec-status-changelog.md` 与部署记录已同步，Spec028 标记为已完成。

## 交接

- 本报告：`docs/sdd/plans/028/artifacts/task-06/review-report.md`
- 需求评审：`docs/sdd/reviews/028-requirement-review.md`
- 技术评审：`docs/sdd/reviews/028-tech-review.md`
- 验收评审：`docs/sdd/reviews/028-acceptance-review.md`

评审子 Agent：Spec028 最终评审子 Agent（Luna high）
日期：2026-09-16（Asia/Shanghai）

## 2026-09-16 收口复核追加

本轮补齐 scheduler status 实现并重启服务。Spec028 定向测试为 `24 passed`、退出码 `0`；全量回归为 `2481 passed, 1 skipped, 5 warnings, 67 subtests`、退出码 `0`；`node --check frontend/research-tasks.js`、`py_compile` 和 `git diff --check` 均通过。

8500 重启后经沙箱外只读 curl 复核，`/api/health`、`/`、`/api/research-scheduler/status` 均 HTTP `200`，未知 `/api/*` 仍返回 404；scheduler 返回 queue/quota/safety 聚合且不泄露租约 token。In-app Browser 对本机地址可能返回 `ERR_BLOCKED_BY_CLIENT`，属客户端环境限制；持久化恢复语义由 Task02/03/06 定向测试覆盖，Spec028 收口为 GO。
