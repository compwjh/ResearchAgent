# Task11 前端实施准备（只读梳理）

日期：2026-10-28  
范围：只读核对已确认 Task11 计划、接口合同和前端接缝；未改业务代码，未运行测试、Git 或部署操作。后台实现由后端角色负责。

## 现有前端接缝

- `frontend/literature-maps.js` 是原生 JS 单模块。`request()`（约241行）统一发相对 `/api/literature-maps/{map_id}` 的请求；UI 由 `createElement()` 构造并通过 `textContent` 填入动态文本，不应引入新框架或 `innerHTML`。
- 单篇入口在 `renderNodeDetail()` 约5021–5027行，目前分别创建“参考文献”和“引用它的论文”按钮，分别调用 `openPreview(kind, node_id)`。统一入口可在这里替换为“扩展关联论文”。
- 当前预览是单实例：state 约92–103行只有一个 `preview`、`previewId`、`previewKind` 和一个按 `candidate_id` 记忆的 `previewSelection`；`renderPreviewPanel()`（2538行起）已经处理候选、已有节点、移除墓碑、容量和确认操作。`renderShell()` 约1245–1254行创建现有 `#literature-map-preview-panel`，无需另建面板框架。
- `openPreview()`（约2670行起）当前 `POST /previews` 不传分页参数；`loadPreview()` 用现有 GET 读取持久预览；当前 `applyPreview()` 仍走单预览 `/previews/{id}/apply`。409 后的 `repreviewAfterConflict()` 会重开来源预览，不保留已加载候选快照，需由显式重核流程取代。
- 草稿当前通过 `previewStorageKey(mapId)` / `persistPreviewSession()`（2464–2479行）只存一个 preview id、kind 和 seed。已有 `mapOwnerId()` 可取得地图 owner；草稿键与内容需扩大到 owner/map/seed、两侧 preview id、活动页签和两侧各自的 candidate ID 选择。恢复时只 GET 持久 preview，不自动 POST 来源请求。
- 布局可复用 `loadMapGraph()`（2386–2422行）和 `layoutPendingNodes()`（3001行起）：已有坐标从图中载入，缺少坐标的新节点按现有间距规则确定性地在已有节点周围布点。地图打开时 `initialFitPending` 才会初次适配；确认新增后应保留现有坐标与 viewport，不触发旧节点重排或强制切换视角。
- 现有摘要队列 `renderAnalysisQueue()` / `pollAnalysisQueue()`（4225–4338行）展示地图级队列并提供地图级暂停、继续、重试；`ensureAnalysisQueue()`（4341行起）会按全图 ensure，不应借它为批次补入旧节点。Task11 批次进度应单独读取 batch job，再沿用地图级队列控制入口。
- CSS 专属规则在 `frontend/literature-maps.css` 145–168行；页面在 `frontend/index.html` 9行和798行分别载入 CSS 与 JS。改动后同步提升这两个资源 URL 的版本号。DOM 与样式必须继续使用 `#literature-maps-view` 作用域。

## 两个小实施阶段

### 阶段一：统一预览、跨页签选择、分页和草稿

**文件接缝：**`frontend/literature-maps.js` 的单篇详情入口、预览 state/render/open/load/poll/sessionStorage 函数；`frontend/literature-maps.css` 的预览面板规则；`frontend/index.html` 的两个资源版本号。保留当前 DOM 安全构造、候选已有/墓碑状态及单图200节点容量提示。

1. 单篇详情只展示“扩展关联论文”，打开同一个面板，页签为“参考文献／引用本文”。按接口合同对同一 seed 分别创建两条 references/citations 预览；某一侧失败不遮挡另一侧候选或选择。切页签不清空另一侧状态。
2. 两侧候选选择按各自 preview 保存 `selected_candidate_ids`，总数按稳定 `identity_key` 去重后显示并限制最多20个新增身份；不能只留下一个方向的候选 ID，否则同论文在两侧均被选中时会丢失一条真实引用边。墓碑仍只提供显式恢复，已有节点不计为新增。
3. 创建 preview 时仅发送合同冻结的分页选项（version 1、page_size 50、max_candidates 500）。新增“加载下一页”与失败页显式重试按钮，调用 `POST /previews/{preview_id}/load-more`，携带 `expected_preview_revision`、`retry_failed` 和幂等键。显示服务端 `loaded_count/total/has_more/state/limit_reached`；`total=null` 显示未知，不把未知当0；到500明确提示未穷尽。GET/重开不得自动续页。
4. 草稿用 owner/map/seed 隔离，保留两侧 preview id、当前页签和每侧选择。重开只读取服务器 preview 快照和本地草稿，不重新请求来源；切地图、切 seed、owner 不一致时不复用草稿。

**前端能力验证建议（不在本准备任务中执行）：**扩展 `tests/frontend/test_frontend_literature_map_expansion.py` 及其 `tests/frontend/fixtures/literature_map_component.html` mock 场景，覆盖双方向均创建且 seed 相同、双页签切换保留选择、同 identity 跨方向计1但保留两个候选 ID、20/21 unique 边界、50条续页/500上限/未知总量、单侧429或失败不阻挡另一侧、重开只 GET、owner/map/seed 草稿隔离、失败页只在显式点击后重试。测试名称按能力命名，不带 Spec/Task 编号。

### 阶段二：冲突重核、单事务确认、布点和批次进度

**文件接缝：**继续扩展 `literature-maps.js` 的确认/409处理与图加载；复用 `layoutPendingNodes()`、现有 `#literature-map-preview-panel` 和 `#literature-map-analysis-queue`，新增的批次进度 DOM/CSS 仍放在既有地图面板与样式作用域中；同步 `index.html` 资源版本。

1. 批量确认只调用合同的 `POST /previews/batch-apply`，一次传 `expected_revision`、幂等键及一至两组 `{preview_id, expected_preview_revision, selected_candidate_ids}`。不串行调用两个旧 `/apply`。
2. 收到409时保留草稿与候选快照；按合同先 GET 当前 graph 和相关 previews，再由用户显式触发 `POST /previews/revalidate`。展示有效/无效选择及变化摘要，失效选项不得静默丢弃；用户处理并再次确认后才调用 batch-apply，不自动重试或只替换 revision。
3. 成功后读取 batch 返回的新节点 ID、刷新 graph，并仅为无位置的新节点复用 `layoutPendingNodes()`；旧节点坐标、分组、颜色、筛选和 viewport 均不变。标记本批新增点并提供“查看新增论文”入口；若当前显示筛选使新节点不可见，说明被隐藏，不自动改筛选或强制缩放/平移。
4. 用合同 `GET /jobs/{batch_job_id}` 的批次投影显示每阶段 counts 与失败项，区分 metadata pending/running/failed、identity unresolved、无摘要跳过、analysis queued/running/completed/failed。继续使用现有分析队列的地图级暂停/继续；仅通过批次 job 的受限 metadata retry 和既有分析 ID 重试修复对应失败步骤，避免调用全图 `analysis-queue/ensure`。

**前端能力验证建议（不在本准备任务中执行）：**在同一组件测试中覆盖409后 GET→显式 revalidate→展示变化→再次确认的顺序与请求体；确保一次跨侧 batch-apply、重复确认幂等、无效选择不静默丢弃；成功后旧坐标/视口/分组/颜色保持、新点靠近 seed 且不重叠、隐藏筛选时提示且筛选不变；批次各状态及单侧失败、缺摘要与获取失败的区分、只重试失败单元、暂停期间状态展示。真实 API/browser E2E 按已确认 Task11 验收合同由后续验收执行，本报告不把 mock 测试当作 API 证据。

## 后端依赖与边界

前端不得假设新能力已部署。阶段一依赖已确认合同的 v8 `preview_revision`/pagination 字段、两个 preview 创建返回值、`load-more` 与 GET 持久快照；阶段二依赖 `revalidate`、原子 `batch-apply` 响应的 node IDs/batch job ID，以及 `GET /jobs/{batch_job_id}` 的批次投影。具体请求字段与错误码以 `task-11-interface-contract.md` 为准；不在前端另造路由、worker、批次模型或持久化格式。后端尚未交付时，前端实现应按分阶段依赖停在其接口可用边界。

## 核对依据

- `docs/sdd/plans/043/task-11-paper-expansion.md`：产品合同第1–12项、实施顺序及验收边界。
- `docs/sdd/plans/043/task-11-interface-contract.md`：第2节 create/load-more/revalidate/batch-apply API，第3节批次摘要/分析投影与重试，第4–5节错误和 worker 生命周期。
- 本准备报告不构成实现、测试、验收或部署证据。
