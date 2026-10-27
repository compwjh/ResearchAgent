# 文献地图论文扩展现状事实核查

日期：2026-10-27。只读核对了 Spec043、Task04/Task09 文档和指定的地图前后端实现；没有读取 raw JSON / coverage artifact、`.env`，没有运行测试或修改业务代码。

## 当前入口与操作

- 节点详情里的“参考文献”和“引用它的论文”分别调用 `openPreview('references', node_id)`、`openPreview('citations', node_id)`；地图工具栏另有“继续搜索”和“刷新预览”两个入口。四类操作共用同一预览面板和 `/previews` API，只是 `kind` 不同。[frontend/literature-maps.js:1421-1423, 2504-2506, 5010-5017](frontend/literature-maps.js)
- references/citations 预览读取所选节点的 Semantic Scholar Graph 关系；确认后，references 建立“所选节点 → 候选节点”的引用边，citations 建立“候选节点 → 所选节点”的引用边。界面图例也将实线箭头定义为“引用者 → 被引用者”。[service.py:608-623, 785-795](backend/app/literature_maps/application/service.py) [literature-maps.js:1237](frontend/literature-maps.js)
- 预览是持久候选快照；生成预览不改图，确认通过 `selected_candidate_ids`、`expected_revision` 和幂等键应用。地图 revision 或预览基准已变化时返回冲突，不覆盖并发操作。[routes_literature_maps.py:514-553](backend/app/api/routes_literature_maps.py) [service.py:727-807](backend/app/literature_maps/application/service.py) [store.py:2076-2103](backend/app/literature_maps/infrastructure/store.py)

## 候选列表、多选与限制

- **多选和确认已存在**：候选逐条显示复选框；“已在当前地图”项不可选；墓碑项不可作为新增项选择，只能走“显式恢复”；选中后用“确认加入”提交。前端上限为每次 20 篇和地图剩余容量，后端再次执行单批 20、整图最多 200 的检查。[frontend/literature-maps.js:2574-2633, 2657-2669](frontend/literature-maps.js) [service.py:767-768](backend/app/literature_maps/application/service.py) [store.py:2096-2103](backend/app/literature_maps/infrastructure/store.py)
- **候选分页目前不存在**：`GET /previews/{preview_id}`返回预览对象，其中含完整 `candidates` 数组；前端对该数组整体 `forEach` 渲染。列表是单列、可滚动区域，CSS 高度上限 210px；未看到候选页码、下一页或候选分页 API。前端的最多 50 页只用于重开地图时扫描历史事件以找回预览，不是候选分页。[routes_literature_maps.py:531-537](backend/app/api/routes_literature_maps.py) [models.py:243-270](backend/app/literature_maps/domain/models.py) [literature-maps.js:2580-2583, 2764-2791](frontend/literature-maps.js) [literature-maps.css:158-164](frontend/literature-maps.css)
- **候选数量边界**：references/citations 每次只请求 Graph 的 `offset=0, limit=100`，预览函数不继续读取 `next_offset`；候选响应随后最多保留 200 项。主题预览使用地图 `requested_count`（建图限定 20/30/50）；刷新预览最多覆盖地图现有 200 个节点。[service.py:47-50, 602-623, 866-879](backend/app/literature_maps/application/service.py) [semantic_scholar_metadata.py:360-394](backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py)
- 因而当前要加入超过 20 篇的关系候选，需要分次预览/确认；超过首个 100 条来源关系的候选不会从当前这次关系预览中出现。地图满 200 篇时可加入数为 0。

## 确认后摘要分析是否自动进行

- **会自动触发**：候选应用写入成功后，如果本次有新增或刷新节点，地图服务调用 `_enqueue_abstract_summaries`；运行时挂接的分析服务会对当前未移除节点执行幂等 `ensure_analysis_queue` 并调度后台队列。[service.py:808-815, 1216-1251](backend/app/literature_maps/application/service.py) [runtime.py:210](backend/app/literature_maps/application/runtime.py) [analysis.py:554-585](backend/app/literature_maps/application/analysis.py)
- 重开地图时前端也会显式 POST `/analysis-queue/ensure`，用于补齐旧图缺项；GET 本身不创建任务。[literature-maps.js:2335-2341, 4340-4354](frontend/literature-maps.js) [routes_literature_maps.py:404-419](backend/app/api/routes_literature_maps.py)
- 队列为后台持久队列，有完成/排队/运行/失败/跳过计数、暂停/继续/重试；无摘要的论文会标记跳过，不自动查元数据补摘要，也不以标题替代摘要分析。它只做摘要分析，不触发全文下载或导入。[literature-maps.js:4237-4277](frontend/literature-maps.js) [analysis.py:554-585](backend/app/literature_maps/application/analysis.py) [task-09-interface-contract.md:39-52](docs/sdd/plans/043/task-09-interface-contract.md)

## 可复用的关系、身份、布局与限流合同

- **身份去重**：身份键优先 DOI，其次 arXiv，再次 Semantic Scholar paper ID；候选 ID 由身份键哈希得到。预览与现有节点身份匹配，重复项标为已存在，墓碑项标为已移除；存储另有 `(map_id, identity_key)` 唯一约束。用户显式恢复墓碑是单独操作。[identity.py:13-55](backend/app/literature_maps/domain/identity.py) [service.py:826-847](backend/app/literature_maps/application/service.py) [store.py:144-162](backend/app/literature_maps/infrastructure/store.py)
- **局部布局**：新增节点以无位置记录写入。重新读取图时，已有节点使用服务器保存的位置；只有缺位置的新节点进入 pending layout，并以已有节点的位置作为占用区布点。因此新节点会获得布局，已有位置不被整体重排。刷新更新白名单仅包括论文元数据，服务端保留节点位置、分组及知识库关联。[store.py:2104-2112](backend/app/literature_maps/infrastructure/store.py) [literature-maps.js:2385-2415, 3000-3052](frontend/literature-maps.js) [task-04-expansion-recovery.md:33-38](docs/sdd/plans/043/task-04-expansion-recovery.md)
- **429 的两层行为要区分**：Semantic Scholar client 共享进程内 1 秒限流器；请求内部最多重试一次，使用有 30 秒上限的 Retry-After/指数延迟。[semantic_scholar_adapter.py:29-30, 33-72, 75-99](backend/app/paper_discovery/infrastructure/semantic_scholar_adapter.py) [semantic_scholar_metadata.py:216-244, 258-291](backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py)
- 初始建图的引用采集把剩余限流错误记为可重试失败单元；job retry 选择 references 阶段，只重试失败/缺失单元并保留成功单元。[service.py:185-206, 1295-1345, 423-484](backend/app/literature_maps/application/service.py)
- 但单节点 references/citations **候选预览**在 client 内置的一次重试耗尽后，只把错误码放到预览 `warnings`；该预览仍可完成，没有逐页补齐或单候选重试控件。用户可再发起新的预览。Task04 计划要求呈现等待退避和失败补缺入口，Spec也要求限流有限退避；这些文档合同不能推导为当前候选预览已实现自动补缺。[service.py:608-623, 866-879](backend/app/literature_maps/application/service.py) [literature-maps.js:2562-2563, 2625-2639](frontend/literature-maps.js) [task-04-expansion-recovery.md:36-38](docs/sdd/plans/043/task-04-expansion-recovery.md) [043-literature-map-topic-exploration.md:114-118](docs/sdd/specs/043-literature-map-topic-exploration.md)

## 对“统一扩展入口 + 两列多选加入 + 后台分析”的缺口判断

- **可直接复用**：preview/apply API、持久候选快照、通用 `kind` 预览组件、复选框多选、显式确认、revision 冲突保护、身份去重、墓碑恢复、局部布局保留，以及确认后自动摘要队列。摘要分析后台本身不是待新增功能。
- **前端可见缺口**：入口目前分散在“继续搜索”“刷新预览”和节点详情的“参考文献/引用它的论文”；需要新增统一入口及其操作选择 UI。候选列表目前单列滚动，非两列；改成两列主要是列表呈现变化，但若要真正候选分页，还需要明确仅前端分批展示现有快照，还是同时增加服务端分页接口。
- **可能的后端缺口**：如果“统一扩展”意味着从多个来源节点合并候选、或越过首个 100 条 Graph 页面继续拉取，现有 API/实现没有对应请求契约；需要明确来源选择、合并时关系归属、候选上限和分页/继续语义。若只是在一个已选节点下选择 references 或 citations，则可沿用现有 `kind` 与接口。
- **摘要边界**：确认新增后已自动分析其保存的非空摘要；无摘要节点会跳过。若预期“扩展加入后必定自动补摘要再分析”，那是现有自动摘要合同明确不做的事情，需另行确定来源获取/失败/限流语义。
- **Spec 范围提示**：Spec043 原产品步骤已写明可从节点选择“参考文献/引用它的论文”、预览勾选并确认；但 2026-10-27 当前确认的 Task10 修订目标是布局、节点配色、全文状态等，没有列入统一扩展入口或候选列表改版。因此，能否作为 Task10 的小范围 UI 调整，取决于 grill 对行为是否变化的澄清，不能仅由旧 Spec 段落推定已获本轮确认。[043-literature-map-topic-exploration.md:130-145, 209-248](docs/sdd/specs/043-literature-map-topic-exploration.md)

## 尚不能从代码确定的产品含义

“统一扩展入口”是否只是集中选择四种既有操作，还是还要支持多节点来源、合并候选、连续分页或反复补齐；“两列表”是否要求候选服务端分页；无摘要候选是否需要先补元数据——现有资料不能判定这些含义，需在讨论中明确。以上未按假设写成已实现行为。
