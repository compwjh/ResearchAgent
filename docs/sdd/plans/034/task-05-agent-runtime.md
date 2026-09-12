# Task05 — ResearchAgentRunner 与真实子 Agent 循环

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task02、Task04；当前状态：`待执行`

## 一句话目标

实现产品内部 ResearchAgentRunner，使每个角色真的调用模型、Skill 和 Tool，并以结构化 AgentRun、预算和持久检查点受确定性 Orchestrator 控制。

## 背景与前置条件

- 必读 Spec034 的角色编排、执行协议、权限、上下文隔离和预算章节。
- 复用 `backend/app/platform/ollama.py`、Spec023 ToolExecutor/Registry 和 Spec027 Orchestrator，不接 CodeBuddy Task、不新增模型客户端。
- Coordinator 是会话层控制器，不进入 Runner；Orchestrator 是唯一创建 AgentRun 和执行 WorkItem 的组件，旧 Orchestrator 与新 Runner 不得双重执行同一 WorkItem。

## 数据、配置与接口

- 实现 AgentRun loop、Skill snapshot、allowed_tools、Schema/语义验证、ToolResult 安全化和交接物。
- `run(AgentRunInput) -> AgentRunOutput` 必须保存 `research_session_id`、实际 `resolved_model/reasoning_effort`、attempt/loop/tool 计数、`checkpoint_ref/checkpoint_hash` 和五类 Schema 的最低字段；计划批准前 Planner Run 可无 Task/WorkItem，批准后执行 Run 不得缺少 Task/WorkItem。
- 支持只读独立 Tool 并行、副作用顺序执行、fast×3 + strong×1 attempt。
- 执行 40/160 Run 限额、160/640 Task 初始限额、扩容链和取消写入屏障。

## 实施步骤与文件边界

1. 先用 Fake 模型和 Fake Tool 冻结循环、批量 Tool 校验、预算和迟到结果合同。
2. 接入真实 Ollama function calling，并持久化实际 model/effort，不保存完整 Prompt/CoT。
3. 实现 Role/Capability Registry、用户授权快照和 Skill 固定版本。
4. 实现模型/Tool/时间 limit_reached、ApprovalRequest 和检查点续跑。
5. 冻结 `run(AgentRunInput) -> AgentRunOutput`、五类结构化输出 Schema、ToolResult 安全摘要、attempt/loop/tool 计数、checkpoint hash、取消前后写屏障。

## 子代理分派

- `backend-dev`：高复杂度；严格一次一个文件，重点自检并发、锁范围、状态终态和容量上限。
- `backend-reviewer`：必须独立检查整批 Tool Call 原子校验、SSRF/凭据泄漏、取消竞争和重试预算。
- `backend-tester`：Fake Runtime 为主，并做最小真实 Ollama 探针。

## 边界与明确不做

- 子 Agent 不递归分派；只由 Orchestrator 创建 AgentRun。
- 本任务不实现论文领域逻辑、三级前端或最终报告。
- 不新增通用 Shell/Python/URL Tool，除非先回到 Spec 重新确认。

## 验收、风险与回滚

- 每个 Run 有独立上下文、真实模型元数据、Skill/Tool 快照和可验证输出。
- RoleCapabilityRegistry 只读取 Spec023 Registry；未知参数、禁用能力、Tool Schema hash 漂移在模型调用前拒绝。
- 非法批次一个 Tool 都不执行；取消后迟到结果无法写回。
- ResourceProbe 20% 余量、探针失败单 Worker和任务级上限测试通过。

## 产出物、执行结果与变更日志

- 产出：Runtime、Registry 映射、预算/检查点、后端测试和评审报告。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。
