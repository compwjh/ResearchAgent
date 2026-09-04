# 任务 07 — 创建 Codex/CodeBuddy 跨 IDE Skills

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 06 ｜ 被依赖：任务 08 ｜ 当前状态：`待执行`

## 一句话目标

用两个通用 Agent Skills 和 CodeBuddy 薄适配器，把“计划落盘”和“执行目前未完成的 Task”变成稳定入口，让弱调度 Agent 只调用 CLI、原样分派 Prompt、校验结果和回填状态。

## 当前证据（2026-09-03）

- 项目现有 Skill 位于 `.codebuddy/skills/`，角色 Agent 位于 `.codebuddy/agents/`。
- Codex 与 CodeBuddy 的子 Agent 工具名称不同，但都能读文件、执行 shell 和发起角色任务。
- `.codebuddy/agents/sdd-orchestrator.md` 当前只产出分派计划，不能直接嵌套分派。
- 通用协议和 CLI 将由 Task 03–06 提供；Skill 不应复制选择、锁、状态或结果逻辑。
- Skill 创建必须按执行环境可用的 skill-creator 指南，由主 Agent 先完整读取指南再落盘。

## 前置门禁

1. Task 06 的完整生命周期 fixture 全部通过。
2. `python3 -m scripts.sdd_tasks --help` 和各命令 JSON 已冻结。
3. 主 Agent 先读取当前环境的 `skill-creator/SKILL.md`，不得把这一步委派给子 Agent。
4. 明确 Codex 与 CodeBuddy 的实际子 Agent 调用方式；不可用能力必须有阻塞返回。

## 思维链

### A. 通用规划 Skill

1. `sdd-plan-tasks` 负责强 Agent 把需求转为 spec、README 和完整 Task。
2. 它要求每个 Task 预生成完整 Prompt、allowed paths、返回 schema 和验收命令。
3. 若 IDE 的 Plan Mode 禁止写文件，最终计划后在首个可写 turn 优先落盘，然后按 SDD 停在待确认。
4. schema 校验失败时只报告问题，不让弱调度器修复。

### B. 通用执行 Skill

5. `sdd-run-next-task` 收到自然语言触发后固定执行 doctor、rebuild/status、next --claim。
6. 根据 CLI 返回的逻辑 agent_role 选择 IDE 适配器，原样传递 rendered prompt。
7. 只接受 result.json；完成后调用 complete/fail 和 result，不根据自然语言摘要自行判定。
8. 门禁、用户交互、缺角色、越界或失败时停止并回传结构化原因。

### C. IDE 适配与项目规则

9. `.agents/skills/` 保存通用 Skill；`.codebuddy/skills/` 只保存引用通用流程和角色映射的薄包装。
10. CodeBuddy 映射现有 pm/tech-lead/junior-dev/tester；Codex 使用可用子 Agent 工具并把逻辑角色写进任务名/Prompt。
11. AGENTS.md 增加两个自然语言入口、结果边界与“不得弱调度器代行”规则。
12. 角色上手文档只增加 CLI/Task 最小读取入口，不让每个角色扫描全项目。

## 子任务拆分与分派

### 分派 1：`junior-dev` — 通用 Skills 草案

**完整 Prompt：**

```text
你是 spec-016 Task 07 分派 1 的 junior-dev。在主 Agent 已读取并提供 skill-creator 关键约束后，创建两个项目级通用 Agent Skills。不要实现或复制 CLI 业务逻辑。

只读取：主 Agent 提供的 skill-creator 约束摘要、docs/sdd/TASK-PROTOCOL.md、spec-016、Task 07、scripts/sdd_tasks/cli.py 的命令接口。

只允许修改：
- .agents/skills/sdd-plan-tasks/SKILL.md
- .agents/skills/sdd-run-next-task/SKILL.md

总改动不超过 150 行。每个 Skill 必须有合法 YAML frontmatter 的 name/description；正文只保留触发条件、固定流程、权限边界和必要引用。

sdd-plan-tasks：要求产出 spec + README + Task 02 起所有文档；每个 Task 含完整 Prompt 和结果协议；落盘后停在待确认。Plan Mode 不允许写时，明确在下一可写 turn 首先落盘。

sdd-run-next-task：固定调用 doctor/status/next --claim；按 agent_role 调用可用子 Agent；原样传 Prompt；只认 result.json；调用 complete/fail/result；一次只执行一个；缺能力/门禁/用户交互时停止。禁止自己改 Task、写业务代码、push/merge/reset/stash/clean。

按 skill-creator validator 校验。结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1。
```

### 分派 2：`junior-dev` — CodeBuddy 薄适配器

**完整 Prompt：**

```text
你是 spec-016 Task 07 分派 2 的 junior-dev。为 CodeBuddy 创建两个薄 Skill 适配器，只映射工具/角色，不复制通用流程。

只读取：Task 07、.agents/skills/sdd-plan-tasks/SKILL.md、.agents/skills/sdd-run-next-task/SKILL.md、.codebuddy/agents/{pm,tech-lead,junior-dev,tester,sdd-orchestrator}.md。

只允许修改：
- .codebuddy/skills/sdd-plan-tasks/SKILL.md
- .codebuddy/skills/sdd-run-next-task/SKILL.md

总改动不超过 150 行。适配器必须引用 .agents 下通用 Skill 和 docs/sdd/TASK-PROTOCOL.md；映射 pm/tech-lead/junior-dev/tester；说明 CodeBuddy Task 工具不可用时返回 executor_unavailable。不得复制 Task 选择、租约、状态机或结果校验代码。

禁止修改现有角色 Agent、AGENTS.md、业务代码或 CLI；不 push/merge/reset/stash/clean。运行 Skill frontmatter/路径校验并写 result.json。
```

### 分派 3：`tester` — 双 IDE 行为验证

**完整 Prompt：**

```text
你是 spec-016 Task 07 的 tester。使用隔离 fixture 验证 Codex 与 CodeBuddy 的两个 Skill 都遵循同一协议，不修改真实业务文件。

只读取：spec-016、Task 07、四个新 Skill、AGENTS.md 新入口、docs/sdd/TASK-PROTOCOL.md、CLI --help。

允许写入：/tmp/spec016-cross-ide-{{RUN_ID}}/ 和 .sdd/runtime/runs/{{RUN_ID}}/result.json。禁止修改 tracked 文件、执行真实未完成 Task、push/merge/reset/stash/clean。

验证场景：
1. “把计划落盘”能产出 spec/README/tasks 并停在待确认。
2. “执行目前未完成的 Task”只 claim 一个，原样传递 Prompt。
3. 缺少子 Agent 时返回 executor_unavailable，不由调度器代行。
4. 子 Agent 只有文字摘要、无 result.json 时执行失败。
5. 门禁/用户输入/越界/测试失败均停止。
6. 两个 IDE 的最终 result JSON 字段一致。

记录逐项证据、通过数、差异和结论到 sdd-run-result/v1；不可真实验证的 IDE 行为标 blocked，不模拟通过。
```

## 子代理返回后主 Agent 必须执行

1. 主 Agent 自行读回并按 skill-creator validator 校验两个通用 Skill。
2. 核对 CodeBuddy 包装只做引用/映射，没有复制状态机逻辑。
3. 更新 `AGENTS.md` 与 `docs/sdd/ROLE-ONBOARDING.md`，每次最多两份纯文档，并读回自然语言触发规则。
4. 分别在 Codex、CodeBuddy 做一次隔离 smoke；无法真实运行的一侧保持阻塞。
5. 回填测试矩阵、差异、适配映射与结果。

## 实时监控命令

```bash
find .agents/skills .codebuddy/skills -name SKILL.md -maxdepth 3 -print
python3 -m scripts.sdd_tasks status --json
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
git diff -- AGENTS.md docs/sdd/ROLE-ONBOARDING.md .agents/skills .codebuddy/skills
```

## 测试与验收标准

- 两个通用 Skill 通过 validator，触发描述清晰。
- CodeBuddy 适配器只做角色映射和通用 Skill 引用。
- 自然语言入口在 AGENTS.md 可检索。
- 两个 IDE 一次只领取一个 Task，使用相同 Prompt/result schema。
- 缺能力时停止，不发生弱调度器代行。
- Skill 不复制 CLI 规则，协议变化只需改通用层。

## 风险、停止条件与回滚

- 某 IDE 不自动发现 `.agents/skills`：保留 AGENTS 显式路径与薄适配器，不复制完整实现。
- 子 Agent API 无法映射逻辑角色：标 executor_unavailable，回架构评审。
- Skill 自动触发过宽：收窄 description，不让普通开发请求误触发。
- 回滚为停止引用新 Skill；CLI 与 Markdown 数据仍可手工使用。

## 产出物

- 两个通用 Skills、两个 CodeBuddy 薄适配器。
- AGENTS 和角色上手入口更新。
- Codex/CodeBuddy 隔离行为矩阵。
- 本文件执行结果。

## 执行结果

> 待 Task 06 完成后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 07，状态置待执行 |

