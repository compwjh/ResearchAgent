# Spec016 legacy 迁移最终验收

- 验收时间：2026-10-19 01:19 UTC
- 验收提交：`4b14130`（Spec015 迁移提交；未在本次验收中提交）
- 范围：Spec013、014、015 的 legacy task metadata、镜像、状态和证据边界；没有运行 Task，也没有生成历史 Run。

## CLI 与目录验证

| 命令/调用位置 | 退出码 | 结果 |
|---|---:|---|
| 从 main checkout 直接执行 `python -m scripts.sdd_tasks --repo . doctor` | 1 | main checkout 不含 CLI 包，返回 `No module named scripts.sdd_tasks`；这是调用入口错误，不是 doctor 诊断。 |
| 从 Spec015 CLI 执行 `python -m scripts.sdd_tasks --repo /workspace/ResearchAgent doctor` | 0 | `healthy=true`，`task_count=38`，`worktree_count=3`；仅有 `legacy_tasks_ignored`、`stale_task_copies_ignored` 警告。 |
| Spec015 与 Spec016 worktree 各执行 `python -m scripts.sdd_tasks --repo . doctor` | 0 / 0 | 两处均返回 `healthy=true`、38 tasks；诊断同上。 |
| Spec015 worktree 执行 `python -m scripts.sdd_tasks --repo . rebuild` | 0 | `tasks=38`、`runs=0`、`deduplicated=38`。 |
| Spec015 worktree 执行 `python -m scripts.sdd_tasks --repo . status --json` | 0 | 38 项：22 completed、15 blocked、1 waiting；`eligible=[]`、`running=[]`。 |
| 只读 Python 循环：38 个 canonical Task 调用 `parse_task` 与 `validate_mirrors` | 0 | Spec013 8/8、Spec014 8/8、Spec015 22/22 通过。 |
| 只读历史比较：以迁移提交的 parent tree 比较旧正文 | 0 | Spec013 7/7、Spec014 8/8、Spec015 16/16；合计 31/31 byte-identical。 |

main checkout 的 CLI 调用问题通过从 Spec015 worktree 加载已提交 CLI、显式将 `--repo` 指向 main 根目录复验通过；没有修改源码解决调用问题。

## Canonical worktree 与 gate 状态

- `git worktree list --porcelain` 显示 canonical `.worktrees/spec-015` 位于提交 `4b14130`，分支为 `feature/spec-015-security-paper-discovery`。
- Spec015 Task04 metadata 指向该 canonical path/branch，状态为 `pending`，依赖为 `spec-015-task-03` 与 `spec-014-task-09`，required gate 为 `spec-015.legacy-resume-authorized`。
- status JSON 将 Task04 放在 `waiting`，原因是 `gate_unsatisfied:spec-015.legacy-resume-authorized`；它不在 eligible 列表。没有添加 gate 证据，也没有执行 `next --claim`。
- Task10 保持 `status=blocked`、`migration_state=unverified`，required gate 为 `spec-015.task10-scope-ownership-confirmed`；status JSON 仍显示 blocked，未尝试领取。

## 历史正文与指标边界

- 已有 Task 的正文从首个 `##` 标题开始与迁移前版本逐字节相同：Spec013 Task02–08、Spec014 Task02–09、Spec015 Task02–17。变化仅含顶层当前状态规范化和新增机器 metadata/prompt 块。
- 新增的剩余工作 Task 为 Spec013 Task09、Spec015 Task18–23；不覆盖或重写已有历史正文。
- `legacy-summaries.md` 中所有 `unknown_metrics` 字段仍为 JSON `null`。rebuild 的 `runs=0`、doctor 的 `summary_count=0` 确认没有把旧证据伪造成 Run 或运行指标。
- 未运行 `next --claim`，未运行 Spec015 业务任务；没有修改 Python 产品源码或测试。
