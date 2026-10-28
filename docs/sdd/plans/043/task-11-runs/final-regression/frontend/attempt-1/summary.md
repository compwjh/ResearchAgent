# Task11 最终前端回归摘要

- 候选：`1f03e9e545027aaf1852634803a55d22dbea383f`；地图 JS v37、CSS v23、app.js v66。
- 最终结论：**BLOCK**。Chromium 提权完整套件 exit 1：384 passed、1 failed、0 skipped，115.12s。
- 唯一失败：`tests/frontend/test_frontend_literature_map_contract.py:98` 断言 MODULE 不得包含 `semantic_scholar`；候选在 `frontend/literature-maps.js` 的 provider 名称映射中包含该键（约第 2843 行）。这是当前实现与静态合同的冲突；本角色未改代码、未删除/跳过断言。
- Chromium 权限：使用 `require_escalated`，0 skipped；本次未将权限错误折算为 skip。
- 补充验证：Node 合同 exit 0（33/33，0 skipped）；`node --check frontend/app.js` 与 `node --check frontend/literature-maps.js` 均 exit 0。
- DOM/CSS：4 个新增 expansion class 均在地图 JS 中渲染，并由限定在 `#literature-maps-view` 的 CSS 定义。
- 资源版本：index 引用 map JS v37、map CSS v23；app.js v66。
- XSS 静态检查：地图 JS 未命中 `innerHTML`、`insertAdjacentHTML`、`outerHTML`。
- 源码 SHA256 在回归前后保持一致，详见 `stamp/source-before.txt` 和 `stamp/source-after.txt`。失败断言文件哈希见 `stamp/failed-test-source.txt`。
- 运行限定：测试使用本地 mock fixtures 与 headless Chromium；未运行后端 pytest/collection、真实 API、数据库、S2/model、部署或用户浏览器。
- 原始 pytest stdout/stderr：`/private/tmp/spec043-task11-final-frontend-20261028/pytest-stdout.log`、`/private/tmp/spec043-task11-final-frontend-20261028/pytest-stderr.log`；其他原始命令日志同目录。
