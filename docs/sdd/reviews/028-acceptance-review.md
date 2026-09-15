# Spec028 最终验收评审

- 验收对象：`docs/sdd/specs/028-research-task-durable-scheduling.md`
- 验收时间：2026-09-16（Asia/Shanghai）
- 验收者：Spec028 最终评审子 Agent
- 角色：测试总控 / 验收评审
- 模型：Luna high
- 分派方式：由主 Agent 分派

## 结论

**自动化验收通过；最终运行时验收待主 Agent 完成。** Task02–05 的持久化并发、计划版本、暂停/继续/取消、审批和前端状态合同均有通过证据；Task06 已补齐 `/recover` API/UI，恢复定向测试通过；最终全量回归为 **2450 passed、1 skipped、5 warnings、67 subtests，退出码 0**。

本报告不声称真实浏览器验证、服务 smoke 或部署已经通过：这些动作尚未由本评审执行，必须由主 Agent 启动服务后完成并记录，随后再决定 Spec028 是否可以标记“已完成”。

## 验收证据

| 验收项 | 结果 | 依据 |
|---|---|---|
| 双进程唯一领取、租约过期接管、旧 owner 拒绝 | 通过（自动化） | Task02 runtime gate、Task03 scheduler/lease 报告 |
| checkpoint 摘要、计划版本、节点推进 CAS | 通过（自动化） | Task02/03 报告 |
| 公平队列、预约容量与释放 | 通过（自动化/定向） | Task02/03 报告；Task02 历史可选探针 skip 已如实保留 |
| pause/resume/cancel 及终态保护 | 通过（自动化） | Task04 后端报告、Task05 前端报告 |
| approval、旧版本不可覆盖、重复提交幂等 | 通过（自动化） | Task04/05 报告 |
| recovery API、checkpoint 校验、未知外部结果不重放 | 通过（定向） | `recovery-api-ui-report.md`：服务层/路由/前端合同通过 |
| 前端权限、二次确认、loading/防重复、错误恢复 | 通过（静态/合同） | Task05/06 报告；`node --check` 通过 |
| 最终全量回归 | 通过 | **2450 passed、1 skipped、5 warnings、67 subtests，退出码 0** |

## 自动化命令摘要

Task06 恢复补缺报告记录的定向命令均退出码 0：

```text
.venv/bin/python -m pytest --noconftest -q tests/test_spec028_recovery_api_ui.py  # 4 passed
.venv/bin/python -m pytest --noconftest -q tests/test_frontend_spec028_task05_contract.py  # 3 passed
.venv/bin/python -m pytest --noconftest -q tests/test_spec028_hitl.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec028_runtime_contract.py  # 14 passed
node --check frontend/research-tasks.js  # 退出码 0
git diff --check  # 退出码 0
```

最终全量回归统计以 Task06 收口阶段结果为准：2450 passed、1 skipped、5 warnings、67 subtests，退出码 0。未将 skip 或 warnings 改写为失败，也未将其改写为额外通过用例。

## 未验证项与剩余风险

### 尚未运行（不能标记为通过）

- 真实服务启动后的 `GET /api/health`、首页/Research Task 入口和 OpenAPI 路由 smoke。
- 真实浏览器中的暂停、继续、批准、取消、检查并恢复点击旅程，包括二次确认、按钮禁用、错误冲突和 SSE 重连。
- 服务强制终止后的跨进程恢复，以及恢复后完成节点不重复执行的运行时证据。
- 部署命令、实际端口、访问地址和停止/保活记录。

这些项目由主 Agent 执行和记录；本报告不以自动化合同测试替代它们。

### 已知语义风险

- `/recover` 返回恢复检查摘要，不会自动重开 `interrupted` 终态，也不会重放结果未知的外部调用；这符合当前 Spec 的安全边界，但若产品需要真正续跑，需新 Spec/状态机评审。
- Task02 报告的可选公平探针曾因缺少 `langchain_ollama` 跳过；最终全量回归的 1 个 skip 不应被描述为该探针已在本环境真实运行。
- 工作树有 Spec029 在途变更；验收范围不包含这些变更，收口前需隔离并确认归属。

## Gate 与签字状态

| 门禁 | 当前状态 | 说明 |
|---|---|---|
| 需求/技术评审文档 | 已落盘 | 本轮同时生成 028 requirement/tech review；Spec 评审记录与状态台账仍由主 Agent同步 |
| 自动化验收 | 通过 | 定向与最终全量回归均有结果 |
| 真实运行时验收 | 待主 Agent执行 | 不得以静态/合同测试冒充浏览器 smoke |
| 部署与最终签字 | 待主 Agent执行 | 完成后补实际端口、地址、命令和遗留风险 |

**最终 Spec028 验收签字：待真实服务 smoke、部署记录和主 Agent 收口确认。**

