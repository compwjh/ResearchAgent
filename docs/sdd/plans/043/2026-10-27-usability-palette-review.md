# Spec043 Task10 配色阶段独立前端复审

- 复审基线：`5d42211a`（已复核的布局阶段提交）
- 复审范围：当前配色/节点样式前端差异 `frontend/literature-maps.js`、`frontend/literature-maps.css`、`frontend/index.html`；以前端夹具浏览器行为和静态合同作证据。未评后端、未改代码、未做 Git/部署操作。
- 结论：**Warning**。有 2 项 P1 需修复后才能通过前端复审，另有 2 项 P2。

## Review Summary

| 严重级别 | 数量 | 状态 |
|---|---:|---|
| CRITICAL / P0 | 0 | pass |
| HIGH / P1 | 2 | fail |
| MEDIUM / P2 | 2 | warn |
| LOW | 0 | pass |

**Verdict: WARNING — 两项 P1 影响核心预览和 390px 移动端图谱可见性。**

## Findings

### [P1] 已有节点颜色覆盖会挡住新的本地预览

文件：`frontend/literature-maps.js:579-591`

`nodeDisplayColor()` 先发现已保存的 `color_override` 就立即返回，随后才检查 `state.colorDraft`。因此，一个已有独立颜色的节点选中另一种颜色时，图上仍显示旧色；选择“恢复跟随分组”也仍显示旧色，直到服务端应用成功。配色核心流程要求点击后先预览、取消还原，当前不能让用户预览这两类改动。

**Chromium 复核：**先保存节点 A 为 `#12abef`，再点预设 `#ff6b6b`；图上仍是 `#12abef`。接着点“恢复跟随分组”；图上仍是 `#12abef`，而分组色是 `#3366cc`。建议先匹配并应用当前节点的草稿（包括 `null`），再回退到已保存覆盖色。

### [P1] 新增常驻样式控件压缩 390px 详情态的可见地图

文件：`frontend/literature-maps.js:1146-1180`、`frontend/literature-maps.css:257-260`

节点样式 fieldset 被常驻放在画布上方的 `layer-tools` 中，移动断点将其单独换行。打开长详情后，这一新增行把画布向下推，使底部详情抽屉遮挡更多地图。

**Chromium 复核：**精确用例 `test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]` 在 `tests/frontend/test_frontend_map_layout_viewport.py:237` 失败，可见地图高 127px，合同下限为 150px。对照中仅隐藏新增 `.literature-map-node-style` 后，画布 top 从 467px 回到 384px，详情抽屉 top 均为 594px；新增控件占据的垂直空间直接减少了 83px 可见范围。建议在移动端调整控件位置或折叠方式，保住该断点的可见地图高度。

### [P2] 分组改色遇到丢失响应时没有 GET 核实

文件：`frontend/literature-maps.js:241-256,1881-1900,2081-2100`

节点覆盖色 PATCH 有 15 秒超时和 GET graph 核实；分组颜色走通用 `runGroupMutation()`，网络错误只显示“分组保存失败”，没有重新读取 groups 核实。`request()` 会把连接错误标成 retryable，而分组 PATCH 可能已在服务端提交，故这里会把未知结果告知为失败，且成功色不会写入最近色。Task10 的保存合同要求网络结果不明时 GET 核实并保留草稿。

建议分组改色也在网络结果不明时重新读取并比较目标分组色，核实成功后才报告成功及更新最近色，核实失败时保留草稿并明确提示待确认。

### [P2] 切图期间迟到的分组改色成功不会写入原 owner 的最近色

文件：`frontend/literature-maps.js:1887-1890,2092-2098`

分组 PATCH 成功返回后，如果用户已切换地图，`runGroupMutation()` 的 stale-map guard 在调用成功回调之前直接返回；记录最近色只在该回调中执行。与节点颜色路径不同，分组改色没有在请求前捕获原 `ownerId/mapId` 并在服务端确认后写入原 owner 桶。结果是服务端已保存的分组色没有进入最近色列表，跨地图重用行为不一致。

建议请求开始时捕获地图与 owner 身份；成功响应只更新对应原 owner 的最近色桶，不触碰当前地图状态。

## 前端硬约束核对

- **DOM 契约 — PASS。**新增调色板/样式 DOM 在 `literature-maps.js:636-709,1140-1191,1823-1849` 创建；对应组件规则位于 `literature-maps.css:228-260`。节点样式、颜色输入、工具栏、组色等钩子均有组件规则或容器内按钮规则。静态合同用例通过。
- **资源版本 — PASS。**`frontend/index.html:9` 实际加载 `literature-maps.css?v=17`，`:798` 实际加载 `literature-maps.js?v=27`；相关版本合同用例通过。
- **XSS — PASS。**新增颜色从严格 `#RRGGBB` 校验进入 `.value` / `dataset` / 样式属性；动态文案由 `createElement()` 使用 `textContent`（`literature-maps.js:165-169`）。对模块检索 `innerHTML|outerHTML|insertAdjacentHTML` 无命中。
- **CSS 作用域 — PASS。**本阶段所有新增实际选择器均以 `#literature-maps-view` 限定（`literature-maps.css:228-260`）；媒体查询只包裹同样受限的组件选择器，没有新增全局标签规则。

## 其他合同抽查

- 12 个预设 HEX 位于 `literature-maps.js:35-40`；最近色按 owner 隔离、规范化去重并最多保留 8 项。取消预览不写最近色。
- 单点和多选以唯一 node ID 集合提交单个 PATCH，显式传 `color_override: null` 可恢复跟随；已有组色仍只影响没有节点覆盖的节点。组色 409 同地图重读后草稿保留，并要求用户再次应用。
- 节点样式默认 `filled/0.3`；节点填充不透明度和不透明描边分开写入 SVG；选中态加粗描边。样式 PATCH 只带 `expected_revision/node_style`，不含位置或 viewport。
- PNG/JSON 导出在颜色或样式草稿未应用时被阻止；JSON 使用 `literature-map-export-v2` 和字段白名单。相关定向浏览器用例通过。

## 验证证据

- `TMPDIR=/private/tmp /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_palette.py`：Chromium 精确运行后 **12 passed**。受限首次启动因 macOS Chromium 权限全部 skip；后续获准的同一单文件重跑通过，未用首次结果作通过证据。
- `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider --tb=short 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]'`：**1 failed**，实际值 127px < 150px。
- 5 项针对性静态合同：DOM、XSS、CSS scope、主页面导航/资源版本、JSON 导出与版本同步：**5 passed**。
- `node --check frontend/literature-maps.js`：退出码 0。
- 前端 tester 报告的更宽定向套件为 46 passed / 2 failed；移动分组抽屉触摸滚动在全集失败、隔离复跑通过，属不稳定结果。本复审未重复运行全集；需在修复后稳定复验该项。

## 结论

配色基本路径、单/多选写入、组色优先级、409/超时节点色核实、JSON/PNG 和资源合同大部分通过；但已有覆盖节点的颜色预览失效，且新增样式控件造成 390px 图谱可见高度回归。上述两项 P1 修复并完成移动端复验后再作通过结论。

进展日志：`.codebuddy/agent-logs/spec-043/task-10/frontend-reviewer/20261027-132500.md`

## 修复后集中复审（2026-10-27 13:52 Asia/Shanghai）

本节结论覆盖上方初审；上方 Warning 是修复前历史记录，现由本节复审结论取代。复审仍以 `5d42211a` 布局阶段为基线，只核对原四项及其相关回归。

- 复审版本：实际页面与浏览器 fixture 均加载 `literature-maps.js?v=28` / `literature-maps.css?v=18`。
- 结论：**PASS**；P0=0、P1=0、P2=0，未发现新同范围问题。

### 原四项复核

1. **已有覆盖色草稿预览 — PASS。**`nodeDisplayColor()` 先匹配当前地图/节点的草稿，再回退到已保存覆盖色；`null` 草稿显示当前分组色。`test_saved_node_override_is_previewed_and_reset_can_be_cancelled` 实测新色预览、取消恢复、null 跟随分组预览及其取消恢复；多选 null 写入仍通过。
2. **390px 移动端地图可见性 — PASS。**移动端默认收起节点样式 disclosure，断点变化时同步切换展开状态。390px 长详情精确用例通过；375px、390px 抽屉单向平移与样式 disclosure 开合用例通过。
3. **组色失响应核实 — PASS。**组色写入结果不明时 GET `/groups` 并比较目标 group 的 HEX；核实未保存时保留草稿并要求确认后重试，核实已保存时才报成功并记录最近色。浏览器分别模拟写前失响应与写后丢响应，两条均通过。
4. **跨地图迟到成功 — PASS。**组色请求发出前捕获原 `mapId/ownerId`；成功响应先将颜色加入原 owner 最近色桶，再按地图身份保护当前 UI 状态。延迟成功测试确认只更新原 owner 桶，不污染新地图 owner。

### 同范围回归与验证

- 精确 Chromium 运行：配色全文件 + 390px 长详情 + 375/390px 抽屉 + 真实移动分组/详情触摸滚动：**20 passed，退出码 0**。触摸用例等待面板真实 transition、逐帧触摸输入和 `requestAnimationFrame` 滚动稳定，不靠固定 240ms 延迟作通过条件。
- 定向静态合同：DOM、XSS、CSS 作用域、资源版本、JSON 导出：**5 passed，退出码 0**。
- `node --check frontend/literature-maps.js`：退出码 0。
- `git diff --check 5d42211a -- frontend/index.html frontend/literature-maps.js frontend/literature-maps.css tests/frontend/test_frontend_map_palette.py tests/frontend/test_frontend_map_mobile_contract.py`：退出码 0。

复审日志：`.codebuddy/agent-logs/spec-043/task-10/frontend-reviewer/20261027-132500.md`

复测命令：

```bash
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider tests/frontend/test_frontend_map_palette.py 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]' 'tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary' tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures
```
