# 验收评审：Spec015 Task06 批量导入与登录续传（定向验收）

> 评审角色：测试（tester）
> 关联计划：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
> 关联实现：`backend/app/domain/paper_import_batch.py`、`backend/app/services/paper_import_batch_store.py`、`backend/app/services/paper_import_batch_service.py`
> 进展日志：`.codebuddy/agent-logs/tester-spec015-task06-acceptance-20260904-191621.md`
> 评审时间：2026-09-04 19:16 CST
> 变更约束：本轮未修改业务代码、测试代码或既有文件；仅新增本报告与进展日志。

## 结论：不通过

SQLite 批次状态机的持久化聚合、逐项登录隔离、失败重试隔离、store 层条件更新/幂等、并发锁错误收敛、过期租约隔离、重启恢复和 20 项硬上限均有通过证据。但 service 层并发 `process_item` / `resume_item` 的竞争调用可能在唯一执行者尚未完成时直接返回 `downloading` 快照；指定回归已因此失败。该结果不满足“并发处理调用的幂等结果均可安全观察为最终状态”的验收要求，不能进入 Task06 收口。

## 一、指定回归命令、退出码和结果

```text
.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py
```

- 退出码：`1`
- 结果：`18 passed, 1 failed in 0.90s`
- 失败用例：`tests/test_paper_import_batch_service.py::test_concurrent_processing_allows_one_claimed_executor`
- 失败断言：importer 调用次数为 1（通过），但两个并发 `process_item` 返回结果未全部为 `completed`（失败）。

## 二、验收矩阵

| 验收项 | 结果 | 证据与说明 |
|---|---|---|
| 批量逐项执行、计数/状态聚合准确 | 通过 | 临时 DB 混合 `public/login/fail`：批次 `waiting_login`；条目分别为 `completed / waiting_login / failed`，公开项继续完成。现有 store 聚合测试通过。 |
| `LOGIN_REQUIRED` 只暂停当前项 | 通过 | `test_public_items_continue_when_one_item_requires_login` 通过；login 项等待，public 项完成。 |
| 失败重试不重跑成功项 | 通过 | `test_failed_item_can_be_retried_and_success_is_not_reexecuted` 通过；临时复核调用序列显示 public 仅执行 1 次，失败项才再次执行。 |
| 创建幂等 | 通过 | 顺序同 key 返回同一批次；临时 DB 20 轮 × 8 线程同 key，160/160 返回有效同一批次，无锁泄漏。 |
| retry 幂等 | 通过 | store 并发 20 轮，每轮 8 线程只有 1 个 retry 成功，其余为预期 `INVALID_STATE_TRANSITION`，无 `DATABASE_LOCKED`。 |
| resume 幂等（store 条件更新） | 通过 | store 并发 20 轮，每轮 8 线程只有 1 个 resume 成功，其余为预期条件冲突，无锁错误泄漏。 |
| cancel 幂等 | 通过 | 8 线程并发取消同一 queued 项：1 个成功、7 个稳定 `INVALID_STATE_TRANSITION`，最终为 `cancelled`。 |
| claim/retry/resume/recover 并发无 database locked 泄漏 | 部分通过 | store 层 20 轮 × 8 线程全部未见 `DATABASE_LOCKED` 或原始 SQLite 锁异常；service 层并发竞争返回快照仍有一致性问题，见阻塞项。 |
| 单一执行者 | 通过（执行层）/不通过（返回观察） | 慢 importer 竞争复核仅调用 1 次，最终 DB 为 `completed`；但 loser 可提前返回 `downloading`。 |
| 过期租约旧 worker 不可越权 | 通过 | recover→retry→新 owner claim 后，旧 owner transition/mark_failed 均被拒绝且未改变新 owner。 |
| 服务重启恢复后可重试 | 通过 | 新 store/service 实例 recover 得到 `failed/IMPORT_INTERRUPTED`，显式 retry 后 `completed`，importer 仅调用 1 次。 |
| 单批最多 20 项 | 通过 | 去重后恰 20 项可创建；21 个唯一项返回 `BATCH_LIMIT_EXCEEDED`；`max_items=21` 不能绕过硬上限。 |

## 三、阻塞问题与复现证据

### P1：service 并发 loser 提前返回活动态

复现设置唯一 importer 睡眠 0.2 秒，两个线程同时调用 `service.process_item(item_id)`：

```text
calls ['one']
returned ['completed', 'downloading']
final completed
```

同样对 waiting-login 项做 8 线程并发 `service.resume_item`：

```text
calls=1
returned statuses include completed and downloading
final completed
```

这不是重复执行（importer 始终只调用一次），但竞争调用者直接读取 winner 尚未完成的状态并返回，导致 API/service 调用结果不稳定；指定回归已稳定捕获该问题。建议后续在已被其他执行者领取时，采用可控等待/重新读取最终状态，或返回明确的“处理中”稳定结果并同步调整验收断言与接口契约；修复后需重跑指定回归及本矩阵。

## 四、范围外项目与风险

- 本次仅验收 Task06 当前批次 domain/store/service 切片；ACM/IEEE headed Playwright、真实权限登录、浏览器崩溃/页面结构变化、API 路由和前端不在本切片可执行范围，不能据此宣称真实登录续传已验收。
- 未修改业务代码或测试代码；未提交、未 push、未 reset/stash/clean。
- 当前结论为不通过；在 P1 修复并由 tester 重跑通过前，不得将 Task06 标记为已完成，也不得推进依赖该切片的最终收口。

## 五、签字

- 测试（tester）：**不通过**
- Tech Lead 签字：待复核（本报告不代签）
- 签字时间：待定
