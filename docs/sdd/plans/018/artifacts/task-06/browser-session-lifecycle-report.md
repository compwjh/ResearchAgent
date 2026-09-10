# Task06 Browser Session Lifecycle Report

## 结果

`PASS（隔离生命周期门）`

已在现有 ACM/IEEE browser boundary 内补齐 session TTL、过期 fail-closed、重复 login 替换、manager 故障恢复和应用 shutdown 清理。TTL 可通过 `PaperBrowserManager(session_ttl_seconds=...)` 或 `PAPER_DISCOVERY_BROWSER_SESSION_TTL_SECONDS` 配置；未配置时沿用 `article_login_timeout_seconds`（默认 300 秒）。过期或已恢复失效的 session 不会进入 batch/import 链路。

## 改动文件

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py`
  - 增加稳定错误码 `BROWSER_SESSION_EXPIRED` / `BROWSER_SESSION_REQUIRED`。
  - session 创建时记录单调时钟 TTL；操作前检查过期并关闭 page。
  - manager 跟踪活动 session；`close()` 和故障恢复逐一关闭 session、清空集合、关闭 context/Playwright 并释放 profile lock。
  - 最后一个过期 session 关闭后释放空闲 browser/profile 资源。
- `backend/app/paper_discovery/application/entry.py`
  - 从受控 application boundary 导出新增 browser 错误码。
- `backend/app/api/routes_paper.py`
  - 重复 login 通过统一 helper 关闭旧 session。
  - resume 在过期或已关闭时返回稳定错误并在调用导入前清理 session。
- `backend/app/main.py`
  - lifespan shutdown 关闭并清空 item-scoped session，再关闭 manager。
- `tests/test_paper_browser_manager.py`
  - 新增 TTL 过期资源释放、故障恢复关闭全部活动 session 的隔离测试。
- `tests/test_paper_browser.py`
  - 新增过期 resume 不调用导入的隔离测试。

## 测试命令/退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import_batch_api.py` | 0 | 31 passed |
| `.venv/bin/python -m ruff check backend/app/paper_discovery/infrastructure/paper_browser_manager.py backend/app/paper_discovery/application/entry.py backend/app/api/routes_paper.py backend/app/main.py tests/test_paper_browser.py tests/test_paper_browser_manager.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/paper_browser_manager.py backend/app/paper_discovery/application/entry.py backend/app/api/routes_paper.py backend/app/main.py tests/test_paper_browser.py tests/test_paper_browser_manager.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

所有验证均使用 fake Playwright/session 和临时隔离边界；未连接真实浏览器、网站、服务或 Qdrant，未执行网络或 `confirm-replace`。

## 风险与未覆盖边界

- TTL 以进程单调时钟计时；进程重启后不会恢复旧的内存 session，持久 profile 只保留浏览器自身认证状态，不把认证状态写入知识库。
- 未验证真实 ACM/IEEE 登录页面、真实 Playwright shutdown 行为或跨进程浏览器进程异常；这些仍属于运行时验收边界。
- item-scoped route 字典仍是进程内状态；manager 故障恢复会使真实 session 失效，下一次 resume 通过已关闭检查返回 `BROWSER_SESSION_REQUIRED`，不会尝试导入。
- 未改变 ACM/IEEE allowlist、候选快照解析、immutable import/compensation 或知识库写入边界。
