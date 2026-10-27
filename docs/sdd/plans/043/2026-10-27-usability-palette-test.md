# Spec043 Task10 配色与节点样式独立前端回归报告

日期：2026-10-27 13:37（Asia/Shanghai）
角色：frontend-tester；独立复核当前配色/样式候选

## 结论

配色和节点样式的 12 项新增浏览器用例全部通过。整体前端候选暂不通过：390px 手机宽度打开长详情时，可见地图高度为 127px，低于既有布局用例要求的 150px；该问题在完整回归和单项复跑中均重现。移动分组抽屉的真实触摸滚动在完整套件初跑失败、单项复跑通过，结果不稳定。

## 验证范围与结果

| 验证 | 结果 |
|---|---|
| 配色与样式浏览器用例 | 12 项通过：节点/多选/组色真实点击、预览与取消、颜色提交、revision 冲突、失响应后 GET 核实、切图迟到响应、owner 最近色隔离、最近色去重上限、样式重开、PNG/JSON 下载与未应用预览阻止。多选走真实 Chromium 鼠标事件；配色用例未 skip。 |
| 完整定向前端套件 | 退出码 1：46 passed、2 failed、0 skipped。覆盖布局视口、组与导出、mobile 手势/版本、地图 DOM/CSS/API 契约，以及 expansion/analysis 资源版本合同。 |
| 390px 详情视口复跑 | 退出码 1：单项失败；可见地图高度 127px，断言下限 150px。完整套件与隔离复跑均复现。 |
| 移动分组抽屉真实触摸滚动复跑 | 隔离复跑退出码 0：1 passed。完整套件中该项先失败，因而记录为间歇性结果，尚不能认定稳定通过。 |
| JavaScript 语法 | node --check frontend/literature-maps.js，退出码 0。 |
| 安全 DOM、CSS 作用域和资源版本 | 相应静态契约用例通过；index.html 与浏览器 fixture 均为 literature-maps.js v27 / literature-maps.css v17。 |

作者此前报告的 21 passed 不作为本次独立结论；本次重新运行了配色套件及受影响前端回归。

## 命令与退出码

完整定向回归（授权 Chromium 后运行）：

    TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_palette.py tests/frontend/test_frontend_map_layout_viewport.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes

    退出码：1（46 passed、2 failed、0 skipped）。

失败用例隔离复跑：

    TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider --tb=short 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]' tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures

    退出码：1（1 passed、1 failed；移动触摸通过，390px 详情失败）。

JavaScript 语法命令：

    node --check frontend/literature-maps.js

    退出码：0。

## 失败与边界

- 390px 长详情可见地图高度问题：两个运行都只在 390px 宽度失败；桌面断点与其他布局用例通过。此报告确认回归现象，不将其归因到某一条 CSS 或配色改动，根因仍需实现方定位。
- 移动分组抽屉触摸滚动：完整套件首次断言最终 scrollTop 为 0，隔离复跑通过；保留为不稳定交互结果。
- 首轮未授权浏览器启动因 macOS Chromium MachPortRendezvous 权限报错，得到 8 passed、29 skipped、11 failed，退出码 1。该轮没有用作产品通过证据；随后已获准启动 Chromium 并完成上述真实浏览器验证。
- 浏览器页面使用本地 fixture/mock API，验证前端请求、状态与导出内容；本轮未运行后端 pytest、未访问已部署服务或执行真实 API E2E，也未改动业务代码。

## 交接

当前前端候选不能因配色用例通过而整体验收。先由前端实现方处理并复核 390px 长详情的可用地图高度，再针对该视口和移动触摸抽屉复验；配色用例现有 12 项结果为通过。

进展日志：.codebuddy/agent-logs/spec-043/task-10/frontend-tester/20261027-132600.md

## 修复后独立复验（2026-10-27 13:51；当前结论）

对修复后的候选 JS v28 / CSS v18 独立重跑，结果覆盖上一节记录的 JS v27 / CSS v17 候选；本次结果更新当前前端定向结论。

完整定向命令：

    TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_palette.py 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]' tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_contract_is_versioned_scoped_and_touch_safe tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_literature_map_contract.py::test_navigation_view_and_version_contract_are_wired tests/frontend/test_frontend_literature_map_contract.py::test_map_styles_are_scoped_and_fixture_is_not_product_data tests/frontend/test_frontend_literature_map_expansion.py::test_expansion_contract_uses_versioned_safe_dom_and_frozen_routes tests/frontend/test_frontend_map_analysis_contract.py::test_map_analysis_contract_uses_frozen_evidence_and_navigation_shapes

    退出码：0（28 passed、0 failed、0 skipped）。计数为配色/样式16项、390px视口1项、移动手势/断点/版本4项、导出与静态契约7项。

JavaScript 语法命令：

    node --check frontend/literature-maps.js

    退出码：0。

新增边界复核：

- 保存的节点 override 会在改色草稿预览中正确显示；取消普通改色恢复保存值，显式 null 跟随分组色的预览取消也恢复保存值；再次应用后请求明确带 color_override=null，节点 group_id 保留。
- 分组 PATCH 结果不明且服务端未保存时，界面读取 /groups、保留色稿并允许显式重试；服务端已保存但响应丢失时，先 GET 核实，之后才报已保存并更新最近色。
- 切换到另一 owner 地图期间分组 PATCH 延迟成功，只记入原 owner 最近色桶；新地图标题和新 owner 存储未被旧响应覆盖。
- 390px 长详情视口用例通过，恢复满足150px可见地图高度的约束。
- 移动抽屉触摸用例通过：真实 CDP touchStart/touchMove/touchEnd 事件后逐动作等待 animation frame，等待面板实际 transform/visibility 过渡，监听 scroll 事件并以连续稳定 rAF 帧确认 scrollTop；滚动路径不再依赖固定240ms等待。
- 主页面和 fixture 同步为 literature-maps.js v28 / literature-maps.css v18；资源版本、安全 DOM、样式作用域和导出合同均在本次选择的契约用例中通过。

当前复验结论：本次指定的配色、390px详情、移动触摸、导出与资源契约均通过，未发生 skip。测试页面使用本地 mock fixture；本报告不覆盖真实后端 API E2E、部署或 Spec043 整体验收。

本次进展日志：.codebuddy/agent-logs/spec-043/task-10/frontend-tester/20261027-135040.md
