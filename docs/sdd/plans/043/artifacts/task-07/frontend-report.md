# Spec043 Task07 前端交接报告：手机地图适配

## 状态

**前端实现可交独立复审（PASS_WITH_LIMITATIONS）**。本轮只修改文献地图前端、前端契约夹具/测试及本 Task 报告；未修改 `backend/**`、provider、配置或部署文件，未运行后端 pytest，未启动服务，未读取 secrets，未提交或推送。

Task05 的全文 KB partial 限制保持原状；本适配没有新增分析调用、下载器或移动端后端，也不把合成夹具验证描述为真实 API 验收。

## 实际改动

- `frontend/literature-maps.js`
  - 在同一地图组件内增加移动端列表/筛选抽屉、详情抽屉、遮罩和明确的打开/关闭按钮；桌面继续使用原三栏布局。
  - 移动端抽屉关闭后异步恢复列表入口或节点的焦点；节点重绘后按 `data-node-id` 找回新的 SVG 节点引用。
  - 触控手势区分单指画布平移/节点点选与双指中心缩放；缩放沿用 `0.35–2.8` 上下限。`pointercancel`、窗口失焦和页面隐藏时清理多指/捕获状态；拖动不触发节点点击。
  - 图谱 SVG 保持既有 API、节点布局、关系开关、定位、创建、预览确认和分组逻辑；手机只改变呈现和输入边界。
- `frontend/literature-maps.css`
  - 760px 以下切换为图谱主画面，列表与详情以固定抽屉显示；抽屉/列表/详情内容使用 `touch-action: pan-y` 与独立滚动，图谱 SVG 才使用 `touch-action: none`。
  - 375/390px 下限制主体横向溢出，长内容在抽屉内部滚动，并保留安全区与 reduced-motion 规则。
- `frontend/index.html`、`tests/frontend/fixtures/literature_map_component.html`
  - 同步资源缓存版本至 `literature-maps.js?v=12`、`literature-maps.css?v=8`；移动夹具补 viewport 元标签。
- `tests/frontend/test_frontend_map_mobile_contract.py`
  - 新增能力命名契约测试，覆盖 375/390px 授权 Chromium 触控模拟、双指缩放与取消清理、抽屉焦点/滚动、节点点选和 1440px 桌面边界。
- 既有地图前端契约测试同步资源版本断言；未改既有 API shape。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（授权 Chromium） | 退出码 0；3 passed（静态契约 + 375px + 390px） |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 退出码 0；20 passed |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

## 前端自查

- class/CSS：通过；新增移动入口、抽屉、遮罩和手势边界均在 `#literature-maps-view` 下，列表/详情滚动规则未施加到整页。
- DOM/XSS：通过；模块仍无 `innerHTML`，节点、标题、摘要、状态和错误沿用 `textContent`/受控属性写入。
- 资源版本：通过；生产 `index.html`、合成 fixture 及既有地图契约断言均为 JS v12/CSS v8。
- 桌面回归：授权 Chromium 1440px 检查保持 grid 三栏和节点详情可见；Task05/06 的分析、扩展、分组与导出精准回归 20 项通过。

## 限制与下一步

- 浏览器证据来自本地合成 API fixture；它证明前端 DOM/API 接线和触控事件边界，不替代真实地图 API、真实来源/provider、真实分组/导出或真实作业状态验收。
- 本轮验证了 375px 与 390px Chromium 触控模拟，不是真机；未宣称 iOS/Android 真机通过。
- 未运行后端 pytest、全量回归、真实服务部署或 Task08 收口门禁；Task05 全文 KB partial 阻塞独立保留。
- 下游应由 `frontend-reviewer` 复核 DOM/CSS/XSS/资源版本/手势竞态，由 `frontend-tester` 复核本报告与浏览器证据；Task08 再接真实 API E2E、全量回归和部署。

## 交接产物

- 前端报告：`docs/sdd/plans/043/artifacts/task-07/frontend-report.md`
- 浏览器验证：`docs/sdd/plans/043/artifacts/task-07/browser-verification.md`
- 前端开发日志：`.codebuddy/agent-logs/spec-043/task-07/frontend-dev/20261021-011310.md`
- 能力测试：`tests/frontend/test_frontend_map_mobile_contract.py`

## 复审修复追加（2026-10-21）

独立 frontend review 将以下两项标为 P1 并 BLOCK：正常双指结束没有保存最终 viewport；浏览器测试只用页面内 `dispatchEvent`，未覆盖真实单指平移、pinch 边界/切换、抽屉滚动、失焦清理和桌面鼠标拖拽。本次在原范围内集中修复并追加证据：

- `frontend/literature-maps.js`：pinch 的首个 `pointerup` 即结束手势、基于最后一次 `updatePinch()` 的真实 `state.view` 调用一次 `scheduleViewSave()`；不为剩余触点建立单指拖动基线，避免双指转单指跳变或错误坐标保存。桌面节点拖拽缺少缓存位置时回退到真实节点位置，保留三栏拖拽能力。
- `tests/frontend/test_frontend_map_mobile_contract.py`：通过授权 Chromium CDP `Input.dispatchTouchEvent`（触控模拟器，非真机）覆盖单指平移、pinch 中心锚定与 `0.35–2.8` 上下限、双指转单指不跳变、失焦清理；使用真实触摸滚动覆盖分组/详情抽屉；使用真实 `page.mouse` 覆盖桌面节点拖动并断言保存位置。
- `tests/frontend/fixtures/literature_map_component.html`：增加 `?mobile-long` 长摘要/多分组夹具以验证抽屉实际滚动；资源版本同步至 `literature-maps.js?v=12`，CSS 保持 v8。

复审后真实命令与结果：

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（授权 Chromium） | 退出码 0；6 passed（静态、375/390 抽屉/单指、pinch、抽屉滚动、桌面鼠标拖拽），10.77s |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 退出码 0；20 passed |
| `git diff --check -- frontend tests/frontend` | 退出码 0（与上方回归命令串联执行） |

复审限制仍保持：Chromium 触控是精准事件模拟夹具，不是真机；fixture 使用合成 API，不替代真实 API E2E；未运行后端 pytest、全量回归、部署或提交。Task05 全文 KB partial 既有阻塞未改门禁。

## P1 修复追加：详情关闭按钮被全局移动导航遮挡（2026-10-21）

主会话授权后，仅处理真实 375/390px 地图详情抽屉的关闭可达性；未修改滚动逻辑。先将真实全局 `#mobile-nav-toggle`（含 `项目与会话` 子节点）及生产 `styles.css` 接入现有 Chromium fixture，并执行无 `force` 的红灯回归：退出码 1，Playwright 明确报告 `<span>项目与会话</span>` 拦截 `#literature-map-detail-close` 的 pointer events。

最小修复如下：

- `frontend/literature-maps.js`：地图移动抽屉打开时设置 `body.literature-map-drawer-open`；列表/详情均关闭、离开地图视图或非移动视口时清除，避免全局导航永久失活。
- `frontend/literature-maps.css`：地图 backdrop 使用 z-index 1060、列表/详情抽屉使用 1070，明确高于全局导航 backdrop/sidebar 的 1040/1050。
- `frontend/styles.css`：仅在该 body 状态下隐藏并禁用 z-index 1100 的全局导航按钮；地图抽屉关闭后按钮恢复可见、可交互，未改变全局导航默认层级。
- `frontend/index.html`、fixture 与既有地图契约：实际资源版本升至 `styles.css?v=58`、`literature-maps.js?v=13`、`literature-maps.css?v=9`。DOM/XSS 自查仍通过：地图模块无 `innerHTML`。

修复后同一无 `force` 回归在 375px 通过；随后 375/390px 抽屉、pinch、滚动、桌面边界及受影响地图契约共 27 项通过。该修复不涉及 backend/provider/服务启停，也未修改旧的详情滚动诊断结论（零间隔 CDP 触控为 harness 假阴性）。

| 命令 | 结果 |
|---|---|
| 授权 Chromium：`pytest tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_detail_close_is_not_blocked_by_global_navigation -q`（修复前） | 退出码 1；真实全局导航子节点拦截关闭按钮 |
| 授权 Chromium：同一测试（修复后） | 退出码 0；1 passed |
| 授权 Chromium：`pytest tests/frontend/test_frontend_map_mobile_contract.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py -q` | 退出码 0；27 passed |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

## P1-01/P2 修复追加：视口切换清理与移动抽屉不透明背景（2026-10-21）

独立 frontend-reviewer 复现了上一轮 P1：详情抽屉打开后切到桌面并 `setActive(false)`，旧实现因 `!isMobileViewport()` 提前返回，只清 body class，留下 `.is-open`、`aria-hidden="false"`、`hidden=false`、backdrop 和 `state.mobile`；仅跨 760px resize 也会复现。新增两条无 `force` Chromium 回归先以退出码 1 红灯确认该残留。

本轮修复：

- `frontend/literature-maps.js`：`closeMobilePanel`/`closeAllMobilePanels` 不再依赖当前 viewport；无论桌面或移动都移除 panel open class、恢复 `aria-hidden`、隐藏详情 panel/backdrop、清零列表/详情状态与 body class。仅在仍为移动视口时恢复焦点，避免桌面切换异步抢焦点。
- `frontend/literature-maps.js`：增加 resize 监听；跨到桌面断点时统一调用 `closeAllMobilePanels(false)`，返回移动端后必须重新点开抽屉。
- `frontend/literature-maps.css`：移动列表/详情抽屉覆盖为不透明 `#fff`，桌面主题未改变；资源版本升至 `literature-maps.css?v=10`（JS13、styles58 保持）。
- `tests/frontend/test_frontend_map_mobile_contract.py`：新增“375→desktop→inactive→375→active”和“仅 resize 往返”回归，均用正常 click/tap；增加移动详情抽屉不透明背景断言。

验证结果：新增切换/关闭/背景窄回归 3 passed；同范围地图前端集合共 29 passed。未运行 backend/full、未启动或停止服务、未提交。

| 命令 | 结果 |
|---|---|
| 授权 Chromium：两条新增视口清理测试（修复前） | 退出码 1；2 failed，确认 desktop 分支残留 panel/state/backdrop |
| 授权 Chromium：新增两条清理测试 + 全局导航关闭测试（修复后） | 退出码 0；3 passed |
| 授权 Chromium：地图 mobile + literature-map 相关五个前端测试文件 | 退出码 0；29 passed |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend docs/sdd/plans/043/artifacts/task-07/frontend-report.md` | 退出码 0 |

## P1-02 修复追加：桌面 resize 保留详情、移动生命周期分流（2026-10-21）

最新独立 review 发现上一轮 resize handler 对所有非移动 viewport 都调用完整 `closeAllMobilePanels(false)`，因此普通 1440→1280 resize 也把已选桌面详情设为 `hidden=true`、`aria-hidden=true`。该路径与移动抽屉清理语义混用，违反桌面三栏原有详情合同。

本轮集中修复：

- `frontend/literature-maps.js`：增加 `state.mobileViewport`，resize 只在断点状态真正变化时处理；desktop→desktop 不再关闭任何详情。
- 移动→桌面且 view 仍 active 时，仅移除移动 drawer class、backdrop、mobile state 与移动 `aria-hidden`，保留已选桌面详情的 `hidden`/可见性；desktop→mobile 会重新收口移动 panel，避免旧 drawer 自动弹出。
- `setActive(false)` 仍走完整清理；resize 事件若在 inactive view 后到达也走完整清理，避免异步事件把 `aria-hidden` 恢复成桌面语义。重新 `setActive(true)` 和桌面 `selectNode` 会恢复桌面 panel 的可访问性。
- `tests/frontend/test_frontend_map_mobile_contract.py`：新增 1440→1280 详情仍可见且 `aria-hidden` 非 true 的回归；更新 mobile→desktop→inactive→mobile 残留清理断言，并保留普通 mobile close/globalnav 回归。

根因修复后，关键生命周期测试 3 passed；同范围地图前端回归 30 passed。此前第一次整组运行暴露了一个 inactive resize 事件顺序竞态（1 failed、29 passed），已通过 `state.active` 分流修正后重新验证。未运行 backend/full、未启动或停止服务、未提交。

| 命令 | 结果 |
|---|---|
| 授权 Chromium：desktop detail、mobile→desktop→inactive→mobile、desktop resize round-trip | 退出码 0；3 passed |
| 授权 Chromium：地图 mobile + literature-map 相关五个前端测试文件 | 退出码 0；30 passed |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend docs/sdd/plans/043/artifacts/task-07/frontend-report.md` | 退出码 0 |

## P1-03 修复追加：全局导航打开态 close/toggle 触控可达性（2026-10-21）

最新 frontend review 在真实 375px 复现了第二个全局导航遮挡：打开 `#mobile-nav-toggle` 后，固定的 z1100 toggle 覆盖 sidebar 内的 `#mobile-nav-close`；450ms 后仍无法正常 `tap()`，Playwright 明确报告 toggle 拦截 pointer events。地图详情滚动诊断保持原结论，不在本轮改动。

本轮仅在 `frontend/**` 与对应前端契约测试内修复：

- `frontend/styles.css`：增加 `body.mobile-nav-is-open .mobile-nav-close` 打开态规则，将 close 控件在 sidebar 内下移 44px，避开固定 toggle 的命中区域；toggle 保持原 z1100 和位置，因此 close 与 toggle 二次关闭两条正常触控路径均保留，Escape/backdrop 逻辑及地图 drawer 的 1060/1070 优先层级不变。
- `frontend/index.html`、`tests/frontend/fixtures/literature_map_component.html`：静态资源版本升至 `styles.css?v=59`。fixture 补齐生产导航的 toggle、`aria-controls/aria-expanded`、close、sidebar、backdrop DOM，并按 `app.js` 的 `mobileDrawerState`、open/close、焦点恢复、Escape/backdrop/sidebar 事件契约复用最小夹具逻辑；桌面 fixture 仅隐藏导航 sidebar，不改变移动生产样式。
- `tests/frontend/test_frontend_map_mobile_contract.py`：新增按能力命名的 375/390 回归，使用正常 `.tap()`（无 `force`）覆盖 close button、toggle 二次关闭、Escape、backdrop，以及关闭后地图列表入口再次打开/关闭；断言 body lock、sidebar class、backdrop hidden、toggle `aria-expanded` 和地图入口可达性。

先红后绿证据：未修复时 375/390 两项均失败，`#mobile-nav-close.tap()` 被 `#mobile-nav-toggle` 拦截；修复后两项通过。服务当前由主会话暂停，未启动 live 8000、未改滚动/后端/provider/full、未提交。

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/frontend/test_frontend_map_mobile_contract.py -k global_mobile_navigation_close_paths_keep_map_entry_reachable -q`（修复前） | 退出码 1；2 failed，375/390 均为 toggle 拦截 close |
| 同一窄回归（修复后） | 退出码 0；2 passed（375/390，正常 tap，无 force） |
| `.venv/bin/python -m pytest tests/frontend/test_frontend_map_mobile_contract.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py -q` | 退出码 0；32 passed |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend docs/sdd/plans/043/artifacts/task-07/frontend-report.md` | 退出码 0 |

前端三项自查：DOM 契约通过（生产导航完整 DOM 与 fixture 同步）；CSS 层级通过（只增加移动打开态命中避让，不改地图/桌面层级）；XSS 通过（本轮未新增 `innerHTML`，地图模块仍无 `innerHTML`）。待 frontend-reviewer 在服务恢复后复核真实 live 375/390 普通 close/toggle 路径。
