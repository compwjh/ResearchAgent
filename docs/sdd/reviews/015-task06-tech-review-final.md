# Spec015 Task06 批次状态机最终技术复核

- 评审者：当前协作 Agent
- 角色：Tech Lead（开发主管）
- 评审时间：2026-09-04 19:25–19:27 CST
- 复核范围：`backend/app/domain/paper_import_batch.py`、`backend/app/services/paper_import_batch_store.py`、`backend/app/services/paper_import_batch_service.py` 及对应 Task06 定向测试
- 复核依据：`docs/sdd/reviews/015-task06-batch-store-tech-review.md`、`docs/sdd/reviews/015-task06-tech-review-recheck.md`、`docs/sdd/reviews/015-task06-acceptance-review.md`
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task06-final-review-20260904-192627.md`
- 约束：仅写本报告与日志；未修改业务代码、测试、spec 或 Git，未提交、未 push、未 reset/stash/clean

## 固定字段

- 结论：**通过（批次状态机切片）**
- 阻塞：**无**
- 测试：**22 passed × 3，三次退出码均为 0**
- 编译：**通过**
- 差异检查：**通过**
- 签字：**Tech Lead（当前协作 Agent）**

## 结论与边界

上次技术复核的两个阻塞均已闭环：非法旧库会在数据改写和索引重建前稳定 fail-fast；service 抢占失败的 loser 会只读轮询竞争 worker 的状态，不重复执行 importer，并在本次阻塞式 importer 回归中与 winner 一样返回 `completed`。锁竞争、租约 CAS、20 项硬上限、身份索引、重试/取消/恢复和批次聚合均有实现证据与回归覆盖。

本签字仅覆盖 Task06 的批次 domain/store/service 状态机切片，不代表 Playwright browser manager、ACM/IEEE 解析、真实外站登录续传、API 路由或前端已经完成。

## 上次阻塞复核

| 阻塞 | 结论 | 当前证据 |
|---|---|---|
| 非法旧库未 fail-fast | **已修复** | `paper_import_batch_store.py:136-200,236-306` 使用独立 `paper_import_schema_meta`，校验 metadata 形状/单例/版本、批次与条目必需列、TEXT/INTEGER/NOT NULL/PK、状态 CHECK 及现有行状态、attempt CHECK、条目复合唯一约束和 `ON DELETE RESTRICT` 外键；校验在历史清理与索引重建前执行。`test_existing_invalid_state_fails_fast_before_schema_repair` 与 `test_existing_tables_require_primary_key_and_foreign_key_constraints` 通过。 |
| 并发 loser 返回中间态 | **已修复** | `paper_import_batch_service.py:360-377,379-391,424-440` 的 `_wait_for_claim_winner` 在 `INVALID_STATE_TRANSITION` 后轮询活动态，winner 完成后返回最终记录；只对 CAS 失败方观察，不再次运行 importer。`test_concurrent_processing_allows_one_claimed_executor` 与 `test_concurrent_resume_waits_for_the_claimed_executor` 通过，均验证 importer 只调用一次且结果全为 `completed`。 |

## 状态机门禁矩阵

| 门禁 | 结论 | 证据 |
|---|---|---|
| 非法状态与迁移 | **通过** | domain 的 `ITEM_TRANSITIONS` 只允许 `queued → downloading → validating → indexing → completed`、`downloading → waiting_login → downloading`，失败仅经 retry/resume 回到 queued；终态 `completed/cancelled` 不再迁移。store 使用 `expected_state` 条件更新并将竞争失败归一为 `INVALID_STATE_TRANSITION`。 |
| 锁错误 | **通过** | `paper_import_batch_store.py:101-134` 统一以 `BEGIN IMMEDIATE` 开写事务，并覆盖连接、begin、事务体和 commit 阶段的 SQLite lock 映射为 `DATABASE_LOCKED`；service `:149-171` 有限重试并在耗尽时返回可重试错误。并发 claim/retry/resume/recover 测试未泄漏原始 `database is locked`。 |
| 租约 CAS / 旧 worker | **通过** | `transition_item` 活动态要求 owner 且条件包含 `state + lease_owner + lease_expires_at > now`；`mark_failed` 同样要求 owner/未过期；`renew_lease` 包含 owner、活动态、未过期及 300 秒门禁；恢复使用独立过期 CAS。`test_old_lease_owner_cannot_transition_or_fail_after_reclaim`、299/300 秒测试通过。 |
| 20 项硬上限 | **通过** | `max_items` 在构造器被限制为 `min(MAX_BATCH_ITEMS, configured)`；`create_batch` 先按 `candidate_id` 去重，再限制唯一项数。重复后恰 20 项可创建，21 个唯一项返回 `BATCH_LIMIT_EXCEEDED`。 |
| 身份索引 / 幂等 | **通过** | 启动时重建 DOI、DBLP、规范标题、item idempotency、`paper_id` 和 batch idempotency 的 partial unique indexes；有效状态为 queued/downloading/waiting_login/validating/indexing/completed，failed/cancelled 释放身份，completed 保留；标题年份/会议 NULL 使用固定 sentinel。失败/取消释放、completed 保留和 NULL 组件唯一性测试通过。 |
| 批次聚合 | **通过** | `_batch_from_row` 与 `_refresh_batch` 从条目真实 state 聚合总数、成功、失败、登录等待和取消数，不维护可漂移计数；混合 completed/failed/waiting/cancelled/queued/active 场景通过。 |
| 重试 / 取消 / 恢复 | **通过** | retry 只处理 failed/waiting_login；cancel 只处理 queued/waiting_login/failed，cancelled 不可再次领取或自动重试；恢复只处理租约过期的 downloading/validating/indexing 并写入 `IMPORT_INTERRUPTED`。并发 retry/resume/cancel/recover 均由条件更新保证单一成功者。 |
| 登录隔离 / 失败隔离 | **通过** | `_import_one` 将 `LOGIN_REQUIRED` 只转为当前 item 的 waiting_login；公开项继续完成；失败重试不重跑已完成项；service 所有活动失败与成功路径传递当前 owner。 |

## 验证命令与结果

定向回归命令按要求连续独立执行三次：

```text
.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py
```

结果：

- 第 1 次：`22 passed in 0.84s`，退出码 0
- 第 2 次：`22 passed in 0.89s`，退出码 0
- 第 3 次：`22 passed in 0.85s`，退出码 0

补充检查：

- `.venv/bin/python -m compileall -q backend/app/domain/paper_import_batch.py backend/app/services/paper_import_batch_store.py backend/app/services/paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py`：退出码 0
- `git diff --check`：退出码 0
- 目标实现/测试文件冲突标记扫描：0 命中

## 改动文件

本次复核新增：

- `docs/sdd/reviews/015-task06-tech-review-final.md`
- `.codebuddy/agent-logs/techlead-spec015-task06-final-review-20260904-192627.md`

业务代码、测试、spec 和 Git：**本次未修改**。

## 风险与后续移交

- `_wait_for_claim_winner` 为 2 秒有界等待；本次契约和阻塞式回归要求下可稳定观察 winner 的最终状态，超时则返回当前活动态，以避免 crashed worker 使调用永久阻塞。若后续要保证任意长耗时 importer 的调用者都同步得到终态，应另立接口超时/异步观察契约并补充验收。
- 本复核未执行真实 ACM/IEEE 登录、Playwright 生命周期、外站页面解析、API 路由和前端验收；这些仍需由 Task06 后续切片或整体验收覆盖。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：通过（批次状态机切片）**
- 签字时间：2026-09-04 19:27 CST
