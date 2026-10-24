# Task09 后端定向测试报告：摘要队列与图谱视图兼容

## 结论

本报告保留首轮候选在全新临时数据根目录中的 `151 passed` 历史结果；backend-review 随后列明的 5 个 P1 与 1 个 schema P2 当时未被首轮集合覆盖，故 `151 passed` 不代表这些路径正确。修复候选重新验证后，完整 `tests/literature_maps` 为 `160 passed`，作者列出的受影响 runtime 精确集合为 `45 passed`，两次均退出码 `0`。这些结果只证明隔离后端测试通过，不是部署服务上的真实 API smoke，也不是 Spec043 最终验收或收口结论。

知识库导入失败 bug 不属于本轮 Task09 后端测试范围；本轮未修改业务代码、测试代码、模型配置、服务或生产数据。

## 依据与范围

- 已读取 `docs/sdd/plans/043/task-09-backend-report.md`。
- 已读取 `docs/sdd/plans/043/task-09-interface-contract.md` 第 6 节，核对队列 envelope、控制请求体、持久 worker token/原子 claim、恢复和 `label_mode` 字段。
- 已读取 `tests/literature_maps/test_map_analysis_queue.py`。现有测试按能力命名，覆盖本轮后端门槛，无需新增诊断测试。
- 按 `docs/sdd/plans/043/artifacts/task-08/regression-plan.md` 的隔离约定执行；没有复用旧真实地图、旧实体 ID 或旧 API 结果作为新版通过证据。

## 隔离环境

本轮使用唯一临时根目录 `/private/tmp/spec043-task09-backend-fSHbKQ`，并将以下写路径全部置于该根目录：SQLite（memory、literature maps、research、agent tasks、paper search）、KB、Qdrant、文章下载、浏览器 profile、pytest cache 和 basetemp。显式设置了 `PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false` 和旧回归计划要求的 `COMPACTION_SUMMARY_MODE=rule`；没有设置 `RUN_E2E`，没有启动服务或打开 8000 端口。

## 实际命令与结果

```text
env PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule \
  KB_DIR=/private/tmp/spec043-task09-backend-fSHbKQ/data/kb \
  QDRANT_PATH=/private/tmp/spec043-task09-backend-fSHbKQ/data/kb/qdrant \
  KB_META_PATH=/private/tmp/spec043-task09-backend-fSHbKQ/data/kb/papers.json \
  MEMORY_DB_PATH=/private/tmp/spec043-task09-backend-fSHbKQ/data/memory/memory.sqlite3 \
  LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task09-backend-fSHbKQ/data/literature_maps/literature_maps.sqlite3 \
  RESEARCH_DB_PATH=/private/tmp/spec043-task09-backend-fSHbKQ/data/research/research.sqlite3 \
  AGENT_TASKS_DB=/private/tmp/spec043-task09-backend-fSHbKQ/data/agent_tasks/agent_tasks.sqlite3 \
  PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task09-backend-fSHbKQ/data/paper-search/state.sqlite3 \
  ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-task09-backend-fSHbKQ/data/articles \
  PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-task09-backend-fSHbKQ/data/browser-profile \
  LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest -q tests/literature_maps \
  -o cache_dir=/private/tmp/spec043-task09-backend-fSHbKQ/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-backend-fSHbKQ/pytest-tmp
```

实际输出摘要：

```text
........................................................................ [ 47%]
........................................................................ [ 95%]
.......                                                                  [100%]
151 passed in 4.79s
```

| 项目 | 结果 |
|---|---|
| 退出码 | `0` |
| passed | `151` |
| skipped | `0` |
| failed | `0` |
| 运行范围 | `tests/literature_maps`，非全量 |
| 服务/真实 API | 未启动、未执行 |
| 模型/外网 | 未调用 |

## 关键能力覆盖

`tests/literature_maps/test_map_analysis_queue.py` 实际收集并通过了以下能力测试：

- `test_analysis_queue_ensure_is_idempotent_and_skips_missing_abstract`：ensure 稳定幂等、无摘要节点持久 `skipped`、不重复创建分析版本。
- `test_analysis_claim_requires_unique_persistent_worker_token_and_finish_fails_closed`：持久 claim 的唯一 worker token、重复 claim、错误 token 和正确 token finish 的 fail-closed 语义。
- `test_analysis_queue_is_serial_and_pause_resume_controls_following_items`：同一地图串行处理、pause 阻止后续 claim、resume 后完成队列。
- `test_analysis_queue_retry_reuses_failed_analysis_version`：失败项重试复用既有 `analysis_id`/版本，不创建新版本。
- `test_analysis_queue_pauses_on_configuration_failure_with_safe_action_code`：配置/鉴权失败转 `paused`，仅暴露安全 action code。
- `test_analysis_queue_removal_rejects_late_completion_and_drops_item`：节点移除后迟到完成回调被拒绝，不能复活节点。
- `test_analysis_queue_recovery_requeues_orphan_running_job_once`：重建服务后的 orphan running 恢复只执行一次。
- `test_analysis_queue_get_is_read_only_and_control_routes_are_owner_scoped`：API `GET` 不创建聚合 job，控制路由通过 owner-scoped TestClient 流程核对；该测试将作业执行器/队列 runner 打桩，属于应用内 API 契约测试，不是真实部署 API。
- `test_view_label_mode_is_optional_and_defaults_for_legacy_rows`：`label_mode` 可选，旧视图缺失字段时默认为 `all`。

## 风险与未覆盖项

1. 本轮没有运行真实部署服务上的 HTTP API E2E；没有验证真实执行器、真实模型/provider、真实 Qdrant/KB 或跨进程 worker 的运行时行为。上面的 TestClient 通过不能冒充真实 API smoke。
2. 本轮没有运行 `tests` 全量回归、浏览器测试、部署验证或 Spec 收口验收；没有使用旧回归样本 ID 冒充新版 Task09 通过。
3. 测试中的模型 runner、executor 和队列运行部分使用本地 stub/inline executor；它们只能证明持久状态和应用层合同，不能证明模型服务可用性或实际延迟/退避表现。
4. 失败恢复、owner 隔离和 GET 无副作用已由领域测试覆盖，但真实 API 门禁仍需由主会话按 SDD 验收流程另行安排；本报告不替代该门禁。

## 交接

- 结果：后端精确领域测试 `PASS`。
- 口径：仅为 Task09 backend-tester 定向证据；不宣称真实 API、全量回归、部署或 Spec043 收口通过。
- 进展日志：`.codebuddy/agent-logs/spec-043/task-09/backend-tester/20261024-113220.md`。

## 修复候选追加验证（2026-10-24）

### 隔离与结果

本轮没有复用首轮临时数据。完整 `tests/literature_maps` 使用新根目录 `/private/tmp/spec043-task09-backend-rerun-HFWvNV`；作者列出的受影响 runtime 集合使用另一个新根目录 `/private/tmp/spec043-task09-backend-runtime-rYygD5`。两次都显式设置 `PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`、`COMPACTION_SUMMARY_MODE=rule`，并将 SQLite、KB、Qdrant、文章下载、浏览器 profile、pytest cache/basetemp 置于对应临时根目录；未设置 `RUN_E2E`。

| 精确集合 | 退出码 | passed | skipped | failed | 输出 |
|---|---:|---:|---:|---:|---|
| `tests/literature_maps` | `0` | `160` | `0` | `0` | `160 passed in 4.94s` |
| `test_map_groups.py` + `test_map_export.py` + `test_map_import_bridge.py` + `test_map_api.py` | `0` | `45` | `0` | `0` | `45 passed in 1.01s` |

### 完整领域命令

```text
env PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule \
  KB_DIR=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/kb \
  QDRANT_PATH=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/kb/qdrant \
  KB_META_PATH=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/kb/papers.json \
  MEMORY_DB_PATH=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/memory/memory.sqlite3 \
  LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/literature_maps/literature_maps.sqlite3 \
  RESEARCH_DB_PATH=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/research/research.sqlite3 \
  AGENT_TASKS_DB=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/agent_tasks/agent_tasks.sqlite3 \
  PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/paper-search/state.sqlite3 \
  ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/articles \
  PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-task09-backend-rerun-HFWvNV/data/browser-profile \
  LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest -q tests/literature_maps \
  -o cache_dir=/private/tmp/spec043-task09-backend-rerun-HFWvNV/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-backend-rerun-HFWvNV/pytest-tmp
```

实际输出：

```text
........................................................................ [ 45%]
........................................................................ [ 90%]
................                                                         [100%]
160 passed in 4.94s
```

### 作者列出的 runtime 精确集合命令

```text
env PYTHON_DOTENV_DISABLED=1 COMPACTION_SUMMARY_MODE=rule \
  KB_DIR=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/kb \
  QDRANT_PATH=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/kb/qdrant \
  KB_META_PATH=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/kb/papers.json \
  MEMORY_DB_PATH=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/memory/memory.sqlite3 \
  LITERATURE_MAP_DB_PATH=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/literature_maps/literature_maps.sqlite3 \
  RESEARCH_DB_PATH=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/research/research.sqlite3 \
  AGENT_TASKS_DB=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/agent_tasks/agent_tasks.sqlite3 \
  PAPER_DISCOVERY_DB_PATH=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/paper-search/state.sqlite3 \
  ARTICLE_DOWNLOAD_DIR=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/articles \
  PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec043-task09-backend-runtime-rYygD5/data/browser-profile \
  LANGFUSE_ENABLED=false \
  .venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_groups.py \
  tests/literature_maps/test_map_export.py \
  tests/literature_maps/test_map_import_bridge.py \
  tests/literature_maps/test_map_api.py \
  -o cache_dir=/private/tmp/spec043-task09-backend-runtime-rYygD5/pytest-cache \
  --basetemp=/private/tmp/spec043-task09-backend-runtime-rYygD5/pytest-tmp
```

实际输出：

```text
.............................................                            [100%]
45 passed in 1.01s
```

### Review 五项 P1 与 schema P2 的行为覆盖核对

新增测试不是只断言字段，而是先驱动对应的持久状态/执行器/迁移行为，再核对结果：

- P1-1 配置指纹：`test_automatic_enqueue_reconciles_after_model_configuration_changes` 两次自动 enqueue，实际 patch 服务端模型配置，验证产生 version 1/2、不同 model ID，旧版本仍可读。
- P1-2 due retry：`test_due_transient_failure_is_requeued_automatically_and_pauses_are_respected` 先让 runner 真实失败，持久化过去的 deadline，验证 paused 不调用；恢复 active 后再次调用完成，并验证 attempts=3 到期不再调用。`test_persisted_retry_deadline_wakes_existing_queue_executor` 另以真实线程池、事件和零退避验证自动唤醒产生第二次调用。
- P1-3 provider 分类：`test_provider_auth_failure_is_classified_and_pauses_the_queue_atomically` 驱动 401 provider 异常并执行队列，验证持久 `paused`/安全 auth code；`test_provider_rate_limit_is_retryable_without_pausing_the_queue` 驱动 429，验证 `partial`、未暂停、稳定 rate-limit code 和 retryable 标志。
- P1-4 槽位公平性：`test_queue_children_release_shared_slots_for_other_map_work` 用两个地图的阻塞 runner 占用摘要队列，在不释放模型阻塞的情况下提交 graph task，并要求 graph future 先完成，直接验证共享槽位不被 drain 饿死。
- P1-5 lease/reaper：`test_analysis_queue_recovery_only_requeues_expired_leases_and_rejects_late_finish` 先验证有效 lease 不 recovery，再将 lease 过期后只恢复一次并执行；`test_analysis_finish_fails_closed_after_lease_expiry` 用旧 token 在过期 lease 后 finish，验证写入被拒绝；paused recovery 测试验证恢复不唤醒暂停队列。
- schema P2：`test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry` 从 schema 5 形态构造旧库，注入迁移故障，逐项检查新增列、索引和 schema marker 均未落库，再清除故障升级到 schema 6 并重复 initialize。

因此本轮确实执行了 review 五项 P1 与 schema P2 的行为复现测试；通过仍只属于隔离测试证据，不替代真实 provider/API、部署或最终 Spec 验收。

### 本轮限制与交接

- 未启动服务、未执行真实 API smoke、未调用模型/外网、未触碰生产 SQLite/KB/Qdrant、未运行全量 `tests`，也未使用旧实体 ID 冒充新候选通过。
- 保留首轮 `151 passed` 记录及其局限：首轮未覆盖 review 列明路径，不能作为这些路径正确的证据；本轮 `160 + 45` 通过才是修复候选的新增定向证据。
- 知识库导入失败 bug 仍不混入本阶段修复或验证。
