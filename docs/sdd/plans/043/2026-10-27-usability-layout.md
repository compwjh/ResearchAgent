# Spec043 Task10 前端布局与视口交接报告

日期：2026-10-27  
范围：仅地图布局/视口；未处理配色、全文状态、后端或部署。

## 交接结论

布局与视口开发范围已完成，等待独立前端评审和后续验收。长详情撑高桌面画布的缺陷已修复；详情开关保留缩放、不移动节点，只在选中点被窗口或移动端详情抽屉遮挡时做最小平移。200 节点混合半径布局、旧图间距预览、取消/确认/冲突恢复及零尺寸画布保护均通过专项浏览器检查。

## 真实复现证据

- 用户提供的 live 证据显示，目标节点 `065389f0f0b64acda6c5a043cc9b6269` 在实际圆节点点击并打开详情后，SVG 高度由 460px 增至 2036.156px，宽度保持 501.992px，transform 不变。首轮 `g` 点击没有打开详情，相关截图与测量不作为有效复现。
- 使用捕获的真实图数据 `task-10-runs/20261027-baseline/graph.json`（地图 `0baabeae7268429c9f7e4de8098ae1d0`，revision 158，21 节点）做隔离浏览器回放。目标节点标题实际渲染后，修复前 1440px 浏览器样例的画布由 564.953px 增至 1021.125px，详情栏增至约 1156px；RED 断言复现了超高。
- 此回放保留真实节点、位置、引用和视口负载，但地图 API 由前端测试夹具模拟；它不等同于当前部署服务的 live API 或最终人工验收。

## 实施内容

- `frontend/literature-maps.css`：桌面详情栏高度上限为 `min(700px, calc(100vh - 160px))`，详情内容区域收缩并在栏内滚动；既有 1180px 与手机抽屉规则继续覆盖相应断点。
- `frontend/literature-maps.js`：选中节点可见区域取 SVG、地图 canvas、浏览器 viewport 的交集；手机详情抽屉覆盖画布时再扣除遮挡区。只平移必要的 x/y，并按 SVG 的 CSS 缩放比例换算，保留用户 zoom；手机抽屉 transform 过渡结束后再检查可见性。
- `frontend/index.html` 与地图回放夹具同步提升资源版本：`literature-maps.css?v=15`、`literature-maps.js?v=23`。
- `tests/frontend/test_frontend_map_layout_viewport.py`：详情测试现在检查真实浏览器 viewport/canvas 交集、节点坐标保持、缩放保持与画布高度稳定；手机夹具先打开地图列表再选图。
- 没有新增 CSS class、输入处理或用户内容 HTML 拼接；新增和修改的 CSS 仍限定在 `#literature-maps-view`。

## 浏览器测量摘要

开详情前后画布与 SVG 高度一致，zoom scale 完全保持，节点中心坐标不变，五个宽度均无 pageerror：

- 1440px：画布/SVG 564.95px；详情栏 700px，详情内容可滚动（scrollHeight 1093px / clientHeight 637px）。
- 1280px：画布/SVG 542.91px；详情栏 700px，详情内容可滚动（1166px / 637px）。
- 1180px：画布/SVG 564.95px；详情面板位于画布下方并限高 300px。
- 900px：画布/SVG 542.91px；详情面板位于画布下方并限高 300px。
- 390px：画布/SVG 600px；移动端抽屉遮挡后，画布剩余 12.41px 可见带，选中圆 9.63px 且完整落在该可见带和浏览器 viewport 内。抽屉过渡完成后才执行可见性平移。

## 定向验证

以下命令均退出码 0：

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -rs -p no:cacheprovider`：12 passed。包含 20/30/50/200 混合半径布局，五个真实图数据断点回放，旧图预览取消/确认、revision 冲突与零尺寸画布。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -k 'detail_stays' -s -p no:cacheprovider`：5 passed，输出上述五个断点测量。
- `node --check frontend/literature-maps.js`：通过。
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py`：`test layout: ok`。
- 定向 Chromium 检查在默认进程权限下会被 macOS Mach port 拦截；随后针对该浏览器测试申请精确授权并完成，无跳过项。

## 未完成项与交接边界

- 尚未执行当前部署服务上的 live API / 浏览器链、最终人工验收、独立前端评审、部署或 Spec 收口；按本次任务边界由主会话和后续验收角色接续。
- 后续配色与全文状态反馈仍按 Task10 余下分端任务实施，本次没有扩展到这些范围。

## Independent review follow-up（2026-10-27）

前端复核指出三项需修复问题：390px 手机上的详情遮罩挡住地图且只留约 12px 可见带；6 个资源版本契约落后于真实 HTML/夹具；旧图加载时没有按圆半径检查间距并提示整理。

### 修复与行为

- 手机详情改为贴底滚动 sheet，最高 `min(34dvh, 320px)`；详情开启时不显示全屏 backdrop，地图区域继续接收触摸。列表 drawer 仍保留 backdrop。画布可见范围现在扣除实际抽屉遮挡矩形，并选择面积最大的剩余矩形，只为让选中圆可见而平移，缩放不变。
- 载入地图后逐对检查所有未移除节点，使用现有 `requiredCenterDistance` 半径净空规则；CSS 隐藏的活动点仍参与检测，移除/墓碑节点不参与。检测只显示“检测到 N 对节点间距不足，原有位置未修改；可点击‘整理间距’预览。”，不改现有坐标，也不因告警安排视图写入。
- 地图 JS 资源版本从 23 更新为 24，CSS 从 15 更新为 16；`frontend/index.html`、回放夹具及相关版本契约测试同步到真实版本，包含 mobile 合约内额外的版本断言。

### 定向证据

- 修复前 RED：390px 浏览器回放中，`elementFromPoint` 命中 `BUTTON#literature-map-mobile-backdrop`，canvas 与 sheet 间只剩 12.41px 可见带；旧图中三个同心节点（含 CSS 隐藏的活动节点）加载后没有“间距不足”提示；六项版本契约全部失败（当时源码与夹具是 23/15，而测试引用 22/14）。
- 修复后手机测量：390×900 viewport，sheet 为 `top=594, bottom=900`，高 306px；canvas 与 viewport 交集内、sheet 以上可触摸地图区域为 `368×211px`。目标圆为 `9.63×9.63px`，完整落在可见区域；圆心的 `elementFromPoint` 命中目标 SVG 圆。随后真实触摸另一个可见圆会切换 `.is-selected`，证明地图仍可操作。画布与 SVG 均保持 600px 高，目标圆坐标未变，transform scale 保持 `0.6550009667`。
- 旧图回归把 3 个活动点设在同一位置，其中一个仍以 `display:none` 隐藏。页面报告 3 对间距不足并提示“整理间距”；圆点坐标保持输入值，650ms 内 `window.__viewBodies` 为空，没有触发视图写入。
- 最初打开日志中“g”点击只选到无效区域、不曾打开详情；该轮 `live-before-after.json` 与 `live-selected.png` 仍不是成功复现证据。以上新测量来自真实基线 `graph.json` 的隔离浏览器回放，端点由前端测试夹具模拟，不等同于当前部署服务的 live API 或真实设备验收。

### 最终验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -rs -p no:cacheprovider`：退出码 0，13 passed。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py -k 'navigation_view_and_version_contract or expansion_contract_uses_versioned_safe_dom_and_frozen_routes or map_analysis_contract_uses_frozen_evidence_and_navigation_shapes or groups_and_export_contract_is_wired_without_html_injection or export_asset_versions_are_synchronised or mobile_map_contract_is_versioned_scoped_and_touch_safe' -q -p no:cacheprovider`：退出码 0，6 passed、27 deselected。
- `node --check frontend/literature-maps.js`：退出码 0。
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py`：退出码 0，`test layout: ok`。

### 后续状态

三项 BLOCK 已按定向测试修复并记录，等待原前端评审复审。没有运行后端测试、部署或 live API 验收；当前部署服务上的 API E2E、最终人工验收与 Spec 收口仍未完成。

## P2 复核补充（2026-10-27）

前三项 P1 已通过原前端复核后，后续复核发现旧图检测可能把 `removed` / `tombstone` 点与活动点的重叠计为违规。最小修复是在 `loadMapGraph` 中以 `activeNodes(payload)` 初始化位置与布局候选，并将同一活动节点列表交给间距检测；`activeNodes` 不按筛选隐藏状态排除论文，因此 hidden 活动点仍参与检测。removed 与 tombstone 节点不再影响布局候选或间距计数。

新增浏览器回归把所有活动点布置在至少 500 个世界单位间距，并分别加入一个与首个活动点重叠的 removed 节点和 tombstone 节点。修复前页面错误报告 3 对间距不足；修复后不再出现告警。此测试证明活动点自身为 0 对违规时，已移除点的重叠不制造假阳性。

JS 源码再次修改后，资源版本从 `literature-maps.js?v=24` 升为 `v=25`；首页、回放夹具和相关静态版本契约同步更新。CSS 保持 `v=16`。

定向验证（均退出码 0）：

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -rs -p no:cacheprovider`：14 passed。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py -k 'navigation_view_and_version_contract or expansion_contract_uses_versioned_safe_dom_and_frozen_routes or map_analysis_contract_uses_frozen_evidence_and_navigation_shapes or groups_and_export_contract_is_wired_without_html_injection or export_asset_versions_are_synchronised or mobile_map_contract_is_versioned_scoped_and_touch_safe' -q -p no:cacheprovider`：6 passed、27 deselected。
- `node --check frontend/literature-maps.js`：通过。
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py`：`test layout: ok`。

