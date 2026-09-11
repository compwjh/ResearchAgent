# Spec024 Task05 后端最终独立复审

## 评审范围

- Spec：`docs/sdd/specs/024-visible-reasoning-controls.md`
- Task：`docs/sdd/plans/024/task-05-review-regression-deploy.md`
- Task03 后端报告：`docs/sdd/plans/024/artifacts/task-03/backend-test-report.md`、`backend-review-report.md`
- 修复证据：`docs/sdd/plans/024/artifacts/task-05/backend-repair-report.md`
- 实际后端 diff：`routes_conversations.py`、`chat_runner.py`、`reasoning.py`、`memory/repository.py`、`ollama.py`、`ollama_direct.py`
- 边界：只评审后端并运行定向测试；未修改 `backend/**`，未执行 reset/stash/clean/push/merge。

## 最终结论

**GO。** P0=0，P1=0，P2=5（均为非阻塞建议）。

本次不采信上一轮结论，重新读取 Spec024、Task05、Task03 报告、最新 repair report 和当前 backend diff。此前唯一剩余 P1——推理流 `finish()` 的跨 chunk carry 在已达到 20,000 字符后仍可能额外发送 SSE 内容——已由 token 分支和正常收尾分支共同预算修复，并由新增回归测试覆盖。

## 关键合同复核

1. **xhigh → Ollama `think=true`：通过。** resolver 对 xhigh 产生 `provider_value=True`/`route_payload["think"] = True`（`backend/app/platform/ollama.py:115-133`）；direct payload 同样映射（`backend/app/platform/ollama_direct.py:77-90`），LangChain 使用同一 provider 值（`backend/app/chat/application/chat_runner.py:154-172`）。off 仍为布尔 `False`，字符串档位不静默降级。
2. **初始 provider 失败保持 `CHAT_FAILED`：通过。** `_iter_run_events` 只有已观察到 thinking/reasoning/token 后才将迭代异常转换为 `ChatStreamInterrupted`；无任何输出的初始异常继续普通失败路径（`backend/app/api/routes_conversations.py:235-254`、失败事件 `527-542`）。
3. **部分流异常/EOF 无 done 为 `STREAM_INTERRUPTED`：通过。** direct adapter 仅看到显式 `done=true` 才设置 `completed_normally`（`backend/app/platform/ollama_direct.py:107-111,177-221`）；消费层拒绝 direct 无正常完成标记的结果并持久化 interrupted（`routes_conversations.py:450-455,507-522`）。
4. **`OllamaChatResult.completed_normally` 语义：主路径通过。** direct 结果字段明确表示 provider 显式最终标记（`ollama_direct.py:35-46,210-220`）；LangChain 结果仍按链路正常收尾生成，异常分类由 `_iter_run_events` 负责，当前未发现 P1 级终态误判。
5. **消息/会话偏好同事务：通过主路径。** 首条消息使用 `create_conversation_messages(..., update_preference=...)`，既有会话使用 `create_message_pair`；会话、两条消息和显式偏好更新共享写事务（`routes_conversations.py:567-602`、`repository.py:1266-1331`）。PATCH 使用 `update_conversation_reasoning` 的同一事务路径（`repository.py:1333-1352`）。
6. **未知模型 404：通过。** 模型列表不可达返回 `MODEL_UNAVAILABLE`/503，列表中不存在的模型返回 `MODEL_NOT_FOUND`/404（`routes_conversations.py:167-173`）。
7. **reasoning 过滤、上限与敏感日志：通过。** 过滤器覆盖 `<think>`/`<analysis>`/`<reasoning>`、`[INST]`、角色标记及协议标记，并保留跨 chunk carry（`backend/app/chat/application/reasoning.py:12-74`）；普通 delta 和两个 `finish()` tail 分支均共享 20,000 code point live budget（`routes_conversations.py:400-441,478-491`），持久化仍经统一过滤/截断。错误消息做敏感字段脱敏（`routes_conversations.py:226-232,527-542`），观测 metadata 为 allowlist，不写 reasoning 原文（`backend/app/platform/observability/spans.py:106-117`）。
8. **SSE event_seq、终态与持久化：主路径通过。** 所有公开事件经 `EventSequencer`，发送前记录 `last_event_seq`，done 带终态（`routes_conversations.py:257-267`）；完成状态在终态事件前持久化（`routes_conversations.py:497-504`）。本轮新增 tail 回归确认展示预算与持久化预算一致。
9. **schema v7 迁移：通过。** v6→v7 在清理流程中补 conversation `reasoning_effort` CHECK；旧 v7 缺约束时校验存量合法值、在同一迁移事务更新 `sqlite_master` 并递增 schema version，非法存量 fail-closed，保留合法数据（`repository.py:528-656`）。
10. **同值更新时间：通过。** conversation、preference 的同值 reasoning 更新不刷新时间戳，值变化仍使用一致时间戳（`repository.py:1237-1246,1333-1352,1363-1431`）。

## 本轮修复确认

上一轮已指出的唯一 P1 已清零：

- 普通 reasoning delta 在 `routes_conversations.py:419-423` 按剩余容量截断并累计 `reasoning_stream_chars`。
- token 到达时 flush 的 carry 在 `routes_conversations.py:427-441` 现在同样按剩余容量截断。
- 无 token 的正常收尾在 `routes_conversations.py:478-491` 也执行同样的预算保护。
- 新增 `tests/test_conversations_api.py:266-289` 覆盖 20,000 个可见字符后追加跨 chunk marker 前缀的边界；断言所有 SSE `reasoning_delta` 合计不超过 20,000，且最终消息 completed。

因此“持久化已截断但线上 SSE 超限”的 P1 不再成立。

## P2（非阻塞）

以下问题不阻塞本 Task 后端 GO，但建议后续单独收口：

1. 新 owner 首次创建且未显式提供 effort 时会回退 xhigh，但 `create_conversation_messages` 不主动补插 preference 行（`repository.py:1275-1285`）；当前固定 `local-user` 已由迁移初始化。
2. `_langchain_drive` 的 `finally` 会生成 `completed_normally=True`（`chat_runner.py:92-112`），该字段语义对 LangChain 异常较宽；当前路由的迭代异常分类不受影响。
3. 失败/断线后 finally 的兜底可能继续把残余 processing step 统一标记为 interrupted（`routes_conversations.py:547-563`），审计细节仍可更精确。
4. `record_event_seq` 失败目前仅 warning 并继续发送 SSE（`routes_conversations.py:261-267`），极端情况下刷新恢复可能缺少已发送序号。
5. direct 已看到 done 后继续迭代时发生 transport 异常的极小窗口仍未单独丢弃后续异常（`ollama_direct.py:177-192`）。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_memory_repositories.py tests/test_task09_conversation_filters.py tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer tests/test_conversations_api.py::test_reasoning_sse_budget_includes_stream_filter_tail` | 0 | **69 passed, 1 deselected** |
| `.venv/bin/python -m pytest -q tests/test_spec024_protocol.py -k 'v7_cleanup or current_sse_helper_is_not_yet_v7_envelope or role_aware_direct_payload_preserves_system_and_user_roles'` | 0 | **10 passed, 3 deselected** |
| `python -m py_compile backend/app/platform/ollama.py backend/app/platform/ollama_direct.py backend/app/chat/application/chat_runner.py backend/app/api/routes_conversations.py backend/app/chat/application/reasoning.py backend/app/memory/repository.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

按用户要求未运行全量 pytest。repair report 已记录 `tests/test_conversations_api.py -x` 的既有 memory-analysis worker 2 秒窗口失败；该环境问题不是本轮 P1，Task05 总控仍需在后续收口阶段决定全量回归/部署 smoke 的处理。

## 复审记录

- 执行模型：临时 Luna high（重新独立复审）
- 进展日志：`.codebuddy/agent-logs/spec-024/task-05/backend-reviewer/20260912-000000.md`
- 开始/结束：2026-09-12（本轮）
- 未执行 reset/stash/clean/push/merge，未修改业务代码；本轮仅更新本评审报告及评审进度日志。
