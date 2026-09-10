# Spec018 Task06：Browser idle TTL timer 修复报告

## 结果

`PASS（隔离 fake browser 生命周期修复）`

仅修改了 `paper_browser_manager.py` 与 `tests/test_paper_browser_manager.py`（另按任务要求新增本报告）。未启动真实 Playwright、未访问 ACM/IEEE 或其他网络、未触碰 Qdrant/知识库原件。

## 实现摘要

- `BrowserSession` 在注册到 manager 后启动可取消的 `threading.Timer`；timer 强制设为 daemon，达到 deadline 后主动关闭 page、释放 site lock，并在最后一个 session 结束时释放 context、Playwright 与 profile lock。
- session 的 `close()`、manager recovery/close 和 `open_session()` 异常路径都会取消 timer；timer 启动失败或 page 创建失败时也会 fail-closed 清理浏览器与 profile 资源。
- timer callback 使用注入 clock 复核 deadline；若 callback 提前触发，则按剩余时间重置 timer，避免提前回收。

## 测试覆盖

- fake clock 推进到 TTL 后，仅手动触发 fake timer，验证闲置 session 自动关闭 page/context/Playwright/profile lock。
- fake timer 验证 session close、manager recovery/close 的取消行为。
- fake timer 启动失败验证 open-session 异常不遗留 timer、context、Playwright 或 profile lock。
- fake page creation failure 验证 manager recovery 收敛 context、Playwright 与 profile lock。

## 验证命令

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser_manager.py tests/test_paper_browser.py` | 31 passed，退出码 0 |
| `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser_manager.py` | All checks passed，退出码 0 |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser_manager.py` | 通过，退出码 0 |
| `git diff --check` | 通过，退出码 0 |

未提交 commit；真实浏览器、网络、Qdrant 与真实等待均未使用。
