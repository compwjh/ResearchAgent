# 任务 13 — 固化全局目录协议与复用审计

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、05、11、12；被依赖：任务 14、17
> 当前状态：`完成`
> 主 Skill：`.agents/skills/usenix-paper-catalog-search/SKILL.md`（本任务不调用下载版 Skill）

## 一句话目标

在不重写既有安全下载、导入、批任务和向量能力的前提下，完成可执行的复用审计，并把 SQLite schema v2、领域模型、迁移与仓储契约固定下来。

## 当前证据

- 当前成果位于 `feature/spec-015-security-paper-discovery@c17c7f4` 之后的未提交工作树；全量回归为 `552 passed, 5 warnings, 38 subtests`。
- 当前 Spec015 成果检查点 commit 尚未创建。开始本任务前，主 Agent 必须先创建仅含 Spec015 的本地 commit，并排除全部 Spec017 文件。
- `paper_download.py`、`paper_download_security.py`、`paper_import.py`、批任务状态机和身份规范化已有测试覆盖，不能复制重做。
- 当前 `paper_discovery_store.py` 以搜索会话和候选副本为中心；它的 WAL、外键、事务和迁移方式可以复用，但新搜索必须以全局目录为权威。
- Spec015 的“现有实现复用与替换边界”是本任务的规范来源；聊天内容不是下游输入。

## 前置门禁

1. Task13–17 的需求复审、技术复审及用户确认均通过；否则只允许评审，不允许修改代码。
2. 主 Agent 记录分支、HEAD、工作树、暂存区和现有数据库 schema；禁止覆盖当前用户修改。
3. 基线 commit 的暂存清单不得包含 `docs/sdd/specs/017-*`、`docs/sdd/plans/017/**`、`docs/sdd/reviews/017-*`。
4. 先生成 `docs/sdd/reviews/015-task13-reuse-audit.md`；审计缺少调用者或测试证据时停止编码。
5. 使用本地 Ollama junior-dev 时，每次分派最多修改 2 个代码文件、约 150 行；线上模型不受数量上限，但仍按切片验证。

## 数据、配置与接口增量

- SQLite schema 由 v1 升到 v2，新增 `source_fetch_units`、`catalog_papers`、`catalog_source_records`、`search_jobs`、`search_source_progress`、`search_events`、`search_results`。
- 表字段、状态枚举、唯一约束、外键与 `metadata_hash` 行为以 Spec015 “SQLite schema v2”章节为准，不允许执行者临时改名或省略。
- v1 的会议配置与导入表原地保留；旧搜索候选仅做可重复迁移和兼容读取，不再承接新搜索写入。
- 本任务不新增 HTTP 路由、不访问外部网络、不创建 Qdrant collection。

## 思维链（可观察执行阶段）

1. 盘点每个必须复用模块的公开符号、调用者、测试和缺口，形成逐项审计表。
2. 将 schema v2 的类型和状态迁移写成纯领域契约，确认 domain 不依赖 FastAPI/httpx/Qdrant。
3. 在现有 store 的连接、PRAGMA、事务和 schema 迁移框架内增加 v2，不另建数据库或连接管理器。
4. 逐项实现抓取单元领取/恢复、目录 upsert、来源记录、搜索任务/进度/事件、冻结结果的最小仓储方法。
5. 使用临时 v1 数据库执行升级、重复升级、失败回滚和并发领取测试；确认旧导入历史不丢失。
6. 读回 diff 对照复用审计，发现重复实现立即停止。

## 子任务拆分与子 Agent 分派

### A：复用审计与 schema 设计复核

- 角色：`tech-lead`；模型：`qwen3.8:27b-mlx`；只读代码，允许写审计文档。

```text
你是 tech-lead，使用 qwen3.8:27b-mlx。执行 Spec015 Task13 的实现前复用审计，不修改代码。
只读取：docs/sdd/specs/015-security-paper-discovery.md 的“现有实现复用与替换边界”“SQLite schema v2”章节、docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md，以及其中明确列出的现有模块和对应 tests/test_paper_*.py、tests/test_kb_services.py。
允许修改：仅 docs/sdd/reviews/015-task13-reuse-audit.md；日志可写 .codebuddy/agent-logs/tech-lead-spec015-task13-<timestamp>.md。
禁止：修改任何代码/配置；扫描 Spec017；执行网络请求；git add/commit/reset/stash/clean；提出第二套下载、安全、导入、批任务、身份或 embedding 实现。
完成状态：审计文档逐项列出当前模块、可复用符号、调用者、测试、明确缺口、处理方式（原样/参数化/替换）和禁止重复实现项；schema v2 字段/约束无未决设计。
必须验证：rg 检查每个引用路径存在；git diff --check -- docs/sdd/reviews/015-task13-reuse-audit.md。
结果路径：docs/sdd/reviews/015-task13-reuse-audit.md。
固定返回字段：结果状态和摘要；改动文件；验证命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
信息不足必须标记阻塞，不得自行补设计。
```

### B：领域模型与 schema v2 迁移

- 角色：`junior-dev`；模型：`qwen3.8:27b-mlx`。

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现 Spec015 Task13 的领域类型和 SQLite schema v2 迁移切片。
只读取：docs/sdd/specs/015-security-paper-discovery.md 的复用/schema v2 章节、docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md、docs/sdd/reviews/015-task13-reuse-audit.md、backend/app/domain/paper_discovery.py、backend/app/services/paper_discovery_store.py、tests/test_paper_discovery_store.py。
允许修改：使用本地 Ollama 时仅 backend/app/domain/paper_discovery.py、backend/app/services/paper_discovery_store.py，约 150 行；若测试无法在该限制内补齐，先返回代码和测试缺口，由主 Agent拆出下一分派。线上模型可同时修改对应测试，但不得修改其他模块。
禁止：新建数据库连接层；删除/重命名 v1 表；改导入表语义；执行外部请求；git add/commit/reset/stash/clean；触碰 Spec017。
完成状态：schema version=2；七张新增表、状态枚举、唯一约束、外键、UTC 时间和可重复 v1→v2 迁移均按 Spec 固定；失败迁移完整回滚。
必须验证：.venv/bin/python -m py_compile backend/app/domain/paper_discovery.py backend/app/services/paper_discovery_store.py；.venv/bin/python -m pytest -q tests/test_paper_discovery_store.py；git diff --check。
结果文档：docs/sdd/reviews/015-task13-schema-implementation.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task13-schema-<timestamp>.md。
固定返回字段：结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
先回传代码与测试结果，再回传说明；信息不足必须阻塞。
```

### C：仓储行为与并发测试

- 角色：`junior-dev`；模型：`qwen3.8:27b-mlx`；在 B 读回通过后执行。

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。补齐 Spec015 Task13 的 schema v2 仓储行为与测试。
只读取：已确认 Spec015、Task13、复用审计、B 修改后的 paper_discovery_store.py、paper_discovery.py 和 tests/test_paper_discovery_store.py。
允许修改：使用本地 Ollama时最多 2 个代码文件、约150行，优先 backend/app/services/paper_discovery_store.py 与 tests/test_paper_discovery_store.py；线上模型不受文件数上限但不得越过本任务。
禁止：HTTP/API/UI/Qdrant 改动；复制批量导入状态机；网络请求；git add/commit/reset/stash/clean。
完成状态：具备原子领取/租约恢复、目录 upsert+来源证据、任务/来源进度/安全事件、冻结结果写入和固定分页读取；两个线程不能同时领取同一 fetch unit；冻结结果不能被改写。
必须验证：.venv/bin/python -m pytest -q tests/test_paper_discovery_store.py；连续运行并发领取测试至少10轮；.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import.py；git diff --check。
结果文档：docs/sdd/reviews/015-task13-store-implementation.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task13-store-<timestamp>.md。
固定返回字段：结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
```

## 子 Agent 必须返回的字段

所有分派都必须返回：结果状态、摘要、改动文件、每条验证命令及退出码、测试计数、产物路径、关键决策依据、风险/阻塞、主 Agent 后续动作、开始时间、结束时间、总耗时；可用时增加模型、token 和工具调用统计。缺一项由主 Agent 退回补齐。

## 主 Agent 回填校验

1. 逐项读回复用审计和改动文件，核对没有新建同类基础设施。
2. 在临时目录创建 v1 数据库，写入会议、候选和导入历史后升级 v2；再次启动确认迁移幂等。
3. 制造迁移中断，确认 schema 与数据原子回滚。
4. 并发领取同一 fetch unit 10 轮，确认每轮只有一个 owner；模拟租约过期并恢复。
5. 冻结 21 条结果，验证页 1/2/3 分别为 10/10/1 且重复读取顺序一致。
6. 运行旧导入仓储回归、`git diff --check`、冲突标记和敏感产物扫描。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/tech-lead-spec015-task13-*.md
tail -f .codebuddy/agent-logs/junior-dev-spec015-task13-*.md
.venv/bin/python -m pytest -q tests/test_paper_discovery_store.py
```

## 测试与验收标准

- v1→v2 可重复迁移，旧会议/导入历史不丢失，失败不留半张表。
- 七张新增表、状态、唯一约束、外键和 UTC 时间与 Spec 完全一致。
- 同一抓取单元不能重复领取，租约过期可恢复。
- 目录哈希不变不更新、不触发索引；哈希变化置 `index_status=pending`。
- 来源原始记录可追溯；冻结结果不可改写且固定 10 条分页。
- 复用审计确认没有第二套下载、安全、导入、批任务、身份或 embedding 实现。

## 风险、停止条件与回滚

- 真实 v1 schema 与 Spec 不一致：停止迁移，记录实际 DDL 和差异，回到 Spec 修订，不猜测字段。
- 迁移可能删除旧数据或需要破坏性重建：停止并请求用户确认；不得自动删除数据库。
- 发现未提交用户改动与本任务冲突：停止相关文件，不 reset/stash/覆盖。
- 回滚到本任务开始前的 Spec015 检查点 commit；数据库迁移失败依靠事务回滚，禁止手工删表补救。

## 产出物

- `docs/sdd/reviews/015-task13-reuse-audit.md`
- schema v2 领域类型、迁移、仓储方法和定向测试。
- `docs/sdd/reviews/015-task13-schema-implementation.md`
- `docs/sdd/reviews/015-task13-store-implementation.md`

## 执行结果

已完成（2026-09-05），实现提交 `fe17e71`（Spec015 检查点基线 `b76cda1`）。

- **子任务A（tech-lead 复用审计）**：结论「通过（附意见）」，产出 `docs/sdd/reviews/015-task13-reuse-audit.md`。逐项审计 11 个服务模块 + domain 层，确认**无第二套**下载/安全/导入/批任务/身份/embedding 实现；落定 C-1~C-6 强制约束与 G-1~G-4 实现层缺口；schema v2 设计自洽、无未决问题。
- **子任务B（领域模型与迁移）**：`domain/paper_discovery.py` 新增 v2 七领域类型与状态枚举常量；`paper_discovery_store.py` 实现 v1→v2 **单事务幂等迁移**（先建七表、后升 `schema_meta=2`，失败整体回滚），新增外键统一 `ON DELETE RESTRICT`（C-3），v1 表与旧数据原地保留。
- **子任务C（仓储行为与测试）**：新增 `acquire_fetch_unit`（单语句条件 UPDATE + `rowcount` 原子领取，含租约过期恢复）、`renew_lease`、`release_lease`、`get_search_results_page`（`ORDER BY rank` 固定 10 条分页）；修复 `upsert_catalog_paper` 在 `metadata_hash` 变化时误返回 `False` 的缺陷；补齐 5 个用例。
- **验证**：
  - `tests/test_paper_discovery_store.py` → **10 passed**（并发领取 10 轮、租约恢复、21 条分页 10/10/1、来源追溯、metadata_hash 语义）
  - 旧导入回归 `test_paper_import_batch_store.py` + `test_paper_import.py` → **22 passed**
  - 聚焦回归（paper discovery + 导入相关）→ **84 passed, 9 subtests**
  - 主 Agent 回填校验：v1→v2 升级、重复启动幂等、旧会议/候选数据保留、迁移中断事务回滚（不留半张表）均通过
- **文档**：`015-task13-schema-implementation.md`、`015-task13-store-implementation.md`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 根据用户确认的文档计划创建 Task13，固定复用审计、schema v2 与仓储门禁；未执行代码 |
| 2026-09-05 | tech-lead（qwen3.8:27b-mlx） | 子任务A：完成只读复用审计，落定 C-1~C-6 约束与 G-1~G-4 缺口 |
| 2026-09-05 | junior-dev（qwen3.8:27b-mlx） | 子任务B：实现 v2 领域类型与 v1→v2 单事务幂等迁移；修复缩进与单例索引容错缺陷 |
| 2026-09-05 | junior-dev（qwen3.8:27b-mlx） | 子任务C：实现原子领取/租约/冻结分页；补 5 用例；修复 upsert metadata_hash 返回缺陷 |
| 2026-09-05 | 架构师（自身） | 创建基线 commit b76cda1（排除 017）；执行回填校验；代行撰写 store 实现文档；提交 fe17e71 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-13",
  "spec_id": "015",
  "title": "# 任务 13 — 固化全局目录协议与复用审计",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-03",
    "spec-015-task-05",
    "spec-015-task-11",
    "spec-015-task-12"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-015",
    "branch": "feature/spec-015-security-paper-discovery",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-tester
Read: ["docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
