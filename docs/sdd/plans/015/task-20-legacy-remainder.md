# Task 20 — 补齐论文检索 Tab 完整交互与真实 GUI 验收

> 关联：[Spec 015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：03, 04, 05, 19
> 当前状态：`阻塞`

## 目标与迁移分类

这是 Spec016 legacy 审计裁决新增的剩余工作 Task；来源为 `docs/sdd/plans/015/task-07-paper-discovery-tab.md`，分类为 `partial`。不得重做已验证交付。

## 剩余工作（审计原文）

先完成依赖 Task04 后，补齐 A3 自定义会议/完整交互、真实 GUI 与受控外站验收及关闭 flag 的用户界面证据；不把 Task16 的 USENIX-only 页面范围当成原完整 UI 验收。

## 验收

逐项提供剩余工作要求的可复核证据；验收者核对产物、范围、依赖和旧审计，不得扩大解释。缺少任一项时保持阻塞并说明缺口。

## 解除阻塞条件

仅当依赖完成、所需外部条件与授权已就绪，且维护者确认范围冻结后，才可改为待执行。验收产物在执行后提供；迁移脚本不自动解除。

## 执行结果

> 待执行后填写。
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-20",
  "spec_id": "015",
  "title": "补齐论文检索 Tab 完整交互与真实 GUI 验收",
  "status": "blocked",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-03",
    "spec-015-task-04",
    "spec-015-task-05",
    "spec-015-task-19"
  ],
  "required_gates": [],
  "agent_role": "frontend-dev",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "frontend/index.html",
    "frontend/app.js",
    "frontend/styles.css",
    "docs/sdd/plans/015",
    "docs/sdd/reviews",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-015",
    "branch": "feature/spec-015-security-paper-discovery",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [
    "docs/sdd/reviews/015-task07-remainder-review.md"
  ],
  "validation_commands": [
    "node --check frontend/app.js"
  ],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: frontend-dev
Read: ["docs/sdd/plans/015/task-07-paper-discovery-tab.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["frontend/index.html", "frontend/app.js", "frontend/styles.css", "docs/sdd/plans/015", "docs/sdd/reviews", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: ["node --check frontend/app.js"]
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope. Remaining work (verbatim from audit): 先完成依赖 Task04 后，补齐 A3 自定义会议/完整交互、真实 GUI 与受控外站验收及关闭 flag 的用户界面证据；不把 Task16 的 USENIX-only 页面范围当成原完整 UI 验收。 Acceptance: 执行后逐项提供剩余工作要求的可复核证据；验收者核对产物、范围、依赖和旧审计。 Release condition: 依赖、所需外部条件与授权已就绪，维护者确认范围冻结后才可改为 pending；验收产物执行后提供。
<!-- sdd-task-prompt:v1:end -->
