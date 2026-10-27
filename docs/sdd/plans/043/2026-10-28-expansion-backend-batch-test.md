# Spec043 Task11 第三阶段 A 后端独立测试

日期：2026-10-28  
角色：Backend Tester  
基线：`f9f14397`（分页阶段）  
范围：revalidate、batch-apply，以及同事务 analysis queue 增量登记和 `expand_batch` outbox。测试通过 `tmp_path` 隔离 SQLite，使用 fake/source stubs 和本地 TestClient；未调用真实来源、模型或真实数据库。

## 验收结果

- 定向后端测试：PASS — 89/89 passed，0 failed，0 skipped。
- 全量 pytest、全量 collection、编译、lint、安全扫描、部署版真实 E2E、真实来源网络、外部模型与生产数据库：本次未运行；不作为本报告通过项。本地 TestClient 路由用例已包含在定向集合中。
- 阻塞项：无。

## 执行记录

命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps/test_map_expansion_batch.py tests/literature_maps/test_map_preview_pagination.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_api_errors.py -q
```

退出码：0；结果：89 passed in 3.83s；失败 0；跳过 0。

覆盖包括：双方向同身份合并成单节点并保留两种真实有向边、已有节点/墓碑/owner/map/seed/kind/候选归属校验、幂等回放与异参冲突、失败 preview 中成功候选的显式使用、raw/unique/活动节点容量、节点/边/job/queue 原子回滚、旧 queue item 保留、仅登记新增节点、无摘要 metadata-pending outbox、严格请求体与公共路由 envelope，以及既有分页/扩展/分析队列/auxiliary job/API error 回归。

未运行全量 pytest 或全量 collection；没有修改或运行前端测试。Metadata 来源 worker、lease/token CAS、analysis-wait 对齐与恢复属于后续阶段，本报告不覆盖这些能力。

进展日志：[backend-tester 日志](../../../.codebuddy/agent-logs/spec-043/task-11/backend-tester/20261028-012019.md)。

## P1 提交后调度修复：最终候选窄复验

开发阶段全定向集合记录为 91 passed；本次独立复验只运行两项新增 scheduler 回归和一项必要的 late-failure rollback，用例共 3 项，不重跑原 89 项集合。

| 测试 | GREEN 结果 |
|---|---|
| `test_batch_apply_dispatches_new_abstract_queue_after_commit_and_replay_is_safe` | 通过。修复前 RED 记录为：outbox child 已持久化，但记录型 executor 的 submit 次数为 0。最终候选在事务提交后派发新增摘要队列；同键 replay 不新建 child，也不增加 executor submission；未调用全图 `ensure_analysis_queue()`。 |
| `test_batch_apply_does_not_dispatch_into_a_paused_analysis_queue` | 通过。暂停队列仍为 paused，新增 queue child 保留为 queued，executor 无派发。 |
| `test_batch_transaction_rolls_back_nodes_edges_jobs_and_queue_on_late_failure` | 通过。事务末端事件写入失败后，节点、边、job 与 queue 状态回滚，executor 无派发。 |

执行命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion_batch.py::test_batch_apply_dispatches_new_abstract_queue_after_commit_and_replay_is_safe tests/literature_maps/test_map_expansion_batch.py::test_batch_apply_does_not_dispatch_into_a_paused_analysis_queue tests/literature_maps/test_map_expansion_batch.py::test_batch_transaction_rolls_back_nodes_edges_jobs_and_queue_on_late_failure
```

退出码：0；结果：3 passed in 0.95s；失败 0；跳过 0。此处为最终候选窄复验结果，不代表重跑开发报告中的 91 项集合。
