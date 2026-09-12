# Task03 — 会话意图、Deep Research Skill 与 Intake

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task02；当前状态：`已完成`

## 一句话目标

把真实 Skill 激活和多轮 Research Intake 接入 `/conversations/{id}/messages` 主路径，使明确研究请求创建可恢复 Session，普通聊天不被误触发。

## 背景与前置条件

- 必读 Spec034 的[§“产品行为与完整流程”](../../specs/034-conversational-deep-research-agent-runtime.md#产品行为与完整流程)、[§“ResearchIntakeDraft / IntakeField”](../../specs/034-conversational-deep-research-agent-runtime.md#researchintakedraft--intakefield)及[§“边界”](../../specs/034-conversational-deep-research-agent-runtime.md#边界)，特别是普通聊天不触发、阻塞字段和活跃 Session 冲突三条合同。
- 复用 Spec023 SkillRegistry、现有 function calling 与会话流，不把旧 `/api/chat` 当产品主入口。
- 需要创建 `deep-research-orchestration` Skill；Skill 只承载领域编排，不写研发流程。

## 数据、配置与接口

- `activate_skill`、`begin_research_intake` 为注册能力，入参和输出必须有 JSON Schema。
- 保存每个 IntakeField 的 value/source/confidence/confirmation_status/message_id。
- topic、objective、time_range 为计划前阻塞字段；安全默认值必须可见。
- Coordinator 属会话层控制器，只创建/恢复 Session 与 Draft，不创建 AgentRun。

## 实施步骤与文件边界

1. 先写明确、含糊、普通请求和模型不可用的意图合同测试。
2. 接入两阶段 Skill 发现：简介候选 → Agent 激活调用 → 验证后加载全文。
3. 实现 Session/Draft 创建与多轮字段更新、冲突选择和会话恢复。
4. 前端只实现 Intake 对话和安全字段摘要；完整计划卡留给 Task04。

## 子代理分派

- `backend-dev`：会话流、Skill 激活、Intake service；每批一个职责文件。
- `frontend-dev`：仅 Intake 展示和必要的静态资源版本更新。
- 双端 reviewer/tester 分端执行，跨端只跑本 Task smoke。

## 边界与明确不做

- 关键词不直接创建 Session；不占用 conversation_active_skill。
- 不创建 ResearchTask、不执行搜索、不生成规则模板计划。
- 同会话已有活跃 Session 时不覆盖，必须返回三种产品选择。

## 验收、风险与回滚

- 明确请求进入 Intake，含糊请求先问，普通聊天无 Session。
- 刷新后消息查询从既有 MemoryRepository processing 投影恢复 Intake 字段、来源、阻塞项、追问、冲突选项和 Skill 快照；普通消息不带 Intake 字段；重复消息不重复创建。
- 模型不可用时保存用户消息并给出真实错误，不伪装 Skill 成功。

## 产出物、执行结果与变更日志

- 产出：Deep Research Skill、会话/Intake 实现、双端定向测试与交接报告。
- 执行结果：后端实现、前端 Intake 展示、双端复审与验收均通过。后端定向测试 106 passed、6 subtests，前端全套契约/静态测试 178 passed；运行时探针覆盖明确/含糊/普通请求、消息先落库、模型失败、Skill/Tool 授权、冲突三选一、历史恢复与终态折叠。未创建 ResearchTask、AgentRun 或计划。详见 `artifacts/task-03/{backend-report,backend-review,backend-test-report,frontend-report,frontend-review,frontend-test-report}.md`。
- 变更日志：2026-09-13 完成 `deep-research-orchestration` Skill、两阶段 Skill 激活门禁、会话主路径 Intake 分流、阻塞字段/默认值 provenance、重复消息幂等与活跃 Session 三选一冲突；补齐冲突 SSE、普通聊天依赖故障回退、消息先落库、Skill/Tool 目标锁定、项目删除稳定异常路径，以及基于既有 `processing_steps.detail_json` 的脱敏 Intake 历史投影和刷新恢复。前端复用既有 assistant 消息流新增安全 Intake 摘要、字段 provenance/阻塞提示、冲突选择和终态折叠，资源版本升至 `v44`；待澄清/冲突/缺失字段或待处理 choice 保持可达，完整历史 Intake 复用同一终态收口规则。backend-reviewer/backend-tester/frontend-reviewer/frontend-tester 均 GO；Task04 可开始。
