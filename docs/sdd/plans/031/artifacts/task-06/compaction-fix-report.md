# Task06 Conversation Compaction/Evolution 回归修复报告

## 固定字段

- spec：031 — 动态模型路由与资源调度优化
- task：Task06 — 最终评审、回归、部署与复盘
- 角色：backend-dev
- 执行模型：Luna high（临时执行）
- 开始时间：2026-09-17 16:32 CST
- 结束时间：2026-09-17 16:38 CST
- 总耗时：约 6 分钟

## 根因

全量回归中的四个失败分为两类：

1. `test_worker_writes_segment_and_finishes_done` 与
   `test_worker_failure_sets_failed_and_thread_alive` 是环境相关的测试契约问题。
   Spec038 明确将 `COMPACTION_SUMMARY_MODE` 默认值设为 `llm`；本机 Ollama 可达时，压缩 worker 走 LLM 摘要，因而不再稳定产生 Spec025 规则摘要标题，也不会命中对 `build_rule_summary` 的异常注入。测试断言的是规则摘要行为，却没有固定模式，导致结果随本机 Ollama 可达性变化。测试现改为在这两个规则 worker 场景内显式使用 `COMPACTION_SUMMARY_MODE=rule`；没有降低生产 LLM 模式覆盖，Spec038 的 LLM 路径仍由 `test_spec038_memory_compaction.py` 独立验证。
2. 两个 evolution worker 失败是真实的代码级异步边界问题。`MemoryEvolutionService.process_session()` 在已经写入会话摘要后，仍在 durable checkpoint 置为 `completed` 前逐条调用记忆分类模型。Ollama 可达且事件量较大时，checkpoint 长时间保持 `running`；在 1001 条普通事件的测试中，5 秒内无法完成。该模型副作用不应阻塞可恢复的摘要 checkpoint。

## 改动文件

- `backend/app/chat/application/conversation_service.py`
  - 新增 `_dispatch_memory_extraction()`，在摘要与 checkpoint 完成后以 daemon 线程执行可选 L1 记忆抽取。
  - `process_session()` 先持久化 summary、完成 checkpoint，再异步派发模型抽取；模型不可达或抽取失败继续 fail-open。
  - 未改变 Spec031 路由、策略、资源门或前端文件。
- `tests/test_conversation_compaction_summary.py`
  - 两个明确验证规则摘要 worker 行为的测试固定 `COMPACTION_SUMMARY_MODE=rule`，消除本机 Ollama 可达性造成的非确定性。
- `docs/sdd/plans/031/artifacts/task-06/compaction-fix-report.md`
  - 本交接报告。

## 测试命令、退出码和结果

```text
python -m py_compile backend/app/chat/application/conversation_service.py
退出码 0

git diff --check -- backend/app/chat/application/conversation_service.py tests/test_conversation_compaction_summary.py
退出码 0

.venv/bin/python -m pytest -q \
  tests/test_conversation_compaction_summary.py::test_worker_writes_segment_and_finishes_done \
  tests/test_conversation_compaction_summary.py::test_worker_failure_sets_failed_and_thread_alive \
  tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse \
  tests/test_memory_repositories.py::test_evolution_worker_consumes_more_than_1000_events_and_recovers
退出码 0；4 passed in 8.79s

.venv/bin/python -m pytest -q \
  tests/test_conversation_compaction_summary.py \
  tests/test_memory_repositories.py \
  tests/test_spec038_memory_compaction.py \
  tests/test_conversations_api.py
退出码 0；70 passed in 14.03s
```

测试期间仅出现 Langfuse 本地 `127.0.0.1:3000` exporter 的 best-effort 连接警告，不影响测试退出码或断言。

## 风险

- L1 记忆抽取现在是 checkpoint 完成后的 daemon 副作用，API/worker 能更快报告摘要完成；若进程在 daemon 完成前退出，本轮 L1 抽取可能丢失，但 raw events 仍持久化，可由后续明确重试重新处理。
- 当前仍可能有多个会话的后台抽取并行调用 Ollama；本修复只解除 checkpoint 阻塞，未引入新的全局并发限流。
- 压缩 worker 的生产默认仍遵守 Spec038 的 `llm` 模式；只有规则摘要测试显式固定 `rule`。

## 主 Agent 后续动作

1. 复核本报告与 diff，确认没有覆盖 Task02–05 的并行改动。
2. 将本修复纳入 Task06 收口分支，并重新运行项目要求的唯一全量回归；同时补齐 Task02 benchmark 的质量响应校验和环境 provenance 门禁。
3. 全量通过后再更新 Task06/Spec031 状态、写最终复盘与验收文档，并执行部署 smoke。不要在此报告基础上直接声称 Spec031 已完成。

## 交接日志

- 进展日志：`.codebuddy/agent-logs/spec-031/task-06/backend-dev/20260917-163253.md`
