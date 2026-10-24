# Task09 后端交接报告：摘要队列与图谱视图兼容

## 范围与状态

- 角色：backend-dev；分支：`codex/spec043-map-interaction`。
- 状态：后端实现与 `tests/literature_maps` 定向回归完成，待 backend-reviewer、backend-tester 和主会话收口；未部署、未启动服务、未调用模型/网络、未触碰全文下载/导入链。
- 权威字段已追加到 [`task-09-interface-contract.md`](task-09-interface-contract.md) 第 6 节。

## 已实现

1. 持久摘要队列复用 `MapJob(operation="analysis_queue")` 聚合和既有 `MapAnalysis`/`MapJob(operation="analysis")` 子项；无摘要节点持久为 `skipped`，摘要 source version 或服务端模型配置变化创建新版本，旧版本保留。
2. `ensure`、GET、暂停、恢复、失败重试均按地图与 owner 隔离并使用持久幂等记录；GET 不创建队列/分析、不提交执行器。新节点、preview 摘要变化和恢复节点通过应用层自动触发 ensure；旧图只能由显式 ensure POST 补入。
3. 队列摘要读模型固定为：

   ```json
   {
     "schema_version": "literature-map-v1",
     "map_id": "…",
     "queue_job_id": "…",
     "state": "active",
     "pause_reason": null,
     "counts": {"total": 2, "completed": 0, "queued": 1, "running": 0, "failed": 0, "skipped": 1},
     "current": null,
     "failed_items": []
   }
   ```

   未 ensure 的地图返回 `queue_job_id: null`、零计数和 `state: completed`，不会写库。
4. `claim_analysis_job` 使用数据库写锁下的 `queued -> running` CAS、持久 worker token/lease、attempts 上限；重复 claim、错误 token、删除地图/移除节点后的迟到 finish 均 fail-closed。active 队列重启会恢复 queued/running 子项，paused 队列不被自动唤醒；配置/鉴权错误会安全暂停队列。
5. `PATCH /{map_id}/view` 增加可选 `label_mode: all|neighbors|hidden`；旧图缺失时读默认 `all`，省略字段保存时保留既有值。

## 接口路径

- `GET /api/literature-maps/{map_id}/analysis-queue`
- `POST /api/literature-maps/{map_id}/analysis-queue/ensure`：`{idempotency_key}`
- `POST /api/literature-maps/{map_id}/analysis-queue/pause`：`{idempotency_key}`
- `POST /api/literature-maps/{map_id}/analysis-queue/resume`：`{idempotency_key}`
- `POST /api/literature-maps/{map_id}/analysis-queue/retry`：`{idempotency_key, analysis_ids?}`

所有接口使用现有 `OWNER_ID` 与 `schema_version` envelope；读模型不包含 worker token、原始异常、凭据或全文/下载状态替代物。

## 代码与测试

- 生产实现：`backend/app/literature_maps/infrastructure/store.py`、`backend/app/literature_maps/application/analysis.py`、`backend/app/literature_maps/application/service.py`、`backend/app/literature_maps/domain/models.py`、`backend/app/api/routes_literature_maps.py`。
- 新测试：`tests/literature_maps/test_map_analysis_queue.py`，按能力命名，无 Spec/Task 数字。
- `./.venv/bin/python -m py_compile backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/analysis.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py backend/app/literature_maps/domain/models.py`：退出码 0。
- `./.venv/bin/python scripts/check_test_naming.py`：退出码 0。
- `./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py`：退出码 0，47 passed。
- `./.venv/bin/python -m pytest -q tests/literature_maps`：退出码 0，151 passed。
- `git diff --check -- backend tests/literature_maps docs/sdd/plans/043/task-09-interface-contract.md`：退出码 0。

## 未执行门禁

本交接不代替独立 backend review、backend tester 的真实 API smoke、前端接入验证、全量回归或部署验收；这些由主会话按 SDD 门禁继续安排。知识库导入失败修复按本阶段要求未修改。

## 独立 review 修复追加（2026-10-24）

本节追加记录 backend review BLOCK 的逐项红/绿证据，保留前述 151 passed 历史证据，不覆盖原记录。

### P1-1 自动 ensure 配置指纹

- 红测：`test_automatic_enqueue_reconciles_after_model_configuration_changes` 首次运行时退出码 1；模型从默认配置切换后仍只有 version 1，原自动 key 冲突被旧代码吞掉。
- 修复：自动同步 key 现在包含 `analysis_config_fingerprint()`（规范化服务端模型配置）；配置变化生成新的 `analysis_id/version`，旧版本仍可读。`_enqueue_abstract_summaries()` 只吞并发删除的 `LookupError`，幂等参数冲突不再静默忽略。
- 绿证据：同一测试在队列定向运行中通过，断言 `{1: "qwen3.8:27b", 2: "changed-model"}`。

### P1-2 持久 due retry、attempt 上限与暂停

- 红测：`test_due_transient_failure_is_requeued_automatically_and_pauses_are_respected` 首次运行时退出码 1；将 `next_retry_at` 调到过去后再次运行没有第二次模型调用。
- 修复：新增 `requeue_due_analysis_jobs()`，在写事务中同时检查持久 deadline、queue 未暂停和 `_ANALYSIS_MAX_ATTEMPTS`，原子地将 failed child 与 analysis 置回 queued/pending；队列运行器每次调度前调用该 transition。进程内只用一次性 Timer 唤醒既有 queue executor，重启由持久 deadline 重建唤醒，不在 worker 中 sleep；达到上限或 paused 不重试。
- 绿证据：同一测试通过，覆盖 paused 不唤醒、due 自动重排和 attempts=3 保持 failed；队列定向测试通过。

### P1-3 provider 鉴权/配置/限流分类与原子暂停

- 红测：`test_provider_auth_failure_is_classified_and_pauses_the_queue`、`test_provider_rate_limit_is_retryable_without_pausing_the_queue` 首次运行分别退出码 1；普通 provider `RuntimeError` 被保存为 `MAP_MODEL_FAILED`，401 不暂停、429 无稳定错误码。
- 修复：在现有 `run_chat` 边界分类 HTTP 401/403、404/缺模型、429、连接/超时为稳定 `MapAnalysisError`；401/403/缺模型使用不可重试 auth/config code，429/网络使用有界 transient code。`finish_analysis(..., queue_pause_reason=...)` 在同一持久事务内完成 child 失败、analysis 错误和 queue paused，消除失败与暂停之间的 claim 窗口。
- 绿证据：两项 provider 测试通过，401 读模型为 `paused/MAP_MODEL_AUTH_REQUIRED`，429 为 `partial/MAP_MODEL_RATE_LIMITED/retryable=true`。

### P1-4 摘要队列与共享建图槽位公平性

- 红测：旧实现用共享 2-worker executor 运行两个阻塞 map drain 时，graph task 在 release 前保持 pending。
- 修复：队列 runner 每个 executor turn 只 claim/run 一个 child；运行时为摘要队列注入独立单槽 `analysis_executor`，graph/preview 继续使用通用 2-worker executor。仅由现有 queue store state/一次性 dispatch guard 管理，不新增第二套持久调度状态机；后续 child 由同一 queue executor 公平轮转。
- 绿证据：`test_queue_children_release_shared_slots_for_other_map_work` 通过：两个 map provider 调用阻塞时，通用 executor 中的 graph task 仍在 release 前完成。

### P1-5 lease 有效性、原子 reaper 与 late finish

- 红测：`test_analysis_queue_recovery_only_requeues_expired_leases_and_rejects_late_finish`、`test_analysis_finish_fails_closed_after_lease_expiry` 首次运行退出码 1；有效 lease 被 recovery 抢走，过期 lease 持 token 仍可 finish。
- 修复：`recover_analysis_jobs()` 仅在 `lease_expires_at IS NULL OR <= now` 的条件 UPDATE 下 requeue；有效 lease 不被抢占，重复 reaper 无副作用。`finish_analysis()` 同时校验 worker token 与可解析且未过期的 lease，并在 UPDATE CAS 中再次带 lease 条件；本阶段采用 300 秒有界 lease、无长生成 renew 协议，超 lease 回调 fail-closed。paused queue 的 child 可恢复为 queued，但聚合仍保持 paused。
- 绿证据：过期/有效 lease、旧 token late finish 的测试通过；受影响 lifecycle recovery 测试已改为先显式过期 lease 后验证一次恢复。

### P2 schema 6 迁移原子性

- 红测：`test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry` 首次运行退出码 1；repair 故障后新 job 列已落库，无法完整回滚。
- 修复：base bootstrap 仍使用既有幂等 `executescript`，但 schema 6 的 node/preview/job 增量 DDL、旧 group 修复、claim/owner index 与 schema version marker 全部移入同一个 `BEGIN IMMEDIATE`/`COMMIT`；异常统一 rollback，避免迁移半完成。
- 绿证据：同一测试通过，故障后四个新增列均不存在，清除故障后升级到 schema 6，重复 initialize 仍成功。

### 本轮复核命令与退出码

- 红测：`./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py`：退出码 1，`9 passed, 7 failed`（修复前基线）。
- 修复后队列能力：同一命令退出码 0，`18 passed`。
- 修复后受影响分析/存储精准集合：`./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py`：退出码 0，`56 passed`。
- runtime 受影响集合：`./.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api.py`：退出码 0，`45 passed`。
- 生产文件 `py_compile`：退出码 0；本轮未运行模型服务、网络、生产 DB、部署或全量回归。

## 第二轮 review BLOCK 修复追加（2026-10-24）

保留历史 151 passed 与第一轮修复记录，追加第二轮 reviewer 复现的两个 P1 和 timer 生命周期修复证据。

### 红测证据

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py -k 'runtime_explicit_analysis or expired_queue_lease or shutdown_cancels_retry'
退出码 1，3 failed，18 deselected
```

红测分别证明生产 runtime 将显式分析错误绑定到自动队列单槽、存活进程无 lease 到期唤醒、shutdown 无法取消旧 retry timer。

### 修复与绿证据

- P1 executor 隔离：`runtime.py` 将 `executor` 绑定通用 2-worker 池，`queue_executor` 继续使用独立单槽；真实阻塞 runner 的跨地图显式分析测试通过。
- P1 lease reaper：claim 后按持久 `lease_expires_at` 注册一次性 timer；到期 callback 在锁内复用原子 `recover_analysis_jobs()` 并重新投递 queue/explicit job；过期 late finish 仍受 token+lease CAS 保护；attempts 达上限的过期 running child 终止为 `MAP_ANALYSIS_LEASE_EXPIRED`，不留下永久 queued。
- shutdown：`MapAnalysisService.shutdown()` 取消/清空 retry 与 lease timer，runtime reset 在 executor 关闭前调用；`test_analysis_service_shutdown_cancels_retry_wakeup_without_late_store_write` 与 `test_analysis_service_shutdown_cancels_lease_reaper_without_late_recovery_write` 验证旧 callback 在关闭闸门下不再持久写。

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py
退出码 0，23 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py
退出码 0，61 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api.py
退出码 0，45 passed

./.venv/bin/python scripts/check_test_layout.py && ./.venv/bin/python scripts/check_test_naming.py
退出码 0（test layout: ok；test naming check passed）
```

本轮仅改 backend 与 `tests/literature_maps` 能力测试及本交接报告；未部署、未启动服务、未调用模型/网络、未访问生产 DB、未改全文/聊天/下载导入链、未运行全量回归。外部 queue 字段与接口路径保持不变。

## 最终 review P1 窄修追加：reset-vs-final-finish barrier（2026-10-24）

### 红测

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py -k 'runtime_reset_and_final_analysis_finish_are_atomic'
退出码 1，1 failed，23 deselected（旧实现）
```

旧 worker 在 `store.finish_analysis` 最终写入前被 barrier 暂停时，旧 runtime reset 可先返回，释放 barrier 后仍写入 `completed`。

### 修复

新增 `_finish_analysis_if_active()`，成功与 error finish 共用 `_queue_dispatch_lock`：shutdown 标记检查与最终持久 CAS 同一临界区，锁只覆盖短 SQLite finish，不覆盖模型生成。reset 若先关闸则 finish 不写；finish 若先进入则 reset 等待事务完成后再返回，杜绝 reset 返回后的旧 worker 持久写。

### 绿测

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py
退出码 0，25 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py
退出码 0，63 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api.py
退出码 0，45 passed
```

`check_test_layout.py`、`check_test_naming.py`、后端生产文件 `py_compile` 和 `git diff --check` 均退出码 0。外部 API/字段未变；不部署、不启动服务、不调用模型/网络、不访问生产 DB、不运行全量回归。

## 真实 API 迟到版本诊断收口：manual regeneration（2026-10-24）

### 只读诊断与结论

本轮只读核对了 `docs/sdd/plans/043/task-09-api-e2e.md` 与 `task-09-runs/20261024-153416-task09-graph-attention/evidence.json`，并用临时 SQLite 重放了“自动 enqueue → 旧图 ensure → 完成 → 再次 ensure”和并发 ensure。当前自动路径按 `node_id/source_version/model_id` stable key 在同一事务中复用，重放没有生成重复版本。

随后由 browser job-source 证据确认：`analysis_id=42cf77712d7c430fb4b4311a3d573931` 是本轮唯一主动 manual regeneration，对应 `job_id=3264b0f9e3cf4e5f9183c9e4a6faf95c`；它与 version 1 共享 source/model 是用户主动重分析的合法新版本，不是自动 ensure 重复。该行为符合既定合同：manual regeneration 可以在相同 source/model 下创建新 version，旧 version 保留。此前只读证据缺少 trigger attribution，不能单独完成该归因；browser 证据补齐后，结论为后端无新 P1。

### 代码与测试处置

本轮未保留针对配置指纹的试探性 backend/test 改动；外部 queue/API 字段、stable ensure 合同和 manual regeneration 语义均保持原实现。真实 API 报告中的 provider `429/SEMANTIC_SCHOLAR_RATE_LIMITED` 仍是独立门禁阻塞，不由本轮后端代码处理；前端重复触发问题交由前端 agent。

收口复核（撤回试探性改动后）：

```text
./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py
退出码 0，25 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_analysis_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py
退出码 0，63 passed

./.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api.py
退出码 0，45 passed
```

本次诊断未访问生产 DB、未启动服务、未调用模型/外网、未重试真实地图、未部署或提交；只读证据和最终 manual regeneration 归因已记录，后端无代码变更需部署。

## KB 导入 arXiv 身份窄修（2026-10-24 16:11，现有 bug）

### 复现与范围

- 诊断依据：`import-failure-diagnosis.md` 的最新证据。官方公开 Atom 元数据 fixture 固定为 `1809.07041v1`、标题 `Exploring Visual Relationship for Image Captioning`、年份 `2018`、作者 `Ting Yao / Yingwei Pan / Yehao Li / Tao Mei`；候选记录作者前三项规范化后相同，第四项为 `T.Mei`。
- 修复前红测：`T.Mei` 被 `_author_key` 规范化为 `tmei`，官方 `Tao Mei` 为 `taomei`，作者分数为 `3/4=0.75`，低于原 `AUTHOR_THRESHOLD=0.80`，指定 arXiv ID 路径错误返回 `ARXIV_IDENTITY_CONFLICT`。
- 只改 `backend/app/paper_discovery/infrastructure/arxiv_adapter.py` 与 `tests/paper_discovery/test_arxiv_adapter.py`；未改下载/导入链、其他来源适配器、队列或外部接口。

### 最小修复

- 保留 exact arXiv ID、标题/年份门禁和 `AUTHOR_THRESHOLD=0.80`。
- 仅 `lookup_by_id` 的指定 ID 解析路径允许“带点的一字母首字母 + 完全相同姓氏”（如 `T.Mei` ↔ `Tao Mei`）的唯一一对一配对；标题搜索路径明确继续不放宽。
- 精确规范化先匹配；缩写候选只有在两侧各自唯一兼容时才计数。错首字母、不同姓、歧义全名、无分隔的 `Tmei`、一对多及重复身份不会通过配对增加分数。缓存键保留原始标点形状，避免 `T.Mei` 与 `Tmei` 共用结果。

### 红绿证据

```text
红测（修复前）：
./.venv/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py -k 'official_metadata_with_author_initial_abbreviation or rejects_unsafe_author_initial_variants'
退出码 1，1 failed，6 passed，10 deselected

新增身份/反例测试：
./.venv/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py -k 'official_metadata_with_author_initial_abbreviation or rejects_unsafe_author_initial_variants or title_lookup_does_not_relax_author_matching or exact_id_cache_keeps_abbreviation_shape_distinct'
退出码 0，9 passed，10 deselected

arXiv 适配器能力回归：
./.venv/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py
退出码 0，19 passed

适配器与 USENIX 来源集成回归：
./.venv/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py tests/paper_discovery/test_usenix_publication_source.py
退出码 0，61 passed，5 warnings（既有 PyMuPDF deprecation warnings）
```

静态门禁：`scripts/check_test_layout.py`、`scripts/check_test_naming.py`、目标生产/测试文件 `py_compile` 与目标 `git diff --check` 均退出码 0；本轮未访问生产 DB、未调用网络/模型、未下载或导入论文、未部署、未运行全量回归。独立 paper-source review 由主会话另行安排后再进入部署复验。

## KB import_candidate canonical 接缝窄修（2026-10-24 21:01，现有 bug）

### 只读根因与范围

- `import_candidate → KnowledgeBasePaperImportAdapter.import_paper` 先通过 `create_immutable_document` 写出完整 canonical document，随后旧代码重新构造只含 legacy 字段的 `PaperRecord` 交给默认 `GenerationBoundIndexPort`。
- 因而 strict bundle/manifest publisher 取不到 `document_id/source_sha256/media_type`，v1/v2 仅被标记 indexed，`indexed_source_sha256` 保持空、`source_hash_state=legacy_unknown`，且不产生 manifest。
- 本轮只改 `backend/app/knowledge_base/application.py` 内 `KnowledgeBasePaperImportAdapter` 与 `tests/kb/test_kb_application_boundary.py`。默认 indexer 直接接收已创建的 canonical mapping；注入式 legacy indexer 继续接收 `PaperRecord`，避免破坏兼容 seam。未改 schema/API/下载器、未手写 hash/manifest、未放宽 full gate。

### TDD 红绿证据

```text
红测（旧 adapter）：
./.venv/bin/python -m pytest -q tests/kb/test_kb_application_boundary.py -k 'default_paper_import_publishes_canonical_manifest_and_hash'
退出码 1，1 failed，6 deselected；canonical record 的 indexed_source_sha256 仍为 null。

窄修正例与 legacy 缺字段反例：
./.venv/bin/python -m pytest -q tests/kb/test_kb_application_boundary.py -k 'default_paper_import_publishes_canonical_manifest_and_hash or legacy_index_record_without_source_hash'
退出码 0，2 passed，6 deselected，5 warnings（既有 PyMuPDF deprecation warnings）

KB strict publication / source safety / reindex 能力：
./.venv/bin/python -m pytest -q tests/kb/test_kb_application_boundary.py tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_document_reindex.py
退出码 0，37 passed，5 warnings（既有 PyMuPDF deprecation warnings）

paper-import 兼容、补偿与 generation binding：
./.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import.py tests/paper_discovery/test_import_compensation.py tests/paper_discovery/test_paper_import_generation_binding.py
退出码 0，49 passed
```

新增默认导入回归实际断言：canonical `document_id`、源文件 SHA-256、payload source hash、manifest `source_sha256/indexed_source_sha256`、`source_hash_state=verified`；已有 owner capability、project association、generation marker、既有 metadata 与既有 manifest 保持不变。缺 canonical hash 的 legacy record 仍走未验证兼容路径，不伪造 verified/manifest；既有 source-byte mutation fail-closed 用例继续通过。

静态门禁：`scripts/check_test_layout.py`、`scripts/check_test_naming.py`、目标文件 `py_compile` 与目标 `git diff --check` 均退出码 0。本轮未访问生产 DB、未调用网络/模型、未执行 reindex、未下载论文、未部署、未运行全量回归；root 可在独立 review 后按授权单次执行既有 reindex 验收。

## Task-04 closure matrix hash maintenance after canonical import fix（2026-10-24）

### 维护理由与范围

- 最终全量回归此前唯一失败为 `tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered`：矩阵仍登记 canonical import 修复前的 `backend/app/knowledge_base/application.py` SHA-256 `3edeb07ab77b4d9db3f55535b35175bde45fff0b55ed9bb398f5ffa12ccb0368`，当前已评审的 canonical 接缝窄修文件哈希为 `222bece39de4bd36aa0b033e96995292263fdc11e15557d48ba39b0af896a244`。
- 按 Task-04 closure matrix 已确认的“实现变化后更新 inventory hashes/digest”配置维护约定，仅更新该受影响 inventory entry 与按 SHA-256 排序的 `inventory_digest`；未改测试断言、entry 名单、其他 inventory entry、entry 状态或旧 Task-04 签字。
- 新总 digest 为 `38af1e9c3ea0eebd2315485e6ccfc2141ef8ea0c09f386b125d8f7bb1cb378e0`。未新增未登记写入口，矩阵符号/AST 门禁仍使用原登记和 allowlist。

### 旧失败与维护后绿证据

```text
旧矩阵（维护前）——保留历史失败证据：
./.venv/bin/python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py
退出码 1，1 failed，1 passed；失败仅为 application.py SHA 与旧 inventory entry 不一致。

矩阵维护后：
./.venv/bin/python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py
退出码 0，2 passed。

canonical import 受影响能力：
./.venv/bin/python -m pytest -q tests/kb/test_kb_application_boundary.py
退出码 0，8 passed，5 warnings（既有 PyMuPDF deprecation warnings）。
```

本次只维护 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 的受影响 hash/digest 配置；未改生产代码、测试断言/名单、其他矩阵 entries，未重做 Task-04、未访问生产 DB、未启动服务、未调用网络/模型、未部署或运行全量回归。待 root 独立复核后交 backend tester 重跑最终全量回归。
