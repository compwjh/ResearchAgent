# 2026-10-27 Spec043 地图可用性增量：后端事实核查

本文是 backend-reviewer 的只读诊断/规划交接物，服务于 Spec043 的地图 UI 增量讨论。未修改业务代码、测试、Spec、状态台账、Git、服务、真实数据库或记忆；未运行服务或测试。以下只记录当前后端事实、可复用边界和仍待确认的数据/接口问题，不替用户决定产品行为。

## 1. 当前分组与颜色契约

- `MapGroup` 是地图内的用户展示分组，字段只有 `group_id`、`map_id`、`name`、`color` 和时间戳；没有透明度、图标或其他样式字段。[`backend/app/literature_maps/domain/models.py:149-165`](../../../backend/app/literature_maps/domain/models.py:149)
- HTTP 创建/修改分组的 `color` 都要求 `^#[0-9a-fA-F]{6}$`；即只接受 `#RRGGBB` 六位十六进制，不接受 `#RRGGBBAA`、`rgb()/rgba()`、命名色或 `transparent`。[`backend/app/api/routes_literature_maps.py:101-115`](../../../backend/app/api/routes_literature_maps.py:101)
- store 再次执行同一白名单校验，并把颜色规范化为大写后写入 SQLite；因此合法值在响应/重读中通常是大写六位十六进制。[`backend/app/literature_maps/infrastructure/store.py:2711-2715`](../../../backend/app/literature_maps/infrastructure/store.py:2711)
- 分组上限是每张地图 200 个；删除分组会把该组节点的 `group_id` 置空，然后删除分组记录，不删除节点。[`backend/app/literature_maps/infrastructure/store.py:713-724`](../../../backend/app/literature_maps/infrastructure/store.py:713)、[`backend/app/literature_maps/infrastructure/store.py:772-790`](../../../backend/app/literature_maps/infrastructure/store.py:772)

## 2. 节点是单组归属，不支持多选

- `MapPaper` 只有一个可空的 `group_id: str | None`；SQLite 的 `literature_map_nodes` 也只有单列 `group_id`，当前没有 node–group 连接表或数组字段。[`backend/app/literature_maps/domain/models.py:94-113`](../../../backend/app/literature_maps/domain/models.py:94)、[`backend/app/literature_maps/infrastructure/store.py:141-163`](../../../backend/app/literature_maps/infrastructure/store.py:141)
- 现有接口是 `PUT /api/literature-maps/{map_id}/nodes/{node_id}/group`，请求只有一个 `group_id` 或 `null`；重新 PUT 会替换原归属，`null` 表示取消分组。[`backend/app/api/routes_literature_maps.py:123-128`](../../../backend/app/api/routes_literature_maps.py:123)、[`backend/app/api/routes_literature_maps.py:311-322`](../../../backend/app/api/routes_literature_maps.py:311)
- store 会验证该组属于同一地图、拒绝已移除节点，并只更新这一列。[`backend/app/literature_maps/infrastructure/store.py:792-837`](../../../backend/app/literature_maps/infrastructure/store.py:792)
- 因此“一个节点可属于多个主题/分组”的 UI 不能只改前端；需要新的持久化形态（连接表或明确的多值字段）、读写接口、迁移和冲突语义。若 UI 保持“每节点一个人工分组”，现有接口足够。

## 3. owner/revision 保护是现有写入前提

- 路由层统一使用当前 `OWNER_ID`，地图/分组/节点查询和写入都会传入 owner。[`backend/app/api/routes_literature_maps.py:17-19`](../../../backend/app/api/routes_literature_maps.py:17)
- 创建、修改、删除分组都要求 `expected_revision`，store 在事务中先按 `map_id + owner_id + deleted_at IS NULL` 找地图，再检查 revision；成功后递增地图 revision。[`backend/app/literature_maps/infrastructure/store.py:694-725`](../../../backend/app/literature_maps/infrastructure/store.py:694)、[`backend/app/literature_maps/infrastructure/store.py:727-770`](../../../backend/app/literature_maps/infrastructure/store.py:727)、[`backend/app/literature_maps/infrastructure/store.py:772-790`](../../../backend/app/literature_maps/infrastructure/store.py:772)
- 节点分组同样要求 `expected_revision`，并在成功替换 `group_id` 后递增 revision。[`backend/app/literature_maps/infrastructure/store.py:792-837`](../../../backend/app/literature_maps/infrastructure/store.py:792)
- 视图保存也要求 `expected_revision`；owner/revision 校验在位置更新前执行，成功后整张地图 revision 递增。[`backend/app/api/routes_literature_maps.py:60-68`](../../../backend/app/api/routes_literature_maps.py:60)、[`backend/app/literature_maps/infrastructure/store.py:598-626`](../../../backend/app/literature_maps/infrastructure/store.py:598)
- 这意味着 UI 的任何“颜色/分组/视图保存”都必须基于最新地图 revision；不能把分组请求与视图请求当作无版本的独立偏好写入。

## 4. view_settings 当前能保存什么

- 地图表结构把视图作为 `view_json` JSON 文本保存，并非独立列；创建默认值只有 `viewport`、`layers`（citation/similarity）和 `label_mode`。[`backend/app/literature_maps/infrastructure/store.py:112-125`](../../../backend/app/literature_maps/infrastructure/store.py:112)、[`backend/app/literature_maps/infrastructure/store.py:427-435`](../../../backend/app/literature_maps/infrastructure/store.py:427)
- `PATCH /api/literature-maps/{map_id}/view` 的公开请求字段是：最多 200 个节点位置、`viewport{x,y,scale}`、任意字典 `filters`、仅允许 citation/similarity 两个键的 `layers`、以及 `label_mode`（all/neighbors/hidden）。[`backend/app/api/routes_literature_maps.py:44-68`](../../../backend/app/api/routes_literature_maps.py:44)
- store 当前只对 `label_mode`、位置 node ID、viewport（路由层有限值检查）做约束；收到的 `filters`/`layers` 会合并进 `view_json`。[`backend/app/literature_maps/infrastructure/store.py:598-622`](../../../backend/app/literature_maps/infrastructure/store.py:598)
- 但这不等于已有 `style` 合同：请求模型没有 `style`/`opacity`/`nodegap` 字段，`layers` 也被 Literal 限制为两个关系层。把 `nodegap` 塞进 `filters` 虽可能被当前宽松字典存下，但语义未定义、没有数值范围/单位/版本契约，不应当作为已支持接口对外承诺。
- JSON 导出只导出白名单视图键：`filters` 只保留年份/来源/会议，`layers` 只保留 citation/similarity，另有 label_mode；未知样式键不会进入导出。[`backend/app/literature_maps/application/service.py:1621-1643`](../../../backend/app/literature_maps/application/service.py:1621)
- 因此：仅需当前浏览器临时的 opacity/nodegap，可以由前端状态承担；若要求“按地图保存、重开地图保留、JSON 导出也保留”，需要明确的 style schema、store 合并/校验和 export 白名单变化。由于底层是 JSON blob，物理 SQLite 新列未必必要，但公开 schema/接口契约和回归必须新增。

## 5. 最近颜色是否已有保存层

- 后端地图领域没有 recent-color、palette、swatch 或用户颜色偏好字段/表；地图 store 只有 map-scoped `literature_map_groups.color`，与地图绑定。[`backend/app/literature_maps/infrastructure/store.py:131-139`](../../../backend/app/literature_maps/infrastructure/store.py:131)、[`backend/app/literature_maps/domain/models.py:149-165`](../../../backend/app/literature_maps/domain/models.py:149)
- 因而“最近使用颜色”若只是当前浏览器/当前用户的便利输入，前端 `localStorage` 是现有后端零变更的边界；它不应写入某张地图的 `groups`，也不应冒充地图导出数据。
- 若产品要求跨浏览器/跨设备同步最近颜色，当前没有可复用的 owner-level map preference API/表，需要另定用户偏好存储和公开接口；不能把现有 `view_json` 误当作用户级偏好，因为它是 `map_id` 作用域。
- 当前前端地图代码已有 `sessionStorage` 只保存未完成预览会话的恢复句柄，不是颜色偏好存储；这不能被解释为已有 recent-color 层。[`frontend/literature-maps.js:1794-1813`](../../../frontend/literature-maps.js:1794)

## 6. 可直接复用的最小现有 API

以下能力不需要新增后端资源，只需 UI 正确使用现有 revision 和错误合同：

1. 分组列表/创建/改名改色/删除：`GET/POST/PATCH/DELETE /api/literature-maps/{map_id}/groups`（删除和 PATCH 带 group_id）。颜色按 `#RRGGBB`，每次写入带 `expected_revision`。[`backend/app/api/routes_literature_maps.py:261-309`](../../../backend/app/api/routes_literature_maps.py:261)
2. 单节点分组或取消分组：`PUT /api/literature-maps/{map_id}/nodes/{node_id}/group`，传一个 `group_id` 或 null，带 `expected_revision`。[`backend/app/api/routes_literature_maps.py:311-322`](../../../backend/app/api/routes_literature_maps.py:311)
3. 节点位置、缩放/平移、关系层、现有筛选、标签模式：`PATCH /api/literature-maps/{map_id}/view`，带 positions/viewport/filters/layers/label_mode 和 expected_revision。[`backend/app/api/routes_literature_maps.py:535-546`](../../../backend/app/api/routes_literature_maps.py:535)
4. 图与节点状态：`GET /api/literature-maps/{map_id}/graph` 和节点详情；节点投影包含 `document_id`、`download_status`、position、group_id。[`backend/app/api/routes_literature_maps.py:253-259`](../../../backend/app/api/routes_literature_maps.py:253)、[`backend/app/literature_maps/domain/models.py:126-146`](../../../backend/app/literature_maps/domain/models.py:126)
5. 用户主动入库：`POST /api/literature-maps/{map_id}/nodes/{node_id}/imports`，复用既有安全下载/导入链；地图侧只接收规范化结果，不另造下载器。[`backend/app/api/routes_literature_maps.py:591-597`](../../../backend/app/api/routes_literature_maps.py:591)、[`backend/app/literature_maps/application/import_bridge.py:38-46`](../../../backend/app/literature_maps/application/import_bridge.py:38)
6. 摘要/全文依据状态：`GET /api/literature-maps/{map_id}/nodes/{node_id}/analyses` 会返回 `source_status`；可用于把“尚未全文索引”与“已可全文分析”分开展示。[`backend/app/api/routes_literature_maps.py:354-362`](../../../backend/app/api/routes_literature_maps.py:354)

## 7. download_status、index 状态与 full evidence ready 的事实区别

### 7.1 地图节点的 download_status 来源

- 生产导入 port 的状态枚举是 `indexed`（成功写入向量索引）、`pending`（已导入但索引未完成）、`failed`（索引失败）。这是跨域 port 的状态定义。[`backend/app/platform/ports.py:72-80`](../../../backend/app/platform/ports.py:72)
- 知识库适配器把记录顶层 status 映射为该枚举：仅 `indexed` 映射为 INDEXED，仅 `failed` 映射为 FAILED，其余回退 PENDING。[`backend/app/knowledge_base/application.py:994-1000`](../../../backend/app/knowledge_base/application.py:994)
- 地图 import bridge 读取返回值中的 `status` 或 `download_status`，限于安全状态集合后写回节点的 `download_status`，同时保存 `document_id`；该字段只是导入链的规范化投影。[`backend/app/literature_maps/application/import_bridge.py:140-145`](../../../backend/app/literature_maps/application/import_bridge.py:140)、[`backend/app/literature_maps/application/import_bridge.py:186-218`](../../../backend/app/literature_maps/application/import_bridge.py:186)
- 所以 `download_status=indexed` 只能说明导入适配器报告了 indexed；它不是全文依据门禁的充分条件。失败/等待登录等状态也可能没有 document_id，不能按“已有节点”推断全文存在。[`backend/app/literature_maps/application/import_bridge.py:283-298`](../../../backend/app/literature_maps/application/import_bridge.py:283)

### 7.2 full evidence ready 的实际门禁

`MapAnalysisService.source_status()` 先报告摘要是否非空，再调用 `_full_source()`；`fulltext_ready` 只有 `_full_source_for_project()` 成功才为 true。[`backend/app/literature_maps/application/analysis.py:147-173`](../../../backend/app/literature_maps/application/analysis.py:147)

该门禁当前同时要求：

- 节点有 `document_id`；
- `list_documents_for_project(project_id, owner_id=owner_id)` 能在正确项目/共享池范围返回 canonical 记录。`project_id=None` 只看无任何 sidecar 关联的共享记录；任何已有项目关联都排除，即使关联属于别的 owner/project。[`backend/app/literature_maps/application/analysis.py:175-205`](../../../backend/app/literature_maps/application/analysis.py:175)、[`backend/app/knowledge_base/application.py:731-766`](../../../backend/app/knowledge_base/application.py:731)
- canonical 记录有 `source_sha256`，`source_hash_state == "verified"`，且 `indexed_source_sha256 == source_sha256`；`chunkers.v1.status == "indexed"`、v1 progress 为 100、v1 error 为空。[`backend/app/literature_maps/application/analysis.py:205-225`](../../../backend/app/literature_maps/application/analysis.py:205)
- 当前 FinalizeBundle generation 可读，v1 Inspection Manifest 的 status 为 `ready`、progress 为 100、source hash 已 verified，document_id/chunker/source hash/indexed hash 与 canonical 记录一致，且有非空 `index_fingerprint`。[`backend/app/literature_maps/application/analysis.py:227-251`](../../../backend/app/literature_maps/application/analysis.py:227)

分析执行时还会再次读取该门禁；全文检索必须从 v1、指定 document_id 得到非空片段，否则返回 `MAP_FULLTEXT_UNAVAILABLE` 或 `MAP_EVIDENCE_UNAVAILABLE`。[`backend/app/literature_maps/application/analysis.py:352-370`](../../../backend/app/literature_maps/application/analysis.py:352)

因此 UI 应把以下状态分开表达：

- “尚未主动入库/导入中/等待登录/导入失败”（节点 `download_status` 与诊断）；
- “已有 document_id，但 v1 索引/manifest/generation/hash 尚未满足”（`source_status.fulltext_ready=false`，reason 通常为 `MAP_FULLTEXT_UNAVAILABLE`）；
- “全文 ready，可执行全文分析”（`fulltext_ready=true`）。

不能把节点 `download_status` 的 `indexed`、文件已落盘、或存在 `document_id` 任一项假定为 full evidence ready。

## 8. 需明确后才可决定是否扩后端契约的问题

1. opacity/nodegap 是仅当前浏览器、用户级跨地图，还是每张地图且跨设备保存？三者分别对应前端 localStorage/内存、需要新的 owner-level 偏好层、或扩展 map view schema/API。
2. nodegap 的单位、允许范围、默认值和异常处理是什么；opacity 是全图、关系层、分组还是节点级？目前没有可复用数值约束。
3. 节点分组是否保持“单个 group_id”，还是需求确实需要多选；多选会改变存储模型和接口，不是 UI 小改。
4. 颜色是否仍限 `#RRGGBB`，还是要 alpha/透明色；后者需同步 route Pydantic、store 校验、前端输入、导出与版本兼容。
5. 状态 UI 是否要分别展示“下载/导入”“索引”“全文证据 ready”；后端目前没有一个把三者合并成单一 ready 状态的 API，建议继续消费现有 `download_status` 与 `source_status` 两个事实来源，避免伪等价。

## 9. 复用约束摘要

- 地图分组/位置/关系层/标签模式直接复用现有 endpoints；所有写操作保留 owner + expected_revision。
- 不在 `filters` 中暗塞未定义的 style 字段来伪装既有契约；若需要持久化 style，先冻结字段、范围、导出和冲突行为。
- 不为 recent colors 新建地图组或污染 `view_json`；浏览器级最近颜色与地图级分组颜色应保持不同作用域。
- 不以 `download_status=indexed`、`document_id` 或 PDF 已落盘替代 fulltext-ready 门禁；全文分析必须继续走 canonical record + v1 manifest + generation/hash 校验。
- 多组归属、透明色、跨设备最近颜色、地图级 style 持久化均属于待确认的 schema/API 扩展；本次仅记录缺口，未做范围决定。
