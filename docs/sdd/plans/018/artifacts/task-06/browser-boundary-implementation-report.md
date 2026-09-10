# Task06 Browser Boundary 实现报告

## 结论

`GO（隔离功能门）`。本轮没有改动论文业务的持久化实现；现有 route 已满足本子任务边界：登录只基于服务端批次快照打开受控浏览器 session，不调用 source/metadata/index 写入；resume 只把 session 的受控下载回调和 context 委托给既有 `PaperImportBatchService.resume_item`，由其继续进入 immutable import/compensation 链路。

## 实现与证据

- `tests/test_paper_browser.py:1-198`
  - 使用 fake batch/discovery store、browser manager/session 和写入 spy，未启动 Playwright、未访问网络、未触碰 Qdrant。
  - `:140-150` 验证登录从服务端 snapshot 解析 ACM 站点并只保存 item-scoped session，所有知识库写入 spy 为 0。
  - `:153-164` 验证非 ACM/IEEE 来源在打开 session 前被拒绝，写入 spy 为 0。
  - `:167-177` 验证没有登录 session 时 resume 返回稳定 `BROWSER_SESSION_REQUIRED`，不会调用批任务导入。
  - `:180-198` 验证 resume 传递 session-owned downloader/context，完成后只关闭该 item 的 session 并清理映射，知识库写入 spy 为 0。
- `backend/app/api/routes_paper.py:725-809`
  - 当前实现只接受服务端搜索快照中的 article/pdf URL，并固定映射 `dl.acm.org`、`ieeexplore.ieee.org`；登录不接受客户端 URL 或凭据。
  - login 只调用 `_paper_browser_manager().open_session`；resume 只调用 `service.resume_item`，没有 direct source/metadata/index 调用。
- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py:428-545`
  - 保留已有 origin、profile lock、session close 和受控下载边界；本轮仅整理 import、条件表达式和资源关闭写法以通过静态检查。

## 验证命令

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 0 | 50 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_import_batch.py -k 'login or resume'` | 0 | 4 passed, 4 deselected |
| `.venv/bin/python -m ruff check tests/test_paper_browser.py backend/app/api/routes_paper.py backend/app/api/common.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile`（上述 6 个实现文件及测试） | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 语义说明与风险

`PaperBrowserManager` 继续使用受控的 persistent Playwright profile，以保留 ACM/IEEE 的人工登录状态；这会产生浏览器 profile 的本地状态写入，但不是论文 source、metadata 或 index 写入。Task06 的“zero KB writes”按该边界解释并由 fake write spy 覆盖。若未来要求登录完全无磁盘状态，应另行设计 ephemeral browser context，并重新评审登录体验、凭据生命周期和既有 `paper_browser_manager` 契约。

本轮未进行真实登录、PDF 下载、服务启动或 Qdrant 操作；未声称生产门已通过。真实浏览器可用性、登录页面行为和跨进程 profile 锁仍属于后续运行时验收范围。

## 主 Agent 后续动作

将本报告与测试文件纳入 Task06 当前批次的独立 reviewer/tester 收口；更新 closure matrix 时仅在 reviewer/tester 证据齐备后关闭 `T-BROWSER-BOUNDARY`，并重新计算 frozen inventory hash/digest。

## 变更日志

- 2026-09-10：新增 browser boundary 隔离测试；确认登录零知识库写入、来源白名单、session 必须和 resume 委托/清理协议。
- 2026-09-10：整理 `paper_browser_manager.py` 的既有静态检查问题；未改变 profile、origin 或下载安全语义。
