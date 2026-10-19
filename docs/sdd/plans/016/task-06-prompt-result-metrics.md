# 任务 06 — 实现 Prompt、结果与指标闭环

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04、05 ｜ 被依赖：任务 07 ｜ 当前状态：`完成（云端 CLI 范围）`

## 一句话目标

把 Task 内预生成 Prompt 渲染成可直接分派的运行文件，持续记录结构化事件，校验子 Agent 结果，生成 Git 跟踪的脱敏摘要与本地原子提交，并提供统一结果和指标导出。

## 当前证据（2026-09-03）

- 当前子 Agent 只需回传自然语言摘要和 `.codebuddy/agent-logs` 路径，没有跨 IDE 结果 schema。
- Task 03 将固定 Prompt 与 `sdd-run-result/v1`；Task 04/05 将提供 store、run、lease、worktree 和 CLI。
- 用户选择“摘要入 Git、完整事件留本地”，因此两类数据必须分开生成。
- 当前 spec 级 commit 纪律允许本地提交，但禁止 push/merge；Task 完成提交必须只包含声明范围。

## 前置门禁

1. Task 04/05 全部单测和两进程领取验证通过。
2. `sdd-run-result/v1` 和敏感字段规则已在 Task 03 冻结。
3. 使用隔离 spec-016 worktree；开始 run 前已记录基线和已有 dirty 集合。
4. 提交策略固定：成功 run 生成原子实现提交；失败/阻塞 run 只生成文档证据提交，部分代码保持未暂存并等待恢复。

## 思维链

### A. Prompt 渲染与事件

1. 从 Task 固定 Prompt 段读取原文，只替换白名单运行变量。
2. 将渲染 Prompt 写入 `.sdd/runtime/runs/<run-id>/prompt.md`，保存 task/prompt hash；不复制 secrets 或环境变量。
3. `event` 只接受结构化类型和 JSON payload，自动加 UTC 时间、sequence 并刷新租约。
4. 同时写 SQLite 与本地 JSONL；SQLite 写失败时不得伪造成功。

### B. 结果校验与摘要

5. 子 Agent 把 `sdd-run-result/v1` 写入本地 result.json，文字回传不作为完成依据。
6. 校验必填字段、时间、退出码、产物存在、allowed paths、Task/Prompt hash 与基线变化。
7. 生成 `docs/sdd/runs/NNN/task-NN/<run-id>.md`，只包含脱敏摘要、相对路径和可验证证据。
8. `complete` 更新 Task 权威状态及 spec/README 镜像，运行校验后只 stage allowed paths + 状态/摘要文档并本地 commit。

### C. 失败、结果查询与指标

9. fail 保存原因；无改动时释放为可重试，有部分改动时保留恢复；第三次失败 blocked。
10. `result --json --run-id <uuid>` 只读返回已完成 ledger summary 中完整且已验证的 sdd-run-result/v1，不让 IDE 解析 Markdown；terminal result 可由新 owner 会话读取。
11. metrics 从 run/event/artifact 导出 JSON/CSV；模型/token/tool count 缺失为 null，并保存来源。
12. 敏感扫描命中时拒绝写 Git 摘要与提交，要求生成脱敏 result。

## 子任务拆分与分派

### 分派 1：`junior-dev` — Prompt 与结果校验

**完整 Prompt：**

```text
你是 spec-016 Task 06 分派 1 的 junior-dev。实现白名单 Prompt 渲染与 sdd-run-result/v1 校验。

只读取：docs/sdd/TASK-PROTOCOL.md、spec-016、Task 06、scripts/sdd_tasks/{documents,store,workspace}.py。

只允许修改：
- scripts/sdd_tasks/prompts.py
- scripts/sdd_tasks/results.py

总改动不超过 150 行；Python 3.9+ 标准库。

Prompt：只允许替换 RUN_ID、WORKTREE、BASE_COMMIT、RESULT_PATH、EVENT_PATH；未知/缺失占位符失败；写入 runtime 后返回 hash。结果：校验 schema/version/必填字段/时间/退出码/相对路径；对照 workspace 快照计算本 run 变更，拒绝 allowed paths 外文件和不存在产物；不可得指标允许 null，不允许字符串伪装数值。

不得修改 Task、Git 状态、业务代码或实现提交；不读取环境变量值写入结果；不 push/merge/reset/stash/clean。

用 /tmp 覆盖合法渲染、未知占位符、hash 漂移、缺字段、越界文件、空指标。运行 py_compile。结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1。
```

### 分派 2：`junior-dev` — 事件、run 摘要与指标

**完整 Prompt：**

```text
你是 spec-016 Task 06 分派 2 的 junior-dev。实现结构化事件、本地 JSONL、Git run 摘要和 metrics 导出，不实现 Git commit。

只读取：docs/sdd/TASK-PROTOCOL.md、Task 06、scripts/sdd_tasks/{store,results}.py。

只允许修改：
- scripts/sdd_tasks/run_docs.py
- scripts/sdd_tasks/metrics.py

总改动不超过 150 行；Python 3.9+ 标准库。

实现：event 自动 UTC 时间/sequence 并刷新租约；SQLite 与 .sdd/runtime/runs/<run>/events.jsonl 同步；run_docs 从已验证 result 生成 docs/sdd/runs/NNN/task-NN/<run>.md；只允许相对路径，执行敏感模式扫描；metrics 按 task/role/model/outcome/time 导出 JSON/CSV，缺失值为空且带 source。

摘要不得包含密码、Cookie、Authorization、Token、环境变量值、绝对个人路径或完整原始命令输出；不得读取/修改业务代码、Task 状态或 Git；不 push/merge/reset/stash/clean。

用 tempfile 验证事件顺序、重复写、摘要脱敏、相对路径、CSV/JSON 和 null 指标。结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1。
```

### 分派 3：`junior-dev` — CLI 完成/失败/查询闭环

**完整 Prompt：**

```text
你是 spec-016 Task 06 分派 3 的 junior-dev。把 Prompt、event、complete、fail、result、metrics 接入现有 CLI，并补闭环测试。

只读取：docs/sdd/TASK-PROTOCOL.md、Task 06、scripts/sdd_tasks 已实现模块、tests/test_sdd_task_claim.py。

只允许修改：
- scripts/sdd_tasks/cli.py
- tests/test_sdd_task_lifecycle.py

总改动不超过 150 行；Python 3.9+ 标准库；测试使用 tempfile Git repo。

next --claim 成功后写 rendered prompt 并返回路径/hash。新增 `event --run-id <uuid> --executor <id> --owner-pid <pid> --type <observation|evidence|decision|action|result|next_step> --payload-json <object>`、`complete --run-id <uuid> --executor <id> --owner-pid <pid> --result <path>`、`fail --run-id <uuid> --executor <id> --owner-pid <pid> --result <path>`、`result --json --run-id <uuid>`、`metrics --format json|csv`。event/complete/fail 要求 owner PID 指向持久执行器进程；CLI 以 executor/PID/process-start identity 核验 owner，从本地账本取 token；token 不得作为命令参数、输出或日志。result/status/metrics 只读、不需 owner principal；result 只返回 ledger terminal summary 中完整且已验证的 sdd-run-result/v1，没有可用 summary 时返回 `RESULT_NOT_AVAILABLE`，不信任 runtime result.json。complete/fail 都实际运行 `validation_runner.run_validations`；complete 用 runner 的实际 commands 覆盖 draft 并仅在所有命令成功、结果/工作区重验通过后完成，fail 记录真实命令结果及失败摘要。commands 和时间戳不信任 actor 输入；complete 时 started_at 来自首个 owner event（无 event 则 claimed_at），ended_at/duration_ms 来自完成重验时的服务端 UTC 时钟。禁止 push/merge/reset/stash/clean。fail 有变化保留恢复，无变化可重试，第三次 blocked。

测试覆盖成功闭环、越界、测试失败、敏感摘要、hash 漂移、三次失败、有/无部分改动、只提交允许路径、没有 push。记录实际命令与退出码到 result.json。
```

## 子代理返回后主 Agent 必须执行

1. 读回所有生产与测试文件，确认每批范围和行数。
2. 在临时 Git fixture 走完 `rebuild → next --claim --ide <id> --executor <id> --owner-pid <persistent-executor-pid> → event → complete → result → metrics`；owner PID 必须是持久执行器进程，不是短命 CLI 子进程。
3. 检查成功 commit 的 staged/committed 文件与 allowed paths 完全一致，远端引用未变化。
4. 分别注入 secret、越界文件、失败测试、hash 漂移和第三次失败，核对停止行为。
5. 删除 fixture SQLite 后 rebuild，确认 Task/run 摘要恢复且租约不伪造。
6. 回填真实结果、命令、commit 和风险。

## 实时监控命令

```bash
python3 -m scripts.sdd_tasks status --json
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
git status --short --branch
git diff --cached --name-status
git log -1 --stat --oneline
```

## 测试与验收标准

- Task 内 Prompt 可无人工改写地生成运行 Prompt，hash 稳定。
- 文字“完成”但缺 result.json 不会完成 Task。
- result、文件、产物、测试与 allowed paths 全部验证后才提交。
- Git 摘要脱敏且可由数据库重建读取。
- result JSON 包含主 Agent 所需完整交接。
- metrics 的时间、重试、模型、token、工具与变更规模可筛选导出。
- 失败、中断、第三次 blocked 与部分改动恢复符合 spec。

## 风险、停止条件与回滚

- CLI 在校验完成前改 Task 状态或提交：立即打回。
- 为了方便而执行 `git add -A`：禁止，必须逐路径暂存。
- 敏感扫描存在漏报样本：补规则与测试后才能通过。
- 回滚为禁用 complete/fail 命令；已有 run 摘要和 Task 文档保留。

## 产出物

- Prompt、result、run_docs、metrics 和 CLI 闭环实现。
- 生命周期与 Git fixture 测试。
- 成功、失败、阻塞、脱敏、rebuild 的可复现证据。
- 本文件执行结果。

## 执行结果

实现与测试：Luna xhigh 子 Agent；root 负责分派、逐片读回和纯文档回填。

- Prompt、事件、结果校验、指标、complete/fail/recover CLI、journal/CAS/精确 index 协调及终态账本全部接通。
- 失败来源与中断重试保留原始 baseline，领取只消费紧邻来源；status 与 next 使用一致证明。独立评审发现的状态 P1 已修复，未放宽 owner/租约/路径/摘要校验。
- Python 3.9 工具域原候选 `281e933` 的 379 项通过；迁移镜像兼容修复 `37bb056` 后最终 382 项通过（153.440 秒，退出 0），镜像定向 10 项通过；Ruff、compileall 均通过。原失败和修复记录完整保留。
- 真实 Luna actor 完成隔离 Task、CLI complete、result/metrics 和删除隔离 DB 后 rebuild，重建后不再领取；另有真实进程中断和 Git journal/index 多阶段恢复测试。
- 独立 Task06 架构复审 PASS。此结果不代替业务全量回归或真实 CodeBuddy A6 验收。

证据：[最终工具域 QA](./artifacts/task06-final-tool-tests.md)、[独立复审](../../reviews/016-task06-review.md)、[真实 Luna 示例](./artifacts/live-luna-demo.md)。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 06，状态置待执行 |
| 2026-10-19 | root（纯文档回填） | 依据 Luna 独立 QA 与架构复审回填云端完成；整体 Spec 保留 CodeBuddy 本地门禁 |

