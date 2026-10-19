# Spec 016 本地运行时收尾

> 状态：实施中。本文用于真实 CodeBuddy 本地验收；A6 仍为 `not_run`，不代表真实跨 IDE 或完整 Spec016 已验收。

## 当前已知证据

- 分支：`feature/spec-016-portable-task-ledger`。到本地执行时重新核对实际 HEAD、worktree 和 `git status`，不依赖历史提交作为验收凭证。
- Python CLI 使用 Python 3.9 标准库。旧提交 `f8a2511`、`8a625f0` 未恢复；当前证据来自真实重建验证。
- [Luna live demo](live-luna-demo.md) 记录隔离 fixture 中真实 claim、原样 Prompt、Luna 执行、`complete`、删除 DB 后 `rebuild`，以及 `result`/`metrics`/`NO_TASK` 对照。该 demo 不证明 CodeBuddy/A6、双 IDE 或真实 Spec015 业务通过。
- [工具域 QA](task06-final-tool-tests.md) 记录最终代码候选 `37bb056` 的 382 tests、Ruff、compileall 通过。[业务与服务 QA](final-business-runtime.md) 记录全仓 3275 passed、3 skipped、546 subtests passed（退出 0）；真实 HTTP smoke 通过。Luna QA 设计与判读，root 仅协调权限入口；模型列表为空，未验收真实推理。[Task08 迁移验证](legacy-migration-validation.md) 已通过：38 tasks、0 runs，缺授权 gate 的任务不可领取。
- 本地账本 `.sdd/runtime/task-ledger.sqlite3` 是私有运行时，不通过 Git 传递。相同主机、同一 repo 的 Codex 与 CodeBuddy 共用主工作树账本；独立 clone 不共享它。删除后 rebuild 只能恢复可重建的 Task 和摘要，不能补造本地 events、leases 或 owner。

## CodeBuddy 本地操作

1. 在隔离 fixture repo 执行，不自动领取或运行 Spec015 的真实业务 Task；记录实际 IDE、executor、PID、run ID、HEAD、命令及退出码。
2. 先读取实际全局帮助，再初始化和查看状态。`--repo` 如需指定，放在子命令之前：

   ```sh
   python3 -m scripts.sdd_tasks --help
   python3 -m scripts.sdd_tasks --repo <repo> doctor
   python3 -m scripts.sdd_tasks --repo <repo> rebuild
   python3 -m scripts.sdd_tasks --repo <repo> status --json
   ```

   全局 help 列出 `doctor/rebuild/status/next/recover/complete/fail/event/result/metrics`；子命令 parser 不提供独立 help。
3. 只在 fixture 有一个可领取 Task 时执行一次 `next`：

   ```sh
   python3 -m scripts.sdd_tasks --repo <repo> next --claim --ide codebuddy --executor <executor-id> --owner-pid <persistent-pid>
   ```

   PID 必须属于真实、持续存活且本机可核验的 executor；短命 CLI/shell PID 不可用。未知 owner、外部不可见的进程身份或无法核实的 CodeBuddy executor 均拒绝领取并记录 `executor_unavailable`，不得模拟成功。
4. 将 CLI 返回的完整 Prompt 原样交给 Task 指定 Role 的真实子代理；保留原始 schema/字段，不改写 Prompt。接收真实 JSON 结果后，按 outcome 调用 `complete` 或 `fail`：

   ```sh
   python3 -m scripts.sdd_tasks --repo <repo> complete --run-id <uuid> --executor <executor-id> --owner-pid <persistent-pid> --result <result.json>
   # 若实际结果失败，则使用 fail，参数相同。
   python3 -m scripts.sdd_tasks --repo <repo> result --json --run-id <uuid>
   python3 -m scripts.sdd_tasks --repo <repo> metrics --format json
   ```

   由 CLI 验证结果、运行 Task 验证命令并写入摘要；状态回填只走 CLI，不手改 SQLite、Task 或镜像。CodeBuddy 无法真实调用指定 Role、无真实结果文件或 owner 无法验证时立即停止，保持 `not_run`/失败证据。
5. 脱敏后保存命令、退出码和结果路径。不要提交 `.sdd/runtime`、原始私有日志或 owner 数据，本轮未生成 Git bundle；代码与文档从分支交接。

## A6 / CodeBuddy 场景清单

以下 9 项均为 CodeBuddy 本地验收项，当前状态保持 `not_run`。只用隔离 fixture，逐项保存真实证据；不得用 Luna demo 替代。

| 场景 | 核验内容 | 状态 |
|---|---|---|
| 双端共享 | 同一 repo 下两 IDE 看到同一 ledger 和持久状态 | `not_run` |
| 并发双领 | 两个独立 executor 同时 claim，只有一个获胜 | `not_run` |
| owner fence | 活跃 lease 与错误 executor 写入均受保护 | `not_run` |
| 无改动恢复 | owner 退出后恢复；有效 owner/lease 时拒绝接管 | `not_run` |
| 部分改动恢复 | 保留允许路径改动，越界改动阻塞且不清理现场 | `not_run` |
| 不得重领 | 终态、未满足依赖/gate、迁移未验证 Task 不可领取 | `not_run` |
| 成功闭环 | fixture 结果经验证、CLI complete、镜像及摘要一致 | `not_run` |
| 拒绝闭环 | 坏 schema、缺产物、失败验证、敏感/越界变更被拒绝 | `not_run` |
| 跨端读取 | 获胜端完成后，另一 IDE 读取相同摘要与 Task 状态 | `not_run` |

参考：[TASK-PROTOCOL.md](../../../TASK-PROTOCOL.md)、[Task 07](../task-07-cross-ide-skills.md)、[Task 09](../task-09-review-acceptance-retro.md)。云端证据已链接；全部本地证据与独立复核完成后，再更新 A6、Task02/07/09 和完整 Spec 状态。
