# Spec043 技术评审：交互式文献地图与自动主题探索

## 评审元数据

- 评审对象：`docs/sdd/specs/043-literature-map-topic-exploration.md`（当前状态：待确认）
- 关联计划：`docs/sdd/plans/043/README.md`、`task-02-validate-feasibility.md`、`task-03-desktop-map-mvp.md`、Task04–08 依赖说明
- 评审角色：architect（独立技术评审）
- 评审者模型与分派方式：Luna xhigh；由主会话独立分派本评审，未分派编码、测试、网络调用或部署
- 评审时间：2026-10-19（Asia/Shanghai）
- 评审范围：复用边界、S2 请求能力、身份/关系方向、相似计算、持久作业/恢复、项目删除接缝、接口冻结和桌面 MVP 可实现性

## 结论

**通过（GO）。**

Spec 的数据模型、端点边界和任务拆分能够支撑独立的 `literature_maps` 领域；未发现需要打回 Spec 的 P0/P1 技术缺陷。Task02 可以先执行真实可行性门禁，Task03 只有在 v1 公开合同冻结后才开始前后端编码。当前结论不宣称外部 API、embedding 或浏览器已验证。

## 现有代码事实

### Academic Graph 请求能力

- `backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py:304-312` 的 `search_bulk` 将 `limit` 约束到 1–100 后作为 `/paper/search/bulk` 参数发送，因此 Spec 的 20/30/50 均在客户端允许范围内。
- 同文件 `:296-302` 的 `batch` 去重输入并允许单次最多 500 个 ID；`:343-377` 的 `graph_edges` 将分页 limit 约束到 1–100，并保留 offset/total/next_offset。
- `:236-245, :261-290` 在生产默认路径复用 `get_semantic_scholar_request_limiter()`，每次请求及重试都经过 limiter；其底层 `semantic_scholar_adapter.py:31-57` 将默认间隔设为 1 秒，`Retry-After` 由既有有限退避处理。地图不得新建第二套 limiter、provider 或无限重试。
- `semantic_scholar_metadata.py:160-211` 的解析器对 `citations` 取 `citingPaper`，对 `references` 取 `citedPaper`，并保留 `relation` 与 `source_paper_id`；这可直接作为地图引用方向归一化的输入，但 MapEdge 仍需自己的稳定身份和持久 provenance。
- 代码可证明“参数范围和请求形态支持 30/50”，不能证明 S2 对每个主题实际返回 30/50。Task02 必须捕获脱敏请求参数、响应数量、缺失字段、状态和论文 ID；返回较少应保持 partial。

### 目录身份与向量边界

- `backend/app/paper_discovery/domain/paper_discovery.py:87-112` 将 `CatalogPaper.catalog_paper_id` 定义为目录主键；`paper_discovery_store.py:211-232` 建立目录表，`:309-315` 建立 DOI 和 `(normalized_title, conference_id, year, authors_json)` 身份索引。该模型没有 S2 paperId 字段。
- 因此 Spec 第 35–36、99–101 行的分层是必要且可执行的：MapPaper 需保存 provider-specific external IDs 和 map-specific node_id；只有 DOI/arXiv 等确定匹配才关联 `catalog_paper_id`，标题近似只保留为未合并证据。
- `backend/app/paper_discovery/application/catalog_search_graph.py:145-180, :211-254, :316-377` 的 `CatalogRagAdapter` 复用 `embed_texts`，但面向已索引 `CatalogPaper` 的 `paper-discovery-catalog` 检索/重排，不是论文节点两两相似算法。Task03 应新增窄的 map similarity application seam：对节点的 title/abstract 文本批量求 dense 向量，计算余弦、记录 `basis/model_version/content_hash`，按 `>=0.75` 每节点 top-3 后无向端点排序去重；不得把 RAG 查询命中或个人 KB Collection 当作 MapEdge。

### 项目删除与前端壳

- `backend/app/api/routes_conversations.py:557-575` 的 `remove_project` 当前先解除 KB 文档关联，再以 fail-closed 方式删除研究任务，最后调用 `_repo().delete_project`；没有 literature map 解绑接缝。Task03 所列“项目删除置空地图 project”需在删除项目之前调用 owner-scoped map detach，并在失败时返回稳定 503、保留项目，不能让地图绑定指向已删除项目。
- `frontend/app.js:4993-5033` 的 `showView` 当前仅隐藏/显示 chat、models、memory、kb、papers、skill-tool；`frontend/index.html:94-102` 当前没有“文献地图”导航，底部 `app.js?v=57`/`styles.css?v=56` 是现有版本标记。Task03 需新增独立 view/组件、导航和事件加载，并同步静态资源版本与 DOM 契约；不应把现有深度研究视图伪装成地图。

## 技术核对矩阵

| 技术点 | 判定 | 依据与实施边界 |
|---|---|---|
| 与 Spec032 解耦 | 通过 | Spec 第 17–18、107、122 行明确不依赖 032 正式报告、不复用 Claim/Matrix 作为引用图、不恢复 032 全部开发；地图可独立迁移、路由和作业。 |
| S2 30/50 与分页 | 通过（待 Task02 实证） | 现有客户端允许 1–100；`search_bulk`/`graph_edges` 参数有效地传递到 provider，`batch` 允许 500。真实返回数量、限流和来源可得性尚未验证，属于 Task02 Go/No-Go 证据，不在本评审伪造。 |
| 共享限流/重试 | 通过 | 生产默认进程级 1 RPS，重试遵循有限退避与 Retry-After；地图只复用客户端，不另造 limiter。多进程共享限流已明确不在本期。 |
| 节点身份与目录关联 | 通过 | MapPaper 外部 ID/目录关联可空，S2 ID 不冒充目录 ID；确定 ID 匹配和不确定未合并语义已冻结。新 map-specific node_id 与 map_id 唯一约束须写入 Task03 v1 合同。 |
| 引用方向 | 通过 | 解析器已区分 citingPaper/citedPaper；MapEdge 持久化仍需固定“引用者→被引用者”、禁止自环、缺失不等于无引用，并保留 provenance。 |
| 相似边 | 通过（实现窄接缝） | Spec 已要求复用 embedding 但新增两两算法；现有 CatalogRagAdapter 不能直接承担该语义。若 embedding 不可用，引用图/元数据仍可用并标记相似待补算，不能降低阈值伪造成功。 |
| 200/20 预算 | 通过 | Spec 第 45、51、73 行及 Task03 第 31–41 行已冻结首批 20/30/50、每次新增 20、总节点 200；创建、preview apply、重试/恢复均需在事务内重检预算。 |
| partial 与恢复 | 通过 | MapJob 独立于既有 research task，包含 cursor/counts/failed_units；MapEvent 单调游标；Task03 持久检查点，Task04 补扩展/刷新/stop/retry/重启竞态。已有目录作业表只可借鉴模式，不能直接冒充 map job。 |
| owner/project/删除 | 通过（实现接缝已定位） | Spec 要求所有读写 owner 隔离、项目删除只解绑地图、地图删除不删共享资产；现有项目删除缺 map hook，Task03 需补 fail-closed detach，旧作业晚回调不得重建节点。 |
| API/事件合同冻结 | 通过 | Spec 第 41、57 行把详细请求/响应交给 Task03；Task03 第 29–37 行要求编码前冻结 schema_version、身份、revision、幂等、错误、事件合同，Task04–08 明确只做版本化扩展。 |
| 桌面 MVP 可用性 | 通过 | Task03 第 35–45 行覆盖持久图、真实主题创建、引用/相似分层、进度/partial/重试、SVG 交互、保存布局、主动入库桥接和真实 API/浏览器 smoke；第 102–114 行要求实际结果、版本、端口和非假图证据。 |

## Task02/Task03 必须执行的技术门禁

这些是已冻结目标的实现和验收条件，不是本轮 Spec 打回项：

1. **Task02 真实 API**：选择一个可复现主题，实测 `search_bulk(limit=30)`、`search_bulk(limit=50)`，至少一组 `graph_edges` citations/references；保存脱敏请求、响应数量、真实 S2 ID、引用方向、缺失/partial 和限流/重试结果。若核心来源或权限不可得，输出 No-Go，不降级成手工地图。
2. **Task02 身份与相似证据**：记录 DOI/arXiv/S2 与目录 ID 的确定匹配和冲突样例；用真实标题/摘要尝试 embedding，记录模型版本、阈值 0.75、真实相似对或明确 blocked，不把 synthetic SVG 性能样例当 API 成功。
3. **Task03 合同先行**：先落盘 `docs/sdd/plans/043/artifacts/task-03/interface-contract.md`，再分派 backend-dev/frontend-dev；合同必须覆盖 `schema_version`、map/node/edge/job/event/preview 身份、revision、幂等冲突、owner/project 错误和安全事件 payload。
4. **Task03 持久与隔离**：SQLite 增量迁移单事务幂等；地图读取不触发下载；停止/重启/旧作业晚回调不丢已完成节点或复活移除节点；项目解绑失败保留项目；MapEdge 不使用目录表外键替代 S2 identity。
5. **前端真实门禁**：新增导航与 view 后核对 `showView`、DOM class、`textContent`/输入安全、资源版本号；200 节点性能样例明确 synthetic，并另做真实 API 创建→图读取→保存重开浏览器 smoke。

## 评审边界与证据诚实声明

本评审只读取 Spec、plans/043、上述最小后端/前端代码及既有定向测试中的请求契约；未修改业务代码或测试，未运行 pytest，未调用 Semantic Scholar、Ollama、Qdrant 或其他网络服务，未部署、提交或推送。上述“通过”是技术方案与任务交接可行，不是运行时成功证明。

## 签字

- 评审人：architect（独立技术评审）
- 日期：2026-10-19
- 结论：**通过（GO）**

---

## 本轮 Task09 增量技术评审（2026-10-24）

### 评审元数据

- 评审对象：已确认 Spec043 本轮增量、`docs/sdd/plans/043/task-09-map-interaction-analysis.md` 及 [Task09 最小接口合同](../plans/043/task-09-interface-contract.md)
- 独立评审角色：architect（独立增量技术评审）
- 评审者模型与分派方式：Luna max（用户本轮临时指定）；由主会话 `/root` 独立分派，未分派编码、测试、模型调用、下载或服务操作
- 评审时间：2026-10-24（Asia/Shanghai）
- 实现事实：本轮未实现 Task09，未修改业务代码/测试，未运行 pytest、模型、下载、全量回归或服务，未调用网络；只追加本评审区段与接口合同
- 评审依据：`map-change-audit.md`、Task03 view 合同、Task05 analysis/conversation 合同，以及当前 `backend/app/literature_maps` 和 `frontend/literature-maps.js`/`app.js` 的最小相关实现

### 结论

**通过（GO）。**

现有分析、视图和会话接缝足以承接本轮增量；没有需要退回 Spec 的 P1 架构阻塞。可在合同落盘后立即分端实现：后端围绕既有 `MapAnalysis`/`MapJob`/`MapEvent`/executor 增加地图级摘要队列控制，前端纯图形部分可并行。

有一个必须在代码与验收前封住的 P1 实现风险：当前 `claim_analysis_job` 对已处于 `running` 的 job 会返回该 job，重复调用者仍可继续执行模型；这会破坏“逐篇、幂等、重启不重复”。它是现有实现缺口，不是本轮需求阻塞；按接口合同增加持久 worker token/等价租约、原子 claim 和 finish 校验即可在 Task09 范围内修复。若开发不封住该风险，应在验收判定 P1，不得以进程内锁或前端去重代替。

### 现有实现事实与接缝

| 接缝 | 已核对事实 | Task09 技术判定 |
|---|---|---|
| 分析 API 与版本 | `backend/app/api/routes_literature_maps.py:129-142,343-389` 已有分析请求/历史/详情；`analysis.py:223-315` 按来源版本创建 job 并在完成前复核来源；`store.py:816-891` 按 map/node/version/idempotency 保存。 | 复用现有显式分析 API；自动队列只调用同一 service/store 原语，不改变 `evidence_level`、source gate 或历史读取。 |
| 幂等与重试 | `store.py:816-891` 同 key 同参数返回同分析；`1547-1610` 的 child retry 可重置同一分析；显式新 key 才是新版本。 | 自动 ensure 使用稳定 key；retry 不新版本，手动 regenerate 才新版本，旧结果不可清空。 |
| 并发缺口 | `store.py:917-938` 的 `claim_analysis_job` 对已有 running job 仍返回 current，两个调用者都可进入 `run_analysis_job`；`runtime.py:182-210` 的共享执行器为有限 worker，不能替代持久 claim。 | 必须补原子 queued→running、持久 token/lease、finish token 校验；同一 map 只允许一个 running 摘要子 job。 |
| 停止与暂停 | `store.py:1587-1610`/现有 job stop 会停止 child 并将分析标为失败；它不等于“当前完成、后续等待”。 | 新增地图级 pause 状态；暂停只阻止下一次 claim，不调用 child stop。建图/聊天 job 不受影响。 |
| 恢复 | `analysis.py:460-465` 和 store recovery 会恢复 queued/running analysis；没有 map-level paused 状态。 | 聚合 MapJob 持久保存 active/paused；paused 重启仍暂停，active 只恢复孤儿未完成项，且不能重复提交。 |
| owner/迟到回调 | `analysis.py:76-102,115-180` 的来源状态和全文 gate 是 owner-scoped 本地读取；`finish_analysis` 仅接受 running 且未删除 map，删除/stop 后迟到结果不应成功写入。 | 队列读写沿 map owner join；移除节点、删除地图和旧 worker 回调均 fail-closed，不复活节点。 |
| GET 与下载边界 | `GET analyses` 只读取 source status/list；full source helper 读取本地文档/manifest，不执行下载；显式 import 是独立 POST。 | GET queue/analyses/graph/view 不能创建缺失项或提交模型；旧图补入队由显式 idempotent POST 完成。 |
| 当前图形实现 | `frontend/literature-maps.js:301-309` 只有首作者/年份及抽样标签；`:2021-2073` 半径硬编码 8/11；`:2230-2240` wheel 只改 scale 无锚点平移；现有 pinch `:2110-2137` 已保留中点。 | 标签、半径、wheel/toolbar/pinch helper 和 view 保存可独立实现；保留现有坐标系和 PATCH revision，不重写布局/分组。 |
| View 合同 | 当前 `PATCH /{map_id}/view` 接收 positions/viewport/filters/layers/expected_revision；前端 `state.view` 为 x/y/scale，旧图没有 label mode。 | 只在既有 `view_settings` 增加可选 `label_mode`，缺失默认 all；不新增第二个保存接口、不覆盖 positions/group。 |
| 全文 UI | `renderAnalysisPanel` (`frontend/literature-maps.js:2661-2737`) 已读 `available_evidence_levels`，但把 `unavailable_reason` 直接显示且 full 不 ready 时按钮禁用；没有可行动分支映射。 | 前端增加安全状态映射和现有导入/登录/上传/索引入口；full ready 前不发 POST，后端 gate 保持不变。 |
| 会话桥接 | `routes_literature_maps.py:392-415` 的 conversation POST 只接收 evidence/idempotency；`literature-maps.js:3007-3025` 只导航 conversation ID；`app.js:3272-3277`/`2983-3031` 现有导航与草稿加载没有预填参数。 | 保持后端 body/消息合同；增加可选 UI prefill 参数，非空草稿不覆盖，不调用 `/messages`。 |

### 技术门槛（直接交开发）

1. **持久队列形态**：使用一个 `MapJob(operation="analysis_queue")` 或同等的已版本化 MapJob 聚合记录，子项仍是既有 analysis jobs；聚合只存状态/计数/游标/失败 ID/幂等信息。不得新建第二个 scheduler、analysis store、chat 或 downloader。
2. **稳定复用**：以同地图规范化论文身份、现有 abstract `source_version`、服务端分析配置指纹和稳定幂等键命中同一分析版本。摘要/配置改变才新版本；无摘要 `skipped`，不调用模型；GET 不补入队。Task09 不新增跨 owner 全局结果缓存。
3. **claim/finish 原子性**：running job 不能被第二 worker 当作可执行返回；必须有持久 worker token/等价租约，finish/recovery 校验 token。服务重启后 active 恢复一次，paused 保持 paused；迟到 callback、移除/删除必须无写入效果。
4. **地图级串行**：同一 map 同时最多一个摘要 child running；不同 map 可复用当前有限 executor。429/瞬时错误使用持久有限退避；配置/鉴权错误置队列 paused 并输出安全行动码。pause 不停止当前 child，不影响建图/聊天；resume 才允许后续 claim。
5. **API 兼容**：保留 Task03 `schema_version="literature-map-v1"`、view `expected_revision`、Task05 分析/会话请求体、owner/project/full gate。队列读/控制接口只能是地图级增量读模型/控制，不得用新同义接口复制现有 node analysis 或 conversation。
6. **图形数学**：半径 helper 对有限非负 citation count 使用 `min(28,8+2*Math.log1p(n))`，未知为 base 8 并显示“未知”；selected 只描边。wheel 以 SVG pointer world coordinate 保持锚点，toolbar 以 viewport center，pinch 复用已有 midpoint；PNG 与当前显示共用渲染状态。
7. **全文与 Prompt**：状态码映射必须处理“无摘要/全文未入库/登录/上传/索引等待/重试”等实际分支；full ready 前只引导。Prompt 由前端预填标题/作者/年份、研究问题/方法/结论/局限/证据等级；不写入 conversation POST、不自动发消息、不覆盖旧 draft。

### 可并行的前端纯图形边界

后端队列实现尚未完成时，`frontend-dev` 可独立完成并自测以下范围：

- 默认 all / neighbors / hidden 标签模式及缺作者、缺年份、多作者回退；
- 引用数 radius helper、未知态、选中描边和现有 SVG/PNG 一致渲染；
- wheel pointer anchor、toolbar viewport-center anchor、已有 pinch midpoint；
- 现有 `PATCH /view` 的可选 `label_mode` 向后兼容读取/保存，保持 revision/positions/group/filters/layers；
- 全状态安全文案映射和 conversation prefill 的 UI-only seam（不增加服务器消息，不自动发送）。

以下不能由前端猜测或先行定制：队列总数/状态字段、pause/resume/retry 请求、自动摘要触发时机、source version、owner 错误、全文 ready 判定。队列面板只在后端读模型字段稳定后接入；前端不得用旧 `GET analyses` 的列表长度冒充队列进度。

### 技术评审签字

- 评审人：architect（独立增量技术评审）
- 日期：2026-10-24
- 结论：**通过（GO）**；无设计 P1 阻塞；现有 running-claim 竞态为必须在实现/验收前关闭的 P1 实现门槛。

---

## 本轮 Task10 独立增量技术评审（2026-10-27）

### 评审元数据

- 评审对象：`docs/sdd/specs/043-literature-map-topic-exploration.md` 的2026-10-27待确认增量、`docs/sdd/plans/043/task-10-map-usability.md`、Grilling及前后端事实交接。
- 评审者：`/root/map_usability_plan_review`；角色：`architect`。
- 临时模型：Luna xhigh（本轮用户临时指派）；原生分派：由主会话 `/root` 原生分派本评审任务。
- 评审时间：2026-10-27（Asia/Shanghai）。
- 实现事实：只读取必要的后端/前端源码与规划文档；未修改业务代码/测试，未运行测试、生产请求、模型/下载、服务、部署或 Git 操作。
- 评审依据：当前数据库迁移/事务、地图路由与 store、MapPaper/MapGroup 模型、视图/导出实现、SVG 布局/详情/状态实现，以及 Task10 明确的 schema/API/边界。

### 结论

**通过（GO；无设计 P1 阻塞；下列实现/验收门槛必须全部封住）。**

Task10 可以复用现有 `literature_maps` 领域、owner/revision、SQLite 事务、SVG 坐标系和全文 source gate；不需要第二套图谱、样式存储、布局库或下载器。当前存在若干明确的实现缺口，但都已被 Spec/Task10 定义为本 Task 的增量契约，而不是需求范围外阻塞。若开发遗漏任一原子性、迁移、只读或 evidence gate，验收应判 P1，不能用前端状态或合成夹具替代。

### 技术核对矩阵

| 技术点 | 判定 | 代码事实与实施边界 |
|---|---|---|
| schema 6→7 无损迁移 | 通过（P1 实现门槛） | 当前物理 schema 为整数 6（`backend/app/literature_maps/infrastructure/store.py:40`）；nodes 表没有 `color_override`（`:141-163`），初始化的增量 DDL/repair/version marker 在一个显式事务内执行（`:339-379`），事务异常回滚（`:87-97`）。必须以幂等、单调的 v7 增量增加 nullable override，旧行保持 `NULL`、稳定 ID/位置/分组/导出字段不丢；不能只改常量、重建/清空表或复用已占版本。API `literature-map-v1`（`domain/models.py:15`）保持不变，export 单独升级为 `literature-map-export-v2`。 |
| view/style 请求合同 | 通过（P1 实现门槛） | 当前 `MapViewRequest` 为 extra-forbid，仅有 positions/viewport/filters/layers/label_mode（`routes_literature_maps.py:60-68`）；store 合并 view JSON 并按 revision 更新位置（`store.py:598-626`），导出白名单也只含现有键（`service.py:1621-1643`）。应显式增加严格 `node_style={fill_mode: filled|outline, fill_opacity: finite 0..1}` 合同，禁止把 style/nodegap 塞进 filters；旧图读取默认 filled/0.3，未知字段/NaN/Infinity 拒绝，JSON v2 白名单明确增加 style/override。 |
| 节点 override、单组与批量原子 | 通过（P1 实现门槛） | `MapPaper`/SQLite 只有单 `group_id`（`domain/models.py:93-113`; `store.py:141-163`），现有 group 与 node-group 写操作都在 owner + expected_revision 事务中（`store.py:694-837`；`routes_literature_maps.py:101-127,311-322`）。新增 `PATCH /{map_id}/node-styles` 可复用该接缝，但必须先验证 map owner、revision、唯一 1–200 node IDs、未移除节点和 HEX/null，再在同一事务内全成或全不改；不得改 group_id、未选节点或返回部分成功。有效色必须在服务/投影与 SVG 两端一致为 `override → group → default`，null 才表示恢复跟随分组。 |
| 冲突与网络不确定性 | 通过（P1 实现门槛） | 现有 view 写入在 owner/revision 校验后更新，异常由事务 rollback（`store.py:601-626,87-97`）；前端 view 请求以 `state.map.revision` 写入并在异常时保留 dirty（`frontend/literature-maps.js:2683-2726`）。颜色批量请求必须保留 409/400/404 的现有错误合同；网络中断不能被客户端声称为回滚或“全部未改”，应显示结果待核对、GET 重读 revision/目标色后由用户显式重试，最近色仅在确认成功后写入。 |
| 半径感知布局与小画布 | 通过（P1 实现门槛） | 当前 `citationRadius` 已固定公式且上限 28（`frontend/literature-maps.js:384-388`），但 `initialPosition` 不读取半径（`:2284-2291`），`scheduleLayout` 只有有限微扰并最终自动 `scheduleViewSave`（`:2293-2316`）。实现必须在缺失位置/显式整理路径使用半径感知、有限、确定性布局；满足边缘净空≥2×较大直径，200 节点允许扩大 world bounds、缩放/平移浏览，不强塞小画布。整理预览必须暂停旧自动保存路径；确认才走现有 revision 保存，拖动/筛选不触发布局。 |
| 旧布局、详情视口与未复现空白 | 通过（P1 证据门槛） | 读取图时会保留保存位置，只有 `initialFitPending` 才 fit（`frontend/literature-maps.js:1726-1752`）；点选详情只改 selected/detail 并请求详情，不改 view/fit（`:2877-2912`）；resize 监听目前只处理移动断点开关（`:1041-1048,1173`）。应保留缩放/布局，仅在选中点不可见时做最小平移；必须先按真实宽度/详情开关采集 rect/transform/node bounds/pageerror。不得把缺少 ResizeObserver 或源码猜疑写成已经证实的根因，也不得因诊断而静默重排旧图。 |
| 地图样式与导出一致性 | 通过（P1 实现门槛） | 当前 SVG 分组颜色写在 inline fill，选中由描边表达（`frontend/literature-maps.js:2354-2371`），PNG 是克隆 SVG 后注入固定 fill/edge CSS（`:2760-2792`），JSON 服务端为 export-v1（`service.py:336-366`）。必须让当前有效颜色、filled/outline、0.3/default 或显式强度同时进入屏幕、PNG 和 export-v2；outline 内部透明、描边 100% 不透明、选中不把颜色改成实心高亮。最近色、临时选择、未确认预览不得进入任何地图数据或导出。 |
| 中文导入状态与 full-ready | 通过（P1 证据门槛） | 导入桥只规范化有限状态集（`backend/app/literature_maps/application/import_bridge.py:140-145,186-223`）；full ready 还要求 owner/project canonical 记录、source/indexed hash、v1 chunker、manifest/generation 等条件（`analysis.py:175-251`）。前端状态 label 未覆盖 `indexed/not_imported`（`literature-maps.js:342-353`），详情 badge 会直接显示原值（`:3655-3659`），而 `document_id/indexed` 另有“已加入知识库”分支（`:3688-3697`）。必须分开中文显示入库/索引/全文 ready；full 未 ready 不能发分析请求，ready 场景不能显示未就绪。 |
| GET 只读与下载边界 | 通过（P1 证据门槛） | `GET /graph` 只组装 map/nodes/edges/job（`service.py:278-286`），`GET /nodes/{node_id}/analyses` 读取 source status/list（`routes_literature_maps.py:354-362`），导入动作明确是独立 POST（`:591-597`）。新增样式/状态读取不能触发迁移写入、自动排队、下载、导入、索引或全文分析；恢复入口继续复用既有安全导入链，不扩大下载范围。 |

### 直接交开发与验收的技术门槛

1. v7 migration 需有旧数据库/旧图读取默认值、重复启动幂等和失败回滚证据；API `literature-map-v1` 与 export-v2 的边界不得混用。
2. `PATCH node-styles` 的请求字段、`null` 语义、唯一节点上限、owner/revision/removed 检查和全成/全不改必须在服务端完成；客户端不能把网络未知当成回滚。
3. view style 只存在正式 `node_style`，不得暗塞 filters；节点颜色覆盖和地图级填充样式必须在 graph/node/read、重开、PNG、JSON 中形成同一有效样式。
4. 自动布局必须有明确有限迭代/兜底和 200 节点混合半径的真实浏览器证据；旧图整理预览不能发写请求，确认才提交，详情开关不得自动 fit。
5. 全文分析继续消费服务端 `source_status.fulltext_ready`；`indexed`/`document_id` 只可作为入库进度事实，不能升级为全文 ready。GET 必须保持无副作用。

这些是 Task10 已冻结范围内的实现/验收门槛；未运行的测试、API E2E 或部署不能在本评审中宣称通过。

### 评审边界与证据诚实声明

本轮技术评审只证明设计能复用当前接缝且缺口已可定位；未执行迁移、真实批量保存、冲突、导出、浏览器间距/空白或 full-ready 成功案例。若任一实现门槛未满足，应在验收阶段判 P1 并退回实现，不得用旧 Task09 报告替代。

### 技术评审签字

- 评审者：`/root/map_usability_plan_review`（architect，独立增量技术评审）
- 日期：2026-10-27
- 结论：**通过（GO；无设计 P1 阻塞，含实现/验收硬门槛）**

---

## 本轮 Task11 独立增量技术评审（2026-10-27）

### 评审元数据

- 评审对象：`docs/sdd/plans/043/task-11-paper-expansion.md`、对应 Spec043 Task11 增量与 Grilling Q1–Q15 决策。
- 评审者：`/root/paper_expansion_plan_review`；角色：`architect`，由主会话分派独立评审。
- 评审时间：2026-10-27（Asia/Shanghai）。
- 评审依据：Task11方案、Grilling记录和`2026-10-27-paper-expansion-findings.md`只读事实报告；未另行调用来源或运行代码。
- 技术范围：MapPreview分页、两preview原子确认、revision冲突恢复、持久后台补全/幂等、限流与429重试、身份/权限/下载门禁及迁移边界。

### 结论

**打回（BLOCK；当前接口/持久化包形不足以冻结，不能给技术GO）。**

复用方向成立：事实报告确认现有持久预览、身份去重、引用边方向、revision/单preview apply、局部布局和摘要队列可供复用。但它也确认当前无候选分页、关系请求只取首100条，单preview apply不能拼成跨preview原子写入，预览429耗尽后只有警告。Task11提出了正确的增量方向，却把关键请求/响应、版本重确认、分页失败恢复及批次级队列契约留给“技术门禁冻结”（Task11:36–44,49）。尤其 `POST /previews` 仍写为“分页选项或版本化扩展”二选一，batch-apply输入示例没有每个preview的预期候选版本，不能据此验证重读后的显式再确认是否仍绑定同一owner/map/seed/方向和候选快照。此时判GO会把决定性架构工作推迟给实现阶段。

本BLOCK只要求冻结已选产品行为的最小技术合同；不要求新增产品能力，也不影响Task10原状态。完成下列门槛并再次独立评审前，不应分派Task11代码实现。

### 现状证据与阻塞项

| 技术点 | 现状 / 阻塞 | 必须冻结的最小合同 |
|---|---|---|
| 复用与候选分页 | 事实报告确认`GET preview`返回完整候选数组，当前候选无分页；references/citations当前取`offset=0, limit=100`且未沿`next_offset`续页（事实报告:14–16）。Task11:40–41只给端点方向和202作业概念。 | 选定唯一的创建preview请求版本；定义每方向的50页、500上限、原始来源游标（只在服务端持久保存）、唯一身份计数、total未知与`has_more`/上限截断的关系、预览候选版本递增时点，以及加载失败时不推进cursor、不丢已成功页。还须明确50表示一个来源页还是50个新增唯一候选；建议一用户动作只取一个limit=50来源页，再按稳定身份去重并显示实际新增数，避免隐藏额外请求。 |
| Load-more并发与幂等 | Task11:41提到preview版本、幂等键、重复请求不重复推进，但没有给出key作用域/载荷绑定、进行中重复请求、失败页再次尝试的语义。 | 冻结请求/响应schema及幂等规则：键至少绑定preview、当前候选版本/服务端cursor和操作；同键同参数返回同一作业/结果，同键异参结构化409；成功提交候选页和下一cursor须一起持久化，失败保留当前cursor，手动重试仅重取该页。客户端不能提交来源URL或cursor。 |
| 跨preview批量原子与并发 | 当前apply只接单preview（事实报告:9,34）；Task11:42提出`batch-apply`，但仅列map `expected_revision`与`{preview_id, selected_candidate_ids}`，缺少所选候选对应的preview版本和持久批次结果形态。 | 请求须包含每组`expected_preview_version`；服务端从认证主体取owner，并校验两个preview均属同一owner/map/seed、方向各异、仍有效、候选ID属于对应快照、种子仍活动。一个DB事务内重检revision与20/200容量，按稳定身份去重，写节点/全部实际方向边、revision、幂等结果、批次关联及可恢复工作记录；任何一项失败全回滚。相同幂等键同载荷返回原结果，异载荷409。网络请求/模型执行不得放进事务；事务提交后才唤醒现有worker，重启由持久工作记录恢复，避免提交节点后丢后台任务。 |
| 409后的显式重确认 | Task11:19、32要求无半写、重读revision与preview版本后显式确认，但没有界定重新确认请求如何防止只替换expected_revision继续用旧/错属preview。 | 规定UI在409后读取当前graph及原preview快照，保留选择并展示变更；用户再次点击确认后以新读到的map revision和原候选版本提交。服务端重新执行owner/map/seed/kind/状态/候选版本/种子活动状态/预算检查；只换revision、拼接他图preview、失效preview、已移除种子均拒绝，不能把旧preview重新绑定到新seed。 |
| 新增节点的补全与分析队列 | Task11:21–23、33要求只为批次新增节点补元数据/摘要，持久记录每步并复用MapJob/MapAnalysis；事实报告:20–22说明现有分析队列持久、但ensure路径会面向当前活动节点，且无摘要不会自动补元数据。 | 冻结batch-scoped node ID集合和每节点步骤状态/唯一幂等键；保证只提交本批真正新增的唯一节点，不触发全图ensure补入旧节点。队列记录与批次在同次DB事务可恢复，重试只补失败/缺失步骤，同一摘要source_version已完成不重跑；迟到worker、重开与重复确认不得重复分析。 |
| 元数据更新边界 | 方案说“一轮有界补全”和字段缺值显式（Task11:22,30），没有具体字段白名单、缓存复用身份、更新优先级和source_version改变条件。 | 指定复用的现有元数据客户端/字段请求与缓存入口；只填定义为缺失的允许字段，不覆盖已有/人工信息；只有摘要内容实际变化才使摘要source_version变化并触发相应一次分析。区分来源请求失败（保留失败态，可有限重试）与成功但无摘要（跳过；按Q6只在用户显式发起时允许稍后再查），不得以标题分析。只读GET不发外部请求。若现有代码没有可复用缓存，应如实限定为持久preview快照去重，不假称已有缓存，也不建立第二缓存/来源栈。 |
| 429、缓存与续页失败 | 事实报告:28–30确认共享Semantic Scholar进程内1秒限流和既有最多一次、Retry-After/指数且30秒封顶的client重试；候选预览耗尽后仅有warnings，尚无失败页补齐。Task11:24,41,44,61承诺有限重试、保留成功页和失败页重试。 | 继续用同一client/limiter及既有有界重试；把最终429按方向和cursor持久标为失败，保留成功候选和cursor，只有显式重试可重取该页，另一个方向可继续。未知总量不能显示为0；来源失败不得返回“成功空结果”。载入的preview快照供重开读取，不因GET重新抓取已加载页。 |
| 来源安全与全文门禁 | Task11:17,22,38–44,67明确关系候选可范围外，但不放宽下载门禁、不下载PDF/全文；不允许客户端任意URL/cursor（:29）。 | 新增请求仍经既有固定来源客户端；关联发现只读论文元数据，不凭候选身份自动入库/下载/全文分析。新增字段填充不得复用或扩大下载/导入来源白名单；认证owner从服务端取。 |
| 持久化/迁移 | Task11:29–34列出了新增分页状态和批次记录，但仅说“需要新列/索引时迁移”，没有精确持久模型与无损升级/回滚对象。 | 接口合同中列出现有MapPreview/MapJob需新增的版本化字段或关联，以及幂等/唯一约束和初始化迁移策略；增量、幂等、失败回滚，旧preview/图/ID/布局/分组/颜色/KB关联保持原样。不得重置数据库。 |

### 重新送审所需的最小材料

在Task11范围内补一份与现有MapPreview/MapJob/MapAnalysis兼容的接口合同，至少包含：

1. `POST /previews`、`POST /previews/{id}/load-more`、`POST /previews/batch-apply` 的请求/响应示例、状态码与稳定错误体，包含双方向候选版本和幂等冲突。
2. 分页持久状态、版本递增、限流失败保留cursor/手动补页、500截断和total未知的状态转换。
3. batch-apply单事务写入清单、并发revision冲突后重读/再次确认流程、owner/map/seed/kind/candidate状态校验，以及提交后后台批次恢复/去重语义。
4. 只针对新增节点的持久补元数据→摘要分析步骤、source_version/幂等规则、字段合并白名单、缺摘要显式重试和现有client/cache/limiter复用边界。
5. 兼容旧preview的增量迁移说明和针对上述边界的合同验收清单；无需在本评审阶段运行测试或真实来源请求。

以上仅把已批准的50/500/20/200、双方向、原子确认、后台恢复和不扩下载门禁翻译成可实现的技术合同，不增加产品行为。技术合同补齐后再复核；届时仍须等用户完成共同理解确认才可进入实现。

### 评审边界与签字

本轮读取方案、事实报告和必要既有评审文本；未改业务代码/测试，未运行测试、真实API、模型、下载、服务、迁移、部署或Git操作。事实报告中的旧测试摘要不是Task11证据；Task10既有评审不替代本轮技术门禁。

- 评审者：`/root/paper_expansion_plan_review`（architect，独立增量技术评审）
- 日期：2026-10-27
- 结论：**打回（BLOCK；接口/持久化合同未冻结）**

---

## Task11 技术复审：接口与持久化合同（2026-10-27）

### 评审元数据

- 评审对象：`docs/sdd/plans/043/task-11-interface-contract.md`及其在Task11/Spec043中的链接；仅复核首轮技术BLOCK和必要代码接缝。
- 评审者：`/root/paper_expansion_plan_review`；角色：`architect`。
- 模型：GPT-6（Codex运行环境；本次分派未显示额外型号覆写）。分派方式：主会话原生分派的子代理复审。
- 评审时间：2026-10-27（Asia/Shanghai）。

### 结论

**仍打回（BLOCK；以下MapJob worker lifecycle接缝未冻结）。**

新合同已真实关闭首轮的大部分阻塞：v7→v8无损分页迁移、服务端cursor及预览版本/幂等、失败页原cursor重试、同seed跨preview revalidate、批量原子事务与outbox、仅本批新增节点的队列、摘要写入白名单、持久metadata缓存、既有限流/429语义、Q6显式重查和不放宽PDF/全文门禁均已写明（合同:8–14,38–42,52,62–85,89–93；Task11:73–75）。

但合同将`preview_page`与`expand_batch`称为复用现有MapJob lease/worker_token并可恢复的操作（合同:12,40,64,85），当前代码并没有供这些普通MapJob直接复用的lease流程：`LiteratureMapStore.claim_job`仅将queued状态CAS为running，没有写入或检查`worker_token`/`lease_expires_at`（`backend/app/literature_maps/infrastructure/store.py:2408-2424`）；带token和lease的`claim_analysis_job`只接受`operation='analysis'`（同文件:1717-1755）。此外`LiteratureMapService.recover`只特判`preview:*`、`analysis`和`analysis_queue`，其他job会提交给通用`run_job`（`backend/app/literature_maps/application/service.py:254-276`）。因此新操作重启后会走建图job路径；合同要求的token校验、过期lease恢复和迟到worker拒写当前没有可直接复用的operation路径。

不能把这一缺口作为普通实现细节略过：它决定并发分页是否重复推进、崩溃后批次是否能续跑，以及旧worker能否在新worker接管后提交过期结果。技术GO前应把新操作的claim/finish/recovery规则精确落到接口合同中。

### 唯一剩余技术阻塞与最小补充

1. 为`preview_page`和`expand_batch`定义受operation白名单保护的持久CAS claim/finish：对queued或可恢复的过期running步骤原子写入worker token、lease/尝试代数；每次进度和终态提交都校验token，旧token不得写入。不可直接复用仅限`analysis`的`claim_analysis_job`，也不能把job送进无操作类型分派的`run_job`。
2. 明确`recover()`按operation将`preview_page`恢复到页处理器、`expand_batch`恢复到outbox批次处理器；cursor须足以幂等恢复当前页/步骤。只接管过期lease，遵守地图暂停状态，不触碰已完成步骤；尚未过期的running worker不重复执行。
3. 在接口合同的既有“提交后崩溃/迟到worker”验收项中，分别验证页cursor只提交一次、批次成功步骤不清空、过期token结果被拒绝。此项是复用MapJob所必需的技术补充，不改变用户产品行为。

其他首轮技术阻塞均已关闭；若上列规则被补入合同，需复核该差异后才可给最终技术GO。用户共同理解确认仍是独立前置门槛。

### 评审边界与签字

只复核新增合同、Task11/Spec链接、Q6增量，以及claim/recovery/cache/queue的必要代码接缝；未改业务代码/测试/Task11合同，未运行测试、来源请求、迁移、部署或Git操作。

- 评审者：`/root/paper_expansion_plan_review`（architect）
- 日期：2026-10-27
- 结论：**打回（BLOCK；仅剩MapJob lease/finish/recovery接缝）**

---

## Task11 技术复审最终结论：worker生命周期补齐（2026-10-27）

### 评审元数据

- 评审对象：`docs/sdd/plans/043/task-11-interface-contract.md` 第5节“新操作的worker生命周期”，以及其与第1–4节分页、batch outbox、队列、暂停和错误状态的衔接。
- 评审者：`/root/paper_expansion_plan_review`；角色：`architect`。
- 模型：GPT-6（Codex运行环境；本次分派未显示额外型号覆写）。分派方式：主会话原生分派的子代理复审。
- 评审时间：2026-10-27（Asia/Shanghai）。

### 结论

**通过（GO；技术设计门禁通过，仍待用户共同理解确认）。**

第5节正面说明普通`claim_job`不具备analysis专用token/lease语义，并要求新增仅允许`preview_page`/`expand_batch`的事务级claim和token校验提交helper；它复用MapJob存储字段和租约模式，而没有把通用claim误称为已安全。它也为新operation补上了处理器路由、启动/过期lease恢复、迟到worker拒写、analysis_wait无长租约、暂停边界、失败页不被lease reaper自动重播，以及外部请求不保证exactly-once等语义（接口合同:95–122）。上一轮唯一技术阻塞已经关闭。

### 与既有接缝的一致性

| 核对项 | 判定 | 依据 |
|---|---|---|
| 普通MapJob与分析worker分界 | 通过 | 合同明确新增辅助操作事务helper，不复用`claim_analysis_job(operation='analysis')`；此点与普通`claim_job`和analysis专用claim的现状一致（`backend/app/literature_maps/infrastructure/store.py:2408-2424,1717-1755`）。 |
| 启动和租约恢复 | 通过 | 合同把两个新operation加入显式handler/reaper，并禁止回落到通用`run_job`；应用已有启动恢复入口（`backend/app/literature_maps/application/runtime.py:241-247`）及分析租约到期唤醒模式（`backend/app/literature_maps/application/analysis.py:747-790`），新操作明确需要沿该模式增加自身状态扫描。 |
| 事务与迟到结果 | 通过 | page/metadata/batch领域提交在同一事务内先校验job、owner、operation、token和lease；失败整段回滚。调用来源在事务外，缓存不等于领域步骤已提交。未知在途外部请求可重取，但最终候选/cursor/分析登记依靠领域CAS防止重复效果。 |
| analysis_wait与分析队列 | 通过 | 元数据结束后释放辅助lease，等待状态只对齐已登记analysis_id，由既有分析worker执行模型；重启不重做metadata或重新调用模型。完成/失败更新批次投影。 |
| 暂停、重试和429终态 | 通过 | preview分页不受“暂停分析”影响；expand_batch在各调度边界尊重地图暂停，resume恢复未完成步骤。来源429在client有限重试后以失败页终态保存，lease reaper不代替用户反复联网；缺摘要重查仍须显式选择。 |
| Lease限制与外部副作用 | 通过 | 300秒租约、命令代数内最多3次自动接管及超限后的显式重试均已写明；合同不承诺HTTP exactly-once，同时要求成功领域写入不重复提交。 |

以上属于Task11合同本身的实现边界；当前没有实现、测试、迁移或运行时成功声明。落实时应原样遵守，不得退回普通`claim_job`或analysis handler处理新operation。

### 评审边界与签字

只复核第5节及其与此前合同和现有runtime/lease接缝的必要关系；未重扫无关历史，未改业务代码/测试/合同，未运行测试、外部请求、迁移、部署或Git操作。Task10历史及需求复审结论不变。

- 评审者：`/root/paper_expansion_plan_review`（architect）
- 日期：2026-10-27
- 结论：**通过（GO；唯一剩余技术阻塞已关闭；待用户共同理解确认）**
