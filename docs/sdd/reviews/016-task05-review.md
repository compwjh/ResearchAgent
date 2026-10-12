# Spec 016 Task 05 — 独立架构复评

- 日期：2026-10-12
- 评审者：architect_review；角色：architect；模型：gpt-6-luna xhigh；分派方式：collaboration.spawn_agent
- 范围：Task05 claims、eligibility、canonical Task/Spec/gate authority、worktree snapshots/recovery、doctor、CLI 与冻结接口；静态源码复核，无生产/测试改动、无本轮测试执行。
- 结论：**PASS — 云端 Task05 实现与已记录验证范围**。这不是 CodeBuddy 本地验收，也不代表 Spec016 整体验收或 Go。

## 阻塞级别

- P0：无。
- P1：无。
- P2（发现与关闭）：初审发现不安全但已存在的 ledger 会错误返回 `present=false`。后续 [newdoctor.py](../../../scripts/sdd_tasks/newdoctor.py#L66) 先安全打开父目录，再用不跟随符号链接的 leaf stat 确认是否存在；符号链接与非普通文件现返回 `present=true, schema_check=unsafe` 并保持阻塞。新增回归用例覆盖符号链接目标不变与目录型 ledger。root 读回确认 doctor 专项 6 项测试和 Ruff 通过；本评审者未重跑这些跟进命令。P2 已关闭。

## 冻结 CLI 接口闭环

初审发现 `next --claim` 的实现要求 `--owner-pid`，而 Spec016 接口表、TASK-PROTOCOL 与 Task05/07 命令说明此前未记录该参数。它是有意的持久执行器身份输入：短命 CLI 退出后不能作为仍在工作的 owner。已按现有实现同步文档，明确 `--owner-pid <persistent-executor-pid>` 必须是可核验的持久执行器进程，且身份不可用时拒绝领取；已更新 Spec016、TASK-PROTOCOL、Task05、Task06 与 Task07。CodeBuddy 本地执行说明留给 Task09。

## 复核依据

- `claim_next()` 在事务内重读 canonical Task、Spec 当前状态、gate evidence、DB hash/status/dependency/lease 和工作区快照；仅从候选自身 canonical view 交集确认 gate，创建 run、lease 及快照事件在一个 `BEGIN IMMEDIATE` 中完成。
- `recover_expired()` 要求 lease 已过期、owner 经 PID/start-time 核验死亡、Task/worktree/base/hash/event 绑定有效；它只写 `abandoned` 与恢复决策事件，不删除或回滚文件。partial claim 保留原始 before snapshot 链，consumed source 不重复领取。
- `doctor()` 的主检查路径没有 SQLite connect、维护锁、目录创建或文件写入；ledger unsafe 诊断失败关闭。CLI 将错误输出为稳定 JSON envelope，调用端可消费状态矩阵。
- 已读取 [Task05 验证记录](../plans/016/artifacts/task05-validation.md)：记录了 Python 3.9.25 工具包 170/170、Ruff、compileall，以及 8 组归档真实 Git/SQLite smoke 均 exit 0；Task05 CLI 定向测试 6/6 通过。本评审未重跑这些命令，且不把该证据扩展为 CodeBuddy 或业务回归。

## 验收边界

云端 Task05 可进入 Task06。Task06 failed/partial lifecycle 仍须按其独立协议和 journal 故障矩阵设计实现与验收；CodeBuddy 本地 Task02/A6、业务全量回归、Spec016 acceptance review 和部署验证仍未完成。本签字不授权宣称整体 Spec016 完成。
