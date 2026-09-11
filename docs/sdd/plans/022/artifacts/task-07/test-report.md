# Spec022 Task07 后端测试报告

## 结果

PASS（Task07 后端定向范围）。能力方法来源门禁、scope 隔离、少量召回与预算、失败降权/候选复审、验证成功工具失败入卡、只读建议队列、状态机和 hash 门禁均通过。

## 命令与退出码

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Task07 定向 pytest | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py --tb=short` | 0；12 passed |
| Task07 + 受影响 memory/Task10 后端回归 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py tests/test_memory_repositories.py tests/test_task10_backend.py --tb=line` | 0；43 passed，1 warning |
| 既有 worker timing 定向 smoke | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=short` | 0；1 passed，1 warning |
| Python 语法 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py tests/test_task07_backend.py` | 0；通过 |
| Diff 空白检查 | `git diff --check` | 0；通过 |

## 覆盖项

- 非 manual 方法卡必须带 evidence；`capability_method` 分类仅在明确、重复或验证成功失败信号下入候选，owner/project 召回隔离，最多 5 条且受字符预算约束。
- 未验证工具失败不会创建方法卡；匹配现有方法时追加 `tool_failure` 证据、降低 confidence 并转 `candidate`，不删除/覆盖历史 evidence。
- 验证成功的工具失败可生成 `verified_failure` candidate；事件携带建议字段时创建 `proposed` Skill 建议，不触碰保护文件。
- 建议只能按状态机流转；`applied` 必须外部确认且 protected hash 前后完全相等，owner 隔离和 scope 校验有效。
- `proposed -> applied` 与 `rejected -> applied` 被拒绝；schema 列形状、默认值、PK、CHECK、FK、索引唯一性/顺序损坏探针均 fail-closed。
- manual/explicit/repeated/verified method source 均拒绝无 evidence；8 线程并发同 statement 只生成一张方法卡。
- assistant 伪造的 `method_explicit` 被拒绝；单会话即使 payload 声称 99 次重复也不建卡，只有 2 个真实 user-message conversation 才可生成 repeated candidate。
- proposal reject/apply 并发仅一个决策成功，另一个被拒绝，最终终态保持稳定。
- schema v6 兼容扩展表可幂等初始化，既有 memory/Task10 测试保持通过。

## 未执行/阻塞

- 未运行全量 pytest、前端测试、部署或最终验收，按 Task07/Task08 范围留给主 Agent。
- 组合运行 `tests/test_conversations_api.py` 的既有 worker timing 断言曾出现一次时序性失败；同一测试独立重跑通过，Task07 定向和受影响 memory/Task10 回归均稳定通过。该已知时序性问题不由本 Task 引入。

## 产物与运行信息

- 实现报告：`docs/sdd/plans/022/artifacts/task-07/implementation-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-022/task-07/backend-dev/20260911-182407.md`
- 开始：2026-09-11 18:24 +0800
- 结束：2026-09-11 18:51 +0800
- 总耗时：约 27 分钟
- 模型：临时 Luna high（按主 Agent 分派）
- token/工具精确统计：运行时不可用；使用 apply_patch、文件读取、pytest、py_compile、git diff check

P1 修复轮：2026-09-11 18:58–19:05 +0800，约 7 分钟；第二轮修复：2026-09-11 19:10–19:18 +0800，约 8 分钟；Task07 12 passed，组合受影响回归 43 passed，worker smoke 1 passed。

## 主 Agent 后续动作

1. 分派 backend-reviewer 复核 Task07 表的迁移原子性、状态机、owner/scope 和 runtime zero-write 边界。
2. 分派 backend-tester 复跑本报告命令并补跨会话重复、并发和保护文件 hash 探针。
3. Task08 执行最终全量回归、验收、部署和运行时验证。
