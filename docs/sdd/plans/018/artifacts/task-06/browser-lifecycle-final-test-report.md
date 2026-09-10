# Spec018 Task06：Browser Lifecycle + Expiry Propagation 最终后端回归报告

## 结论

`PASS（隔离 browser lifecycle / expiry propagation 门禁）`。

指定七个后端测试文件共 **68/68 passed**。测试覆盖 idle TTL 自动过期、page/context/Playwright/profile-lock 资源清理、manager recovery/close 清理、过期 resume 返回 HTTP 424 且不触发导入、browser session error code 持久化并保持 `failed`（不转 `completed`），以及 URL/Cookie/secret 等敏感文本不泄露。

本轮只使用 fake/in-memory browser、服务替身和临时目录；未连接真实浏览器、网站、服务、Qdrant 或网络。

## 命令、退出码与数量

| 命令 | 退出码 | 数量 / 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py` | 0 | **68 passed**，5 个既有第三方 `DeprecationWarning`，1.49s |
| `.venv/bin/ruff check backend/app/api/routes_paper.py backend/app/main.py backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py` | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile backend/app/api/routes_paper.py backend/app/main.py backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py` | 0 | 14 个目标文件编译通过 |
| `git diff --check` | 0 | 通过，无 whitespace/error |

补充：尝试的全仓 `.venv/bin/ruff check backend tests/...` 退出码为 1，共 49 个问题，均分布在本轮未修改的既有模块；本轮变更边界 scoped ruff 已通过，不将该基线问题归因于 browser lifecycle 变更。

## 验收覆盖摘要

- idle TTL：fake clock/短 TTL 到期后自动关闭 session page、context、Playwright 和 profile lock，并从 manager 活动集合移除。
- 资源清理：显式 `close()`、manager recovery/close、重复 login 替换及应用 shutdown 路径均验证幂等清理。
- 过期 resume：返回稳定 `BROWSER_SESSION_EXPIRED` / `BROWSER_SESSION_REQUIRED` 与 HTTP 424，不调用导入服务。
- 状态与错误码：browser session code 沿 application → batch service → route 透传；失败 item 保持 `failed`，不发生 `completed` transition。
- 敏感信息：注入 URL、Cookie、secret、token 的异常文本不会出现在持久化 error message 或 HTTP body。

## 未覆盖真实边界

- 未启动真实 Playwright/浏览器进程，未访问 ACM/IEEE 或任何网站，未验证真实登录页面与真实浏览器进程被杀后的 SDK 行为。
- 未启动生产 API/后台服务，未连接真实 Qdrant，未操作真实 `data/kb`、`data/papers` 或原件，未执行网络请求或真实导入。
- 未验证跨进程/进程重启后的内存 session 恢复、真实 SIGTERM/崩溃 shutdown、真实 profile/storage-state 持久化及多 worker 并发。
- TTL 使用注入 fake clock/隔离测试替身，不能替代生产时间漂移、网络抖动和真实浏览器资源泄漏观察。
- 未执行 `confirm-replace`、alias/collection 切换或生产 cutover。

## 交接约束

- 本轮未修改业务代码或测试；仅新增本报告及 backend-tester 进展日志。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-100154.md`
