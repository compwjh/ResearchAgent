# Spec018 Task06 Browser Session Lifecycle 独立后端评审

## 结论

**NO-GO（生命周期子门禁）**。

定向测试、ruff、`py_compile` 和 `git diff --check` 均通过，ACM/IEEE 精确 allowlist 与登录路由的零知识库持久化边界未见回归；但当前实现仍有两个确定的资源释放缺口，并且存在 TTL 竞态导致过期错误码被导入层吞并的路径。在这些问题修复并补齐故障注入测试前，不能把 browser session lifecycle 标记为完成或作为真实登录/生产运行时门禁证据。

## 审查范围

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py`
- `backend/app/paper_discovery/application/entry.py`
- `backend/app/api/routes_paper.py`
- `backend/app/main.py`
- `tests/test_paper_browser.py`
- `tests/test_paper_browser_manager.py`
- 关联的过期 resume 调用链：`backend/app/paper_discovery/application/paper_import_batch_service.py`

未启动 Playwright/真实浏览器，未访问 ACM、IEEE 或其他网站，未启动服务，未执行网络请求或 `confirm-replace`，未写入知识库/Qdrant。

## Findings

### P1 — TTL 是惰性检查，闲置过期 session 不会释放任何资源

文件：`backend/app/paper_discovery/infrastructure/paper_browser_manager.py:183-193, 570-583, 631-644`

`is_expired()` 只读取单调时钟；实际关闭仅发生在后续调用 `_ensure_active()`，或 route 显式触发 `_close_item_browser_session()`。没有定时清理、manager 级过期扫描或其他 deadline callback。用户打开登录页后不再发起 `goto`/`resume` 时，即使 TTL 已经过期，page 仍在 `_sessions` 中，site lock、profile lock、persistent context 和 Playwright 进程都继续持有；另一个 manager 会持续收到 `BROWSER_PROFILE_LOCKED`。现有 TTL 测试只验证“过期后再次调用”这一触发型路径，不能证明闲置过期会收敛。

建议由 manager 的生命周期 owner 增加可证明的过期回收机制（或在明确的请求/后台维护入口统一扫描并关闭），并增加“时间经过但没有任何 session 操作后，page/site/profile/context 均已释放”的隔离测试。

### P1 — `new_page()`/page 初始化失败时泄漏已创建的 context/Playwright

文件：`backend/app/paper_discovery/infrastructure/paper_browser_manager.py:567-596`

`_ensure_context()` 可能已经成功创建并保存 persistent context 与 Playwright；随后 `context.new_page()`、`set_default_timeout()` 或 `set_default_navigation_timeout()` 抛错时，`session` 尚未创建。异常分支只释放 `site_lock` 和 `_ProfileLock`（`:587-595`），没有调用 `_recover_after_failure()` 或 `_release_if_idle()`，因此 `_context`/`_playwright` 保持非空且 context 未关闭。下一次打开会复用这个可能已损坏的 context，manager close 之前浏览器资源也持续泄漏。

建议为“context 已创建但 session 尚未注册”的异常统一走 manager recovery，并补 `new_page`、page 配置三类失败的 context/Playwright/profile/site lock 断言。

### P1 — TTL 与导入之间存在竞态；过期错误会被吞成通用导入失败

文件：`backend/app/api/routes_paper.py:811-845`；调用链 `backend/app/paper_discovery/application/paper_import_batch_service.py:406-429`、`backend/app/paper_discovery/infrastructure/paper_browser_manager.py:246-255`

route 先调用 `_browser_session_is_expired()`，再调用 `service.resume_item()`；两者之间 TTL 可能到期。此时 batch service 已 claim item 并进入 importer，`BrowserSession.authenticated_pdf_request()` 才在 `_ensure_active()` 抛出 `BROWSER_SESSION_EXPIRED`。`PaperImportBatchService._import_one()` 捕获所有异常并按安全错误表将未知 browser code 归为 `KB_IMPORT_FAILED`，返回失败批次；route 不会返回稳定的 `BROWSER_SESSION_EXPIRED`，而且“过期 resume 不进入导入”的保证只对 precheck 命中成立。虽然 browser downloader 在网络/知识库写入前会失败，仍会改变持久化批次状态并丢失可重试的 browser 错误语义。

建议让 session 生命周期检查与 resume claim/import 形成明确的原子边界，或让 `BROWSER_SESSION_EXPIRED` 在导入层保持稳定传播并将已 claim 的 item 安全回到等待登录状态；增加“precheck 后立即过期”的故障注入测试，断言 importer 不执行、item 状态/错误码稳定且无知识库写入。

### P2 — `BROWSER_SESSION_REQUIRED` 未纳入 route browser 错误码映射

文件：`backend/app/api/routes_paper.py:796-798, 831-833, 860-869`

`BROWSER_SESSION_REQUIRED` 已从 manager/application entry 导出，也被无 session/closed session 的正常 route 分支直接返回 424；但它没有加入 `_BROWSER_ERROR_STATUS`。任何经 `BrowserManagerError` 异常路径冒出的同名错误都会被代码判断降级成 `BROWSER_UNAVAILABLE`（503），造成同一稳定错误码在不同生命周期路径下状态码/错误码不一致。建议加入统一映射并补异常路径测试。

## 已确认无回归的边界

- `SITE_ORIGINS` 仍只允许精确 `https://dl.acm.org` 与 `https://ieeexplore.ieee.org`；本次改动没有放宽 origin、端口、fragment 或 hostname 规则。
- 登录 route 仍从服务端搜索 snapshot 解析站点/文章地址，客户端不能替换 URL；过期 precheck 命中时在调用 batch/import 前关闭并移除 item session。
- resume 的 session/context 仅作为既有 batch → immutable import 链路的受控 seam；route 本身未增加 source/metadata/index 写入。现有 fake write spy 仍为 0。
- manager 故障恢复的正常路径使用 `RLock`，先逐一关闭 tracked page，再关闭 context/Playwright，释放 profile lock 并清空 session 集合（`paper_browser_manager.py:606-645`）；现有 crash recovery 测试通过。
- `main.lifespan` shutdown 会遍历并关闭 item-scoped sessions、清空 route 字典，再调用 manager close（`backend/app/main.py:42-60`）；该路径未见明显旁路泄漏，但缺少真实 shutdown/close 抛错故障注入覆盖。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import_batch_api.py` | 0 | `31 passed`，5 个既有 DeprecationWarning |
| `.venv/bin/python -m ruff check backend/app/paper_discovery/infrastructure/paper_browser_manager.py backend/app/paper_discovery/application/entry.py backend/app/api/routes_paper.py backend/app/main.py tests/test_paper_browser.py tests/test_paper_browser_manager.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/paper_browser_manager.py backend/app/paper_discovery/application/entry.py backend/app/api/routes_paper.py backend/app/main.py tests/test_paper_browser.py tests/test_paper_browser_manager.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 评审记录

- 本报告为独立 backend-reviewer 评审产物；未修改业务代码、测试代码或既有实现报告。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-093957.md`
