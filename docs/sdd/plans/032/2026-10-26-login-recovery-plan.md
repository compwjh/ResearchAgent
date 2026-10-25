# Spec032 登录恢复计划：优先复用导入条目持久快照

> 关联：[Spec032](../../specs/032-research-source-expansion.md) §接口、边界与产品步骤 6–7；Task11 登录/恢复范围。
>
> **状态：提议中（未实施）**。本文件只记录只读诊断和最小实施方案；本轮未修改业务代码、未执行产品 POST、未打开浏览器、未初始化或迁移状态库、未执行 Git 操作。

## 结论

`waiting_login` 的登录入口应先从 `PaperImportBatchService` 已有的、带 hash 校验的持久候选快照恢复 URL，再决定是否需要读取仍有效的 live search session。这样用户可以在搜索 TTL 之后、甚至服务重启后重新打开 ACM/IEEE 登录页；这不等于延长搜索 TTL，也不需要重新运行研究。

最小改动是收紧 `_paper_snapshot_for_item` 的解析顺序：复用现有 `_snapshots_for(batch_id, None)` 的 durable-first 语义，只有持久快照缺失、损坏或无法完成身份校验时才保留当前 live-search fallback 和原有错误。`login`、`resume`、`retry-item` 共用这一解析边界；不新增 HTTP API、request/response schema、数据库表或第二套状态机。

## 只读运行时证据

仅使用 `data/paper_search/state.sqlite3` 的 SQLite `mode=ro`/`-readonly` 查询，没有调用 Store 构造函数或迁移逻辑：

| 实体 | 观察结果 |
|---|---|
| batch `1a76e369-c638-4f2c-a430-42552a1e7012` | `waiting_login`；`search_id=acm-manual-20260922144403614390`；`search_expires_at=2026-09-22T16:44:03.614546Z` |
| item `9eed783f-ff98-4021-99dd-1ab2787688cb` | `waiting_login`、`LOGIN_REQUIRED`、`attempt_count=1`；`snapshot_json` 2784 bytes，`snapshot_hash` 非空 |
| 持久快照身份 | `candidate_id=014eb508824e53378629b79e08d9ff2e` 与 item 一致；`search_id` 与 batch 一致 |
| 持久快照 URL | ACM article `https://dl.acm.org/doi/10.1145/3658644.3690205`；PDF 候选同为 `dl.acm.org` |
| 完整性 | 计算 SHA-256 与存储 hash 完全相等 |
| live search | 对应 `search_sessions` 已过期，`search_results` 当前为 0；已无可依赖的 live 结果重建路径 |

因此当前失败不是候选丢失，而是路由先执行 `_paper_search_expired`，在到达 durable snapshot restore 之前返回 `SEARCH_EXPIRED`。

## 现有可复用边界

- `routes_paper.py:_paper_snapshot_for_item`（约 893–924 行）目前先读 `search_sessions`/候选并检查搜索 TTL，是阻塞点。
- `PaperImportBatchService._snapshots_for`（约 399–502 行）已经先逐 item 调用 `store.get_snapshot`；完整且 hash 校验通过时直接返回，不依赖 live session、旧 `search_expires_at` 或进程内 `_snapshots`。快照不完整时才保留重建门禁。
- `PaperImportBatchStore.get_snapshot`（约 561–577 行）校验 `snapshot_json` 的 SHA-256、JSON 可恢复性和 `candidate_id/search_id` 非空；必须继续作为唯一持久快照读取入口。
- `_paper_item_browser_target`（约 1079–1100 行）继续从服务端快照取 URL，并只接受精确 `dl.acm.org`/`ieeexplore.ieee.org` origin；`PaperBrowserManager` 和下载器的 URL、重定向、SSRF/allowlist 校验不变。
- `login`（约 1134–1152 行）仍只打开受控 headed page；`resume`（约 1155–1208 行）仍检查内存 session 的 `required/expired/closed`，再交给 `resume_item` 的 CAS/lease/status 约束。
- `PaperBrowserManager` 的 session TTL（约 639–665 行）仍是浏览器会话生命周期，不是研究任务或候选快照 TTL；`open_session`（约 788–823 行）继续使用同一 persistent profile，空闲回收只释放 page/context/profile lock。

## 最小实施方案（不扩大 Spec032）

1. 在 `_paper_snapshot_for_item` 已完成 item/batch 存在性检查后，先调用现有 service durable resolver（直接复用 `_snapshots_for(batch.batch_id, None)`；若代码边界不允许路由调用私有方法，只增加一个不对外暴露的薄 wrapper，内部仍只委托该方法）。
2. 对返回集合做窄身份检查：目标值的 `candidate_id` 必须等于 item 的 `candidate_id`，`search_id` 必须等于 batch 的 `search_id`；目标缺失、hash 校验失败、JSON 不可恢复或身份不匹配时 fail-closed，不能退回客户端输入或任意 live URL。持久快照完整时**跳过** `_paper_search_expired`。
3. 将已校验的 durable snapshot 列表交给现有 `_paper_item_browser_target`，保留其 URL 精确 origin 检查。`login`/`resume` 的公开响应、错误码和 session 清理逻辑不变；`resume_item` 继续只允许既有 `waiting_login/failed` 状态，`retry_item` 继续只允许 `failed`，`waiting_login` 不转入 retry。
4. 对缺失/损坏快照保留现有 live-search fallback 和稳定错误（如 `SNAPSHOT_REBUILD_REQUIRED`、`SEARCH_EXPIRED`、`SEARCH_NOT_FOUND`、`CANDIDATE_NOT_FOUND`）；不要用过期 search 结果重建，也不要静默把坏快照当成可用快照。
5. 不修改 `PaperBrowserManager` TTL。TTL 到期仍关闭临时 session/page 并 fail-closed；批次和 item 的持久状态不删除、不取消、不重跑研究。用户再次点击登录时，复用同一 persistent profile；profile 中仍有效的 publisher cookie 可以继续使用，publisher 授权已过期则照现有 `LOGIN_REQUIRED`/`BROWSER_SESSION_EXPIRED` 语义回到可行动的登录状态。
6. 不改搜索结果 GET、批次创建、整批 retry 或研究重检索/refresh 路径；本修复只解决已有 import-item 的登录/继续/单条恢复。没有必要新增 schema、迁移或公开接口。

## 现有测试与缺口

已有保护应继续通过：

- `tests/paper_discovery/test_paper_import_batch_service.py`：过期 search session + durable snapshot 可执行、缺失 `search_expires_at` 的 durable batch 可恢复、重启后从 SQLite 快照恢复、损坏快照要求 rebuild。
- `tests/paper_discovery/test_paper_import_batch.py`：快照/attempt 跨重启持久化、快照篡改触发 `SNAPSHOT_REBUILD_REQUIRED`。
- `tests/paper_discovery/test_paper_browser.py`：服务端快照与 allowlist、零 KB 写入、缺失/过期 browser session、精确 session 关闭。
- `tests/paper_discovery/test_paper_import_batch_api.py`：server snapshot resume、登录后 resume、browser session race 的 424 脱敏错误。
- `tests/paper_discovery/test_paper_browser_manager.py`：TTL 回收、profile lock、context 重开、过期后 fail-closed。

本修复必须补的最小缺口：

1. 路由测试：expired `search_sessions` + 完整 durable snapshot 时，`login` 仍返回 opened，并使用快照中的受控 ACM/IEEE URL；不读取客户端 URL、不触碰 KB。
2. 路由/API 测试：同一场景在服务/进程内 session 重新打开后，`resume` 不返回 `SEARCH_EXPIRED`，而继续走既有 downloader、CAS、item 状态和精确 session 清理。
3. 负向测试：持久快照缺失、hash 损坏、candidate/search 身份不匹配时，仍 fail-closed（`SNAPSHOT_REBUILD_REQUIRED` 或既有搜索门禁），且 browser manager 不被调用；allowlist/SSRF 与现有测试保持不变。
4. 生命周期回归：browser session TTL 到期只回收临时浏览器资源，批次仍为 `waiting_login`，下一次 login 可重新打开同一 persistent profile；不把 session TTL 改成无限或修改任务/搜索 TTL。

## 验收口径

实现后先跑上述后端定向测试和静态检查，再用实际已有 batch 做只读 GET 状态确认；真实登录/继续 smoke 需在实现、评审和部署门禁之后执行。成功标准是“过期搜索仍可从完整服务端快照打开受控登录页并继续”，而不是延长 live-search TTL、重跑目录检索或宣称 publisher 授权永不过期。

## Backend-dev 交接（未启动）

仅在根会话关闭 KB 分支并创建 `codex/fix-paper-login-recovery` 后启动；当前工作树的 KB/frontend 改动不得作为本 Task 的实现基线。角色配置要求依次读取 `progress-logging`、`strategic-compact`、`backend-patterns`、`regression-guard`、`tdd-workflow`、`python-testing`；本 Task 只允许改 `backend/**` 与后端测试。

### TDD 最小顺序

1. **RED（两个测试文件）**：先在 `tests/paper_discovery/test_paper_import_batch_service.py` 增加 durable snapshot 在过期 search session 后仍可解析的 wrapper 契约；再在 `tests/paper_discovery/test_paper_browser.py` 增加 expired search + valid durable snapshot 时 login 仍打开受控 URL 的路由契约。测试必须使用 `tmp_path`/fake boundary，不初始化 `data/paper_search`，不 POST、不启动浏览器。
2. **GREEN（两个生产文件）**：在 `backend/app/paper_discovery/application/paper_import_batch_service.py` 增加一个 public-internal 薄 wrapper（建议 `get_item_snapshot_candidates`），内部委托现有 `_snapshots_for(batch_id, None)` 并校验 item/batch/candidate/search 身份；在 `backend/app/api/routes_paper.py` 让 `_paper_snapshot_for_item` 调用 wrapper。路由不得直接调用私有方法；不新增 HTTP API、schema、迁移或浏览器 TTL 配置。hash/损坏快照应继续 fail-closed，现有状态/CAS/allowlist/SSRF 逻辑不动。

### 建议命令

RED（写完测试后预期失败）：

```text
.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_batch_service.py::test_item_snapshot_candidates_reuse_durable_snapshot_after_search_expiry \
  tests/paper_discovery/test_paper_browser.py::test_login_opens_from_durable_snapshot_after_search_expiry
```

GREEN/定向回归：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_service.py tests/paper_discovery/test_paper_browser.py tests/paper_discovery/test_paper_import_batch_api.py
.venv/bin/ruff check backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/api/routes_paper.py tests/paper_discovery/test_paper_import_batch_service.py tests/paper_discovery/test_paper_browser.py tests/paper_discovery/test_paper_import_batch_api.py
.venv/bin/python -m py_compile backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/api/routes_paper.py
.venv/bin/python scripts/check_test_layout.py
```

依赖阻塞：当前 Spec032 总体仍暂停，但本次仅授权上述 login/resume 恢复窄范围；不得顺手处理整批 retry、搜索刷新、浏览器 TTL 或 Spec032 收口。真实部署、POST、headed browser smoke 留待实现评审和验收门禁之后。

