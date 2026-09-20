# Spec028 最终验收评审

- 验收对象：`docs/sdd/specs/028-research-task-durable-scheduling.md`
- 验收时间：2026-09-16（Asia/Shanghai）
- 验收者：Spec028 最终评审子 Agent
- 角色：测试总控 / 验收评审
- 模型：Luna high
- 分派方式：由主 Agent 分派

## 结论

**GO。** Task02–05 的持久化并发、计划版本、暂停/继续/取消、审批和前端状态合同均有通过证据；Task06 已补齐 `/recover` API/UI 与声明的 scheduler status API，恢复与状态聚合定向测试通过；最终全量回归和 8500 本机部署 smoke 均通过。

本报告以自动化合同、持久化恢复测试和重启后本机 HTTP smoke 作为收口证据；In-app Browser 受客户端策略影响的交互不作为服务端通过条件，真实 Ollama 长任务不纳入本 Spec 的部署门禁。

## 验收证据

| 验收项 | 结果 | 依据 |
|---|---|---|
| 双进程唯一领取、租约过期接管、旧 owner 拒绝 | 通过（自动化） | Task02 runtime gate、Task03 scheduler/lease 报告 |
| checkpoint 摘要、计划版本、节点推进 CAS | 通过（自动化） | Task02/03 报告 |
| 公平队列、预约容量与释放 | 通过（自动化/定向） | Task02/03 报告；Task02 历史可选探针 skip 已如实保留 |
| pause/resume/cancel 及终态保护 | 通过（自动化） | Task04 后端报告、Task05 前端报告 |
| approval、旧版本不可覆盖、重复提交幂等 | 通过（自动化） | Task04/05 报告 |
| recovery API、checkpoint 校验、未知外部结果不重放 | 通过（定向） | `recovery-api-ui-report.md`：服务层/路由/前端合同通过 |
| `GET /api/research-scheduler/status` | 通过 | 8500 沙箱外只读 curl HTTP 200；返回 queue/quota/safety 聚合且不含租约 token |
| 前端权限、二次确认、loading/防重复、错误恢复 | 通过（静态/合同） | Task05/06 报告；`node --check` 通过 |
| 最终全量回归 | 通过 | **2481 passed、1 skipped、5 warnings、67 subtests，退出码 0** |

## 自动化命令摘要

Task06 恢复补缺报告记录的定向命令均退出码 0：

```text
.venv/bin/python -m pytest --noconftest -q tests/test_spec028_recovery_api_ui.py  # 4 passed
.venv/bin/python -m pytest --noconftest -q tests/test_frontend_spec028_task05_contract.py  # 3 passed
.venv/bin/python -m pytest --noconftest -q tests/test_spec028_hitl.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec028_runtime_contract.py  # 14 passed
node --check frontend/research-tasks.js  # 退出码 0
git diff --check  # 退出码 0
```

最终全量回归统计以 Task06 收口阶段结果为准：2481 passed、1 skipped、5 warnings、67 subtests，退出码 0。未将 skip 或 warnings 改写为失败，也未将其改写为额外通过用例。

## 未验证项与剩余风险

### 收口说明

- 浏览器端交互由 Task05 的状态合同、确认/防重复和 SSE 恢复测试覆盖；当前环境的 In-app Browser 对本机地址可能返回 `ERR_BLOCKED_BY_CLIENT`，不把该环境限制误判为服务故障。
- 强退后的 lease/checkpoint 语义由 Task02 runtime gate 与 Task03/06 定向测试覆盖；服务启动时的中断收敛已在 lifespan 路径中复用并通过全量回归。
- 本轮已重启 8500 服务并完成 health、scheduler status、首页及未知 API 负路径 smoke。

这些边界不改变本 Spec 的服务端收口结论；真实 Ollama 长任务和浏览器客户端限制作为后续环境验证项记录。

### 已知语义风险

- `/recover` 返回恢复检查摘要，不会自动重开 `interrupted` 终态，也不会重放结果未知的外部调用；这符合当前 Spec 的安全边界，但若产品需要真正续跑，需新 Spec/状态机评审。
- Task02 报告的可选公平探针曾因缺少 `langchain_ollama` 跳过；最终全量回归的 1 个 skip 不应被描述为该探针已在本环境真实运行。
- 工作树有 Spec029 在途变更；验收范围不包含这些变更，收口前需隔离并确认归属。

## Gate 与签字状态

| 门禁 | 当前状态 | 说明 |
|---|---|---|
| 需求/技术评审文档 | 已落盘 | 本轮同时生成 028 requirement/tech review；Spec 评审记录与状态台账仍由主 Agent同步 |
| 自动化验收 | 通过 | 定向与最终全量回归均有结果 |
| 真实运行时验收 | 通过（本机 HTTP smoke；浏览器环境限制已记录） | 端口 8500，服务只绑定 127.0.0.1 |
| 部署与最终签字 | 通过 | `PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh` |

**最终 Spec028 验收签字：GO。**

## 2026-09-16 收口复核记录

### 结果状态和摘要

**自动化定向验收通过；P1 接口已修复，最终验收 GO。** 本轮重启服务后完成 scheduler status、health 和首页 smoke；没有把 In-app Browser 的客户端阻断伪造为业务交互通过。

### 改动文件

- 更新本评审及 Task06 文档产物；scheduler status 实现与定向测试见本次 Spec028 代码提交。

### 测试命令 / 退出码 / 结果

- `.venv/bin/python -m pytest --noconftest -q tests/test_spec028_scheduler_status.py tests/test_spec028_runtime_contract.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec028_hitl.py tests/test_spec028_recovery_api_ui.py tests/test_frontend_spec028_task05_contract.py` → `0`，`24 passed`。
- `node --check frontend/research-tasks.js` → `0`。
- `git diff --check` → `0`。
- 沙箱外只读 `curl`：`http://127.0.0.1:8500/api/health`、`/`、`/api/research-scheduler/status` → 各 HTTP `200`、退出码 `0`；scheduler 返回 `status=ok`、queue/quota/safety 聚合，首页 58183 bytes。

### 产物路径

- `docs/sdd/reviews/028-acceptance-review.md`
- `docs/sdd/plans/028/artifacts/task-06/review-report.md`
- `docs/sdd/plans/028/artifacts/task-06/recovery-api-ui-report.md`
- `docs/sdd/plans/028/artifacts/task-06/runtime-smoke.md`

### 决策依据

24 项 Spec028 定向测试、静态检查、全量回归和重启后 health/API smoke 均通过；未将 In-app Browser 客户端阻断或真实 Ollama 长任务误记为服务端失败，因此最终验收 GO。

### 风险与阻塞

- 8500 的 health、首页和 scheduler status smoke 已通过沙箱外只读 curl；In-app Browser 对该地址的 `ERR_BLOCKED_BY_CLIENT` 属环境限制。
- Task02/03/06 定向测试覆盖强退后持久化 lease/checkpoint 恢复语义和完成节点不重放；真实 Ollama 长任务不作为本 Spec 门禁。
- `/recover` 仍是安全检查摘要，不会把 `interrupted` 伪造为 running，也不自动重放未知外部调用；scheduler status 缺失不能用其他 endpoint 代替。

### 主 Agent 后续动作

主 Agent 已补齐 scheduler status API，并同步 Spec、README、状态台账与部署记录；后续若需真实浏览器旅程或 Ollama 长任务压力测试，可作为独立运行时验证，不阻塞本 Spec 收口。

### 时间与统计

- 复核时间：2026-09-16 22:53 CST（Asia/Shanghai）；本轮工具执行约 8 分钟。
- 模型：当前临时 Luna high；独立 token 统计不可用；工具统计：文件读取/检索、pytest、node、git diff、curl、lsof、只读浏览器打开。
