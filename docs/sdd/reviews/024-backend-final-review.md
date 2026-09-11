# Spec024 Task05 后端最终独立复审

## 评审范围

- Spec：`docs/sdd/specs/024-visible-reasoning-controls.md`
- Task：`docs/sdd/plans/024/task-05-review-regression-deploy.md`
- Task03 证据：`docs/sdd/plans/024/artifacts/task-03/backend-test-report.md`、`backend-review-report.md`
- 最新修复证据：`docs/sdd/plans/024/artifacts/task-05/backend-repair-report.md`、`repair-report.md`
- 实际后端 diff：`backend/app/api/routes_conversations.py`；并复核 reasoning、Ollama、repository、observability 相关实现。
- 边界：只评审后端并运行定向测试；未修改业务代码，未执行 reset/stash/clean/push/merge。

## 最终结论

**GO。** P0=0，P1=0，P2=5（均为非阻塞建议）。

本轮重新核对了最新显式 `reasoning_completed` 终态修复，以及 13 项旧测试合同迁移。修复后的关键终态、reasoning 脱敏 allowlist、schema v7 CHECK、LAN Ollama 配置、未知模型 404、初始失败/部分流异常/EOF 无 done 分类均与 Spec024 一致；定向测试通过。

## 关键合同复核

1. **显式 reasoning completed 后异常：通过。** `_iter_run_events` 记录 provider 的 `reasoning_completed` 与是否已产生 answer token；推理已完成但首 token 前异常保持普通 `CHAT_FAILED`，不回退 reasoning 状态，也不重复发 `reasoning_completed`（`backend/app/api/routes_conversations.py:235-267`）。消费层对 provider terminal 事件持久化合法状态并只发一次公开终态（`routes_conversations.py:438-458`）；异常分支用 `reasoning_completed_emitted` 防止重复/回退（`routes_conversations.py:544-585`）。新增 fake-adapter 测试断言 reasoning 仍为 completed、正文为空、`CHAT_FAILED`/`done.failed` 且 generation step 为 failed（`tests/test_conversations_api.py:243-282`）。
2. **xhigh → Ollama `think=true`：通过。** resolver 对 xhigh 产生 `provider_value=True`（`backend/app/platform/ollama.py:115-133`）；direct payload 使用相同映射（`backend/app/platform/ollama_direct.py:77-90`），LangChain 消费统一 provider 值（`backend/app/chat/application/chat_runner.py:154-172`）。
3. **初始失败、部分流异常与 EOF：通过。** 无任何输出的 provider 初始异常保留 `CHAT_FAILED`；已经产生推理或正文后迭代异常映射 `STREAM_INTERRUPTED`（`routes_conversations.py:235-267,544-585`）。direct 只有 Ollama 显式 `done=true` 才设置 `completed_normally`（`backend/app/platform/ollama_direct.py:107-111,177-221`）；无 done 的 EOF 不收敛为 completed（`routes_conversations.py:486-491`）。
4. **reasoning allowlist、无 raw chain 与敏感日志：通过。** `_TEMPLATE_MARKERS` 覆盖 think/analysis/reasoning、INST、角色和协议标记，并保留跨 chunk carry（`backend/app/chat/application/reasoning.py:12-74`）。观测输入经 `redact_prompt_messages` 清空所有 prompt 内容，仅保留角色（`backend/app/platform/observability/spans.py:159-170,219-221`）；metadata 只接受 reasoning presence/chars、阶段耗时和稳定错误码 allowlist（`spans.py:106-117`），不保存 raw reasoning、`thinking`、旧 `chain_type`/`success_flag`/输入输出字符字段。错误消息使用敏感字段脱敏（`routes_conversations.py:226-232,565-585`）。
5. **消息/会话偏好同事务：通过主路径。** 首条消息和既有会话分别通过 `create_conversation_messages`/`create_message_pair`，会话、消息和显式偏好更新共享写事务（`routes_conversations.py:567-602`、`backend/app/memory/repository.py:1266-1331`）；PATCH 使用同一事务更新 conversation 与 preference（`repository.py:1333-1352,1363-1431`）。
6. **未知模型 404 与 LAN 配置：通过。** `_validate_model` 对模型不存在返回 `MODEL_NOT_FOUND`/404，对 Ollama 不可达返回 `MODEL_UNAVAILABLE`/503（`routes_conversations.py:167-173`）。Ollama 客户端和 probe 使用 `config.OLLAMA_BASE_URL`（`backend/app/platform/config.py:16`、`backend/app/platform/ollama.py:26,136-143`），三个客户端保留 `trust_env=False` 安全约束；测试不再把 LAN 环境误写死为 localhost。
7. **schema v7 CHECK：通过。** v6→v7 清理流程补齐 conversation `reasoning_effort` CHECK；旧 v7 缺约束时先验证存量合法值，再在同一事务更新 `sqlite_master` 并递增 schema version，非法存量 fail-closed（`backend/app/memory/repository.py:528-656`）。系统规则旧测试已迁移为权威 schema v7，同时保留 owner 隔离、Unicode 上限、损坏表 fail-closed 和角色安全断言。
8. **SSE 上限、event_seq 与终态持久化：通过主路径。** 普通 reasoning delta 与两个 `finish()` tail 分支共用 20,000 code point 预算（`routes_conversations.py:415-476,514-533`）；公开事件经 `EventSequencer` 并记录 `last_event_seq`（`routes_conversations.py:270-281`）；完成状态在 `done` 前持久化（`routes_conversations.py:534-541`）。

## 旧测试合同迁移复核

最新 repair report 声称的 13 项失败均为已确认合同迁移，并保留了安全断言：

- `test_chat_route.py` / `test_kb_ask_trace.py`：允许平台约束、系统规则、evidence/advisory 扩展 system 消息，但仍断言角色顺序、prompt 内容观测为空、唯一 user 和问题文本不进入 system 内容。
- `test_observability.py`：断言 reasoning allowlist 和阶段耗时/稳定错误码，同时明确排除 raw reasoning、`thinking`、`success_flag`、`chain_type`、`output_chars`、`thinking_chars` 等旧字段。
- `test_ollama_service.py`：基于运行配置断言 LAN base URL，并保留三个客户端 `trust_env=False`。
- `test_task10_backend.py`：v6 断言迁移为 v7，仍覆盖 owner 隔离、Unicode 限制、损坏表 fail-closed 与角色安全。

## P2（非阻塞）

1. 新 owner 首次创建且未显式提供 effort 时回退 xhigh，但不主动补插 preference 行（`repository.py:1275-1285`）；当前固定 `local-user` 已由迁移初始化。
2. `_langchain_drive` 的 `finally` 仍生成 `completed_normally=True`（`chat_runner.py:92-112`），字段语义对 LangChain 异常偏宽；当前路由通过 iterator 分类和新增 terminal guard 保持主路径正确。
3. 失败/断线后的 finally 兜底可能把残余 processing step 统一标记为 interrupted（`routes_conversations.py:586-602`），审计细节可进一步精确。
4. `record_event_seq` 持久化失败目前只记录 warning 并继续发送 SSE（`routes_conversations.py:274-281`），极端刷新恢复可能缺少已发送序号。
5. direct 已见 done 后继续迭代时发生 transport 异常的极小窗口仍未单独丢弃后续异常（`ollama_direct.py:177-192`）。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_spec024_protocol.py tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_failure_after_reasoning_completed_keeps_reasoning_completed tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer tests/test_conversations_api.py::test_reasoning_sse_budget_includes_stream_filter_tail tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_observability.py tests/test_ollama_service.py tests/test_task10_backend.py` | 0 | **112 passed, 1 deselected** |
| `python -m py_compile backend/app/api/routes_conversations.py backend/app/platform/ollama.py backend/app/platform/ollama_direct.py backend/app/chat/application/chat_runner.py backend/app/chat/application/reasoning.py backend/app/memory/repository.py backend/app/platform/observability/spans.py` | 0 | 通过 |
| `git diff --check -- backend tests docs/sdd/plans/024/artifacts/task-05/repair-report.md docs/sdd/reviews/024-backend-final-review.md` | 0 | 通过 |

补充运行的 `tests/test_task05_backend.py` 组合为 35 passed、1 failed；唯一失败是旧 fixture 未 mock reasoning capability probe，当前 LAN Ollama 不可达时收到 503，非本轮业务改动路径。按用户要求未运行全量 pytest；真实 Ollama xhigh/low/off smoke 的环境限制已记录在 acceptance/repair report，不能用假适配器替代。

## 复审记录

- 执行模型：临时 Luna high
- 进展日志：`.codebuddy/agent-logs/spec-024/task-05/backend-reviewer/20260912-000000.md`
- 日期：2026-09-12
- 未执行 reset/stash/clean/push/merge，未修改业务代码；本轮仅更新本评审报告及评审进度日志。
