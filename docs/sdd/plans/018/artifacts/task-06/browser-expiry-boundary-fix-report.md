# Task06 Browser Expiry Boundary Fix Report

## 结论

`PASS（过期竞态导入边界隔离门）`。

认证请求在响应体读取或 PDF 校验期间跨过 TTL 时，browser session 在返回成功
`DownloadResult` 前再次 fail-closed 检查并关闭资源。即使下载器已经返回成功结果，
`import_candidate` 仍会从 bound `BrowserSession.download_pdf` 取得受控的
`import_boundary`，在 manager 状态锁内做最终 TTL 检查；过期时不会调用
`PaperImportPort.import_paper`，因此 metadata/vector 写入为 0，调用方可保留稳定的
`BROWSER_SESSION_EXPIRED` 错误码。

## 当前证据

reviewer 的故障注入复现了：fake request 在 `get()` 返回后推进时钟，旧链路仍会把成功
结果交给 KB port。另一个并发测试显示 manager 工作树已采用 state-lock 保护
`new_page()` 到 session 注册的窗口；本轮保留该实现，并同步其测试语义，确保 TTL 清理
等待新 session 注册而不误关共享 context。

## 改动文件

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py`
  - 增加 `BrowserSession.import_boundary()`，把最终有效性检查与 KB port 调用入口置于
    manager state lock 保护范围。
  - `_close()` 与 import boundary 共享 state lock，避免 TTL cleanup 在最终检查和
    `import_paper()` 之间关闭 session。
  - `authenticated_pdf_request()` 在响应体/PDF 页校验后、返回成功结果前复核 TTL。
- `backend/app/paper_discovery/application/paper_import.py`
  - 识别 bound browser downloader 的最小生命周期协议；公共 downloader 仍使用
    `nullcontext`，不引入第二套下载器或知识库写入逻辑。
  - 调用 `PaperImportPort.import_paper()` 前进入最终生命周期 guard。
- `tests/test_paper_browser_manager.py`
  - 注入响应体期间过期，断言稳定错误码、session/page/context/Playwright 均关闭。
  - 校正并发 reopen 测试，断言 state-lock 保护注册窗口后旧 session 才可被回收。
- `tests/test_paper_import.py`
  - 注入下载完成后过期，断言 import boundary 拒绝写入且 port 调用次数为 0。

## 测试与验收

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser_manager.py tests/test_paper_import.py` | 0 | 41 passed，5 个既有 DeprecationWarning |
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py` | 0 | 72 passed，5 个既有 DeprecationWarning |
| `.venv/bin/ruff check backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_import.py tests/test_paper_browser_manager.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_import.py tests/test_paper_browser_manager.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

补充复验：首次整组运行暴露新增过期测试未注入离线 DNS resolver；仅在测试构造器中补入
既有 `_offline_public_dns` 夹具后，原定向命令再次得到 `72 passed`，未产生业务逻辑改动。

## 决策依据

- 只在已有 browser session 与已有 `PaperImportPort` 之间增加窄协议，避免恢复旧下载、
  安全、导入或向量实现。
- `BrowserSession` 是 route 传入 downloader 的 bound method owner，因此无需改变 route
  或数据库 schema 即可在 import boundary 获得可信 session 生命周期。
- 将状态锁扩展到关闭路径是必要的，否则 timer 线程可能在最终检查后回收资源；锁只保护
  生命周期状态，不持有任何模型、网络或知识库内部实现。

## 风险与阻塞

- 未启动真实 Playwright、未访问 ACM/IEEE、未连接 Qdrant、未执行网络请求或
  `confirm-replace`；真实浏览器/跨进程与生产切换仍是 Task06 总门禁的未验收项。
- `PaperImportPort` 若已经开始执行内部多阶段写入后才自行失败，仍由既有补偿账本处理；
  本修复保证的是“过期在 port 入口前”不产生任何 KB 写入。
- 全仓库历史测试中的 legacy/migration_unverified 失败不由本子任务恢复旧 API。

## 主 Agent 后续动作

1. 将本报告与 browser lifecycle 的其他报告一并纳入 Task06 工作树审计。
2. 复跑 Task06 定向门禁，并检查最终 reviewer 是否将该 P1 标记为已关闭。
3. 与 generation-bound、真实 Qdrant/alias、跨进程锁和 confirm-replace 门禁一起决定
   Task06 是否可以进入 production GO；本报告本身不改变 Task06 总状态。

## 执行元数据

- 开始：2026-09-10 10:10（约）
- 结束：2026-09-10 10:15（约）
- 总耗时：约 5 分钟
- 逻辑角色：backend-dev
- 模型：按主 Agent 临时分派使用 Luna high；本报告不固化模型规则
- token / tool 统计：未提供
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-browser-expiry-boundary-fix.md`
