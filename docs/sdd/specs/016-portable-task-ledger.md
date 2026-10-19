# Spec 016 — 可移植 Task 账本与自动执行协议

## 状态

**当前状态：`实施中`**

> 本 spec 只改变项目研发流程与 Agent 编排工具，不改变 ResearchAgent 的业务接口。
> 用户已授权按记录恢复或重做云端 CLI 与测试；独立需求/技术评审通过。真实 CodeBuddy 验收延期本地，Task 02 与 A6 保持未完成，整体 Spec 不提前收口。
> 状态变更须同步追加 `docs/sdd/spec-status-changelog.md`。

## 一句话目标

让 Codex、CodeBuddy 或其他带 Agent 能力的 IDE，都能只依赖项目中的规范文档发现一个可执行的未完成 Task，按预先生成的 Prompt 调用正确子 Agent，安全地记录执行过程并把结果交接给后续 Agent，而无需重新阅读历史聊天或临时补全任务设计。

## 背景与要解决的问题

当前项目已建立 `spec → plans/NNN/README → task-NN.md → reviews` 的 SDD 文档链路，但执行阶段仍存在以下问题：

- Task 是面向人阅读的 Markdown，缺少稳定、可机器解析的元数据；不同 Agent 只能依赖自然语言搜索状态。
- Task 状态同时出现在 spec、README 与 task 文件中，手工同步容易产生不一致。
- 旧 Task 的“Prompt 要点”并不总是可直接分派的完整 Prompt，能力较弱的调度 Agent 仍需重新设计任务。
- 子 Agent 的进展日志位于 `.codebuddy/agent-logs/` 等 IDE 私有目录，换 IDE 后难以恢复执行上下文。
- 当前没有防重复领取、执行租约、失败恢复和统一结果协议；两个 IDE 可能重复执行同一任务。
- 执行耗时、模型、重试、token、工具调用和改动规模没有统一口径，无法长期分析模型与任务拆分效果。
- spec-013～015 已出现“代码有进展、Task 状态仍待执行”的事实差异，直接自动扫描会造成重复实施。

本 spec 采用两层事实模型：

1. **Git 跟踪的 Markdown 文档是长期事实源**：保存 Task 定义、完整执行 Prompt、持久状态与脱敏运行摘要，供任意 IDE 和后续克隆读取。
2. **项目本机 SQLite 是可重建运行层**：保存查询索引、原子领取、租约、详细事件和性能指标；数据库丢失不影响长期项目记录。

这里的“保存在 Git 中”仅指把 Markdown 作为仓库普通文本文件并创建本地 commit，不代表自动上传 GitHub；本 spec 仍禁止自动 push 或合并 `main`。

## 回滚点（Rollback Baseline）

本轮真实基线：`5b1b1d918db8858e848a73da4cee2df54f513ea2`；独立分支 `feature/spec-016-portable-task-ledger`，worktree `.worktrees/spec-016`。原云端未推送提交没有恢复，本轮测试须重新执行。授权与恢复证据见 [recovery-context.md](../plans/016/artifacts/recovery-context.md)。以下表格保留原始设计时的历史基线。

| 项 | 当前值 |
|---|---|
| 工作目录 | `/Users/wjh/ResearchAgent` |
| 当前分支 | `feature/spec-011-knowledge-base-rag` |
| 当前 HEAD | `294138ce9e709d3ed4213b3f1fcb11286f05dbdc` |
| 工作树 | 存在 spec-013/014/015、观测、知识库及其他用户未提交修改 |
| 原流程 | `docs/sdd/00-sdd-spec-template.md` + `docs/sdd/SDD-GATE-CHECKLIST.md` + `.codebuddy/agents/` |

回滚策略：

- 新工具未启用或失败时，继续使用现有 Markdown Task 手工分派流程；业务服务不受影响。
- `.sdd/runtime/task-ledger.sqlite3` 是可删除后重建的运行缓存，但任何清理动作都必须先确认没有活跃租约。
- 016 的实现必须在独立 `feature/spec-016-portable-task-ledger` 分支和 `.worktrees/spec-016` worktree 中进行。
- 不对当前工作树执行 `git reset`、`git stash`、`git clean`、覆盖式复制或其他会丢失既有改动的操作。
- 已生成的运行摘要保留为审计记录；失败回滚不得伪造、覆盖或删除历史失败证据。

## 关键调研结论（已核实的硬事实）

- 当前业务层已有 `backend/app/services/task_store.py`，其 SQLite 表只服务论文下载任务；研发 Task 账本必须使用独立模块、路径和 schema。
- 项目 `.venv` 为 Python 3.11.16，系统 `python3` 为 3.9.7；新的 CLI 必须仅依赖 Python 3.9+ 标准库，不能假定 worktree 中存在 `.venv`。
- 本机 SQLite 3.36.0 已支持 JSON1；Python 3.11 环境中的 SQLite 为 3.53.4。WAL、事务与 JSON 字段足以覆盖 v1，无需 MongoDB 服务。
- `ollama list` 于 2026-09-03 实测存在 `qwen3.8:27b-mlx` 与 `qwen3.5:9b`。`MODEL_REGISTRY.md` 尚未登记 MLX 名称，首次分派前必须先同步模型库，不得让执行配置与真实注册信息长期不一致。
- 当前 `.codebuddy/agents/` 已有 `pm`、`tech-lead`、`junior-dev`、`tester`；Codex 与 CodeBuddy 的子 Agent 调用接口不同，因此 Task 只能声明逻辑角色，由 IDE 适配器完成映射。
- Git 二进制数据库不可有效 review/merge；SQLite 不进入版本控制。可移植性由 Markdown 定义与每次执行的脱敏摘要提供。
- v1 用户已确认：同机共享仓库、一次执行一个 Task、摘要入 Git、完整日志留本地、每个 Spec 自动使用独立 worktree。

## 数据模型

### `TaskDefinition`（Markdown 中的权威定义）

| 字段 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `schema_version` | int | 必填，初始 `1` | Task 协议版本 |
| `task_id` | str | 全仓唯一，如 `spec-016-task-04` | 稳定任务标识 |
| `spec_id` | str | 三位编号 | 所属 spec |
| `title` | str | 必填 | 任务标题 |
| `status` | enum | `pending/blocked/completed/cancelled` | 持久状态唯一事实源 |
| `priority` | int | 默认 `100`，值越大越优先 | 多个任务同时可执行时排序 |
| `created_at` | str | 必填，带时区 ISO 8601 | 同优先级按创建时间排序 |
| `depends_on` | list[str] | 默认空，不得成环 | 跨 Task / 跨 Spec 依赖 |
| `required_gates` | list[str] | 必填 | spec 确认、评审、用户交互等门禁 |
| `agent_role` | str | 必填 | 逻辑角色，不绑定具体 IDE API |
| `required_capabilities` | list[str] | 必填 | read/edit/shell/subagent 等能力 |
| `allowed_paths` | list[str] | 必填 | 本次允许修改的文件/目录边界 |
| `worktree` | object | 必填 | 分支、worktree 模式与基线规则 |
| `max_attempts` | int | 默认 `3` | 连续失败上限 |
| `prompt_version` | int | 初始 `1` | Prompt 修改时递增 |
| `return_schema` | str | `sdd-run-result/v1` | 子 Agent 回传协议 |
| `expected_artifacts` | list[str] | 可为空 | 必须存在的输出 |
| `validation_commands` | list[str] | 可为空 | 完成前必须执行的验证 |

Task 文件顶部保存一个有明确起止标记的 JSON 元数据块。CLI 只修改该块，不解析自由文本中的状态词。spec 与 README 的状态表是自动生成镜像，发现不一致时必须拒绝领取。

### `TaskRun`

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | str | 一次尝试的唯一 ID |
| `task_id` / `attempt` | str / int | 对应 Task 与尝试序号 |
| `state` | enum | `claimed/running/succeeded/failed/blocked/abandoned` |
| `ide` / `executor_id` | str | Codex、CodeBuddy 或其他执行器身份 |
| `agent_role` / `model` | str | 实际角色与实际模型；不可得时为空并注明来源 |
| `worktree` / `branch` / `base_commit` | str | 执行基线 |
| `task_hash` / `prompt_hash` | str | 防止执行中 Task 被静默替换 |
| `claimed_at` / `started_at` / `ended_at` | datetime | ISO 8601，带时区 |
| `duration_ms` | int | 调度器墙钟耗时 |
| `result_doc` | str | Git 跟踪的脱敏摘要路径 |
| `error_code` / `error_summary` | str | 失败或阻塞原因 |

### `TaskEvent`

按 `run_id + sequence` 追加记录时间、事件类型与 JSON payload。事件只写“观察、证据、决策依据、动作、结果、下一步”，不要求或保存模型隐藏的完整内部思维链。

### `TaskArtifact`

记录 `run_id`、相对路径、类型、SHA-256、Git 状态与是否纳入本次提交；绝对路径不得进入 Git 摘要。

### `TaskLease`

每个 Task 同时最多一条活动租约，包含 owner、领取时间、刷新时间和过期时间。默认租约 120 分钟，每次 `event/complete/fail` 自动刷新；恢复前必须核对进程、worktree 和未提交改动。

## 端点 / 接口

统一入口为零第三方依赖 CLI：`python3 -m scripts.sdd_tasks`。

| 命令 | 输入 | 成功返回 | 失败行为 |
|---|---|---|---|
| `doctor` | repo/worktree | schema、依赖、镜像、敏感信息检查 | 非零退出并列出阻塞项，不修改 tracked 文件 |
| `rebuild` | 可选 `--all-worktrees` | 从 Task 与 run 摘要重建 SQLite | 文档冲突/重复 ID 时停止，不猜测 |
| `status` | 可选 `--json` | 可执行、等待、运行、阻塞、完成列表 | 数据库缺失时提示先 rebuild |
| `next --claim` | `--ide`、`--executor`、`--owner-pid`（持久执行器进程的正整数 PID） | 原子领取一个 Task，返回 run/worktree/角色/Prompt 路径 | 无可执行项时返回原因矩阵，不改变 Task；执行器 PID 不可确认时拒绝领取 |
| `event` | `--run-id`、`--executor`、`--owner-pid`、`--type`、`--payload-json` | 追加 observation/evidence/decision/action/result/next_step 之一并刷新租约 | run/owner 不匹配或 payload 不安全时拒绝 |
| `complete` | `--run-id`、`--executor`、`--owner-pid`、`--result` | 校验结果、生成摘要、同步状态、本地 commit | 越界改动、测试失败或 hash 漂移时拒绝提交 |
| `fail` | `--run-id`、`--executor`、`--owner-pid`、`--result` | 保存失败摘要，按改动情况决定重试或保留恢复 | 第三次连续失败将 Task 置 blocked |
| `recover` | run 或 task | 恢复过期/中断任务 | 活跃 owner 或基线不明时拒绝接管 |
| `result` | `--run-id`、`--json` | 返回 ledger terminal summary 中完整且已验证的 sdd-run-result/v1 | 结果未可用时返回稳定 `RESULT_NOT_AVAILABLE`；只读，不需 owner 身份 |
| `metrics` | 时间/角色/model/filter、`--format` | JSON 或 CSV 指标 | 缺失字段保留 null，不伪造数据 |

`next --claim` 的固定选择顺序：可恢复的中断任务优先；之后选择所有门禁和依赖已满足的 `pending` Task，按 priority 降序、创建时间升序、Task ID 升序排列，一次只返回一个。

## 边界（每条之后会变成一条测试）

- Spec 为 `待确认`：Task 可以被扫描和展示，但不能被领取。
- 依赖未完成或形成环：阻止领取，并返回完整依赖路径。
- Task 缺少 JSON 元数据、完整 Prompt、返回协议或 allowed paths：标记定义无效，不允许弱调度器补写。
- 两个 IDE 同时领取同一 Task：SQLite `BEGIN IMMEDIATE` + 唯一活动租约保证只有一个成功。
- SQLite 不存在或损坏：从主仓库和全部已登记 worktree 的 Markdown 重建；不能从摘要恢复的瞬时字段保持为空。
- Task 文档在运行中被修改：task hash 或 prompt hash 不一致，停止 finalize 并要求架构师判断。
- Agent 中断但没有文件变化：租约过期后允许重新领取，保留 abandoned 尝试摘要。
- Agent 中断且已有文件变化：不得自动清理；优先恢复原 worktree，并把改动清单交给下一执行者。
- 子 Agent 返回“完成”但没有结果 JSON/产物：视为失败，不相信文字摘要。
- 改动包含 allowed paths 外文件：停止提交并标记 `out_of_scope_changes`，不自动回滚。
- validation command 非零：不得完成 Task 或创建成功提交。
- IDE 没有目标子 Agent/工具能力：标记 `executor_unavailable` 并阻塞，不由弱调度器代写。
- 需要登录、权限、验证码、安装或其他用户参与：暂停租约并向用户请求，不伪造成功。
- 日志或结果疑似含密码、Cookie、Token、Authorization：拒绝写入 Git 摘要，先生成脱敏版本。
- token、模型耗时或工具计数不可得：写 null 和来源说明，不通过估算伪造。
- 完成成功 Task：只暂存声明文件、Task 状态镜像和 run 摘要，创建本地原子 commit；不 push、不合并。

## 明确不做（划出范围，防 AI 自由发挥）

- 不引入 MongoDB、PostgreSQL、Redis 或常驻调度服务。
- 不做跨机器并发和远程租约；v1 只保证同机共享仓库。
- 不建设 Web 管理页、看板或业务 API。
- 不复用或修改论文下载业务的 `backend/app/services/task_store.py`。
- 不保存模型隐藏的完整内部思维链；只保存可审计的执行依据与事件。
- 不把 SQLite、完整原始日志、worktree 或敏感信息提交进 Git。
- 不让弱调度 Agent 修改 Task、改写 Prompt、扩大范围或选择新的技术方案。
- 不自动 push、开 PR、合并 `main`、force push、reset、stash、clean 或删除用户文件。
- 不在本 spec 顺手完成 spec-013/014/015 的业务代码；Task 08 只做事实对账和协议迁移。

## 验收方式

| 验收点 | 验证方法 |
|---|---|
| A1 文档自足 | 新 IDE 只读 spec、README、Task 和 run 摘要，可说明当前进度、下一任务、所需角色和完成条件 |
| A2 Prompt 完整 | `doctor` 对缺少完整 Prompt/返回协议/路径边界的 Task 返回失败；合法 Task 可直接生成分派 Prompt |
| A3 单任务选择 | 多个 Task 并存时 `next --claim` 按固定规则只返回一个正确 Task |
| A4 防重复领取 | 两个独立进程同时 claim，同一 Task 只有一个成功 |
| A5 门禁有效 | 未确认 spec、未完成依赖、未对账 legacy Task 均不可领取 |
| A6 跨 IDE | Codex 与 CodeBuddy 分别用同一句“执行目前未完成的 Task”完成发现、分派和结果回填 |
| A7 结果闭环 | 子 Agent 的文件、测试、风险、主 Agent 待办和耗时进入统一结果；Task 与索引状态同步 |
| A8 越界保护 | allowed paths 外改动或失败测试阻止完成与提交，且不自动回滚用户内容 |
| A9 中断恢复 | 无改动与有部分改动两种中断都能保留证据并按规则恢复 |
| A10 可重建 | 删除测试用 SQLite 后，`rebuild` 从 Markdown 恢复全部持久 Task 状态和 run 摘要 |
| A11 指标导出 | metrics 可按 Task/角色/model/结果导出耗时、重试、token、工具调用、文件和行数，缺失值不伪造 |
| A12 Git 边界 | 成功任务只创建本地原子提交，不 push/合并；SQLite、原始日志和 worktree 均未进入提交 |
| A13 Legacy 对账 | spec-013～015 已完成/部分完成/未验证状态均有证据，不重复执行已完成工作 |
| A14 回归 | ResearchAgent 既有测试与运行时行为不受流程工具影响 |

## 产品使用步骤

评审者：protocol_review
评审角色：architect
评审模型：gpt-6-luna xhigh
分派方式：collaboration.spawn_agent

## 旅程 1：强 Agent 规划并落盘

架构师/规划 Agent 读取 Spec、README、已有 Task 与真实证据，填写版本化 metadata、完整 Prompt、角色、allowed_paths、validation commands、依赖和结果 schema。解析器拒绝缺字段/缺完整 Prompt；状态镜像由权威 Task 状态生成。用户可审阅 Task，而不必从历史聊天猜测执行范围。

映射：A1 文档自足；A2 Prompt 完整；A5 gate；A13 legacy 对账。

## 旅程 2：用户确认并开放执行

用户审阅需求/技术评审与验收界限，确认后留下可核实 gate 记录。用户本轮明确允许云端 CLI 和测试先执行，真实 CodeBuddy 验收延至本地；系统因此允许 Task03/04 按 cloud-stage gate 进行，但保留 Task02/A6 的待完成状态。未满足的用户参与、登录或本地 IDE gate 会阻止对应阶段领取，不生成虚假通过。

映射：A5 gate；A6 双 IDE；A12 Git 边界；A14 回归。

## 旅程 3：弱调度器领取并分派一个 Task

Codex、CodeBuddy 或其他获准 CLI 执行器调用 status/next。SQLite 原子事务重新校验文档 hash、状态、depends_on、required_gates 和 lease，按固定排序只返回一个 Task；CLI 返回固定 JSON 和预生成 Prompt 路径。执行角色通过 IDE 适配器映射到当下可用的逻辑角色（本工具后端工作为 backend-dev），调度器不改写 Prompt、不扩路径、不补协议字段。

映射：A2 Prompt 完整；A3 单任务选择；A4 防双领；A5 gate。

## 旅程 4：换 IDE 查看结果

另一 IDE 通过 docs/sdd/runs 中 Git 跟踪的脱敏 summary 和 Task/spec/README 状态镜像了解完成项、证据、风险和主 Agent 待办；如果本机 SQLite 不存在，可以从 Task 与合法 summary rebuild。原始 events 和 lease 是本机运行数据，丢失后保持未知，不会从 summary 伪造。metrics 对不可得值显示 null/source。

映射：A1 文档自足；A7 结果闭环；A10 可重建；A11 指标；A12 Git 边界。

## 旅程 5：执行器中断并恢复

心跳/事件刷新 120 分钟 lease。租约过期后，恢复器先确认原 owner 进程已结束，再核对 worktree、base、Task/Prompt hashes 和 dirty path。无改动 run 可标记 abandoned 并重排；有部分改动时保留原 worktree 并提供文件清单恢复；任何 hash/path/ref 冲突都留住 journal 与改动，返回 blocker，不自动清理或回滚。

映射：A4 防重复领取；A7 结果闭环；A8 越界保护；A9 中断恢复；A10 rebuild。

## 全部验收映射

- A1：旅程1、4
- A2：旅程1、3
- A3：旅程3
- A4：旅程3、5
- A5：旅程1、2、3
- A6：旅程2（当前待本地 CodeBuddy 实测）、3
- A7：旅程4、5
- A8：旅程5
- A9：旅程5
- A10：旅程4、5
- A11：旅程4
- A12：旅程2、4
- A13：旅程1
- A14：旅程2

以上为产品流程与验收关联，不替代各 Task 的可复现实测结果或用户尚未执行的本地 CodeBuddy 验收。


## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent） | 200k | 主会话 | 编排、修订文档、读回校验与决策 |
| 文档更新 doc-updater | gpt-6-luna，xhigh（用户明确指定，Codex覆盖） | 32k | Codex 子 agent | 产品旅程、legacy证据与交接 |
| 独立评审 architect | gpt-6-luna，xhigh（用户明确指定，Codex覆盖） | 32k | Codex 子 agent | 需求/技术/安全评审及验收签字 |
| 工具开发 backend-dev | gpt-6-luna，xhigh（用户明确指定，Codex覆盖） | 32k | Codex 子 agent | 本 Spec 的 scripts 工具范围；每分派最多2文件150行 |
| 独立测试 tester | gpt-6-luna，xhigh（用户明确指定，Codex覆盖） | 32k | Codex 子 agent | Python3.9、并发、恢复、回归和真实运行 |
| 前端开发/测试 | 不适用（本 Spec 无前端改动） | — | — | — |
| 弱调度执行器 | 调用方实际已注册模型 | 16k | sdd-run-next-task skill | 只按冻结协议领取、分派、回填 |

本轮角色名称按现行框架映射；项目 CodeBuddy 模型默认值不修改。Task 03/04 的云端阶段依据用户授权与 [独立技术评审](../reviews/016-tech-review.md) 执行，不伪造 Task 02 双 IDE Go。冻结接口及强制安全条件见 [TASK-PROTOCOL.md](../TASK-PROTOCOL.md)。

## 任务计划

> 任务 01 = 本 spec 的编写，由架构师完成，不重复创建 Task 01。
> Task 02–09 的完整思维链、子 Agent Prompt、回传协议与执行结果位于 `docs/sdd/plans/016/`。

| 编号 | 任务 | 思维链文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-016 与任务计划 | 本文件 | — | 完成 |
| 02 | 验证 Task 运行时（Go/No-Go） | [`task-02-validate-task-runtime.md`](../plans/016/task-02-validate-task-runtime.md) | 01 | 进行中（CodeBuddy待本地） |
| 03 | 定义 Task 文档与 Prompt 协议 | [`task-03-task-document-contract.md`](../plans/016/task-03-task-document-contract.md) | 云端阶段授权 + Task02前置证据 | 完成 |
| 04 | 实现 SQLite Task 账本 | [`task-04-sqlite-task-ledger.md`](../plans/016/task-04-sqlite-task-ledger.md) | 03 | 完成 |
| 05 | 实现领取、worktree 与恢复 | [`task-05-claim-worktree-recovery.md`](../plans/016/task-05-claim-worktree-recovery.md) | 04 | 完成 |
| 06 | 实现 Prompt、结果与指标闭环 | [`task-06-prompt-result-metrics.md`](../plans/016/task-06-prompt-result-metrics.md) | 04, 05 | 完成（云端 CLI） |
| 07 | 创建 Codex/CodeBuddy 跨 IDE Skills | [`task-07-cross-ide-skills.md`](../plans/016/task-07-cross-ide-skills.md) | 06 | 云端完成；CodeBuddy 待本地 |
| 08 | 对账并迁移 spec-013～015 | [`task-08-reconcile-legacy-tasks.md`](../plans/016/task-08-reconcile-legacy-tasks.md) | 07 云端范围 | 进行中 |
| 09 | 评审、验收、提交与复盘 | [`task-09-review-acceptance-retro.md`](../plans/016/task-09-review-acceptance-retro.md) | 08 | 进行中 |

## 评审记录

- 需求评审：`docs/sdd/reviews/016-requirement-review.md`（2026-10-11 独立评审通过云端阶段；完整双 IDE 验收未完成）
- 技术评审：`docs/sdd/reviews/016-tech-review.md`（2026-10-11 独立评审通过云端阶段；完整双 IDE 验收未完成）
- 验收评审：`docs/sdd/reviews/016-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 用户 | 提出跨 Agent/IDE 的 Task 落盘、自动发现执行、子 Agent Prompt、结果回填与执行指标需求 |
| 2026-09-03 | 用户 | 确认 v1 采用同机共享仓库、一次一个 Task、Git 保存脱敏摘要、SQLite 保存完整运行数据、每个 Spec 自动独立 worktree |
| 2026-09-03 | 用户 | 确认方案内容，并要求参照 spec-013 格式先落盘 Spec 016 与全部 Task 文件 |
| 2026-09-03 | 架构师（自身） | 核实当前基线、现有 Task/Agent/SQLite 结构与本机模型，创建本 spec，状态置待确认 |
| 2026-10-11 | 用户 / 架构师 | 按先前授权重做云端范围，恢复真实Git基线；独立需求/技术评审通过，状态转实施中，CodeBuddy延期本地 |

---
**六条自检**：①每条边界均可变成测试；②spec 描述“做什么”，task 承载“怎么做”；③Task 02–09 链接真实且依赖无环；④Git 文档与 SQLite 的事实边界明确；⑤执行配置包含全部角色、模型与上下文；⑥A1–A14 可由产品步骤和验收报告逐项映射。
**收口自检**：三份评审真实落盘、Task 状态一致、状态台账已追加、legacy 对账完成、复盘存在、运行时验证通过后才可转已完成。

