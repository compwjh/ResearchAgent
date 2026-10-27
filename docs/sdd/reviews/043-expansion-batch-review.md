# Spec043 Task11 后端第三阶段 A 评审：重核与原子批次

- 评审者：backend-reviewer
- 模型：临时 Luna xhigh
- 日期：2026-10-28
- 基线：分页阶段提交 `f9f14397`
- 范围：仅评审当前 backend diff 与后端测试，覆盖 revalidate、batch-apply、事务内 analysis queue 增量登记和 `expand_batch` outbox。对照接口合同 §2/§3 与 `2026-10-28-expansion-batch-readiness.md`。未评前端并行改动；metadata worker、批次重试/恢复和 analysis-wait 完成态投影按本阶段边界未作为缺陷。

## 发现

### [HIGH / P1] 批次创建的摘要分析项未提交给现有队列调度器

文件：`backend/app/literature_maps/application/service.py:1370-1379`。

`batch_apply_previews()` 在 store 事务中正确创建新节点、analysis child 与 queue item，但提交后直接返回结果，没有触发现有 `MapAnalysisService` 调度器。运行时把 `analysis_service` 和独立 `queue_executor` 接在 `LiteratureMapService` 上；现有的 `ensure_analysis_queue()` 才会在持久化后调用 `_schedule_analysis_queue()`（`analysis.py:579-586`）。应用启动恢复只运行一次（`runtime.py:242-247`），因此批次新增的、已有摘要的节点会有 `queued=1` 的持久队列项，但正常批次请求不会让 executor 认领它；除非随后显式 ensure/resume 或进程重启，分析就停留在队列中，批次对应的 `analysis_wait` 也不会前进。

复现：临时 SQLite 创建一个带摘要候选，给 `LiteratureMapService` 挂接使用记录型 executor 的 `MapAnalysisService`，执行 batch-apply。返回时 analysis queue 有一个 queued child，但 executor `submit` 次数为 0。该问题只涉及已有摘要节点和现有分析 worker 的调度，不涉及本阶段明确留待后续的 metadata worker。

建议：在 batch 事务提交后，沿用现有 analysis queue scheduler 对已返回的 queue job 做一次增量调度；不要在事务内调用 `ensure_analysis_queue()` 或扫描全图。若队列暂停，沿用现有 paused 检查，不派发。

## 已核对项

- owner/map 在事务内确认；操作范围幂等结果在 map revision、preview revision 与选择校验前回放；异参同键冲突。
- 两个 preview 必须属于同一活动 seed、方向不同且为 references/citations；候选 ID 归属和每个 preview revision 均在事务内复核。batch apply 还要求 preview base revision 与当前 map revision 匹配。
- 稳定身份由候选 external IDs 重新验证。跨方向同身份只插入一个节点，并分别写入 seed→candidate 与 candidate→seed 的 citation edge；活动节点与墓碑均纳入验证，墓碑不会被隐式恢复。自环/无效候选失败，不静默跳过。
- raw 每方向 20/21、跨方向 unique 20/21 与活动节点 199/200 边界均有定向测试；map revision 仅在新增节点或边时递增一次。
- revalidate 只更新快照候选状态和 preview base/revision，不改节点、边；无效选择通过 `invalid_selections` 明示，不会随着 batch apply 静默丢弃。
- queue helper 在当前事务连接中增量合并旧 items，并保留 paused 状态；同一跨方向身份只生成一个新节点和一份 analysis queue item。`expand_batch` 初始 counts/outbox、preview 加入标志、节点/边、幂等结果与事件都位于同一个 store 事务中。
- 将异常注入在最后的 `expansion_batch_queued` 事件写入处，验证事务回滚 map revision、节点、边、preview revision、analysis child/queue、outbox 与幂等记录。
- `run_expansion_batch()` 的 fail-closed 占位及缺摘要 metadata 执行属于后续 3B，本次没有据此报缺陷。

## 定向验证

命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_expansion_batch.py \
  tests/literature_maps/test_map_analysis_queue.py::test_analysis_queue_is_serial_and_pause_resume_controls_following_items \
  tests/literature_maps/test_map_analysis_queue.py::test_expired_child_recovery_keeps_a_paused_queue_as_paused \
  tests/literature_maps/test_map_analysis_queue.py::test_analysis_queue_ensure_is_idempotent_and_skips_missing_abstract
```

结果：退出码 0，20 passed。另以临时 SQLite 和记录型 executor 复现了上述未调度问题；并在最后 outbox event 注入失败，确认所有写入回滚。未运行全量测试、未访问外网或模型、未启动/部署服务。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | fail |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **WARNING — 修复 1 个 HIGH 问题后复审。** 后续 3B handler / metadata worker 不在本阶段评审范围内。

## 窄复审最终结论：提交后队列调度

复核范围仅限原 P1 及其公共 runtime 接线：store 事务提交后是否调度已摘要 child、幂等重放是否额外创建 child/重复提交 executor、暂停队列和事务失败是否阻断派发。

- `batch_apply_previews()` 现在只在 store 事务成功返回后读取持久化 outbox；仅当 outbox 包含 `analysis_queued` 且有 `analysis_id`，并且返回 queue id 与现有 queue projection 一致时，才调用既有 `_schedule_analysis_queue()`（`backend/app/literature_maps/application/service.py:1370-1395`）。未调用全图 `ensure_analysis_queue()`。
- 公共 runtime 将同一 `LiteratureMapStore`、`MapAnalysisService` 和专用 `queue_executor` 接入服务（`backend/app/literature_maps/application/runtime.py:204-219`）。新回归用记录型 executor 验证 executor 提交时 child 已持久化；同键重放返回原结果、analysis row 仍只有一份，dispatch lock 阻止第二次 executor 提交。暂停队列没有提交，事务最终事件失败也没有提交。
- 同键重放仍会再次尝试调度，以便恢复事务成功但先前派发失败的情况；调度器的 map dispatch lock 合并重叠调用，已完成或暂停队列不派发。

定向复核命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/literature_maps/test_map_expansion_batch.py::test_batch_apply_dispatches_new_abstract_queue_after_commit_and_replay_is_safe \
  tests/literature_maps/test_map_expansion_batch.py::test_batch_apply_does_not_dispatch_into_a_paused_analysis_queue \
  tests/literature_maps/test_map_expansion_batch.py::test_batch_transaction_rolls_back_nodes_edges_jobs_and_queue_on_late_failure \
  tests/literature_maps/test_map_analysis_queue.py::test_runtime_explicit_analysis_uses_general_slot_while_queue_child_runs
```

结果：退出码 0，4 passed。未运行全量测试、未访问外网或模型、未部署。

最终结论：原 P1 已关闭，第三阶段 A 后端评审更新为 **PASS**。本窄复审未重新评估其余代码或后续 3B metadata worker/批次恢复范围。
