# Task07 手机地图浏览器验证

## 证据类别

- 环境：授权启动的 Chromium headless；Playwright `has_touch=True`、`is_mobile=True`。
- 页面：`tests/frontend/fixtures/literature_map_component.html`，明确为合成 API fixture，不是真实部署，不是真机。
- 视口：375×820、390×820；桌面边界 1440×900。
- 运行命令：`.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`
- 结果：退出码 0，3 passed。

## 已观察行为

1. 375px 与 390px 均可打开“地图列表和筛选”抽屉，关闭后焦点回到列表入口；选中地图后抽屉关闭且 `document.documentElement.scrollWidth <= innerWidth`。
2. 通过 Chromium PointerEvent 触控模拟执行两指分开、抬起和取消；图谱 transform 发生缩放变化，取消后手势状态清理，后续单指触控仍可点选节点。
3. 通过 Chromium touchscreen tap 点选节点，详情抽屉打开；详情内容 computed `touchAction` 为 `pan-y`，不把抽屉滚动交给图谱；关闭详情后焦点回到当前节点。
4. 1440px 页面保持 `.literature-map-grid` 为 `grid`，节点详情可见，未回退桌面三栏。

## 未覆盖

- 未使用真实后端 API、真实来源目录或 provider。
- 未使用 iOS/Android 真机；浏览器触控模拟不能替代真机验收。
- 未在本证据中断言 Task05 全文 KB 可用；其既有 partial 限制保持不变。

## 复审修复追加（2026-10-21）

原报告的 3 passed 是首轮页面级触控检查；复审后已补充并实际运行以下 Chromium 触控模拟证据。事件由授权 Chromium DevTools `Input.dispatchTouchEvent` 注入到浏览器输入管线，明确不是物理真机：

1. 390×820：单指平移改变 viewport；双指在同一中心放大，中心对应的世界坐标保持近似不变；极窄/极宽 pinch 分别触及 `0.35` 与 `2.8` 边界。
2. 双指结束时首个触点抬起，剩余触点移动不再产生突跳；`window.__viewBodies` 在稳定等待后恰好收到一次最终 viewport 保存。真实 touch 触点被窗口 `blur` 中断后，下一次真实 touchscreen tap 仍可打开详情。
3. 375×820 长内容夹具中，分组抽屉与详情抽屉都通过真实触摸移动产生 `scrollTop > 0`；地图 SVG 仍是 `touch-action: none`，抽屉内容为 `pan-y`。
4. 1440×900：真实 `page.mouse` 节点拖拽后，合成 `/view` 请求中的 node-a 位置相对初始位置改变，三栏 grid 保持不变。

复审命令：

- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`：退出码 0，6 passed，10.77s。
- `node --check frontend/literature-maps.js && .venv/bin/python scripts/check_test_naming.py && .venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py && git diff --check -- frontend tests/frontend`：退出码 0，受影响回归 20 passed；命名检查通过。

限制：仍为本地合成 API fixture 与 Chromium 触控模拟，不宣称 iOS/Android 真机或真实后端验收；未启动服务、未运行 backend pytest、未执行全量回归/部署。
