# Spec043 五处修改只读事实核查

日期：2026-10-24
范围：只读核查 `frontend/literature-maps.js`、`frontend/app.js`、地图分析相关后端/API 与前端/地图测试；未修改业务代码、未启动服务、未访问外网。

## 结论摘要

| 修改点 | 当前事实 | 主要缺口/需裁决 |
|---|---|---|
| 地图默认作者年份标签 | 已有 `nodeLabel()`，取第一作者+年份，缺失时回退标题/node ID；但图上只给选中节点或每 25 个节点绘制 `<text>` | “默认标签”是所有节点可见，还是保留稀疏策略；第一作者显示、截断和缺字段回退规则需定 |
| 引用数 log 节点尺寸 | API/MapPaper 已带 `citation_count`，详情也展示；图节点半径目前固定 8，选中 11，完全未用引用数 | 需定 log 底/最小最大半径、缺失/0 值、选中态是否叠加，以及是否增加图例/可访问文本；前后端接口无需新增字段 |
| 摘要分析自动触发 + 重新生成 | 当前明确是用户点击触发；打开节点只 GET 历史/来源状态，不 POST；全文就绪也不会自动创建新分析 | 这是对 Task05/Spec043 既有“用户点击才分析、全文就绪只提示可重新分析、旧结果保留”的范围变更，需确认自动触发时机、重复/幂等、是否自动耗模型；“重新生成”是否仅新版本摘要分析 |
| 全文分析点击无反应 | `基于全文分析` 在 `full` 不可用时 `disabled=true`，因此点击不会进入 handler；状态提示直接渲染后端 `unavailable_reason`，而后端常返回 `MAP_FULLTEXT_UNAVAILABLE` 机器码 | 需确认改为可点击并展示可行动引导，还是继续禁用但旁边显式说明；引导至少应覆盖“加入知识库 → 等待索引 ready → 重新打开/刷新详情”，不可把 metadata/indexed 当全文 ready |
| 关于本篇提问预填 prompt | 当前只 POST 创建/复用 map/node conversation，再把 `conversation_id` 交给既有导航；没有 prompt 字段、没有写入初始 user message、没有给输入框预填内容 | 需定预填文案、摘要/全文依据级别和“仅预填不发送”边界；若自动发送则会新增消息/模型消耗，超出当前会话桥接契约，需要单独确认 |

## 逐项证据

### 1. 作者/年份标签

- `frontend/literature-maps.js:302-310` 的 `nodeLabel(node)` 取 `authors[0]` 与 `year`，拼为 `作者, 年份`；两者都缺失时回退 `title`、再回退 `node_id`，并截断至 38 个字符。
- `frontend/literature-maps.js:2064-2068` 只有 `selected || index % 25 === 0` 才创建 SVG 文本标签，因此并非每个节点默认可见标签。
- `frontend/literature-maps.js:2056` 的 `aria-label` 使用完整标题或 node ID；详情 `:2844-2852` 仍单独显示作者、年份和摘要。
- 后端无需补模型字段：`backend/app/literature_maps/domain/models.py:94-145` 的 `MapPaper` 已有 `authors`、`year`，`to_dict()` 原样输出。
- Spec043 `:84-86` 约束短标签语义为作者/年份，缺作者/年份回退标题短标签；没有规定所有节点都必须绘制标签。

可复用入口：仅需前端 `nodeLabel()`/`renderGraph()` 的呈现决策；若用户要求所有节点标签，需同时考虑 200 节点重叠、缩放和移动端性能。

### 2. 引用数 log 节点尺寸

- `frontend/literature-maps.js:2050-2059` 绘制节点时半径只有 `selected ? 11 : 8`，没有读取 `node.citation_count`，模块中没有 `Math.log`/log 尺寸函数。
- `frontend/literature-maps.js:2844-2846` 详情字段已显示 `引用数`，说明字段已进入节点 DTO。
- `backend/app/literature_maps/application/service.py:273-281` 图查询返回 `store.list_nodes(...).to_dict()`；`MapPaper.to_dict()` 在后端 `:126-145` 输出 `citation_count`。
- Spec043 `:25` 将引用数纳入节点 metadata，`:85-86` 要求详情显示可取得引用数及来源；关系章节 `:71-77` 只规定引用边语义，没有尺寸公式。

可复用入口：前端本地计算尺寸即可，不需要修改 `/graph` 合同。必须先裁决 `null/0`、极端引用数、半径上下限、选中半径和图例文案。

### 3. 摘要自动触发与重新生成

- `frontend/literature-maps.js:2467-2500` 选中节点后先 GET 节点，再调用 `loadNodeAnalyses()`；没有调用 `startAnalysis()`。
- `:2740-2755` 的 `loadNodeAnalyses()` 只 GET `/{map_id}/nodes/{node_id}/analyses`，填入历史和 `source_status`。
- `:2675-2684` 的“基于摘要分析”仅绑定 click handler，`startAnalysis('abstract')` 在 `:2960-2989` 由用户点击触发 POST。
- `:2686-2690` 的会话按钮虽然自动绑定 click，但不是自动分析；`:2694-2709` 只读历史版本。
- 后端 `backend/app/literature_maps/application/analysis.py:223-254` 仅在收到显式 `request_analysis()` 后创建分析 job；`routes_literature_maps.py:354-374` 也是 POST 分析入口，没有 GET 副作用。
- Task05 明确约束见 `docs/sdd/plans/043/task-05-analysis-conversations.md:33-40`：点击触发；全文就绪只提示可重新分析，用户点击创建新结果并保留旧结果。前端交接报告 `docs/sdd/plans/043/artifacts/task-05/frontend-report.md:9-15` 亦明确“打开详情不创建任务”“全文就绪只显示可重新分析入口”。
- Spec043 `:31` 标记 `MapAnalysis` 为用户触发，`:90-92` 要求全文就绪提示主动重新分析、保留旧摘要，不自动覆盖或自动消耗模型。

因此“自动触发摘要分析”不是现有实现内的小修，至少会改 Task05/Spec 的用户行为和耗用边界；应先在 Spec 中明确自动触发仅首次无结果、还是每次打开/来源变化均触发，以及是否允许后台自动消耗模型。

### 4. 全文按钮无反应与引导

- `frontend/literature-maps.js:2603-2607` 只有 `available_evidence_levels` 含 `full`（或兼容的 `fulltext_ready`）才认为全文可用。
- `:2680-2683` 将全文按钮设置为 `disabled = !analysisAvailable('full') || ...`，disabled 元素不会触发 `:2683` 的 click handler；这解释了“点击无反应”。
- `:2609-2612` 虽有 `analysisUnavailableMessage('full')`，但 `renderAnalysisPanel()` `:2665-2669` 实际直接把 `sourceStatus.unavailable_reason` 原文放进 DOM，没有调用该映射函数。
- 后端 `backend/app/literature_maps/application/analysis.py:76-102` 在摘要/全文都不可用时把 `unavailable_reason` 设为 `MAP_ABSTRACT_UNAVAILABLE` 或 `MAP_FULLTEXT_UNAVAILABLE`；全文 gate `:104-180` 还要求 owner/project、source hash、v1 manifest ready/100%/verified、generation 和 fingerprint 全部通过。
- 后端分析路由在 `backend/app/api/routes_literature_maps.py:343-351` 返回 `source_status`，POST 分析在 `:354-374`；不可用 POST 会稳定报 `MAP_FULLTEXT_UNAVAILABLE`，不是无响应。
- 现有 fixture 把不可用原因写成中文 `全文索引尚未就绪`（`tests/frontend/fixtures/literature_map_component.html:292-303`），所以前端契约测试 `tests/frontend/test_frontend_map_analysis_contract.py:43-49` 只能证明 mock 中文提示，未覆盖生产机器码。

可复用入口：保留后端严格全文证据门禁；前端可用 `analysisErrorMessage()` `:2614-2619` 的中文映射，且在禁用按钮旁渲染明确的“加入知识库并等待索引完成后刷新/重开详情”指引。若决定允许点击 disabled 状态，需要定义点击是否只展开引导而不 POST。

### 5. “关于本篇提问”预填 prompt 与 QA 自动发送事实

- `frontend/literature-maps.js:3007-3024` 的 `createNodeConversation()` POST body 只有 `evidence_level` 和 `idempotency_key`；成功后只调用 `navigateToConversation(payload.conversation_id)`。
- `navigateToConversation()` `:2992-3005` 最终调用 `window.openConversationFromWorkspace(conversationId)`。
- `frontend/app.js:3272-3277` 的 `openConversationFromWorkspace(conversationId)` 只 `showView('chat')` 并 `openConversation(conversationId)`，签名不接 prompt；`openConversation()` `:2983-3031` 只加载已有会话/消息，不填 `#question`。
- 普通发送路径在 `frontend/app.js:3418-3585`，只有 `sendConversationMessage()` 才 POST `/api/conversations/.../messages`；表单提交 `:3588-3590` 先读 `input.value`，没有地图入口自动调用。
- 后端 `backend/app/literature_maps/application/analysis.py:354-440` 只创建/复用 conversation 和 binding，`memory.create_conversation()` `:418-423` 未创建 user message；API 请求模型 `backend/app/api/routes_literature_maps.py:137-141` 也没有 prompt/content 字段。
- 当前前端 QA `tests/frontend/test_frontend_map_analysis_contract.py:65-70` 只点击“关于本篇提问”，断言 conversation POST 的 `evidence_level`、幂等键和导航 ID；没有断言 prompt，也没有断言 `/messages` 或自动发送。fixture `tests/frontend/fixtures/literature_map_component.html:320-326` 同样只记录 conversation POST。
- 后端会话测试 `tests/literature_maps/test_map_analysis_api.py:80-92` 只验证 conversation 创建/幂等；没有初始消息。`tests/literature_maps/test_map_conversation_binding.py` 的消息测试均是先手工创建 user/assistant，再验证上下文门禁，不是地图入口自动发送。

推荐的最小边界是“打开会话后只预填输入框，不发送、不写消息”，但文案、是否包含标题/摘要级或全文级说明仍需用户裁决；若要自动发送，应视为新的公开行为并补 API/UI/消息级验收。

## 现有 QA 覆盖判断

- 已覆盖：人工点击摘要分析、异步轮询/失败重试、历史版本查看、会话创建与导航、全文不可用时按钮 disabled（均为 mock/fixture；`tests/frontend/test_frontend_map_analysis_contract.py`）。
- 未覆盖：摘要分析打开详情自动触发、全文不可用机器码的可读引导、引用数驱动半径、所有节点默认标签、会话 prompt 预填，以及任何地图入口自动发送 `/messages`。
- 既有 Task05 报告声称的真实摘要/全文 API PASS 只证明当前显式 POST/异步 job/会话绑定合同，不证明上述五项新行为。

## 需用户/架构师先裁决的边界

1. 标签：所有节点常显还是保留每 25 个/选中节点；多作者是否显示第一作者或 `et al.`；标签长度和缺字段策略。
2. 尺寸：`log1p(citation_count)` 的底数/半径上下限、`null/0`、选中态和图例/无障碍说明。
3. 自动摘要：首次无结果自动触发还是每次打开触发；是否允许后台耗模型；来源版本变化如何去重；“重新生成”是否总建新版本并保留旧结果。
4. 全文引导：继续 disabled + 明文引导，或允许点击只展示引导；索引等待期间是否提供刷新/重新读取按钮；严禁放宽后端全文证据门禁。
5. 提问：预填具体文案、是否保留用户已有草稿、是否仅摘要/全文依据提示；默认不自动发送。若改为自动发送，需明确用户确认、失败重试和消息持久化验收。
