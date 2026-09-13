---
name: research-plan-authoring
description: 会话式深度研究计划编排协议，负责把已完成 Intake 转成可验证、可审批的版本化研究计划。
tools: []
---

# 研究计划编排

本 Skill 只负责研究计划的结构化编排与校验，不执行搜索、下载、导入、模型运行或
研发任务分派。计划必须来自已确认的 Research Intake，不得自行扩大用户目标。

## 输入与输出

- 输入：已完成的 `topic`、`objective`、`time_range`，以及可见的来源、预算、输出和约束默认值。
- 输出：带 `schema_version`、`plan_version`、目标、范围/排除、来源策略、WorkItem、
  允许的 Skill/Tool 快照、预算、报告结构、降级策略和 `output_hash` 的
  `ResearchPlanOutput`。
- 输出不得包含隐藏思维链、原始 Prompt、凭据、Cookie、任意 URL、Shell/Python
  代码或未经 Registry 验证的能力。

## 编排规则

1. 先验证阻塞字段和计划语义，再生成版本；字段缺失返回 `INTAKE_INCOMPLETE`，不创建 Task。
2. 每个 WorkItem 必须有稳定 ID、角色、输入/输出和依赖；依赖图必须无环、最多三层、
   且不超出预算与时间范围。
3. Skill/Tool 只能引用当前 Registry 中存在且启用的条目；批准时冻结名称、版本和内容哈希。
4. 结构性变化（目标、来源、时间、能力、预算或报告结构扩大）生成新 `plan_version`，
   supersede 旧计划和待审批；无结构变化的补充不制造新版本。
5. 计划只进入 `plan_pending_approval`；用户通过统一 `approve_plan` 命令批准后，
   才能创建或激活 ResearchTask、WorkItem 和 activity assistant message。

## 失败与停止

- 禁用/不存在/未授权 Skill 或 Tool、任意公网 URL、Shell/Python 能力、越界来源或
  不可验证的模型输出：fail-closed，并返回稳定错误，不写入批准计划。
- 同一 `plan_version` 的旧按钮、重复请求和多窗口竞争由后端命令层按
  `subject_version + idempotency_key` 处理；本 Skill 不自行批准。
- 不在本 Skill 中执行 AgentRun、论文搜索、报告合成或外部副作用。
