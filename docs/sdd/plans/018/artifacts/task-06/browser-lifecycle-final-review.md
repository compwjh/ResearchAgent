# Spec018 Task06 Browser Lifecycle Final Backend Review

## 结论

**NO-GO（browser session lifecycle 子门禁）**。

当前离线隔离功能测试与静态检查全部通过，ACM/IEEE 精确 allowlist、登录路径零知识库 source/metadata/index 写入、错误码脱敏和常规资源回收未见回归。但仍存在一个确定的 P1 过期竞态：TTL 在认证请求开始后到期时，下载仍可成功并继续进入知识库 import port；另有一个 P1 并发 reopen/idle 回收窗口，可能把新建 session 绑定到已关闭的 context。两项均直接影响“过期竞态不成功导入”和“所有资源可靠释放”，修复并补故障注入测试前不能放行。

## 审查范围与约束

- 实现：`backend/app/paper_discovery/infrastructure/paper_browser_manager.py`、`backend/app/paper_discovery/application/entry.py`、`backend/app/paper_discovery/application/paper_import.py`、`backend/app/paper_discovery/application/paper_import_batch_service.py`、`backend/app/api/routes_paper.py`、`backend/app/main.py`
- 测试：对应 browser/import/batch/integration/security/startup 测试及新增 lifecycle 测试
- 未启动真实 Playwright/浏览器，未访问 ACM/IEEE 或其他网站，未启动服务，未连接 Qdrant，未执行网络请求、真实导入或 `confirm-replace`。

## Findings

### P1 — TTL 在认证请求期间到期仍可成功写入知识库

文件与位置：

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:309-310`：只在请求开始前调用 `_ensure_active()`。
- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:338-400`：请求、响应体读取、PDF 校验完成后没有再次检查 session 是否仍有效。
- `backend/app/paper_discovery/application/paper_import.py:470-489`：拿到成功 `DownloadResult` 后直接调用 `port.import_paper()`。

证据：使用 fake request 在 `get()` 内将注入时钟从 100 推进到 106（TTL=5），`session.download_pdf()` 仍返回成功的 `DownloadResult`；随后用现有 `import_candidate` seam 验证 `import_paper` 被调用一次，最终状态为 `indexed`，此时 `session.is_expired()` 已为真且 session 尚未关闭。也就是说，当前测试覆盖“调用前已过期”和“downloader 主动抛出 session code”的竞态，但未覆盖“请求完成时才过期”。

影响：过期的认证 session 可能把已下载内容提交到 KB，违反 fail-closed 的过期竞态要求；route 的稳定 `BROWSER_SESSION_EXPIRED` 透传无法挽回已经进入 `port.import_paper` 的路径。

建议：在认证请求成功返回前增加有效性复核，并将 session 有效性与下载结果交给 import boundary 做不可被并发窗口打断的最终检查；补“请求期间过期”的故障注入测试，断言 KB import port、metadata/vector 写入均为 0、item 不进入 `completed`，且只执行一次尝试。

### P1 — 并发 reopen 与 idle cleanup 存在已关闭 context 绑定窗口

文件与位置：`backend/app/paper_discovery/infrastructure/paper_browser_manager.py:624-642, 688-701`。

当前 `open_session()` 在 `context.new_page()` 后才在 `_state_lock` 下把 session 加入 `_sessions`；TTL callback 先从 `_sessions` 移除最后一个旧 session，随后 `_release_if_idle()` 在看见集合为空时关闭 context/Playwright。若新线程已通过 `_ensure_context()` 拿到旧 context、正在 `new_page()` 或尚未完成 `_sessions.add()`，idle cleanup 可先关闭该 context，之后新线程仍把 session 注册并返回。该 session 的 page/context 已关闭，且 profile ownership 已被释放，后续 resume 只能走不稳定的浏览器失败路径。

同时，`_profile_owned` 检查和设置在 `open_session()` 中不受 `_state_lock` 保护（`:624-626`），多站点并发打开可能交错操作同一 `_ProfileLock` 句柄。

建议：把 profile ownership、context 使用、session 注册和 idle release 置于同一可证明的状态/引用计数边界，或在 cleanup 前后使用代际/重新读取校验；补充“两站点并发 open + 最后旧 session TTL 回收”的确定性故障注入测试，断言新 session 可用且 context/profile lock 未被误关。

## 已确认通过的边界

- `SITE_ORIGINS` 未放宽：仍只允许精确 `https://dl.acm.org` 与 `https://ieeexplore.ieee.org`，不接受端口、fragment、相似 hostname 或非 HTTPS。
- 登录 route 仍从服务端 search snapshot 解析 article URL，客户端不能替换目标；allowlist 拒绝发生在打开 session 前。
- 登录及 preflight 过期/缺失 session 路径不调用 batch/import，现有 fake store write spy 保持 0。
- `BROWSER_SESSION_EXPIRED` / `BROWSER_SESSION_REQUIRED` 已从 browser manager 经 application entry、single import、batch item safe error 到 route 映射；正常异常路径返回 HTTP 424，不暴露 URL、Cookie、token 或 secret。
- batch browser failure 只执行一次 importer attempt，item 保持 `failed`，不执行 validating/indexing/completed 成功 transition。
- session timer 为 daemon、可取消；timer 启动失败、page 创建失败、page 导航崩溃、manager close/recovery 的常规 fake 路径均清理已跟踪 page、context、Playwright、site/profile lock。
- lifespan finally 遍历 item-scoped sessions、清空 registry 后调用 manager close；代码路径具备 shutdown 清理，但未有真实 SDK/进程退出证据。

## 验证命令与退出码

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py tests/test_paper_download_security.py tests/test_kb_startup_generation_gate.py` | 0 | **81 passed**，5 个既有第三方 `DeprecationWarning` |
| `.venv/bin/ruff check`（上述 15 个实现/测试目标文件） | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile`（上述 15 个实现/测试目标文件） | 0 | 全部编译通过 |
| `git diff --check` | 0 | 通过 |

## 残余风险与未覆盖边界

- 未验证真实 Playwright context/page close、浏览器进程被杀、SIGTERM、跨进程 profile lock、跨 worker session registry 或真实 ACM/IEEE 登录。
- TTL 使用 fake clock/timer；生产时间漂移、请求阻塞期间过期、网络抖动和多线程 reopen 尚未有自动化门禁。
- manager 的持久 profile 是显式受控边界；本审查只确认其不写入 KB source/metadata/index，不把 profile 的 credential persistence 误判为“全盘零持久化”。
- Task06 整体真实 Qdrant/alias/finalize/cutover 仍禁止执行；本报告只裁决 browser lifecycle/expiry propagation 子门禁。

## 交接

- 本报告为独立 backend-reviewer 产物；未修改业务代码或测试代码。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-100136.md`
