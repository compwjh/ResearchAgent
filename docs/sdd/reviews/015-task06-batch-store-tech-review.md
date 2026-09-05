# Spec 015 Task06 批次状态机切片技术复核

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 实际模型：当前协作 Agent（运行时未提供可核验模型标识，不冒充执行配置模型）
- 分派方式：主会话通过协作 Agent 独立分派
- 评审时间：2026-09-04 18:55:56 CST
- 评审范围：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`、`backend/app/domain/paper_import_batch.py`、`backend/app/services/paper_import_batch_store.py`、`tests/test_paper_import_batch_store.py`
- 评审约束：只做技术复核；未修改业务代码、测试或 Git，未提交、未 push、未 reset/stash/clean
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task06-batch-review-20260904-185556.md`

## 结论：打回

当前切片的条目状态常量、主路径/登录分支、批次计数实时聚合、基础取消边界和 5 分钟续租条件方向正确，现有定向测试也通过。但实现尚不能作为 Task06 的 SQLite 状态机门禁放行：并发写锁会泄漏 `database is locked`，schema 没有条件迁移，身份/幂等索引未按有效任务状态限定，20 项限制顺序及硬上限不成立，且活动状态更新可被失效租约的旧 worker 越权。上述问题会直接破坏“重复 retry/resume 只能一个生效”和“失败/取消后的任务可安全重新创建”语义。

## 代码事实与发现

| 优先级 | 判定 | 证据 | 影响与放行要求 |
|---|---|---|---|
| **P1** | 并发写入会泄漏 SQLite 锁错误 | `_connect()` 设置了 WAL、`busy_timeout=5000`（`paper_import_batch_store.py:85-91`），但所有写操作仍以 deferred `BEGIN` 先读后写（如 `claim_item:346-360`、`transition_item:314-340`）。8 线程并发领取实测为 1 次成功、2 次稳定 CAS 错误、5 次 `sqlite3.OperationalError: database is locked`。 | 并发 claim/retry/resume/恢复的失败结果不稳定，调用方无法按稳定错误码重试或判定幂等。统一使用可序列化的写事务（例如 `BEGIN IMMEDIATE`）或有限重试并将锁竞争映射为稳定 CAS/冲突错误；补至少 2 个进程/线程竞争 claim、retry、resume、recover 的回归测试。 |
| **P1** | schema 版本检查不是条件迁移，且未验证既有表结构 | `_init_schema`（`paper_import_batch_store.py:93-147`）只创建/读取 `schema_meta` 并要求版本为 1；没有检查 `schema_meta` 列形状、单例约束、批次/条目缺列或旧约束，也没有 `ALTER TABLE`/重建迁移。该 DB 与 `PaperDiscoveryStore` 共享 `schema_meta`，未来任一 store 升级版本会让另一 store 误判。 | 旧的/部分创建的状态库可能在启动时静默接受后在运行中缺列、或直接因共享版本号拒绝启动，无法满足“固定 schema version + 条件迁移”。需明确 v1 兼容策略：实现逐版本、事务内、可重入迁移并隔离各 store 元数据，或对结构不兼容状态库做完整校验后稳定 fail-fast；补旧 schema、重复 metadata、缺列/索引和并发首次启动测试。 |
| **P1** | 20 项上限在去重前检查，且可被构造器放大 | `create_batch` 在 `paper_import_batch_store.py:175-178` 先按原始输入长度拒绝，随后才在 `179-188` 按 candidate 去重；`__init__(max_items=...)`（`76-79`）允许调用者传入大于 20 的值。 | 21 个输入中含重复项时会错误拒绝，且 `max_items=21` 可绕过 Task06 的硬性单批 20 项。应先验证/去重，再对唯一项数执行 `min(configured_limit, MAX_BATCH_ITEMS)`（或拒绝大于 20 的配置）；补“重复后恰为 20/超过 20”和构造器大上限测试。 |
| **P1** | 全局身份/条目幂等索引没有按有效任务状态过滤 | `paper_import_doi/dblp/title/idempotency`（`paper_import_batch_store.py:136-145`）分别对所有非 NULL 值做唯一约束，包含 `failed` 与 `cancelled`，而没有 `state` 条件；因此永久失败或用户取消的历史条目会阻塞未来合法任务。`paper_id`（schema `:118`）也没有唯一索引。 | “搜索会话 + 候选 + 目标知识库身份 + 有效任务状态”的幂等语义无法成立：失败/取消不应继续占用活动身份；同时两个候选可能在 transition 时得到同一 `paper_id`。应固定有效状态集合（至少明确 queued/downloading/waiting_login/validating/indexing/completed 的处理），建立相应 partial unique indexes/目标知识库身份唯一约束；失败/取消释放行为、completed 去重行为和跨批并发测试必须覆盖。 |
| **P1** | 活动状态迁移和失败标记可绕过租约所有权 | `transition_item` 的 `lease_owner` 是可选参数（`300-324`），因此从 downloading/validating/indexing 的更新默认只按 `item_id + state`；`mark_failed`（`395-407`）对活动状态也不带 owner/未过期条件。旧 worker 租约过期后，条目可被恢复、重试并重新领取，旧 worker 仍可能把新 worker 的条目标记 waiting/failed/completed。 | 单一执行者和状态一致性失效。所有活动态的 transition/fail 必须强制带当前 lease owner，并在 SQL 条件中检查 owner 与未过期租约；只有明确的系统恢复动作可不带 owner，且必须使用独立 CAS 条件。补过期→retry→新 claim 后旧 owner 写入被拒绝的测试。 |
| **P2** | 标题组合唯一索引对 NULL 组成字段不具备真正唯一性 | `import_item_title`（`paper_import_batch_store.py:141-144`）只要求 `normalized_title IS NOT NULL`；SQLite 的复合 UNIQUE 遇到 `year` 或 `conference_id` 为 NULL 时允许重复。 | 未知年份/会议的同标题任务可重复入队，导致身份去重不确定。应使用规范化 sentinel/生成身份键，或为 NULL 组合建立等价唯一策略，并补 NULL 年份/会议的重复测试。 |

## 已通过或条件通过的检查

- `PaperImportBatch`/`PaperImportItem` 状态常量和合法迁移集合覆盖 queued → downloading → validating → indexing → completed 及 downloading ↔ waiting_login，终态不再迁移（`paper_import_batch.py:20-41`）。
- `_batch_from_row` 与 `_refresh_batch` 均从 `paper_import_items` 按真实 state 聚合计数，不维护可漂移的独立成功/失败计数（`paper_import_batch_store.py:224-235,273-298`）。需在补丁中增加混合 completed/failed/waiting/cancelled/active 的批次真值表测试。
- `renew_lease` 使用 owner、活动状态、未过期以及 `lease_renewed_at <= now - 300s` 条件（`paper_import_batch_store.py:378-393`），5 分钟门禁表达正确；仍应补边界的 299/300 秒、过期租约、错误 owner 和时间倒退测试。
- `cancel_item`/`cancel_batch` 只处理 queued/waiting_login/failed（`426-454`），completed/indexing 不可取消；`retry_batch` 只将 failed/waiting_login 置回 queued（`413-424`）。这些边界符合计划，但须与修复后的并发 CAS 一起回归。
- 过期恢复只扫描活动态且 `lease_expires_at <= now`，并写入 `IMPORT_INTERRUPTED`（`456-484`）；恢复、重试和重新领取仍受上述锁竞争/租约 owner 问题影响。

## 验证结果

定向测试：

```text
pytest -q tests/test_paper_import_batch_store.py
收集失败：ModuleNotFoundError: No module named 'backend'（环境未设置包路径）

PYTHONPATH=. pytest -q tests/test_paper_import_batch_store.py
5 passed in 0.02s
```

并发证据：8 个线程对同一 `queued` item 并发 `claim_item`，结果为 1 次成功、2 次 `PaperImportBatchStoreError`、5 次 `sqlite3.OperationalError: database is locked`。该复现为临时数据库，不改变仓库文件。

补充边界复现：20 个重复候选加 1 个唯一候选在去重前被拒绝；`max_items=21` 可创建 21 项；取消后的 DOI 仍阻塞新批次；旧租约恢复、retry、新 worker claim 后，旧 worker 在不传 `lease_owner` 时仍可将条目 transition 成功。

## 最小修订清单

1. 为所有写事务统一确定 SQLite 并发策略，确保锁竞争转换为稳定、可重试的业务结果，并补竞争测试。
2. 补齐 schema 形状校验和事务内条件迁移/稳定拒绝策略，解决与搜索 store 共享 `schema_meta` 的版本耦合。
3. 去重后再执行硬性 20 项校验，限制构造器上限不得超过 20。
4. 按有效任务状态重建 DOI/DBLP/title/item-idempotency 索引，增加 `paper_id`/目标知识库身份的唯一约束，并固定 NULL 身份字段策略。
5. 活动态 transition/mark-failed 强制租约 owner + 未过期 CAS；补旧 worker 越权负例。
6. 补聚合混合状态、续租 299/300 秒、恢复/取消/重试并发及旧库迁移测试。

## 不计入本轮

任务服务调度、公开/登录下载、Playwright browser manager、ACM/IEEE 解析器、API 路由、前端和真实账户验收不在本切片范围；本结论不替代这些后续任务的技术/验收评审。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：打回**
- 签字时间：2026-09-04 18:55:56 CST
