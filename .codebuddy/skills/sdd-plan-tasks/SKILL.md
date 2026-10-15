---
name: sdd-plan-tasks
description: 在 CodeBuddy 中规划或拆分 SDD spec 与 Task 文档时，使用通用规划 Skill。
---

# CodeBuddy SDD planning adapter

按 [通用规划 Skill](../../../.agents/skills/sdd-plan-tasks/SKILL.md) 编排需求；Task 与 Prompt 格式遵循 [Task Protocol](../../../docs/sdd/TASK-PROTOCOL.md)，通用流程查 [AGENTS.md](../../../AGENTS.md)。

为生成的 `Role:` 选择 CodeBuddy 中同名的真实角色 Agent：`architect`、`backend-dev`、`backend-reviewer`、`backend-tester`、`doc-updater`、`frontend-dev`、`frontend-reviewer`、`frontend-tester`、`planner` 或 `tester`。模型和角色配置沿用对应 `.codebuddy/agents/<role>.md`。

若规划过程中需要委派，而 CodeBuddy Task 能力不可用或不能调用指定角色，返回 `executor_unavailable` 并停止；不要声称任务已分派。
