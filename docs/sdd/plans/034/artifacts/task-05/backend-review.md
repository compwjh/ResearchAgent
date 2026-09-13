# Spec034 Task05 后端最终复审报告

## 固定字段

- spec：034 — 会话式深度研究与真实子 Agent Runtime
- task：Task05 — ResearchAgentRunner 与真实子 Agent 循环
- reviewer：backend-reviewer（当前执行 Agent）
- review_base：当前工作树相对提交 `1879fb3` 的实际差异（含当前未跟踪的 `agent_runtime.py`、`runner.py` 与 Task05 合同测试）
- review_scope：最终复核 production dispatch、预算扩容/Run 链累计、Ollama/Router 元数据回写、唯一 Orchestrator、lease 早期异常和 fast×3 + strong×1 attempt 链
- conclusion：GO
- blocking_levels：P0=0，P1=0，P2=0

## 结论

当前 Task05 backend 可 GO。第三批修复已闭合上一轮三个 P1：默认预算恢复为 Run 40/160、Task 160/640；owner/session/task 绑定的批准扩容按 0–3 次累加并受 Run 链/Task/时间绝对上限约束；实际 Router model/effort/provider 通过 running-generation CAS 写入每个 AgentRun；注入 Runner 时唯一 Orchestrator 在 WorkItem 边界走单一路径，旧 pipeline 不再执行同一 WorkItem，也不再调用 no-op model invoke。

## 重点核对

- **扩容与 hard cap：通过**。`agent_runtime.py:28-38,65-79` 区分初始额度与绝对上限；`BudgetSnapshot.from_value` 仅对 owner/session/task 绑定的 approved resource snapshot 采用增量，caller-only 预算只能收紧初始值（`agent_runtime.py:97-182`）。实际探针结果：扩容 0/1/2/3 次分别为 Run `40/160`、`80/320`、`120/480`、`160/640`，Task 分别为 `160/640`、`320/1280`、`480/1920`、`640/2560`，时间分别为 `5400/10800/16200/21600s`；第 4 次稳定拒绝。Runner 从 Store 读取 continuation chain 与同 Task 累计用量，再在模型/Tool 前检查（`agent_runtime.py:930-946,990-1022`；`research_store.py:2136-2175`）。
- **Router metadata CAS：通过**。Runner 在首个模型调用前和每次 Router 选择后调用 `_record_model_metadata`（`agent_runtime.py:614-634,966-1010`）；Store 以 owner + `status='running'` + expected generation CAS 更新 `resolved_model/reasoning_effort/provider`（`research_store.py:2212-2251`），`AgentRun`/迁移已包含 provider（`domain/models.py:425-452`；`research_store.py:548-568`）。新增故障合同确认四个独立 Run 分别持久化 `fast-selected/high/fake-provider`、`fast-selected/high/fake-provider`、`fast-selected/high/fake-provider`、`strong-selected/high/fake-provider`（`tests/test_spec034_task05_contract.py:449-474`）。
- **唯一 Orchestrator / 不双执行：通过**。当注入 Runner 且 Session→Task 绑定存在时，计划 WorkItem 创建后立即进入 `_run_agent_work_items` 并 return（`orchestrator.py:239-247`）；该方法为每个 WorkItem 构造完整 owner/session/task/work-item 的 `AgentRunInput`，仅调用 `self.run_agent`（`orchestrator.py:461-511`）。旧确定性搜索/报告路径只在未注入 Runner 时保留；`_model_kwargs` 仅作展示/审计字段解析，不含 invoke stub（`orchestrator.py:1035-1043`）。新增 pipeline 合同确认 WorkItem 有界绑定 Run 且只完成一次（`tests/test_spec034_task05_contract.py:477-505`）。
- **production dispatch / 无第二套注册表：通过**。Runner 优先使用注入 handler，否则调用既有 `backend.app.skills.tool_dispatch.build_default_dispatch()`（`agent_runtime.py:743-775`）；既有 Spec023 `ToolLoop`/dispatch/registry 未复制，生产路径没有第二个工具表或模型客户端。合同 `tests/test_spec034_task05_contract.py:230-242` 已覆盖 fallback seam。
- **lease 早期异常：通过**。ResourceProbe admission 后，checkpoint 配对、Store lookup/binding、预算读取、model factory、模型/Tool/Store 写屏障及外层异常均释放租约（`agent_runtime.py:864-942,1105-1118`）。checkpoint-store、Store binding、model-factory 故障探针通过。
- **fast×3 + strong×1 独立 attempt 链：通过**。非法输出会持久化 handoff、收敛旧 Run 为 `limit_reached`，创建独立 Run、attempt、`continued_from_agent_run_id` 和 checkpoint（`agent_runtime.py:660-724,1062-1078`）；每次 attempt 单独 Router 选档并单独写 metadata。四次 Run 的持久化链与终态合同通过（`tests/test_spec034_task05_contract.py:430-474`）。
- **快照/安全/取消边界：通过**。Skill/Tool 版本、hash、source、enabled、entry、side-effect 和 allowlist fail-closed（`agent_runtime.py:311-511`）；递归 Prompt/CoT/凭据/URL 拒绝，ToolResult 仅安全摘要；generation CAS 阻断终态后的迟到 counter/checkpoint/output 写入。

## P0/P1/P2

- P0：0。未发现跨 owner 数据泄露、任意命令执行、不可恢复数据破坏或绕过取消/CAS 的问题。
- P1：0。上一轮的预算、metadata CAS、Orchestrator stub/双执行问题均已修复并有直接合同/源码证据。
- P2：0。未发现需阻塞 Task05 收口的低优先级问题。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_skill_registry.py tests/test_tool_registry.py tests/test_tool_executor.py tests/test_spec027_runtime_contract.py` | 0 | **179 passed，6 subtests passed** |
| `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py -k 'extension or four_attempts_persist_router_metadata or orchestrator_agent_pipeline'` | 0 | 4 passed，26 deselected |
| `.venv/bin/python -m py_compile`（Task05 runtime/approval/plan/orchestrator/entry/service/store/models、合同测试） | 0 | 通过 |
| `.venv/bin/ruff check`（上述 Task05 改动文件与合同测试） | 0 | All checks passed |
| `git diff --check 1879fb3 --` | 0 | 通过 |
| `ollama list` + `get_available_models()` 平台模型枚举探针（提权读取） | 0 | 本机 11 个模型可读；adapter 的 model/effort/tool binding 合同通过 |

## 复审边界

- 仅更新本报告与 reviewer 进展日志；未修改任何业务代码、Spec、状态文件，未 commit/push/merge/reset/stash/clean。
- 未运行全量 pytest；本轮只运行 Task05 及 Task02–04、Skill/Tool/Spec027 相关定向测试和静态检查。未把 Fake adapter 结果冒充真实 Ollama 推理成功。

进展日志：`.codebuddy/agent-logs/spec-034/task-05/backend-reviewer/20260913-030000.md`。
