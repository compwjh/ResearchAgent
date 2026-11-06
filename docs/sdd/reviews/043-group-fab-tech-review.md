# Spec043 增量 · 节点分组画布左下角入口改造 — 技术评审（Tech Review）

| 项 | 值 |
|---|---|
| **评审者** | `architect` 子代理（本轮 Spec043 增量评审，Gate 2 技术评审） |
| **角色** | 架构师 / `architect`（技术评审 + 跨端边界裁决 + 合并裁决参考） |
| **模型** | Deepseek-V4.1-Flash（按 spec 执行配置表 `docs/sdd/specs/043-literature-map-topic-exploration.md:884`；上下文上限 32k 档，故与需求评审分两份落盘） |
| **分派方式** | 主会话单次分派：只读代码（`frontend/literature-maps.js` 7190 行、`.css` 364 行、`index.html` 812 行、`backend/.../routes_literature_maps.py` 815 行、`service.py`、`tests/frontend/`）后产出本文件；**禁改业务代码 / 测试 / spec / 版本号，禁部署、禁重启服务、禁 git 操作** |

## 评审基线

- 实现前技术评审。所有代码事实为本次实测，行号取自当前工作区快照（`literature-maps.js` 7190 行、`literature-maps.css` 364 行、`index.html` 812 行、`routes_literature_maps.py` 815 行）。
- spec 给的行号基本准确（多数在 ±2 行内），**但 spec 遗漏 5 处强耦合**，是本文件 P0 的主要来源。

---

## 一、结论

# 结论：**通过（附强制约束清单）**

**「零后端改动」成立**、**高亮视图态不会污染 `revision`/视图保存/导出/多选态**（前提见 T-P0-2 的 3 条保护约束）、**`nodeDisplayColor()` 简化与历史 `color_override`/旧导出 JSON 兼容**（前提见 T-P0-3）、`aria-*`/Esc/点外部关闭**可测**。但**任务拆分与真实改动面严重不符**（P0-1），且 spec 未识别 4 处隐藏耦合，按现拆分派活**必然**产出 CI 红 + 运行期回归。故判 **通过附意见，P0 闭合后放行**。

**P0 阻断（必须回填 spec 后才派活）**

| 编号 | 问题 | 实测证据 | 后果 |
|---|---|---|---|
| T-P0-1 | **改动面被低估**：夹具 `tests/frontend/fixtures/literature_map_component.html`（1123 行）不在任何任务格；4 个既有测试文件对**将被移除的 DOM** 有硬断言 | 夹具 `:8`（css?v=28）、`:1120`（js?v=42）；`test_frontend_map_groups_exports.py:23-25` marker 断言、`:63-69` 点 `#literature-map-group-create`、`:80` `#literature-map-group-list`；`test_frontend_literature_map_expansion.py:125` `#literature-map-groups .literature-map-group-row` 必须可见；`test_frontend_map_mobile_contract.py:286-309` 抽屉内 `#literature-map-groups` 触摸滚动；`test_frontend_map_palette.py:136-201` 点 `.literature-map-group-color-trigger` | 按 FE-1/FE-2 派活 → 至少 5 个文件漏改，`pytest tests/frontend` 直接红 |
| T-P0-2 | **高亮必须与 `revision`/脏标记/导出彻底隔离**，但 spec 只写了"不写库"，没写代码级护栏；`hasUnappliedVisualDraft()`（`literature-maps.js:5633-5635`）会把 `state.colorDraft` 与脏 nodeStyle 当成"导出拦截"，若高亮被误塞进 `colorDraft` 或任何 dirty 判定，导出/保存会被无辜拦截 | `hasUnappliedVisualDraft()` 5633-5635、`blockExportWithUnappliedDraft()` 5637 起、`saveView()` 5396/5524、`updateGroupState()` 1985-1986（唯一写 `revision` 处之一） | 高分险回归：一次点高亮 → "存在未应用的预览"挡住导出；或高亮被 `hasUnappliedVisualDraft` 计入导致永久拦截 |
| T-P0-3 | **`createColorPalette()` 一函数三目标未收敛**：删 node/selection 后，函数体内 4 段分叉变死代码，且 `cancelColorDraft()`/`applyGroupColor()` 回调仍走 `renderGroups()` 单一路径，浮层不会刷新 | `createColorPalette(target, groupId)` 712-802：文案三元 763、apply 分支 766-769（`applyNodeColor(target)`）、`followGroup` 分支 775-786、`renderGroups()/renderNodeDetail()` 分叉 708-710；`applyGroupColor()` 2255-2258 成功后仅 `renderGroups()`+`renderGraph()` | ①留下第二套死分支（违反 YAGNI 与"禁止第二套实现"）②浮层改色后色块不刷新（用户可见回归） |
| T-P0-4 | **`refs.selectionPalette` 与 `renderMultiSelectControls()` 强耦合**：删多选调色板会导致 `querySelector` 空转或抛错 | 创建 `1242-1244`（`createColorPalette('selection')`）、注册 `refs` 1319、使用 `renderMultiSelectControls()` 1868-1875 里 `refs.selectionPalette.querySelector('.literature-map-color-apply')` | 若仅"不 append"而保留 ref，`hidden` 逻辑仍跑（空转）；若连 ref 删，`renderMultiSelectControls` 需同步改 → 必须在 FE-1 内一起动 |
| T-P0-5 | **`nodeDisplayColor()` 简化会打断"草稿预览"链路**：现有实现把 `state.colorDraft`（node/selection 目标）作为最高优先级，简化成"只取 `currentGroupColor(group_id)`"后，`initialPaletteColor()`（678-689）与 `setColorDraft()`（696-702）为 node/selection 提供的预览能力整体失效 | `nodeDisplayColor()` 657-668；`initialPaletteColor()` 678-689 对 node 走 `nodeDisplayColor`；`colorDraftMatches()` 670-676 | 若只删 DOM 不删数据流，`state.colorDraft` 仍可被 `setColorDraft('group')` 使用，但 `nodeDisplayColor` 不再理会 → 分组改色草稿预览**也**依赖 `currentGroupColor()` 的 draft 分支（647-653），必须保留该分支，否则分组色板失去"预览"能力 |

**P1（放行前应写明）**

| 编号 | 问题 | 证据 |
|---|---|---|
| T-P1-1 | 高亮 + 扩展高亮两套强调并存：`.is-expansion-highlighted circle { stroke:#f08c00 !important; stroke-width:5 !important }`（CSS:236）会压过任何非 `!important` 的分组高亮描边 | `literature-maps.js:4950,4954`、`literature-maps.css:236` |
| T-P1-2 | FAB 与 SVG 的 `pointer-events`：`.literature-map-canvas-empty` 已是 `inset:0` + `pointer-events:none`（CSS:76-77），FAB 若复用同一层级但漏写 `pointer-events:auto` 会被 empty 或 SVG 吃掉点击 | CSS:74,76-77,82；JS:1264-1268 |
| T-P1-3 | 移动端 375 视口下画布高度被压缩到 `min(360px, max(180px, calc(100dvh - 520px)))`（CSS:289），FAB + 向上展开的浮层极易溢出画布上边界；且抽屉 `z-index:1070`/backdrop `1060`（CSS:299,313），浮层若 `position:fixed` 会穿透抽屉层级 | CSS:282,288-290,299,313 |
| T-P1-4 | `Esc`/点击外部关闭的实现必须绑在 `refs.root` 的捕获阶段或 document 上并做**解除绑定**，现有 `bindEvents()` 无统一 teardown，重复 mount 会叠加监听 | `bindEvents(newButton, refreshButton, closeDetail)` JS:1325；`state.mounted` 1326 |
| T-P1-5 | `aria-expanded` 的"点外部关闭"若用 document 监听，`page.locator(...).click()` 在 Playwright 里会先触发 mousedown 外部判定 → 断言序必须"先开→断言 expanded=true→再点外部→断言 false"，否则 flaky | 可测性约束，见 `test_frontend_map_groups_exports.py:63-69` 现有写法 |
| T-P1-6 | 版本号：`index.html:9` css=28、`:805` js=42，夹具 `:8,:1120` 同值；**改 css 必然要升 28→29，改 js 必然 42→43**，且 6 个测试文件硬编码这两组数字 | `test_frontend_literature_map_contract.py:28-29`、`_expansion.py:28-29`、`_map_analysis_contract.py:34-35`、`_map_groups_exports.py:18-19,43-44`、`_map_header_actions_readability.py:26,276,303`、`_map_mobile_contract.py:94-98` |
| T-P1-7 | `validateGroupForm()` 只校验"非空 + ≤80 + `#RRGGBB`"，**不校验重名**；spec 边界（`spec:817`）要求"重名提示"，重名只能靠后端返回 → 前端错误文案映射需复用 `errorAction()`，不得新造 | `validateGroupForm()` 804-814；`runGroupMutation()` 2024-2059 的 409/unknown-outcome 分支 |

**P2（建议）**

- T-P2-1 高亮属性命名：`data-group-highlight="on"/"off"` 建议改为 `data-group-highlighted="true"/"false"` 或直接复用 `.is-group-highlighted` 类，与既有 `.is-selected`/`.is-expansion-highlighted` 风格统一（现有代码全用 class，未用 `data-*-on/off`）。
- T-P2-2 浮层滚动：分组上限 `MAX_GROUPS=200`（JS:37），浮层必须 `max-height + overflow:auto + overscroll-behavior:contain`，否则移动端 200 组撑爆视口。
- T-P2-3 浮层内渲染 `state.groups` 时沿用 `createElement`/`setAttribute`（JS:191-196,220-224），已有 `renderGroups()` 1952-1979 可作模板。
- T-P2-4 不要在浮层里放 `<form>` 复用到列表面板的 `#literature-map-group-form` 节点本体（move 会破坏 `refs.groupForm` 绑定），而是"同一个 DOM 节点搬到浮层容器"或"新建一份但共用 `createGroup()`"——**二选一必须写明**，否则 dev 可能造出第二套表单（违反"禁止重复实现"）。

---

## 二、逐条判定依据

### 2.1 「零后端改动」是否成立 —— **成立**

| 需求 | 需要的后端能力 | 是否已有 | 证据 |
|---|---|---|---|
| 浮层列分组 + 色块 | `GET /groups` 返回 `{groups:[{group_id,name,color}],revision}` | 已有 | `routes_literature_maps.py:401-407`；`service.py:818-822`；`models.py:162-164` |
| 新建组 | `POST /groups` | 已有 | `:409-420`；`GroupCreateRequest` 173-178 |
| 已有分组再改色/改名 | `PATCH /groups/{id}`（name/color 均可选） | 已有 | `:423-435`；`GroupPatchRequest` 181-186 |
| 删除组（节点回落） | `DELETE /groups/{id}` + store 级联置 NULL | 已有 | `:438-448`；spec 记录 `store.py:896` |
| 节点切组、颜色随新组 | `PUT /nodes/{id}/group` 返回 `{revision,node}` | 已有 | `:451-462`；`service.py:846-864` |
| 高亮该组节点 | **无需后端**：前端从 `GET /graph` 的 `nodes[].group_id` 判定 | 已有 | `service.py:808-816` 返回全量 nodes；`models.py:145` 含 `group_id` |
| 忽略历史 `color_override` | **无需后端**：纯渲染决策 | 已有 | `models.py:147` 仍返回，前端不读即可 |
| 导出不含高亮 | **无需后端**：前端 `sanitizeJsonExportBlob()` 白名单裁剪 | 已有 | JS:5594-5631，nodes 字段白名单 5613-5616 |
| 导出保留 `color_override` | **无需后端**：同上，白名单本就含该字段 | 已有 | JS:5613-5616；`service.py:2749-2769` |

**判定**：**零后端改动成立**，本批次 `backend/**` 不进范围是对的，也符合"改动只涉及一端时只派该端 agent、纯前端不跑后端 pytest"。唯一附带条件：验收阶段跑一次 `tests/literature_maps` 属**回归核对**（不是改动验证），需在报告里标注这一性质，避免被误读为"动了后端"。

### 2.2 `state.groupHighlightId` 纯视图态是否污染 `revision`/视图保存/导出/多选 —— **不会污染，但需 3 条护栏**

- **`revision`**：全仓写 `state.map.revision` 的位置只有服务端响应回写（`literature-maps.js:1985-1986`、`2018`、`2193-2194`、`3599`、`3794`、`5416-5417`、`6679-6680`）与 `applyMapPayload()`。纯前端 `state.groupHighlightId = ...` 不进这条链 → **无污染**。风险点是"顺手调了 `renderGraph()` 之外的保存函数"，需护栏 A。
- **视图保存**：`saveView()` 的 payload 由 `state.view` / `state.layers` / `state.labelMode` / `state.nodeStyleDraft` 组装（5396-5410、5524-5534），与高亮无关；脏标记 `viewDirty` 只在平移/缩放/图层/标签/外观路径置位 → **无污染**。
- **导出**：`hasUnappliedVisualDraft()` = `state.colorDraft || nodeStyleIsDirty()`（5633-5635）。**高亮绝不能写进 `state.colorDraft`**，否则 `blockExportWithUnappliedDraft()` 会拦住导出并提示"存在未应用的颜色或外观预览" → **必须护栏 A**。PNG 导出走 SVG 序列化，若把高亮写成 `circle` 的 `stroke` 之类会被序列化进 PNG → PNG 应**反射高亮视觉**（合理），但 JSON 导出不含 → 已由白名单保证。
- **多选态**：`state.multiSelectedNodeIds` 与 `state.multiSelectActive` 只在 `toggleMultiSelectMode()`（1878-1906）/`toggleMultiSelectNode()`（1908-1922）变更 → 高亮为独立字段，**互不影响**。唯一边界：多选态下点节点会 `toggleMultiSelectNode`，而高亮是靠"点浮层色块"触发的，两者入口不同 → 无冲突。
- **切图清除**：`resetMapSelectionState()`（2374-2460）是唯一统一的清态入口（跨图清多选/草稿 2381-2386），`state.groupHighlightId = null` **必须**加在此处（放 `2381-2386` 的 `previousMapId !== mapId` 分支内，或放在 2387 之前无条件执行——建议前者，与"只有换图才清"语义一致）。

**护栏（强制）**
- **A**：`state.groupHighlightId` 只允许在 ①浮层开关/点色块 ②`resetMapSelectionState()` ③`renderGraph()` 读取 三处出现；**不得**写进 `state.colorDraft`、不得调用 `saveView()`、不得调用任何 `request()`。
- **B**：`renderGraph()` 写入的高亮属性只放在 `<g>`（`data-group-id` 旁边，4954）或独立 class，**不要新增到 `circle` 的 `stroke`/`fill` 内联样式**（`setAttributes(circle, {... stroke: color ...})` 4962 已被 `nodeStyle` 占用，冲突面太大）。
- **C**：`selectMap()`（2513-2542）路径下 `resetMapSelectionState()` 必定先执行（2516），故清态只需改这一处；但**同一张图的 `selectMap(refresh)` 也会走 2374**，`previousMapId === mapId` 时不进清态分支 → 符合"刷新不清高亮"，需在 spec 确认这与裁定 5「切换地图清除」一致。

### 2.3 `nodeDisplayColor()` 简化后历史 `color_override` 与旧导出 JSON 兼容性 —— **兼容成立，但简化边界要钉死**

- **渲染兼容**：把 `nodeDisplayColor()` 改为 `currentGroupColor(node?.group_id)`（保留 `currentGroupColor` 的 draft 分支 647-653）后，库中残留 `color_override` 被**忽略**，节点显示分组色 → 符合裁定 3「渲染忽略历史值」。`data-color-override`（4962）若保留原值，会不会被 CSS 用到？实测 CSS 中**无任何 `[data-color-override]` 选择器**（`grep data-color-override frontend/literature-maps.css` 为空）→ 保留该属性属无害冗余；但**建议保留**，因为 `test_frontend_map_palette.py:249` 等既有用例读的是 mock 数据而非属性，且未来排障有用。
- **旧导出 JSON 导入**：本仓未实现"导入 JSON"路径（`sanitizeJsonExportBlob()` 只做**导出前**裁剪，`EXPORT_SCHEMA_VERSION='literature-map-export-v2'` JS:51）。spec 边界「导入含 `color_override` 的旧导出 JSON 不报错」（`spec:819`）**当前没有可验证的对象**——没有导入入口就没有这条失败面。**必须**在 spec 改为「导出 JSON 仍含 `color_override` 字段（保持 v2 schema 不变），下游消费者不会因字段存在而报错」，否则测试无法写。
- **导出值来源**：`sanitizeJsonExportBlob()` 5613-5616 从服务端 response 的 `payload.nodes[].color_override` 读，前端**不参与计算** → 前端忽略 override **不会**改变导出内容。这点很关键：说明"渲染忽略"与"导出保留"互不干扰，裁定 3 自洽。
- **简化边界（强制）**：`nodeDisplayColor()` 必须**保留 `currentGroupColor()` 调用**，不得内联成 `groupById(node.group_id)?.color || DEFAULT_NODE_COLOR`——否则 `state.colorDraft.target === 'group'` 的实时预览失效（`createColorPalette('group')` 的色点预览依赖它：`initialPaletteColor()` 683 → `currentGroupColor()`）。

### 2.4 左下角 FAB 与画布 SVG 的 `pointer-events` / 三档宽度 / 移动端抽屉冲突 —— **可行，但有 4 个坑**

| 坑 | 实测 | 约束 |
|---|---|---|
| 层叠顺序 | 画布内 DOM 顺序：`svg`(1264) → `empty`(1267)；`empty` 是 `position:absolute; inset:0; pointer-events:none`（CSS:76-77）。FAB 必须在 `empty` **之后** append（或 `z-index` 更高），且显式 `pointer-events:auto` | 强制 |
| SVG 吃点击 | `#literature-map-svg` 是 `display:block; width/height:100%`（CSS:75），且在 DOM 中在 FAB 之前 → 只要 FAB 后渲染 + `position:absolute`，Z 序天然在上 | 无需额外 `z-index`，但要求 absolute |
| 三档宽度 | `@media (max-width:1180px)`（276）只改 grid 列；`@media (max-width:760px)`（282）把画布压到 `min-height:min(360px, max(180px, calc(100dvh - 520px)))`（289），极端矮屏可能只剩 180px | FAB 尺寸 ≤44px，浮层 `max-height` 建议 `min(60dvh, 画布高度 - 2×FAB)`，且**必须** `overflow:auto` |
| 移动端抽屉 | 列表/详情抽屉 `position:fixed; z-index:1070`（299），backdrop `1060`（313）。若浮层用 `position:fixed` 且 z-index <1060 → 会被 backdrop 压住；若 >1070 → 会盖住抽屉 | 强制：浮层用 `position:absolute`（画布内），**不要** `position:fixed`；这样天然被画布 `overflow:hidden`（CSS:74）裁剪，不跨层 |

附加：画布 `overflow:hidden`（CSS:74）意味着"向上展开"的浮层若高度超过画布上边界会被**裁掉**——必须用 `bottom: calc(100% + 8px)` 之类锚定 + 自身 `max-height`，**不能**靠 `top` 负值硬撑。

### 2.5 分组浮层复用 `groupForm` 与 `validateGroupForm()` 是否可行 —— **可行，但"搬 DOM"与"共建逻辑"必须二选一并写死**

- `validateGroupForm()`（804-814）是纯函数（返回 `{name,color}` 或抛 `LiteratureMapError`），与 DOM 无关 → **可直接复用**，无争议。
- `createGroup()`（2062-2072）直接读 `refs.groupNameInput.value` / `refs.groupColorInput.value` 并复位为 `'#8d80e6'` → 若浮层**另建**一份 `name/color` 输入，`createGroup()` 必须参数化（传入两个 input），否则要么改 `refs`（影响 `renderGroups()` 的 `refs.groupsPanel` 判定 1948），要么造第二套创建逻辑（**禁止**）。
- 三个可选方案，**必须择一写明**：
  1. **搬 DOM（推荐）**：把 `groupForm` 元素从 `groupsPanel` 搬到浮层容器，`refs.groupForm` 指针不变（`Object.assign(refs,...)` 1319 的 ref 仍指向同一节点），`createGroup()` 零改动。代价：`renderGroups()` 1947-1982 需重写为"只渲染浮层行"。
  2. **参数化**：`createGroup(nameInput, colorInput)` 接受输入元素，浮层另建表单，`refs.groupsPanel` 保留但整体 `hidden`。
  3. **废弃 `refs.groupsPanel`**：整段删除列表面板，`createGroup()` 改为读浮层输入。
  三方案都 ≤2 文件（`literature-maps.js` + `.css`），但**删除 `#literature-map-groups` 会命中 T-P1-6 的测试断言**，必须同步改测试。
- 重名：`validateGroupForm()` 不查重名，后端 `create_group` 是否对重名报错需实测；spec 的"重名提示"（`spec:817`）应改为"沿用后端错误 + `errorAction()` 文案"，**不得**在前端自建重名规则（会与后端不一致）。

### 2.6 `aria-*` / Esc / 点击外部关闭的可测性 —— **可测，给出具体断言**

| 行为 | 可断言锚点 | 备注 |
|---|---|---|
| FAB 可访问 | `aria-label="分组"`、`aria-expanded="false"→"true"`、`aria-controls=<popover id>` | `aria-controls` 建议加，提升可测性 |
| 浮层存在 | 稳定 id，如 `#literature-map-groups-popover` + `hidden` 属性切换 | 与既有 `[hidden]{display:none!important}` 模式一致（CSS:344、265） |
| 色块按压态 | `aria-pressed="true"/"false"` | 与 `#literature-map-multi-select-toggle` 的 `aria-pressed`（JS:1864）风格一致 |
| Esc 关闭 | `page.keyboard.press("Escape")` 后断言 `aria-expanded=="false"` 且 popover `hidden` | 需绑 `keydown`，且在浮层内部也要生效（焦点在色块上时） |
| 点击外部关闭 | 先 `expect expanded=true`，再 `page.mouse.click(画布空白处)`，断言 `false` | **不要**用 `locator.click()` 连点，Playwright 的 mousedown 序会导致 flaky |
| 高亮可断言 | `[data-node-id="X"]` 的 `data-group-id` 与浮层被点组的 `data-group-id` 相等，断言该 `<g>` 带高亮标记、其余不带 | 复用现有 `data-group-id`(4954)，避免新造 map |
| 不写库 | `window.__requestLog` 无新 `PATCH/POST/PUT`（fixture 已有 `__requestLog`） | 现有测试已用此机制（`test_frontend_map_palette.py:250`） |
| 导出不含高亮 | 下载 JSON 后断言无 `groupHighlight` 字段 | 走 `expect_download()`，模式见 `test_frontend_map_groups_exports.py:84-90` |

**强制**：Esc/点外部必须在 `state.active=false`（切走地图视图）时解除，否则挂到 document 的监听会在其它视图响应 Esc → 与全局快捷键打架。

### 2.7 任务拆分（每任务 ≤2 文件）是否满足 —— **不满足**

真实改动面（实测）：

| 文件 | 是否已列入 spec 拆分 | 说明 |
|---|---|---|
| `frontend/literature-maps.js` | ✅ FE-1 | — |
| `frontend/literature-maps.css` | ✅ FE-1 | 必改（浮层/FAB/高亮规则） |
| `frontend/index.html` | ✅ FE-2 | 版本号（css 28→29、js 42→43） |
| `tests/frontend/fixtures/literature_map_component.html` | ❌ **缺失** | 1123 行，浏览器用例唯一宿主，`:8`,`:1120` 要跟着升版本号 |
| `tests/frontend/test_frontend_map_groups_exports.py` | ❌ **缺失** | `:23-25` marker、`:63-69` 面板操作、`:80` `#literature-map-group-list`、`:18-19,43-44` 版本号 |
| `tests/frontend/test_frontend_literature_map_expansion.py` | ❌ **缺失** | `:125` `#literature-map-groups .literature-map-group-row` 必须可见 |
| `tests/frontend/test_frontend_map_mobile_contract.py` | ❌ **缺失** | `:286-309` 抽屉内 `#literature-map-groups` 触摸滚动；`:94-98` 版本号 |
| `tests/frontend/test_frontend_map_palette.py` | ❌ **缺失** | `:136-201` `.literature-map-group-color-trigger`；`:242-253` node 调色板；`:389-395,412` `color_override` 导出 |
| 新增 1 个定向测试 | ✅ FE-2 | — |

→ 实际 **9 个文件**（含新增），spec 拆分只覆盖 4 个。**判定：不满足 ≤2 文件规则**（不是因为文件多，而是因为漏列）。

**建议拆分（仍满足 ≤2）**

| 任务 | 文件 | 说明 |
|---|---|---|
| FE-1 | `literature-maps.js`、`literature-maps.css` | FAB/浮层/高亮/删除节点调色板与多选调色板/收敛 `createColorPalette` 为单目标 |
| FE-2 | `literature-maps.js`（续）、`tests/frontend/test_frontend_map_palette.py` | ⚠ 与 FE-1 同文件，需串行；或把测试改造单独成格 |
| FE-3 | `tests/frontend/fixtures/literature_map_component.html`、`tests/frontend/test_frontend_map_groups_exports.py` | 夹具 + 面板断言改造 + 版本号 |
| FE-4 | `tests/frontend/test_frontend_literature_map_expansion.py`、`tests/frontend/test_frontend_map_mobile_contract.py` | 分组可见性 / 移动端滚动锚点迁移到浮层 |
| FE-5 | 新增定向测试文件、`frontend/index.html` | 版本号 + 新用例 |

（FE-2 若坚持"每任务不同文件"，可把 `literature-maps.js` 的剩余改动并入 FE-1，测试改造按 FE-2/FE-3/FE-4 分三格，共 4 格。）

### 2.8 XSS 与缓存版本号契约 —— **契约成立，写法需钉死**

- **XSS**：现有 `createElement(tag, className, text)` 走 `textContent`（191-196）、`setAttributes()` 走 `setAttribute`（220-224）。`assert "innerHTML" not in MODULE` 已被 `test_frontend_map_groups_exports.py:38` 守住。浮层渲染分组名**必须**沿用 `createElement` / `setAttribute`，`aria-label` 与 `title` 均用 `setAttribute` 插值（现有 `renderGroups()` 1958/1967 即为此写法）。
- **缓存版本号**：`index.html:9`（css=28）/`:805`（js=42）；夹具 `:8`/`:1120` 同值。**只要改 js 就必升 42→43，改 css 必升 28→29**，且必须同步 6 个测试文件的硬编码断言（清单见 T-P1-6）。这是项目硬约束「改 CSS/JS 内容必须同步 `?v=N` 且同步全部版本断言」。
- **不得**只升 `index.html` 而漏夹具（`test_frontend_map_groups_exports.py:43-44`、`_map_mobile_contract.py:97-98` 会红）。

### 2.9 已知基线（不在本轮范围内）

`test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 本机超阈属**环境基线**。本轮评审**不要求**放宽阈值、**不允许**固化 skip；若该用例在改动后仍失败，按"环境基线"记录并单独说明，不得混入本轮 P 项。

---

## 三、强制约束清单（供主会话回填 spec，逐条可验证）

**A. 文件与任务**
1. 任务拆分重排为 **≥4 格**，显式包含：`tests/frontend/fixtures/literature_map_component.html`、`test_frontend_map_groups_exports.py`、`test_frontend_literature_map_expansion.py`、`test_frontend_map_mobile_contract.py`、`test_frontend_map_palette.py`。
2. 不得再出现"FE-2 = `index.html` + 新增 1 个测试文件"这种与实际不符的表述。
3. 版本号写死：`literature-maps.js?v=42→43`、`literature-maps.css?v=28→29`，同步 `index.html:9,805`、夹具 `:8,:1120`、6 个测试文件断言（T-P1-6 清单）。

**B. 高亮实现（硬护栏）**
4. `state.groupHighlightId` 只允许三个读写点：浮层交互、`resetMapSelectionState()`（2374-2460）、`renderGraph()`（4946-4979）。**禁止**写入 `state.colorDraft`、**禁止**触发 `saveView()`/`request()`。
5. 高亮标记写在 `<g>`（4954 附近）或新 class，**不得**改 `circle` 的内联 `stroke`/`fill`（4962 已被 `nodeStyle` 占用）。
6. 同图刷新（`selectMap` 且 `previousMapId === mapId`，2379/2381）不清高亮；换图清（2381-2386 分支）。此语义须与裁定 5「切换地图清除」一致并写明。
7. 与扩展高亮并存时**扩展高亮优先**（CSS:236 的 `!important` 保持不变）；或写明反向规则，但必须择一。

**C. 颜色链路收敛**
8. `nodeDisplayColor()` 改为 `currentGroupColor(node?.group_id)`，**必须保留** `currentGroupColor()` 的 `colorDraft.target==='group'` 分支（647-653），否则分组色板预览失效。
9. `createColorPalette()` 收敛为**单目标**（group-only）：函数签名、`palette.dataset.target`、763 文案、766-769 分支、775-786 `followGroup` 分支一并清理；`applyNodeColor()`/`updateGraphColorOverrides()` 若变无调用者，**必须删除**（不得留死代码）。
10. `refs.selectionPalette`（1242-1244、1319）与 `renderMultiSelectControls()` 1868-1875 必须同批清理，`querySelector` 不得指向已删节点。
11. 浮层改色/重命名/删除成功后，`applyGroupColor()`（2255-2258）、`cancelColorDraft()`（704-710）、`renameGroup()`、`deleteGroup()` 的 `renderGroups()` 回调必须**同时**刷新浮层（建议把浮层渲染并入 `renderGroups()`，保持单一入口）。

**D. 浮层与 FAB 布局**
12. FAB：`position:absolute`、显式 `pointer-events:auto`、append 在 `empty`（1267）之后、尺寸 ≤44px、带 `aria-label`/`aria-expanded`/`aria-controls`。
13. 浮层：`position:absolute`（**不用** `position:fixed`，避免与抽屉 `z-index:1070`/backdrop `1060` 冲突，CSS:299,313）；自带 `max-height` + `overflow:auto` + `overscroll-behavior:contain`；向上展开用 `bottom` 锚定，**不得**依赖负 `top`（画布 `overflow:hidden`，CSS:74）。
14. 375 视口下画布可能仅 ~180px 高（CSS:289），浮层 `max-height` 必须自适应且可滚动，验收断言 `document.documentElement.scrollWidth <= innerWidth`。

**E. 表单复用（择一写死）**
15. `groupForm` 处置必须二选一写明：(a) 搬 DOM 到浮层、`refs.groupForm` 指针不变、`createGroup()` 零改动；或 (b) `createGroup(nameInput, colorInput)` 参数化。**禁止**第三套表单。
16. 重名/非法色的文案走 `errorAction()` + 后端错误，**不得**在前端自建重名校验（`validateGroupForm()` 804-814 现状不含查重）。

**F. 验收与测试**
17. 新增用例文件命名**禁止**含 spec/task 编号（项目硬约束）；测试基线数字由 dev 实跑后回填，不得沿用历史「396」。
18. 高亮"不写库"用例断言 `window.__requestLog` 无新增 `POST/PATCH/PUT`（复用夹具既有机制）。
19. 验收阶段跑 `tests/literature_maps` 需在报告中标注为**回归核对（零后端改动前提下）**，并附 `.venv` 激活命令。
20. 已知基线 `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 不得放宽阈值、不得固化 skip。

---

## 四、放行条件

| 门槛 | 条件 |
|---|---|
| 技术评审放行 | T-P0-1 ~ T-P0-5 全部回填 spec；T-P1-6（版本号清单）必须逐项列出 |
| 派活 | 按重排后的 ≥4 格任务拆分派 `frontend-dev`（纯前端，不跑后端 pytest） |
| 合并裁决 | 需求评审 + 技术评审双通过、P0 闭合、`node --check` + `pytest tests/frontend -q` 实跑通过 |

---

## 五、评审记录

- 2026-11-06 ｜ `architect`（子代理）｜ 增量技术评审完成，结论 **通过（附 20 条强制约束）**；P0 5 项、P1 7 项、P2 4 项。核心判断：零后端改动成立；高亮视图态可控但需 3 条护栏；任务拆分严重低估改动面（9 文件 vs spec 4 文件）。
- 本文件为只读评审产出，未修改业务代码 / 测试 / spec / 版本号。
