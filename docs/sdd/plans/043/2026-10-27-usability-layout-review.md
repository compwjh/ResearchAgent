# Spec043 Task10 前端布局/视口独立评审

日期：2026-10-27  
评审角色：frontend-reviewer  
范围：仅 `frontend/**` 与对应 `tests/frontend/**`；未评审并行后端改动，未修改业务代码。

## 结论

**BLOCK：3 项 P1 阻塞需在本 Task 范围内修复并复审。P0：0。**

## P1 阻塞项

### 1. 390px 手机详情打开后，地图只露出窄条，目标圆也被 backdrop 截获

- 文件：`frontend/literature-maps.css:206-220`、`frontend/literature-maps.js:2630-2654`、`tests/frontend/test_frontend_map_layout_viewport.py:164-210`
- 证据：授权运行五断点真实图回放后，390px 下 canvas 宽 368px，详情抽屉 `left=23.406px`、宽 366.594px；扣除遮挡后仅剩 12.406px 地图宽。选中圆实际宽高只有 9.625px。独立读取该圆心的 `document.elementFromPoint` 得到 `BUTTON#literature-map-mobile-backdrop`（z-index 1060），所以节点既不是可实际命中的地图目标，图谱也只剩边缘细条。
- 问题：当前用矩形交集断言证明了“圆的矩形落在未被抽屉遮住的区域”，没有证明用户能看清地图或点中节点。测试在抽屉打开前点击目标圆，之后只检查交集，因此漏过了 backdrop 命中。
- 修复方向：同范围内调整手机详情布局/抽屉占位，使地图保留可用的可见区域；验收需验证详情打开后的真实截图和 `elementFromPoint`/真实触摸命中，而非只测矩形相交。

### 2. 资源已升到 23/15，六个前端契约断言仍固定为 22/14

- 文件：`frontend/index.html:9,798`、`tests/frontend/test_frontend_literature_map_contract.py:28-29`、`tests/frontend/test_frontend_literature_map_expansion.py:28-29`、`tests/frontend/test_frontend_map_analysis_contract.py:34-35`、`tests/frontend/test_frontend_map_groups_exports.py:18-19,43-45`、`tests/frontend/test_frontend_map_mobile_contract.py:54-58`
- 证据：当前应用入口及 fixture 实际引用 `literature-maps.js?v=23` 和 `literature-maps.css?v=15`。精确运行六个纯静态版本契约用例，结果为 **6 failed、27 deselected、退出码 1**，失败点均是断言仍寻找 22/14。
- 问题：前端回归门禁在本次资源更新后必然失败，且旧断言无法确认新脚本和样式版本已同步。
- 修复方向：把受影响断言及 fixture 版本契约同步到 23/15，再运行这些静态契约用例。

### 3. 旧图没有按圆间距违规检测并提示整理

- 文件：`frontend/literature-maps.js:2372-2439,852-858`
- 证据：`requiredCenterDistance` 只在 `layoutPendingNodes` 中用于给新布局节点找位置；载入已有位置后没有计算任意旧节点对的间距。工具栏始终显示同一个“整理间距”按钮，但没有针对违规地图的检测结果或提示。现有旧图测试从用户主动点该按钮开始，未验证载入时会识别不合规旧图。
- 问题：Task10 已确认行为要求旧图只检测并提示、由用户显式预览整理；保存位置彼此重叠或间距不足的旧图加载后不会收到该提示。
- 修复方向：在旧图读取/显示后检测活动节点的半径感知净空，仅在有违规时给出明确整理提示，并保留现有显式预览与确认保存流程。

## 已通过检查

- **新图半径感知净空**：20、30、50、200 个混合半径节点浏览器回放通过；`minGap >= 4 * max(radius) + 4`，满足圆间净空至少为较大节点直径的两倍并含描边余量。
- **整理预览流程**：取消恢复全部节点位置和视图且不写接口；确认按 revision 保存全部活动节点；409 冲突不伪报保存，预览保留且可取消。零尺寸画布不保存错误 viewport。专项测试均通过。
- **详情和视口**：1440/1280/1180/900/390 五断点均从真实捕获图数据打开真实 SVG 圆节点；桌面长详情在面板内滚动，canvas/SVG 高度稳定，节点坐标与用户缩放保持。390px 的可用性缺陷见 P1-1。
- **旧点位置保护**：自动布局只为 `layoutPendingIds` 生成坐标，并将新增结果合并到 `state.positions`；整理取消也恢复快照坐标。未发现重排旧点的实现路径。新增节点扩展旧地图的场景没有独立浏览器断言，建议修复时补上该专项覆盖。
- **DOM/XSS 与语法**：安全 DOM 契约 1 passed；地图模块未发现 `innerHTML`、`insertAdjacentHTML`、`outerHTML`、`document.write` 或 `eval` 写入点；`node --check frontend/literature-maps.js` 通过。新增视口/布局面板使用节点创建、`textContent` 和受限属性。

## 验证记录

1. 默认权限运行 `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -rs -p no:cacheprovider` 时 12 项均因 Chromium 的 macOS Mach port 权限失败而跳过；未计作通过。
2. 对同一专项浏览器命令申请精确授权后重跑：**12 passed，0 skipped，退出码 0**。
3. 对详情断点运行 `... test_frontend_map_layout_viewport.py -q -k detail_stays -s -p no:cacheprovider` 并获精确浏览器授权：**5 passed，0 skipped，退出码 0**；暴露 390px 窄条测量。
4. 六个纯静态资源版本契约用例命令：

   ```sh
   /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py -k 'navigation_view_and_version_contract or expansion_contract_uses_versioned_safe_dom_and_frozen_routes or map_analysis_contract_uses_frozen_evidence_and_navigation_shapes or groups_and_export_contract_is_wired_without_html_injection or export_asset_versions_are_synchronised or mobile_map_contract_is_versioned_scoped_and_touch_safe' -q -p no:cacheprovider
   ```

   结果：**6 failed、27 deselected，退出码 1**。
5. `test_map_module_uses_frozen_api_and_safe_dom_boundaries`：**1 passed，退出码 0**。
6. `node --check frontend/literature-maps.js`：退出码 0。

浏览器专项基于隔离 fixture/mock API 和捕获的真实图数据，不代表当前部署服务 API E2E 或实体手机验收。除此之外未运行前端全量回归、后端测试、部署或服务操作。

## Review Summary

| 严重度 | 数量 | 状态 |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 3 | block |
| P2 | 0 | — |

Verdict: **BLOCK** — 修复上述 3 项后由独立 frontend-reviewer 复审，再进入 Task10 后续验收。

## Independent follow-up review（2026-10-27）

本节复审并取代上文初次评审的 BLOCK 状态：原 3 项 P1 已修复；另发现 1 项 P2，同范围处理后再确认。

### 原 P1 复审结果：均已关闭

1. **手机详情区域与命中：通过。** 390×900 Chromium mobile viewport 下详情 sheet 范围为 `top=594..900`，地图可触摸区域 `368×211px`；目标圆完整可见，`elementFromPoint` 圆心命中目标 `circle`。用例继续对另一个可见圆触摸并等待 `.is-selected` 切换，成功。canvas/SVG 仍为 600px 高，目标节点坐标不变，scale 仍为 `0.6550009667`。
2. **资源版本契约：通过。** `frontend/index.html` 和 fixture 均引用 JS `v=24`、CSS `v=16`，相关静态契约同步；六个版本用例 **6 passed，27 deselected，退出码 0**。
3. **旧图间距提示：对活动节点通过。** 旧图三点重合，其中一个通过 CSS `display:none` 隐藏；页面提示 3 对间距不足，三点坐标与输入完全一致，等待 650ms 后 `window.__viewBodies` 仍为空。此前报告中的旧图无检测缺陷已关闭。

### 新发现 P2：间距告警把 removed/tombstone 节点也计入

- 位置：`frontend/literature-maps.js:1828,2389-2402`。
- 根因：`countSpacingViolations()` 默认使用过滤过 removed/tombstone 的 `activeNodes()`；但 `loadMapGraph()` 显式传入未经筛选的 `normalizeNodes(payload)` 结果，而计数函数在显式参数路径没有过滤这两个标记。
- 独立复现：隔离 fixture 中将两个活动点分别置于 `(300,300)` 与 `(1000,1000)`，另将一个 `removed: true` 节点置于 `(300,300)`。打开地图后状态错误显示“检测到1对节点间距不足”；按“移除节点不参与检测”的既定契约，该图应没有间距违规。这个提示不会改坐标，也未触发 view 写入，故列 P2。
- 建议同范围修复：计数时统一过滤 removed/tombstone，并分别覆盖 removed 与 tombstone 的不告警测试；继续确保临时 CSS 隐藏的活动点被计入且 GET/告警不写 view。

### 独立验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -rs -p no:cacheprovider`（对 Chromium 测试获精确授权）：**13 passed，0 skipped，退出码 0**。
- 390px 和隐藏活动节点告警两例：`-k 'real_graph_detail and 390 or existing_graph_spacing_warning' -s`：**2 passed、11 deselected，退出码 0**。另外用 fixture 对 removed 节点做独立回放，复现上述误告警。
- 六个静态版本契约：**6 passed、27 deselected，退出码 0**。
- `test_map_module_uses_frozen_api_and_safe_dom_boundaries`：**1 passed，退出码 0**。
- `node --check frontend/literature-maps.js`：退出码 0。

上述浏览器检查使用隔离 fixture/mock API 和捕获的真实图数据，不代表当前部署服务 API E2E 或实体手机验收；本次未运行后端测试、部署或服务操作。

### Follow-up Review Summary

| 严重度 | 数量 | 状态 |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 0 | 原三项已关闭 |
| P2 | 1 | 同范围修复后再确认 |

Verdict: **WARNING** — 原 3 项 P1 均已关闭；移除节点误告警是本次复审中新发现的 P2，建议同范围修复后再复审。

## Independent follow-up review：P2 关闭（2026-10-27）

本轮只复验间距节点集合与真实资源版本，没有重跑此前 14 项布局专项或其它测试。

- **removed/tombstone 排除，hidden 活动点保留：通过。** `loadMapGraph()` 现在用 `activeNodes(payload)` 构造位置与告警输入；该过滤只检查节点的 `removed` / `tombstone` 标记，不按 CSS 可见性筛选。新增回归用例把 removed 和 tombstone 节点分别压在活动点上，页面不再出现间距告警。现有隐藏活动节点用例仍将三个同坐标活动点计为 3 对违规，并验证坐标未改、650ms 后 `window.__viewBodies` 为空。
- **资源同步：通过。** `frontend/index.html` 和 fixture 均引用 JS `v=25`、CSS `v=16`；相关六个静态版本契约测试 **6 passed，27 deselected，退出码 0**。

### 本轮定向验证

- 间距集合两例命令：

  ```sh
  /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_map_layout_viewport.py -q -k 'existing_graph_spacing_warning_is_read_only_and_counts_hidden_active_nodes or existing_graph_spacing_check_ignores_removed_overlaps' -rs -p no:cacheprovider
  ```

  对 Chromium 测试获精确授权后：**2 passed，12 deselected，退出码 0**。
- 资源版本契约命令：

  ```sh
  /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py -k 'navigation_view_and_version_contract or expansion_contract_uses_versioned_safe_dom_and_frozen_routes or map_analysis_contract_uses_frozen_evidence_and_navigation_shapes or groups_and_export_contract_is_wired_without_html_injection or export_asset_versions_are_synchronised or mobile_map_contract_is_versioned_scoped_and_touch_safe' -q -p no:cacheprovider
  ```

  结果：**6 passed，27 deselected，退出码 0**。

### 本轮 Review Summary

| 严重度 | 数量 | 状态 |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 0 | 原三项已关闭 |
| P2 | 0 | 已关闭 |

Verdict: **PASS** — Task10 布局/视口独立前端评审项已完成。此前 14 项专项、13 项首次复审、资源契约等证据保持有效；当前部署 API E2E、人工验收与 Spec 收口仍由后续流程负责。
