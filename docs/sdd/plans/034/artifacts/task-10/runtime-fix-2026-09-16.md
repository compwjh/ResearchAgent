# Spec034 运行时修复记录：Intake 计划入口与通知 SSE

日期：2026-09-16

## 现象与根因

- Intake 参数齐全后只显示“已保存”，没有继续进入计划阶段。原因是会话层只持久化了
  `ResearchIntakeDraft`，没有调用既有 `PlanApprovalService.author_plan`；因此会话一直停在
  `intake_pending`，并非模型生成慢。
- 研究通知卡显示“通知连接中断”。通知接口采用有限轮询，正常 EOF 被浏览器
  `EventSource.onerror` 当成异常；不是通知数据丢失。

## 修复

- 新增 `session_plan_generation`：从已完成 Intake 生成受校验的首版计划，复用既有
  `Planner`、`PlanApprovalService` 和 Skill/Tool Registry，幂等回放已有计划。
- 会话 SSE、表单入口和历史会话恢复均接入计划生成；历史 Intake 可通过幂等恢复端点补齐
  计划投影与审批卡。
- 通知 SSE 增加明确的 `stream_end` 事件；前端正常结束后静默重连，只有真实异常才显示中断。
- 前端资源版本更新为 `app.js?v=51`、`research-tasks.js?v=6`，避免浏览器缓存旧逻辑。

## 验证

| 检查 | 结果 |
|---|---|
| Python/JavaScript 语法检查 | 通过 |
| 相关 Spec034/Spec022 定向测试 | `68 passed` |
| `POST /api/research-sessions/49e3f56441654542925031b11132e77f/plans/generate` | `202`，返回 `plan_pending_approval`、版本 1 |
| 历史消息恢复 | Intake 助手消息带计划与 pending 审批投影 |
| `GET /api/research-notifications/events?after_seq=47&polls=1` | 返回 heartbeat 后 `event: stream_end` |
| 运行时服务 | `http://127.0.0.1:8500`，`/api/health` 返回 200 |

## 用户验收

刷新 `http://127.0.0.1:8500/#research-view`。参数齐全时应看到“正在生成研究计划”，随后出现“计划已生成，等待批准”；通知卡在正常轮询结束时不再显示“连接中断”。

## 追加修复：批准后的下一步指引

### 现象与根因

点击“批准计划”后，聊天页只把按钮改成“批准计划已完成”，没有把后端已经返回的
`queued` 状态和 `research_task_id` 呈现给用户。后端实际已创建研究任务并写入“研究执行已获批准，正在排队。”活动消息，
但该消息不会自动插入当前已渲染的聊天 DOM，因此用户看不到后续阶段。

### 修复与验证

- 批准成功后即时显示“已批准、任务已创建并进入队列”，并说明后续会自动检索、评估和生成报告。
- 增加“查看研究进度”入口；研究工作台继续复用原有 Session/Task/SSE 管线。
- 批准卡状态改为“已批准”，同时禁用同一审批卡上的另一决策按钮，避免重复决策。
- 历史会话或刷新后若读到已批准/排队状态，也恢复同一指引；所有动态文本使用 `textContent`。
- 前端资源更新为 `app.js?v=52`、`styles.css?v=52`。

定向验证：`node --check frontend/app.js` 与 `tests/test_frontend_spec034_approval_guidance.py` 通过。
