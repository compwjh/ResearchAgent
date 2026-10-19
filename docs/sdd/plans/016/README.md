# spec-016 任务计划索引

> 关联 spec：[`docs/sdd/specs/016-portable-task-ledger.md`](../../specs/016-portable-task-ledger.md)
> 本目录保存 spec-016 的详细实施任务。每个 Task 包含执行思维链、完整子 Agent Prompt、固定回传协议、主 Agent 读回校验和执行结果。

## 编号规则

- 任务 01 是 spec 本身，由架构师完成，不重复建立 Task 01 文件。
- 从任务 02 起一任务一文档，命名为 `task-NN-kebab-case.md`。
- 当前 spec-016 为 `实施中`；用户已授权云端 CLI 和测试先完成，真实 CodeBuddy 验收留本地。Task 02 整体与 A6 尚未完成。
- 每次代码分派最多修改 2 个文件、150 行；必须先分派 `backend-dev`（本 Spec 的 scripts 工具范围） 再落地。
- 弱调度 Agent 只能执行 Task 中的完整 Prompt，不得自行改变目标、范围、角色、路径或验收条件。
- Task 03 定义的新协议在 Task 09 验收通过后才成为项目默认流程；此前 spec-016 自身继续遵循现有 SDD 门禁。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-016 与任务计划 | [spec-016](../../specs/016-portable-task-ledger.md) | — | 完成 |
| 02 | 验证 Task 运行时（Go/No-Go） | [task-02](./task-02-validate-task-runtime.md) | 01 | 进行中（CodeBuddy待本地） |
| 03 | 定义 Task 文档与 Prompt 协议 | [task-03](./task-03-task-document-contract.md) | 云端阶段授权 + Task02前置证据 | 完成 |
| 04 | 实现 SQLite Task 账本 | [task-04](./task-04-sqlite-task-ledger.md) | 03 | 完成 |
| 05 | 实现领取、worktree 与恢复 | [task-05](./task-05-claim-worktree-recovery.md) | 04 | 完成 |
| 06 | 实现 Prompt、结果与指标闭环 | [task-06](./task-06-prompt-result-metrics.md) | 04, 05 | 完成（云端 CLI） |
| 07 | 创建 Codex/CodeBuddy 跨 IDE Skills | [task-07](./task-07-cross-ide-skills.md) | 06 | 云端完成；CodeBuddy 待本地 |
| 08 | 对账并迁移 spec-013～015 | [task-08](./task-08-reconcile-legacy-tasks.md) | 07 云端范围 | 完成（云端迁移） |
| 09 | 评审、验收、提交与复盘 | [task-09](./task-09-review-acceptance-retro.md) | 08 | 云端完成；CodeBuddy 待本地 |

## 固定执行顺序

1. Task 02 云端 SQLite/worktree 前置实验7/7通过。依据用户授权先完成云端阶段；双 IDE 整体验收仍待本地 CodeBuddy，不伪造 Go。
2. Task 03 固定文档 schema、完整 Prompt 和统一结果协议。
3. Task 04–06 实现 CLI 账本、领取恢复和结果指标闭环。
4. Task 07 只做 Codex/CodeBuddy/通用 Agent Skills 适配，不复制业务逻辑。
5. Task 08 对账 legacy 状态；未核实项保持不可领取。
6. Task 09 完成独立验收、开发主管签字、复盘和本地提交。

## 分支与回滚

- 实施分支：`feature/spec-016-portable-task-ledger`。
- 计划 worktree：`.worktrees/spec-016`，必须加入 Git 忽略。
- 当前记录基线：`5b1b1d918db8858e848a73da4cee2df54f513ea2`；本轮已正常克隆，旧未推送产物未恢复。
- 不触碰当前主工作树中的 spec-013/014/015 未提交改动。
- 新工具不可用时继续使用现有 Markdown 手工流程，不影响 ResearchAgent 业务服务。

