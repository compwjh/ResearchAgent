# Task11 Expansion Batch 架构准备

日期：2026-10-28  
范围：只读核对 Task11 已确认合同与现有 literature-map service/store/analysis 接缝；本报告是后续实现准备，不是实现、测试或验收证据。没有调用来源、模型、全量测试或部署。

## 结论

无需另建队列、缓存或 worker 框架。现有 `literature_map_jobs`、mutation 幂等表、请求缓存、analysis queue 和 auxiliary lease 已覆盖所需持久化基础；当前缺口集中在双预览命令的事务级存储入口、批次 worker 的领域处理，以及批次与 analysis 完成态的事务内关联。

实现时应把双预览校验和写入留在一个 SQLite `BEGIN IMMEDIATE` 事务中。不要分别调用两个公开 `apply_preview()`，也不要在这个事务里调用公开 `ensure_analysis_queue()`：二者都会自行开事务。只为本次新节点登记 analysis 项，不能用全图队列 reconcile 代替。

## 当前接缝

| 区域 | 当前已有 | Task11 尚需接上 |
|---|---|---|
| HTTP/service | [routes_literature_maps.py](../../../../backend/app/api/routes_literature_maps.py) 有单预览创建、读取和 `/previews/{preview_id}/apply`；[service.py](../../../../backend/app/literature_maps/application/service.py) 有单预览 `apply_preview()`。本次查看的路由段没有跨预览 `revalidate` / `batch-apply` 入口。 | 按冻结合同增加 revalidate 和 batch-apply 的请求入口与 service 编排；分页入口/行为由并行实现处理，本报告不重复设计。 |
| 单预览写入 | [store.py](../../../../backend/app/literature_maps/infrastructure/store.py) 的 `apply_preview()` 自己开事务并校验 map revision、单 preview 的 base revision 和候选 ID；service 先在事务外把候选转成 node/relations。 | 跨预览必须在同一连接内检查 owner/map/活动 seed、两 preview 的版本与 base revision、方向和候选归属/身份/墓碑状态，再统一计算去重和容量。单预览 service 会在提交后重新算全图 similarity，并调用全活动图的摘要队列 reconcile，不能直接复用为 batch apply 路径。 |
| Edge 与墓碑 | 单预览 service 已把 `references` 转为 seed→候选、`citations` 转为候选→seed。store 对关系端点缺失或自环会 `continue` 跳过；`literature_map_nodes` 对 `(map_id, identity_key)` 有唯一约束，墓碑仍占身份；显式恢复走 `restore_node()`。 | batch 必须保留两种真实有向关系；在写入前把无效端点、自环、身份不确定、被移除节点作为拒绝条件，不能静默略过或自动恢复。跨预览同身份只插入一个新节点，但仍写入各方向真实边。 |
| 辅助 worker | service 的 dispatch/recovery 已识别 `preview_page` / `expand_batch`；store 已有 `claim_auxiliary_job()`、token/lease 检查的 `auxiliary_job_transaction()`、事务内 `finish_auxiliary_job_tx()` 和过期 lease recovery。 | [service.py:325](../../../../backend/app/literature_maps/application/service.py) 的 `run_expansion_batch()` 目前仍走 fail-closed 占位处理；需要实现有限的 metadata 工作流。辅助 handler 不调用模型。 |
| Analysis queue | `MapAnalysisService.ensure_analysis_queue()` 计算当前全活动节点的 source version/model 候选并调用 store；store 的 `_update_queue_items_tx(db, ...)` 与 `_create_analysis_tx(db, ...)` 已可在当前连接内登记分析 child。analysis worker 继续由现有 queue scheduler 串行调度。 | batch 只登记新增且已有摘要的节点；缺摘要节点在摘要成功的同一写事务登记。不能从 batch 触发全图 `ensure_analysis_queue()`。 |
| Batch 状态 | `GET /jobs/{job_id}` 已直接投影 `MapJob.to_dict()`；`MapJob` 含 cursor/counts/failed_units。`finish_analysis()` 事务内更新 analysis child 与 aggregate analysis queue。 | 批次 cursor 的 metadata/analysis 状态和 counts 需要持久更新；analysis child 完成/失败时还需在同一事务更新关联 batch，恢复时校正投影，避免 `analysis_wait` 长期停留在 queued/0。 |
| S2 与缓存 | service 已使用 `SemanticScholarGraphClient.batch()`、现有 metadata parser、`request_cache_key/get_request_cache/put_request_cache`；cache key builder 支持 fields/version，写缓存有既定 TTL。 | expansion 只请求合同指定字段并使用 `operation=metadata`、规范化身份/字段/版本组成持久 key；只写缺失 abstract 与来源证明。refresh 的 `metadata_batch` 宽字段更新路径不是 expansion 的写入实现。 |

## 事务设计约束

1. `revalidate` 是显式、无来源网络的预览重核。一个事务检查 map 与两 preview 的 owner/map/seed/kind、分页非 busy、expected map revision / preview revisions 及候选归属；基于当前活动图重新标记已有、失效、移除选项，更新所涉 preview 的 base revision 和 preview revision，并记录 operation-scoped 幂等结果。它不写 node/edge；失效选择交还用户处理，不能自动删选项。
2. `batch-apply` 先查幂等重放（同键异参冲突），再在同一事务核对当前 map 与两 preview 版本、seed 和候选身份。每方向至多 20 个原始候选、跨方向按稳定 identity 去重后至多新增 20 个，活动图上限 200；已有活动节点计入 existing，不算新增；墓碑不得当作新节点绕过唯一约束。按有效 identity 插入节点、写正确方向的 citation edge、只增加一次 map revision，更新两条 preview 的加入标记/版本，并保存固定命令结果。
3. 同一事务创建 `expand_batch` job/outbox，cursor 使用合同 v1；items 保存 metadata 阶段与关联的 analysis id/source version。已有摘要的新节点在该事务注册现有 analysis queue child。若无 metadata pending，不应让 batch 进入一个无法被 auxiliary claim 领取的空 queued 状态；它应进入合同定义的 analysis-wait/终态投影路径。
4. metadata 网络请求在事务外执行；成功响应可写入共享持久 cache，但 cache 命中本身不代表领域步骤已提交。随后用 `auxiliary_job_transaction()` 在短事务内重验 lease/token、节点仍活动且 abstract 仍缺失，CAS 写入 abstract 和来源证明、按现有 `_hash_source({title, abstract, external_ids})` 算 source version、登记分析 child，并推进 batch item/count。若另一合法写入已填摘要，采用现值且不覆盖；墓碑/移除节点安全跳过。失败、确定无摘要、身份不确定分别保留为合同区分的状态。
5. analysis 完成/失败现已在 `store.finish_analysis()` 的事务内更新 child 和 analysis queue。批次关联也应在该事务里按 batch item 中的 `analysis_id`/`source_version` 更新并重算 batch counts/status；恢复时基于持久 child 状态修正投影，不另建调度器或结果表。批次等待期间不改 `literature_maps.status`，队列暂停时不继续派发 metadata；恢复沿既有 analysis queue 与 `auxiliary_recovery` 路径。

## 避免嵌套事务：具体重构点

- **队列登记的主重构点是 `LiteratureMapStore.ensure_analysis_queue()`。** 它当前在函数内 `with self.transaction()`；把事务体提取为接收 `db: sqlite3.Connection` 的内部 `_ensure_analysis_queue_tx(...)`，公开方法仅保留事务包装。batch apply 与 metadata worker 调用 tx 版本，并在提交后由现有 analysis service 调度 queue。
- 现有 `_update_queue_items_tx(db, ...)` 已接收连接，但当前以新候选集整体替换 `cursor["items"]`。直接传“仅新增节点”的候选集会丢失旧 queue 项。需要为批次调用提供增量合并语义（或提取小型 merge helper），同时沿用 `_create_analysis_tx(db, ...)` 的幂等创建；不能通过全图扫描来规避。
- **预览写入也要有 tx 级复用点。** `store.apply_preview()` 是单预览事务包装；将共享的校验/写入片段提取成接收当前 `db` 的内部 helper，或由新的 batch tx 方法直接复用其纯 DB 子步骤。公开 `apply_preview()` 不可嵌套调用两次，batch 也不能借用其 service 后处理。

## 关键文件定位

- 合同：`docs/sdd/plans/043/task-11-interface-contract.md` §2 的 revalidate / batch-apply、§3 的补摘要与分析队列、§5 的 claim/token/lease/恢复要求。
- API：`backend/app/api/routes_literature_maps.py:514-553`；job 读取：`:588-596`。
- Service：`backend/app/literature_maps/application/service.py:325-328`（batch handler 占位）、`:818-906`（legacy 单预览 apply 与提交后处理）、`:1307-1338`（全活动图队列 reconcile）、`:1178-1208`（cache wrapper）。
- Store：`backend/app/literature_maps/infrastructure/store.py:92-101`（事务边界）、`:1062-1114`（ensure queue wrapper）、`:1563-1619`（queue item transaction helper）、`:956-1031`（analysis child tx helper）、`:2076-2178`（单预览事务）、`:2183-2260`（显式 restore/remove）、`:2465-2679`（auxiliary claim/transaction/finish）、`:3020-3115`（auxiliary recovery）。
- Analysis：`backend/app/literature_maps/application/analysis.py:50-55`（既有 source hash）、`:329-429`（analysis worker 生命周期）、`:556-587`（全图 queue reconcile）、`:595-600`（resume 触发 analysis 与 auxiliary recovery）；analysis terminal CAS 在 `store.finish_analysis()`，见 `store.py:1776-1849`。

## 未做事项

本次仅做架构核对并形成准备报告。没有改业务代码、测试、合同或 Git 状态；没有运行测试、来源请求、模型调用或部署。分页实现由并行 Task 负责，本报告不代表其完成或验收。
