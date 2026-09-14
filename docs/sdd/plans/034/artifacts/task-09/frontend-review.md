# Spec034 Task09 前端终审报告

评审角色：frontend-reviewer（只评 `frontend/**`；跨端契约问题单独标注）  
评审时间：2026-09-13（Asia/Shanghai）  
评审范围：Task09 Research Tab/表单/会话旅程、Task04/07/08 前端交付与评审、当前工作树 diff；未修改业务代码，未 commit。

## 结论

**NO-GO**。本轮已关闭共享 canonical projection、Session hydrate 的大部分字段，以及 Tab 审批后的 Task/SSE/报告接续问题；但仍有 1 个 P1 阻断：hydrate 后的真实 Session 卡片会把 conversation 标题覆盖成通用“深度研究”，且当前 Task 详情不提供 Agent/Tool 统计，因此 Task09 承诺的卡片可观测字段仍不成立。P0 为 0，另有 1 个 P2 项目上下文观察。

## P1 问题

### ~~P1-01：Tab 与聊天没有复用同一套 Intake/Plan/Approval/Report/Notification 组件和状态~~（本轮关闭）

本轮新增 `frontend/research-session-ui.js?v=1`，由聊天与 Research Tab 共同调用 `ResearchSessionUI.projectSession()`；计划字段也通过 `ResearchSessionUI.planField()` 归一化。聊天审批成功通过 `research-session-command-success` 事件桥接到 Tab，Tab 再复用相同 Session/Task loader、SSE 和报告管线。ProcessingTree 仍由两边共同使用。

历史上两边仍保留各自 DOM renderer（Intake/Plan/Approval/Report/Notification），但本 Task 的修复目标是共享 canonical projection/state seam；当前已具备该 seam，且没有再发现会阻断本轮范围的独立状态模型。原 P1 关闭。

<!-- Historical evidence retained for review traceability:

Task09 明确要求“复用 Task04/07/08 组件，不创建第二套树或审批 UI”，Spec034 也要求 Intake、计划/能力/资源审批卡、处理树、报告和通知在会话与 Research Tab 投影同一 Session 状态。当前只有 ProcessingTree 实际共享：

- `frontend/research-tasks.js:819-858` 自己实现 `renderSessionApprovals`、`renderSessionPlan` 和 Tab 专用 `submitSessionCommand`；聊天侧另有 `frontend/app.js:1648-1803` 的 `createConversationResearchPlan`、`renderConversationApprovals`、`submitResearchSessionCommand`。两套代码虽发送相同命令，但拥有不同 DOM、局部状态和成功后的更新行为。
- Intake 只在聊天侧 `frontend/app.js:1394-1454` 通过 `.conversation-intake` 渲染；Research Tab 没有 Intake 组件/状态面板，表单只 POST 后端，Session 处于 `intake_pending` 时无法在 Tab 内完成缺失字段交互。
- 报告也是两套投影：聊天 `frontend/app.js:1191-1279` 的 `renderConversationReport` 与 Tab `frontend/research-tasks.js:~970-1110` 的本地报告渲染；通知状态/列表只在 Tab 局部维护，聊天没有共享通知组件或同一通知状态。
- 处理树 `window.ProcessingTree.createProcessingTree` 在 `frontend/app.js:1329` 与 `frontend/research-tasks.js:899-938` 共享，Task07 的这一部分通过。

这不是纯重构偏好：用户从聊天批准计划后和从 Tab 批准计划后，局部投影更新路径不同，刷新、通知、报告可出现分叉。按任务的明确组件/状态复用要求，判定 P1。 -->

### P1-01：真实 Session hydrate 后标题与 Agent/Tool 字段仍不正确

Research Tab 现在会逐项调用 `hydrateSession()`（`frontend/research-tasks.js:607-640`），并补取 Session detail、旧 Task detail 和 conversation。状态、计划版本、阶段（由 `ResearchSessionUI.PHASES` 推导）、进度（queued/终态默认值）、审批、耗时等基础字段已能从真实返回形状恢复；旧的“直接使用列表基础字段”问题已关闭。

但当前实现有明确的优先级覆盖 bug：`hydrateSession()` 把已经由首次 `projectSession(raw)` 生成的 `base.title = '深度研究'` 和 `base.goal_excerpt` 再 spread 到新对象，同时只把刚取回的 conversation 放在嵌套 `conversation` 字段（`frontend/research-tasks.js:617-628`）。`ResearchSessionUI.projectSession()` 优先读取 `value.title` 再读取 `conversation.title`（`frontend/research-session-ui.js:31-35`），所以刷新后的真实卡片仍显示通用“深度研究”，而不是后端创建的“深度研究：<主题>”。

此外后端 Session detail 与旧 Task detail 的当前响应不含 `agent_tool_summary`、`work_items_json` 或 capability 统计；共享 projector 的推导分支（`frontend/research-session-ui.js:35-42`）没有输入，Agent/Tool 仍显示 `—`。这直接违反 Task09 要求卡片显示标题/主题及 Agent/Tool 摘要，Fake-DOM 手工注入字段不能覆盖真实 API 形状，判定 P1。

### ~~P1-02：Tab 内批准计划后没有接回新 Task/Session 状态~~（本轮关闭）

`mergeSessionCommandResult()` 现在消费后端返回的 `research_task_id`/`task`，更新 `selectedTask` 与列表投影，并在需要时调用 `selectTask(taskId, sessionId)`；该 loader 会 `loadReport(taskId)` 后 `connectStream()`（`frontend/research-tasks.js:832-857,1266-1321`）。聊天侧命令也通过 `research-session-command-success` 事件桥接到同一 merge 路径（`frontend/app.js:1730-1743`、`frontend/research-tasks.js:1466-1477`）。原 P1 关闭。

对 Session-only 审批的原有 stale 状态已通过上述路径修复；处理树继续使用 Task07 renderer，报告继续使用 Task08 loader。

## P2 / 非阻断观察

### P2-01：无当前会话时的“继承当前项目”依赖 sidebar DOM

创建 payload 现在调用 `currentProjectId()`（`frontend/research-tasks.js:552-557,1357-1364`），优先从 sidebar `.project-item-main[aria-pressed="true"]` 读取 draft project，再回退到当前会话项目；常规已加载 sidebar 的路径通过。若 Research Tab 在 sidebar 尚未渲染/异步加载完成前立即提交，则仍可能漏传 draft project；建议后续共享 app 的 project-context getter。该项不阻断本轮 P1 修复。

## 已通过项

- 普通会话列表中的独立 `research-conversation-action` 已从前端移除；`rg` 未发现残留引用。聊天中的深度研究模式由 `bindModeGuard()` 捕获并导向 Research Tab，阻止普通聊天提交（`frontend/research-tasks.js:1385-1402`），未发现旧 POST 启动旁路。旧 `/api/research-tasks/{id}` 仅保留详情/事件/报告兼容读取。
- 创建使用 `/api/research-sessions`，响应解析 Session/Conversation，并调用 `openConversationFromResearch()`（`frontend/research-tasks.js:1304-1350,1376-1383`）；标题由后端生成“深度研究：<主题>”，绑定已有会话时保留会话标题。卡片有 Session/Task ID、状态、计划版本、动态字段及“打开对应会话”；打开按钮阻止冒泡并使用既有 app 导航。
- 取消路径使用同一 Session `cancel_research` 命令，按钮具备禁用和幂等键；终态不允许重复取消。
- Task09 新增动态文本均使用 `textContent`/DOM API；未发现新增 `innerHTML`、`eval`、`document.write`。Markdown 仍走既有净化管线。打开会话 ID 使用 `encodeURIComponent`。
- 新增 CSS 均限定在 `#research-view`（`frontend/styles.css:3284-3315`）；Research Tab 已有 `prefers-reduced-motion` 规则（`frontend/styles.css:3183-3190`）。Tab 任务列表、详情、报告区域保留 `role`/`aria-label`/`aria-live`；按钮类型、忙碌态和焦点样式合同通过。
- 资源版本已更新：`frontend/index.html` 使用 `styles.css?v=48`、`app.js?v=48`、`research-tasks.js?v=2`；ProcessingTree 继续使用现有版本标记，未发现 Task09 引入未版本化资源。

## 验证记录

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js && node --check frontend/research-session-ui.js && node --check frontend/research-tasks.js && node --check frontend/processing-tree.js` | 退出码 0 |
| `node tests/test_frontend_spec034_task09.js` | 退出码 0；Session projection、进度/审批/耗时/Agent-Tool、XSS Fake-DOM 通过 |
| `node tests/test_frontend_processing_tree.js`、`node tests/test_frontend_spec034_task08.js`、`node tests/test_frontend_conversation_research.js` | 全部退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task09_contract.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task04_contract.py` | 退出码 0；27 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 退出码 0；205 passed |
| `for test_file in tests/test_frontend*.js; do node "$test_file"; done` | 退出码 0；全部前端 JS 合同通过 |
| `git diff --check -- frontend ... tests/...` | 退出码 0，无空白错误 |
| 真实浏览器/Ollama 服务 smoke | 未执行；需主 Agent 在服务可达环境补验创建→聊天→Tab→审批→Task/树/报告与刷新恢复 |

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0/CRITICAL | 0 | pass |
| P1/HIGH | 1 | **阻断** |
| P2/MEDIUM | 1 | follow-up |
| P3/LOW | 0 | pass |

Verdict: **NO-GO**。共享 canonical projection、真实 hydrate 主路径及审批→Task/SSE/报告接续已通过；仍需修复 hydrate 的标题优先级并补齐真实 Agent/Tool 摘要字段，然后再重新评审并执行真实浏览器 smoke。
