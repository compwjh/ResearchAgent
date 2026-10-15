---
name: sdd-run-next-task
description: 在 CodeBuddy 中执行下一项 SDD Task 时，使用通用执行 Skill 和现有角色 Agent。
---

# CodeBuddy SDD execution adapter

遵循 [通用执行 Skill](../../../.agents/skills/sdd-run-next-task/SKILL.md)；Task/Prompt/result 协议以 [Task Protocol](../../../docs/sdd/TASK-PROTOCOL.md) 为准，通用流程查 [AGENTS.md](../../../AGENTS.md)。

读取 Prompt 的 `Role:`，按同名映射到现存 CodeBuddy Agent：`architect`、`backend-dev`、`backend-reviewer`、`backend-tester`、`doc-updater`、`frontend-dev`、`frontend-reviewer`、`frontend-tester`、`planner` 或 `tester`。使用对应 `.codebuddy/agents/<role>.md` 的既有模型与角色配置，将完整 Prompt 原样交给它。

若 CodeBuddy Task 能力不可用，或不能调用该角色，返回 `executor_unavailable` 并停止；不要改用调度器自行执行。
