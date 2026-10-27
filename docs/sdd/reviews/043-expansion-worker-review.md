# Spec043 Task11 第三阶段 B 后端评审

- 评审者：backend-reviewer
- 模型：临时 Luna xhigh
- 日期：2026-10-28
- 范围：仅当前 backend/** 改动和后端测试；对照冻结接口合同 §2 retry、§3、§5 与阶段报告。未评并行前端改动；未将本阶段之后的 handler 或 UI 工作作为缺陷。

## 发现

未发现有把握的 P0/P1/P2 后端问题。

## 已核对项

- `run_expansion_batch()` 通过既有 `claim_auxiliary_job` 和 `auxiliary_job_can_write` 获取并复核 owner/map/operation、worker token 与 lease；来源请求在事务外执行，领域结果由 `finish_expansion_batch_metadata()` 在同一事务内复核资格后提交。失效 token 不会提交节点、队列或批次状态。
- metadata worker 使用既有 `SemanticScholarGraphClient.batch()` 和固定字段集，最多处理本批 20 个待补节点。响应只在确定身份匹配后可补写缺失 abstract 和 `expansion_abstract_source` 证明；不会覆盖现有 abstract 或改写 title、external IDs 等其他论文字段。节点/seed 已移除、身份未定、无摘要和来源失败分别落入相应状态。
- request cache 按 metadata operation、稳定 identity、字段集和版本保存，错误响应不写缓存；显式重试只针对本批 `metadata_failed` / `skipped_no_abstract` 节点，并以事务幂等记录约束同键重放和代数递增。重试的 `metadata_refresh` 会绕过持久缓存。
- 已核实父会话指出的客户端内存缓存疑点：`SemanticScholarGraphClient.batch()`（`backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py:296-302`）直接调用 `_request()`；`_batch_cache` 只由 `enrich()`（同文件 `:396-428`）读取/写入。worker 与显式 retry 均直接调用 `batch()`，因此不会命中客户端旧的无摘要内存缓存。
- metadata 完成、analysis queue 增量登记、batch item/count/status 投影及 auxiliary lease 释放位于一个 store 事务。采用现有 source hash 与 queue helper，保留既有 queue items；没有摘要或失败的节点不会被伪装成已分析。
- 暂停中的在途请求可以在 lease 有效时保存合法元数据，但不会派发暂停队列；resume 通过 typed recovery 恢复未完成的 metadata 步骤。`analysis_wait` 仅对齐已持久化的 analysis child，analysis finish 同事务更新批次投影。removed 节点不会被复活。
- retry 路由复用现有 `POST /jobs/{job_id}/retry`：batch 请求严格校验 `node_ids`、`steps=["metadata"]` 与幂等键；legacy 空请求仍走旧兼容语义。恢复按 operation 进入专用 handler，不落入通用建图 handler。

## 定向验证

执行 14 个精确后端用例，分两组：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_no_abstract_retry_bypasses_persisted_cache_once \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_batch_metadata_worker_updates_only_abstract_proof_and_schedules_after_commit \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_rate_limit_stays_terminal_until_explicit_retry \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_finishes_during_pause_and_resume_reconciles_projection \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_batch_analysis_finish_and_restart_reconcile_without_repeating_work \
  tests/literature_maps/test_map_expansion_batch.py::test_batch_retry_payload_is_strict_and_uses_existing_job_route \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_existing_analysis_queue_resume_releases_paused_batch_to_typed_recovery \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_expired_auxiliary_token_cannot_write_or_finish_after_recovery
```

结果：8 passed。

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_requires_exact_identity_and_skips_removed_nodes \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_cache_is_persistent_between_service_instances \
  tests/literature_maps/test_map_expansion_batch.py::test_removed_node_during_metadata_request_is_skipped_without_resurrection \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_late_token_cannot_write_after_lease_expiry \
  tests/literature_maps/test_map_expansion_batch.py::test_expansion_metadata_merge_preserves_existing_analysis_queue_items \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_invalid_page_payload_and_metadata_batch_provider_failure_are_typed
```

结果：6 passed。总计 14 passed。未运行全量测试、未访问外网或模型、未操作真实数据库、未部署服务。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **PASS**（限 Task11 第三阶段 B 后端 metadata worker、批次投影恢复和显式 retry）。
