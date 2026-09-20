# Spec028 Task06 恢复 API/UI 补缺报告

## 结果状态和摘要

**完成（定向实现与验证通过）**。补齐了 `POST /api/research-tasks/{id}/recover` 和研究任务详情页的“检查并恢复”按钮。恢复动作复用现有 `ResearchScheduler.recover()` 清理过期租约/资源预约，并复用 `ResearchService._validate_resume_checkpoint()` 校验可选 checkpoint；未知外部调用不会被自动重放，`interrupted` 任务不会被伪造为 running。

## 改动文件

- `backend/app/research/application/research_service.py`：新增 `recover()`，返回任务、调度器、WorkItem 与 checkpoint 摘要；有效租约返回稳定 409。
- `backend/app/api/routes_research.py`：新增可空 checkpoint envelope 与 `/recover` 路由，沿用既有错误体。
- `frontend/research-tasks.js`：新增 recover action、状态权限、二次确认、loading/冲突/失败反馈及 `/recover` 调用。
- `frontend/index.html`：新增 `research-task-recover-button`。
- `tests/test_spec028_recovery_api_ui.py`：新增服务层、checkpoint、路由转发和前端合同测试。

## 测试命令/退出码/结果

```text
.venv/bin/python -m pytest --noconftest -q tests/test_spec028_recovery_api_ui.py
退出码 0；4 passed

.venv/bin/python -m pytest --noconftest -q tests/test_frontend_spec028_task05_contract.py
退出码 0；3 passed

.venv/bin/python -m pytest --noconftest -q tests/test_spec028_hitl.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec028_runtime_contract.py
退出码 0；14 passed

node --check frontend/research-tasks.js
退出码 0

git diff --check
退出码 0
```

## 产物路径

`docs/sdd/plans/028/artifacts/task-06/recovery-api-ui-report.md`

## 决策依据

- Spec028 要求 `/recover` 返回恢复摘要，同时要求未知外部结果不得伪造成功。
- 当前 ResearchTask 状态机将 `interrupted` 视为终态，编排器明确拒绝终态重开；因此本补缺不扩展第二套状态机、不绕过 CAS、不自动重放未知 WorkItem。
- 租约与资源预约的唯一恢复入口是 `ResearchScheduler.recover()`；暂停恢复已有 `/resume` 与 checkpoint 校验，故 `/recover` 只负责安全检查和接管摘要。

## 风险阻塞

- 当前 `/recover` 是安全恢复检查/摘要，不会把 `interrupted` 任务直接重开；仍有未知 WorkItem 时必须由后续受控 checkpoint/计划流程决定是否继续。
- Task06 原报告指出的三份 Gate 评审、真实服务 smoke、部署证据、README 状态同步仍由主 Agent 收口；本子任务未部署、未跑全量回归、未 commit/push。
- 工作树已有 Spec029 在途变更，本次未修改或提交这些文件。

## 主 Agent 后续动作

1. 复核本补缺实现与 Spec028 恢复语义，确认与 Spec029 在途工作树隔离。
2. 运行最终 Gate 评审、唯一全量回归和真实浏览器 recovery smoke；若产品需要真正重开 interrupted 任务，应先修订 Spec/状态机并重新评审。
3. 更新 Spec028/README/status changelog、部署并记录运行时证据。

## 开始/结束/总耗时

- 开始：2026-09-16 03:52 CST（Asia/Shanghai）
- 结束：2026-09-16 03:59 CST（Asia/Shanghai）
- 总耗时：约 7 分钟

## 模型/token/tool 统计

- 模型：当前执行 Agent（Luna high，按父 Agent 分派信息）
- token：工具侧未提供可核实的独立 token 统计
- tool：读取/检索、补丁编辑、pytest、Node 语法检查、git diff 检查

## 2026-09-16 收口复核追加

### 结果状态和摘要

**补缺自动化回归通过；scheduler status P1 已修复。** 本轮保留 `/recover` 的安全检查语义，并补齐状态聚合读取接口。

### 改动文件

- 更新 Spec028 评审与 Task06 收口文档；scheduler status 业务实现和定向测试见本次代码提交。

### 测试命令 / 退出码 / 结果

- 六个 Spec028 相关 pytest 文件定向集合 → 退出码 `0`，`24 passed`。
- `node --check frontend/research-tasks.js` → 退出码 `0`。
- `git diff --check` → 退出码 `0`。

### 运行时复核与产物

- 8500 服务重启后经沙箱外只读 curl，health、首页和 `/api/research-scheduler/status` 均退出码 `0` / HTTP `200`；scheduler 返回 queue/quota/safety 聚合且不泄露租约 token；In-app Browser 对本机地址可能被 `ERR_BLOCKED_BY_CLIENT` 阻断。
- 本报告、`review-report.md`、`runtime-smoke.md` 及三份 `docs/sdd/reviews/028-*.md` 为本轮文档产物。

### 决策依据、风险与主 Agent 后续动作

自动化证据支持 `/recover` 与 scheduler status 实现，重启后的 health/API smoke 也通过；持久化 lease/checkpoint 恢复语义由 Task02/03/06 定向测试覆盖，Spec028 收口为 GO。真实 Ollama 长任务与客户端浏览器限制作为后续环境验证项，不引入第二套调度实现。

复核时间：2026-09-16 22:53 CST；独立 token 统计不可用；模型为当前临时 Luna high。
