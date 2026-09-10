# Spec018 Task06 Browser Lifecycle Final Backend Review v2

## 固定结论字段

```text
conclusion=GO (isolated browser lifecycle / expiry propagation subgate)
expiry_during_request_p1=CLOSED
concurrent_reopen_idle_cleanup_p1=CLOSED
targeted_tests=85 passed
focused_fix_tests=4 passed
ruff_exit_code=0
py_compile_exit_code=0
git_diff_check_exit_code=0
real_browser_or_site_touched=false
real_network_touched=false
real_qdrant_touched=false
confirm_replace_executed=false
business_code_or_tests_modified_by_reviewer=false
```

## 审查范围

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py`
- `backend/app/paper_discovery/application/entry.py`
- `backend/app/paper_discovery/application/paper_import.py`
- `backend/app/paper_discovery/application/paper_import_batch_service.py`
- `backend/app/api/routes_paper.py`
- `backend/app/main.py`
- 对应 browser/import/batch/integration/security/startup 测试与 Task06 生命周期交接报告

本轮只读审查当前工作树；没有启动真实 Playwright/浏览器、访问网站或网络、启动服务、连接 Qdrant、执行真实导入或 `confirm-replace`。

## P1 关闭证据

### 1. 请求期间 TTL 到期不会调用 `PaperImportPort` — CLOSED

代码证据：

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:414-417`：响应体读取和 PDF 校验后、返回成功 `DownloadResult` 前再次 `_ensure_active()`；期间到期会关闭 session 并抛出稳定 `BROWSER_SESSION_EXPIRED`。
- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:199-211`：`import_boundary()` 在 manager `_state_lock` 内做最终有效性检查并保持锁直到 importer port 调用完成，TTL close/recovery 无法插入检查与 port 入口之间。
- `backend/app/paper_discovery/application/paper_import.py:192-204,495-496`：仅对 bound browser downloader 发现窄生命周期协议；`PaperImportPort.import_paper()` 在该 guard 内调用，普通 downloader 仍使用 `nullcontext()`。

针对性测试：

- `tests/test_paper_browser_manager.py:575`：fake response body 期间推进时钟，断言稳定过期错误、session/page/context/Playwright 全部关闭。
- `tests/test_paper_import.py:239`：下载成功后推进时钟，`import_boundary()` 在 KB port 入口拒绝，断言 `PaperImportPort.import_paper()` 调用次数为 0、错误码为 `BROWSER_SESSION_EXPIRED`。

这闭合了上一轮复现的窗口：即使下载器已经产生成功结果，只要 TTL 在 port 入口前到期，KB 写入不会发生；batch 层仍只记录一次失败 attempt，不进入 `completed`。

### 2. concurrent reopen/idle cleanup 不会绑定已关闭 context — CLOSED

代码证据：

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:647-667`：profile ownership、context 获取、`new_page()`、page 配置及 `_sessions.add(session)` 在同一个 `_state_lock` 临界区内完成。
- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:689-724`：recovery/idle cleanup 使用同一 state lock；`close()` 不再有锁外 profile release 旁路。

针对性测试：

- `tests/test_paper_browser_manager.py:242`：阻塞新 session 的 `new_page()`，并发触发旧 session TTL；断言旧 session 先完成关闭、新 session 注册后共享 context 仍未关闭且 profile ownership 保持。
- `tests/test_paper_browser_manager.py:296`：ACM/IEEE 两站点并发 open，断言两个 session 成功、共享同一未关闭 context、profile ownership 未丢失。

这闭合了上一轮指出的“`new_page()` 后、session 注册前 idle cleanup”与多站点 `_profile_owned` 交错窗口。

## 错误透传与安全边界

- `BROWSER_SESSION_EXPIRED` / `BROWSER_SESSION_REQUIRED` 从 browser manager 经 application entry、single import、batch item safe error 到 route 保持稳定；异常 resume 映射 HTTP 424。
- 过期/缺失 session 的 preflight 不调用 batch/import；下载器竞态失败时 batch item 保持 `failed`，不会执行 validating/indexing/completed 成功 transition，也不会二次恢复导入。
- 固定安全错误表只返回脱敏消息；测试注入 URL、Cookie、token、secret 后，`PaperImportError`、持久化 item message 和 HTTP body 均不含敏感文本。
- `SITE_ORIGINS` 仍为精确 ACM/IEEE HTTPS origin，未放宽 hostname、端口或 fragment；登录 route 仍只消费服务端 snapshot。
- 登录 route 只使用受控 browser seam，不执行 KB source/metadata/index 写入；现有 fake write spy 保持 0。

## 验证命令与退出码

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py tests/test_paper_download_security.py tests/test_kb_startup_generation_gate.py` | 0 | **85 passed**，5 个既有第三方 `DeprecationWarning` |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py::test_import_boundary_rechecks_expiry_before_port_write tests/test_paper_browser_manager.py::test_authenticated_pdf_request_rechecks_expiry_after_response_body tests/test_paper_browser_manager.py::test_ttl_reclaim_cannot_close_context_during_concurrent_reopen tests/test_paper_browser_manager.py::test_two_sites_open_concurrently_share_owned_context` | 0 | **4 passed** |
| `.venv/bin/ruff check`（本轮 15 个实现/测试目标文件） | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile`（本轮 15 个实现/测试目标文件） | 0 | 全部编译通过 |
| `git diff --check` | 0 | 通过 |

## 剩余风险与未覆盖真实边界

- 未验证真实 Playwright context/page close、浏览器进程被杀、SIGTERM、真实 profile/storage-state、跨进程 profile lock、跨 worker session registry 或真实 ACM/IEEE 登录。
- `import_boundary` 将 manager state lock 持有到 `PaperImportPort.import_paper()` 完成；这是本轮原子性设计的有意取舍，真实 KB 写入耗时与锁争用仍需维护窗口观察。
- 真实请求超时、网络抖动、系统时钟/进程调度、真实 page close 异常的 after-effect 仍未覆盖；离线 fake/timer 证据不替代运行时门禁。
- Task06 整体真实 Qdrant/alias/finalize/cutover 仍未放行；本报告只裁决 browser lifecycle 与 expiry propagation 隔离子门禁。

## 交接

- 本报告为独立 backend-reviewer v2 产物；未修改业务代码或测试代码。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-100136.md`
