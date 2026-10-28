# Spec043 Task11 最终前端候选回归报告

日期：2026-10-28（Asia/Shanghai）  
角色：frontend-tester（本次临时档位：Luna xhigh）  
Attempt 1 候选：`1f03e9e545027aaf1852634803a55d22dbea383f`（地图 JS v37 / CSS v23，app.js v66）  
结果：**PASS（Attempt 2）**。最终候选完整 `tests/frontend` 为 385 passed、0 failed、0 skipped；Attempt 1 的 384/1 历史失败记录保留如下。

## 当前最终候选（Attempt 2）

- 候选：`d2bd4ba7b02aaa803ea36e2aebd279480aa88ed7`；该提交只修订静态合同测试与文档，生产前端哈希与 `1f03e9e5` 完全一致（地图 JS v37 / CSS v23，app.js v66）。
- 命令：`TMPDIR=/private/tmp/spec043-task11-final-frontend-20261028/attempt-2 PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs -p no:cacheprovider tests/frontend`，require_escalated。
- 结果：exit 0，385 passed、0 failed、0 skipped，114.59s（UTC 14:41:33–14:43:28）。Chromium 未发生权限 skip。
- 原始日志：`/private/tmp/spec043-task11-final-frontend-20261028/attempt-2/pytest-stdout.log` 与 `pytest-stderr.log`。
- Node 合同 33/33 与 app.js/literature-maps.js 语法检查复用 Attempt 1 的 exit 0 证据；生产前端哈希相同，没有重跑。

## Attempt 1（合同修订前的历史失败）运行命令与结果

| 命令 | 权限 | 退出码 | 结果 |
|---|---|---:|---|
| `TMPDIR=/private/tmp/spec043-task11-final-frontend-20261028 PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -rs -p no:cacheprovider tests/frontend` | require_escalated | 1 | 384 passed、1 failed、0 skipped；115.12s |
| `node --test frontend/contract-tests/*.test.mjs` | 普通 | 0 | 33 passed、0 failed、0 skipped；127.77ms |
| `node --check frontend/app.js` | 普通 | 0 | PASS |
| `node --check frontend/literature-maps.js` | 普通 | 0 | PASS |

Chromium 全套使用提权权限执行，未发生权限相关跳过。测试仅使用本地 fixtures/headless Chromium；未运行后端 pytest/collection、真实 API、数据库、S2/model、部署或用户浏览器。

## Attempt 1 失败定位（合同修订前）

`tests/frontend/test_frontend_literature_map_contract.py:98` 明确断言前端模块不得包含 `semantic_scholar`。候选 `frontend/literature-maps.js` 的 `expansionCandidateSourceLabel` 在约第 2843 行新增 `providerLabels` 映射，其中包含 `semantic_scholar`，因此触发唯一失败。该项是当前候选代码与现存静态合同的冲突，非资源版本错误、Chromium 权限问题或 skip。

本回归角色没有修改业务代码或测试，也未删除/跳过失败断言。后续若修改合同或实现，需在独立 review 后对最终候选重跑完整前端套件；本报告只记录本次候选。

## 前端静态合同（生产前端未变）

- **语法：PASS** — app.js 与 literature-maps.js 均通过 `node --check`。
- **DOM/CSS：PASS** — 新增的 `literature-map-expansion-scope-note`、`literature-map-expansion-sort-controls`、`literature-map-expansion-candidate-scope`、`literature-map-expansion-scope-tag` 均由地图 JS 渲染，并在限定于 `#literature-maps-view` 的 CSS 中定义。
- **资源版本：PASS** — `frontend/index.html` 引用 `/assets/literature-maps.js?v=37` 和 `/assets/literature-maps.css?v=23`；app.js 为 v66。
- **XSS：PASS** — `frontend/literature-maps.js` 未命中 `innerHTML`、`insertAdjacentHTML` 或 `outerHTML`。
- **Attempt 1 测试合同：FAIL（历史）** — 上述 `semantic_scholar` 禁止断言与候选 provider 显示映射冲突；Attempt 2 修订后完整套件通过。

## Attempt 1 候选指纹

| 文件 | SHA256 |
|---|---|
| `frontend/app.js` | `df12d89aa0b5b59319214a6fa4752f4d86aacddf80faf11ddbff6e759280e29b` |
| `frontend/literature-maps.js` | `a69fb6fa68dd8831cdb34bfb34119563b9823984bcb3169ddbc5a58f9507042d` |
| `frontend/literature-maps.css` | `376f0ab30922ead3d42bd1de843a89453d66aa356bb9e0313452c8904e842561` |
| `frontend/index.html` | `e63a033ebf6dbaa6609ebddeecf1d3e6d6fd0bdf2e8ba733c343ddcdac9ab7ef` |
| `tests/frontend/fixtures/literature_map_component.html` | `92247e378e9150da5b4626674fd414370b837eb0e89706cbf87540528327be2a` |
| Failed assertion source SHA256 | `e5394e2318991e32f5cea0f554902df9b02a9ca7caaef0d1cc8df301829bf4ac` |

回归前后前端源码指纹一致；本角色未修改源码。

## Attempt 1 原始证据

完整 stdout/stderr 与退出码均保存在 `/private/tmp/spec043-task11-final-frontend-20261028/`。仓库内的精简命令、候选 stamp 与脱敏摘要位于 `docs/sdd/plans/043/task-11-runs/final-regression/frontend/`。前端回归进展日志：`.codebuddy/agent-logs/spec-043/task-11/frontend-tester/20261028-222816.md`。

## Attempt 1 VERIFICATION REPORT（历史）

Syntax: PASS  
Contract: FAIL（1 项静态断言与候选 provider 显示映射冲突）  
Tests: **BLOCK**（384/385 passed，1 failed，0 skipped）  
DOM/CSS: PASS  
Version: PASS（JS37 / CSS23 / app.js v66）  
XSS: PASS  
Overall: **BLOCK**，需对冲突作独立裁决并对最终候选重跑完整 `tests/frontend`。


## Attempt 2 VERIFICATION REPORT（当前最终候选）

Build: N/A（纯前端回归，无构建步骤）  
Types: N/A（原生 JS）  
Syntax: PASS（复用相同前端源码哈希下 Attempt 1 的 app.js 与 literature-maps.js `node --check` exit 0）  
Contract: PASS（更新后的 request-boundary 合同；完整 pytest exit 0）  
Tests: **PASS**（385/385 passed，0 failed，0 skipped；Chromium 提权执行）  
DOM/CSS: PASS（4 个新增 expansion class 具有渲染与 scoped CSS）  
Version: PASS（JS37 / CSS23 / app.js v66；与 Attempt 1 相同）  
XSS: PASS（地图 JS 未发现不安全 HTML 插入 API）  
Node contract suite: PASS（33/33 passed，复用相同源码哈希下 Attempt 1 的 exit 0 证据）  
Overall: **PASS**。当前最终候选为 `d2bd4ba7b02aaa803ea36e2aebd279480aa88ed7`。

Attempt 2 命令、stamp 与摘要位于 `docs/sdd/plans/043/task-11-runs/final-regression/frontend/attempt-2/`；原始 stdout/stderr 位于 `/private/tmp/spec043-task11-final-frontend-20261028/attempt-2/`。Attempt 1 原始失败日志及摘要继续保留在旧路径。

## Attempt 3 — 新候选（地图 JS v37 / CSS v24）

- 候选：`074845b21de20230e87738d6778119d59f411bb8`（`new candidate: true`）；相对 Attempt 2 更新 CSS 与 `index.html` CSS 版本，回归前后生产前端指纹一致。
- 完整命令：见 `task-11-runs/final-regression/frontend/attempt-3/commands/pytest-frontend.txt`。使用隔离 TMPDIR、禁用 pyc / dotenv / Langfuse / pytest cache；Chromium 使用 `require_escalated`。
- 结果：**FAIL**，exit 1；386 passed、1 failed、0 skipped，147.36s。Playwright Chromium 确实运行；失败不是浏览器权限 skip。
- 唯一失败：`test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures` 在关闭列表抽屉后真实触摸地图节点，等待 `.literature-map-detail-panel.is-open` 30 秒超时（测试第 318 行）。隔离复跑同一用例仍以相同超时失败（exit 1，31.97s）。
- Node：`app.js` 与 `literature-maps.js` `node --check` 均 exit 0；Node 合同 33 passed、0 failed、0 skipped。
- DOM/CSS、版本、XSS：PASS。CSS 变更涉及的 `.literature-map-canvas` 和 `.literature-map-preview-panel` 均有 HTML/JS 与 CSS 对应；版本为地图 JS v37 / CSS v24 / app.js v66；未命中不安全 HTML 插入 API。
- Attempt 1/2 历史与产物保留。Attempt 3 命令、source before/after、CSS class 对照、run stamp 与摘要位于 `task-11-runs/final-regression/frontend/attempt-3/`；原始完整及隔离测试输出位于 `/private/tmp/spec043-task11-final-frontend-20261029/attempt-3/`。
- **VERIFICATION REPORT：Overall BLOCKED**，可复现的真实触摸打开详情失败；需修复后对新候选重跑全量前端套件。

## Attempt 4 — 新候选（地图 JS v37 / CSS v25）

- 候选：`7364a26b9ea97b902c91d12a5251236a0771a70a`（`new candidate: true`）；CSS25 移动端画布修复版本，回归前后生产前端指纹一致。
- 完整命令：见 `task-11-runs/final-regression/frontend/attempt-4/commands/pytest-frontend.txt`。隔离 TMPDIR，禁用 pyc / dotenv / Langfuse / pytest cache；Chromium 使用 `require_escalated`。
- 结果：**PASS**，exit 0；387 passed、0 failed、0 skipped，117.99s。Playwright Chromium 实际执行，浏览器用例未权限跳过。
- Node：`app.js` 与 `literature-maps.js` `node --check` 均 exit 0；Node 合同 33 passed、0 failed、0 skipped。
- DOM/CSS、版本、XSS：PASS。画布/预览/详情相关选择器有 HTML/JS 与 CSS 对应；版本为地图 JS v37 / CSS v25 / app.js v66；无不安全 HTML 插入 API 命中。
- Attempt 3 CSS24 真实触摸失败及其隔离重现完整保留。Attempt 4 命令、source before/after、CSS class 对照、run stamp 与摘要位于 `task-11-runs/final-regression/frontend/attempt-4/`；原始 stdout/stderr 位于 `/private/tmp/spec043-task11-final-frontend-20261029/attempt-4/`。
- **VERIFICATION REPORT：Overall PASS**。候选 `7364a26b9ea97b902c91d12a5251236a0771a70a` 的完整前端套件通过，Chromium 0 skip。
