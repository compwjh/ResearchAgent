# Spec032 登录恢复修复实施报告

> 当前收口状态：本次登录/继续窄修已完成并已集成主目录；Spec032 整体仍暂停。

> 关联：[登录恢复计划](./2026-10-26-login-recovery-plan.md)；Spec032 Task11 窄范围恢复。
>
> **状态：本次 Task11 登录恢复窄修已完成并已在主目录集成（2026-10-26）；Spec032 总体仍保持暂停。** 本报告不代表 Spec032 整体收口。

## 实现范围

本轮只改了 4 个业务/测试文件：

- `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - 新增 public-internal `get_item_snapshot_candidates(item_id)`。
  - 完整持久快照先通过 `store.get_snapshot`，再复用现有 `_snapshots_for(batch_id, None)`；目标 candidate/search 身份必须匹配 item/batch。
  - 双字段均缺失的 legacy item 返回 `None`，让路由保留原 live-search fallback。
  - hash/JSON 损坏、部分快照元数据、身份不匹配均 fail-closed，分别保留 `SNAPSHOT_REBUILD_REQUIRED`/`INVALID_SEARCH_SNAPSHOT` 语义。
- `backend/app/api/routes_paper.py`
  - `_paper_snapshot_for_item` 先调用上述 wrapper；只有 wrapper 返回 `None` 时才进入原 search session/job TTL fallback。
  - 未改公开 API/schema、URL allowlist/SSRF、状态/CAS、浏览器 session TTL 或 persistent profile。
- `tests/paper_discovery/test_paper_import_batch_service.py`
  - 覆盖过期搜索后的 durable restore、legacy 缺失快照 fallback、身份篡改和部分元数据损坏。
- `tests/paper_discovery/test_paper_browser.py`
  - 覆盖过期搜索下 login/resume、legacy fallback、损坏快照 fail-closed，并保留既有 allowlist/session 生命周期断言。

没有初始化生产 Store、迁移数据库、启动服务、发送产品 HTTP POST、打开 headed browser、部署、commit 或 push。

## TDD 与验证结果

| 阶段 | 命令/范围 | 结果 |
|---|---|---|
| RED | 两个新行为测试（service wrapper + login route） | 退出码 1；预期 2 failed，分别暴露 wrapper 缺失和 live-search TTL 先行拦截 |
| GREEN 核心 | service 4 个 wrapper 测试 + browser 全文件 | 退出码 0；14 passed |
| 定向 service/browser | `test_paper_import_batch_service.py` + `test_paper_browser.py` | 退出码 0；43 passed |
| 定向 API 生命周期 | server snapshot resume、session callback、browser race、queued runner 等 4 个既有节点（含参数化） | 退出码 0；5 passed |
| 静态 | Ruff `--no-cache`、临时 `PYTHONPYCACHEPREFIX` 下 `py_compile`、`scripts/check_test_layout.py` | 全部退出码 0；`All checks passed!` / `test layout: ok` |

完整 service/browser/API 三文件切片为 **63 passed、1 failed**。唯一失败为既有 `test_storage_locked_import_sets_item_error_code_via_api`：期望 `KB_STORAGE_LOCKED`，实际 `KB_IMPORT_FAILED`；该路径不调用本轮 item snapshot/login route，未在本 Task 修改，需另行诊断，不能作为本修复通过证据。

## 后端评审跟进

- 已将首轮 `store.get_snapshot()` 的 `PaperImportBatchStoreError(SNAPSHOT_REBUILD_REQUIRED)` 转换为稳定的 `PaperImportBatchServiceError`，避免真实 hash/JSON 损坏被路由误报为 `BROWSER_UNAVAILABLE` 或 `IMPORT_BATCH_ERROR`。
- 新增真实临时 SQLite 快照损坏回归：login 与 resume 均返回 `503 SNAPSHOT_REBUILD_REQUIRED`，且 browser `open_session` 未调用；未使用生产数据库、产品 HTTP 或 headed browser。
- 评审报告已用 `git archive HEAD` 临时副本复现基线：相同三文件为 `55 passed`、退出码 0；当前 worktree 对既有 storage-lock 节点单独运行仍为 `KB_STORAGE_LOCKED` → `KB_IMPORT_FAILED`，因此不是新增快照测试的顺序污染，也不归因于本 Task diff。

## 安全与生命周期核对

- 完整快照不再依赖过期 live-search TTL，但仍来自服务端 SQLite snapshot，并经过 hash、JSON、candidate/search 身份校验。
- 客户端 URL 未进入恢复路径；`_paper_item_browser_target`、BrowserManager exact-origin、下载器重定向/SSRF/allowlist 边界保持不变。
- 浏览器 session TTL 未延长；到期仍回收临时 page/context 并 fail-closed。批次/item 持久 `waiting_login` 状态不被删除或取消；再次 login 仍复用既有 persistent profile。
- `waiting_login` 未转入仅支持 `failed` 的 retry；resume 的既有 CAS/lease/status 语义未改。

## 待根会话处理

1. 审查 4 个业务/测试文件的 diff，确认只保留本 Task 改动；当前工作树中 KB/frontend 相关 docs/spec 改动是基线遗留，不属于本修复。
2. 在集成后使用实际旧 batch `1a76e369-c638-4f2c-a430-42552a1e7012` 做授权的 GET 状态核对，再由根会话执行实际 login/resume 验证；本代理不执行该动作。
3. 单独处理上述 `KB_STORAGE_LOCKED` 存量失败；不得因本修复而扩大到 Spec032 全量回归或收口。该项不阻断本次已完成的 login/resume 路由窄修，但认证后 resume/download/import 仍未验证。

## 2026-10-26 窄修收口

主目录集成版本已由 `2026-10-26-login-recovery-test.md` 记录 `64/64` 定向通过，并由 `2026-10-26-login-recovery-review.md` 独立复审 GO；真实旧批次 login 返回 `200/opened/acm`。本报告的实现范围完成，Spec032 整体状态仍为“暂停，待下次继续”。
