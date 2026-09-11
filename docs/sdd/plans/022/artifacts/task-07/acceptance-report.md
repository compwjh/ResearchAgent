# Spec022 Task07 后端验收报告

> 验收角色：backend-tester（临时 Luna high）
> 日期：2026-09-11（Asia/Shanghai）
> 范围：Task07 后端定向测试、受影响 memory/Task10 回归、worker timing 单测、Python 语法/diff 检查，以及指定隔离、状态机、hash、证据探针。未运行前端或全量 pytest。

## 结论

**PASS（Task07 后端最终定向范围）。** backend-dev 已修复 proposal 状态机、schema fail-closed、方法卡 evidence 强制、并发重复合并、真实 user 角色门禁、跨会话 evidence 计数和 proposal expected-status CAS；最终定向测试、受影响回归、worker timing、综合边界探针、语法与 diff 检查全部通过。未运行前端或全量 pytest，本结论不表示 Spec022 已完成。

## 命令与结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py --tb=short` | 0 | **12 passed in 0.30s** |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py tests/test_memory_repositories.py tests/test_task10_backend.py --tb=line` | 0 | **43 passed, 1 warning in 1.74s**；warning 为 Starlette/anyio 弃用提示 |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=short` | 0 | **1 passed, 1 warning in 0.77s**；同上弃用提示 |
| Task07 改动 Python 文件 `py_compile` | 0 | **PASS**；models/repository/conversation_service 与 Task07 测试语法通过 |
| `git diff --check` | 0 | **PASS** |
| 临时 SQLite/文件边界探针 | 0 | **PASS**；schema 逐列/check/FK/index、8 线程幂等、隔离、重复合并、证据追加、状态/hash/保护文件探针全部通过 |

## 探针覆盖与结果

- **owner/project 隔离：PASS。** owner-b 不可召回 owner-a 的方法卡或建议；owner-a 查询另一项目时不可看到项目方法卡/建议。
- **重复合并：PASS。** 大小写、空白归一化后的重复 capability method 返回同一 `memory_id`，没有新增第二条方法卡。
- **8 线程幂等：PASS。** 8 个并发 `create_capability_method` 调用返回同一 `memory_id`，数据库只保留一张方法卡。
- **失败证据追加：PASS。** `record_capability_failure` 将方法降为 `candidate`、降低 confidence，并在保留原证据的同时追加 `tool_failure` 证据（证据数 1→2）。
- **方法卡证据门禁：PASS。** 无 evidence 的 explicit/repeated/manual 方法卡创建均被拒绝；完整 evidence 才能创建。
- **真实角色门禁：PASS。** `method_explicit` 只接受同 owner、同会话的 `user` message；assistant 事件被拒绝或忽略，不会生成方法卡。
- **真实跨会话 evidence：PASS。** 伪造 `repeated_sessions` 计数和同一会话多条消息均不足以建立重复方法；来自两个不同会话的 user evidence 才能生成 repeated method。
- **proposal CAS：PASS。** 并发 reject/apply 决策只有一个成功，另一个以状态冲突失败，最终状态保持单一终态。
- **schema fail-closed：PASS。** 逐列定义、默认值、scope/status CHECK、两条 FK 和两条复合 index 均符合契约；损坏 schema 启动时拒绝。
- **非法状态迁移：PASS。** `proposed -> applied`、`rejected -> accepted` 和 `rejected -> applied` 均被拒绝。
- **applied hash 门禁：PASS。** `accepted -> applied` 使用变化后的 protected hash 被拒绝且状态保持 `accepted`；使用未变化 hash 才能应用。
- **受保护文件零写：PASS。** 以临时 `AGENTS.md` 计算前后 SHA-256，proposal 创建及合法应用后 hash 不变。

## 修复复验记录

- P1 状态机旁路已移除：`update_skill_improvement_proposal` 现在严格按 `proposed -> accepted/rejected -> applied` 校验。
- schema 校验已扩展为逐列、CHECK、FK、index 和主键形状 fail-closed；破损表无法继续启动。
- `create_capability_method` 现在所有 source（含 `manual`）均需完整 evidence，并在事务中完成归一化重复检查与插入；8 线程幂等探针通过。
- `method_explicit` 现在强制绑定真实 user message；repeated method 只统计不同会话的真实 user evidence，不信任 payload 计数。
- proposal 更新改为事务内 expected-status CAS；并发 reject/apply 只允许一个决策成功。

## 后续动作

1. 主 Agent 汇总本 PASS 交接物，并在 Spec022 收口阶段执行 Task08 全量回归、验收、部署和运行时验证。
2. 保留现有 Starlette/anyio 弃用 warning，作为非阻塞后续清理项。

## 运行信息

- 业务代码修改：无；仅写本验收报告、acceptance review 章节和进展日志。
- 进展日志：`.codebuddy/agent-logs/spec-022/task-07/backend-tester/20260911-acceptance.md`
