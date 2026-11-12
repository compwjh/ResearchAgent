# Spec-048 · task-04 · frontend-dev 实施报告（版本号 / marker / 静态契约同步）

| 项 | 值 |
|---|---|
| 角色 | `frontend-dev`（ECC tdd-guide 精神，测试/契约驱动） |
| 任务 | task-04 的版本号 / marker / 静态契约同步部分（本次分派范围） |
| 日期 | 2026-11-13 |
| 依据 | spec-048 边界 1–10、Gate 2 强制约束 C6 / C7 / C8、`task-04-contracts-and-e2e.md`、`048-tech-review.md` §六 |
| 文件边界 | 仅 7 个指定目标文件；**未改** `literature-maps.js` / `literature-maps.css`（task-02/03 已完成并读回校验）、`backend/**`、其它视图、spec、台账 |
| 落地方式 | 4 批、每批 ≤2 文件、串行；每批改完 `Read` 回读确认再进入下一批 |

## 一、4 批逐批改动摘要

### 批 1 · 版本与 marker（2 文件，均回读确认）
| 文件 | 改动点 | 回读结论 |
|---|---|---|
| `frontend/index.html` | `:11` `literature-maps.css?v=34→v=35`；`:903` `literature-maps.js?v=47→v=48`；`:917` 之后追加两条 `Spec048 compatibility marker` 纯属性片段（`src="/assets/literature-maps.js?v=47"` / `href="/assets/literature-maps.css?v=34"`） | 已回读：live `:11`/`:903` 为新值；`:918-919` marker 位于末尾注释区、不含 `<script` / `<link` 字面串、不在 `<head>`；`:905` `app.js?v=77` 与 `:8` `styles.css?v=77` **未动** |
| `tests/frontend/fixtures/literature_map_component.html` | `:8` `literature-maps.css?v=34→v=35`；`:1135` `literature-maps.js?v=47→v=48` | 已回读：两处均为新值；`:7` `styles.css?v=62` 未动 |

**marker 置于文件末尾是 C8 的关键**：`test_frontend_map_groups_exports.py:54-55` 的 `re.findall(...)[-1] == "47"/"34"` 精确断言依赖旧值为最后一次出现；10+ 处 `in INDEX` 冻结断言（`contract.py:28-29`、`groups:18-19`、`mobile:93-95`、`task_d:192-193`、`button_affordance:201/203`、`task_j`、`memory_return_global`、`expansion`、`map_analysis`）靠两条 marker 继续通过。marker 是 `literature-maps.*` 旧值，不会污染 `readability.py` 取首个 `styles.css?v=` 的 `active_version` 语义（首个仍为 `:8` 的 `v=77`）。

### 批 2 · 两个核心契约测试（2 文件，均回读确认）
| 文件 | 改动点 |
|---|---|
| `tests/frontend/test_frontend_map_header_actions_readability.py`（C6/C8） | `HEADER_ACTION_IDS` 移除 `literature-map-new-button`；`MAP_CSS_VERSION = 34→35`（C8：该常量参与 CSS 版本断言）；`test_four_header_buttons_keep_id_text_and_hidden_contract` 的 `expected` 删 new 与旧文字刷新两条、刷新按钮改判为「两参数 `createElement` 无可见文字 + `refreshButton.setAttribute('aria-label', '刷新状态')` + 旧 `'secondary-button btn-outline', '刷新状态'` 写法禁止」三条真实源码字符串断言；`test_header_button_event_bindings_are_unchanged` 的 `pairs` 移除 `newButton`、保留 `refreshButton`。`APP_JS_VERSION=74` / `STYLES_VERSION=75` 逐字不动 |
| `tests/frontend/test_frontend_literature_map_contract.py`（C7） | 新建地图入口定位 `get_by_role('button', name='新建地图')` → `get_by_role('tab', name='新建地图')`，共 7 处（`:140/:249/:263/:277/:291/:310/:320`，含任务点名的 `:277`）；`:28-29` 的 `in INDEX` 冻结断言与 `:270,:284` 的 `#literature-map-create-panel.is_hidden()` 断言逐字不动；`:278-285` 填写 / 提交 / 回 tab 流程不变 |

三态（`hidden`）/ 尺寸（桌面 36px、移动端 44px）/ 对比度（`#4a4560` on `#fff` ≈ 9.09:1）相关函数（`test_header_action_buttons_*` / `test_mobile_breakpoint_*`）**逐字未改**；不改松 / 不删 / 不 skip / 不 xfail。

### 批 3 · fixture 版本断言（2 文件，均回读确认）
| 文件 | 改动点 |
|---|---|
| `tests/frontend/test_frontend_map_groups_exports.py` | `:52-53` fixture 内版本串 → `v=35` / `v=48`；`:54-55` `re.findall[-1]` 精确断言与 `:18-19` `in INDEX` 冻结断言**不动** |
| `tests/frontend/test_frontend_map_mobile_contract.py` | `:97-98` fixture 内版本串 → `v=48` / `v=35`；`:93-95` `in INDEX` 冻结断言**不动** |

### 批 4 · 新增静态契约测试（1 文件，heredoc 创建 + Read 回读）
`tests/frontend/test_literature_map_tabs_and_refresh_icon.py`（221 行 / 12 个测试函数，**按能力命名、无 spec/task 编号**，纯静态、不依赖浏览器）。断言覆盖：
- live 版本精确值 `js?v=48` / `css?v=35`；两条 marker 有且仅有、在 HTML 注释内、不含 `<script` / `<link` 字面串、位于 `</head>` 之后；旧值 `in INDEX` 与 `re.findall[-1]=47/34` 兼容；首个 `styles.css?v=` 仍为 77；
- tab DOM：`role="tablist"` / `role="tab"` / `role="tabpanel"` / `aria-controls` / `aria-labelledby` / `data-map-tab`（11 项逐字）、默认 maps `aria-selected="true"`、`createTabPanel.hidden = true`；
- `activateMapTab`：用 `_function_body()` 按花括号配对**限定函数体内**只改 `aria-selected` / `tabIndex` / `hidden` + `focus`，且体内无 `replaceChildren` / `createElement` / `innerHTML`（避免被 `closeCreatePanel` 里合法的 `replaceChildren` 误伤）；`closeCreatePanel` 切回 maps tab；
- 刷新按钮：`id='literature-map-refresh-button'`、两参数 `createElement('button', 'icon-button literature-map-tool')` 无文字、`tools.append(refreshButton)` 成块、`aria-label="刷新状态"`、`literature-map-refresh-icon` span、事件仍绑 `refreshButton`；源码中不得再出现 `createElement('button', 'secondary-button btn-outline', '刷新状态')` 或 `'新建地图'` header 文字按钮；
- CSS：`.literature-map-refresh-icon` + `::before/::after`、`is-spinning`、`@keyframes literature-map-refresh-spin`、`prefers-reduced-motion`、`:disabled`、移动端 ≥44px，且所有图标规则选择器带 `#literature-maps-view` 前缀；tab 样式同样限定作用域；
- header 其余 5 个作业按钮（continue / refresh-preview / open-saved-preview / stop-job / retry-job）id 与 `.hidden = true` 仍在。

断言全部逐字比对真实源码、可失败、无恒真断言；不 skip / 不 xfail。

## 二、Gate 2 强制约束逐条结论

- **C6 — 通过**。`HEADER_ACTION_IDS` 移除 new；`expected` 删 new、刷新按钮改判「无可见文字 + `aria-label="刷新状态"`」；`:249-252` 旧 `secondary-button btn-outline`/`'刷新状态'` 逐字正则按新契约改写为三条真实源码断言；`pairs` 移除 `newButton`、保留 `refreshButton`；三态 / 尺寸 / 对比度约束与 `APP_JS_VERSION` / `STYLES_VERSION` 逐字保留。命令 2 全绿验证。
- **C7 — 通过（含一处需主会话知悉的范围决策）**。任务与 tech-review 点名 `:277`；实测同文件有 **7 处**同一定位（`:140/:249/:263/:277/:291/:310/:320`），且 `:132-295` 属**同一测试函数**——其前置入口 `:140/:249/:263` 若不同步为 tab，`:277` 段永不可达，与「`:278-285` 填写 / 提交 / 回 tab 流程保持可跑」直接冲突；`:310/:320` 在另一浏览器函数内同性质。故按 C7 本质（入口 `role` 变更 → 定位同步）统一同步 7 处，**严格不碰** `:28-29` 冻结断言与 `:270,:284` 隐藏断言。命令 2 无 skip 全绿（浏览器用例真实跑通）反证该同步是流程可跑的必要条件。若主会话坚持「严格只改 `:277`」，可回退其余 6 行，但会令浏览器用例红灯。
- **C8 — 通过**。live `js?v=47→48` / `css?v=34→35`；两条旧值纯属性 marker 追加到 `index.html` 末尾注释区（不放 `<head>`、无标签字面串）；核对 `MAP_CSS_VERSION=34` 确参与 CSS 版本 / fixture 断言，已同步 `35`；`app.js?v=77` 与 styles.css 版本号不动；fixture 与 `groups:52-53` / `mobile:97-98` 精确断言同步到新值；`groups:54-55` 的 `re.findall[-1]` 靠末尾 marker 兼容。附加自查逐条验证 4 类冻结断言旧值仍 `in INDEX`。

## 三、frontend-dev 三项自查（改完必做）

1. **class ↔ CSS**：`literature-map-main-tabs` / `literature-map-main-tab` / `literature-map-tabpanel` / `literature-map-refresh-icon` / `is-spinning` / `literature-map-tool` 均在 `literature-maps.js` 被渲染且在 `literature-maps.css` 有定义（附加自查 + 批 4 断言双确认）。本次未新增/修改任何 class。
2. **资源版本号**：改了 `literature-maps.js` / `literature-maps.css`（task-02/03）后，`index.html` 的 `?v=N` 已精确升为 `v=48` / `v=35`；`app.js?v=77` / `styles.css?v=77` 未动；Grep 复核 `:8/:11/:903/:905/:918/:919` 一致。
3. **XSS / innerHTML**：`frontend/literature-maps.js` 中 `innerHTML` 出现 **0 次**（Grep + 附加自查 + 批 4 断言）；用户输入沿用 `textContent` / `input.value` 口径，本次未引入任何 `innerHTML` 拼接。

## 四、验证命令 / 真实退出码 / 通过数

| # | 命令（统一 `cd /Users/wjh/ResearchAgent` 后执行） | 结果 | EXIT |
|---|---|---|---|
| 1 | `node --check frontend/literature-maps.js` | 无输出（语法通过） | **0** |
| 2 | `.venv/bin/python -m pytest -q` 指定 5 文件（readability / contract / groups_exports / mobile_contract / 新增 tabs_and_refresh_icon） | **44 passed in 28.59s**，无 skipped / failed | **0** |
| 3 | `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | **0** |
| 附 | 附加 Python 自查（class↔CSS / `?v=N` / 无 innerHTML / 4 类冻结断言旧值 / `re.findall[-1]` / fixture 新值） | `SELF_CHECK_OK` | **0** |
| 附 | 新测试文件 `ast.parse` 语法自检 | `PY_SYNTAX_OK` | **0** |

环境说明：本 shell 默认 cwd 为 `/`，相对 `.venv/bin/python` 会返回 127；所有命令均 `cd` 到项目根或使用绝对路径执行，退出码为真实值。node `v26.7.0`、pytest `9.1.1`。

## 五、风险与遗留

1. **C7 范围决策**（见 §二）：任务点名 `:277`，实测 7 处并按「流程可跑」统一同步；已在日志与本报告透明披露，请主会话裁决是否保留 6 行伴随改动。
2. **验证覆盖范围**：任务指定的 5 文件全部真实通过；另有 6 个含 `in INDEX` 冻结断言的文件（`memory_return_global` / `task_j` / `task_d` / `button_affordance` / `expansion` / `map_analysis`）**未纳入本次 pytest 5 文件**，但已通过附加静态自查逐条验证 marker 旧值可达（同一 `in INDEX` 子串机制）；未逐一跑它们的全套用例。
3. **不在本次分派范围**：真实 Chromium E2E（桌面 + ≤760px 窄屏）、部署验证（`/api/health`、资源 200）、`frontend-reviewer` / `frontend-tester` 评审签字、spec 状态收口与复盘，属 task-04 后续角色与主会话；本次仅落地契约与版本同步。
4. 按分派边界**未执行任何 git / push / 合并**操作。
5. 未改动 `literature-maps.js` / `literature-maps.css`（task-02/03 成果读回校验通过）、`backend/**`、其它视图、spec 与状态台账。

## 六、改动文件清单（7 个目标文件 + 2 个产出文件）

| 文件 | 类型 | 当前行数 |
|---|---|---|
| `frontend/index.html` | 修改（3 处：2 版本 + 2 行 marker） | 921 |
| `tests/frontend/fixtures/literature_map_component.html` | 修改（2 处版本串） | 1138 |
| `tests/frontend/test_frontend_map_header_actions_readability.py` | 修改（C6 + C8 常量） | 318 |
| `tests/frontend/test_frontend_literature_map_contract.py` | 修改（C7，7 处定位） | 425 |
| `tests/frontend/test_frontend_map_groups_exports.py` | 修改（2 行 fixture 断言） | 126 |
| `tests/frontend/test_frontend_map_mobile_contract.py` | 修改（2 行 fixture 断言） | 535 |
| `tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | **新增**（静态契约测试） | 221 |
| `docs/sdd/plans/048/runs/task-04/implementation.md` | 产出（本报告） | — |
| `.codebuddy/agent-logs/spec-048/task-04/frontend-dev/20261113-024739.md` | 产出（进展日志） | — |
