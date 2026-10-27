# Spec043 Task11 后端分页阶段交接

日期：2026-10-28  
阶段：已确认范围内的后端分页实现，等待独立复审  
基线：`ee836345`

## 实现范围

- `MapPreview` 返回 `preview_revision` 和可空 `pagination`。分页仅接受冻结配置 `{version: 1, page_size: 50, max_candidates: 500}`，仅用于 references/citations；不传配置仍走旧预览路径。
- `POST /api/literature-maps/{map_id}/previews` 为显式分页创建 `preview_page` 作业；`POST /api/literature-maps/{map_id}/previews/{preview_id}/load-more` 按 `expected_preview_revision`、严格布尔 `retry_failed` 和幂等键排队。
- 新页复用 `literature_map_jobs`、现有 executor、300 秒 auxiliary lease、worker token CAS、恢复路由和请求缓存；没有建立第二个执行器。既有 `SemanticScholarGraphClient.graph_edges` 接收每页 50 条与服务端 offset，复用其 parser、全局限流和有限重试。
- 候选、身份去重、next cursor、分页状态和 job finish 在同一个 auxiliary token 事务提交。失败页保留已成功候选与 next cursor，只保存 failed cursor，必须使用 `retry_failed=true` 显式续试。循环/不前进游标会失败；未知 total 保持 null；达到 500 个唯一候选后进入 capped。
- lease 接管耗尽时在回收事务中把对应预览从 loading 更新为 failed，并将 `MAP_JOB_LEASE_EXHAUSTED` 存为安全错误；通用 job retry 被拒绝，恢复必须走 load-more 显式失败页重试。
- 对分页预览禁用旧单预览 apply，返回 `MAP_PREVIEW_REVALIDATION_REQUIRED`。本阶段没有实现 revalidate、batch-apply、expand_batch 元数据或新来源客户端。

## 复用与变更文件

- 复用：`SemanticScholarGraphClient.graph_edges` / `SemanticScholarGraphPage`、现有 `_preview_candidate` 与 `_to_node`、SQLite auxiliary claim/finish/reaper、mutation idempotency 表、请求缓存、`recover_auxiliary_jobs` 的 typed handler 分派。
- 修改后端文件：`backend/app/api/routes_literature_maps.py`、`backend/app/literature_maps/application/service.py`、`backend/app/literature_maps/domain/models.py`、`backend/app/literature_maps/infrastructure/store.py`。
- 测试：新增 `tests/literature_maps/test_map_preview_pagination.py`；调整 `tests/literature_maps/test_map_auxiliary_jobs.py` 中无效 preview_page 作业的终态断言。测试名按能力命名，没有 Spec/Task 编号。

## 定向验证

所有 pytest 使用 `/Users/wjh/ResearchAgent/.venv/bin/python`，测试 SQLite 由 `tmp_path` 隔离。

| 命令 | 结果 |
|---|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_preview_pagination.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_schema_migrations.py` | exit 0；36 passed（1.89s） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/api/routes_literature_maps.py backend/app/literature_maps/application/service.py backend/app/literature_maps/domain/models.py backend/app/literature_maps/infrastructure/store.py` | exit 0 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | exit 0；`test layout: ok` |
| `git diff --check` | exit 0 |

覆盖包括严格请求体与 preview 序列化、创建幂等重放/异参冲突、续页旧 revision 幂等回放、并发单飞、50 页边界与 500 唯一候选上限、重复身份但推进 cursor、空页仍有 next、未知 total、游标循环、429 失败保留旧候选并显式重试、owner/map/seed 校验、seed 在网络请求期间被移除、过期 token 不写、lease 耗尽后显式重试，以及重启后 typed preview_page 恢复。

## 未覆盖与交接

- 未访问 Semantic Scholar 网络、未运行真实数据库、未启动或部署服务、未运行全量测试。
- 分页完成后的跨预览 revalidate 与原子 batch-apply、expand_batch 元数据/摘要队列接缝仍留后续阶段；当前旧 apply 会明确拒绝分页预览。
- 请独立复审本次分页差异，尤其检查 preview/job revision 一致性、分页失败与过期 worker 的事务边界，以及重试和恢复语义。

## 追加：修复 P1 坏页缓存重试

日期：2026-10-28  
复审依据：`docs/sdd/reviews/043-expansion-pagination-review.md`

- RED 复现：在隔离 SQLite 的真实 request-cache 表预置 offset=50、`next_offset=50` 的坏页；首次续页按预期失败。旧逻辑再次 `retry_failed=true` 后仍命中坏缓存，状态继续 failed，fake provider 没有收到 offset=50 请求。
- 修复：load-more 接受失败页重试时，在排队事务内只删除该 preview 的失败 relation/offset/page-size 对应 request-cache key；其它成功页和地图缓存保留。分页 worker 将 fresh graph page 延迟到 offset、页大小、total 和 cursor 推进校验通过后才写共享缓存，因此新响应中的循环 cursor 不会再写为 24 小时成功缓存。重试仍使用原 `SemanticScholarGraphClient`，沿用共享限流和有限 Retry-After/指数退避。
- 崩溃恢复：有效页在通过分页校验后仍进入共享缓存；新增回归验证 worker 在 finish 前 lease 过期后，typed recovery 能复用该有效缓存，不重复请求来源。
- 新增回归验证坏缓存会被目标页 retry 清除、来源修正页只请求一次并覆盖该 offset 缓存、已成功的 offset=0 缓存未被删除；新收到的坏 cursor 响应不会进入缓存。

修复后执行命令及结果：

| 命令 | 结果 |
|---|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_preview_pagination.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_schema_migrations.py` | exit 0；38 passed（1.99s） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/application/service.py backend/app/literature_maps/infrastructure/store.py` | exit 0 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | exit 0；`test layout: ok` |
| `git diff --check` | exit 0 |

未访问外网、真实数据库或部署服务；未运行全量测试。等待原 reviewer 对该 P1 窄复核。
