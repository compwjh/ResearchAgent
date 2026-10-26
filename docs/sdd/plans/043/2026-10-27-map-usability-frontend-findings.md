# Spec 043 前端地图可用性诊断（2026-10-27）

## 角色、范围与证据

- 角色：`frontend-reviewer`；本轮只做源码/已有测试/本地夹具诊断，不修改业务代码、测试、Git、服务、部署或线上状态。
- 已读最小上下文：`docs/sdd/specs/043-literature-map-topic-exploration.md`、`frontend/literature-maps.js`、`frontend/literature-maps.css`、`frontend/index.html`，以及现有地图前端契约。
- 既有局部验证：

  ```text
  .venv/bin/python -m pytest tests/frontend/test_frontend_map_graphics.py tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_analysis_actions.py tests/frontend/test_frontend_map_import_diagnostics.py
  退出码 0；22 passed in 13.01s
  ```

- 这 22 项使用合成 API 夹具，证明当前夹具在桌面窄画布、200 节点、点选详情、分组/PNG、全文不可用动作和入库诊断路径可用；不等于真实部署或用户截图问题已复现。
- 资源版本与 DOM/XSS 合同仍是 `frontend/index.html:9,798` 的 `literature-maps.css?v=13` / `literature-maps.js?v=21`；`tests/frontend/test_frontend_literature_map_contract.py` 继续核对版本、`textContent`/无 `innerHTML` 等边界。

## 1. 布局、半径与“边缘净空至少两倍直径”

### 已证实

1. 节点半径不是固定圆：`citationRadius` 使用 `min(28, 8 + 2*log1p(citation_count))`，缺失/非法引用数取半径 8，见 `frontend/literature-maps.js:384-389`。最大半径 28，即最大直径 56（SVG world units）。
2. 无保存位置时，`initialPosition` 只按固定环层和椭圆纵向压缩生成中心点：`ring=ceil(sqrt(total/2))`、每环 `ring*2` 点、半径 `70 + layer*58`（上限 285）、`y` 方向乘 `.78`，见 `frontend/literature-maps.js:2284-2291`。它不读取节点半径，也不做圆—圆碰撞检查。
3. `scheduleLayout` 只对缺少持久位置的节点做最多 8 帧的确定性微扰，最大微扰约 `0.72` world units；不会把节点推到不重叠位置，见 `frontend/literature-maps.js:2293-2316`。已有保存位置也不会被这段算法重排。
4. 以当前公式计算未保存位置时，首环相邻中心距（考虑 `.78` 的 y 压缩）大致为：总数 20/30 为 43.71、50 为 34.77、100 为 21.56、200 为 17.22；最大圆直径 56 时对应边缘间距约为 -12.29、-21.23、-34.44、-38.78。也就是说，当前初始位置没有“变半径节点不相撞”的保证，更没有“两倍直径净空”保证。这是对公式的数学推导，不是对用户真实地图的截图复现。
5. 标签避让只用 `occupiedLabels` 逐一寻找最多 6 次的 y 偏移，见 `frontend/literature-maps.js:437-450`；它不改变节点中心位置，且不替代圆的碰撞布局。
6. 初始 fit 在图数据加载后调用：`loadMapGraph` 先填入保存/初始位置，再按 `initialFitPending` 调 `fitView(false)`，见 `frontend/literature-maps.js:1726-1752`。`fitView` 先按 `MAX_NODE_RADIUS=28` 估算，再渲染并尝试用 `getBBox()` 测量节点/边界，见 `frontend/literature-maps.js:2627-2665`；它保证的是视图边界留白，不保证节点彼此净空。

### “两倍直径”可实施定义候选（留给 root/用户选择）

“净空”需同时定口径和适用范围；以下仅是可实施候选，不替用户选定：

| 候选 | 精确定义 | 代价/边界 |
|---|---|---|
| A：大圆保守、world-space | 对任意需互相避让的节点对，`gap = distance(i,j) - (ri+rj)`，要求 `gap >= 2*max(2ri,2rj)`，即中心距至少 `ri+rj+4*max(ri,rj)`。 | 最接近“较大节点边缘外再留两倍直径”；200 节点会显著扩大图面，需允许降低 scale 或增加画布 world 范围。 |
| B：对称、world-space | 要求 `gap >= 2ri+2rj`，即边缘净空至少两节点直径之和（等价于两倍两节点平均直径）。 | 对不同半径节点比 A 宽松或严格取决于半径差；定义对称，但必须明确“两个直径”是两节点各一份还是大圆两份。 |
| C：可见像素口径 | 将 `gap * screenScale` 换算为 CSS px，要求不小于所选的“两倍直径”像素阈值；fit/resize 后重新计算。 | 视觉直观但会随缩放变化；需决定是仅首次自动布局、每次 fit，还是只对当前可见/筛选节点保证。 |

还需由决策者明确两个范围：

- 约束对象是全部节点对、同一环的局部邻居，还是当前筛选后可见节点；
- 自动布局是否只作用于“没有保存位置”的新节点，还是首次打开时允许重排全部节点。当前 Spec 要求保留保存位置、拖动和人工分组，故后者会改变既有用户行为，不能在实现时默默加入。

### 最小复用与边界建议

- 复用现有 `citationRadius`、`positionFor`、`state.positions`、`positionsDirty`、`fitView` 与 `saveView`；不新增 D3/force 依赖、不改变半径公式、不创建第二套布局模型。
- 若选择自动避让，最小实现应在 `initialPosition`/缺失位置补位阶段使用半径感知的确定性布局，并将实际位置继续走现有 `PATCH /{map_id}/view`；不要用 `labelPosition` 代替圆碰撞。
- 拖动后不应偷偷移动其他已保存节点；如需“重新布局”应是显式按钮/动作，并由 Spec 决定是否保存。

## 2. 点选后右详情导致图空白：事实、疑点与未复现项

### 已证实的执行链

- SVG 固定为 `viewBox="0 0 960 680"`，节点/边放在 `#literature-map-viewport` `<g>` 中；每次 `renderGraph` 仅把 `state.view` 写成 `translate(x y) scale(scale)`，见 `frontend/literature-maps.js:881-897,2323-2386`。
- `selectNode` 只设置 `selectedNodeId`、重置当前节点分析状态、打开详情面板、调用一次 `renderGraph`，随后 GET 节点详情与分析；该函数没有清空 `state.graph`、没有修改 `viewBox`、没有调用 `fitView` 或 `locateSelectedNode`，见 `frontend/literature-maps.js:2877-2912`。
- 桌面详情点选本身不改变 `state.view`；移动端只是打开固定抽屉。选中态改变的是圆的 class/描边及标签模式依据，见 `frontend/literature-maps.js:2354-2383`。
- `locateSelectedNode` 只有用户点“定位”才运行，并用固定 `MAP_WIDTH/2`、`MAP_HEIGHT/2` 将所选中心放到 SVG world 中心，见 `frontend/literature-maps.js:2668-2681`。当前 viewBox 恰好也是 960×680，因此暂未形成实际偏移；若未来改变 viewBox，这里是硬编码接缝。

### 可疑根因（有源码依据，但本轮不宣称已复现）

1. **没有尺寸观察器/resize fit**：源码没有 `ResizeObserver`；`window.resize` 只调用 `handleMobileViewportResize`，只在是否跨 `max-width:760px` 断点变化时关闭抽屉，见 `frontend/literature-maps.js:1041-1048,1173`。从桌面三列（`>1180px`）切到两列+下方详情（`<=1180px`）时，或详情/浏览器窗口导致画布实际尺寸变化时，没有重新计算 fit。
2. **fit 依赖一次性可见尺寸**：`mapViewportWorldSize` 读取当前 SVG `getBoundingClientRect()`，没有有效尺寸时退回 viewBox world 尺寸，见 `frontend/literature-maps.js:2588-2603`；初始 fit 只发生在 `loadMapGraph`。若某次打开/切换发生在隐藏、布局尚未稳定或尺寸为 0 的时序，实际渲染 transform 可能不匹配后续画布尺寸。
3. **详情打开没有自身定位逻辑**：由于 `selectNode` 明确不改 transform，若用户观察到“点选后整图空白”，需要记录点选前后 SVG rect、viewport transform、节点数量、`getComputedStyle(svg).display/visibility` 和 page error，才能区分画布被重排/裁切、资源异常或其他运行时错误；当前源码不足以把空白归因到某一条。

### 本轮复现结论与下一步证据

- 本轮 22 项定向浏览器测试在 1440、1280、900 等桌面尺寸点选节点后均能看到详情或继续操作；移动断点另有既有 `test_frontend_map_mobile_contract.py`，不在本轮 22 项命令中。因此本轮**未在本地合成夹具复现“点选后图空白”**。
- 现有测试没有覆盖真实 API 数据、窗口从 1440/1280 跨过 1180 的连续 resize 后再点选、详情打开前后 SVG rect/CTM 变化，故不能据此排除截图问题。
- 复现时建议只采集本地页面 DOM/控制台证据：宽度 1440→1280→1180→900→390，分别在地图稳定后点选；记录 `#literature-map-svg.getBoundingClientRect()`、`#literature-map-viewport.getAttribute('transform')`、`[data-node-id]` 数量/边界、`getComputedStyle` 以及 `pageerror`。不需要截图用户桌面，也不需要访问私人数据或网络。

## 3. 圆的填充、边框、opacity、分组颜色与 PNG

### 已有渲染语义

- 默认圆：`.literature-map-node circle` 为白色填充、`#8d80e6` 边框、2px；hover/focus 填充 `#eeeaff`；选中圆为 `var(--accent)` 填充、白色边框、2.5px，见 `frontend/literature-maps.css:74-82`。
- 圆本身没有 opacity；只有边有 `.literature-map-edge { opacity:.56 }`，引用/相似关系分别为紫色实线和淡紫色虚线，见 `frontend/literature-maps.css:74-77`。因此“圆太实/太蓝”不能通过现有 opacity 控件调整。
- 分组节点在 `renderGraph` 中给 `<g>`/`<circle>` 写入 `data-group-color`，并对圆同时写 `fill` 属性和 inline `style="fill:<group.color>;"`，见 `frontend/literature-maps.js:2357-2372`。inline fill 会覆盖 CSS 的 `.is-selected circle { fill:var(--accent) }`，所以选中的分组节点仍保持分组颜色，主要以白色描边表示选中。
- 颜色仅表示人工整理，代码在左侧分组标题、节点分组下拉框和保存提示中明确说明，见 `frontend/literature-maps.js:713-727,3574-3595,1472`；不代表学术立场。

### 现有 color input / 单点、多点、分组 UI

- **图谱单点选择**：只有 `state.selectedNodeId` 一个选中 ID；点击/键盘选择一个节点、打开详情、邻居标签模式也只围绕该 ID，见 `frontend/literature-maps.js:55-56,406-414,1103-1120`。当前没有“同时选多个图谱节点”的 state、checkbox 或批量分组动作。
- **多选只存在于预览候选**：`state.previewSelection` 是候选论文加入预览的 Set，最多 20 个；对应的是预览列表 checkbox，不是图谱节点多选，见 `frontend/literature-maps.js:1905-1970,1989-2000`。
- **创建分组颜色**：左侧地图列表的 `#literature-map-group-name` + `#literature-map-group-color` 是原生 `input[type=color]`，默认 `#8d80e6`；提交前仅接受 `#RRGGBB`，创建后发 `POST /{map_id}/groups`，见 `frontend/literature-maps.js:714-731,467-476,1485-1494`。
- **修改已有分组颜色**：分组列表每行有一个 `input[type=color]`，用户选择后立即通过 `PATCH /groups/{group_id}` 保存，见 `frontend/literature-maps.js:1404-1434,1509-1518`。
- **给节点分组**：右侧详情的单选下拉 `#literature-map-node-group` 通过 `PUT /nodes/{node_id}/group` 为一个节点设置/清除 `group_id`，见 `frontend/literature-maps.js:3574-3622`。当前没有批量给多点着色的既有入口。

### PNG 导出事实

- `buildExportSvg` 克隆当前 SVG，保留当前标签、节点半径、选中 class、分组圆的 inline fill 和当前 viewport transform；再注入导出专用 CSS、白色背景、标题和图例，见 `frontend/literature-maps.js:2760-2812`。
- 导出 CSS 将普通圆设为白填充/#8d80e6 边框，将选中态设为白色描边；但分组圆的 inline `style` 优先级更高，因此分组颜色会继续进入 PNG。边 opacity `.56` 也在导出 CSS 中保留，见 `frontend/literature-maps.js:2779-2792`。
- PNG 通过 `XMLSerializer` → `Image` → `canvas.toBlob('image/png')` 生成，固定 960×772 world export，高度额外含标题/图例，见 `frontend/literature-maps.js:2815-2855`。没有独立的圆填充/边框/透明度导出设置；PNG 反映当前图谱和当前标签/分组状态。

## 4. 全文页签、全文分析按钮与未 ready 反馈

### 已有逻辑

- 点选节点后，分析面板由 `renderNodeDetail` 追加；分析页签始终创建“摘要/全文”两个按钮，见 `frontend/literature-maps.js:3638-3740,3357-3389`。
- `analysisAvailable('full')` 只接受后端 `available_evidence_levels` 含 `full`，或旧字段 `fulltext_ready=true`，见 `frontend/literature-maps.js:3238-3247`。
- 未 ready 时，面板显示“全文索引尚未就绪；请先主动入库并等待索引完成。”（或安全映射后的实际原因）；“基于全文分析”按钮仍可点击，点击后由相邻 `role=status` 给出下一步；这是为避免原生 disabled 静默无反馈，见 `frontend/literature-maps.js:3270-3295,3419-3432`。
- 只有用户先切到“全文”页签且 full 不可用时，才会追加“获取并加入知识库”或“等待索引后重试/打开知识库处理全文”等来源动作，见 `frontend/literature-maps.js:3473-3508`。摘要页签上的全文分析点击反馈会提示先切到全文页签，这一行为由 `analysisUnavailableActionMessage` 生成。
- 当前已修复并有测试覆盖“full ready 不再显示错误未就绪文案”；现有 `tests/frontend/test_frontend_map_analysis_queue.py:50-78` 和本轮 `test_frontend_map_analysis_actions.py` 覆盖的是文本/请求行为，不是视觉显著性。

### 为什么截图中可能“不明显”（代码事实，不断言用户实际根因）

- 未 ready 的 tab 没有 `disabled`、`aria-disabled` 或状态徽标；它与 ready tab 外观相同，只有点击后或切换后才看见原因/恢复入口。
- 说明文字和 action feedback 共用 9px monospace 的 muted/琥珀色样式，见 `frontend/literature-maps.css:104-110`；在右侧窄详情面板中不属于醒目的卡片/警告区域。
- 摘要页签默认只展示“当前没有可用分析依据/全文索引尚未就绪”文本，不展示“获取并加入知识库”按钮；恢复按钮被有意放在全文页签路径中。因此功能存在，但发现路径是“读提示 → 点全文 → 再点恢复”，容易被误认为无入口。

## 5. `indexed` / `not_imported` 英文状态的根源

- `mapStatusLabel` 只覆盖地图/作业/分析常见词（`generating/ready/partial/failed/stopped/queued/running/completed`），没有 `indexed`、`not_imported`，见 `frontend/literature-maps.js:342-353`。
- 详情状态徽章无条件调用 `renderStatusBadge(node.download_status || 'not_imported')`，见 `frontend/literature-maps.js:3655-3659`；因此后端返回 `not_imported` 或 `indexed` 时会直接把英文原值作为 badge 文本显示。
- 下方“已加入知识库”文案是另一条 `document_id/indexed` 分支，见 `frontend/literature-maps.js:3688-3697`，不能覆盖上方 badge 的英文。`importStatusMessage` 也复用同一个未覆盖 import 状态的 `mapStatusLabel`，见 `frontend/literature-maps.js:595-599`；`not_imported` 还被特意隐藏为空。
- 这是确定的前端映射缺口，不是截图误读。最小修复候选是为入库状态单独建立 import label helper（至少覆盖 `not_imported/indexed/queued/running/importing/downloading/validating/indexing/pending/failed/waiting_login/completed/partial`），让状态 badge、状态行和恢复入口使用同一中文词汇；不要把 import 状态直接混入地图 job 的 `mapStatusLabel`，避免跨域状态语义冲突。

## 建议交给 root 的决策/验收点（不替用户确认）

1. 先确认净空定义 A/B/C、约束范围（全部/可见节点）、生效时机（只对缺失位置/显式重新布局/拖动后是否不动）；确认前不实现布局算法。
2. 对“点选后空白”先按宽度/断点/详情抽屉矩阵获取 DOM 与 pageerror 证据；当前本地夹具未复现，不能把“无 ResizeObserver”直接写成根因。若确认是 resize 造成，最小修复优先是尺寸稳定后一次性 fit/重算边界，并保持用户保存视图不被静默覆盖。
3. 若要改善全文 discoverability，验收应同时断言：未 ready tab 有明确状态标识；摘要页点击全文分析在原地可见下一步；切到全文后恢复按钮位于同一视觉块；ready 场景没有“未就绪”文案；不可用路径不发 analysis/conversation POST。
4. 对颜色验收区分默认/hover/selected/grouped/PNG 五态：选中仍以描边表达；分组颜色是否覆盖 selected fill 需明确；PNG 应与当前分组色、标签模式、边 opacity 一致；不新增学术立场颜色语义。
5. 对状态验收至少覆盖 `not_imported`、`queued/running`、`indexed`、`failed`、`waiting_login`，统一中文文案；现有“已加入知识库 · 文档 ID”仍保留，不以 badge 翻译替代真实索引状态。

## 本轮交接

- 报告：`docs/sdd/plans/043/2026-10-27-map-usability-frontend-findings.md`
- 进展日志：`.codebuddy/agent-logs/spec-043/task-00/frontend-reviewer/20261027-002023.md`
- 未修改业务代码、测试、Spec 状态、Git、服务、部署或线上状态。
