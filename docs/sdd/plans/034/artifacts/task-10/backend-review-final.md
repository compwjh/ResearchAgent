# Spec034 Task10 后端最终复审（二次）

评审角色：backend-reviewer（Luna high）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：Task10 三项后端修复：`approve_plan` 启动唯一 ResearchService runtime、旧幂等 key 在 stale 校验前重放、cleanup CLI 注入只读跨库 snapshot provider 并在 provider 不可用时 fail-closed。只读检查 `backend/**`、`backend/scripts/cleanup_legacy_research_tasks.py`、Task10 后端测试与交接物；未修改业务代码，未 commit/push。

## 最终结论

**GO。** 上一版后端复审提出的三个 P1 均已关闭，且有实现路径、定向合同测试和静态校验证据支持。当前未发现会阻断 Task10 后端收口的 P0/P1。

P0：0。  
P1：0。  
P2：沿用上一版报告中的统一错误体字段与 trigger message role 校验观察；本次范围未修改，也不阻断本轮三项修复放行。

## 三项修复复核

### P1-01：`approve_plan` 启动唯一 runtime——已关闭

- `routes_research._approval_service()` 通过 `get_provider("research_service")` 注入 `PlanApprovalService`，没有在命令边界构造第二套 `ResearchService`/`Orchestrator`：`backend/app/api/routes_research.py:167-188`。
- 生产组合根仅在 `backend/app/research/application/entry.py:170-186` 构造 `ResearchService`；`build_research_service()` 使用 `@lru_cache(maxsize=1)`，API provider 默认 singleton，故审批路径复用既有 `ResearchAgentRunner`、executor 和惰性 `Orchestrator`。
- `PlanApprovalService._resume_activity()` 先完成 activity outbox 与 Session→Task/activity 链接，再调用同一注入 runtime 的 `start(task.research_task_id, owner_id)`：`backend/app/research/application/approval_service.py:251-301`。ResearchService 自身的 `_INFLIGHT` guard 防止同一 Task 重复提交后台运行。
- `test_approve_plan_dispatches_materialized_task_to_existing_research_service` 通过，证明批准后的 materialized Task 会经注入的既有 service 启动，且只产生批准事件，不留在“仅排队不执行”的旧路径：`tests/test_spec034_task10_backend.py:29-47`。

该复核确认的是批准到 runtime 的后端接缝；真实 Ollama/USENIX 浏览器 Smoke 仍属于 Task10 主流程后续验收，不在本次只读复审中声称已完成。

### P1-02：旧幂等 key 重放优先于 stale——已关闭

- `command()` 先按 `owner_id + idempotency_key` 读取 durable command result，并在 Session/command/原 `subject_version` 身份一致时直接返回保存的 `response_json`；当前计划版本校验位于其后：`backend/app/research/application/approval_service.py:146-170`。
- 同一旧 key 在计划版本变化后可返回原响应；未命中的新 key 仍严格执行 `PLAN_VERSION_STALE`，没有放宽新命令的版本门禁。
- `test_old_command_key_replays_durable_response_before_plan_version_stale` 通过，覆盖 v1 命令、生成 v2、同 key 重放和新 key stale 对照：`tests/test_spec034_task10_backend.py:50-84`。

### P1-03：cleanup CLI provider 注入与 fail-closed——已关闭

- CLI 在 dry-run 与 execute 两条路径都创建并传入同一个 `build_cross_store_snapshot_provider(owner_id=...)`：`backend/scripts/cleanup_legacy_research_tasks.py:31-45`。
- provider 对既有 memory/catalog/KB 文件执行只读测量；不存在、损坏、缺表或非法 manifest 均返回 `status=unverified`，不创建缺失数据库或猜测为零：`backend/app/research/application/cleanup_snapshot.py:23-28,47-65,68-120`。
- `ResearchStore._cross_store_snapshot()` 对缺失字段或 `unverified` 保持未验证状态；execute 在任何删除前拒绝并回滚，只有 before/after 三项均已测量且不变才提交：`backend/app/research/infrastructure/research_store.py:1180-1203,1287-1349`。
- `test_cleanup_snapshot_provider_supports_verified_dry_run_and_execute`、`test_cleanup_snapshot_provider_is_unverified_when_external_store_is_unavailable` 和 `test_cleanup_cli_wires_provider_for_real_dry_run_then_execute` 全部通过，覆盖成功删除、不可用 provider 和真实 CLI dry-run→execute：`tests/test_spec034_task10_backend.py:87-177`。

## 验证记录

| 检查 | 退出码/结果 |
|---|---:|
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec034_task09_backend.py tests/test_spec034_task10_backend.py` | 0；105 passed in 2.80s |
| `find backend -name '*.py' -print0 \| xargs -0 .venv/bin/python -m py_compile` | 0；通过 |
| `.venv/bin/ruff check backend/app/api/routes_research.py backend/app/research/application/approval_service.py backend/app/research/application/cleanup_snapshot.py backend/scripts/cleanup_legacy_research_tasks.py tests/test_spec034_task10_backend.py --select E9,F63,F7,F82,I001` | 0；All checks passed |
| `git diff --check -- backend tests` | 0；通过 |

## 交接

本报告仅记录 Task10 后端三项修复的最终复审结论；未执行 commit/push。真实服务启动、Ollama/USENIX Smoke、最终全量回归和 Spec034 状态收口仍由主 Agent 按 Task10 计划执行。
