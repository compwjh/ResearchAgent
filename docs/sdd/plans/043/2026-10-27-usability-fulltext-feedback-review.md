# Spec043 Task10 全文反馈前端独立评审

日期：2026-10-27 14:27（Asia/Shanghai）  
基线：`62c3bb50`  
评审范围：仅本阶段 `frontend/index.html`、`frontend/literature-maps.js`、`frontend/literature-maps.css` 的工作树差异。

## 结论

**Approve（P0/P1 = 0；有 1 项 P2 建议修复）**。未发现阻断项。主要用户旅程和状态安全门禁通过 Chromium 验证；下述 P2 是状态摘要在不一致 API 响应下会与全文卡片冲突。

## 评审发现

### [P2] “可用依据”摘要没有用全文就绪字段过滤全文项

文件：[frontend/literature-maps.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/literature-maps.js:4631)

`renderAnalysisPanel()` 将 `source_status.available_evidence_levels` 中的 `full` 直接显示为“全文索引片段依据”；全文状态卡和分析提交门禁则正确只在 `source_status.fulltext_ready === true` 时认定全文可用。若服务端两个字段不一致，顶部摘要会声称全文依据可用，卡片却显示原因未确定或全文不可用。应在摘要显示中同样以 `fulltext_ready === true` 决定是否列出全文。

当前 `analysisAvailable('full')` 的 POST 门禁仍是严格布尔判断，因此此问题不会使未就绪状态发出分析请求。

## 评审清单

| 检查项 | 结论 | 依据 |
|---|---|---|
| 全文门禁与状态来源 | PASS | `analysisAvailable('full')` 和状态卡均检查 `fulltext_ready === true`；`indexed`/`document_id` 只表达已入库后仍未确认全文，不会代替就绪状态。 |
| 未就绪恢复与重复动作 | PASS | 未入库复用详情既有入库按钮；登录走既有论文检索/登录处理入口；等待只刷新状态；失败只提供现有人工处理入口。未就绪点击不会提交分析请求。 |
| 进度、完成、历史与节点隔离 | PASS | 原有 POST/poll/Markdown/历史路径保留；异步结果包含地图、节点、请求代次校验，迟到的前节点状态不覆盖当前卡片。 |
| DOM 契约 | PASS | 新增反馈卡及反馈元素 class 在 CSS 中均有定义；CSS 规则也都有 JS 对应节点。 |
| 配色与布局回归 | PASS | 本阶段 CSS 仅新增反馈卡样式，没有改动既有布局/配色规则。 |

## 四项前端必守

1. **DOM 契约 — PASS**：JS 生成的 `literature-map-fulltext-feedback`、`literature-map-fulltext-title`、`literature-map-fulltext-badge`、`literature-map-fulltext-message` 和 `literature-map-analysis-action-feedback` 均有对应 CSS（JS：`rg -n "literature-map-(fulltext-feedback|fulltext-title|fulltext-badge|fulltext-message|analysis-action-feedback)" frontend/literature-maps.js`；CSS：同一查询目标 `frontend/literature-maps.css`，命中第 124–134 行）。
2. **资源版本 — PASS**：[frontend/index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:9) 引用 `literature-maps.css?v=19`，第 798 行引用 `literature-maps.js?v=29`。
3. **XSS — PASS**：`createElement()` 用 `textContent` 写入动态文案（`literature-maps.js:165–169`）；分析 Markdown 仍经过 `window.renderMarkdown`，其实现调用 DOMPurify。`rg -n "innerHTML|insertAdjacentHTML|outerHTML" frontend/literature-maps.js` 无命中。
4. **CSS 作用域 — PASS**：新增规则均限制在 `#literature-maps-view` 下（`literature-maps.css:124–134`）；全文卡片和操作反馈的 `[hidden]` 显式隐藏规则均保留。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/literature-maps.js` | 0 | 语法检查通过 |
| `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_fulltext_feedback.py`（按授权启动 Chromium） | 0 | 11 passed，0 failed，0 skipped |

首次普通权限启动 Chromium 时 11 个用例因 macOS Mach rendezvous 权限拒绝而跳过；记录原因后申请了仅运行上述前端 Chromium 用例的精准权限，重跑全部 11 项通过。未运行后端测试，未改业务代码、未部署、未执行 Git 操作。

## 评审统计

| Severity | Count | Status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM / P2 | 1 | follow-up |
| LOW | 0 | note |

Verdict: **Approve** — 无 P0/P1；建议修正 1 项 P2 后进入后续验收。

日志：[20261027-141852.md](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/.codebuddy/agent-logs/spec-043/task-10/frontend-reviewer/20261027-141852.md)

## P2 独立关闭复核（2026-10-27）

**状态：已关闭。** 对应修复将“可用依据”列表改为从 `abstract_available === true` 与 `fulltext_ready === true` 派生；全文可用性及 POST 门禁仍仅认 `fulltext_ready === true`。因此 `available_evidence_levels` 与权威布尔字段即使矛盾，也不会让页面误报全文就绪或发出未就绪分析请求。

复核证据：

- Chromium 精确用例 `test_available_evidence_summary_follows_authoritative_source_fields`：**1 passed，退出码 0**。同一用例验证列表误含 `full` 且 `fulltext_ready` 为 false 时只显示摘要，点击全文操作不发 POST；反向列表缺少 `full` 而 `fulltext_ready` 为 true 时按权威字段显示全文。
- 版本契约 `test_navigation_view_and_version_contract_are_wired`：**1 passed，退出码 0**；`node --check frontend/literature-maps.js`：**退出码 0**。
- `frontend/index.html` 与 Chromium fixture 均同步引用 `literature-maps.js?v=30`、`literature-maps.css?v=19`。

本次仅复核 P2、未就绪 POST 门禁和资源版本；未重复原有 92 项回归，未改代码、未执行 Git 或部署操作。此前发现现已由上述独立证据关闭，Task10 其他验收门禁仍由主会话继续。

## NULL 导入状态修复独立窄复审（2026-10-27）

**结论：Approve；本次指定范围无新发现。** 只复核未提交的 `frontend/literature-maps.js`、`frontend/index.html` 与相关状态/版本测试。

- 详情和全文卡对 `download_status` 为 null、空串或缺失且无 `document_id` 的已返回节点显示“未入库”，提供既有“获取并加入知识库”按钮。按钮只在用户点击时转发到既有导入 handler；未就绪全文按钮不会提交分析 POST。
- `analysisSourceStatus` 尚未返回时，当前代码保留“正在读取全文来源状态”；不会因节点状态尚缺而抢先标成未入库。一次性 Chromium 延迟 1.2 秒状态 GET 的检查验证了响应前显示读取中、响应后才显示未入库，且前后都没有分析 POST。
- 只有 `document_id` 而无导入状态时，详情显示已入库，全文卡仍显示全文依据未确认并提供知识库检查；ready 和全文 POST 仍只由 `fulltext_ready === true` 决定。
- 显式未知非空状态仍映射为“状态待确认”，没有改成未入库；未知状态用例通过。
- 入口与 Chromium fixture 均同步为 `literature-maps.js?v=31`、`literature-maps.css?v=19`。

精确验证证据：

| 命令 | 结果 |
|---|---|
| `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_fulltext_feedback.py::test_missing_import_status_without_document_shows_manual_import_action tests/frontend/test_frontend_map_fulltext_feedback.py::test_null_import_status_with_document_is_not_misclassified_as_missing_or_ready tests/frontend/test_frontend_map_fulltext_feedback.py::test_unknown_import_status_is_not_exposed_as_machine_code`（按授权启动 Chromium） | 5 passed，0 failed，0 skipped，退出码 0；涵盖 null/空/缺失三种状态、仅有文档 ID、显式未知状态，以及未点击前无导入/分析 POST、手动 CTA 只触发导入 |
| `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_map_groups_exports.py::test_export_asset_versions_are_synchronised` | 2 passed，退出码 0 |
| `node --check frontend/literature-maps.js` | 退出码 0 |

另以一次性内存 Chromium 检查延迟 `GET /nodes/node-a/analyses` 1.2 秒，观察加载态和响应后的状态转移，断言全程 `window.__analysisBodies` 为空；结果 **PASS**。

本次未运行全套测试、未改业务代码、未执行 Git 或部署操作，也未覆盖 Task11。该关闭结论仅适用于 NULL 导入状态修复及其资源版本合同。
