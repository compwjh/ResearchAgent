# Task06 Browser Boundary 独立评审

## 结论

**GO（T-BROWSER-BOUNDARY 语义子门；不等于 Task06 生产切换放行）**。

当前 route 的“知识库 source/metadata/index 写入中立”隔离行为成立，来源解析也确实来自服务端搜索快照。架构师已将 closure matrix 的 current behavior 和 T-BROWSER-BOUNDARY 断言精确改为“零知识库持久化写入；受控 profile 认证状态可显式持久化”，这与实现使用固定 persistent Playwright profile 的事实一致。因此原先关于“zero persistence”字面冲突的阻塞项已解除。login 状态门、session owner/token/TTL 和终止路径清理仍是后续生命周期加固条件，但不再阻塞本次已明确的知识库写入隔离子门。

## 检查范围

- `backend/app/api/routes_paper.py:725-809`
- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:467-545`
- `tests/test_paper_browser.py:1-198`
- closure matrix `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json:88-104,178-184`
- 前置缺口记录 `docs/sdd/plans/018/artifacts/task-06/import-closure-gap-analysis.md:60-69,87-95`

未修改业务代码；未启动真实 Playwright、未访问网络、未连接 Qdrant、未使用 `confirm-replace`。

## 已确认的正确边界

1. `_paper_item_browser_target` 先读取服务端 item/search snapshot，再从 snapshot 中选择 candidate；客户端请求体没有提供 URL 或凭据入口（`routes_paper.py:725-746`）。
2. 站点只接受精确 hostname `dl.acm.org` 或 `ieeexplore.ieee.org`，不在白名单的来源在打开 session 前返回 `BROWSER_ORIGIN_NOT_ALLOWED`（`routes_paper.py:740-745`）。manager 还会再次执行 exact-origin 校验（`paper_browser_manager.py:495-500`）。
3. resume 只取 item-scoped session 的受控 `download_pdf` 与 context，委托给 `PaperImportBatchService.resume_item`，没有 route 级 direct source/metadata/index 写入（`routes_paper.py:773-792`）。成功或异常 finally 会关闭并移除该 item session（`routes_paper.py:800-809`）。
4. 测试中的 fake write spy、恶意来源、缺 session、downloader/context 委托与 exact-session close 均有断言；这些是有效的隔离测试，不是对真实浏览器 profile 的持久化证明（`tests/test_paper_browser.py:140-198`）。
5. `paper_browser_manager.py` 当前 diff 仅是 import 顺序、表达式和 `suppress` 写法整理，没有看到 origin、下载校验、profile lock 或 context 启动参数的语义变化；相关 manager 回归仍通过。

## 阻塞项与风险

### 已解除：实现与矩阵的“zero persistence”语义不一致

`PaperBrowserManager._ensure_profile` 会创建/修改 profile 目录并设置权限（`paper_browser_manager.py:501` 经 `:467-493` 间接调用）；`_ProfileLock.acquire` 还会创建 `.profile.lock`；随后 `launch_persistent_context(str(self.profile_dir), ...)` 会把浏览器 storage state 写入该目录（`paper_browser_manager.py:487`）。这不是 source/metadata/index 写入，但确实是磁盘持久化。

该事实现在已被 closure matrix 明确记录：login current behavior 为“without knowledge-base persistence; authentication state may remain in the explicitly configured browser profile”，测试断言为“zero knowledge-base persistence writes; controlled authentication profile persistence is explicit”（`upload-closure-matrix.json:90-94,184`）。因此不再把 profile 磁盘写入误报为失败；当前测试证明的范围正是 matrix 要求的 zero KB writes。

仍需保留 profile 权限、TTL 和清理作为生产安全债务；它们属于受控 profile 的生命周期治理，不应再以“zero persistence”名义回退该子门。

### P1（后续生命周期加固）：login 没有 item 状态门

`login_paper_import_item` 只解析 snapshot 就打开 session（`routes_paper.py:754-763`），没有要求 item 当前为 `waiting_login`，所以理论上 queued、completed 或 cancelled item 都可以建立登录 session。前置缺口记录已指出这一问题。建议后续固定只允许当前有效状态，并对 completed/cancelled/过期批次返回稳定错误；这不是当前 matrix 两条 browser assertions 的失败。

### P1（后续生命周期加固）：session 没有 durable attempt owner/token、TTL 或终止路径统一失效

session 仅以 `paper_browser_sessions[item_id]` 存在于进程内字典；没有和 item 的 `attempt_owner`/`attempt_token` 绑定，也没有跨重启语义。login 替换旧 session 时会 close，但 batch cancel、lease expiry/recover、搜索过期、进程退出及 manager.close 不会从该字典逐 item 关闭并清理。resume finally 的关闭只覆盖 resume 被调用的路径（`routes_paper.py:800-809`），不能替代上述生命周期协议。它不改变本次 route 的 zero-KB-write 结论，但在真实生产登录和异常恢复前必须补齐。

### P2（后续生命周期加固）：resume 的 session 与当前 snapshot 的 URL 关联仅靠 item key

`resume_paper_import_item` 解析了当前 `site/article_url`（`:779`），但没有校验 session 自身绑定的 site/target 是否一致；真实 manager 的 session 是受控对象，但 item-scoped dictionary 仍缺少显式 binding contract。建议 session token/target digest 由服务端创建并在 resume 前核对，避免 stale session 被复用。该项是后续加固建议，不否定当前 matrix 已明确的委托边界。

## 精确验证结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_import_batch.py -k 'login or resume'` | 0 | 4 passed, 4 deselected |
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import_batch.py -k 'login or resume or browser or session'` | 0 | 23 passed, 4 deselected；5 个既有 DeprecationWarning |
| `.venv/bin/python -m ruff check backend/app/api/routes_paper.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_paper.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 本次子门放行与后续条件

1. **已满足**：架构师已在 matrix 中明确 zero persistence 指 zero knowledge-base persistence，并显式允许受控认证 profile 持久化；current behavior、assertions、状态和证据已同步。
2. **已满足**：T-BROWSER-BOUNDARY 精确命令退出码为 0；独立 route/manager 回归和静态检查均通过。
3. **后续生产条件**：补 login item-state/过期 guard、session token/target binding、TTL 以及 manager/cancel/recover/异常退出清理；补充真实 manager seam 对 profile/lock/storage-state 允许集合的观察。
4. **范围限制**：本报告只放行 Browser Boundary 隔离子门；Task06 的真实 Qdrant/索引维护窗口、其他 closure entries 及整体 production cutover 仍由总矩阵和独立验收决定。

## 主 Agent 后续动作

- 可采纳实现报告的 `GO（隔离功能门）` 作为 Browser Boundary 局部证据；它现在与已修订 matrix 语义一致。
- 在生产登录和异常恢复前补齐生命周期加固；不要因为受控 profile 的已声明本地持久化而把它重新标记为 zero-persistence 失败。
- 仍不得触碰真实 PDF、Qdrant 或生产索引；整体生产放行由总矩阵和 Task06 验收决定。

## 评审记录

- 2026-09-10：独立 backend-reviewer 首轮只读审查；测试与静态检查通过，但因 zero-persistence 语义冲突及生命周期缺口判定 NO-GO。
- 2026-09-10：架构师将 matrix 改为“零知识库持久化写入；受控 profile 认证状态可显式持久化”，复核确认实现与矩阵一致；Browser Boundary 子门改为 GO，生命周期治理列为后续生产条件。
