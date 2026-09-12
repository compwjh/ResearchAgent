# Task 06：非领域规则归位与 Skill 编写边界

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05；当前状态：`待执行`

## 一句话目标

确认「与 Skill 无关的规则」在项目中的唯一落点，并在 `AGENTS.md` 补一条
**Skill 编写边界**原则，防止研发流程/调度纪律/Git 规则再次被写进 Skill 造成污染回归。

## 背景与关键发现（已核实，不要重复排查）

旧的 `usenix-accepted-papers` / `usenix-paper-catalog-search` 两份 SKILL.md 中混入的规则，
**在 `AGENTS.md` 中早已存在**。逐条核对结果：

| Skill 中的污染项 | AGENTS.md 现状 | 结论 |
|---|---|---|
| 「每次最多 2 个代码文件、约 150 行」 | **已存在**（约 323 行：≥3 文件须拆成「每任务 ≤2 代码文件、≤150 行」） | Skill 中为重复，已剥离 |
| 回传字段清单、进展日志路径、先回传代码后回传说明 | **已存在**（约 143 / 218 / 311 / 328 行） | 同上 |
| Git 禁止项（reset / stash / clean / 自动 push / 合并 main） | **已存在**（`## Git 规范` → `### 提交与推送纪律`：Agent 只做本地 commit，不主动 push、不合 main、不 force push） | 同上 |
| `` `.sdd/runtime/task-ledger.sqlite3` `` 回填 | **未实现**：spec-016 task-04 状态 `待执行`，`.sdd/runtime/` 目录不存在；Skill 原文措辞为「（若启用）」 | **不迁移**，待 spec-016 落地 |
| `junior-dev` 角色引用 | **该角色不存在**：`.codebuddy/agents/` 实际只有 architect / backend-dev / backend-reviewer / backend-tester / doc-updater / frontend-dev / frontend-reviewer / frontend-tester / planner / tester | **删除引用**，不得再出现 |
| 子模型指挥与编排 | **已存在**（`### 如何指挥子模型执行`，约 69 行起） | 同上 |

**结论**：本任务**不是「搬家」**——AGENTS.md 早已是这些规则的正确落点。
真正的缺口是：**缺少一条明确禁止把这类规则写进 Skill 的原则**，所以才会反复污染。

## 实施步骤与文件边界

1. 在 `AGENTS.md` 的合适位置（建议靠近「如何指挥子模型执行」或「文件和编号规则」）
   新增一小节（例如 `### Skill 编写边界（防污染）`），明确：
   - **Skill（`.agents/skills/*/SKILL.md`）只写领域编排协议**：适用范围、输入契约、编排决策点、
     固定发现链/下载链、领域边界、停止条件。
   - **禁止写入**：研发分派纪律（每次文件数/行数、回传字段清单）、研发台账回填
     （Task、`.sdd/runtime/task-ledger.sqlite3`）、Git 操作禁止项（reset/stash/clean/自动 push/合并 main）、
     不存在的角色名、以及对 spec/plan 研发过程文档的引用。
   - **这些规则的唯一落点**：通用研发纪律 → `AGENTS.md`；角色特有分派约束 → `.codebuddy/agents/<role>.md`。
   - **引用角色名必须真实存在**（列出现有 10 个角色，并注明**不存在 `junior-dev`**）。
2. 核对并按需微调 `.codebuddy/agents/*.md`：确保角色分派约束落在对应角色定义里，
   与 AGENTS.md 不矛盾；**不要大改**，只做去重与纠偏。
3. 在 `docs/sdd/spec-status-changelog.md` 登记 spec-032.1 的状态与本次决策要点。

**只允许改动**：`AGENTS.md`、`.codebuddy/agents/*.md`、`docs/sdd/spec-status-changelog.md`。
**不要改**任何 SKILL.md（新旧四份均已定型）、不要改 `backend/**`、`frontend/**`。

## 子代理分派

角色 `doc-updater`（模型 `qwen3.5:9b`）。回传：改动文件与新增小节位置、核对结论、风险。

## 边界与明确不做

- 不删除或改写任何 Skill 文件。
- 不改动 spec-016 及其 task-ledger 设计（未实现，按「若启用」条件性指令处理）。
- 不修改 `docs/sdd/specs/` 下其它 spec 的执行配置表（模板要求五行齐全，历史文件不在本次范围）。
- 不新增流程、不改门禁规则。

## 验收

1. `AGENTS.md` 中存在明确的 Skill 编写边界小节，且包含「禁止写入」清单与「唯一落点」说明。
2. 该小节列出现有真实角色名，并注明**不存在 `junior-dev`**。
3. 新写的规则与 AGENTS.md 既有内容**不重复、不矛盾**（先读后写，去重）。
4. `docs/sdd/spec-status-changelog.md` 已登记 spec-032.1。
5. 未改动任何 SKILL.md 与前后端代码。

## 产出物、执行结果与变更日志

> 待执行后填写：真实改动位置、核对结论、台账登记内容。
