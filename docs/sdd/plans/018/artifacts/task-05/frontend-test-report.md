# Spec018 Task05 前端验收报告（历史首轮，已被最终报告取代）

> 本文件保留首轮失败证据。最终结果见 [`frontend-test-final-report.md`](./frontend-test-final-report.md)，最终结论为 `PASS`。

## 结论

**FAIL（Task05 功能门未通过）**。

Node 前端 renderer/runtime/PDF/interaction 契约与语法检查全部通过，PDF.js
vendored 文件 hash、DOM id/ARIA、响应式 CSS 和 GET-only 静态边界也通过；但
Task05 的两个硬门未满足：

1. `dom-contract.schema.json` 仍固定 `styles` 资源 query 为 `?v=16`，而当前
   `frontend/index.html` 的 `styles.css`、`kb-inspection.js`、`app.js` 均为
   `?v=18`，因此 DOM 契约与实际资源版本不一致。
2. `frontend-fixture-index.json` 的网络证据仍为
   `node-fake-fetch-contract`，不是 Task05 要求的真实浏览器 hostile
   PDF/Markdown 证据；其中没有真实浏览器的零远程请求观测。

## 验证范围与结果

| 检查 | 命令/证据 | 结果 |
|---|---|---|
| Markdown renderer | `node tests/test_frontend_kb_inspection_renderer.js` | PASS（exit 0） |
| Runtime/API 状态与取消 | `node tests/test_frontend_kb_inspection_runtime.js` | PASS（exit 0） |
| PDF.js display-only | `node tests/test_frontend_kb_inspection_pdf.js` | PASS（exit 0） |
| 双向交互 | `node tests/test_frontend_kb_inspection_interaction.js` | PASS（exit 0） |
| JavaScript 语法 | `node --check frontend/kb-inspection.js`, `frontend/app.js` 及交互测试 | PASS（exit 0） |
| diff 空白 | `git diff --check` | PASS（exit 0） |
| API/DOM/vendor JSON 结构 | Node 静态检查 | PASS |
| PDF.js vendor hash | manifest 与四个文件 SHA-256 重算 | PASS |
| DOM id/ARIA/CSS | index、styles 与 `dom-contract.schema.json` | FAIL（资源 query 版本不一致） |
| 同源/远程资源/HTTP 方法 | HTML/JS 静态检查 | PASS（未发现业务 CDN、iframe、远程 loader 或 POST/PUT/DELETE） |

## 真实浏览器验收

已使用 Codex In-app Browser 加载 `http://127.0.0.1:8000/`，并完成：

- 进入“知识库”导航；
- 进入“切片检查”二级 Tab；
- 观察 `kb-tabs`、`kb-panel-inspection`、文档选择器、v1/v2 单选、双栏
  `kb-inspection-layout`、source/chunk pane 的真实 DOM/ARIA；
- 观察到浏览器错误态 `HTTP_404：请求暂时不可用`，console error/warn 为空。

当前运行时的文档列表请求返回 HTTP 404，选择器没有可用文档。因此无法在
真实页面上驱动 hostile Markdown/PDF、点击/Enter/Space 双向联动、PDF 懒渲染
和窄屏切换；没有把这些未执行项伪造为通过。当前 fixture 也没有提供真实浏览器
网络请求计数，故 Task05 的“除同源 source/worker/API 外远程请求数为 0”硬门
仍为未满足。

本地 Node 依赖中未安装 `playwright`、`puppeteer` 或 `@playwright/test`；可用的
In-app Browser 只完成了真实页面加载与 DOM/错误态观察，不能替代 hostile fixture
网络拦截证据。

## Task05 功能门与 Task06 生产债务区分

- **Task05 功能门：FAIL**。需先修正 DOM 契约资源版本，并补齐真实浏览器
  hostile fixture 的网络/交互证据；随后重新执行 frontend-tester。
- **Task06 生产债务：未评估/保持阻塞**。本轮没有修改或放行生产切换、旧库
  回填、真实索引切换等 Task06 范围内容；Task05 未通过时不得启动 Task06。

## 不执行项

- 未运行后端 pytest。
- 未修改业务文件或前端实现。
- 未把本地服务 HTTP 404 当成前端功能通过。
