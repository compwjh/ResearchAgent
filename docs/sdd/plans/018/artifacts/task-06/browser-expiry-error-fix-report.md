# Task06 Browser Expiry Error Fix Report

## 结论

`PASS（browser session 错误码透传隔离门）`。

`BROWSER_SESSION_EXPIRED` 与 `BROWSER_SESSION_REQUIRED` 现在沿已有
application boundary 从 browser downloader 透传到批量服务和 route；不会被
`import_candidate` 或 batch service 的通用异常兜底改写为 `KB_IMPORT_FAILED` /
`IMPORT_FAILED`。batch item 在该失败路径保持 failed，不执行 validating/indexing/
completed 成功 transition；resume route 返回稳定 HTTP 424，并且不泄露 browser
异常文本。

## 改动范围

- `backend/app/paper_discovery/application/paper_import.py`
  - 从受控 application entry 使用 browser session 错误码与异常类型。
  - 将两条 session code 纳入固定安全错误码/消息表。
  - `import_candidate` 单独保留两条 session code，转换为 `PaperImportError`；其他
    browser manager 错误仍沿原有 KB 失败兜底处理。
- `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - 依赖稳定 browser code 导出；借助统一安全错误码表持久化 session failure，避免
    `_mark_failed` 将其收敛为 `IMPORT_FAILED`。
- `backend/app/api/routes_paper.py`
  - 单篇 import、browser error map 均纳入 `BROWSER_SESSION_EXPIRED` /
    `BROWSER_SESSION_REQUIRED`（424）。
  - resume 在 downloader 竞态失败后读取 item 的稳定 error code，返回 424，而不是
    返回误导性的成功形状 batch payload。
- 隔离测试：`tests/test_paper_import.py`、`tests/test_paper_import_batch_service.py`、
  `tests/test_paper_import_batch_api.py`。

未修改 browser manager；未启动真实浏览器/网站/服务，未连接 Qdrant，未执行网络请求。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | 0 | 31 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_browser.py tests/test_paper_browser_manager.py tests/test_paper_import.py tests/test_paper_import_batch.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_integration.py` | 0 | 68 passed，5 个既有 DeprecationWarning |
| `.venv/bin/python -m ruff check backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/api/routes_paper.py tests/test_paper_import.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/api/routes_paper.py tests/test_paper_import.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 安全/状态断言

- 测试注入包含 URL、Cookie、secret 的 browser 异常文本，application exception、batch
  item message 与 HTTP body 均不包含这些内容。
- downloader 在 import boundary 抛出 session code 时，KB `import_paper` spy 调用次数为
  0。
- batch browser failure item 的最终状态为 `failed`，error code 保持原 session code，
  调用次数为 1，且不为 `completed`。
- route race 测试验证初始 login 失败加一次 resume 尝试，不发生第二次恢复导入；响应
  code 为对应 session code、HTTP 424，item 仍为 failed。

## 交接说明

本轮不提交 commit；由主 Agent 在同一工作树汇总其它 Task06 改动后统一评审、验收与提交。
