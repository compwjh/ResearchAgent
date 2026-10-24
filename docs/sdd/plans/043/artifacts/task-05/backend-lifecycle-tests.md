# Task05 backend-tester 生命周期测试交接

> 角色：backend-tester ｜ 日期：2026-10-20 ｜ 范围：Task05 持久 job、分析版本与会话 reservation 生命周期

## 测试产物

- 新增 `tests/literature_maps/test_map_analysis_lifecycle.py`。
- 未修改 `backend/**`，未修改既有测试文件。
- 测试仅使用每个用例的临时 SQLite；模型接缝返回现有真实 `ChatRun` 类型，未调用生产 provider、生产数据库或部署服务。

## 覆盖边界

1. `test_stopped_analysis_rejects_late_chat_run_completion`
   - 让分析模型运行暂停，在另一个 SQLite 写事务中停止持久 job，再释放模型回调。
   - 断言迟到结果不能写成 `completed`，分析保持受控停止失败，job 保持 `stopped`。
2. `test_analysis_retry_reuses_version_and_idempotency_after_failure`
   - 首次返回空 `ChatRun` 形成可重试失败，随后 retry/resume。
   - 断言同一幂等键复用同一 analysis/job/version，恢复后结果完成；显式新幂等键才创建 version 2。
3. `test_concurrent_conversation_reservation_across_sqlite_connections_uses_one_id`
   - 使用两个独立 `LiteratureMapStore` 与两个独立 `MemoryRepository` 连接，在两个线程同时执行同一 reservation。
   - 断言两次返回同一个 conversation ID，只有一个 binding 行和一个 conversation 行。
4. `test_map_deletion_keeps_confirmed_binding_snapshot_and_cleans_analysis_rows`
   - 先持久化 pending analysis 与已确认摘要会话，再删除地图。
   - 通过独立 SQL 查询断言 analysis 行清理、binding 行保留，并通过绑定快照恢复标题/摘要上下文。
5. `test_analysis_recovery_after_service_rebuild_runs_once_without_graph_mutation`
   - 在旧 Store 中将 analysis job 持久化为 `running`，再用新的 Store/Service 实例恢复。
   - 图谱服务恢复分流不提交 analysis；新的 analysis service 通过受控 executor 仅执行一次，第二次 recover 不重放。
   - 断言 analysis ID/version、幂等 job 保持不变，且地图、节点、边图谱状态未被分析恢复改写。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python scripts/check_test_naming.py` | 0 | 命名门禁通过，无 `spec/task` 数字文件名 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_lifecycle.py` | 0 | **5 passed** |
| `.venv/bin/python -m pytest --collect-only -q tests/literature_maps/test_map_analysis_lifecycle.py` | 0 | **5 tests collected**，无收集错误 |

本交接不声称真实 API/model E2E；本轮按 Task05 backend-tester 范围只验证临时 SQLite 持久化与既有 `ChatRun` 结果接缝。真实 provider/API smoke 仍需由验收阶段执行并落盘请求、响应、实体 ID 与产物路径。
