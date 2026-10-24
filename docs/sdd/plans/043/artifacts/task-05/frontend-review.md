# Spec043 Task05 前端独立评审

## 结论

**BLOCK（P0：0；P1：3）**。精准前端测试全部通过，但有两项项目强制前端门禁失败，且分析轮询达到上限后没有可恢复状态。未把 fixture、静态检查或前端报告当作真实后端/provider/API E2E 证据；本评审不覆盖 `backend/**`。

## 评审范围与证据

- 交接：`docs/sdd/plans/043/task-05-analysis-conversations.md`、`artifacts/task-05/interface-contract.md`、`artifacts/task-05/frontend-report.md`。
- 实际前端：`frontend/literature-maps.js`、`frontend/literature-maps.css`、`frontend/index.html`、`frontend/app.js`；相关 fixture 与契约测试。
- `node --check frontend/literature-maps.js && node --check frontend/app.js`：退出码 0。
- `git diff --check -- frontend tests/frontend`：退出码 0。
- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py`：退出码 0，16 passed。
- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py tests/frontend/test_frontend_conversation_contract.py`：退出码 0，23 passed。

## P1 问题

### [P1 / CRITICAL] 修改 `app.js` 后没有递增真实资源版本

- 文件：`frontend/app.js:6252-6254` 新增 `window.openConversationFromWorkspace = openConversationFromWorkspace`；`frontend/index.html:786` 仍为 `src="/assets/app.js?v=58"`。
- 最小复现：`git diff -- frontend/app.js` 可见该文件有本Task改动；读取 live script tag 仍得到 `app.js?v=58`。浏览器/CDN 命中旧缓存时不会加载本Task新增的地图→现有会话导航桥，行为取决于旧脚本是否存在其它兼容路径。
- 违反：项目 `?v=N` 门禁要求任何 `app.js` 改动同步递增版本；这是缓存一致性与发布正确性问题，不因 23 个 fixture 测试通过而消失。
- 修复方向：将 live `app.js` 版本递增到高于 58，并同步/补充当前版本的静态断言。

### [P1 / CRITICAL] 新增 DOM class 没有对应 CSS 选择器

- 文件：`frontend/literature-maps.js:1975` 为历史项创建 `literature-map-analysis-history-item`。
- 核对：`frontend/literature-maps.css:102-114` 定义了 analysis、history 容器及其它分析 class，但全文没有 `.literature-map-analysis-history-item` 选择器（`rg -n "\\.literature-map-analysis-history-item" frontend/literature-maps.css` 无命中）。其余本Task新增 `literature-map-analysis*` class 均有 `#literature-maps-view` 作用域样式。
- 影响：违反项目 DOM 双向契约；该项当前主要表现为未受控的历史条目样式，仍必须在合入前补 scoped selector 或移除无用 class。

### [P1 / HIGH] 分析轮询达到 120 次后静默卡在“生成中”，没有失败/重试入口

- 文件：`frontend/literature-maps.js:2112-2115`。
- 最小复现：让 `GET /api/literature-maps/{map_id}/analyses/{analysis_id}` 连续返回 `analysis.status=queued/running`；第 120 次后 `state.analysisPollAttempts >= MAX_ANALYSIS_POLL_ATTEMPTS` 分支直接 `return`，不更新状态、不显示错误、不安排下一次读取。此时 `state.analysis` 仍是 queued/running，按钮仍由 `1955-1960` 禁用；“重新分析”只在 `1984-1992` 的 failed+retryable 分支创建，因此用户无法恢复，只能切节点/重新打开页面。
- 影响：违反“异步 job 失败/重试”可操作性要求；与既有地图轮询在 `2283-2285` 明确给出后台运行提示的做法不一致。
- 修复方向：达到上限时设置受控、可重试的分析错误/状态并渲染恢复入口，或明确显示后台继续与刷新状态；不能静默停轮询并保持生成中。

## 四项前端必守逐条结论

| 门禁 | 结论 | 代码事实 |
|---|---|---|
| DOM 契约 | **FAIL** | `literature-map-analysis-history-item` 在 `literature-maps.js:1975` 创建，但 `literature-maps.css` 无对应 selector。 |
| 资源版本 `?v=N` | **FAIL** | `app.js` 在 `6252-6254` 改动，live tag `index.html:786` 仍为 `app.js?v=58`；地图 JS/CSS 自身为 v8/v6。 |
| XSS | **PASS** | `createElement` 在 `literature-maps.js:90-95` 使用 `textContent`；摘要/错误/source version/引用在 `1913-1933` 均通过安全 DOM 写入；模块无 `innerHTML`、`insertAdjacentHTML`、`document.write` 或 `eval`。fixture 的 `<img onerror>` 仅作为文本显示。 |
| CSS 作用域 | **PASS**（除上列缺失 class） | 本Task新增 CSS 选择器均以 `#literature-maps-view` 开头（`literature-maps.css:102-114`），未发现裸全局 selector。 |

## 冻结合同核对（通过项）

- 详情读取 `loadNodeAnalyses`（`literature-maps.js:2001-2007`）只发 GET；模型 POST 只由“基于摘要分析/基于全文分析”按钮事件（`1952-1960`）进入 `startAnalysis`（`2137-2153`），打开详情不会自动生成。
- `available_evidence_levels`/`abstract_available`/`fulltext_ready` 控制入口（`1888-1892`、`1955-1960`）；缺摘要或全文不可用时不会从前端发起对应 POST。全文结果标题明确为“全文索引片段依据”，摘要结果明确为“仅基于摘要”（`1917-1919`）。真实索引门禁仍需后端/E2E 验证。
- 分析及会话 POST body 只包含 `evidence_level` 与 `idempotency_key`（`2150-2153`、`2189-2192`）；本Task新增请求没有客户端 `document_ids`、URL 或 project override。地图创建流程中的既有 `project_id` 不属于本分析/会话 body。
- 结果、source version、引用和错误通过纯文本渲染；历史版本只读展示（`1971-1979`），新任务失败时仍保留历史 completed 结果（`1995-1997`），未见前端静默覆盖旧结果。
- 切图、切节点、关闭详情及迟到响应有 request/generation/map/node/active 守卫（`922-931`、`1756-1780`、`2005`、`2118`、`2128`、`2193-2198`）；关闭地图视图时未回写 stale 响应。`setActive(false)` 未显式清理分析 timer，但 timer callback 首行检查 `!state.active`，不会继续请求或写回。
- 会话跳转只使用服务端返回的 `conversation_id`（`2167-2179`），通过 `app.js:6252-6254` 暴露的既有 `openConversationFromWorkspace` 复用原会话页面，不创建聊天 UI 或客户端伪造 ID。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 2 | fail |
| HIGH | 1 | fail |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **BLOCK** — 先修复两个前端强制门禁，并为轮询上限增加可操作的失败/重试状态，再进行集中复审。真实摘要级/全文级分析、来源索引、会话绑定 smoke 仍由后端门禁与主会话负责，不能由本报告放行。

## 复审追加：集中修复后窄复审（2026-10-20）

### 原 BLOCK 项逐项复核

1. **资源版本：PASS** — `frontend/index.html:786` 已更新为 `app.js?v=59`；地图资源仍为 JS v8/CSS v6。对应静态契约已更新并通过。
2. **DOM 契约：PASS** — `frontend/literature-maps.css:110-112` 已补齐 `.literature-map-analysis-history-item` 与可点击历史按钮的 `#literature-maps-view` scoped 样式；`literature-maps.js:1991-2000` 创建并使用的 class 均有对应 selector。
3. **轮询上限：PASS** — `frontend/literature-maps.js:2156-2163` 在 120 次后保留 queued/running，不伪造 failed，显示后台运行提示和“重新查询”；`2144-2153` 的重新查询仅重置 GET 轮询窗口并复用原 analysis/job，不触发 POST。Chromium fixture 在首次与重新查询阶段均断言 `analysisBodies.length == 1`。
4. **旧历史结果与 source/evidence：PASS** — `literature-maps.js:1946-1952` 按选中的 `analysis_id` 选择记录，`1995-1998` 点击历史按钮后重新渲染，结果卡片使用选中记录自己的 `evidence_level`、`source_version` 和 `result`。除 fixture 断言旧摘要外，额外只读 Chromium 窄验证将旧记录临时改为 `full/source-full-old` 后点击 v0，卡片实际显示“全文分析结果（全文索引片段依据）”、`版本：source-full-old` 与旧摘要文本，未串用当前 v1 字段。

### 修复后验证

- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_feasibility.py tests/frontend/test_frontend_conversation_contract.py`：退出码 0，40 passed，无 skip。
- `node --check frontend/literature-maps.js && node --check frontend/app.js`：退出码 0。
- `git diff --check -- frontend tests/frontend`：退出码 0。
- 机械核对：live 版本为 v8/v6/v59；history item/button selector 均存在且 scoped；地图模块无 `innerHTML`、`insertAdjacentHTML`、`document.write` 或 `eval`。

### 窄复审结论

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **GO（仅前端 Task05 窄复审）**。原三项 P1 已关闭，旧历史结果点击及 source/evidence 隔离通过。该 GO 不替代真实摘要级/全文级分析、provider、canonical document/index readiness、Conversation binding API smoke、后端 pytest、部署或 Spec 级验收；这些仍由主会话按后端门禁执行。
