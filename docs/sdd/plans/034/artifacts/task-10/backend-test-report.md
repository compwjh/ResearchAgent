# Spec034 Task10 后端验收报告

## 结论

**GO（后端定向验收通过）。** Task10 新增后端合同 5 条、评审固定合同集合 105 条、Task02–09 受影响后端合同 124 条均通过；`py_compile`、聚焦 Ruff 和 `git diff --check` 全部退出码 0。未修改业务代码、未修改测试代码、未执行 commit/push/merge/reset/stash/clean。

Task10 合同覆盖并实际执行了 Fake ResearchService runtime 启动、旧幂等 key 在计划版本变化后的 durable response 重放、跨库 snapshot provider 的 measured/unverified 边界，以及 cleanup CLI dry-run→execute 接线。Task09 合同同时覆盖 unverified/changed 跨库快照时 fail-closed、事务回滚与审计。

## 命令与结果

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| Task10 单独合同 | `.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py` | 0 | **5 passed**，0.39s |
| 评审固定合同集合（Task04–10） | `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec034_task09_backend.py tests/test_spec034_task10_backend.py` | 0 | **105 passed**，2.75s |
| Task02–09 受影响后端合同 | `.venv/bin/python -m pytest -q tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec034_task08_backend.py tests/test_spec034_task09_backend.py` | 0 | **124 passed**，3.45s |
| Python 语法 | `find backend -name '*.py' -print0 \| xargs -0 .venv/bin/python -m py_compile` | 0 | 通过 |
| 聚焦 Ruff | `.venv/bin/ruff check backend/app/api/routes_research.py backend/app/research/application/approval_service.py backend/app/research/application/cleanup_snapshot.py backend/scripts/cleanup_legacy_research_tasks.py tests/test_spec034_task10_backend.py --select E9,F63,F7,F82,I001` | 0 | `All checks passed!` |
| diff 空白检查 | `git diff --check -- backend tests` | 0 | 通过 |

## 验收覆盖摘要

1. **批准 runtime 接缝**：Fake runtime 收到 materialized task 的 `(task_id, owner_id)`，任务进入 `planning` 并写入 approved 事件；证明批准路径复用注入的 ResearchService。
2. **幂等重放**：v1 `revise_plan` 成功后生成 v2；同 owner、同 command、同 subject version、同 key 重放返回原 durable response；新 key 仍返回 `PLAN_VERSION_STALE`。
3. **cleanup provider**：预先存在的 memory/catalog/KB store 可测得 `status=measured`，dry-run 与 execute 使用同一 provider 并完成清理；缺失外部 store 返回 `status=unverified`、各计数为 `None`，不猜测为零且由执行路径 fail-closed。
4. **CLI 接线**：临时隔离 SQLite/JSON 下真实调用 cleanup CLI 的 dry-run→`--execute --confirm --dry-run-id` 完成，跨库快照保持 unchanged。
5. **既有边界回归**：Task09 合同覆盖跨库变化、unverified 快照的删除前拒绝、事务回滚与审计；未见回归。

## 真实 Smoke 状态

- **真实 Ollama/USENIX/浏览器端到端 Smoke：延期。** 本角色只执行后端定向合同与静态门禁，未把 Fake runtime 或固定 provider 结果冒充真实 Smoke 成功。
- 真实 Smoke 仍由 Task10 主 Agent 在服务启动后执行，并需记录实际 `resolved_model/reasoning_effort`、Tool 名、`research-event:{task}:{seq}`、三级 ProcessingStep 和 Markdown/HTML/manifest Artifact ID。
- 本报告不执行最终全量 pytest、前端验收、部署或 Spec034 状态收口。

## 日志

- 进展日志：[backend-tester 日志](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-034/task-10/backend-tester/20260915-020000.md)
