# Spec034 Task09 后端最终复审

评审角色：backend-reviewer（只读代码评审）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：`backend/**`、Task09 后端合同测试、Task09 计划/交付报告及上一版 `backend-review.md`；未修改业务代码，未执行 commit/push/全量回归。

## 最终结论

**NO-GO。** 上一版 P1-1～P1-4 已修复并通过定向验证；P1-5 的跨库不变性校验仍未满足 Task09 的“任一校验失败即中止、不做部分删除”要求：当 sessions/catalog/kb 的前后快照不一致时，当前实现仅记录 `cross_store.unchanged=false`，仍将目标 Task 删除并返回 `status=completed`。在修复并补充失败回滚测试前，不得将 Task09 后端标记为 GO 或推进 Spec034 收口。

P0：0。  
P1：1（P1-5 残留）。  
P2：4（沿用上一版，非本轮阻断）。

## P1-1～P1-4 修复复核

### P1-1：项目继承与批准物化——已修复

- 创建已有会话时，显式 `project_id` 与会话项目不一致返回 `PROJECT_MISMATCH`，不再静默忽略；未显式传项目时继承会话项目：`backend/app/api/routes_research.py:536-544`。
- 批准计划物化 Task 时重新读取 owner-scoped conversation，并把 `conversation.project_id` 写入 `ResearchTask.project_id`，缺失会话 fail-closed：`backend/app/research/application/approval_service.py:281-289`。
- 行为探针验证：项目绑定会话批准后，Task 的 `project_id` 与会话项目一致，退出码 0；Task09 合同中的显式 mismatch 也返回 409 且不创建 Session。

### P1-2：Session 创建竞争/重试副作用——已修复

- 创建路径使用进程内串行接缝、稳定 request fingerprint/idempotency key，并在消息写入前使用 `create_idempotent_message_pair()`；user/assistant 两行由唯一活动幂等键保护：`backend/app/api/routes_research.py:506-604`、`backend/app/memory/repository.py:1706-1752`。
- `get_active_session()` 直接按 owner/conversation 查询，不依赖受限列表页：`backend/app/research/infrastructure/research_store.py:1751-1761`。
- `test_session_create_is_idempotent_under_concurrent_retries` 验证 4 个并发请求只得到 1 个 Session、1 条 user 消息和 1 条 assistant 消息；退出码 0。

### P1-3：Session 列表 cursor 分页——已修复

- `GET /api/research-sessions` 接受 `project_id/status/cursor/limit` 并返回 `next_cursor`；ResearchStore 使用 `(created_at,research_session_id)` keyset cursor：`backend/app/api/routes_research.py:759-796`、`backend/app/research/infrastructure/research_store.py:1875-1920`。
- 项目过滤路径扫描 raw page，并将 next cursor 锚定到最后一条可见 Session，避免过滤导致跨页重复/跳过；Task09 两个 cursor 合同测试通过。

### P1-4：cleanup 必须先 dry-run——已修复

- execute 强制要求 `confirm=True` 与同 owner 的 planned dry-run audit ID，锁内重新读取目标并校验目标 ID/children 快照：`backend/app/research/infrastructure/research_store.py:1233-1277`。
- 临时库执行 CLI `--execute --confirm` 且不提供 dry-run ID 时，内部退出码为 1，抛出 `LEGACY_CLEANUP_DRY_RUN_REQUIRED`；Task09 合同也覆盖缺失 dry-run 的直接 store 调用。

## 仍然阻断：P1-5 跨库不变性失败未回滚

Task09 要求清理前后 sessions/catalog/KB 的计数或内容摘要不变，且任一校验失败都不得部分删除。当前实现确实持久化 `before/after` 和 `unchanged` 字段，也会在 provider 缺失时标记 `unverified`；但不一致时只计算布尔值，没有抛出错误：

- `cross_before`、删除、`cross_after` 与 `cross_unchanged` 在 `backend/app/research/infrastructure/research_store.py:1278-1324` 完成。
- `cross_unchanged` 为 `False` 时仍组装 `status="completed"` 报告、插入 execute 审计并提交事务；没有 `LegacyCleanupError`，也没有 rollback。
- 最小行为探针：`external_snapshot` 返回 execute 前后不同 sessions 计数时，实际结果为 `completed False None`（`status=completed`、`unchanged=False`、目标 Task 已不存在），证明删除已提交。

建议：当 provider 返回完整且 `cross_before != cross_after` 时抛出稳定错误码（例如 `LEGACY_CLEANUP_CROSS_STORE_CHANGED`），在删除事务内回滚；失败审计应在事务外记录 `aborted`。补充测试应断言：Task/children 保留、execute 审计为 aborted、报告不暴露 completed。

## 非阻断 P2（沿用上一版）

- Intake 的 `SKILL_DISABLED`/`CAPABILITY_NOT_AUTHORIZED` 在创建 API 中仍统一映射 503，而 Spec 错误矩阵期望 403。
- Legacy adapter 仍只把 `goal` 映射为 Intake `topic`，旧 `quality_profile`、`target_paper_count`、`language`、`review_plan_first` 未映射或未在兼容文档中明确忽略。
- `_intake_coordinator()` 保留 API 层 fallback 装配 registry/provider 的测试便利路径，生产装配边界仍可进一步收紧。
- dry-run 会持久化 audit row；CLI/运维文档应明确其是“无业务删除的审计写入”，而非完全无写入。

## 验证记录

| 检查 | 退出码/结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py` | **0**；12 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task09_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py` | **0**；176 passed |
| `.venv/bin/python -m py_compile`（Task09 后端改动文件及测试） | **0**；通过 |
| `.venv/bin/ruff check`（Task09 改动文件，排除 memory/repository.py 的既有 lint） | **0**；All checks passed |
| `.venv/bin/ruff check backend/app/memory/repository.py` 与 HEAD 基线比较 | 当前/基线均 15 个既有告警；未新增本轮幂等消息代码告警 |
| `git diff --check --`（Task09 后端文件/测试） | **0**；通过 |
| 项目物化行为探针 | **0**；批准后 Task.project_id 与会话项目一致 |
| cleanup 无 dry-run ID 探针 | 内部退出码 **1**；`LEGACY_CLEANUP_DRY_RUN_REQUIRED` |
| cleanup 跨库快照变化探针 | **违规复现**；返回 `completed/unchanged=false` 且 Task 已删除，支持 P1-5 |

## 交接

进展日志：`.codebuddy/agent-logs/spec-034/task-09/backend-reviewer/20260915-100000.md`。  
评审报告：`docs/sdd/plans/034/artifacts/task-09/backend-review-final.md`。
