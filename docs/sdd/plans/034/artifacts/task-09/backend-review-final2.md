# Spec034 Task09 后端最终复审（二次）

评审角色：backend-reviewer（Luna high）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：`backend/**` 中 Task09 相关改动、`tests/test_spec034_task09_backend.py`、Task09 后端交付/上一版复审报告；未修改业务代码，未 commit/push。

## 最终结论

**GO。** P1-1～P1-5 均已在当前工作树关闭，并有实现证据、Task09 合同测试和定向回归支持。上一版阻断项 P1-5 已改为跨库 fail-closed：sessions/catalog/kb 快照不一致或未验证时，清理事务回滚、目标 Task/children 保留，并在事务外写入 `status=aborted` 审计；成功路径才提交 completed 审计。

P0：0。  
P1：0。  
P2：沿用上一版的非阻断观察（错误码映射、legacy 可选字段兼容说明、dry-run 审计写入文档化），不阻断 Task09 后端放行。

## P1 关闭复核

### P1-1：项目继承与批准物化——已关闭

- 创建/复用 Session 时校验显式项目属于 owner，并拒绝显式项目与 conversation 项目不一致（`PROJECT_MISMATCH`）：`backend/app/api/routes_research.py:539-544`。
- Session→Task 批准物化重新读取 owner-scoped conversation；Task 的 `project_id` 使用会话项目，缺失会话 fail-closed：`backend/app/research/application/approval_service.py:281-289`。
- `test_project_is_materialized_and_explicit_mismatch_fails_closed` 通过，确认 mismatch 不创建 Session；Task09 合同共 14/14 通过。

### P1-2：Session 创建竞争/重试副作用——已关闭

- 创建入口以稳定 fingerprint、trigger/idempotency key 和进程内串行接缝处理重放；既有 response 可直接 replay，fingerprint 不同则返回稳定冲突：`backend/app/api/routes_research.py:506-529,601-604`。
- 首条 user/assistant 消息通过事务内 `create_idempotent_message_pair()` 及派生 activity 幂等键创建，竞争重试不产生重复消息：`backend/app/api/routes_research.py:557-564`、`backend/app/memory/repository.py:1706-1752`。
- `test_session_create_is_idempotent_under_concurrent_retries` 通过，确认 4 个并发请求仅 1 个 Session、1 条 user 消息和 1 条 assistant 消息。

### P1-3：Session 列表 cursor 分页——已关闭

- 列表接口支持 owner scope、`project_id/status/cursor/limit`，项目过滤时扫描 raw keyset page，并将下一页锚定到最后一条可见 Session，避免过滤造成重复/跳过：`backend/app/api/routes_research.py:759-796`。
- `test_session_list_returns_status_aware_keyset_cursor` 与 `test_session_list_project_filter_cursor_anchors_to_last_visible_row` 均通过。

### P1-4：cleanup 必须先 dry-run——已关闭

- dry-run 输出目标 Task/children、计数、保护计数与验证错误，并持久化带 owner 的 planned audit；只写审计，不改 Task/children：`backend/app/research/infrastructure/research_store.py:1205-1231`。
- execute 强制 `confirm=True` 和同 owner、未过期、planned 状态的 dry-run ID；锁内重新读取并比较目标快照，目标变化/无目标/活跃任务均拒绝：`backend/app/research/infrastructure/research_store.py:1233-1286`。
- `test_execute_requires_matching_dry_run_and_cross_store_audit` 通过；缺少 dry-run ID 返回 `LEGACY_CLEANUP_DRY_RUN_REQUIRED`。

### P1-5：跨库不变性与失败回滚——已关闭

- 清理前后读取 sessions/catalog/kb 快照；缺失 provider/字段或 unverified 返回 `LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED`，前后值变化返回 `LEGACY_CLEANUP_CROSS_STORE_CHANGED`：`backend/app/research/infrastructure/research_store.py:1180-1203,1287-1297,1331-1348`。
- 变化/未验证均发生在同一删除事务内，异常路径 rollback 后再以新连接写入 `execute/status=aborted` 审计，记录 research before/after、cross-store before/after、失败码及 attempted/deleted 数量：`backend/app/research/infrastructure/research_store.py:1368-1413`。
- 成功路径仅在三库快照相等且所有子表删除计数匹配时提交 completed 审计：`backend/app/research/infrastructure/research_store.py:1318-1367`。
- `test_execute_rolls_back_when_cross_store_changes_and_audits_before_after` 与 `test_execute_rolls_back_when_cross_store_is_unverified_and_audits_state` 通过，确认目标 Task/children 保留且审计为 aborted。

## 统一入口与安全边界

- 旧 `POST /research-tasks` 仅构造统一 Session/Intake 请求，不调用 `ResearchService.create_task` 或启动 Orchestrator：`backend/app/api/routes_research.py:835-861`；`test_old_post_is_an_intake_adapter_and_does_not_create_task` 通过。
- legacy 判定要求空 conversation 且无 Session 绑定；已绑定 Task、其他 owner Task、活跃无绑定 Task 均受保护。删除顺序和计数校验覆盖子表，未发现动态 SQL 表名来自用户输入（表名来自固定元组）。

## 验证记录

| 检查 | 退出码/结果 |
|---|---:|
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py` | 0；14 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py` | 0；178 passed |
| `.venv/bin/python -m py_compile`（Task09 后端文件及测试） | 0；通过 |
| `.venv/bin/ruff check`（Task09 后端文件，排除 memory/repository.py 基线告警） | 0；All checks passed |
| `.venv/bin/ruff check backend/app/memory/repository.py` | 1；15 条告警，与 HEAD 基线同数；新增 `create_idempotent_message_pair()` 未新增告警 |
| `git diff --check` | 0；通过 |

## 交接

进展日志：`.codebuddy/agent-logs/spec-034/task-09/backend-reviewer/20260915-160500.md`。

本报告仅记录复审结论；未修改业务代码，未执行 commit/push。
