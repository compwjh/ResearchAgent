# Spec 016 本地运行时验收交接

> 状态：计划，尚未执行。本文不是验收结果；所有本地场景初始均为 `not_run`。

## 本轮依据与边界

- 本轮真实基线：`5b1b1d918db8858e848a73da4cee2df54f513ea2`；实现分支 `feature/spec-016-portable-task-ledger`；worktree `/workspace/ResearchAgent/.worktrees/spec-016`。执行前须重新记录实际 HEAD、注册 worktree、git status 与最终云端产物版本。
- 用户已授权云端 CLI 开发与测试；真实 CodeBuddy 本地验收延期。Task 02 与 A6、Spec 016 整体验收仍未完成。
- Luna xhigh 是 Codex 子代理本轮覆盖；项目 CodeBuddy 模型默认值未更改。
- 原本地提交 `f8a2511`、`8a625f0` 等未恢复；历史聊天中的测试计数不能算本轮通过，所有验收结论须来自当前重做分支的新执行记录。
- CLI 仍在开发。协议中列出的命令是计划接口，不代表当前可用；云端定稿后以实际 `--help`、Task 文件和测试报告更新执行步骤。本文不提供或声称验证了可直接运行的验收命令。
- Git bundle 交接尚未生成，也没有可核验的 bundle 文件、ref 或哈希。下文只列拟议交接步骤，不表示已导出或验证。

依据：[`recovery-context.md`](./recovery-context.md#L5)、[`README.md`](../README.md#L10)、[`spec-016`](../../../specs/016-portable-task-ledger.md#L8)、[`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md#L7)。

## 执行前准备（待云端 CLI 定稿）

1. 从云端实施分支核对最新提交、工作树和最终 CLI 帮助；记录 commit、环境版本、实际命令、退出码及日志位置。不得从历史提交或本计划反推成功结果。
2. 确认 Codex 与 CodeBuddy 指向同一仓库身份和同一个主工作树 `.sdd/runtime/task-ledger.sqlite3`；两端各自能只读查看 Task/run 状态。不要用两个独立数据库模拟共享账本。
3. 只在隔离 fixture/专用测试 Task 上执行并发、恢复和提交场景；不得让本地验证抢占仍活跃的云端租约。保护原有 dirty files，不执行 `reset`、`stash`、`clean`、push 或 merge。
4. 确认最终 Task 定义、Prompt 与 `sdd-run-result/v1` 以云端落盘文件为准；按实际 CLI 语法调用。未提供的模型/token/工具计数写 `null`，不得估算。

协议规定 shared runtime 与命令计划接口；Task02 要求真实 Codex/CodeBuddy smoke，而 Task09 明确不能以单测替代双 IDE、rebuild 和恢复验收。参见 [`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md#L7)、[`task-02`](../task-02-validate-task-runtime.md#L48)、[`task-09`](../task-09-review-acceptance-retro.md#L15)。

## 本地验收清单（全部待执行）

| 场景 | 操作计划 | 通过证据 |
|---|---|---|
| 双端共享 | Codex 与 CodeBuddy 分别连接同一 repo/runtime；先分别只读列出相同 Task、run 和 ledger 路径。 | 两边识别同一账本与一致持久状态；记录各自 IDE、executor、run id、路径和只读输出。 |
| 并发双领 | 在同步屏障后由两个独立进程/IDE 对同一 eligible fixture Task 同时执行最终 `next --claim` 接口。命令形式待 CLI 定稿。 | 恰好一个领取成功、一个稳定拒绝；数据库仅一条活动 lease/run；未发生双 Prompt 分派。保存原始脱敏 JSON、退出码及领取前后状态。 |
| 活跃租约与 owner fence | 成功领取后，在租约有效期内由另一 executor 尝试接管，并尝试用非 owner 写 event/complete。 | 活跃 owner 不被替换；错误 owner 的写操作被拒绝；原 lease/run 仍完整。 |
| 无改动中断恢复 | fixture 中结束/模拟 owner 退出且 lease 到期，核实 worktree 未变后恢复。另测 lease 未过期或 owner 仍活跃时恢复。 | 前者保留 abandoned 历史并按协议重新排队/领取；后者拒绝接管；没有丢失 run/event 证据。 |
| 部分改动恢复 | 在允许路径写入 fixture 文件后中断，确认恢复指回原 worktree；另外制造越界改动。 | 部分改动保留并提供 changed-path 清单，不自动清理/回滚；越界变更明确阻塞且文件仍在。 |
| 不得重领 | 检查 `completed`、`cancelled`、仍阻塞/依赖未满足项及 `migration_state=unverified` legacy fixture；重复 rebuild/status/claim。 | 终态、gate/依赖未满足和 legacy `unverified` 均不成为可领取项；rebuild 不把持久完成状态降回 pending。保留诊断与前后镜像。 |
| 结果提交成功闭环 | 对一个允许完成的隔离 Task，以真实结果 JSON、实际命令/test 记录和允许路径内产物走完整 `result`/`complete` 流程；成功提交仅限声明文件。 | schema、Task/run/hash、产物、脱敏和 allowed-path 校验均有证据；Task/spec/README 镜像一致，脱敏摘要可读，生成本地提交且不 push/merge。 |
| 结果提交拒绝 | 分别提交缺字段/未知字段、缺产物、验证失败、hash 漂移、敏感内容或越界 diff 的 fixture 结果。 | 每种情况均拒绝成功完成/提交，给出稳定诊断；Task 未被误标完成，用户文件与失败证据保留。 |
| 跨端结果读取 | 由获胜端完成后，新 CodeBuddy 会话只读 Git 摘要、Task 和状态镜像；再由 Codex 复核同一内容。 | 双端读到一致摘要、状态、风险、待办和实际 artifacts；SQLite 不可重建的瞬时 lease/event 不被伪造。 |

接口依据：claim 单事务与租约见 [`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md#L217)；恢复判定见 [`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md#L223)；结果规则见 [`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md#L180)；legacy gate 见 [`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md#L186)。命令计划包括 `doctor`、`rebuild`、`status`、`next --claim`、`event`、`recover`、`result`、`complete`，最终调用形式须以云端 CLI 定稿为准。

## Git bundle 交接计划（未生成）

云端分支和验收材料稳定后，主 Agent 再冻结要交接的 branch/ref 与基线，生成独立 Git bundle；校验 bundle refs、可验证性和 SHA-256 后，在隔离克隆中导入并核对 HEAD/diff。交付时附 bundle 路径、ref、base commit、哈希和导入核验记录。只纳入已审阅的 Git 提交；不打包 `.sdd/runtime`、SQLite、原始本地日志、凭证或无关 dirty files。当前这些步骤均未执行，bundle 尚无文件或哈希。

## 结果记录与关闭条件

每个场景回填实际 IDE/执行器、commit、命令 argv、真实退出码、脱敏输出、run/lease 状态、fixture 前后 Git diff、产物路径及新鲜测试结果；没运行写 `not_run`，阻塞项写原因。不得仅凭 CLI exit 0 或文字摘要判通过。

只有并发唯一领取、恢复保真、不可重领、结果成功/失败闭环及两端读取均有新证据，才可将本地 CodeBuddy/A6 验收提交给独立 reviewer；Task02、A6 和 Spec 状态由负责人按完整证据另行更新。Task09 还要求 A1–A14、数据库重建、业务回归和审批，不能由本文替代。

## 输入路径清单

- `docs/sdd/plans/016/artifacts/recovery-context.md`
- `docs/sdd/plans/016/README.md`
- `docs/sdd/plans/016/task-02-validate-task-runtime.md`
- `docs/sdd/plans/016/task-09-review-acceptance-retro.md`
- `docs/sdd/specs/016-portable-task-ledger.md`
- `docs/sdd/TASK-PROTOCOL.md`
- `docs/sdd/ROLE-ONBOARDING.md`
- `.codebuddy/skills/progress-logging/SKILL.md`
- `.codebuddy/skills/strategic-compact/SKILL.md`
