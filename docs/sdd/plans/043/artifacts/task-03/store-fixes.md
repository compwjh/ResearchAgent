# Task03 store contract repair

本轮仅覆盖 `infrastructure/store.py` 与 literature-map store tests；不修改 service/runtime/routes/frontend。

## 供 service/similarity 复用的接口

- `create_map_with_job(owner_id, *, topic, name, project_id, filters, requested_count, operation, idempotency_key, params_hash) -> (LiteratureMap, MapJob, created)`：单个 `BEGIN IMMEDIATE` 内完成 owner + 幂等 key + 参数哈希校验、地图和作业创建；重复同参数返回既有对象与 `created=False`，冲突抛稳定 `ValueError("idempotency conflict")`。
- `request_cache_key(...)`、`get_request_cache(key)`、`put_request_cache(key, payload, ttl_seconds=86400, status="success", ...)`：请求缓存 key 包含 provider/operation/query/identifier/filter/page/fields/schema-version；仅成功响应可写入，失败/429 不作为成功空结果。
- `claim_job(job_id, map_id, owner_id)` 与 `retry_job(...)`：分别以 CAS 抢占 `queued -> running`、终态 `failed/partial/stopped -> queued`；`job_can_write` 只对 running 返回真，终态 stop 为幂等 no-op。
- `finish_job(job_id, map_id, owner_id, *, status, map_status, step, cursor, counts, failed_units, error_code, event_type) -> MapJob | None`：只接受当前 running job，在同一 `BEGIN IMMEDIATE` 内以 running CAS 写 terminal job、map status 和终态 event；stop/delete 已先获锁时返回 `None`，迟到 finish 不复活状态。普通 `update_job` 仅允许 expected running 状态，queued→running 仍只能走 `claim_job`。
- `save_unit_checkpoint(...)`、`get_unit_checkpoint(...)`、`completed_units(...)`：持久化发现、引用、相似度单元完成状态，供 retry 仅重排失败/缺失单元。
- `add_nodes(..., job_id=...)` / `add_edges(..., job_id=...)`：写事务内同时验证 owner、地图未删除和 job running，避免外部资格检查与写入间 TOCTOU。
- `update_node_import_result(map_id, node_id, owner_id, ...)`：owner/node 同事务作用域回写 document/import 状态。
- `put_embedding(...)`：拒绝空向量、非有限元素、空范数，并支持显式 `dimension` 校验。

删除在事务内先写墓碑，再清理该地图 jobs/checkpoints/events/nodes/edges/idempotency；晚回调只能资格失败，不会复活地图。

旧库升级先按 owner/key、活动墓碑优先、created_at/job_id/map_id 稳定排序选 canonical，仅删除重复 idempotency binding，不删除 map/job；每条重复绑定写入 `literature_map_idempotency_migration_log`，然后再建立 owner/key 唯一索引。

## 本轮精准验证

- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_identity.py`：退出码 0，16 passed。
- `.venv/bin/ruff check backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py`：退出码 0，All checks passed。
- `.venv/bin/python -m pytest -q tests/literature_maps`：退出码 1，37 passed / 2 failed；失败为现有 service retry 仍在 queued 状态调用普通 `update_job`，以及旧测试直接从 queued 写 completed，需由 service/test 接入 claim/finish 契约。
- 未运行全量 pytest、真实外部 API、生产数据库、部署或前端测试；service `_finish` 尚待接入 `finish_job`。

### 续接验证

- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_identity.py`：退出码 0，16 passed。
- `.venv/bin/ruff check backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py`：退出码 0，All checks passed。
- `.venv/bin/python -m pytest -q tests/literature_maps`：退出码 1，38 passed / 6 failed；5 项属于其他 agent 的 import bridge resolver/error seam，1 项属于 service retry 在 queued 状态调用普通 `update_job`，本轮未修改这些文件。
