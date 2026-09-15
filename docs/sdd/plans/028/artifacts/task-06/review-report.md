# Spec028 Task06 收口审查报告

## 当前结论

**条件收口（自动化门禁通过，运行时/部署门禁待完成）。** Task02–05 的实现和交接物已完成，Task06 已关闭此前发现的 recovery API/UI P1 缺口；恢复 API/UI 定向测试通过，最终全量回归通过。当前不得把 Spec028 标记为“已完成”，因为真实服务 smoke、浏览器交互、强退恢复和部署记录仍由主 Agent执行。

本报告只记录 Spec028 收口证据，未修改业务代码、测试代码、Spec 状态或 Git，也未执行部署。

## 文档门禁

- 已生成：`docs/sdd/reviews/028-requirement-review.md`、`028-tech-review.md`、`028-acceptance-review.md`。
- 需求评审结论：通过（附产品步骤回写条件）。
- 技术评审结论：通过（附运行时门禁条件）。
- 验收评审结论：自动化验收通过，最终运行时验收待主 Agent。
- Spec 的“产品使用步骤”、评审记录状态和最终状态台账仍需主 Agent同步；本报告不代行这些状态变更。
- `plans/028/README.md` 已记录恢复 API/UI 补缺后的收口上下文；Task06 最终状态以主 Agent完成 smoke/部署后为准。

## 技术复用审查

| 领域 | 已核对事实 | 结论 |
|---|---|---|
| 存储与迁移 | ResearchStore 统一承载 lease/checkpoint/reservation、WorkItem 和 plan version；惰性幂等表/索引兼容 Task02 probe | 通过 |
| 并发与恢复 | `BEGIN IMMEDIATE` + owner/expiry CAS；过期 lease/reservation 由 `ResearchScheduler.recover()` 单一负责 | 通过 |
| 调度与资源 | ResearchScheduler 复用既有 `_GlobalWorkerScheduler`/ResourceProbe，按任务轮转并配对 durable reservation | 通过 |
| 计划与状态 | 复用既有状态机；计划只追加新版本；终态不可回 running；取消收敛活动 WorkItem | 通过 |
| API/UI | `/pause`、`/resume`、`/cancel`、`/recover` 与既有 `/feedback` 接线；前端使用状态 allowlist、确认、loading/冲突态和 SSE 重连 | 通过 |
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

最终候选全量结果：**2450 passed、1 skipped、5 warnings、67 subtests，退出码 0**。

该统计只证明当前最终候选的自动化回归结果。1 个 skip 和 5 个 warnings 均原样记录；不能将历史 Task02 的可选探针 skip 改写成真实运行通过。

## 尚未完成的运行时/部署门禁

以下证据尚未由本报告或本子 Agent执行：

1. 启动 FastAPI 服务并记录实际可用端口、启动命令、health 和首页/Research Task API smoke。
2. 真实浏览器验证 pause/resume/approval/cancel/recover 的按钮可达性、二次确认、loading/冲突反馈、SSE 重连和窄屏行为。
3. 强制终止服务并以真实数据验证 lease/checkpoint 恢复、完成节点不重复执行和未知外部结果不伪造成功。
4. 完成部署验证后，将命令、地址、结果和遗留风险写回验收文档与 Spec/Task 状态台账。

这里不得使用静态合同测试、Fake probe 或定向 pytest 代替真实浏览器/服务证据。

## 剩余风险与收口动作

- `/recover` 是安全检查/摘要，不直接重开 `interrupted`；真正续跑需求需另行修订状态机和 Spec。
- Task02 曾受可选依赖影响而跳过公平探针；如运行时环境可用，应由主 Agent复验并记录实际结果。
- 工作树存在 Spec029 在途变更；主 Agent必须确认归属并隔离，避免把无关改动纳入 Spec028 提交/部署。
- 主 Agent完成上述运行时门禁后，再同步 Spec/README/Task 状态、`spec-status-changelog.md`，补复盘并决定是否标记 Spec028 已完成。

## 交接

- 本报告：`docs/sdd/plans/028/artifacts/task-06/review-report.md`
- 需求评审：`docs/sdd/reviews/028-requirement-review.md`
- 技术评审：`docs/sdd/reviews/028-tech-review.md`
- 验收评审：`docs/sdd/reviews/028-acceptance-review.md`

评审子 Agent：Spec028 最终评审子 Agent（Luna high）
日期：2026-09-16（Asia/Shanghai）
