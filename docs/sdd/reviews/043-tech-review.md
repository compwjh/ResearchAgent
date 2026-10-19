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
