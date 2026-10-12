# 任务 04 — 实现 SQLite Task 账本

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03 ｜ 被依赖：任务 05、06 ｜ 当前状态：`完成`

## 一句话目标

实现 Python 3.9+ 标准库 Task 文档解析、schema 校验、依赖图、SQLite 持久化、跨 worktree 扫描、状态查询和可重复 rebuild，为后续领取与执行闭环提供可靠底座。

## 当前证据（2026-09-03）

- 项目没有 `scripts/sdd_tasks/` 包和研发 Task 数据库。
- 现有业务 `TaskStore` 只有单表 JSON payload，无依赖、run、event、artifact 或 lease，不在本任务修改范围。
- Task 03 将产出 `docs/sdd/TASK-PROTOCOL.md`，它是本任务唯一协议输入。
- 系统 Python 3.9.7 可用，故不能使用 `tomllib` 等仅 3.11 内置模块。

## 前置门禁

1. Task 03 已完成并通过合法/非法 fixture 验证。
2. `docs/sdd/TASK-PROTOCOL.md` 的 schema v1、状态枚举和路径发现规则已冻结。
3. 已在 `feature/spec-016-portable-task-ledger` 的 `.worktrees/spec-016` 中执行；主工作树保持原状。
4. 每次 `backend-dev` 分派最多两个文件、150 行；完成一批后主 Agent 必须读回和测试再继续。

## 思维链

### A. 文档领域层

1. 用 dataclass 表示 Task 定义、依赖和校验错误，不绑定 SQLite 行对象。
2. 只解析带明确起止标记的 JSON 元数据块；自由文本仅用于返回给 Agent，不参与状态判断。
3. 对 Task ID、状态、依赖、allowed paths、Prompt 段和返回协议执行确定性校验。
4. 文档 hash 必须排除运行时镜像或按协议固定算法，确保不同 IDE 得到同一值。

### B. SQLite 层

5. 建立 tasks、dependencies、runs、events、artifacts、leases、schema_migrations 表。
6. 启用 WAL、foreign keys、busy timeout；写事务使用 `BEGIN IMMEDIATE`。
7. Task 文档仍是定义与持久状态事实源；数据库只保存索引和运行数据。
8. schema 版本不兼容时停止，禁止静默丢表重建。

### C. Catalog 与 rebuild

9. 通过 `git worktree list --porcelain` 获取主仓库和 linked worktree，不假设当前 cwd 是主工作树。
10. 扫描各 worktree 的 `docs/sdd/plans/*/task-*.md` 与 `docs/sdd/runs/`；相同 Task ID/同 hash 去重，不同 hash 报冲突。
11. 依赖图做缺失节点与环检测，输出完整问题路径。
12. `rebuild` 先验证完整 catalog；已有 DB 在原库单事务合并且保留 WAL、事件及租约，活动租约时拒绝。首次创建以临时库 fsync 后无覆盖发布；失败保留原数据库。

## 子任务拆分与分派

### 分派 1：`backend-dev` — Task 定义与文档解析

**完整 Prompt：**

```text
你是 spec-016 Task 04 分派 1 的 backend-dev。实现 Task schema v1 的 Python 领域对象和 Markdown JSON 元数据解析器。

只读取：docs/sdd/TASK-PROTOCOL.md、docs/sdd/specs/016-portable-task-ledger.md、docs/sdd/plans/016/task-04-sqlite-task-ledger.md，以及一个协议指定的 fixture Task。

只允许修改：
- scripts/sdd_tasks/__init__.py
- scripts/sdd_tasks/documents.py

限制：总改动不超过 150 行；兼容 Python 3.9+；只用标准库；不修改旧 Task、业务代码、模板或数据库；不执行 Git 提交/push/merge/reset/stash/clean。

实现：定位并解析 sdd-task-meta JSON；返回不可变/清晰的 TaskDefinition；校验必填字段、枚举、Task ID、依赖、allowed paths、Prompt 段、占位符白名单和 return schema；错误包含文档路径与字段。提供稳定 task_hash/prompt_hash，禁止解析自由文本状态词。

验证：python3 -m py_compile scripts/sdd_tasks/__init__.py scripts/sdd_tasks/documents.py；用 /tmp 合法、缺 Prompt、损坏 JSON 三个样例做 smoke。

把结构化结果写到 .sdd/runtime/runs/{{RUN_ID}}/result.json，字段必须包含 outcome、summary、changed_files、artifacts、commands、tests、decisions、risks、blockers、main_agent_actions、started_at、ended_at、duration_ms、model、token_usage、tool_call_count、log_paths。可用指标未知时写 null。回传只给摘要和结果路径。
```

### 分派 2：`backend-dev` — SQLite schema 与 catalog/rebuild

**完整 Prompt：**

```text
你是 spec-016 Task 04 分派 2 的 backend-dev。在分派 1 已通过后，实现 SQLite 账本和跨 worktree catalog。

只读取：docs/sdd/TASK-PROTOCOL.md、Task 04、scripts/sdd_tasks/documents.py、git worktree list --porcelain 的真实输出。

只允许修改：
- scripts/sdd_tasks/store.py
- scripts/sdd_tasks/catalog.py

限制：总改动不超过 150 行；Python 3.9+ 标准库；不得导入 backend 业务 TaskStore；不得修改 tracked 文档、旧 Task 或 Git 状态；不 push/merge/reset/stash/clean。

实现：创建 schema_migrations/tasks/dependencies/runs/events/artifacts/leases 表；连接时启用 WAL、foreign_keys、busy_timeout；提供事务上下文；扫描主仓库及 linked worktree；相同 ID 同 hash 去重、不同 hash 报冲突；校验缺依赖和依赖环；rebuild 先构建临时 DB，全部成功后原子替换。不得在 import 时创建数据库。

验证：python3 -m py_compile scripts/sdd_tasks/store.py scripts/sdd_tasks/catalog.py；用 /tmp fixture 验证首次建库、重复 rebuild、冲突 ID、依赖环、失败保留旧 DB。

结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，固定字段同 sdd-run-result/v1：outcome、summary、changed_files、artifacts、commands、tests、decisions、risks、blockers、main_agent_actions、started_at、ended_at、duration_ms、model、token_usage、tool_call_count、log_paths。
```

### 分派 3：`backend-dev` — 单元测试

**完整 Prompt：**

```text
你是 spec-016 Task 04 分派 3 的 backend-dev。只为已经存在的文档解析和 SQLite/catalog 行为补单元测试，不改变生产实现。

只读取：docs/sdd/TASK-PROTOCOL.md、Task 04、scripts/sdd_tasks/{documents,store,catalog}.py 和现有测试风格。

只允许修改：
- tests/test_sdd_task_documents.py
- tests/test_sdd_task_store.py

总改动不超过 150 行；测试全部使用 tempfile，不读写真实 .sdd 数据库，不依赖 Ollama/网络；不修改业务代码或生产模块。

必须覆盖：合法解析、缺字段、损坏 JSON、未知占位符、hash 稳定；schema 建立、rebuild 幂等、重复 ID 冲突、依赖缺失、依赖环、失败保留旧 DB、两个 worktree 的同 hash 去重。

运行两个新测试文件并记录命令、退出码、数量和耗时。结果写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1 字段；不得声称未运行的测试通过。
```

## 子代理返回后主 Agent 必须执行

1. 每批读回实际文件，确认没有越界改动且单批不超过两文件/150 行。
2. 运行 `python3 -m py_compile` 和两个新测试文件。
3. 用独立临时 fixture 重跑 rebuild 两次并比对结果。
4. 检查模块导入不会创建 `.sdd` 或数据库。
5. 回填实际 schema、命令、测试数量、风险和结果；同步三处 Task 状态。

## 实时监控命令

```bash
git diff --stat
find .sdd/runtime/runs -maxdepth 2 -type f 2>/dev/null
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
python3 -m unittest tests.test_sdd_task_documents tests.test_sdd_task_store
```

## 测试与验收标准

- Python 3.9+ 标准库可导入运行。
- Task JSON 元数据和 Prompt/返回协议能稳定校验。
- SQLite schema、版本、WAL、外键和 busy timeout 生效。
- rebuild 幂等；失败不破坏已有数据库。
- 跨 worktree 重复/冲突和依赖环均有确定结果。
- 测试不触碰真实仓库运行数据或业务 TaskStore。

## 风险、停止条件与回滚

- 单模块超过模型可控输出或 150 行：继续拆分，不让主 Agent代写代码。
- 协议与实现产生新字段需求：停止并回 Task 03 修订，不在代码中私自扩展。
- rebuild 可能覆盖有效 DB：已有数据库必须在原库事务内合并且保留历史；首次发布须无覆盖，禁止替换已有 DB/WAL。
- 回滚为停用新包；未启用前不影响现有流程。

## 产出物

- `scripts/sdd_tasks/` 的文档解析、存储与 catalog 底座。
- 两个独立单元测试文件。
- 真实 schema、rebuild 与依赖检查证据。
- 本文件执行结果。

## 执行结果

Python 3.9.25 工具包 89/89 通过，Ruff、编译和 8 组真实 Git/SQLite smoke 均通过。独立评审签署云端 Task04 PASS，无未解决 P0/P1/P2。详见 [验证记录](./artifacts/task04-validation.md) 与 [独立评审](../../reviews/016-task04-review.md)。该结论不含 CodeBuddy 本地验收或后续 CLI 生命周期。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 04，状态置待执行 |


## 本轮执行记录（2026-10-11）

本轮 Task04 自动化实现、测试和独立复评已完成；允许进入 Task05。整体 Spec016 仍实施中，CodeBuddy 本地验证未完成。
