# Spec043 Task11 后端基础阶段交接

日期：2026-10-28  
阶段：v8 持久化与 auxiliary worker 生命周期基础  
范围：仅完成 Task11 第一阶段，不开放新公共 API。

## 实现结果

- 地图 schema 从 v7 增量到 v8。`literature_map_previews` 新增 `preview_revision INTEGER NOT NULL DEFAULT 1` 和可空 `pagination_json`；旧 preview、候选快照、地图节点和布局均保留。迁移列变更及版本 marker 在现有初始化写事务中提交；中途失败会整体回滚。
- 在既有 `literature_map_jobs` 上增加 `preview_page` / `expand_batch` 专用领取与完成资格：只领取 queued job，以单条条件 `UPDATE ... RETURNING` 写入随机 worker token、UTC 300 秒 lease 和尝试次数；完成、失败和领域写事务都校验 owner/map/operation、running 状态、token 与未过期 lease。token 不进入 `MapJob` JSON。
- 辅助作业恢复会保留有效 running lease，回收过期 lease 并撤销旧 token；允许首次领取后最多三次自动接管，第四个租约过期后以 `MAP_JOB_LEASE_EXHAUSTED` 失败。此阶段没有实现重试命令；后续显式重试须开启新代数。扩展批次遵循既有地图分析队列的暂停状态，resume 走现有分析队列入口并只调度该地图的 typed recovery。
- 恢复路由明确为 `preview_page → run_preview_page`、`expand_batch → run_expansion_batch`。通用 `run_job` 不执行这两种操作；未知 operation 明确以 `MAP_JOB_OPERATION_UNSUPPORTED` 失败。
- 两个新 handler 当前按阶段要求安全失败，错误码为 `MAP_AUXILIARY_HANDLER_UNAVAILABLE`；没有实现来源分页、metadata 补全、批量确认接口或任何新 public API。后续阶段可以在此基础上实现 handler，并用 `auxiliary_job_transaction` + `finish_auxiliary_job_tx` 将领域变更和 finish 放进同一事务。

## 修改文件

- `backend/app/literature_maps/infrastructure/store.py`：schema v8、auxiliary claim/资格/finish/reaper。
- `backend/app/literature_maps/application/service.py`：typed recovery 路由、未实现 handler 的安全终态。
- `backend/app/literature_maps/application/analysis.py`、`backend/app/literature_maps/application/runtime.py`：把既有地图级队列 resume 接到同一地图的 auxiliary recovery；复用现有 executor，没有新建执行器。
- `tests/literature_maps/test_map_schema_migrations.py`、`tests/literature_maps/test_map_auxiliary_jobs.py`：新增 9 个迁移与 worker 生命周期用例。
- `tests/literature_maps/test_map_analysis_queue.py`、`tests/literature_maps/test_map_node_styles.py`：更新 schema v8 的事务回滚和版本断言。

工作区还包含其他并行工作的文档变更；上述文件清单仅列本阶段后端实现相关内容。

## 复用与边界

复用了 `LiteratureMapStore.transaction` / WAL 写锁、既有 jobs 表的 `worker_token`、`lease_expires_at`、`attempts` 列、`_append_event`、现有分析队列暂停标记与 executor。普通 `claim_job` 未被改造成 auxiliary claim，也没有增加第二套 worker 框架。测试数据库全部使用 `tmp_path`；未触碰生产地图数据库，未访问外网，未部署或启动服务。

## 验证记录

1. RED 基线：

   `PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_schema_migrations.py tests/literature_maps/test_map_auxiliary_jobs.py`

   退出码 1；实现前 7 项失败，分别暴露缺少 v8 迁移、claim/reaper 和 typed recovery 的现状。

2. 定向后端测试：

   `PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_schema_migrations.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_node_styles.py tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry tests/literature_maps/test_map_analysis_queue.py::test_analysis_queue_is_serial_and_pause_resume_controls_following_items tests/literature_maps/test_map_analysis_queue.py::test_expired_child_recovery_keeps_a_paused_queue_as_paused`

   退出码 0；33 passed。覆盖 v7→v8 默认值与旧数据保留、迁移失败整段回滚、并发 claim 唯一胜者、旧 token 过期拒写及事务回滚、最多三次接管、typed recovery 无 generic fallback、缺失 handler 安全失败，以及现有分析队列暂停/恢复回归。

3. 编译：

   `PYTHONPYCACHEPREFIX=/tmp/spec043-task11-pycache /Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/literature_maps/application/analysis.py backend/app/literature_maps/application/runtime.py tests/literature_maps/test_map_schema_migrations.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_node_styles.py`

   退出码 0。

4. 测试布局：`/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py`，退出码 0，`test layout: ok`。

5. 测试命名：`/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py`，退出码 0，未发现 Spec/Task 编号命名。

6. 全量收集（未运行全量测试）：

   `set -o pipefail; PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q 2>&1 | tail -n 5`

   退出码 0；3506 tests collected，无 collection error。仅有依赖发出的 `swigvarlink` DeprecationWarning。

7. `git diff --check`：退出码 0。

## 后续缺口

分页抓取与 cursor 推进、批量确认事务、metadata 受限补全、batch 状态投影和用户可见接口仍待后续 Task11 阶段实现。当前两个 typed handler 会安全终止对应工作，不会误把它们交给通用建图 worker。未运行全量测试、真实 API 或部署验证；本阶段没有声称这些能力已可用。

进展日志：`.codebuddy/agent-logs/spec-043/task-11/backend-dev/20261028-010744.md`。

## 独立复审 P1 修复记录（2026-10-28 01:24）

复审指出：第四次 claim 的 lease 在地图分析队列暂停期间过期时，恢复逻辑先转 `paused`，漏掉 `MAP_JOB_LEASE_EXHAUSTED`；resume 又将它转成 `queued`，但 claim 上限仍拒绝领取，形成无法执行的作业。

先新增并运行 `test_paused_queue_does_not_suppress_auxiliary_lease_exhaustion`：精确 pytest 退出码 1，复现最终状态为 `paused`。修复仅调整 `recover_auxiliary_jobs` 的过期分支顺序：先判定达到四次总 claim 上限并转为失败终态，再对未耗尽作业遵循队列暂停状态。自动接管上限未放宽；暂停中未耗尽的作业仍保持 paused。回归同时确认耗尽 job 在 resume 后仍为 failed，且不会重新进入 recovery。

复验命令与结果：

- 原 33 项定向集合加该 P1 回归：退出码 0，`34 passed in 1.79s`。
- `PYTHONPYCACHEPREFIX=/tmp/spec043-task11-pycache /Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_auxiliary_jobs.py`：退出码 0。
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py`：退出码 0，`test layout: ok`。
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py`：退出码 0，无 Spec/Task 数字命名。
- `git diff --check`：退出码 0。

本次只改该恢复顺序并新增回归用例；未新增 API、未部署、未运行全量测试，也未执行 Git 写操作。待原 reviewer 窄复核。
