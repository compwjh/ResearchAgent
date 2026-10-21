# Spec043 Task07 前端独立评审

## 结论

**BLOCK（P1=2，P0=0）**。

评审只覆盖 `frontend/**`、地图 fixture 与前端契约测试；未修改业务代码、未运行后端 pytest/全量回归、未启动服务、未接触 provider 或 secrets、未提交/推送。Task05 全文 KB partial 阻塞保持独立，不因本评审改变。

## 评审依据与环境

- 交接物：`interface-contract.md`、`frontend-report.md`、`browser-verification.md`。
- 代码基线：相对 `788a4b9` 的 `frontend/index.html`、`frontend/literature-maps.js`、`frontend/literature-maps.css` 与地图 fixture/前端测试增量。
- 语法：`node --check frontend/literature-maps.js`，退出码 0。
- 静态合同：新增 mobile 静态合同 1 passed；既有地图版本/DOM/XSS/接口静态合同 7 passed。
- 命名与空白：`.venv/bin/python scripts/check_test_naming.py` 通过；`git diff --check -- frontend tests/frontend` 通过。
- 独立 Playwright 尝试：`tests/frontend/test_frontend_map_mobile_contract.py` 为 **1 passed、2 failed**；两个 Chromium 启动失败均为当前 macOS 沙箱 `MachPortRendezvousServer ... Permission denied (1100)`，不能当作触控通过，也不把该环境失败归因于业务代码。授权 CUA 只能绑定已有本地服务页；新开 `http://127.0.0.1:8000` 返回 `ERR_CONNECTION_REFUSED`，未启动服务或伪称真实部署验证。
- 交接报告声称的 `3 passed` 来自其先前环境，本轮未能独立复现；页面是合成 API fixture，浏览器模拟不等于 iOS/Android 真机。

## 已通过项

1. **DOM/XSS 边界：通过。** 组件以 `createElement`/`textContent`/受控属性构造 DOM（`frontend/literature-maps.js:105-121`），当前模块不含 `innerHTML`；详情标题/作者/摘要/分析结果均通过文本节点写入（`frontend/literature-maps.js:2781-2869`）。外链使用 `safeHttpUrl`，并设置 `noopener noreferrer`（`frontend/literature-maps.js:2817-2824`）。
2. **抽屉基本 DOM、关闭与焦点逻辑：源码通过。** 列表/详情分别维护 `aria-hidden`、open 状态和恢复焦点引用（`frontend/literature-maps.js:704-747`）；详情关闭会清理选中节点并恢复焦点（`frontend/literature-maps.js:837-856`）。新增测试实际断言列表入口焦点和详情节点焦点（`tests/frontend/test_frontend_map_mobile_contract.py:59-67,94-104`），但因浏览器权限错误本轮未能执行这些运行时断言。
3. **触控 CSS 作用域：源码通过。** 只有 SVG 图谱使用 `touch-action: none`（`frontend/literature-maps.css:68-70`）；移动端列表、分组、创建面板、详情内容使用独立 `overflow-y`/`touch-action: pan-y`（`frontend/literature-maps.css:188-191`），没有将 `none` 施加到整页或抽屉。
4. **桌面布局与资源版本：源码/静态合同通过。** 桌面默认三栏 grid 仍在 `frontend/literature-maps.css:16`，移动断点才切换为抽屉（`:172-196`）。生产页同步 `literature-maps.css?v=8` 与 `literature-maps.js?v=11`（`frontend/index.html:9,784`），fixture 与既有地图合同同步（`tests/frontend/fixtures/literature_map_component.html:7,299`；`tests/frontend/test_frontend_map_mobile_contract.py:25-49`）。
5. **边界清理/缩放夹具：源码存在。** pointer capture 安全释放、`pointercancel`、窗口失焦、页面隐藏清理均已接线（`frontend/literature-maps.js:2047-2055,2185-2189,864-868`）；pinch 比例使用 `0.35–2.8` 常量上下限（`frontend/literature-maps.js:12-14,2095-2104`）。这些是源码检查结果，不替代未执行的真实 Chromium 运行时证据。

## 阻断问题

### P1-01：正常双指结束不会保存 viewport 缩放/平移

位置：`frontend/literature-maps.js:2158-2170`。

双指开始后 `state.pinch` 有效。正常抬指顺序为：第一个 `pointerup` 删除一个 pointer，因剩余 pointer 数小于 2 将 `state.pinch = null`（`2161-2163`），但不会进入 `!state.pointers.size` 的保存分支；第二个 `pointerup` 看到 `state.pinch` 已是 null、`state.pointer` 也是 null，直接在 `2170` 返回。因此正常 pinch 完成不会调用 `scheduleViewSave()`（该调用只在 `2164-2167`），用户重新打开地图时会丢失本次缩放/中心平移。需要在 pinch 结束的单一收口处保存一次，并补测试检查 PATCH body 的 `viewport`。

### P1-02：新增测试不足以证明 Task07 触控/回归验收条件

位置：`tests/frontend/test_frontend_map_mobile_contract.py:25-115`。

- `25-50` 主要是字符串/版本静态断言；不能证明运行时行为。
- `77-92` 用页面内 `dispatchEvent(new PointerEvent(...))` 发送两指事件，只断言 transform 字符串变化；没有验证真实单指 pan 位移、pinch 以触点中心锚定、`0.35/2.8` 上下限、首指/次指抬起后的触点数切换不突跳、失焦/`visibilitychange` 后 capture 与状态清理，亦没有验证 P1-01 的 viewport 保存。
- `94-104` 只用一次 `touchscreen.tap` 验证节点打开详情；没有验证详情长内容 `scrollTop` 真的变化，也没有验证列表抽屉长列表/筛选内容滚动和抽屉滚动不被图谱手势劫持。
- `107-113` 桌面只点击节点并检查详情可见，没有用真实鼠标 `down→move→up` 验证节点布局拖动、位置变化和保存。
- fixture 节点标题/摘要/组名均为短文本，`73` 的 `scrollWidth` 检查不能覆盖 375/390px 长标题、长摘要、长组名场景。

Task07 合同明确要求真实 Chromium 触控模拟及上述交互边界；在 P1-01 修复、补足真实 pointer/touch 序列与抽屉/桌面回归断言，并在可用 Chromium 环境重跑 375/390 与 1440 用例前，不予 GO。

## 复核范围外

- 未评审 `backend/**`、provider、真实 API、Task08 全量/验收/部署。
- 未把合成 fixture 或先前交接报告的浏览器数字当作真实 API、真机或最终收口证据。
- 未对 `Task05` 的全文 KB partial 状态做任何放宽或重新解释。

## 交接

- 评审报告：`docs/sdd/plans/043/artifacts/task-07/frontend-review.md`
- 评审进展日志：`.codebuddy/agent-logs/spec-043/task-07/frontend-reviewer/20261021-review.md`

## 窄复审结论（2026-10-21，修复后）

**GO（P0=0，P1=0；首轮 P1-01/P1-02 已关闭）**。

本次只复核 Task07 前端范围，未修改代码，未运行后端 pytest、全量/provider/deploy，也未改变 Task05 全文 KB partial 阻塞。针对首轮 BLOCK，先核对集中修复，再在明确授权提升权限的 Chromium 环境重跑真实浏览器输入序列；此前 macOS Mach-port 沙箱失败已按要求重试，不再以环境失败代替运行时证据。

### P1 关闭证据

1. **Pinch 最终 viewport 持久化、双转单不跳变：通过。** `frontend/literature-maps.js:2160-2175` 在首个 `pointerup` 使触点数低于 2 时清理 pinch、保留最后一次 `updatePinch()` 的 `state.view` 并调用一次 `scheduleViewSave()`；不为剩余触点建立单指基线，第二个 `pointerup` 不会再次保存。`frontend/literature-maps.js:2065-2104` 以触点中心计算 world anchor，并将比例限制在 `0.35–2.8`。运行测试在 `tests/frontend/test_frontend_map_mobile_contract.py:139-225` 通过中心锚定、上下限、首触点抬起后的剩余触点移动不突跳，以及稳定等待后 `window.__viewBodies` 恰好一次。
2. **真实事件覆盖缺口：通过。** `tests/frontend/test_frontend_map_mobile_contract.py:26-34` 使用 Chromium CDP `Input.dispatchTouchEvent`，不是页面内 `dispatchEvent`；`79-126` 覆盖 375/390px、列表关闭焦点、主体无横溢、真实单指 pan、节点点选/详情关闭焦点；`228-274` 通过真实触摸序列断言分组和详情抽屉 `scrollTop` 增长；`277-297` 通过真实 `page.mouse` down/move/up 断言桌面节点位置保存。`139-225` 还覆盖 blur 后清理及后续 tap；源码的 `pointercancel`、`blur`、`visibilitychange` 清理接线位于 `frontend/literature-maps.js:2192-2195,864-869`。

### 独立命令与结果

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（`require_escalated`，授权 Chromium） | 退出码 0；**6 passed**，10.86s |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（`require_escalated`） | 退出码 0；**20 passed**，16.21s |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

## 独立 frontend-reviewer 复审：P1 手机导航遮挡修复（2026-10-21）

### 结论

**BLOCK（P0=0，P1=1，P2=1）**。本次 z-index 与正常详情关闭路径的原始遮挡问题已由无 force Chromium 路径证实修复；但“离开 view / 切到桌面时清理抽屉状态”仍有可复现的 P1 残留，不能交给 root 提交或部署复验。

### P1-01：桌面切换后离开 view 未清理移动抽屉

- **证据**：`frontend/literature-maps.js:708-769` 的 `closeMobilePanel`/`closeAllMobilePanels` 在 `!isMobileViewport()` 分支只调用 `setMobileDrawerBodyState(false)` 后返回，没有移除 `.is-open`、恢复 `aria-hidden`、隐藏 backdrop 或清零 `state.mobile.listOpen/detailOpen`；`setActive(false)` 在 `3153-3175` 调用该分支。
- **最小复现**（授权 Chromium、fixture、无 force）：375px 打开详情后输出 `body="literature-map-drawer-open", nav="hidden", panel="... is-open"`；切换到 1440px 并调用 `LiteratureMaps.setActive(false)` 后输出 `body="", nav="visible", panel="... is-open", hidden=false`；回到 375px 并 `setActive(true)` 后仍为 `panel="... is-open"`、body 无锁、导航可见。
- **影响**：用户从手机详情切到桌面再离开地图，随后回到手机时详情抽屉仍显示，但全局 `#mobile-nav-toggle` 已恢复可见，遮挡/点击竞态会再次出现；同时旧抽屉状态与 backdrop 状态不一致，违反 Task07 “关闭/离开 view/desktop 清理”要求。
- **修复边界**：在视口无论移动/桌面时都清除两个 panel 的 class/ARIA、backdrop、mobile state 与 body lock；不得用 force click 掩盖。修复后补同一视口切换回归案例。

### P2-01：抽屉背景仍为半透明，存在可读性风险（非本轮阻塞根因）

- `frontend/literature-maps.css:17` 的公共 panel 背景为 `rgba(255,255,255,.83)`；授权 Chromium 实测详情抽屉计算背景为 `rgba(255, 255, 255, 0.83)`，遮罩为 `rgba(32, 28, 61, 0.4)`。现有截图 `docs/sdd/plans/043/artifacts/task-07/screenshots/live-resume-375-detail-scroll.png` 可见后方标题/图形透出。
- 当前文本仍可读、遮罩/抽屉点击层级正确，因此记为同范围 P2 可读性改进，不单独阻塞 P1 修复；如产品要求抽屉承担不透明 modal 语义，应将移动抽屉背景覆盖为不透明主题色并补截图/对比度验收。

### GO 检查项

- **Stacking context / click**：无发现 `#literature-maps-view` 祖先存在 transform/filter/opacity/contain/isolation 等会截断 fixed z-index 的规则；移动 CSS 为 backdrop 1060、panel 1070，生产全局导航为 backdrop 1040、sidebar 1050、toggle 1100。375px 详情关闭路径的无 force `.click()` 退出码 0，实际命中 `#literature-map-detail-close`；关闭后全局 toggle 恢复可见。
- **DOM/XSS**：地图模块仍无 `innerHTML`/`insertAdjacentHTML`/`document.write`/`eval`/`new Function`；动态文本使用 `textContent`，资源 URL 与属性写入沿用受控边界。
- **版本/范围**：生产页与 fixture/既有地图契约同步 `styles.css?v=58`、`literature-maps.css?v=9`、`literature-maps.js?v=13`；测试文件名通过能力命名检查；仅 frontend/** 与对应 tests 有改动，未运行后端 pytest，未启动服务。

### 本轮真实命令与结果

| # | 命令 | 退出码 / 结果 |
|---:|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（授权 Chromium） | 0 / **7 passed**，12.84s |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 0 / **20 passed**，16.30s |
| 3 | `node --check frontend/literature-maps.js` | 0 / passed |
| 4 | `.venv/bin/python scripts/check_test_naming.py` | 0 / passed；无 spec/task 编号 |
| 5 | `git diff --check -- frontend tests/frontend` | 0 / passed |
| 6 | 授权 Chromium 只读视口切换探针（375→1440、`setActive(false)`、回到 375、`setActive(true)`） | 0 / **探针复现 P1-01**（非测试崩溃） |
| 7 | 授权 Chromium 读取详情关闭按钮命中元素与计算样式 | 0 / 命中 `literature-map-detail-close`；panel z=1070、backdrop z=1060；背景 alpha=.83 |

### 评审汇总

| 严重级别 | 数量 | 状态 |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 1 | **block** |
| P2 | 1 | note |

**Verdict: BLOCK — 修复 P1-01 并补视口切换回归后，再由 frontend-reviewer 复审；本轮不授权提交/部署。**

### 其他前端门槛

- **DOM/XSS：通过。** 当前模块仍无 `innerHTML`；详情字段、摘要和错误通过 `textContent`/受控属性（`frontend/literature-maps.js:2788-2831`），外链保留 `safeHttpUrl` 与 `noopener noreferrer`。
- **CSS/布局/滚动：通过。** SVG 手势区为 `touch-action: none`（`frontend/literature-maps.css:68-70`），移动列表/分组/创建面板/详情为独立 `overflow-y` 与 `touch-action: pan-y`（`frontend/literature-maps.css:176-196`）；桌面默认三栏 grid 未改。生产页和 fixture 已同步 JS v12/CSS v8（`frontend/index.html:9,784`；`tests/frontend/fixtures/literature_map_component.html:7,311`）。
- **报告数字说明：** `frontend-report.md:31` 与 `browser-verification.md:9` 的 3 passed 是首轮历史记录；两份文档的复审追加（`frontend-report.md:56-74`、`browser-verification.md:24-38`）已记录当前 6 passed 和真实事件范围，本报告以复审结果为准。

### 限制与结论边界

Chromium CDP 触控是浏览器输入管线的模拟，不是真实 iOS/Android 设备；页面使用合成 API fixture，不替代真实 API/provider 验收。`GO` 仅表示 Task07 前端独立复审通过，不表示 Spec043 全量收口、部署或 Task05 阻塞解除。

## 最新复审台账（2026-10-21 23:20，覆盖前述历史结论）

本轮针对 P1 手机导航遮挡修复的最终结论为 **BLOCK（P0=0，P1=1，P2=1）**。上文早于本轮的窄复审 `GO` 仅保留为历史记录，不得作为当前提交/部署授权。当前唯一阻塞是 `frontend/literature-maps.js:708-769,3153-3175` 在桌面视口分支未清理移动抽屉 `.is-open`、ARIA/backdrop/state；只清 body lock 会导致 375px 回访时详情抽屉与全局导航再次重叠。P2 为移动抽屉沿用 `rgba(255,255,255,.83)` 的非阻塞可读性风险。

本轮已真实执行并记录：mobile contract **7 passed**、受影响地图回归 **20 passed**、`node --check`、测试命名检查、`git diff --check` 均退出码 0；授权 Chromium 视口切换探针退出码 0 但复现上述 P1。修复并补同一切换回归后，需重新进行独立 frontend-review；在此之前不应提交或部署。

## 最新复审台账（2026-10-21，集中修复后；覆盖本报告此前结论）

### 结论

**BLOCK（P0=0，P1=1，P2=0）**。上一轮 P1-01 的“离开地图 view 后移动抽屉残留”已修复；移动抽屉不透明背景的 P2 也已关闭。但新增 resize 清理路径把桌面详情误当作移动详情关闭，仍回归桌面原有详情能力，不能授权提交或部署复验。

### P1-02：桌面视口 resize 会隐藏正在查看的详情

- **根因**：`frontend/literature-maps.js:766-768` 的 `handleMobileViewportResize()` 对所有进入非移动视口的 resize 调用 `closeAllMobilePanels(false)`；`closeMobilePanel('detail')` 在 `:712-715` 无条件设置 `refs.detailPanel.hidden = true`。该 helper 同时用于移动→桌面 resize，因此没有区分“清移动抽屉状态”和“保留桌面详情”。
- **无 force Chromium 证据**：在 375px 打开节点详情后仅 `set_viewport_size(1440x900)`，无需 `setActive(false)`，输出 `detailHidden=true, detailOpen=false, display=none, gridDisplay=grid, aria-hidden=true, backdropHidden=true, body=''`。桌面三栏 grid 仍在，但已选详情不可见。
- **同类桌面 resize 证据**：在 1440px 直接打开详情后 `set_viewport_size(1280x900)`，同样得到 `hidden=true, is-open=false, display=none`；随后正常点击详情关闭按钮无可达元素并等待超时。这个 resize 不涉及移动 drawer，证明问题不是仅跨断点竞态。
- **影响**：桌面用户调整窗口大小会丢失当前节点详情；从移动抽屉切到桌面也不会保留已选论文详情。Task07 要求“桌面三栏不回退”“桌面原功能保留”，该回归属于 P1。修复应只清移动 panel/backdrop/body/state，或在桌面详情语义下保留/恢复 `hidden=false` 与选中详情；同时保留 `setActive(false)` 离开 view 的关闭语义。

### 已关闭项与独立路径证据

- **P1-01 离开 view 清理：通过。** 375px 打开详情→1440px→`LiteratureMaps.setActive(false)` 后，详情 `hidden=true`、无 `is-open`、`aria-hidden=true`、backdrop hidden、body 无 drawer lock；回到 375px 并 `setActive(true)` 后仍是干净关闭状态，必须重新打开。
- **正常 close/global navigation：通过。** 详情关闭按钮使用普通 `.click()`，关闭后 body/backdrop 清理；再对 `#mobile-nav-toggle` 做普通 `.tap()`，监听器收到 `clicks=1`，按钮有尺寸可见且没有 overlay 残留。列表普通 click 关闭后同样通过。
- **移动背景可读性：通过。** 375px 详情计算背景为 `rgb(255, 255, 255)`；1440px 桌面详情仍为原有 `rgba(255, 255, 255, 0.83)`，未改桌面主题。
- **层叠/DOM/XSS/版本：通过。** 移动 backdrop/panel 为 z1060/z1070，高于全局导航 backdrop/sidebar 的 1040/1050；body lock 暂停 z1100 toggle，关闭后恢复。地图模块未发现 `innerHTML`、`insertAdjacentHTML`、`document.write`、`eval`、`new Function`；资源版本为 `styles.css?v=58`、`literature-maps.css?v=10`、`literature-maps.js?v=13`，fixture 同步。

### 本轮真实命令与结果（8 条独立执行；第 3 条含 3 个静态检查）

| # | 命令/探针 | 退出码 / 结果 |
|---:|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`（授权 Chromium） | 0 / **9 passed**，14.56s |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py`（授权 Chromium） | 0 / **20 passed**，16.41s |
| 3 | `node --check frontend/literature-maps.js && node --check frontend/app.js && .venv/bin/python scripts/check_test_naming.py && git diff --check -- frontend tests/frontend docs/sdd/plans/043/artifacts/task-07/frontend-report.md` | 0 / 全部通过；无编号测试名、无 diff whitespace 错误 |
| 4 | 授权 Chromium：375 打开详情→仅 resize 1440（无 `setActive`） | 0 / **复现 P1-02**：桌面 detail hidden/display:none，grid 仍为 grid |
| 5 | 授权 Chromium：1440 打开详情→resize 1280→正常 close | 130 / 详情已被 resize 隐藏，close locator 无可达元素后按证据终止；前序输出明确复现 P1-02 |
| 6 | 授权 Chromium：1440 打开详情→普通 close（无 resize） | 0 / detail hidden=true、is-open=false、aria-hidden=true；桌面正常 close 语义本身通过 |
| 7 | 授权 Chromium：375→1440→`setActive(false)`→375→`setActive(true)`，列表普通 close 后 global nav 普通 tap | 0 / 清理状态通过；nav click 监听命中 1 次，body/backdrop 无残留 |
| 8 | 授权 Chromium：375 详情普通 close 后 global nav 普通 tap | 0 / nav click 监听命中 1 次，按钮可见，detail/backdrop/body 均清理 |

未运行后端 pytest、全量回归、服务或真实 API；未修改实现/测试，未提交。**当前唯一阻塞为 P1-02；需修复 resize 时桌面详情保留并补对应回归后重新复审。**

## 最终复审台账（2026-10-21，P1-02 修复后；覆盖此前 BLOCK）

### 结论

**GO（P0=0，P1=0，P2=0）**。本轮仅复审 P1-02 的断点状态机、ARIA 与 inactive resize 竞态；未扩大到后端、服务或全套浏览器回归。此前普通桌面 resize 隐藏详情的问题已关闭，原 P1-01 离开 view 清理、移动遮挡修复和移动抽屉不透明背景仍保持通过。

### P1-02 关闭证据

- **desktop→desktop：通过。** 1440px 打开节点详情后 resize 到 1280px，详情保持 `hidden=false`、`is-open=true`、`aria-hidden` 缺省、计算 `display:flex`；随后普通关闭按钮可点击并恢复 `hidden=true`。
- **active mobile→desktop：通过。** 375px 打开详情后 resize 到 1440px，移动 drawer class/backdrop/body lock 清除；已选桌面详情保持 `hidden=false`、`is-open=false`、`aria-hidden` 缺省，桌面详情可见。
- **active desktop→inactive：通过。** 在桌面保留详情后调用 `LiteratureMaps.setActive(false)`，详情变为 `hidden=true`、`is-open=false`、`aria-hidden=true`，backdrop hidden，body 无 `literature-map-drawer-open`。
- **inactive mobile→desktop 事件竞态：通过。** 手机详情打开后先 `setActive(false)`，再 resize 到桌面；详情仍是完整关闭语义（`hidden=true`、`aria-hidden=true`、无 open/backdrop/body 残留），没有被 resize 反向恢复为桌面可访问状态。之后 `setActive(true)` 在桌面移除桌面 panel 的 `aria-hidden`；再回到移动端时恢复 `aria-hidden=true`，不会自动重开旧抽屉。
- **正常导航与 close：通过。** 详情/列表普通关闭后，真实 global-nav toggle 普通 `.tap()` 监听命中 1 次；无 force、无 overlay 残留。

### 代码与范围核对

- `state.mobileViewport` 仅在移动断点跨越时触发清理；desktop→desktop 不调用 `closeAllMobilePanels`。active mobile→desktop 使用保留桌面详情的分支；inactive 与 `setActive(false)` 使用完整清理。
- `selectNode` 在桌面移除详情 `aria-hidden`；重新激活桌面视图调用 `restoreDesktopPanelAccessibility`；移动端继续由抽屉 open/close 管理 `aria-hidden`。
- 移动 backdrop/panel 仍为 z1060/z1070，移动详情背景为 `#fff`；生产/fixture 版本保持 `styles.css?v=58`、`literature-maps.css?v=10`、`literature-maps.js?v=13`。未发现地图模块 `innerHTML`、`insertAdjacentHTML`、`document.write`、`eval`、`new Function`。
- 非核心建议（P2，**不阻塞**）：后续可补一条“inactive 状态多次 resize 不改变 ARIA/hidden”的静态/浏览器回归，但本轮独立探针已覆盖该序列，不扩大范围。

### 本轮独立命令与结果（5 条；未重复全地图回归）

| # | 命令/探针 | 退出码 / 结果 |
|---:|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py::test_desktop_detail_survives_desktop_resize tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_state_resets_after_desktop_view_exit tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_state_resets_on_desktop_resize_round_trip`（授权 Chromium） | 0 / **3 passed**，3.33s |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_detail_close_is_not_blocked_by_global_navigation`（授权 Chromium） | 0 / **1 passed**，1.31s |
| 3 | `node --check frontend/literature-maps.js && node --check frontend/app.js && .venv/bin/python scripts/check_test_naming.py && git diff --check -- frontend tests/frontend docs/sdd/plans/043/artifacts/task-07/frontend-report.md` | 0 / 全部通过；无编号测试名、无 diff whitespace 错误 |
| 4 | 授权 Chromium 生命周期探针：desktop→desktop、active mobile→desktop、desktop inactive、mobile re-entry、ARIA/body/backdrop/global-nav tap | 0 / 全部状态符合预期，global-nav click 命中 1 次 |
| 5 | 授权 Chromium inactive 竞态探针：mobile `setActive(false)`→desktop resize→desktop `setActive(true)`→mobile resize | 0 / `aria-hidden`、hidden、backdrop、body 状态均符合预期 |

开发交接报告已记录生命周期窄测 **3 passed**、同范围地图前端集合 **30 passed**；本轮独立验证未重复该全集合。未运行后端 pytest、全量回归、服务或真实 API；未修改实现/测试，未提交。**Verdict: GO（仅 Task07 frontend 独立复审，不代表 Spec043 收口或部署授权）。**
