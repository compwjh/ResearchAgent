# Spec043 Task11 后端基础阶段验收

日期：2026-10-28  
角色：Backend Tester  
范围：Task11 第一阶段影响的 literature_maps 后端迁移、辅助 job lease/recovery 与分析队列关联回归。按要求不运行全量 pytest、不验证前端、不连接真实数据库或外网、不启动/部署服务、不执行 Git 操作。

## VERIFICATION REPORT

- Build / compile：PASS — 本阶段涉及的 8 个 Python 文件均通过 `py_compile`（见命令 2）。未做整包构建。
- Types：未运行 — 本次验收范围未要求类型检查。
- Lint：未运行 — 本次验收范围未要求 lint。
- Tests：PASS — 33/33 passed，0 failed，0 skipped；未采集覆盖率。
- Security：未运行 — 本次定向回归不含安全扫描。
- Diff：初始验收未查看 diff；P1 补充阶段按要求只读使用 diff 定位新增回归测试，未执行 Git 写操作。验收范围依据 Task11 后端交接文件清单与合同 §1/§5。

## 验收点与结果

- v7→v8 preview schema 默认值、旧数据保留、迁移失败整体回滚和重试：通过迁移测试及 schema 回滚用例。
- auxiliary job owner/map/operation 限定、CAS claim、私有 token/lease、迟到 worker 拒写、领域写入和 finish 原子性、自动接管上限及 typed recovery：通过 auxiliary/job recovery 定向测试。
- 既有普通 job store/recovery 行为：通过回归测试。
- schema v8 对现有 node style 和分析队列暂停/恢复的影响：通过 node style schema 回归及三个相关分析队列用例。
- 新公共 API、分页来源请求和真实运行时部署：不属于此阶段验收范围，未验证。

## 执行记录

1. 定向后端测试：

   ```text
   PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_schema_migrations.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_node_styles.py tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry tests/literature_maps/test_map_analysis_queue.py::test_analysis_queue_is_serial_and_pause_resume_controls_following_items tests/literature_maps/test_map_analysis_queue.py::test_expired_child_recovery_keeps_a_paused_queue_as_paused
   ```

   退出码：0；结果：33 passed in 1.74s；失败 0；跳过 0。

2. Python 编译：

   ```text
   PYTHONPYCACHEPREFIX=/tmp/spec043-task11-backend-tester-pycache /Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/literature_maps/application/analysis.py backend/app/literature_maps/application/runtime.py tests/literature_maps/test_map_schema_migrations.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_node_styles.py
   ```

   退出码：0。

3. 测试布局：

   ```text
   /Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
   ```

   退出码：0；输出：`test layout: ok`。

## 阻塞项

无。本报告仅确认上述定向范围；全量回归、真实 API E2E 和部署验证仍需由后续对应收口阶段完成。

进展日志：[backend-tester 日志](../../../.codebuddy/agent-logs/spec-043/task-11/backend-tester/20261028-012019.md)。

## P1 修复后补充：最终候选定向回归

本轮针对最终候选只补跑新增回归和两项既有 paused 恢复用例；不重复此前 33 项回归，不运行 collection。

1. 新增 P1 回归 `test_paused_queue_does_not_suppress_auxiliary_lease_exhaustion`：确认第四次过期 lease 在分析队列暂停时仍先终结为 `MAP_JOB_LEASE_EXHAUSTED`，队列恢复后 job 仍保持失败且不会重新领取。
2. 既有 auxiliary batch 恢复用例 `test_existing_analysis_queue_resume_releases_paused_batch_to_typed_recovery`：通过。
3. 既有分析队列暂停恢复用例 `test_expired_child_recovery_keeps_a_paused_queue_as_paused`：通过。

执行命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_auxiliary_jobs.py::test_paused_queue_does_not_suppress_auxiliary_lease_exhaustion tests/literature_maps/test_map_auxiliary_jobs.py::test_existing_analysis_queue_resume_releases_paused_batch_to_typed_recovery tests/literature_maps/test_map_analysis_queue.py::test_expired_child_recovery_keeps_a_paused_queue_as_paused
```

退出码：0；结果：3 passed in 1.05s；失败 0；跳过 0。此补充结果只覆盖上述最终候选用例。
