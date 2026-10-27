# Spec043 Task11 第三阶段 B：批次元数据 Worker 交接

日期：2026-10-28 02:39（Asia/Shanghai）  
范围：仅后端 `expand_batch` metadata worker、批次状态投影/恢复、显式 metadata retry 及后端测试；未实现 metadata 来源以外的新工作流。

## 实现结果

- `run_expansion_batch` 使用既有 `claim_auxiliary_job`、300 秒 lease 和 token CAS；调用现有 `SemanticScholarGraphClient.batch` 与 metadata parser，最多处理本批 20 个新增节点。请求使用既有共享限流器和有限重试，不引入来源 client 或模型执行器。
- 持久请求缓存按 `operation=metadata`、规范 identity、固定字段集及 `literature-map-expansion-metadata-v1` 版本分区，使用现有 TTL。成功的无摘要结果进入缓存；错误响应不缓存。显式重试 `skipped_no_abstract` 节点时只绕过该节点缓存一轮；重试幂等重放不增加代数或再次联网。
- 元数据写入、仅补缺失 abstract 与 Semantic Scholar 来源证明、增量登记现有 analysis queue child、批次 item/count/status 更新和 auxiliary lease 释放在同一事务内完成。不会覆盖已有摘要及其他论文字段；节点或种子已移除时不会复活节点。
- 成功提交后仅唤起现有 analysis queue scheduler，且队列暂停时不派发。没有调用全图 `ensure_analysis_queue`。暂停中的在途合法 worker 可以持久化元数据/待分析状态；恢复通过既有 auxiliary recovery 对齐批次。
- `finish_analysis` 同事务更新关联批次投影；启动恢复会按持久 analysis child 状态校正批次进度。显式 metadata retry 复用 `POST /jobs/{job_id}/retry`，严格接受 `node_ids`、`steps=["metadata"]` 与幂等键；已有空请求行为不变，同键异参返回冲突。

当前批次 item 状态包括：`metadata_pending`、`metadata_failed`、`skipped_no_abstract`、`identity_unresolved`、`skipped_removed`、`analysis_queued`、`analysis_running`、`analysis_failed`、`completed`。批次计数包括：`added_count`、`existing_count`、`total`、`metadata_pending`、`metadata_failed`、`identity_unresolved`、`skipped_no_abstract`、`skipped_removed`、`analysis_queued`、`completed`、`failed`。

## 复用的现有接缝

- `SemanticScholarGraphClient.batch`、固定 `SEMANTIC_SCHOLAR_METADATA_FIELDS`、`_parse_search_payload`、`deterministic_identity_key`。
- `literature_map_request_cache` 的 key/get/put 和现有缓存 TTL。
- auxiliary job 的 claim、lease、token CAS、typed recovery。
- `_merge_analysis_queue_items_tx`、`_create_analysis_tx` 及现有 `MapAnalysisService._schedule_analysis_queue`。队列 helper 仅追加本批新 child，并保留旧 queue item。
- `finish_analysis`、analysis queue pause/resume/retry 生命周期；没有新增 public route 或第二 scheduler/executor。

## 验证记录

以下均在 worktree 内执行，临时 SQLite 由 pytest `tmp_path` 创建，命令未访问外网或真实数据库。

| 命令 | 结果 |
|---|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps/test_map_expansion_batch.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_api_errors.py -q --basetemp=/private/tmp/spec043-worker-focused-suite-20261028` | 退出码 0；74 passed（3.27s） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_expansion_batch.py tests/literature_maps/test_map_auxiliary_jobs.py` | 退出码 0 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `git diff --check` | 退出码 0 |

缓存元数据回归先失败，暴露缓存写入缺少 operation/identity/fields/version 描述字段；修正现有 cache writer 调用后，精确重试为 2 passed。最终 74 项定向组复验通过。

## 尚未实现与边界

- 本阶段没有实现 Task11 后续 UI、真实 API E2E、部署或全量 Spec 回归；不据此声称 Spec043 已验收或完成。
- 没有实现 batch apply/revalidate、分页 handler 或其他 Task11 阶段功能。
- 无生产数据库、外网 Semantic Scholar、模型服务调用。
- 等待 backend reviewer 对本阶段改动独立复审。
