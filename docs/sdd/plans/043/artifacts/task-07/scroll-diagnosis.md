# Task07 真实详情抽屉滚动 P1 诊断

## 结论

真实详情滚动在带自然间隔的 CDP 触摸序列中 **PASS**；此前 BLOCK 是触控注入时序过密导致的测试复现假阴性，不是产品 CSS 或 pointer handler 阻止。窄复测等待分析 GET 完成后，记录了触摸前后 scrollTop、DOM mutation 时间、pointer/touch 事件和同页临时独立滚动容器对照；未观察到触摸期间异步重绘，也未观察到产品滚动失败。

## 真实失败证据

- 候选提交：`82c816f`（地图前端 JS v12/CSS v8）。
- 页面：`http://127.0.0.1:8000/#literature-maps-view`；地图 `0baabeae7268429c9f7e4de8098ae1d0`；节点 `21041260a5394f42891b020128fa60fa`。
- 环境：授权提升权限的 Chromium + Playwright/CDP，`has_touch=True`、`is_mobile=True`、375×820；不是物理真机。
- 详情几何和计算样式：`x=23.5,y=62,width=350.5,height=757`；`scrollTop/scrollHeight/clientHeight=0/3075/757`；`overflow-y=auto`；`touch-action=pan-y`。
- 起点命中：`elementFromPoint(center, bottom-20)=literature-map-document-link`，即详情滚动容器内真实内容，不是 SVG、遮罩或页面空白。
- 轨迹：同一详情页面经 CDP `touchStart → touchMove(-120) → touchMove(-100) → touchEnd`；结束后仍为 `scrollTop=0`。
- 截图：[live-375-detail-scroll-repro.png](screenshots/live-375-detail-scroll-repro.png)。完整运行时记录见 [browser-e2e.md](browser-e2e.md) 的 2026-10-21 真实服务复测段。
- 边界：该复现未发送 analysis POST、未改 group/map/viewport；前置列表、节点点选、viewport pan/pinch 保存重开均已在同一真实回合通过。本轮使用主会话已托管的 8000 服务，未启动/停止服务，也未重复整套 smoke。

## 窄化复测（2026-10-21，提升权限 Playwright，仅 375px）

- 真实页面同一地图/节点；分析 GET `200` 在相对测试开始 `2570.9ms` 返回。等待历史 v1/v2 出现并额外等待 500ms 后再触摸。
- MutationObserver 仅记录 `2427.9ms`、`2431.6ms`、`2569.6ms` 三批详情重绘，均发生在触摸前；触摸过程中没有 mutation，且 `#literature-map-detail` 元素身份保持不变。
- 详情触摸序列加入 120ms 间隔：`touchStart(y=801)` → 120ms → `touchMove(y=711)` → 120ms → `touchMove(y=611)` → 120ms → `touchEnd`。`scrollTop` 为 `0 → 75 → 175 → 175`（结束后延迟 600ms 仍为 175）；记录到 `pointerdown/pointermove/pointercancel` 与 `touchstart/touchmove/touchend`，其中 `pointercancel` 是浏览器把手势交给原生滚动的正常交接。
- 同页临时独立容器（`overflow-y:auto`、`touch-action:pan-y`，测试后移除）使用同样带间隔的 CDP 输入，`scrollTop=0 → 165`，证明 Chromium/CDP 输入管线确实能驱动原生滚动。
- 详情起点仍命中 `.literature-map-document-link`；详情计算样式仍为 `overflow-y:auto`、`touch-action:pan-y`、`scrollHeight=3075/clientHeight=757`。

结论：之前的零间隔 `touchStart → touchMove → touchMove → touchEnd` 不能作为真实手机触摸时序；事件虽进入输入管线，却没有给 Chromium 足够时间完成滚动手势接管。该 P1 不需要产品 CSS/JS 滚动修复，最小修正应落在真实浏览器验收脚本：在触点移动之间加入可复现的短等待，并在第一段 move 后直接断言详情 `scrollTop` 增长；不要用 `element.scrollTo` 代替触控。

## CSS / 事件定位

1. 移动详情规则位于 `frontend/literature-maps.css:181-191`：详情面板固定在右侧且 open 时 `pointer-events:auto`；详情内容为 flex 子项，`min-height:0`、`overflow-y:auto`、`touch-action:pan-y`、`-webkit-overflow-scrolling:touch`。真实 `scrollHeight > clientHeight` 与 computed style 与此一致。
2. SVG 图谱的 `touch-action:none` 位于 `frontend/literature-maps.css:68-70`，只作用于 `#literature-map-svg`，不是详情面板祖先；详情上方命中点也证明遮罩没有盖住触点。
3. `frontend/literature-maps.js:798-813` 的 pointerdown/move/up/cancel 与 click 监听只挂到 `refs.svg`；详情容器及其父级没有 touch/pointer listener，也没有 `preventDefault`。因此当前证据不支持“产品 pointer 事件把详情触控转成地图 pan”的解释。
4. 触摸起点在容器下部、两次移动向上，方向和目标符合原生垂直滚动；不能把失败简单归因于测试选到了链接或把轨迹方向走反。`elementFromPoint` 命中 `.literature-map-document-link` 仍属于详情滚动内容。
5. 全局 `frontend/styles.css` 的移动规则只对 `body.mobile-nav-is-open` 设置页面级 `overflow:hidden`，并对 `.main-area` 设置 `overflow-x:hidden`；没有给 `#literature-maps-view`、详情面板或详情滚动容器设置 `overflow-y:hidden`/`touch-action:none`。全局 `document` pointerdown 仅用于浮动菜单外点击关闭，也没有对详情触控调用 `preventDefault`。

## 已排除：异步详情重绘归零

`selectNode()`（`frontend/literature-maps.js:2435-2467`）先渲染论文字段，随后等待 `loadNodeAnalyses()`；分析请求完成后，`loadNodeAnalyses()`（`:2707-2721`）再次调用 `renderNodeDetail(state.selectedNode)`。`renderNodeDetail()`（`:2788-2869`）首先对同一个 `#literature-map-detail` 执行 `replaceChildren()`。

虽然 `loadNodeAnalyses()` 完成后会再次调用 `renderNodeDetail()`/`replaceChildren()`，本次窄复测已在分析 GET 完成、且额外等待 500ms 后触摸；MutationObserver 显示触摸期间没有重绘，且详情元素身份未变，滚动在第一段 move 即从 0 增至 75。因此本次真实 BLOCK 不能归因于异步分析重绘。此前报告中的“重绘归零”应视为已排除假设，不再建议添加 scroll 恢复逻辑。

## 最小修复方案（待主会话授权）

无需产品滚动修复。若要修验收，保持真实 CDP/Playwright 输入，给 `touchStart` 与连续 `touchMove` 留出短暂时间窗口，并在滚动中读取 `scrollTop`；可保留 `pointercancel` 作为原生滚动接管证据。禁止用 `element.scrollTo` 冒充触控成功。

## 验收边界

- 本窄复测可将“375px 详情真实触控滚动”标记为 PASS；它只覆盖该单项，不替代 390/桌面/完整 Task07 smoke，也不把 fixture 结果当真实 API 证据。
- 真实失败截图和原始运行时数值已存在；无代码编辑、无服务启动/停止、无后端/full/commit。
- 不需要产品修复；主会话可在同一候选上按带间隔的真实触控序列补记该单项，然后再决定是否执行后续 390/桌面回归。本轮未修改业务代码。
