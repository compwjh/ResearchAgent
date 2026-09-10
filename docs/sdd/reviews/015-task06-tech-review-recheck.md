# Spec 015 Task06 批次状态机切片技术复核（修复后复核）

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 实际模型：当前协作 Agent（运行时未提供可核验模型标识，不冒充执行配置模型）
- 评审时间：2026-09-04 19:16:24 CST
- 复核范围：`docs/sdd/reviews/015-task06-batch-store-tech-review.md` 提出的阻塞；`backend/app/domain/paper_import_batch.py`、`backend/app/services/paper_import_batch_store.py`、`backend/app/services/paper_import_batch_service.py` 及对应测试
- 评审约束：只做复核；未修改业务代码、测试或 Git，未提交、未 push、未 reset/stash/clean
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task06-recheck-20260904-191624.md`

## 结果状态和摘要

**暂不放行（打回）。** 上次提出的 store 并发锁映射、硬 20 项、有效状态身份索引/NULL 身份和活动租约 owner CAS 均已有实质修复，服务失败路径也已传递 owner。指定测试最终重跑为 `19 passed`，但首次执行出现 `18 passed, 1 failed`，并通过阻塞 importer 的确定性复现确认 service 并发调用仍存在真实竞态：抢占失败的一方在胜者仍处理时立即返回 `downloading`，不能稳定返回最终 `completed`。此外，schema 目前只检查元数据基本形状、版本和必需列；一个包含全部必需列但已有非法 `state`/约束形状的旧表可被接受，未达到完整 fail-fast。

## 逐项复核

| 上次阻塞 | 结论 | 当前证据 |
|---|---|---|
| SQLite 并发写锁泄漏 `database is locked` | **已修复（store 层）** | `paper_import_batch_store.py:101-129` 统一通过 `BEGIN IMMEDIATE` 建立写事务，并将连接、开始事务、事务体和提交阶段的 SQLite 锁错误映射为 `PaperImportBatchStoreError(DATABASE_LOCKED)`；`paper_import_batch_service.py:148-169` 对该错误做有限重试并在耗尽时转为可重试 service 错误。store 并发 claim/retry/resume/recovery 用例 `12 passed`。但 service 抢占失败后的最终状态竞态仍未收口，见下文新增阻塞。 |
| schema 版本/形状 fail-fast 与 store 隔离 | **部分修复，仍未通过** | `paper_import_batch_store.py:119-131` 使用独立的 `paper_import_schema_meta`，不再复用搜索 store 的 `schema_meta`；`paper_import_batch_store.py:132-199` 检查 metadata 表列、单行、整数版本和批次/条目必需列，缺列测试通过，重复 active identity 也会稳定失败。但只做列存在性检查，没有验证既有批次/条目表的 CHECK、FK、主键/唯一约束或既有 state 值。只要旧表列名齐全，即使批次行 `state='bogus'`，构造 `PaperImportBatchStore` 仍成功（只读临时 DB 复现）。需补齐结构/数据契约校验，或在版本迁移不兼容时稳定拒绝。 |
| 去重后硬 20 项、构造器不可放大 | **已修复** | `paper_import_batch_store.py:83` 将配置限制为 `min(MAX_BATCH_ITEMS, int(max_items))`；`create_batch:260-271` 先按 candidate_id 去重、校验，再按有效唯一项数比较上限。`test_deduplicates_before_hard_limit_and_constructor_cannot_raise_limit` 通过，重复后恰为 20 项可创建，21 个唯一项被 `BATCH_LIMIT_EXCEEDED` 拒绝。 |
| DOI/DBLP/title/item idempotency 按有效状态唯一 | **已修复** | `paper_import_batch_store.py:202-227` 删除旧索引后重建 partial unique indexes，活动集合为 `queued/downloading/waiting_login/validating/indexing/completed`，明确排除 `failed/cancelled`；另有 `paper_id` 唯一索引。失败/取消批次的 key 会释放，completed 保留。对应失败/取消释放、completed 保留和 DOI 重复测试通过。 |
| NULL 标题身份唯一性 | **已修复（当前策略）** | `paper_import_batch_store.py:216-220` 以 `COALESCE(year, -2147483648)` 和 `COALESCE(conference_id, X'00')` 将 NULL 组件纳入复合身份；`test_null_title_components_are_part_of_identity` 通过，未知年份/会议的相同标题不会因 SQLite NULL UNIQUE 语义而重复。该 sentinel 约定应在后续 schema 文档中保持不变。 |
| 活动 transition/mark_failed 的租约 owner CAS | **已修复** | `paper_import_batch_store.py:404-428` 对活动状态强制 `lease_owner` 且 SQL 同时约束 owner、状态和 `lease_expires_at > now`；`mark_failed:489-503` 同样强制 owner/未过期，非活动 queued/waiting_login 才允许无 owner。过期恢复→retry→新 worker claim 后旧 owner transition/fail 的负例通过。 |
| service 失败路径传当前 owner | **已修复** | `paper_import_batch_service.py:284-341` 的登录、成功 transition 均传 `owner`；`_mark_failed:343-356` 调用 `mark_failed(..., lease_owner=owner)`。service 旧 worker 失败负例通过，且静态检查确认所有失败路径均使用当前 owner。 |

## 新发现的 service 并发竞态（放行阻塞）

`PaperImportBatchService.process_item:364-368` 在 `claim_item` 失败时直接读取一次 item 并返回。若 worker A 已完成 claim、正在 importer 中处理，worker B 的 claim 会按 CAS 失败；B 随即返回 A 尚未完成的 `downloading`。这不是稳定锁异常，而是调用语义不稳定，且违反当前回归用例“两个并发调用都得到 `completed`”的预期。

确定性复现通过临时 importer 阻塞得到：

```text
loser_status= downloading
winner_status= completed
```

首次指定命令也捕获到同一竞态：

```text
..............F....  [18 passed, 1 failed]
test_concurrent_processing_allows_one_claimed_executor
```

之后同一命令连续 3 次为 `19 passed`，说明该问题受调度影响；但阻塞 importer 的复现不依赖偶然时序，仍应修复为等待/轮询最终 CAS 状态（或明确并测试“抢占失败即返回中间状态”的 API 契约）。

## 验证命令与结果

指定定向测试：

```text
.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py
```

- 首次结果：`18 passed, 1 failed`（service 并发处理竞态）。
- 随后连续 3 次重跑：每次 `19 passed`。
- store 单独测试：`12 passed`。
- 目标三个业务模块 `compileall`：退出码 `0`。
- 额外静态/临时 DB 检查：确认 `BEGIN IMMEDIATE`、`DATABASE_LOCKED` 映射、5 个 active-state partial unique indexes、NULL title sentinel、owner CAS 及 service `mark_failed` owner 传递；非法已有 state 的全列旧表被接受，支持 schema 阻塞结论。

## 最小修订清单

1. 修复 `process_item` 抢占失败后的并发语义：在不重复执行 importer 的前提下等待同一 item 的最终状态，或明确返回中间态并同步修改/补强验收契约；至少加入阻塞 importer 回归测试。
2. 完善 schema fail-fast：验证既有表的列类型、主键/FK/唯一约束、CHECK 状态集合和既有行状态；不兼容旧结构必须事务内迁移或稳定拒绝，并保留 `paper_import_schema_meta` 命名空间隔离。
3. 复跑目标测试并确认首次与重复运行均稳定通过后，再进入验收评审。

## 已通过的实现边界

- 本轮确认批次计数仍由条目状态实时聚合，未引入可漂移计数。
- 5 分钟续租门禁及 299/300 秒边界测试通过。
- 取消、重试、过期恢复和登录等待状态边界在目标测试中通过。
- 不计入本轮：任务 API 路由、Playwright browser manager、真实外站登录/下载、前端入口和全量集成验收。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：打回**
- 签字时间：2026-09-04 19:16:24 CST
