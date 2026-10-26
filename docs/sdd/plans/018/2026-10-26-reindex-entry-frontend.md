# Spec 018 重建入口前端交接报告

> 当前收口状态：canonical ID 衔接与 partial 展示窄修已完成；历史“等待验收”文字仅保留为当时交接事实，最终签字见 [`../../reviews/018-acceptance-review.md`](../../reviews/018-acceptance-review.md)。

状态：前端实现完成，等待独立前端评审/回归及主会话真实 API 验收；本报告不改变 Spec 状态台账。

## 范围与边界

- 修复知识库列表真实 DTO 的 `document_id` → 单文档 canonical reindex 入口衔接；`paper_id` 仅作旧 DTO 的安全兼容回退。
- 重建始终调用现有 `POST /api/kb/documents/{document_id}/reindex`，请求体保持 `{ "chunker": "all" }`。
- 缺少稳定 ID 时零 POST，并显示“未提交请求”；同一按钮的并发点击只允许一个 POST。
- 解析现有结构化错误的 `error_code`/`code` 与 `message`/`detail`；409 `INDEX_ALREADY_RUNNING`（或 running 状态）显示可行动的忙碌提示，不显示成功提示；503 等错误保留服务端可读 message。
- 未改后端、上传、删除、全库重建、模型调用、真实生产 POST、部署或网络下载。

## 代码与测试改动

- `frontend/app.js:5931-5995`：新增 ID 规范化、结构化重建错误解析、busy/失败文案、in-flight 防重复及 canonical endpoint；`renderKbPapers` 写入 `data-document-id`。
- `frontend/index.html:786`：live app bundle 版本 `?v=60` → `?v=61`；styles 继续使用 `?v=61`。
- `frontend/contract-tests/kb-reindex-failure-recovery.test.mjs:289-407`：基于真实 app.js 与生产 KB 目标 ID 的合同测试，覆盖 canonical-only DTO、旧 DTO 回退、生产 markup、202/all、缺 ID 零 POST、409/503 错误可见性、并发双击及既有失败错误标签回归。

## 实际验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | JavaScript 语法通过 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 14 tests passed，0 failed |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 22 tests passed，0 failed |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py` | 0 | 23 frontend static contracts passed |
| 隔离 Playwright Chromium smoke（生产 `index.html` + API route interception） | 0 | canonical DTO 渲染后双击仅 1 次 POST，URL 与 body 正确 |
| `python scripts/check_test_naming.py` | 0 | test naming check passed |
| `python scripts/check_test_layout.py` | 0 | test layout ok |
| `.venv/bin/python -m pytest --collect-only -q` | 0 | 3407 tests collected，0 collecting error |
| `git diff --check` | 0 | 无空白/冲突标记错误 |

系统 `pytest --collect-only -q` 曾因系统解释器缺少 `playwright` 以退出码 2 失败；按项目实际环境改用 `.venv/bin/python -m pytest --collect-only -q` 后收集成功。未运行后端 pytest。

## 读回与角色自查

- 读回确认 `frontend/app.js` 请求路径为 `/api/kb/documents/${encodeURIComponent(documentId)}/reindex`，请求体仅为 `JSON.stringify({ chunker: 'all' })`；未出现生产重建旧路径调用。
- 读回确认 `frontend/index.html` live script 为 `/assets/app.js?v=61`，styles 为 `/assets/styles.css?v=61`。
- DOM 契约：本次没有新增 CSS class；新增的 `data-document-id` 不依赖样式，既有 `.kb-item-rebuild` 继续复用。
- XSS：本次新增状态/错误均使用 `textContent`，没有新增 `innerHTML`；服务端 message 不作为 HTML 解析。
- 版本号：`app.js` 改动后已同步升 live `?v`；styles 未改。
- 角色边界：只改前端代码、前端合同测试与本交接报告；保留现有用户未跟踪的 `docs/sdd/plans/pr-2-gate-baseline.md`，不 push、不合并、不部署。

## 下游交接

前端评审应只检查上述三个前端文件的 DOM/版本/XSS 及请求合同；前端回归应复跑 Node 合同测试、`node --check`、命名/布局检查。主会话仍需在独立评审后按计划对指定截图文档执行一次真实 canonical API 重建，并落盘 202 响应、任务 ID、v1/v2 终态和产物路径；本报告中的 mock/合同测试不能替代该真实验收。

## P1 复审追加（2026-10-26）

独立复审发现并已闭合两项 P1：成功响应现在严格要求 HTTP 202 和非空字符串 `task_id`；防重复锁改为模块级 `Set` 按归一后的文档 ID 持有，列表重绘期间不会因替代按钮再次提交，失败后在 refresh 完成并进入 `finally` 时释放。实现与测试仍限于前端，没有改后端公开 API、上传、删除、用户草稿或生产调用。

当前读回位置：`frontend/app.js:5931-6015`（ID/错误解析、202/task ID 门、文档锁、失败释放）与 `frontend/app.js:6049-6059`（canonical `data-document-id`）；`frontend/index.html:786` 为 `app.js?v=61`，styles 仍为 `v=61`。新增合同位于 `frontend/contract-tests/kb-reindex-failure-recovery.test.mjs:322-515`，测试文件名按被测能力命名。

当前实际结果（均退出 0）：

- `node --check frontend/app.js`：通过；
- `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs`：18/18 通过；
- 与 `context-meter-and-kb-count.test.mjs` 合跑：26/26 通过；
- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py`：23/23 通过；
- `python scripts/check_test_naming.py`、`python scripts/check_test_layout.py`、`git diff --check`：通过；
- `.venv/bin/python -m pytest --collect-only -q`：3407 项收集成功。

独立复审详见 `docs/sdd/plans/018/2026-10-26-reindex-entry-review.md`；真实 API 202、非空任务 ID、v1/v2 终态和产物路径仍由 root 在最终验收执行，本报告不替代真实验收。

## 2026-10-26 `indexed_partial` 可见反馈增量

本次在既有 canonical reindex 改动上追加窄范围的真实 partial DTO 展示契约：目标文档 `d4dfd2a620384ad5bece27320661f8f0` 顶层保持 `status=indexed`，v1 为 `indexed`/107 片段，v2 为 `indexed_partial`/297 片段，`chunkers.v2.error` 为 `SOURCE_RANGE_UNRESOLVED`（合法的 20 个未映射来源区间）。

- `frontend/app.js`：从已有 `paper.status` 与 `chunkers.*.status/error` 推导 partial；保留顶层“已索引” metadata、v1/v2 版本徽章和片段数；卡片增加 `status-indexed_partial`，显示“部分切片无法精确定位原文，已保留可用索引；可进入切片检查”。原始原因仅保留在 `title`，不伪造 mapped/unmapped 数量、不改重建策略、不新增 API/POST。
- `frontend/styles.css`：为 scoped partial 卡片、`indexed_partial` 徽章和 `.kb-item-warning` 使用 amber 警示样式；未修改 literature map 资源。
- `frontend/index.html`：live KB 资源同步为 `app.js?v=62`、`styles.css?v=62`；地图资源保持 `literature-maps.js?v=21`、`literature-maps.css?v=13`。
- `frontend/contract-tests/kb-reindex-failure-recovery.test.mjs`：新增真实 DTO 合同，锁定 v1 ready/v2 partial+reason、顶层 indexed metadata、非 failed/非全量成功文案、原始码不泄漏和渲染零额外 reindex POST。
- 受资源版本影响的精确静态合同/fixture 已同步更新；未改 backend、模型、真实 API、部署或 Git 状态。

### 本轮实际测试与读回

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | JavaScript 语法通过 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 19/19 通过，含新增 `indexed_partial` DTO 合同 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs frontend/contract-tests/context-meter-and-kb-count.test.mjs` | 0 | 27/27 通过 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py tests/frontend/test_frontend_composer_layout.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_mobile_contract.py` | 0 | 46/46 通过 |
| `python scripts/check_test_naming.py` | 0 | test naming check passed |
| `python scripts/check_test_layout.py` | 0 | test layout ok |
| `git diff --check -- frontend/app.js frontend/styles.css frontend/index.html frontend/contract-tests/kb-reindex-failure-recovery.test.mjs tests/frontend` | 0 | 无空白/冲突标记错误 |

读回确认：`renderKbPapers` 未新增 fetch；partial DTO 渲染时仅有既有首屏 GET，reindex POST 数为 0；`item.title` 保留 `SOURCE_RANGE_UNRESOLVED`，可见文案不含原始码；`frontend/index.html` 的 map JS/CSS 版本仍为 21/13。真实生产 API 重建与 v1/v2 终态验收仍由 root 按原交接计划执行。
