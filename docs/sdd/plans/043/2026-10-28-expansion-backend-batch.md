# Spec043 Task11 后端第三阶段 A：重核与原子批次

日期：2026-10-28  
基线：`f9f14397`（分页阶段已提交）  
范围：实现 `POST /previews/revalidate`、`POST /previews/batch-apply`，以及事务内 analysis queue 增量登记和 `expand_batch` outbox。未实现补摘要来源 worker、批次重试/恢复、analysis-wait 对齐；未部署。

## 实现

- 新增严格的请求模型和两条 owner-scoped 路由。请求拒绝未知字段、bool revision、重复 preview/candidate ID、超过两组选择，以及每组超过 20 个 candidate ID。
- `revalidate_previews` 在一个 `BEGIN IMMEDIATE` 中重核当前地图和预览版本、seed、方向、候选身份及墓碑状态；更新预览的候选状态、`base_revision`、`preview_revision`，返回有效/无效选项和变化摘要。它不写地图节点/边，也不访问来源。
- `batch_apply_previews` 先按操作范围查询幂等结果，再验证 map/preview revision、owner、同一活动 seed、preview kind 和候选归属。按确定身份跨方向去重；拒绝墓碑、无效身份、自环、超出 20 个新增节点或 200 个活动节点上限的请求。
- 节点、references/citations 两种真实有向 citation edge、单次地图 revision 增量、`expand_batch` outbox、analysis queue 子项、预览加入标志、幂等结果和事件在同一事务提交；任一失败整体回滚。仅为新插入且已有摘要的节点登记分析，不调用全图 `ensure_analysis_queue()`。
- 增量队列 helper 复用 `_create_analysis_tx()`、`_queue_counts_tx()` 和既有 `_hash_source()` 版本算法；保留已有 queue items 及暂停状态。无摘要的新节点持久化为 `metadata_pending`，供后续阶段的 worker 接续。
- 当批次没有 metadata 待办时，outbox 状态落为 `analysis_wait` 或 `completed`，不留在无法 claim 的空 `queued` 状态。

## 复用与阶段边界

- 复用 `literature_map_mutation_idempotencies`、现有 maps/previews/jobs/edges/analysis queue 表、`MapPaper.new()`、`_create_analysis_tx()`、`_append_event()` 和 `analysis._hash_source()`。
- 没有调用两次公开 `apply_preview()`，没有在批次事务内调用会自行开事务的 `ensure_analysis_queue()`；没有新增 worker/scheduler、来源客户端、PDF 流程或模型调用。
- `run_expansion_batch()` 仍是 fail-closed 占位处理器。metadata worker、analysis-wait 完成态投影与恢复属于后续阶段；本阶段未部署，不能据此宣称批次后台已可执行。

## 验证结果

以下均在 worktree 执行，Python 使用 `/Users/wjh/ResearchAgent/.venv/bin/python`。

| 命令 | 结果 |
|---|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps/test_map_expansion_batch.py tests/literature_maps/test_map_preview_pagination.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_api_errors.py -q` | 退出码 0；91 passed，3.96 秒 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/api/routes_literature_maps.py backend/app/literature_maps/application/service.py backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_expansion_batch.py` | 退出码 0 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `git diff --check -- backend/app/api/routes_literature_maps.py backend/app/literature_maps/application/service.py backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_expansion_batch.py` | 退出码 0；无 whitespace 错误 |

新测试覆盖双方向同身份单节点双边、已有节点、墓碑、owner/map/seed/kind 和候选归属、幂等回放与同 key 异参冲突、failed preview 可显式使用已成功候选、每方向 raw 20/21、跨方向 unique 20/21、活动节点 199/200、事务回滚、旧 queue item 保留、只登记新增节点、无摘要 outbox、严格 payload 与公共路由 envelope。

## 未完成与风险

- metadata 来源请求、摘要白名单写回、batch worker 的 lease/token CAS、analysis-wait 终态对齐与恢复均留给 Task11 后续阶段。
- 没有运行全量 collection、真实来源请求、模型、生产数据库或部署验证。
- 结束时共享工作树还显示以下前端文件有未提交改动；本阶段未编辑这些文件：`frontend/index.html`、`frontend/literature-maps.css`、`frontend/literature-maps.js`、`tests/frontend/fixtures/literature_map_component.html`、`tests/frontend/test_frontend_literature_map_contract.py`、`tests/frontend/test_frontend_literature_map_expansion.py`、`tests/frontend/test_frontend_map_analysis_contract.py`、`tests/frontend/test_frontend_map_groups_exports.py`、`tests/frontend/test_frontend_map_mobile_contract.py`。

## P1 修复记录：提交后调度已有摘要分析

复审报告：`docs/sdd/reviews/043-expansion-batch-review.md`。

- RED 复现命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps/test_map_expansion_batch.py::test_batch_apply_dispatches_new_abstract_queue_after_commit_and_replay_is_safe -q`。结果：退出码 1；数据库已有 queue child，但记录型 executor 的 `submit` 次数为 0。
- 修复：`LiteratureMapService.batch_apply_previews()` 在 store 事务成功返回后，检查持久化 batch outbox 是否含 `analysis_queued` child；有则读取现有 analysis queue，并调用 `MapAnalysisService._schedule_analysis_queue()`。没有调用全图 `ensure_analysis_queue()`，没有新增 executor。
- 幂等重放仍只返回原 batch/outbox 与 child，不会再次建 child；它可以再次请求调度以恢复提交后的调度失败，现有 map dispatch lock 会合并重复在途提交。事务异常发生在 store 返回前，不会触发调度；paused 状态会被现有 scheduler 保留并拒绝派发。
- 新回归覆盖：事务提交后 executor 可读到持久 child、同键重放不重复提交或建 child、不调用全图 ensure、暂停队列不派发、事务末端事件失败时不派发。
- 修复后复验：上表定向命令退出码 0，91 passed，3.96 秒；编译、test-layout 和 diff whitespace 检查均通过。仍未调用模型或部署。
