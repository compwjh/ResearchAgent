# 任务 02 — 验证 Task 运行时（Go/No-Go）

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01 ｜ 被依赖：任务 03 ｜ 当前状态：`待执行`

## 一句话目标

在编写正式工具前，用隔离的临时样例证明 SQLite 能原子领取、Markdown 能重建状态、Git worktree 能隔离当前脏工作树，且 Codex/CodeBuddy 都能执行同一个 CLI 协议；任一硬前提失败则 No-Go。

## 当前证据（2026-09-03）

- 系统 `python3` 为 3.9.7、SQLite 3.36.0，JSON1 查询可用；项目 `.venv` 为 Python 3.11.16、SQLite 3.53.4。
- 当前 Git HEAD 为 `294138c`，工作树同时包含 spec-013/014/015 和业务代码的未提交改动，不能把当前目录当作安全实验场。
- `.codebuddy/agents/` 已有四个角色 Agent；当前 Codex 环境也具备子 Agent 编排能力，但二者接口不同。
- `.gitignore` 尚未统一忽略 `.sdd/runtime/` 与 `.worktrees/`。
- 研发 Task 账本尚不存在；已有 `backend/app/services/task_store.py` 只服务论文下载，不能用于本任务。

## 前置门禁

1. spec-016 需求评审、技术评审均通过且用户明确确认。
2. 记录执行时的分支、HEAD、worktree 列表和工作树状态；不得覆盖当前未提交修改。
3. 停止与本任务无关的后台 Agent 写入，确认实验只使用 `/tmp` 或新建的 spec-016 worktree。
4. `ollama list` 再次核实模型；若 `MODEL_REGISTRY.md` 尚无 `qwen3.8:27b-mlx`，先走文档同步门禁再调用对应 Agent。

## 思维链

> 本节记录预先设计的执行顺序与判定依据，不要求执行 Agent 输出隐藏内部推理。

### A. SQLite 原子领取验证

1. 在 `/tmp` 创建最小 SQLite 数据库，启用 WAL、busy timeout 和唯一活动租约约束。
2. 用两个独立 Python 进程同时对同一 Task 执行 `BEGIN IMMEDIATE` 领取。
3. 验证恰好一个进程成功，另一个得到稳定的“已领取”结果，而不是数据库损坏或未处理异常。
4. 验证进程异常退出后，过期租约可识别；活跃租约不可被第二进程接管。

### B. 文档重建验证

5. 在 `/tmp` 写两个最小 Task Markdown 样例及一个 run 摘要，删除测试数据库后重新扫描。
6. 验证任务 ID、持久状态、依赖和历史 run 可恢复；租约与未落盘原始事件明确不可恢复。
7. 制造重复 ID、依赖环、损坏 JSON、状态镜像不一致，确认均被拒绝而非猜测修复。

### C. worktree 隔离验证

8. 基于明确 commit 创建临时 Git 仓库或安全 fixture，验证 `.worktrees/spec-NNN` 形式的 linked worktree 可用。
9. 验证从 linked worktree 能定位主仓库协调目录，且不会把 `.worktrees/`、`.sdd/runtime/` 纳入版本控制。
10. 验证主工作树有未提交文件时，创建隔离 worktree 不覆盖或移动这些文件。

### D. 跨 IDE 协议验证

11. 固定一份 JSON 输出，至少包含 task、run、role、worktree、prompt path、lease 状态。
12. 由 Codex 和 CodeBuddy 各执行一次只读 smoke：读取同一输出、识别目标角色、读取 Prompt、生成符合统一结果 schema 的空操作结果。
13. 任一 IDE 需要专属业务逻辑或无法执行 shell/subagent 调用时，记录差异并判定是否可由薄适配器解决。

## 子代理分派计划

### 分派 1：`tester` — 运行时可行性矩阵

**完整 Prompt：**

```text
你是 spec-016 Task 02 的 tester。目标是在不修改任何仓库 tracked 文件的前提下，验证 SQLite 原子领取、文档重建和 Git worktree 隔离是否可行，并输出 Go/No-Go 原始证据。

只读取：
1. docs/sdd/specs/016-portable-task-ledger.md
2. docs/sdd/plans/016/task-02-validate-task-runtime.md
3. .gitignore
4. backend/app/services/task_store.py（仅用于确认不能复用）

允许写入：
- /tmp/spec016-task-runtime-{{RUN_ID}}/
- .sdd/runtime/runs/{{RUN_ID}}/events.jsonl
- .sdd/runtime/runs/{{RUN_ID}}/result.json

禁止：
- 修改仓库 tracked 文件；修改业务 TaskStore；安装依赖；启动业务服务。
- git reset/stash/clean/checkout 覆盖、push、merge、force push。
- 删除或移动当前工作树中的任何文件。

执行：
1. 记录 Python/SQLite/Git 版本与当前基线。
2. 在 /tmp 编写最小实验，验证两个进程并发领取同一行时只有一个成功。
3. 验证 WAL、唯一租约、过期判断和数据库删除后从 Markdown 样例重建。
4. 验证重复 ID、依赖环、损坏 JSON、状态不一致会失败。
5. 在临时 Git fixture 中验证 repo-local .worktrees/spec-NNN 与共享协调目录，不触碰真实脏工作树。
6. 把逐项命令、退出码、关键输出和 Go/No-Go 写入 result.json。

result.json 必须符合 sdd-run-result/v1，包含：outcome、summary、changed_files、artifacts、commands、tests、decisions、risks、blockers、main_agent_actions、started_at、ended_at、duration_ms、model、token_usage、tool_call_count、log_paths。不可得指标写 null，不得估算。

完成后只回传：Go/No-Go、通过项数量、失败项、result.json 路径、日志路径、主 Agent 下一步。不要粘贴完整日志。
```

### 分派 2：`tech-lead` — Go/No-Go 复核

**完整 Prompt：**

```text
你是 spec-016 Task 02 的 tech-lead。只复核运行时可行性证据，不实现正式工具。

只读取：
1. docs/sdd/specs/016-portable-task-ledger.md
2. docs/sdd/plans/016/task-02-validate-task-runtime.md
3. tester 生成的 .sdd/runtime/runs/{{RUN_ID}}/result.json
4. tester 声明的 /tmp 实验文件与关键命令输出

允许写入：
- .sdd/runtime/runs/{{REVIEW_RUN_ID}}/events.jsonl
- .sdd/runtime/runs/{{REVIEW_RUN_ID}}/result.json

禁止修改任何仓库 tracked 文件、安装依赖、启动业务服务或执行破坏性 Git 命令。

逐项判断：SQLite 是否能保证单领取；数据库能否由文档重建；worktree 是否不触碰脏主工作树；跨 IDE 差异是否只需薄适配器；失败证据是否被保留。HTTP/命令退出 0 不能替代语义检查。

输出明确结论 Go 或 No-Go。No-Go 必须给出阻塞事实、复现命令和应回到 spec 的哪项决策；Go 必须列出正式实现不可违反的强制约束。

result.json 使用 sdd-run-result/v1，固定返回 outcome、summary、commands、tests、decisions、risks、blockers、main_agent_actions、started_at、ended_at、duration_ms、model、token_usage、tool_call_count、log_paths。不可得指标写 null。
```

## 子代理返回后主 Agent 必须执行

1. 读回两个 `result.json`，核对路径存在、JSON 可解析、时间与命令真实。
2. 抽查并发领取结果必须为“一成功、一拒绝”，不能只看两个进程退出码。
3. `git status --short` 确认真实仓库除本 Task 状态回填外没有新增实验文件。
4. 将命令、结果和 tech-lead 结论回填本文件；同步 spec 与 README 状态。
5. No-Go 时 Task 03–09 保持待执行，并将 spec 标记阻塞或退回待确认；不得继续实现。

## 实时监控命令

```bash
git status --short --branch
git worktree list --porcelain
find .sdd/runtime/runs -maxdepth 2 -type f 2>/dev/null
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
```

## 测试与验收标准

- 两个进程并发 claim，只有一个获得活动租约。
- 删除测试 SQLite 后可恢复 Task 持久状态、依赖和 run 摘要。
- 四类无效文档均被稳定拒绝。
- worktree 实验未改变真实主工作树已有文件。
- Codex/CodeBuddy 可消费同一 CLI JSON 与 Prompt/结果 schema。
- tester 与 tech-lead 均给出 Go，才允许开始 Task 03。

## 风险、停止条件与回滚

- 任一并发测试出现双领取、数据库锁死或不可恢复损坏：No-Go。
- worktree 操作触及真实脏工作树：立即停止，保留证据，不自行清理。
- CodeBuddy/Codex 必须依赖无法通用化的私有格式：回 spec 重新划分通用协议与适配器。
- 所有实验限于 `/tmp` 与 `.sdd/runtime/`；失败后不删除证据，由主 Agent 决定清理时机。

## 产出物

- SQLite、Markdown 重建、worktree 和跨 IDE 可行性矩阵。
- tester 与 tech-lead 的结构化结果。
- 本文件中的 Go/No-Go 结论与真实执行记录。

## 执行结果

> 待 spec 评审、确认并执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 02，状态置待执行 |

