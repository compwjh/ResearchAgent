# Task04 — 计划版本、统一审批命令与前端卡片

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；当前状态：`已完成`

## 一句话目标

让真实 Planner 输出可验证计划，并使计划、能力和资源审批在会话与 Research Tab 中都有明确、幂等、版本绑定的前端按钮。

## 背景与前置条件

- 必读 Spec034 的 Planner 能力输出、ApprovalRequest、统一命令和卡片规则。
- 复用 ResearchPlan 版本语义；不得把自然语言“同意”转成长期授权。

## 数据、配置与接口

- 新增 `research-plan-authoring` Skill 和 ResearchPlanOutput Schema。
- 实现 `/research-sessions/{id}/commands` 的六类命令与 ApprovalRequest 状态机。
- 固定请求 `{command, subject_version, scope_json, idempotency_key}`，按 Spec034 命令表执行 CAS；重复请求返回原决策，旧版本返回 `APPROVAL_STALE`，竞争返回 `APPROVAL_CONFLICT`。
- 计划卡包含目标、范围/排除、真实研究方向、来源策略、Agent、预算、结构和降级。

## 实施步骤与文件边界

1. 后端先实现计划生成、Schema/语义校验、版本与审批幂等。
2. 实现按钮和自然语言到同一命令层的适配。
3. 前端实现三类审批卡的提交中、成功、失败、过期和多窗口冲突状态。
4. 计划批准后创建专用 activity assistant message；此时才允许 Task 进入 queued。

## 子代理分派

- `backend-dev` 与 `frontend-dev` 分端；每次只改本端文件。
- `backend-reviewer` 检查授权快照、plan_version 绑定和竞争。
- `frontend-reviewer` 检查按钮可达、DOM、XSS、静态版本号和无障碍。

## 边界与明确不做

- 不实现 AgentRunner、论文搜索或报告。
- 禁用/不存在/未授权的 Skill/Tool 不能进入批准计划。
- 通用 Shell/Python/URL 能力若被认为必需，立即停止并修订 Spec，不在本任务临时加入。

## 验收、风险与回滚

- 双击、多窗口、旧版本和自然语言/按钮竞争测试无重复副作用。
- `approve_plan` 才能创建/激活 ResearchTask 与 activity message；`revise_plan` supersede 旧 Approval；三种 active Session 冲突选择均可重复验收。
- 前端会话、Tab 和通知入口都能找到审批按钮；终端不参与审批。
- 结构修改 supersede 旧批准，小型非结构指令不制造无意义版本。

## 产出物、执行结果与变更日志

- 产出：Planner Skill、审批 service/API、三类卡片、双端评审与测试报告。
- 执行结果：后端实现、六项 P1 与 activation/outbox 幂等修复、前端会话/Research Tab 计划卡和统一审批按钮均已完成；backend-reviewer/frontend-reviewer 与 backend-tester/frontend-tester 全部 GO。后端定向回归 `116 passed、6 subtests`，4/4 故障探针通过；前端 Task03/04 合同 `28 passed`、全前端回归 `186 passed`，5/5 Fake-DOM/HTTP 探针通过；Node、py_compile、聚焦 Ruff、DOM/XSS/class/version、diff-check 均通过。详见 `artifacts/task-04/{backend-report,backend-review,backend-test-report,frontend-report,frontend-review,frontend-test-report}.md`。
- 变更日志：2026-09-13 完成计划版本、六类统一审批命令、Registry 能力/资源快照、可恢复 activation/outbox、稳定 activity 消息幂等、Research Tab 投影与计划/审批卡；旧 `/feedback` 批准旁路已移除，未知审批类型 fail-closed，stale/conflict 提供刷新接缝。资源版本升至 v45；未实现 AgentRunner、搜索或报告，Task05 可开始。
