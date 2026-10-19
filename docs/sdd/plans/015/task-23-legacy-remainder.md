# Task 23 — 补齐 USENIX-only 收口签字与复盘

> 关联：[Spec 015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：13, 14, 15, 16
> 当前状态：`阻塞`

## 目标与迁移分类

这是 Spec016 legacy 审计裁决新增的剩余工作 Task；来源为 `docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md`，分类为 `partial`。不得重做已验证交付。

## 剩余工作（审计原文）

保留已通过的 USENIX-only QA/部署证据；补 Task17 范围的复盘和 Tech Lead 对 USENIX-only 收口的明确签字。Spec015 全范围 A1–A20 的阻塞继续由 Task02/04/06–09 跟踪，不能由本项单独关闭。

## 验收

逐项提供剩余工作要求的可复核证据；验收者核对产物、范围、依赖和旧审计，不得扩大解释。缺少任一项时保持阻塞并说明缺口。

## 解除阻塞条件

仅当依赖完成、所需外部条件与授权已就绪，且维护者确认范围冻结后，才可改为待执行。验收产物在执行后提供；迁移脚本不自动解除。

## 执行结果

> 待执行后填写。
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-23",
  "spec_id": "015",
  "title": "补齐 USENIX-only 收口签字与复盘",
  "status": "blocked",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-13",
    "spec-015-task-14",
    "spec-015-task-15",
    "spec-015-task-16"
  ],
  "required_gates": [],
  "agent_role": "architect",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015",
    "docs/sdd/specs/015-security-paper-discovery.md",
    "docs/sdd/reviews",
    "docs/sdd/retro",
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
    "docs/sdd/retro/2026-10-spec015-usenix-closure-retro.md"
  ],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: architect
Read: ["docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015", "docs/sdd/specs/015-security-paper-discovery.md", "docs/sdd/reviews", "docs/sdd/retro", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope. Remaining work (verbatim from audit): 保留已通过的 USENIX-only QA/部署证据；补 Task17 范围的复盘和 Tech Lead 对 USENIX-only 收口的明确签字。Spec015 全范围 A1–A20 的阻塞继续由 Task02/04/06–09 跟踪，不能由本项单独关闭。 Acceptance: 执行后逐项提供剩余工作要求的可复核证据；验收者核对产物、范围、依赖和旧审计。 Release condition: 依赖、所需外部条件与授权已就绪，维护者确认范围冻结后才可改为 pending；验收产物执行后提供。
<!-- sdd-task-prompt:v1:end -->
