# task-02 实现自测报告（frontend-dev）

- Spec：048 ｜ Task：02 页面级 tab：新建地图入口 tab 化
- 角色：frontend-dev ｜ 日期：2026-11-13
- 文件边界：仅 `frontend/literature-maps.js`、`frontend/literature-maps.css`；未改 index.html / 任何测试文件 / spec / 台账 / 其它视图
- 落地顺序：本次分派按 02→03 在同一 literature-maps.js 内串行落地避免互相覆盖；本报告记录 task-02 完成态。

## 1. 改动点（关键节点）

| # | 文件 | 节点 | 内容 |
|---|---|---|---|
| E1 | literature-maps.js | renderShell header | 删除 header 的 `newButton`（`literature-map-new-button`）创建 |
| E2a | literature-maps.js | header 之后 | createElement 动态生成 `#literature-map-main-tabs`（role=tablist）与 maps/create 两个 role=tab（data-map-tab / aria-controls / aria-selected / tabindex） |
| E2b | literature-maps.js | notice 之后 | 生成 `#literature-map-tabpanel-maps` / `-create` 两个 role=tabpanel（aria-labelledby），create 默认 hidden |
| E3 | literature-maps.js | createPanel 装配 | `listPanel.append(createPanel)` → `createTabPanel.append(createPanel)`；表单节点/h3/所有 id 逐字不变 |
| E4 | literature-maps.js | grid 组装 | `root.append(grid)` → `mapsTabPanel.append(grid)` |
| E6 | literature-maps.js | bindEvents 调用 | `bindEvents(newButton, refreshButton, closeDetail)` → `bindEvents(refreshButton, closeDetail)` |
| E7 | literature-maps.js | bindEvents 之前 | 新增 MAP_TAB_IDS / MAP_TAB_ORDER + `activateMapTab(name, focus)`；签名改为 `(refreshButton, closeDetail)` |
| E8 | literature-maps.js | bindEvents 内 | newButton toggle 块（含 `openMobilePanel('list', ...)`）替换为 tab click + 键盘 ←/→/Home/End/Enter/Space 绑定 |
| E9 | literature-maps.js | closeCreatePanel 末尾 | 追加 `activateMapTab('maps', true)`；清理逻辑（form.reset / 选项清理 / catalog 复位）不丢 |
| E10 | literature-maps.css | 文件末尾 | 新增 tablist/tab/tabpanel 样式 + ≤760px 规则，全部 `#literature-maps-view` 前缀 |

`Object.assign(refs, ...)`（现 1376 行）逐字未动。

## 2. 命令与真实退出码

- `node --check frontend/literature-maps.js` → `NODE_CHECK_EXIT=0`
- `grep -n "literature-map-main-tabs|literature-map-main-tab|literature-map-tabpanel" literature-maps.css` → 命中 590-600（新增 class 全部存在）
- `grep -n "innerHTML" literature-maps.js` → 0 命中

## 3. 三项自查

1. **新增/修改 class ↔ CSS 一一对应**：JS 新增 `literature-map-main-tabs` / `literature-map-main-tab` / `literature-map-tabpanel` 三个 class，均在 literature-maps.css 590-600 有定义；反向：CSS 新增选择器全部由 renderShell 的 createElement 渲染。✓
2. **资源版本号 `?v=N`**：按本次任务约束**不升版**（版本升版与 marker 属 task-04，见实现契约 C9 与「不改 ?v=N」）；`index.html` 未改动，`app.js` / `styles.css` 未改动，无需同步。如实记录为合规，非遗漏。
3. **XSS**：新增节点全部走 `createElement`（第三参 textContent）/`setAttribute` 静态字符串；tab 文本「地图」「新建地图」为字面量；无 `innerHTML`、无拼接用户输入。✓

## 4. C1–C3 逐条结论

- **C1 ✓**：tab DOM 全部在 `renderShell()` 内 createElement 生成，位置在 `.literature-map-header` 之后、`.literature-map-grid`（现为 mapsTabPanel 子节点）之前；`role=tablist` / 两个 `role=tab`（data-map-tab、aria-controls、aria-selected、tabindex）/ 两个 `role=tabpanel`（aria-labelledby）齐全；未改 index.html、未动深度研究 tablist。
- **C2 ✓**：闭包内新建 `activateMapTab(name, focus)`，只切 `hidden` / `aria-selected` / `tabIndex` + 可选 `focus`，并同步 `state.createPanelOpen` 与 `createPanel.hidden`（与 tab 态同源）；**不重建面板**，refs/表单节点复用，tab 往返保留已填值；键盘 ←/→/Home/End（含 ↑/↓/Enter/Space）切换并同步 `tabIndex`；未跨文件调用 `activateResearchTab()`、未抽公共函数、未改 `research-tasks.js`。
- **C3 ✓**：createPanel 迁入 `#literature-map-tabpanel-create`，表单节点 / `h3`「新建主题地图」/ 所有 id（1081-1151）/ `Object.assign(refs,...)` 指针逐字不变；grid 整体进 `#literature-map-tabpanel-maps`；取消（cancelButton）、建图成功（createMap→closeCreatePanel）、离开视图（setActive(false)→closeCreatePanel）三个调用点统一由 closeCreatePanel 末尾 `activateMapTab('maps', true)` 切回并聚焦；回到 maps tab 时 createTabPanel.hidden=true 且 createPanel.hidden=true，`#literature-map-create-panel.is_hidden()` 断言成立；清理逻辑不丢。

## 5. 风险与遗留

- 刷新按钮图标化（C4/C5）、图标 CSS 与 `@keyframes` 的 `#literature-maps-view` 前缀、图标按钮 ≥44px 触摸目标属 task-03，本报告未覆盖；最终态以 task-03 报告为准。
- `?v=N` 冻结断言、marker、测试断言同步（C6/C7/C8）属 task-04，不在本次分派范围。
- 新建入口已不再触发 `openMobilePanel('list', ...)`；未改动 `openMobilePanel` / `closeMobilePanel` 定义本身，窄屏抽屉逻辑保留给其它入口。
