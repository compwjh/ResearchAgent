# 任务 05 — 实现领取、worktree 与恢复

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04 ｜ 被依赖：任务 06 ｜ 当前状态：`待执行`

## 一句话目标

在 Task 账本之上实现一次一个任务的确定性选择、原子租约、每个 Spec 独立 worktree、执行基线快照和中断恢复，使多个 IDE 不会重复执行或污染其他 Spec 的修改。

## 当前证据（2026-09-03）

- 当前主工作树含多个 Spec 的未提交修改，自动执行必须隔离。
- 用户已选择“一次一个 Task”和“自动独立 worktree”。
- Task 04 计划提供 Task catalog、run/lease 表和事务接口，但尚无领取或 Git 操作。
- 当前 Git 规范禁止自动 push、合并、force push、reset、stash 和 clean。

## 前置门禁

1. Task 04 的 parser、store、catalog 和 tests 全部通过。
2. spec-016 实施分支和 `.worktrees/spec-016` 已由主 Agent 基于明确 commit 建立。
3. `.worktrees/` 与 `.sdd/runtime/` 已进入忽略规则，`git check-ignore` 可验证。
4. Git worktree 创建、复用和冲突处理规则已在 Task 02 实测通过。

## 思维链

### A. 确定性选择与领取

1. 读取 catalog，先找可恢复的中断任务，再找 gate/dependency 已满足的 pending Task。
2. 排序固定为 priority 降序、created_at 升序、Task ID 升序。
3. 在 `BEGIN IMMEDIATE` 中再次检查可执行性并创建唯一活动租约与 run，避免检查后竞态。
4. 一次调用只返回一个 Task；无任务时输出每类不可执行原因。

### B. worktree 与基线

5. 每个 Spec 固定 `.worktrees/spec-NNN` 和 `feature/spec-NNN-<slug>`；已存在时验证映射，不重新创建。
6. 通过 `git rev-parse --git-common-dir` 找协调根，不能用 cwd 猜主仓库。
7. 领取后记录分支、HEAD、`git status --porcelain=v1 -z` 与 allowed paths 的初始 hash。
8. worktree 含未归属改动或分支不匹配时停止，禁止自动清理。

### C. 中断与恢复

9. 默认租约 120 分钟，event/complete/fail 刷新；活跃租约不可接管。
10. 无文件变化的过期 run 标 abandoned，Task 可重新领取。
11. 有部分变化的过期 run 保留原 worktree，下一次优先恢复并向 Agent 提供已有改动清单。
12. 三次连续失败或基线无法确认时置 blocked，保留全部尝试摘要。

## 子任务拆分与分派

### 分派 1：`junior-dev` — 选择与租约

**完整 Prompt：**

```text
你是 spec-016 Task 05 分派 1 的 junior-dev。实现确定性 next 选择、原子 claim、租约刷新与过期判断。

只读取：docs/sdd/TASK-PROTOCOL.md、spec-016、Task 05、scripts/sdd_tasks/{documents,store,catalog}.py。

只允许修改：
- scripts/sdd_tasks/selection.py
- scripts/sdd_tasks/leases.py

总改动不超过 150 行；Python 3.9+ 标准库；所有领取必须在 BEGIN IMMEDIATE 中重新检查；同一 Task 最多一个活动租约。排序固定为 recoverable 优先，再 priority 降序、created_at 升序、Task ID 升序。默认租约 120 分钟，时间使用 UTC；禁止使用墙钟差值判断耗时以外的逻辑。

不得创建 worktree、修改业务代码/文档、执行 git commit/push/merge/reset/stash/clean。

用 /tmp SQLite 做两进程竞争、活跃租约拒绝、过期识别、无可执行原因矩阵 smoke。运行 py_compile。结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1 字段。
```

### 分派 2：`junior-dev` — Git worktree 与恢复快照

**完整 Prompt：**

```text
你是 spec-016 Task 05 分派 2 的 junior-dev。实现安全的 spec worktree 准备、执行基线快照和恢复判定。

只读取：docs/sdd/TASK-PROTOCOL.md、spec-016、Task 05、scripts/sdd_tasks/store.py，以及 Task 02 的真实 worktree 证据。

只允许修改：
- scripts/sdd_tasks/workspace.py
- tests/test_sdd_task_workspace.py

总改动不超过 150 行；Python 3.9+ 标准库；测试只用 tempfile Git fixture。

实现：用 git-common-dir 找协调根；每个 spec 映射 .worktrees/spec-NNN 和 manifest 分支；不存在时从明确 base commit 创建，已存在时验证；记录 HEAD、branch、porcelain -z、allowed path hash；判断自 run 开始后的变化；有无部分改动分别给出 recover/requeue 决策。

绝对禁止对真实或 fixture 执行 reset/stash/clean、覆盖文件、push、merge、force push；遇到非预期 dirty path 只返回结构化错误。测试覆盖创建、复用、分支冲突、主工作树 dirty 不受影响、有/无部分改动恢复。

运行新测试和 py_compile；结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1 字段。
```

### 分派 3：`junior-dev` — CLI 领取与恢复入口

**完整 Prompt：**

```text
你是 spec-016 Task 05 分派 3 的 junior-dev。把已完成的 catalog/selection/leases/workspace 组装成最小 CLI，不实现 Task 06 的 Prompt/result/metrics。

只读取：docs/sdd/TASK-PROTOCOL.md、Task 05、scripts/sdd_tasks 已实现模块。

只允许修改：
- scripts/sdd_tasks/cli.py
- scripts/sdd_tasks/__main__.py

总改动不超过 150 行；Python 3.9+ 标准库。

实现命令：doctor、rebuild、status --json、next --claim --ide --executor、recover。stdout 的 JSON schema 固定，诊断写 stderr；成功/无任务/定义无效/活跃租约/工作区冲突使用稳定退出码。next 只领取一个，不渲染最终 Prompt；Task 06 再补。

不得实现 complete/fail/result/metrics，不修改文档、Git 状态或业务代码，不 push/merge/reset/stash/clean。

运行 --help、doctor/status 的 /tmp fixture smoke 和 py_compile；结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1 字段。
```

## 子代理返回后主 Agent 必须执行

1. 读回三批文件并核对每批范围和行数。
2. 在临时 Git fixture 并发执行两次 `next --claim`，确认只有一个成功。
3. 验证真实主工作树的 `git status` 在测试前后完全一致。
4. 验证分支冲突、dirty worktree、活跃租约不会触发清理或覆盖。
5. 回填真实退出码、JSON schema、租约行为与测试结果。

## 实时监控命令

```bash
git worktree list --porcelain
git status --short --branch
python3 -m scripts.sdd_tasks status --json
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
```

## 测试与验收标准

- 选择顺序稳定且一次只领取一个。
- 两进程竞争只能一个成功。
- spec worktree 创建/复用不影响 dirty 主工作树。
- 基线、文件 hash、租约与过期状态可追踪。
- 有部分改动的中断任务只恢复，不自动回滚或重新执行。
- CLI JSON 与退出码可由弱 Agent 机械消费。

## 风险、停止条件与回滚

- worktree 路径或分支映射不唯一：停止并阻塞，不自动重建。
- Git 命令可能清理用户内容：不允许实现该路径。
- 两个 claim 都成功：回 Task 02/04 查事务和约束，不进入 Task 06。
- 回滚为停用 claim/worktree 命令；已有 Markdown Task 不受影响。

## 产出物

- 选择、租约、worktree、恢复和 CLI 模块。
- 隔离 Git fixture 测试。
- 并发领取与主工作树不变的证据。
- 本文件执行结果。

## 执行结果

> 待 Task 04 完成后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 05，状态置待执行 |

