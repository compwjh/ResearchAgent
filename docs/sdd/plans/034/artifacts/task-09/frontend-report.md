# Spec034 Task09 前端交付报告

## 结果状态/摘要

GO（前端实现与定向合同验证完成，等待主 Agent 进行双端联调、真实浏览器 smoke 与最终收口）。Research Tab 现以 ResearchSession 为创建/列表产品入口，创建表单提交 `/api/research-sessions` 的 Intake 摘要；返回 Session 后自动打开关联会话。列表卡片复用既有 Task07 ProcessingTree、Task04 审批和 Task08 报告/通知状态投影，不创建第二套树或状态模型。普通会话列表不再注入独立“研究”按钮。

本轮前端评审修复已完成：聊天与 Research Tab 共用 `ResearchSessionUI.projectSession/planField`；Tab 列表对真实 Session 响应做详情、Task、会话标题的渐进式 hydrate，补齐 Session 卡片承诺字段；聊天审批成功会发布统一 Session 命令结果，由 Research Tab 合并并复用既有 `selectTask`、ProcessingTree SSE、报告加载与通知上下文。创建请求继续复用稳定 `idempotency_key`/`trigger_message_id`，当前项目从会话或选中项目继承。

## 改动文件

- `frontend/research-tasks.js`：Session 列表与创建入口、Session→Task 兼容投影、会话卡阶段/进度/审批/耗时/Agent-Tool 摘要、打开对应会话、统一 `cancel_research` 命令；保留 Task07/08 的树、报告、通知和旧 Task 详情/事件读取兼容。
- `frontend/research-session-ui.js`：聊天与 Research Tab 共用的只读 Session 投影及计划字段、进度/审批/耗时/Agent-Tool 格式化 helper；不持有 transport 或独立 UI 状态。
- `frontend/app.js`：聊天计划使用共享投影；聊天 Session 命令成功向 Research Tab 发布统一结果事件。
- `frontend/index.html`：创建表单改为 Session 语义，按钮与状态文案更新；移除普通会话研究按钮样式；`research-tasks.js` 版本升至 `v2`，app/styles 资源升至 `v48`。
- `frontend/styles.css`：新增 Session 卡片摘要与“打开对应会话”按钮样式，全部限定在 `#research-view`。
- `tests/test_frontend_spec034_task09.js`：Session projection、进度、审批、耗时、Agent/Tool 摘要与恶意文本 Fake-DOM 探针。
- `tests/test_frontend_spec034_task09_contract.py`：Session-only create/list、旧按钮/旁路移除、表单/项目继承、资源版本、XSS/CSS 作用域静态合同。
- `.codebuddy/agent-logs/spec-034/task-09/frontend-dev/20260913-frontend-review-fixes.md`：本轮 P1/P2 修复与验证日志。

## 测试命令/退出码/结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-session-ui.js && node --check frontend/app.js && node --check frontend/research-tasks.js && node --check frontend/processing-tree.js` | 0 | 语法通过 |
| `node tests/test_frontend_spec034_task09.js` | 0 | Task09 Session/Fake-DOM 通过 |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 0 | 8/8 前端 JS 合同通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 0 | 205 passed |
| DOM/XSS/class/version/冲突标记机械检查 | 0 | Research renderer 无 `innerHTML`/`eval`/`document.write`/`prompt`；新增 class 均有 `#research-view` CSS；`?v=48`/`?v=2` 已同步 |
| `git diff --check -- frontend tests/test_frontend_spec034_task09.js tests/test_frontend_spec034_task09_contract.py` | 0 | 通过 |

## 决策依据

- 创建和列表均走 `/api/research-sessions`；旧 `/api/research-tasks` 仅保留详情/事件/报告调试兼容读取，前端没有旧 POST 启动旁路。
- 后端 Session 列表/创建响应可能只返回 Session、嵌套 Task 或创建响应中的 `conversation`，前端统一 `sessionTaskProjection()` 归一化，Session 仍是 canonical 状态来源。
- Intake 只发送后端白名单字段（topic/objective/language/depth/sources/output/citations/constraints），首条自然语言消息与“深度研究：<主题>”标题由统一 Session 后端接缝生成；现有会话只发送 conversation/project 绑定，不覆盖既有标题。
- 卡片动态值全部通过 `textContent`；会话跳转使用编码后的 `/c/{conversation_id}` 与既有 app `popstate` 导航，避免新增导航/任务状态模型。
- 顶部取消按钮改为 Session `cancel_research` 统一命令，和会话计划审批按钮共享同一幂等命令层。

## 风险/阻塞

- 尚未执行真实服务/浏览器 smoke；需主 Agent 在后端 Session 列表与创建接口启动后验证真实返回字段、自动打开会话、Session→Task 绑定及通知跳转。
- Session 列表当前后端摘要未必包含 topic/progress/Agent-Tool 汇总；前端会安全显示占位 `—`，待后端投影字段可用后自动展示，不伪造进度。
- 未运行后端 pytest，未执行部署、commit、push、merge、reset、stash 或 clean，符合前端分端范围。
- 聊天命令成功事件在 Research Tab 未启动或尚未完成列表 hydrate 时仅更新可用的当前选择；若用户随后进入 Research Tab，`refreshWorkspace` 会重新从 Session 详情恢复 canonical 状态。

## 主 Agent 后续动作

1. 联调 `POST/GET /api/research-sessions`，确认创建响应的 `research_session_id`、`conversation.conversation_id`、Session 状态与项目继承。
2. 运行 frontend reviewer/tester，并做创建→会话→Tab 往返、统一 Intake/Plan/Approval、Task07 树、Task08 报告/通知 smoke。
3. Task10 收口时运行全量回归、真实浏览器/窄屏验证、直接启动服务并更新 Spec034 状态台账。

## 开始/结束/总耗时

- 开始：2026-09-13（Asia/Shanghai，Task09 前端上下文恢复后）
- 结束：2026-09-13 15:08（Asia/Shanghai）
- 总耗时：本轮评审修复约 25 分钟；含前轮实现约 65 分钟

## 模型/token/工具统计

- 模型：当前执行 Agent 自身；主 Agent 指定临时 Luna high
- token：子任务上下文未提供可查询 token 计数
- 工具：`apply_patch`、`exec_command`；本轮未使用网络、后端测试或子 Agent；精确 token 计数不可查询

## 进展日志

- `.codebuddy/agent-logs/spec-034/task-09/frontend-dev/20260913-frontend-start.md`
- `.codebuddy/agent-logs/spec-034/task-09/frontend-dev/20260913-frontend-final.md`
- `.codebuddy/agent-logs/spec-034/task-09/frontend-dev/20260913-frontend-review-fixes.md`
