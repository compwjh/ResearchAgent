# Spec024 Task05 后端修复报告

## 范围与结论

本轮仅修复 `024-backend-final-review.md` 的后端 P1，以及 Task05 范围内可安全收敛的 P2；未修改 `frontend/**`。修复覆盖 xhigh provider 合同、流式中断终态、会话/用户偏好事务一致性、未知模型状态码，并补充了请求体、假适配器中断、事务和迁移 marker 校验用例。

复评追加的两项 P1 也已闭环：provider 初始失败（没有任何模型输出）保留 `CHAT_FAILED`/既有错误语义；只有已产生正文或推理后迭代异常才映射 `STREAM_INTERRUPTED`。direct adapter 结果新增 `completed_normally`，无显式 Ollama `done` 的 EOF 不得收敛为 completed。

本轮最终复评的 3 项 P1 也已修复：reasoning 过滤器覆盖所有 Spec024 包装/角色标记并支持跨 chunk；v7 conversations 表已补齐 reasoning_effort CHECK，旧 v7 通过同事务 sqlite_master 修复保留现有数据；同值 PATCH/update 不刷新会话或 owner preference 时间戳。

最终复评剩余的 SSE P1 也已闭环：`ReasoningStreamFilter.finish()` 产生的 carry 与普通 reasoning delta 共用 20,000 code point 预算，避免持久化已截断但线上 SSE 超限。

## 修复清单

| 问题 | 修改 | 验证 |
|---|---|---|
| P1-1 xhigh 请求值错误 | resolver、direct payload、LangChain factory 统一使用 `provider_value=True`；业务字段仍保留 `effort=xhigh` | direct payload `think is True`；LangChain `reasoning=True` |
| P1-2 中途断线误完成 | Ollama 部分流结果带 `interrupted` 标志；provider iterator 异常被区分于正常 `StopIteration`；保存正文/推理草稿，发送 `STREAM_INTERRUPTED` 与 `done(interrupted)`，GeneratorExit 仍走持久化兜底 | `test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer`、断线假响应用例 |
| P1-3 偏好跨事务不一致 | 首条消息和既有会话消息均在同一写事务内冻结 conversation、user/assistant message、`last_reasoning_effort`；会话值优先于 owner 默认值；失败返回明确 `MESSAGE_TRANSACTION_FAILED` | `test_explicit_message_effort_updates_conversation_and_preference_atomically` |
| P1-4 未知模型状态码 | `MODEL_NOT_FOUND` 改为 HTTP 404；Ollama 不可达仍保持 503 `MODEL_UNAVAILABLE` | 既有 API 回归 + 状态分支核对 |
| P2-1/P2-2/P2-4 | 完成状态延迟到终态事件前；事件序列持久化失败改为 warning；实时 reasoning 增量增加 20,000 code point 上限 | 定向 SSE/事件序列用例 |
| P2-3 marker 校验 | v7 重启校验增加 marker payload 字段、计数非负、backup_id 长度、reasoning 默认/非空约束核对 | `test_schema_v7_marker_and_restart_are_idempotent` |
| 复评 P1：初始失败/中途异常混淆 | `_iter_run_events` 仅在已有 thinking/token 输出后将迭代异常映射为 interrupted；无输出异常继续 CHAT_FAILED | `test_provider_initial_iterator_failure_keeps_chat_failed_semantics` |
| 复评 P1：EOF 无 done 误完成 | `OllamaChatResult.completed_normally` 仅由 provider 显式 `done=true` 设置；消费层拒绝 direct 无 done 结果 | `test_eof_without_done_marker_is_not_normal_completion` |
| 最终 P1：推理过滤覆盖不足 | 增加 think/analysis/reasoning、INST、角色分隔符和控制模板；保留合法正文，跨 chunk 通过 carry 过滤 | `test_reasoning_filter_removes_wrappers_roles_and_controls_without_losing_text` |
| 最终 P1：conversation CHECK 缺失 | v6→v7 清理完成后写入 CHECK；已有合法 v7 在事务内安全补约束，非法存量 fail-closed，不重建/丢失保留数据 | `test_schema_v7_conversation_reasoning_check_survives_restart` |
| 最终 P1：同值更新时间刷新 | `update_conversation_reasoning`、`update_conversation`、preference setter 对同值更新保持原时间戳 | `test_same_effort_updates_preserve_conversation_and_preference_timestamps` |
| 最终 P1：SSE reasoning tail 超限 | token 分支和正常收尾分支均将 `finish()` tail 纳入同一 20,000 字符 live budget；持久化截断与 SSE 上限保持一致 | `test_reasoning_sse_budget_includes_stream_filter_tail` |

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python -m py_compile backend/app/platform/ollama.py backend/app/platform/ollama_direct.py backend/app/chat/application/chat_runner.py backend/app/api/routes_conversations.py backend/app/memory/repository.py` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py` | 0 | 10 passed |
| `.venv/bin/python -m pytest -q tests/test_ollama_direct.py -k 'not real_stream'` | 0 | 25 passed, 1 deselected |
| `.venv/bin/python -m pytest -q tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer tests/test_spec024_backend.py` | 0 | 36 passed, 1 deselected |
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer` | 0 | 39 passed, 1 deselected |
| `.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_task09_conversation_filters.py` | 0 | 28 passed |
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_memory_repositories.py tests/test_task09_conversation_filters.py tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer` | 0 | 68 passed, 1 deselected |
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer tests/test_conversations_api.py::test_reasoning_sse_budget_includes_stream_filter_tail` | 0 | 41 passed, 1 deselected |
| `python -m py_compile backend/app/platform/ollama.py backend/app/platform/ollama_direct.py backend/app/chat/application/chat_runner.py backend/app/chat/application/reasoning.py backend/app/api/routes_conversations.py backend/app/memory/repository.py` | 0 | 通过 |
| `git diff --check -- backend tests docs/sdd/plans/024/artifacts/task-05/backend-repair-report.md` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_conversations_api.py -x` | 1 | 环境/既有 worker 异步测试失败：memory analysis 在 2 秒断言窗口仍为 `running`；非本轮变更路径，未修改 worker |

Task03 原固定集合中的 `test_ollama_direct.py` 真实 Ollama smoke 在当前环境发现模型后请求未及时返回，单测默认 300 秒超时；因此本轮以假适配器定向集合验证，不将真实 smoke 伪报为通过。

## 决策与风险

- `OllamaChatResult.interrupted` 是向后兼容的末尾默认字段；普通 `chat_direct` 仍可返回部分正文，但会明确标记异常终止，调用层不得再收敛为 completed。
- 仅 provider 迭代器异常映射为 interrupted；模型创建/HTTP 初始失败仍按既有 `CHAT_FAILED`/`MODEL_UNAVAILABLE` 路径处理。
- 既有异步 memory-analysis worker 的 2 秒测试窗口在当前环境不稳定/超时，属于未闭环的既有测试阻塞，需 Task05 总控决定是否单独延长验收窗口或记录环境限制。
