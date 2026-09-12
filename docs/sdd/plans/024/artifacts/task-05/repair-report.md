# Spec024 Task05 修复与回归报告

## 结果状态和摘要

**PASS（本轮修复范围）**。修复了 `_message_stream` 在 provider 已明确发出
`reasoning_completed(completed)`、尚未收到正文首 token 时再次异常的终态回退：
持久化 reasoning 状态保持 `completed`，不再重复发送 `reasoning_completed(failed)`，
随后仅发送 `error(code=CHAT_FAILED)` 与 `done(status=failed)`；assistant 正文保持空，
generation processing step 记录为 failed。补充了假适配器回归用例。

其余 13 项失败均为已确认 Spec024 合同迁移：观测输入只保留角色和空内容，
metadata 只保留 reasoning allowlist/阶段耗时/稳定错误码，Ollama 地址跟随运行配置，
系统规则迁移断言使用 schema v7。未修改 frontend、生产配置、Ollama 部署或数据。

## 合同迁移记录

| 文件 | 迁移内容与理由 |
|---|---|
| `tests/test_chat_route.py` | 观测 prompt 当前包含平台系统约束、系统规则和 user；断言角色顺序为 system/system/user、内容全部脱敏为空，并同步 role_count/role_names，不再使用旧两条消息合同。 |
| `tests/test_kb_ask_trace.py` | KB prompt 的系统消息数量随平台约束、规则、evidence/advisory 组合为扩展合同；断言最后一条为唯一 user、其余均为 system、观测内容为空，并保留平台规则与 evidence 内容存在及不泄露问题文本的安全断言。 |
| `tests/test_observability.py` | 按 Spec024 allowlist 断言 `reasoning_present`、`reasoning_chars`、`reasoning_duration_ms`、`answer_duration_ms` 和 `stable_error_code`；明确断言 raw reasoning、thinking、success_flag、chain_type、output_chars、thinking_chars 等旧字段不进入 metadata。 |
| `tests/test_ollama_service.py` | base URL 与 `backend.app.platform.config.OLLAMA_BASE_URL` 比较，避免把当前 LAN 配置写死为 localhost；保留三个客户端 `trust_env=False` 安全断言。 |
| `tests/test_task10_backend.py` | 系统规则迁移合同从 v6 更名/更新为当前权威 schema v7；保留 owner 隔离、Unicode 上限、API 状态码、损坏表 fail-closed 和角色安全断言。 |
| `backend/app/api/routes_conversations.py` | provider 显式 reasoning terminal 事件进入持久化/发送状态机；已完成推理在后续异常中不回退，且“推理完成但未出正文”异常不再被误判为中途断线。 |
| `tests/test_conversations_api.py` | 新增 fake adapter：thinking → reasoning_completed(completed) → provider exception，验证只出现一次 completed、CHAT_FAILED/done.failed、reasoning 持久化 completed、正文为空、generation step failed。 |

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_observability.py tests/test_ollama_service.py tests/test_task10_backend.py` | 0 | **57 passed**；原 14 个失败合同全部收敛。 |
| `.venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_spec024_protocol.py tests/test_ollama_direct.py -k 'not real_stream' tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics tests/test_conversations_api.py::test_provider_failure_after_reasoning_completed_keeps_reasoning_completed tests/test_conversations_api.py::test_provider_eof_without_done_is_interrupted_at_consumer tests/test_conversations_api.py::test_reasoning_sse_budget_includes_stream_filter_tail` | 0 | **55 passed, 1 deselected**；Spec024/backend 定向与假适配器故障矩阵通过。 |
| `.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_provider_failure_after_reasoning_completed_keeps_reasoning_completed tests/test_conversations_api.py::test_provider_iterator_failure_emits_interrupted_and_keeps_partial_answer tests/test_conversations_api.py::test_provider_initial_iterator_failure_keeps_chat_failed_semantics` | 0 | **3 passed**；核心终态修复独立复验通过。 |
| `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py` | 0 | 通过。 |
| `git diff --check -- backend tests docs/sdd/plans/024/artifacts/task-05/repair-report.md` | 0 | 通过，无空白错误。 |
| `.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse` | 1 | 既有异步 worker 测试在 2 秒窗口内仍为 `running`；与本轮流状态修复无关，未修改 worker 或放宽断言。 |

## 风险与主 Agent 后续动作

1. 主 Agent 在本修复合入当前 Task 分支后重新执行唯一全量回归；本轮未运行全量。
2. 异步 memory-analysis worker 的既有 2 秒窗口失败需由 Task05 总控单独记录或在独立范围处理。
3. 真实 Ollama xhigh/low/off smoke 仍按 acceptance-report 记录的环境阻塞处理，不以假适配器替代真实性能证据。

## 改动文件

- `backend/app/api/routes_conversations.py`
- `tests/test_chat_route.py`
- `tests/test_conversations_api.py`
- `tests/test_kb_ask_trace.py`
- `tests/test_observability.py`
- `tests/test_ollama_service.py`
- `tests/test_task10_backend.py`
- `docs/sdd/plans/024/artifacts/task-05/repair-report.md`

未修改 `frontend/**`、生产配置、Ollama 部署、数据库及其他 Task05 验收产物。

## 模型与边界

- 执行模型：临时 Luna high（按任务要求）。
- 未执行 reset、stash、clean、push、merge；未启动或停止服务。
