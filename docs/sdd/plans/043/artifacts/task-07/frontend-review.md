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

### 其他前端门槛

- **DOM/XSS：通过。** 当前模块仍无 `innerHTML`；详情字段、摘要和错误通过 `textContent`/受控属性（`frontend/literature-maps.js:2788-2831`），外链保留 `safeHttpUrl` 与 `noopener noreferrer`。
- **CSS/布局/滚动：通过。** SVG 手势区为 `touch-action: none`（`frontend/literature-maps.css:68-70`），移动列表/分组/创建面板/详情为独立 `overflow-y` 与 `touch-action: pan-y`（`frontend/literature-maps.css:176-196`）；桌面默认三栏 grid 未改。生产页和 fixture 已同步 JS v12/CSS v8（`frontend/index.html:9,784`；`tests/frontend/fixtures/literature_map_component.html:7,311`）。
- **报告数字说明：** `frontend-report.md:31` 与 `browser-verification.md:9` 的 3 passed 是首轮历史记录；两份文档的复审追加（`frontend-report.md:56-74`、`browser-verification.md:24-38`）已记录当前 6 passed 和真实事件范围，本报告以复审结果为准。

### 限制与结论边界

Chromium CDP 触控是浏览器输入管线的模拟，不是真实 iOS/Android 设备；页面使用合成 API fixture，不替代真实 API/provider 验收。`GO` 仅表示 Task07 前端独立复审通过，不表示 Spec043 全量收口、部署或 Task05 阻塞解除。
