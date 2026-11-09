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
