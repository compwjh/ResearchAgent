# Spec018 Task06：Browser Session Lifecycle 后端测试报告

## 结论

```text
conclusion=PASS (isolated browser-session lifecycle gate)
specified_tests=31/31 passed
additional_boundary_tests=17/17 passed
shutdown_probe=PASS
ruff=PASS
py_compile=PASS
git_diff_check=PASS
real_browser_or_site_touched=false
real_service_or_qdrant_touched=false
confirm_replace_executed=false
business_code_or_tests_modified_by_tester=false
production_cutover=NOT EXECUTED / NOT AUTHORIZED
```

当前 browser session lifecycle 加固在离线 fake/内存边界下通过：TTL 到期会 fail-closed 并释放 page/context/profile lock；重复 login 会关闭并移除旧 session；manager failure recovery/close 会清理活动 session；shutdown 会关闭所有 item session、清空 registry 并关闭 manager；过期或缺失 session 的 resume 不会调用导入服务。

## 验证命令与退出码

| 命令 | 退出码 | 数量 / 真实结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/test_paper_browser.py -q` | 0 | **5 passed** |
| `.venv/bin/python -m pytest tests/test_paper_browser_manager.py -q` | 0 | **21 passed**；5 个第三方 DeprecationWarning，无失败 |
| `.venv/bin/python -m pytest tests/test_paper_import_batch_api.py -q` | 0 | **5 passed** |
| `.venv/bin/python -m pytest tests/test_kb_startup_generation_gate.py -q` | 0 | **3 passed** |
| `.venv/bin/python -m pytest tests/test_paper_download_security.py -q` | 0 | **10 passed** |
| `.venv/bin/python -m pytest tests/test_paper_import_batch.py -q` | 0 | **4 passed** |
| 纯内存 `main.lifespan` shutdown probe（2 sessions + manager） | 0 | **通过**：2/2 session closed、registry empty、manager closed |
| `.venv/bin/ruff check backend/app/api/routes_paper.py backend/app/main.py backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import_batch_api.py` | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile backend/app/api/routes_paper.py backend/app/main.py backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import_batch_api.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

指定测试共 31 项，附加边界回归共 17 项，合计 **48/48 passed**。

## 生命周期覆盖

| 场景 | 证据 |
|---|---|
| TTL 过期 | fake clock 到期后 `goto` 返回 `BROWSER_SESSION_EXPIRED`；page/context/playwright/profile lock 均清理，session 从 manager 集合移除 |
| 重复 login | route login 先关闭并移除 item 旧 session，再打开新 session；持久化写 spy 保持 0 |
| manager failure recovery | page 导航异常映射为 `BROWSER_CRASHED`，manager 关闭所有活动 session/context；下一次 session 可重新启动 |
| manager close | manager recovery/close 路径保持幂等并释放资源；相关 manager 测试通过 |
| shutdown | 内存 lifespan 探针验证所有 item session close、`paper_browser_sessions.clear()` 和 manager close |
| resume 不调用导入 | 缺失或 TTL 过期 session 返回 424 稳定错误；`resume_item` 调用记录与 store writes 均为 0；正常 resume 才委托现有 session downloader |
| startup boundary | lifespan 只执行 catalog recovery 与 generation gate 检查，不执行旧 fixed-collection mutation |

## 真实环境未覆盖边界

- 未启动真实 Playwright、真实浏览器进程或 headed login 页面；未访问 ACM/IEEE 或任何网站。
- 未连接真实 Qdrant、生产 API 服务、用户 `data/kb`/`data/papers` 或真实原件；未执行真实导入。
- 未执行 `--confirm-replace`、alias/Collection 写删、真实服务 SIGTERM/进程崩溃重启或跨进程 session 恢复。
- TTL 测试使用注入 fake clock，未替代真实等待；网络断开、浏览器进程被杀、page/context close 抛错的真实 SDK after-effect 仍需真实维护窗口前的独立门禁。
- 本报告是 Task06 browser lifecycle 的隔离功能测试 PASS，不构成生产 index cutover 或真实数据操作授权。

## 约束与交接

- 未修改业务代码或测试；本报告与进展日志是本角色新增落盘物。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-094018.md`
- 本报告：`docs/sdd/plans/018/artifacts/task-06/browser-session-lifecycle-test-report.md`
