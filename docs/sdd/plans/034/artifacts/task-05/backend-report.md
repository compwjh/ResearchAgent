# Spec034 Task05 后端交付报告

状态：backend-review P1/P2 修复完成；backend-reviewer/backend-tester 已 GO，Task05 后端验收完成。

执行元数据：2026-09-13（Asia/Shanghai）；本轮 backend-dev 起止约 08:19–09:56，耗时约 97 分钟；执行模型为当前执行 Agent 自身（主 Agent 指定本轮 Luna high）；未使用子 Agent、网络、commit、push、merge、reset、stash 或 clean。

## 改动文件

- `backend/app/research/application/agent_runtime.py`：新增 `ResearchAgentRunner.run(AgentRunInput) -> AgentRunOutput`、BudgetSnapshot、FakeModel/FakeTool、RoleCapabilityRegistry；复用既有 AgentRun store 写屏障、Spec023 Tool schema 校验与 ResourceProbe。实现 PlanApprovalService envelope 到 Runner 的快照适配、角色/Skill/Tool snapshot 校验、首个 Run 40/160 与批准扩展增量、Run 链/Task hard cap、fast×3 + strong×1 的四次输出尝试上限、批量 Tool 原子校验、只读批量并行、副作用顺序执行、安全 ToolResult 摘要、checkpoint ref/hash、取消及迟到结果屏障。
- `backend/app/research/application/runner.py`：Task05 Runner 兼容导出。
- `backend/app/research/application/entry.py`：受控 application 出口导出 runtime 合同。
- `backend/app/research/application/orchestrator.py`、`backend/app/research/application/research_service.py`：由唯一既有 Orchestrator 在 WorkItem 边界创建完整 owner/session/task/work-item AgentRunInput 并转发 Runner；注入 Runner 时旁路旧确定性执行路径，避免同一 WorkItem 双执行。
- `backend/app/research/application/approval_service.py`、`backend/app/research/application/plan_authoring.py`：统一批准能力快照的 Tool allowlist/side-effect 枚举，并扩展共享递归安全字段和值校验。
- `backend/app/research/domain/models.py`、`backend/app/research/infrastructure/research_store.py`：新增 owner/session/task/work-item 绑定的不可变 checkpoint 表与 CRUD；AgentRun generation CAS，取消/计数/模型 metadata/输出写屏障要求 running generation；新增 provider 字段迁移及 owner-bound Task/continuation chain 累计用量读取，续跑不重置硬预算。
- `backend/app/research/domain/contracts.py`：补充 `TASK_TOOL_CALL_LIMIT_REACHED`、`TOOL_EXECUTION_FAILED` 稳定错误码。
- `tests/test_spec034_task05_contract.py`：30 项 Fake/Store/Orchestrator 合同测试，另覆盖既有默认 dispatch、批准扩展 0/1/2/3 与 caller base_limits、lease early Store/Run binding 错误、Ollama adapter、四个独立 attempt 的持久 Router metadata、唯一 Orchestrator WorkItem seam。
- `docs/sdd/plans/034/task-05-agent-runtime.md`、`docs/sdd/plans/034/README.md`、`docs/sdd/spec-status-changelog.md`：更新 Task05 实现状态与变更记录。

## 测试命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py` | 0 | 30 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_skill_registry.py tests/test_tool_registry.py tests/test_tool_executor.py tests/test_spec027_runtime_contract.py` | 0 | 179 passed，6 subtests passed |
| `.venv/bin/python -m py_compile backend/app/research/application/approval_service.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/plan_authoring.py backend/app/research/application/research_service.py backend/app/research/application/runner.py backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task05_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/research/application/approval_service.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/plan_authoring.py backend/app/research/application/research_service.py backend/app/research/application/runner.py backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task05_contract.py` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## Backend-review P1/P2 修复矩阵

| 项目 | 修复结论 |
|---|---|
| P1-01 快照 | PlanApprovalService 输出 `skill`+`tools` envelope；Runner 从既有 SkillRegistryService/ToolRegistryService 快照适配，强制 Skill/Tool source_ref/version/schema_version/content_hash/enabled、Tool schema/entry/hash/side-effect 与批准值相等；role→skill tools allowlist 越界拒绝。 |
| P1-02 输出安全 | 复用 Task04 递归安全校验，拒绝嵌套 Prompt/CoT/password/api_key/authorization/token/cookie/凭据/URL/domain-like/exec/shell/python 及敏感值；source_refs 仅稳定 ID；不写 checkpoint。 |
| P1-03 checkpoint | ResearchStore 持久化不可变内容/schema/hash，并校验 owner/session/task/work-item/agent_run/continued_from；ref/hash 成对且续跑重新验 hash、只接受同绑定前序 limit_reached Run 的最小 handoff。 |
| P1-04 取消 CAS | AgentRun generation 在终态失效；counter/checkpoint/output 仅 running generation 可写；完成 CAS 失败返回当前 Store 终态。 |
| P1-05 Tool 异常 | dispatch 捕获所有普通异常，返回稳定 `TOOL_EXECUTION_FAILED` 安全摘要，Run 收敛 failed，WorkItem 尝试收敛 failed。 |
| P1-06 hard cap | 首个 Run/Task 初始为 40/160、160/640；仅 owner/session/task 绑定的 approved extension 分别增加 Run +40/+160、Task +160/+640、时间 +90min；累计截断 Run 160/640、Task 640/2560、6h、3 次扩容；caller base_limits 不能抬高。 |
| P1-07 真实装配 | 默认生产路径懒加载既有 Spec023 `build_default_dispatch()`；Router 选择值进入真实 Ollama adapter，解析并传递实际 reasoning effort；provider/model/effort 经 running-generation CAS 写入每个 AgentRun，四次独立 attempt 均有持久记录；Orchestrator 不再使用 no-op invoke stub。 |
| P1-08 lease | ResourceProbe admission lease 从 Runner 调用前持续到 model/tool/Store 写屏障所有出口，early validation、取消、异常和完成路径均释放；只读 fan-out 的线程数受授予 worker 数限制。 |
| P2-01 故障合同 | 新增默认 dispatch、批准扩展矩阵、caller base_limits、lease early Store/Run binding 错误、Ollama adapter、四个独立 attempt Router metadata、唯一 Orchestrator WorkItem seam 等故障探针，Task05 合同共 30 项。 |

## 运行时探针

- 最小真实 Ollama 探针：`.venv/bin/python -c 'from backend.app.platform.ollama import get_available_models; print(get_available_models())'`。
- 退出码：1；`httpx.ConnectError: [Errno 1] Operation not permitted`。当前沙箱禁止访问 `localhost:11434`，因此未声称真实模型成功；Fake Runtime 结论不受该环境阻塞。

## 决策与边界

- 不新增模型客户端、通用 Shell/Python/URL Tool、第二套 Orchestrator 或 Tool Registry；实际模型与 Tool 通过注入点接入既有平台/Spec023 执行器。
- AgentRun 绑定在模型调用前经 Session/Task/WorkItem 的既有 ResearchStore 约束；Planner 可仅绑定 Session，批准后的其他角色要求 Task+WorkItem。
- 能力快照是当前计划的安全投影；工具名、启用状态、参数 schema hash 任一不匹配均 fail-closed。ToolResult 仅保存 name/status/error/result_id/长度/hash/短安全摘要，不保存 Prompt、CoT、凭据或 URL。
- 达到 Run/Task 模型或 Tool 上限进入稳定 `limit_reached`，返回 `resource_extension` 后续审批信号；取消在模型调用前后、Tool 执行前后和 checkpoint 写入前检查，迟到结果不写回。

## 风险与后续动作

- 真实 Ollama function-calling 在可达环境中的端到端装配、WorkItem `waiting_approval` 投影和跨进程 checkpoint 重放需由后续集成/评审任务验证；本 Task 只冻结 runtime/contract。
- `backend-reviewer` 应重点复核四次 attempt 路由、Tool 批量原子性、ToolResult 脱敏、取消竞争和 ResourceProbe 资源 admission。
- 主 Agent 后续：运行独立 backend-reviewer/backend-tester，补真实可用 Ollama 环境探针；通过后再与 Task06/07 接线，最终由 Task10 做全量回归、部署与 Spec 收口。

进展日志：`.codebuddy/agent-logs/spec-034/task-05/backend-dev/20260913-081951.md`。
