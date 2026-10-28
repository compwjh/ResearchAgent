# Task11 最终前端回归摘要

## 当前最终候选：Attempt 2

- 候选：`d2bd4ba7b02aaa803ea36e2aebd279480aa88ed7`；生产前端哈希与 Attempt 1 相同，地图 JS v37 / CSS v23 / app.js v66。
- 完整 `tests/frontend`：**PASS**，exit 0，385 passed、0 failed、0 skipped，114.59s。Chromium 使用 `require_escalated`，未发生权限跳过。
- Node 合同与 app.js/literature-maps.js 语法检查复用 Attempt 1 中同一生产源码哈希的通过证据：33/33 passed，两个 `node --check` exit 0。
- Attempt 2 原始日志：`/private/tmp/spec043-task11-final-frontend-20261028/attempt-2/pytest-stdout.log`、`pytest-stderr.log`。
- 命令、stamp、摘要见本目录 `attempt-2/`。

## Attempt 1 历史失败（保留）

- 候选：`1f03e9e545027aaf1852634803a55d22dbea383f`。
- 完整套件：exit 1，384 passed、1 failed、0 skipped；失败为 `tests/frontend/test_frontend_literature_map_contract.py:98` 对 `semantic_scholar` 字符串的旧负向断言。
- 该 attempt 的命令、stamp 和摘要仍保留在本目录根部；完整原始日志仍在 `/private/tmp/spec043-task11-final-frontend-20261028/`，另存摘要于 `attempt-1/summary.md`。
- Attempt 1 失败没有被覆盖或从历史报告删除。最终结论以 Attempt 2 为准。
