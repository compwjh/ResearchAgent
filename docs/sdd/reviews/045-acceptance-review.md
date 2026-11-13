# 045 跨端验收报告 · 任务 O（E2E 真跑 + 分批全量前端套件 + 浏览器真实联调）

- 验收角色：QA / tester（跨端验收总控，只读验证）
- 日期：2026-11-10；服务：`http://127.0.0.1:8000`（`/api/health` = 200，Reranker 精排已启用，**未重启服务**）
- 基线：git HEAD `efec3c06 fix(ui): 深度研究 tab 与全站可用性修复批次`（`docs/sdd/spec-status-changelog.md` 首条标注 `Refs: spec-045`）
- 运行方式：`.venv/bin/python`（3.11.13 / pytest 9.1.1 / Playwright chromium-1169 headless）；E2E 用 `RUN_E2E=1 E2E_BASE_URL=http://127.0.0.1:8000`
- 边界声明：本轮**未修改**任何业务代码、测试断言、夹具/fixture、既有文档与 `?v=` 版本号；未新增 skip/xfail；未执行任何 git 写操作。仅新增本报告与进展日志。浏览器侧只做 DOM 读取与用户级点击（E2E 用例按设计创建了 2 条研究会话）。
- 进展日志：`.codebuddy/agent-logs/spec-045/task-00/tester/20261110-021100.md`

## VERIFICATION REPORT（跨端总表）

| 维度 | 结论 | 数字 |
| --- | --- | --- |
| E2E 真跑（`tests/e2e/`） | **FAIL** | 2 failed / 0 passed / 0 skipped（无环境 skip） |
| 前端全量 pytest（3 批） | **PASS** | 510 passed / 0 failed / 0 skipped |
| 前端全量 JS 探针（1 批） | **FAIL** | 30 pass / 1 fail / 0 skip（共 31 文件） |
| 浏览器真实联调 | **PASS** | 4/4 项成立（DOM + 截图） |
| 高频回归点（版本号 / class↔CSS） | **PASS** | 生效版本 7/7 与任务给定一致 |
| **Overall** | **NOT READY** | E2E 2 FAIL + 1 个稳定真实回归 + 1 个存量 flaky |

## 1. E2E 真跑（原始输出）

前置核对（先读后跑）：`tests/e2e/test_research_lifecycle_e2e.py:22-25` `pytestmark = pytest.mark.skipif(not os.environ.get("RUN_E2E"), reason="浏览器端到端需设置 RUN_E2E=1 并先启动后端服务(:8000)")`；`tests/e2e/conftest.py:13` `BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")`，`page` fixture 用 `browser.new_context(base_url=BASE_URL)`；浏览器二进制已装、`/api/health` 200。本批次对该文件唯一改动为 `_fill_and_create` 新增 `page.click("#research-tab-create")` 共 3 行（`git show HEAD -- tests/e2e/...` 显示 diff +3）。

因未安装 `pytest-timeout`，改用 `.venv/bin/python` + `subprocess.run(..., timeout=170)` 分用例包裹（单用例 ≤180s，捕获原始输出，无工具级超时 kill）。命令：

```
RUN_E2E=1 E2E_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m pytest -q -v -s tests/e2e/test_research_lifecycle_e2e.py::<nodeid>
```

### 用例 1 `test_research_task_create_shows_in_list`

```
collected 1 item
tests/e2e/test_research_lifecycle_e2e.py F
page = <Page url='http://127.0.0.1:8000/c/e32fe115557a488a911f8c0acd11e2e9'>
tests/e2e/test_research_lifecycle_e2e.py:105: in test_research_task_create_shows_in_list → _wait_task_opened(page)
tests/e2e/test_research_lifecycle_e2e.py:89: in _wait_task_opened → page.click(
E   playwright._impl._errors.TimeoutError: Page.click: Timeout 30000ms exceeded.
E     - waiting for locator("#research-task-list .research-task-card[data-session-id='0e38dc5caed4403187d8649bd4d607d7']")
E       - locator resolved to <button type="button" class="research-task-card" data-task-id="d21317d817b051768919dfd95b177522" data-session-id="0e38dc5caed4403187d8649bd4d607d7">…</button>
E       - attempting click action → 56 × "element is not visible" / retrying
FAILED tests/e2e/test_research_lifecycle_e2e.py::test_research_task_create_shows_in_list
1 failed in 34.55s   ; RETURNCODE=1
```

### 用例 2 `test_research_lifecycle_follow_through`

```
collected 1 item
tests/e2e/test_research_lifecycle_e2e.py F
page = <Page url='http://127.0.0.1:8000/c/47fad803f2fd4311a1f9fe42e70d76f8'>
tests/e2e/test_research_lifecycle_e2e.py:125: → _wait_task_opened(page)
tests/e2e/test_research_lifecycle_e2e.py:89: → page.click(同一 data-session-id='0e38dc…')
E   TimeoutError: Page.click: Timeout 30000ms exceeded … "element is not visible"
FAILED tests/e2e/test_research_lifecycle_e2e.py::test_research_lifecycle_follow_through
1 failed in 33.26s   ; RETURNCODE=1
```

**pass/fail/skip 汇总**：2 failed / 0 passed / 0 skipped。两用例均在 `_wait_task_opened():89` 同一行、同一卡片、同一「element is not visible」失败，100% 同源、稳定复现（非 flaky）。`RUN_E2E=1` 已生效（未 skip）。

**关于外部 LLM 依赖（按要求如实记录）**：两用例都**未**到达用例 2 的 `page.wait_for_function(..., timeout=300000)` 计划生成等待段，源文件内的 3 个 `pytest.skip`（`:138` LLM 不可用、`:169` 运行期审批、`:172/:231` 环境依赖/重型阶段）**一个都没触发**。因此外部 LLM 是否可达**本轮未被测出**，不能记为环境阻塞、更不能把失败改写成 skip；spec029 全文获取 / spec030 证据矩阵与只读报告阶段本轮**不可达、未验证**。E2E 运行中会创建真实研究会话（两条 URL `/c/e32fe115…`、`/c/47fad803…`），未做数据清理（不属本任务边界）。

### 失败根因（代码事实，判断是否本批次引入）

1. 创建链路可用：`#research-tab-create → #research-goal → #research-create-button` 成功返回新 session/task id（卡片 locator 已解析出来）。
2. `frontend/index.html:225-247`：主 tab `#research-tab-tasks`(aria-selected=true) / `#research-tab-create`(false)，`#research-tabpanel-create` 默认 `hidden`、`#research-tabpanel-tasks` 默认显示。`git show HEAD~1:frontend/index.html | grep research-tabpanel` **零命中** → 主 tab 结构为本批次新增。
3. `frontend/research-tasks.js:3754-3763` `createTask` 成功分支：`:3756` 新增 `activateResearchTab('tasks')`（切回任务面板）→ `:3759 renderTaskList()` → `:3762 if (conversationId) openConversationFromResearch(conversationId)` → `:3763 await selectTask(...)`。`:896-914 activateResearchTab` 只改 `panel.hidden / aria-selected / tabIndex`，不重建 DOM。
4. `:3782-3789 openConversationFromResearch` 调 `root.openConversation(conversationId)`（`frontend/app.js:3161` 定义）；`:3850-3872` history guard 在 `location.hash !== '#research-view'` 时调用 `closeResearchView()`，而 `:958-961 closeResearchView` 执行 `view.hidden = true`。结果 `#research-view` 整体隐藏，`#research-task-list` 卡片随之 `not visible`，且 `#research-detail-status` 未变成非空状态 → `_wait_task_opened` 回退到 `page.click` 卡片并 30s 超时。
5. **是否本批次引入**：`git show HEAD~1:frontend/research-tasks.js` 显示 `:3467` 的 `openConversationFromResearch(conversationId)` 调用、`:3487-3493` 的函数实现、`:3555-3572` 的 history guard 在改动前**逐字存在**；即"创建后自动打开会话视图"不是本批次新增。本批次新增的是 hidden 主 tab 面板与 E2E 测试侧静态适配（+3 行），并在 `:3756` 新增切回逻辑（说明已意识到可见性），但切回被紧随的 `:3762` 覆盖。该 E2E 此前**从未真跑过（无历史绿灯基线）**，故不能断言"改动前必 pass"；准确结论是：**既有「创建后自动开会话」行为与 E2E「停留在研究任务视图点选卡片」的契约不一致，在本批次第一次真跑时暴露**，不属于本批次新建的视图切换代码缺陷。

**最小修复建议（只回报，未改任何代码，请主会话分派）**：
- 业务侧（优先）：`createTask` 成功后不要在 `selectTask` 前 `openConversationFromResearch`，或先完成 `selectTask` 并保持 `#research-view:not([hidden])` + `#research-tab-tasks[aria-selected=true]` 后再决定是否跳转，使 `#research-detail-status[data-status]` 变为非空 planning 状态。
- 测试侧（需主会话明确授权，本任务禁止改断言）：`_wait_task_opened` 前等待 `#research-view:not([hidden])` 与任务面板可见，再点卡片。
- 两处均超出任务 O 边界，未实施。

## 2. 分批全量 `tests/frontend/` 统计

按前缀精确切 4 批，写清单到 `/tmp/qa_batch_{A,B,C,D}.txt` 并断言覆盖：`test_*.py` 56 个 → A=18 / B=18 / C=20，`test_*.js` 31 个 → D=31；`pytest tests/frontend --collect-only -q` = **510 tests collected**，与三批 passed 之和 510 一致，无遗漏、无重叠。批 A 首次前台单命令触发**工具级超时**（正是上一轮遗留问题），改为 `nohup` 后台 + 日志轮询绕过；每批一条独立命令。

| 批次 | 范围 | 命令要点 | passed | failed | skipped | 耗时 |
| --- | --- | --- | --- | --- | --- | --- |
| A | `test_frontend_literature_map_*` + `test_frontend_map_*`（18 个 .py） | `pytest -q --tb=short --no-header $(cat /tmp/qa_batch_A.txt)` | **174** | 0 | 0 | 425.92s (7:05) |
| B | `test_frontend_task_*` / `test_research_*` / `test_paper_*` / `test_evidence_*` 等（18 个 .py） | 同上 | **124** | 0 | 0 | 12.19s |
| C | 其余 20 个 .py（button affordance / composer / context / task J/D 契约等） | 同上 | **212** | 0 | 0 | 60.49s |
| D | 全部 31 个 `test_*.js`（node:vm 探针） | `node <file>` 逐个，按 exit code 统计 | **30** | **1** | 0 | — |
| **合计** | 87 文件 | — | **540**（510 py + 30 js） | **1** | **0** | — |

K1 新建契约覆盖情况：`tests/frontend/test_frontend_map_canvas_head_narrow_desktop.py`（批 A，PASS）；`tests/frontend/test_research_view_stability.js`（批 D，PASS，输出 `ok - research view stability behavior contract`）；另 `test_frontend_tag_multiselect.js`、`test_frontend_memory_projects.js`、`test_frontend_short_text_helpers.js`、`test_frontend_task_j_behavior.js`、`test_frontend_button_affordance_contract.py`（批 C）、`test_frontend_task_d_contract.py`（批 B）均 PASS。

## 3. 失败项判定与证据

### 3.1 `tests/frontend/test_report_action_race.js` —— 真实回归（稳定失败，非 flaky）

- 复跑：首跑 + 3 次 = **4/4 全部 rc=1**，排除 flaky。
- 原始错误：`AssertionError [ERR_ASSERTION]: boot refresh should load the current report; status=undefined; requests=[... "/api/research-sessions/session-target"]`；`at runBootListRace (tests/frontend/test_report_action_race.js:770:12)`、`at async testLateBootListFailureCannotClearSelectedCurrentSession (:802:3)`；`actual: undefined, expected: 2`。
- 断言依据：`tests/frontend/test_report_action_race.js:770` `assert.equal(state.report?.report_version, 2, ...)` —— boot refresh 后 `state.report` 未加载。
- 是否本批次引入：`git show HEAD --stat -- tests/frontend/test_report_action_race.js` **空**（测试文件未改）；而 `frontend/research-tasks.js` 本批次 `+372 / -82` 行（防闪烁 / key 化 diff / generation 守卫 / 静默刷新校验），与失败语义高度相关。定位线索：`research-tasks.js:786/:788/:1697/:2520` 的 `loadReport` / `selectTask` 调用路径，boot 的 `refreshWorkspace` 后未走到报告加载（测试桩里 `requests` 列表已含 `/api/research-sessions/session-target`，但没有对应的报告请求完成态）。
- 结论：**稳定真实回归**，建议主会话分派前端 dev 核查 boot refresh 与 `state.report` 装配时序；未改代码。

### 3.2 E2E 两用例 —— 见 §1，稳定失败、同源，不重复计入前端套件统计。

## 4. 两个历史 flaky 的稳定结论（各连跑 3 次）

| 用例 | run1 | run2 | run3 | 结论 |
| --- | --- | --- | --- | --- |
| `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（K2 度量口径） | PASS 16.38s | **FAIL 8.66s** | PASS 17.95s | **仍未真稳定** |
| `test_frontend_literature_map_contract.py::test_component_fixture_renders_and_supports_core_interactions`（K1 竞态/gate） | PASS 13.85s | PASS 12.64s | PASS 13.68s | **3/3 稳定** |

- K2 失败原文：`E assert 7 == 8`，位置 `tests/frontend/test_frontend_map_feasibility.py:114` `assert initial["metrics"]["layoutIterations"] == 8`（实际 7）；Captured stdout：`[litmap:baseline] maxGestureWallMs=32.00 maxRenderWallMs=0.20 … interactionCount=12 renderRafCount=25`。属布局迭代计数/时序口径的偶发漂移，并非阈值 `< 1000` 放宽问题；批 A 全量那一次恰好 PASS 属偶然，**不得据此宣称已稳定**。
- K1 用例 3/3 PASS，说明创建面板竞态与 gate 修复在本次样本内有效（样本 3 次，仍建议后续观察）。
- 本轮**未放宽任何断言、未新增 skip/xfail**。

## 5. 浏览器真实联调（Playwright headless，直接打开 `http://127.0.0.1:8000`）

逐项 DOM 断言（截图落 `/tmp/qa_item1_research_create_tab.png`、`/tmp/qa_item2_memory_projects.png`、`/tmp/qa_item3_tag_menu.png`、`/tmp/qa_item3_multi_selected.png`、`/tmp/qa_item3_or_filter.png`，为临时证据不入库）：

**项 1 ✅ PASS** — 深度研究视图顶部主 tab。
- 默认：`#research-main-tabs [role=tab]` = `[{id:research-tab-tasks,text:"研究任务",sel:"true"},{id:research-tab-create,text:"创建研究会话",sel:"false"}]`；`research-tabpanel-tasks.hidden=false`、`research-tabpanel-create.hidden=true`、`#research-task-list` 存在、`#research-view.hidden=false` → 默认「研究任务」tab 正常。
- 点 `#research-tab-create`：`#research-goal` **visible=true**、`#research-create-button` **visible=true**、`create-panel.hidden=false`、`tasks-panel.hidden=true`、`aria-selected=true`。再点回 `#research-tab-tasks` 恢复 `tasksHidden=false / sel=true`。依据 `index.html:225-247`、`research-tasks.js:896-943`。

**项 2 ✅ PASS** — 记忆治理「项目记忆」列表 ≥1 条。
- `#memory-view.hidden=false`，`#memory-project-documents-title` = 「项目记忆」；`#memory-project-documents-list` 有 **2 条** `li.memory-project-doc`（`DeFi / projects/001270c0…md`、`test深度研究 / projects/ea7d1d6a…md`），`#memory-project-documents-empty.hidden=true`，状态区无错误。
- 后端对照：浏览器内 `GET /api/memory-documents/projects` = **200**，返回 2 条 active 项目（`DeFi`、`test深度研究`），与 DOM 一致。依据 `index.html:453-464`、`app.js:74`、`styles.css:497`。

**项 3 ✅ PASS** — 标签筛选「+N / 更多」下拉可打开且多选、OR 语义成立。
- 筛选条：`#literature-map-tag-filter-bar.hidden=false`，3 个 chip（演示数据 / test2 / test3）+ 按钮 **`+1 更多`**（`.btn-outline.literature-map-tag-filter-more`，`aria-haspopup=true`、`aria-expanded=false`）；`GET /api/literature-maps/tags` = 200 返回 4 个标签（> `TAG_FILTER_CHIP_LIMIT=3`），故 +N 出现。依据 `literature-maps.js:2013-2030`。
- 打开：菜单 `.literature-map-tag-filter-menu` `aria-label="按标签筛选（可多选）"`，`aria-expanded=true`，4 个 `input[type=checkbox][data-tag-id]`（演示数据/test2/test3/test4），浮层计数「已选 0」。依据 `literature-maps.js:2065-2112`。
- 多选：勾选 2 个后 `checkedCount=2`、浮层计数「已选 2」；Esc 关闭菜单后筛选条重绘出 `.literature-map-tag-filter-count` = 「已选 2」、`aria-pressed=true` 的 chip = `[test2, test4]`。（首轮下拉开着时 `chipCount=null` 是 `setTagFilter(..., redrawBar=false)` 的刻意设计，见 `literature-maps.js:2036`，避免替换「更多」anchor 令浮层悬空，非缺陷。）
- **OR 语义硬证据**：API `/api/literature-maps` 共 3 张图；标签覆盖「演示数据」=3 张、`test2`/`test3`/`test4` 各=1 张（同为 `89209acd…` 认证与协议安全）。清空后 `#literature-map-count` = `3/3`；只选 `test2` → `1/3`「已选 1」；加选 `test4` → `1/3`「已选 2」（并集=1，符合 OR）；选「演示数据」(3) + 「test2」(1) → `3/3`（**OR 并集=3；若为 AND 应为 1/3**）。实现依据 `literature-maps.js:1692` `const matchesTag = !state.listTagIds.size || (map?.tags || []).some(tag => state.listTagIds.has(tag?.tag_id))`（`some` 即 OR）与 `:104` `listTagIds: new Set()`。

**项 4 ✅ PASS** — 次级按钮明确可用态（白底紫描边、hover/focus 有变化）。
- 取 `#memory-project-documents-refresh`（`class="btn-outline memory-project-documents-refresh"`）computed style：基态 `background=rgb(255,255,255)` 白底、`border=1px solid rgb(216,210,255)`（#d8d2ff 淡紫）、`border-radius=8px`、`color=rgb(74,69,96)`、`font-weight=600`。
- hover：`background=rgb(240,237,255)`（#f0edff）、`border-color=rgb(109,93,252)`（`var(--accent)` 紫）→ 明确变化。
- focus（`Shift+Tab`/`Tab` 键盘导航）：`:focus-visible=true`、`border-color=rgb(109,93,252)`、`box-shadow=rgb(238,236,255) 0 0 0 3px`（`var(--accent-soft)` 光环）、白底保持 → 明确变化。依据 `styles.css:4297-4319`（`.btn-outline` / `:hover` / `:focus-visible` / `:disabled` 四组规则齐全）。注：仅用程序性 `.focus()` 时浏览器启发式不给 `:focus-visible`（首轮 `focusVisible=false`），属正常，非缺陷。

页面 `pageerror` 列表为空。

## 6. 高频回归点核查（regression-guard）

- **静态资源版本号**：`index.html` 生效 `<script src>/<link href>` 引用 `app.js?v=73`、`styles.css?v=71`、`literature-maps.css?v=34`、`literature-maps.js?v=47`、`research-tasks.js?v=23`、`research-session-ui.js?v=3`、`conversation-research.js?v=3` —— **7/7 与任务给定一致**；另有 `kb-inspection.js?v=24`、`processing-tree.js?v=2` 及 vendor 资源未变动。批 A 内版本契约断言（如 `test_frontend_literature_map_contract.py` 断言 `?v=47` / `?v=34`）随 174 passed 通过。
- **JS class 名 ↔ CSS 选择器**：`styles.css:497` `#memory-view .memory-project-documents-status[data-state="error"]` 与 `index.html:462` `class="conversation-status memory-project-documents-status"` 一致 —— 前端评审 `20261109-frontend-ux-fix-review.md` 记录的 1 个 CRITICAL（类选择器永不匹配）**已修复**；`app.js:74` 按 id 查询、设置 `data-state`。`.btn-outline` 在 JS 渲染（`literature-maps.js:2016`、`index.html:460`）与 CSS（`styles.css:4297`）双向一致。
- 后端侧本轮未改动、未重启；未触发 SQLite 迁移 / 外键 / SSRF / USENIX 来源相关路径（仅只读探活 `/api/health`、`/api/memory-documents/projects`、`/api/literature-maps*`）。

## 7. 汇总单端结论（背景，不重复跑单端单测）

- 后端：`docs/sdd/reviews/20261109-demo-data-cleanup-backend-review.md` = **APPROVE**（2 个 MEDIUM 已补强）；本轮跨端探活 `/api/health` 200、`/api/memory-documents/projects` 200（2 条 active）、`/api/literature-maps` 与 `/tags` 200。未重复跑后端 pytest。
- 前端：`docs/sdd/reviews/20261109-frontend-ux-fix-review.md` 原判 **BLOCK**（1 CRITICAL + 2 MEDIUM），CRITICAL 已按本报告 §6 核实修复；本轮全量前端套件见 §2。
- 本批次 agent-logs 中**无**新的 `backend-tester` / `frontend-tester` 单端报告（spec-045/task-00 仅有 architect / backend-dev / frontend-dev / doc-updater 日志），故单端细节以上述两份 review 与本轮全量实测为准。

## 8. 不通过项、风险、未完成项与环境阻塞

**不通过项（阻断）**
1. E2E 两用例稳定 FAILED（`_wait_task_opened():89` 卡片不可见）——见 §1 根因与最小修复建议，回报主会话分派，未改代码。
2. `tests/frontend/test_report_action_race.js` 稳定 FAILED 4/4（boot refresh 未加载 `state.report`）——真实回归，见 §3.1。
3. `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 3 次中 1 次 FAIL（`layoutIterations 7≠8`）——**K2 flaky 未消**，见 §4。

**风险**
- E2E 无历史绿灯基线，无法量化"改动前是否通过"；两处修复（业务跳转 vs 测试适配）需主会话裁决归属，避免只改测试掩盖视图跳转契约问题。
- `test_report_action_race.js` 失败点与本批次 `research-tasks.js` 大改（generation 守卫 / 静默刷新）语义相邻，若业务侧修 E2E 时再动 `createTask`/boot，需重跑该 JS 探针防二次回归。
- K1 flaky 仅 3 次样本稳定，样本量有限。

**未完成项**
- E2E 用例 2 的 LLM 依赖段（spec029 全文获取、spec030 证据矩阵/只读报告）因前置失败**不可达、未验证**；未放宽任何断言，未新增 skip。
- 未验证 `RUN_E2E=1 pytest -q tests/e2e/ -v` 整目录一次性运行的完整输出（按「单用例 ≤180s」要求改为分用例跑，两用例均已单独真跑并留原始输出）。
- 未做浏览器端「创建研究会话后点选新卡片」的修复后复验（需先由主会话分派改码）。

**环境阻塞**
- 外部 LLM / 检索可达性**本轮未测出**（用例 2 未进入 300000ms 等待段），如实记录为「不可判定」，不记为环境阻塞、不 skip。
- 工具级超时（约 <170s）导致批 A 首次前台单命令被截断，已用后台运行 + 轮询解决，最终 174 passed 完整取得；该环境限制不影响结论。
- 按要求**未重启服务**；后端任务 N 将改代码，主会话收口时统一重启，故本报告结论仅对当前运行中的服务快照有效。

---

## 开发主管签字

（留空，交由架构师签署）
# SPEC-045 验收评审报告（Gate 5 · Acceptance Review）

- **Spec 编号 / 标题**：045 — 评测与可观测性加固闭环（`docs/sdd/specs/045-evaluation-observability-hardening.md`）
- **评审角色**：`tester`（跨端验收总控 / `e2e-runner` + `verification-loop`）；本报告**不含** architect 签字
- **评审日期**：2026-11-08
- **分支 / HEAD**：`feature/spec-045-evaluation-observability-hardening` / `f8106ff9`；`origin/main=1b26c76c`（未 push、未合 main）
- **Spec 状态（本轮只读核实）**：头部字段为 `已确认`（spec:5），任务计划口径为 `实施中`（spec:324、需求评审:108、技术评审:110）。本轮**不修改、不转 `已完成`**，口径差异列入残留项交主会话收口。
- **证据目录**：`docs/sdd/plans/045/runs/task-02/`、`runs/task-07/`、`runs/task-08/`；`docs/sdd/reviews/045-requirement-review.md`、`045-tech-review.md`；`docs/sdd/plans/045/runs/task-07/backend-review.md`；`.codebuddy/agent-logs/spec-045/task-08/`（backend-tester / backend-dev-trace / architect-review / tester）。
- **判定纪律**：全部结论基于 `Read` / `Grep` / `git` / 只读 `curl` 的真实文件与运行时事实，逐项附「路径:行」；不 mock 冒充 E2E、不代签、不改 spec 状态、不 `git commit`/`push`/合 main。
- **判定依据标准**：11 项加固 `spec:95-107`；Q9 硬前置 `spec:134-138`；Q10 四类证据 `spec:140-147` + 场景映射 `spec:268-273`；明确不做 `spec:117-130`；边界 `spec:187-196`；产品使用步骤 `spec:198-273`；Gate 5 `SDD-GATE-CHECKLIST.md:106-112`；DoD `SDD-GATE-CHECKLIST.md:128-138`；准备度约束 `AGENTS.md:58`、`task-08:74-75`。

---

## 一、验收结论（先给结论）

**通过。**

- 11 项加固 **11/11 通过**（逐项依据见第三节）；Q10 四类证据 **4/4 齐全**（第三节）；Q9 三项硬前置均满足。
- 准备度十项 **9/10 通过**（第四节，满足 `AGENTS.md:58` 的「至少九项通过」；第 10 项签字与台账闭环待主会话/architect，未闭环，故**不宣称 10/10**）。
- 单端无 P0/P1（backend-reviewer P0=0/P1=0；backend-tester 定向 `49 passed, EXIT=0`）；全量 `4112 passed / PYTEST_EXIT=0`；**当前部署版本服务真实在线**（PID 65665，`/api/health` 200），本轮独立只读 curl 跨端集成复核四端点全部符合契约（第五节）。
- 验收结论为「通过」**不等于** Spec 可转 `已完成`：签字栏留空（Gate 5 `SDD-GATE-CHECKLIST.md:111` 规定留空不得转状态），部署门禁（CI / 覆盖率阈值 / PR approval）本轮**未宣称通过**，状态台账/复盘/changelog/本地 commit 由主会话收口（第八节）。

---

## 二、真实验收材料（命令 / 退出码 / 通过数量 / 阻塞项）

| 材料 | 真实命令 | 退出码 / 状态 | 通过数量 / 结果 | 证据路径 |
|---|---|---|---|---|
| 最终全量回归 | `.venv/bin/python -m pytest -q` | `PYTEST_EXIT=0` | `4112 passed, 2 skipped, 5 warnings, 67 subtests passed in 779.30s (0:12:59)` | `runs/task-08/full-regression.txt`（尾 2 行） |
| 新增测试定向合并集（真 SDK / 并发流中断 / 隐私 thinking / kb trace 归属 / `--send` dashboard） | `.venv/bin/python -m pytest tests/observability/... -q` | `EXIT=0` | **精确 `49 passed`** | `.codebuddy/agent-logs/spec-045/task-08/backend-tester/20261108-171302.md:41`；3 个新增测试 `tests/observability/test_{kb_trace_attribution,privacy_thinking_chain,stream_context_isolation}.py` |
| Q10① RED（三项，隔离副本回退） | `.venv/bin/python -m pytest tests/observability/test_task05_decoupling.py::... / tests/platform/test_task06_identity_redaction.py -q --tb=short` | `EXIT=1`（真实失败断言） | 3 条 RED 日志各含 `FAILED` | `runs/task-08/red-03-sampling.log` / `red-04-flush.log` / `red-09-redaction-thinking.log`；方法学 `q10-red-green-summary.md:7-43` |
| Q10① GREEN（当前仓库真实代码） | 同上（当前代码） | `EXIT=0` | `21 passed` | `runs/task-08/green-current-code.log`、`q10-red-green-summary.md` |
| 评测真实 CLI | `python -m backend.eval_042.cli --export ...` | 0 | `report.json` + `report.md` 五类指纹齐全；score 真实重跑 `979 → 979`，`delta=0` | `runs/task-02/eval-baseline/report.json`、`report.md`、`runs/task-02/evidence.md` |
| 真 SDK 冒烟 | 真 `Langfuse` client 跑 chat + kb-ask（非 mock） | HTTP 200 | `langfuse==4.15.1`，四段 phase span | `runs/task-08/sdk-smoke.json` |
| `--send` 真重跑 + dashboard 默认重建 | fixtures `--send`；`setup_langfuse_dashboards.py`（默认） | 0 | traces `385→405`、scores `+140`；默认重建幂等「新建 0 个，跳过 6 个」 | `runs/task-08/dashboard-contract.json:59-90` |
| 当前部署版本 API E2E（服务重启后） | chat / kb-ask 真实 SSE | `health=200` | chat 帧 `meta/progress/token/done` `status=completed` 无 error；kb 帧 `meta/stage/citations/token/debug/done` 无 error | `runs/task-08/deploy-verification.json`、`deploy-chat-sse.txt`、`deploy-kb-sse.txt` |
| 本轮独立跨端集成复核（tester 亲自执行，只读） | `curl /api/health`、`/api/research-tasks`、`/processing-steps?limit=0`、`/processing-steps`（无参） | `200 / 200 / 400 / 200` | health 真实模型列表；`limit=0` → `{"code":"INVALID_LIMIT","message":"limit 越界","retryable":false}`；无参 → 扁平 `{'steps': 25}` | 本轮 Bash 输出；服务进程 `lsof` 实证 Python PID 65665 监听 127.0.0.1:8000 |

- **阻塞项：无**（技术/证据层无未解决 P0/P1、无 API E2E 失败、无关键产物缺失）。收口流程项（签字、台账、复盘、changelog、本地 commit）列入残留项，属主会话待办，非验收阻塞。

> 覆盖率口径如实说明：项目**无覆盖率采集/阈值配置**——`pyproject.toml` / `setup.cfg` / `.coveragerc` / `pytest.ini` / `tox.ini` 均不存在，`requirements.lock.txt` 仅含 `coverage==7.16.0` / `pytest-cov==7.1.0` 依赖但未配置 `addopts`/`fail_under`，全量命令不带 `--cov`。此与 Spec044 合并门禁披露一致，本次以 `pytest -q` 退出码 0 + `4112 passed` 为全量证据（见第七节「已声明边界」）。

---

## 三、11 项加固逐项判定（11/11 通过）

| # | 项目（类别 / task） | 判定 | 证据路径 + 依据 |
|---|---|---|---|
| 01 | `--fallback` 生效 + 合并三套 judge 编排（规格落地 / 03） | **通过** | `spec:97,312` 状态「代码与契约测试完成；Q10② 真实产物已补」；`runs/task-02/eval-baseline/report.json`、`report.md`（真实 `eval_042 --export`）；`runs/task-02/evidence.md`（score 重跑 `979→979` delta=0）；`runs/task-08/full-regression.txt`（4112 passed 含评测用例） |
| 02 | 冻结可复现质量基线（能力补齐 / 03） | **通过** | `report.json` 命中 `sha256`×2 / `seed` / `tie_break`，`report.md` 命中 `sha256` / `dataset`，五类指纹齐全；真实重跑 `979→979` delta=0 可跨版本比较（`runs/task-02/evidence.md`） |
| 03 | 采样提到 trace/请求级 ContextVar（缺陷修复 / 05） | **通过** | `runs/task-08/red-03-sampling.log`（真实 `FAILED`×2 失败断言）→ `green-current-code.log`（`21 passed`）；`q10-red-green-summary.md:47-60`；四段 phase span 见 `runs/task-02/trace-summary.json`、`runs/task-08/sdk-smoke.json`、`deploy-verification.json:35-40` |
| 04 | `flush()` 移出 SSE 关键路径（缺陷修复 / 05） | **通过** | `red-04-flush.log`（`FAILED`）→ `green-current-code.log`（21 passed）；`deploy-chat-sse.txt`（meta/progress/token/done，无 error）、`deploy-kb-sse.txt`（meta/stage/citations/token/debug/done）；`deploy-verification.json:6-19`（chat_status=completed）；`backend-review.md:80`（`enqueue_flush` 适配） |
| 05 | 私有 SDK 符号兼容层 + 显式降级告警（能力补齐 / 05） | **通过** | `runs/task-08/sdk-smoke.json`（真 SDK `4.15.1`、14 处 HTTP 200、四段 phase）、`trace-attribution-fix.json`、`waterfall.png`（真实 PNG 393×565，四段时间轴可见）；升版回归要求保留（见已声明边界第 9 条，不判失败） |
| 06 | 前端基准卡片 `benchmark_summary`（规格落地 / 07，A 裁决打通） | **通过** | `runs/task-07/benchmark-card.png` + `benchmark-card-browser.txt:9-20`（真实 Chromium 四项指标 38478.93 ms / 19.73 tokens/s / 106070016 bytes / 0%，`sectionHidden=false`）；`benchmark-summary.event.json`（seq 40、status 未变）；`backend-review.md:61-66`（A 打通真实性、四项真实测量、前端零改动）；本轮 `git status` 前端改动计数=0 |
| 07 | 统一 trace_id/request_id 贯穿三套观测（能力补齐 / 06） | **通过** | `runs/task-08/trace-attribution-fix.json`（kb 单条 trace `1979780d…`：9 observations、四段 `phase:*`、7 scores、根 observation 已结束）；`deploy-verification.json:21-79`（kb `220f5fb2…` 9 obs / `root_ended=true`；chat `f7e44efc…` 5 obs 含四段 phase）。chat 归属未回归如实记录（见边界） |
| 08 | score 幂等键 + 报告目录文件锁（能力补齐 / 04） | **通过** | `spec:313`（已完成，`真实重跑 score delta=0`）；`runs/task-02/evidence.md`（`979→979`）；文件锁产物 `runs/task-02/eval-baseline/.report.writer.lock`、`eval-rerun/.report.writer.lock` 真实存在；`report.json`/`report.md` |
| 09 | 统一脱敏 + `raw_events.payload` 上限 + thinking 正文（缺陷修复 / 06） | **通过** | `red-09-redaction-thinking.log`（`FAILED`×8）→ `green-current-code.log`（21 passed）；`q10-red-green-summary.md:124-158`（15 用例红转绿、payload 50031→≤4000）；`sdk-smoke.json:203-221`（合成 `sk-proj-FAKECRED…` 真链路 `plaintext_credential_in_stored_trace=false`、`input_is_redacted=true`）；`tests/observability/test_privacy_thinking_chain.py`。值级不按 key 名属已声明边界 |
| 10 | 事件表 retention + `processing-steps` 分页（能力补齐 / 07） | **通过** | `runs/task-07/paging-api-evidence.txt:1-18`（无参扁平 25 条、`LIMIT=2` 带游标、三类越界 400 `INVALID_LIMIT`/`INVALID_CURSOR`、逐页 9 页 `unique=25 set_equal=True`）；`backend-review.md:40-48`（retention 保守 / fail-open / VACUUM 在事务外 / 外键 RESTRICT）；本轮独立 curl 复核 `limit=0`→400、无参→扁平 25 条。启动期同步执行与并列行序属已声明边界 |
| 11 | 真 SDK 冒烟 + 并发/流中断 ContextVar + `--send`/dashboard 契约（能力补齐 / 08） | **通过** | `sdk-smoke.json`（真 SDK 4.15.1）；3 个新增测试 `tests/observability/test_{kb_trace_attribution(4),privacy_thinking_chain(8),stream_context_isolation(7)}.py` 精确 `49 passed, EXIT=0`；`dashboard-contract.json:59-90`（`--send` 385→405 / +140、默认重建幂等「新建 0 跳过 6」）；`q10-red-green-summary.md`。`--force` 非幂等属已声明边界 |

### Q10 四类证据齐全性（4/4）

| 类别 | 判定 | 保存路径（缺一不验收，逐类可查） |
|---|---|---|
| ① 缺陷类红绿测试（03/04/09 先红后绿） | **齐全** | `runs/task-08/q10-red-green-summary.md`（汇总、含 03/04/09 三项）、`red-03-sampling.log`、`red-04-flush.log`、`red-09-redaction-thinking.log`、`green-current-code.log`（`21 passed`）。历史红测未落盘，已用「隔离副本按修复前提交语义回退 + 仓库既有红测文件」补可复现 RED→GREEN（`q10-red-green-summary.md:7-43`），仓库 `backend/**` 零改动 |
| ② 真实 `eval_042` CLI 评测产物（含指纹） | **齐全** | `runs/task-02/eval-baseline/report.json` + `report.md`（`dataset_sha256` / `judge_model_digest` / `prompt_sha256` / `seed` / `tie_break_rule` 五类指纹齐全），score 真实重跑 `979→979` delta=0 |
| ③ Langfuse 可查完整 trace（四段 phase + score 回写 + trace ID） | **齐全** | `runs/task-02/trace-summary.json`（`98b91aa3…` 四段 phase span + 7 scores）、`runs/task-08/sdk-smoke.json`（真 SDK、chat/kb HTTP 200）、`trace-attribution-fix.json`（修复后 kb `1979780d…` 9 obs / 四段 / 7 scores / 根已结束）、`deploy-verification.json`（kb `220f5fb2…` / chat `f7e44efc…`） |
| ④ 瀑布图截图（时间轴四段可见、顺序正确） | **齐全** | `runs/task-08/waterfall.png`（`file` 实证 PNG 393×565；Langfuse v4.27.0 UI 真实截图，四段 phase span 时间轴可见；已裁剪、不含系统提示/召回明文） |

- **Q9 三项硬前置**：① Langfuse 启用（`sdk-smoke.json` 真 SDK、`deploy-verification.json` trace 可查）；② 可复现样本（`dashboard-contract.json` `--send` 真重跑）；③ 真实端到端（真实 Ollama + 真实 Langfuse，非 mock：`deploy-verification.json` + 两份 SSE txt，本轮另以只读 curl 独立复核服务在线）。**三项均满足**。

---

## 四、准备度十项检查（9/10 通过）

> 依据 `AGENTS.md:58`（十项至少九项通过、无 P0/P1、无 API E2E 失败、无关键产物缺失）与 `task-08:74-75`（不得宣称 10/10 除非真实满足）。矩阵沿用 `043-acceptance-review.md:105-116` 十项结构。

| # | 准备度检查 | 判定 | 通过依据 + 产物路径 |
|---|---|---|---|
| 1 | Spec 目标、边界与明确不做已能映射 | **通过** | `spec:88-130`（11 项分类 + 明确不做 + P2）；`045-requirement-review.md:28-58`、`045-tech-review.md:26-67` 均判通过 |
| 2 | 真实 API E2E 请求/响应/实体 ID/终态/产物路径齐全 | **通过** | `runs/task-08/deploy-verification.json:1-84`（health 200、`deployed_service`、两条真实 trace ID、帧计数、SSE 产物清单）、`deploy-chat-sse.txt`、`deploy-kb-sse.txt`；本轮独立 curl 四端点复核一致 |
| 3 | 主路径入口可按真实操作（UI / 自然语言 / CLI） | **通过** | `spec:198-273`（产品使用步骤场景①②③，六要素齐备）；`runs/task-07/benchmark-card-browser.txt:1-25`（真实 Chromium Playwright 选中 `research-benchmark-*` 元素、四项指标可见）；需求评审:52-58 复核「已具备」。本轮前端零改动，既有契约不回归 |
| 4 | 关键产物可查看（report / trace / PNG / 分页 / 基准卡片） | **通过** | 20 个证据文件读回全部 EXISTS 且非空（步骤 3）；两张 PNG 经 `file` 实证为真实 PNG；`report.json`/`report.md`、`trace-summary.json`、`sdk-smoke.json`、`trace-attribution-fix.json`、`paging-api-evidence.txt`、`benchmark-summary.event.json` 均可查 |
| 5 | 人工步骤含点击/提示/等待/等待中状态/下一步/失败恢复 | **通过** | `spec:208-266` 逐步六要素 + 最终产物路径；`spec:268-273` 场景→Q10 映射；`045-requirement-review.md:52-58` 判「逐步具备六要素」 |
| 6 | 关键失败/降级场景诚实呈现且无 P0/P1 | **通过** | 三份评审 P0=0/P1=0（`045-requirement-review.md:20,97-98`、`045-tech-review.md:20,99-100`、`backend-review.md:8,85-102`）；Q10① 三条真实 RED 失败断言保留；已声明边界逐条如实记录（第七节），不冒充成功 |
| 7 | 最终全量回归通过且退出码/计数可复核 | **通过** | `runs/task-08/full-regression.txt` 尾 2 行 `4112 passed, 2 skipped, 5 warnings, 67 subtests passed in 779.30s` / `PYTEST_EXIT=0`；命令 `.venv/bin/python -m pytest -q`。项目无覆盖率采集/阈值配置（与 Spec044 合并门禁披露一致），作为第七节「已声明边界」披露，不计失败 |
| 8 | 当前候选部署 health / 关键链路验证 | **通过** | `deploy-verification.json:3-4`（`health=200`、`http://127.0.0.1:8000`）；本轮 `lsof` 实证 Python PID 65665 监听 8000、`curl /api/health`=200（真实模型列表）；`/api/research-tasks`=200；两份 SSE 帧无 error |
| 9 | API / 浏览器 / 人工步骤 / 导出产物统一绑定当前部署版本 | **通过** | `deploy-verification.json:2-3`（`captured_at` + `deployed_service`）、`:21-79` 两条部署 trace；`benchmark-card-browser.txt:3`（`deployedUrl: http://127.0.0.1:8000/#research-view`）；本轮 curl 复核与证据同端口同契约一致 |
| 10 | tester 结论、architect 签字与状态台账闭环 | **未通过（待闭环，非实现缺陷）** | 本报告 tester 结论「通过」已出具；但**架构师签字栏留空**（`SDD-GATE-CHECKLIST.md:111` 规定留空不得转 `已完成`），spec 头部状态与「实施中」口径未同步、`spec-status-changelog.md` 条目、`docs/sdd/retro/` 复盘、本地 `git commit` 均由主会话收口（第八节残留项）。属流程未闭环，不计入实现/证据缺失 |

**计分：9 PASS / 1 未通过（待闭环）= 9/10，满足 ≥9/10；不通过项无 P0/P1、无 API E2E 失败、无关键产物缺失。按 `task-08:74-75` 如实不写 10/10。**

---

## 五、跨端集成验收（Gate 5 运行时验证，本角色亲自执行）

- **服务真实启动**：当前部署版本服务在线，`lsof -nP -iTCP -sTCP:LISTEN` 实证 `Python 65665 ... TCP 127.0.0.1:8000 (LISTEN)`（与 `deploy-verification.json` 记录的 PID 一致），`node 32716` 监听 3000（Langfuse web）。
- **只读 curl 复核**（未改任何状态、未跑 SSE 写链路、未重跑单端单测）：

| 端点 | 期望 | 实测 |
|---|---|---|
| `GET /api/health` | 200 | **200**，`{"status":"ok","model":"qwen3.8:27b",...}` 真实模型列表 |
| `GET /api/research-tasks` | 200 | **200**，真实任务列表（含 USENIX Security 目标） |
| `GET /processing-steps?limit=0` | 400 稳定错误体 | **400**，`{"detail":{"code":"INVALID_LIMIT","message":"limit 越界","retryable":false}}` |
| `GET /processing-steps`（无参） | 200 扁平 `steps` | **200**，`keys=['steps'] count=25` |

- **跨端判定：PASS**。后端分页越界/无参兼容契约（加固项 10）与前端既有 `app.js` 消费形状一致；服务在线、主链路只读入口全通。真实 SSE 写链路（chat/kb-ask）以已落盘 `deploy-chat-sse.txt` / `deploy-kb-sse.txt` 真实帧为准（非 mock），本角色不重复触发写操作。
- **`regression-guard` 高频回归点核对**：前端 JS class 名与 CSS 选择器、`index.html` 静态资源 `?v=N` —— 本轮 **前端零改动**（`git status` 中 `frontend/**` 命中 0 行），版本号无需升级，既有契约由 `benchmark-card-browser.txt` 真实 Chromium 复核（`research-benchmark-metrics` / `.research-benchmark-metric` 被真实选中并渲染）；后端 SQLite 迁移 / 外键 RESTRICT / SSRF / USENIX 来源 —— 由 `backend-review.md:40-48,79`（无 DDL、`ON DELETE RESTRICT` 规避、全 `?` 参数化、fail-open）与 Task07 只读评审覆盖，本轮无新增业务代码改动，未引入新回归面。

---

## 六、汇总单端报告

| 单端角色 | 结论 | 依据 |
|---|---|---|
| `backend-tester`（后端回归） | **通过** | 真 SDK 冒烟（`sdk-smoke.json` langfuse 4.15.1、chat/kb HTTP 200）、并发/流中断 ContextVar、隐私与 thinking、`--send` + dashboard 契约；**精确 `49 passed, EXIT=0`**（`.codebuddy/agent-logs/spec-045/task-08/backend-tester/20261108-171302.md:41`）；Q10① 真 RED→GREEN 汇总 `q10-red-green-summary.md`（GREEN `21 passed`）；3 个新增测试落 `tests/observability/`；全量 `4112 passed` |
| `backend-reviewer`（只读后端评审） | **通过（Approve）**，**P0=0 / P1=0** | `docs/sdd/plans/045/runs/task-07/backend-review.md:8,102,108`；六个必查点全过、5 条 LOW 为文档记录/可选加固/收口残留（R1–R5）；独立重跑定向集 `38 passed, EXIT=0`、矩阵 `inventory_digest MATCH=True` |
| `frontend-tester`（前端静态核对） | **本轮未派** | 如实说明：本轮**前端零改动**（`git status --short` 中 `frontend/**` 命中 0 行）；Task 07 对第 06 项的 **A 裁决**明确「只改后端 + 复用既有前端契约，不改前端文件」（`spec:109-115`、`task-07`、`backend-review.md:5,71`）。既有前端基准卡片契约由 `benchmark-card-browser.txt` 真实 Chromium 截图 + `backend-review.md:26-28`（`app.js` 消费 `data.steps` 扁平形状）复核，无需单端回归 |

- 跨端总控不重复跑单端单测；单端细节以上述报告/日志为准。

---

## 七、已声明边界（如实声明，均**非遗漏、非失败**）

> 依据 `task-08:89-92` 要求：以下为 Q1/Q3/Q7/Q8、ADR 0002、task-07/08 边界内已声明并如实取证的设计取舍、第三方读回怪癖或后续阶段项，**不得写成遗漏或失败**。与 `045-requirement-review.md:79-100`、`045-tech-review.md:80-89` 口径一致。

1. **`human_agree_rate=null`**：P2 人工标注 gold 集明确不做（`spec:119`、`F2 spec:32`）；`runs/task-02/eval-baseline/report.json:6` 实际为 `null`。评测结论为相对回归基线，不宣称绝对准确率。
2. **两套分数口径仍不统一**：`research_model_outcomes.quality_score` 与 Langfuse score 无映射（P2，`spec:120`、`F17 spec:47`、`spec:184` `POST .../evidence` 不改）。**在线实时评测不做**（ADR 0002、`spec:121`）。
3. **`redaction.py` 值级脱敏、不按 key 名过滤**：按精确凭据模式（`_SK_KEY_RE`/`_BEARER_RE`/`_AUTHORIZATION_RE`/`_CREDENTIAL_ASSIGN_RE`/`_URL_RE`）只改字符串值、保留结构（`backend/app/platform/observability/redaction.py:9-10,29-41,60-70`；`045-tech-review.md:82`），真链路 `sdk-smoke.json:203-221` 验证 `input_is_redacted=true`。属设计取舍，避免误伤含 `token` 的学术文本。
4. **`setup_langfuse_dashboards.py --force` 非幂等**：`dashboard-contract.json:92-104` 如实记录 `DEFECT (reported, not fixed)`（业务脚本超出本 spec 文件边界），给出 `setup_langfuse_dashboards.py:274,280` + `schema.prisma:1542` 证据链；**默认重建幂等已真实验证**（`:59-90`「新建 0 个，跳过 6 个」，6 dashboard / 40 widget ID 与名称多重集不变）；`--force` **未真实重跑**（破坏性，按边界仅只读契约核验，`:11-14,102-103`）。
5. **`018` 冻结矩阵 `inventory_git_revision` 仍为 `8b0cde1`**：`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json:3`、`task-07:183`、`045-tech-review.md:84`；哈希/digest 已按当前内容重算并验证 `MATCH=True`（`backend-review.md:35,79`），revision 保留为历史冻结基线标识，未授权改动。
6. **并列 `started_at` 行序差异（集合一致）**：无参 `ORDER BY started_at, logical_sequence`（`repository.py:1693`）vs 分页 `ORDER BY started_at, step_id`（`:1720`），并列时集合一致但行序不同（`backend-review.md:33-38` R1、`045-tech-review.md:85`）；`paging-api-evidence.txt:18` 实测 `set_equal=True`。分页 keyset 正确、不重不漏，判已知边界非缺陷。
7. **retention 启动期同步执行**：`EVENT_RETENTION_ENABLED` 默认 `True`（`config.py:234-239`），在 lifespan `yield` 之前同步、低峰 fail-open（`backend-review.md:42-45` R2、`045-tech-review.md:86`）；当前阈值 `deleted=0` 不删行，未来大规模清理应改异步（演进点，非当前故障）。
8. **Langfuse 读回怪癖**：`GET /api/public/traces/{id}` 对 kb trace 返回空数组（`trace-attribution-fix.json:10` `public_api_quirk`），改用 `GET /api/public/observations?traceId=` 与 `GET /api/public/scores` 按 traceId 过滤核对；**scores 端点 `limit=100` 截断**，`deploy-verification.json:42,70` `score_count=100` 为截断值，归属按 **7 类 score name**（`eval_ms` / `is_cold_start` / `load_ms` / `overhead_ms` / `prompt_eval_ms` / `tokens_per_sec` / `ttft_ms`，`deploy-verification.json:43-51,71-79`、`trace-attribution-fix.json:53`）核对，不把 100 当成真实 score 总数。属 Langfuse v4 读回怪癖，非本 spec 缺陷。
9. **`spec-041:93` 升版回归要求仍保留**：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md:93`、「每次 langfuse 升版跑 1 次回归（含观测测试 + 一次真实对话触发）」的人肉要求不撤销（`045-tech-review.md:88`、`task-08:18,92`）。本期已补真 SDK 冒烟（`sdk-smoke.json`）与兼容层，但封装保证「退化可发现 + 修复点唯一」，**不保证不退化**（Q7 `spec:64`）。
10. **项目无覆盖率采集/阈值配置**：与 Spec044 合并门禁披露一致；本次以 `pytest -q` 退出码 0 + `4112 passed` 为全量证据（第二节）。覆盖率配置文件不存在、命令不带 `--cov`，如实声明而非宣称覆盖率门禁通过。
11. **Spec045 不 push / 不合 main**：`spec:130`、`task-08:76`；本轮 `git` 只读核实分支 `feature/spec-045-evaluation-observability-hardening`、`HEAD f8106ff9`、`origin/main=1b26c76c`、工作区改动未提交/未推送/未合并。本评审未做任何 `commit`/`push`/合 main。
12. **chat trace 归属未回归 / `root_ended=false` 如实记录**：`trace-attribution-fix.json` 修复聚焦 kb 单条 trace（根 observation 已结束），chat 未回归；`deploy-verification.json:69` chat trace `f7e44efc…` `root_ended=false`（读回时点未结束），不冒充为成功，也不判为失败——属读回时点/归属边界，kb 链路 `root_ended=true`（`:41`）已满足四段 + 归属验证。

---

## 八、残留项（由主会话 / architect 收口，本角色不代做）

1. **spec 头部状态字段与「实施中」口径同步**：`spec:5` 为 `已确认`，而 `README.md:4` / `spec-status-changelog.md:3` 记「已确认（实施中）」、`spec:324` 与用户口径为「实施中」（`045-requirement-review.md:108`、`045-tech-review.md:110` 均已标注）。需收口时统一；**本轮禁止改 spec 状态为 `已完成`**。
2. **架构师签字**：本报告签字栏留空（`SDD-GATE-CHECKLIST.md:111`），由 `Task(architect)` 评审签署；留空期间不得把 spec 转 `已完成`。
3. **复盘落盘** `docs/sdd/retro/`（DoD `SDD-GATE-CHECKLIST.md:138`）、**`docs/sdd/spec-status-changelog.md` 追加 `实施中 → 已完成` 条目**（DoD `:134`）、**本地 `git commit`**（`task-08:53-54`，仅本地、不 push）均由主会话完成。
4. DoD 其它项（`SDD-GATE-CHECKLIST.md:130-138`：任务计划/README/task 文件状态一致、评审记录三行真实结论、变更日志逐行、引用路径真实存在）属主会话收口机械校验，本报告不代执行。
5. 本轮**不宣称部署门禁通过**：CI 流水线、覆盖率阈值、PR approval 均不在本角色验收范围，未做也未声称。

---

## 九、只读与纪律声明

- 本角色仅产出本报告 `docs/sdd/reviews/045-acceptance-review.md` 一份文档（外加系统强制进展日志）；**未改任何业务代码 / 测试 / spec 状态 / 评审文档**；未 `git commit` / `push` / 合 main / `reset` / `stash` / `clean`。
- 集成验收为**只读 curl 复核**（health / 任务列表 / 分页越界 / 无参），未触发 SSE 写链路、未重跑单端单测、未 mock 冒充 E2E；真实 SSE 写链路证据以已落盘 `deploy-chat-sse.txt` / `deploy-kb-sse.txt` 与 `deploy-verification.json` 为准。
- 进展日志：`.codebuddy/agent-logs/spec-045/task-08/tester/20261108-205202.md`。

---

## 十、开发主管 / 架构师签字栏

> Gate 5 规定：本栏由架构师评审子代理 `architect` 签署；**留空则不得把 spec 转 `已完成`**（`SDD-GATE-CHECKLIST.md:111`）。本报告 tester 结论为「通过」；签字栏已于 2026-11-08 由 `architect` 子代理签署（见下），本角色未代签。

- **tester 结论**：通过（2026-11-08，本报告第一、三、四节）
- **架构师签字**：**通过（Approve / 同意验收）** — 由架构师（评审/合并）子代理 `architect` 签署，同意本报告验收结论「通过」，替代原「待 architect 签字」占位。
- **签字日期**：2026-11-08
- **签署意见**：
  1. **结论与依据**：同意 `045-acceptance-review.md` 验收结论「通过」。依据：本报告第一节（通过）、第三节（11 项加固 11/11、Q10 四类证据 4/4、Q9 三项硬前置满足）、第四节（准备度 9/10、P0/P1=0、阻塞项无）、第五节（服务真实在线 + 只读跨端复核 PASS）；本人上一轮 `045-requirement-review.md` 与 `045-tech-review.md` 两份结论均为「通过」（P0=0/P1=0）；`runs/task-07/backend-review.md` 通过（P0=0/P1=0）；Gate 5（`SDD-GATE-CHECKLIST.md:106-112`）与 DoD（`:128-138`）签字前置已逐条核对，无缺失。
  2. **真实证据抽查**：`runs/task-08/full-regression.txt` 尾行 `4112 passed` / `PYTEST_EXIT=0`；`runs/task-08/waterfall.png` 存在（真实 PNG）；`runs/task-08/deploy-verification.json` 中 kb trace `220f5fb2…` 为 `observation_count=9` / `root_ended=true` —— 三条均落盘属实。
  3. **准备度 9/10 的第 10 项**：认可其未闭环项（架构师签字与状态台账闭环）属**流程待办，非实现/证据缺陷**；本签字即其中架构师签字环节的落地，其余（状态台账 / 复盘 / changelog / 本地 commit）由主会话随后补齐，不因此宣称 10/10。
  4. **已声明边界**：认可本报告第七节 **12 条已声明边界**（均非遗漏、非失败）如实成立，口径与两份评审一致。
  5. **合并纪律**：明确**不 push、不合 main**；`origin/main` 仍为 `1b26c76c`（工作分支 `feature/spec-045-evaluation-observability-hardening`，HEAD `f8106ff9`，改动未提交 / 未推送 / 未合并）。本签字未做任何 `git commit` / `push` / 合 main。
  6. **Spec 状态**：本签字仅补齐 Gate 5 签字前置；spec 状态**保持 `实施中`**，由主会话按 DoD（`SDD-GATE-CHECKLIST.md:130-138`）收口（台账 / 复盘 / changelog / 本地 commit）后再转 `已完成`，本角色不代改状态、不代做收口动作。

## 十一、收口后状态同步（主会话，2026-11-08）

- 第十节签字栏已由 `architect` 子代理签署「通过」。第四节准备度第 10 项与第八节残留项中
  「签字栏留空 / 待 architect 签字」是 tester 出具本报告**时点的描述**，现已签署，
  原文保留作历史记录，不回改准备度评分。
- 准备度 **9/10** 按架构师签署意见保留，不改写为 10/10；未闭环项属流程待办而非实现/证据缺陷。
- 主会话随后已按 DoD 补齐：`spec-status-changelog.md` 的 `实施中 → 已完成` 条目、
  `docs/sdd/retro/2026-11-08-spec045-evaluation-observability-closure.md` 复盘、
  spec 头部状态与任务计划 / README / HANDOVER 口径同步、本地 `git commit`
  （**不 push、不合 main**，`origin/main` 仍 `1b26c76c`）。
- 当前部署版本 `/api/health` 200（PID 65665）；最终全量回归
  `4112 passed, 2 skipped, 67 subtests`，`PYTEST_EXIT=0`；Q10 四类证据 4/4 齐全。
