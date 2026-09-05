# 验收评审：Spec 015 Task06 批量导入与登录续传（批次状态机最终复验）

> 评审角色：测试（tester）
> 关联计划：`docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
> 关联前次报告：`docs/sdd/reviews/015-task06-acceptance-review.md`
> 关联技术复核：`docs/sdd/reviews/015-task06-tech-review-recheck.md`、`docs/sdd/reviews/015-task06-batch-store-tech-review.md`
> 关联实现：`backend/app/domain/paper_import_batch.py`、`backend/app/services/paper_import_batch_store.py`、`backend/app/services/paper_import_batch_service.py`
> 进展日志：`.codebuddy/agent-logs/tester-spec015-task06-final-acceptance-20260904.md`
> 评审时间：2026-09-04
> 变更约束：本轮未修改业务代码、测试代码或既有文件；仅新增本报告与进展日志；未提交、未 push、未 reset/stash/clean。

## 结论：通过（当前批次 domain/store/service 切片）

前次 P1 的 service 并发 loser 提前返回活动态问题已由等待竞争 winner 的实现收口；指定回归连续三次稳定通过，临时隔离数据库验证也全部通过。批次条目状态、真实状态聚合、登录/失败逐项隔离、幂等、CAS 并发、旧租约防越权、非法旧库 fail-fast、20 项硬上限和重启恢复均满足本轮验收范围。

本结论不等同于真实外站登录续传已完成：当前仓库未发现 Playwright/browser manager、ACM/IEEE 解析器或 Task06 API 路由实现；ACM/IEEE 合法账户登录、浏览器崩溃/页面结构变化和接口层验收仍是后续范围与风险，不能据此宣称完整 Task06 已交付。

## 一、指定回归命令、退出码和结果

命令（当前可用 Python 环境）：

```text
python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py
```

| 次数 | 退出码 | 结果 |
|---:|---:|---|
| 1 | 0 | `22 passed in 1.07s` |
| 2 | 0 | `22 passed in 1.07s` |
| 3 | 0 | `22 passed in 1.09s` |

补充：`.venv/bin/pytest` 的 shebang 指向不存在的 `/Users/wjh/PyCharmMiscProject/.venv/bin/python`，因此该入口退出码为 127；未修改环境，使用当前可用的 `python -m pytest` 完成同一测试集。五个目标文件的 `compileall` 检查退出码为 0。

## 二、逐项验收矩阵

| 验收项 | 状态 | 证据 |
|---|---|---|
| 批量逐项更新、计数/状态聚合准确 | 通过 | 临时 SQLite 混合 `public/login/fail` 得到条目 `completed / waiting_login / failed`，公开项继续完成；`paper_import_batch_store.py:432-459` 从条目真实状态聚合批次状态与计数。 |
| 登录项与失败项不阻塞公开项 | 通过 | `paper_import_batch_service.py:295-328` 将 `LOGIN_REQUIRED` 仅转为当前条目 `waiting_login`，其他异常仅标记当前条目失败；`run_batch` 使用逐项 futures（`paper_import_batch_service.py:393-404`）。临时 importer 调用三项且公开项完成。 |
| 创建幂等 | 通过 | `paper_import_batch_store.py:336-379` 去重后事务插入，唯一 key 冲突返回既有批次；临时 8 线程同 key 返回同一 `batch_id`，无 raw 锁异常。 |
| retry 幂等 | 通过 | `retry_item` 仅允许 `failed → queued`（`paper_import_batch_store.py:582-595`）；临时 8 线程仅 1 次成功，其余为预期 `INVALID_STATE_TRANSITION`。 |
| resume 幂等 | 通过 | `resume_item` 使用 `WHERE state='waiting_login'` 的条件更新（`paper_import_batch_store.py:527-539`）；临时 8 线程仅 1 次成功，其余为预期 CAS 冲突。 |
| claim 并发单一执行者 | 通过 | `claim_item` 以 `BEGIN IMMEDIATE` + `WHERE state='queued'` 更新（`paper_import_batch_store.py:101-134,512-525`）；临时 8 线程仅 1 次成功，无 `database is locked` 泄漏。 |
| service 并发 process/resume 返回最终状态 | 通过 | 失败 claim/resume 后调用 `_wait_for_claim_winner`，轮询至非活动终态（`paper_import_batch_service.py:360-377,379-391,424-436`）；既有两个阻塞 importer 回归均通过，结果均为 `completed` 且 importer 只执行一次。 |
| recover 并发幂等 | 通过 | `recover_expired_leases` 只处理过期活动态并用条件更新（`paper_import_batch_store.py:625-641`）；临时 8 线程仅 1 次返回 1，其余返回 0。 |
| SQLite 锁错误稳定收敛 | 通过 | 写事务统一 `BEGIN IMMEDIATE` 并映射为稳定 `DATABASE_LOCKED`（`paper_import_batch_store.py:101-132`）；service 对该错误有限重试并转为 retryable service error（`paper_import_batch_service.py:149-170`）。三次回归和临时并发验证均未见 raw SQLite 锁异常。 |
| 旧库非法状态 fail-fast | 通过 | schema 校验状态 CHECK、既有行状态、attempt_count、唯一约束和 FK（`paper_import_batch_store.py:236-306`）；临时注入旧表 `state='bogus'` 后重新打开稳定抛出 `RuntimeError`。 |
| 单批最多 20 项（去重后） | 通过 | 常量与构造器上限为 20（`paper_import_batch_store.py:38-50,82-87`）；输入先去重再比较上限（`paper_import_batch_store.py:336-347`）；临时 20 个唯一项加重复项成功，21 个唯一项返回 `BATCH_LIMIT_EXCEEDED`。 |
| 过期旧 worker 不可越权 | 通过 | 活动态迁移要求 owner、状态及 `lease_expires_at > now`（`paper_import_batch_store.py:461-505`）；失败标记同样要求 owner（`paper_import_batch_store.py:558-580`）。临时 recover→retry→新 owner claim 后，旧 owner transition/mark_failed 均被拒绝，新 owner 保持不变。 |
| 服务重启后可安全重试 | 通过 | 恢复将过期 downloading/validating/indexing 置为 `failed/IMPORT_INTERRUPTED`（`paper_import_batch_store.py:625-641`）；临时新建 store/service 实例后 recover→retry 完成，`attempt_count=2`，importer 仅执行一次。 |

## 三、前次阻塞复验

前次报告记录的确定性竞态为：winner 正在 importer 中处理时，loser 直接返回 `downloading`。当前 service 已增加有界只读等待：

```text
_wait_for_claim_winner: 竞争者仍为活动态则轮询；进入 completed/failed/waiting_login 等非活动态后返回。
```

`test_concurrent_processing_allows_one_claimed_executor` 与 `test_concurrent_resume_waits_for_the_claimed_executor` 均在三次回归中通过；临时 importer 竞争场景也验证了调用只执行一次且所有调用者观察到最终 `completed`。前次 P1 关闭。

## 四、风险与明确未覆盖项（不阻塞本切片结论）

- 当前实现目录没有 Playwright/browser manager、ACM/IEEE 页面解析器、登录/resume API 路由或前端入口；因此真实 ACM Digital Library 与 IEEE Xplore 合法账户登录续传尚未验收。
- 浏览器不可用、崩溃、页面结构变化、机构 SSO/验证码/付费墙和受控 profile 脱敏需在浏览器/API 切片实现后单独验收。
- 本轮临时验证使用内存 importer 和临时 SQLite，不代表真实外部站点、Qdrant 或完整 API 集成可用性。
- `.venv` 启动脚本已失效（shebang 指向不存在路径）；本轮未修复环境，以系统当前 Python 模块入口完成测试。

## 五、签字

- 测试（tester）：**通过（当前批次 domain/store/service 切片）**
- Tech Lead 签字：**待填**
- 签字时间：待定
