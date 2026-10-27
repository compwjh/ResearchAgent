# Spec043 Task11 后端基础阶段评审

- 评审者：backend-reviewer
- 模型：临时 Luna xhigh
- 分派方式：主会话多 Agent 分派
- 日期：2026-10-28
- 范围：Task11 第一阶段 backend/** 变更；对照已确认接口合同 §1、§5 与 Task11 计划。未将后续分页、批量确认或 metadata handler 尚未实现作为本阶段缺陷。

## 发现

### [HIGH / P1] 暂停队列会绕过租约耗尽终态并留下无法领取的 queued 批次

文件：`backend/app/literature_maps/infrastructure/store.py:3035-3043`，恢复后重入位置 `3084-3091`；claim 次数门槛 `2500-2510`。

问题：当 `expand_batch` 的第四次 claim（首次领取加三次接管）过期时，如果地图分析队列正处于 paused，恢复器先选择 `paused`，不会记录 `MAP_JOB_LEASE_EXHAUSTED`。队列恢复后作业被改回 `queued` 并返回给 typed dispatcher；但 `claim_auxiliary_job` 的 `attempts < 4` 条件拒绝再次领取。后续恢复继续返回同一个 queued 作业，因此它既不能运行，也不会进入约定的耗尽失败终态。

复现：使用临时 SQLite 库，将带 `metadata_pending` 的 expand_batch 领取并过期四次；在第四个 lease 过期前暂停 analysis queue。`recover_auxiliary_jobs` 将作业置为 `paused`；调用 `resume_analysis_queue` 后恢复结果为 `queued`；下一次 claim 返回 `None`，再次 recovery 仍返回该 `queued` 作业。未修改仓库测试文件或真实数据库。

修复建议：在过期恢复时先判断 claim 次数是否耗尽，再应用队列暂停状态；或者在 paused→queued 时对达到上限的作业直接写入 `MAP_JOB_LEASE_EXHAUSTED` 失败终态。暂停不能使第四次过期的作业跳过冻结的接管上限。

## 已核对项

- v7→v8 仅给旧 preview 追加列，默认值和已有节点/候选保留；迁移 DDL 与 schema marker 在同一显式事务内，故障回滚覆盖到新增列。
- claim 使用 queued 条件更新及事务， owner/map/operation/status 与 stopped-map 条件均受限；并发 claim 只有单一胜者，token 不进入 `MapJob.to_dict()`。
- finish 与 domain transaction 检查 owner/map/operation、running、token 和 lease；过期 token 不能提交，租约在 domain transaction 中失效会回滚整个事务。
- typed recovery 将 `preview_page` / `expand_batch` 路由到专用 handler，未知 operation 失败关闭；普通 create / preview 与分析队列的恢复路径仍有类型隔离。
- map-local resume 只恢复目标地图的辅助作业；正常暂停/恢复路径测试通过。发现项限定于 claim 上限与暂停同时发生的边界。

## 定向验证

执行命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_schema_migrations.py::test_schema_upgrade_adds_pagination_defaults_and_preserves_existing_rows \
  tests/literature_maps/test_map_schema_migrations.py::test_schema_upgrade_failure_rolls_back_v8_columns_and_keeps_legacy_preview \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_auxiliary_claim_is_single_owner_scoped_cas_with_private_token_and_lease \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_expired_auxiliary_token_cannot_write_or_finish_after_recovery \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_auxiliary_domain_write_rolls_back_when_lease_expires_before_finish \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_auxiliary_recovery_allows_three_takeovers_then_fails_closed \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_recovery_routes_auxiliary_operations_to_typed_handlers_and_fails_unknown \
  tests/literature_maps/test_map_auxiliary_jobs.py::test_existing_analysis_queue_resume_releases_paused_batch_to_typed_recovery
```

结果：8 passed。另以临时 SQLite 数据库执行上述暂停边界复现，确认失败路径。未运行全量测试、未调用外网或模型、未启动服务。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | fail |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: WARNING — 修复 1 个 HIGH 问题后复审。未覆盖后续 handler/API 阶段。

## 窄复审最终结论（2026-10-28）

原 HIGH/P1 已修复。`recover_auxiliary_jobs` 在过期 running 作业上先判断 `attempts >= _AUXILIARY_MAX_CLAIMS` 并终结为 `MAP_JOB_LEASE_EXHAUSTED`，仅未耗尽作业才按分析队列暂停状态转为 `paused`。因此第四次 lease 在暂停期间过期不会再变成恢复后无法领取的 queued 作业。

未耗尽语义也已验证：attempts 未达上限的 running 批次在暂停期间过期后保持 `paused`；恢复队列后回到 `queued`，且可以再次 claim。耗尽后 resume 仍保持 `failed`，不会重新进入 recovery。

窄验证：

- `test_paused_queue_does_not_suppress_auxiliary_lease_exhaustion`、`test_auxiliary_recovery_allows_three_takeovers_then_fails_closed`、`test_existing_analysis_queue_resume_releases_paused_batch_to_typed_recovery`：3 passed。
- 临时 SQLite 边界验证：未耗尽的过期批次先暂停、恢复后可领取，PASS。

最终结论：**PASS（限本次暂停与 lease 上限修复）**。未重评整个阶段、未运行全量测试。
