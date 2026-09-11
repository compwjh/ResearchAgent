# Task06 前端评审报告：手机端体验

## 固定回传字段

- 角色：frontend-reviewer
- 模型：临时 Luna high（按主 Agent 分派）
- 时间：2026-09-11（最终修复复审，Asia/Shanghai）
- 范围：仅评审 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、Task06 前端合同及 Task09/Task10 前端交接报告；未修改业务代码。
- 上一轮报告：[review-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/022/artifacts/task-06/review-report.md)
- 上一轮进展日志：[20260911-180557.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-022/task-06/frontend-reviewer/20260911-180557.md)
- 本轮最终进展日志：[20260911-181114.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-022/task-06/frontend-reviewer/20260911-181114.md)

## 结论

**GO（最终修复复审）。** 上一轮 P1/P2 均已清除：流式回答失败不再提供会重复 POST 的聊天 retry，只保留消息加载/历史分页 GET 重试；assistant 已创建和未创建两条流式失败路径均给出“请确认后重新发送”文案；移动抽屉/项目新建/会话菜单关闭后的焦点目标按打开状态和可见性分支，桌面菜单仍恢复原触发器；项目、会话、记忆、导航和 `#new-project-button` 等移动入口满足 44px。49 项前端合同、JavaScript 语法、5 个 Node 合同及 diff check 全部通过。

## 最终修复复审（2026-09-11）

| 检查项 | 结论 | 当前证据 |
|---|---|---|
| 流式失败不显示会重复 POST 的 retry | PASS | `messages` 事件委托没有聊天 retry 分支，`sendConversationMessage(question, { appendUser: false })` 不存在；流式失败由 `addConversationError`/`addConversationErrorNotice` 写入手动“请确认后重新发送”提示（`app.js:266-279,1519-1527`）。用户若确认后再次点击发送，属于明确的新发送。 |
| 消息加载/历史分页 GET retry | PASS | `loadConversationMessages` 与 `loadOlderConversationMessages` 失败路径仅通过 `setConversationRetryStatus` 重试各自 GET；历史请求继续携带 `before: conversationState.messageCursor`（`app.js:998-1002,1037-1041`）。 |
| assistant 已创建/未创建的流式错误文案 | PASS | SSE `error` 与流式连接中断最终均进入 `addConversationErrorNotice`；未创建 assistant 的网络/HTTP 失败进入 `addConversationError`，两者均包含“请确认后重新发送”（`app.js:1500,1506-1517,1519-1527`）。未自动发起第二个 POST。 |
| 移动抽屉、项目新建、会话/项目菜单焦点 | PASS | `closeMobileDrawer` 先检查 `mobileDrawerState.open`，再只在 `mobileTriggerIsVisible()` 时恢复仍连接的目标（`app.js:116-143`）；项目新建窄屏保存 `mobileNavToggle`、桌面保存 `newProjectButton`，且移动点击先收起抽屉而不聚焦 off-canvas 按钮（`app.js:1578-1583,1592`）。菜单关闭后移动最终回到可见 toggle，桌面由 `closeFloatingMenu(true)` 回到原触发器（`app.js:831-854`）。 |
| Esc、遮罩、对话框关闭 | PASS | 抽屉关闭按钮、遮罩和 Escape 均调用 `closeMobileDrawer(true)`；dialog close 仅聚焦已连接的保存目标（`app.js:1572-1577,1603-1613`）。 |
| 移动触控目标 | PASS | `@media (max-width:760px)` 为项目树/项目菜单/新建项目、new-chat、nav、项目/会话行、历史分页和行菜单设置 `min-height:44px`，菜单按钮设置 `min-width:44px`，来源编号为 44×44（`styles.css:1863-1866,1877-1883`）。 |
| safe-area、软键盘、100dvh、无横向溢出、reduced-motion | PASS（静态） | 抽屉/工作区使用 `100dvh` 与 safe-area，composer/textarea 预留底部安全区和 `34dvh` 高度，body/main/bubble 有横向溢出防护，`prefers-reduced-motion` 关闭 processing/import 动画（`styles.css:1797-1800,1804-1884`）。 |
| 单一 sidebar/业务状态与窄屏入口 | PASS | `index.html` 仍只有一个 `#mobile-sidebar`；移动状态仅保存 drawer open/focus，项目、会话、记忆、历史分页、processing 与 RAG 继续复用既有状态/handler（`index.html:11-47`; `app.js:87-114,998-1041,443-592`）。 |
| 桌面 Task09/Task10 行为 | PASS（合同/静态） | Task09/Task10、Conversation、Management、Task05 合同均在本轮 49 项中通过；移动规则限定在 `@media (max-width:760px)`，桌面菜单触发器恢复路径未改变。 |
| 资源版本、XSS、DOM 契约 | PASS | 实际资源为 `app.js?v=32`、`styles.css?v=32`；新增动态文本使用 `textContent`，Markdown 仍先 DOMPurify 后 `innerHTML`，静态 candidate/message HTML 仅为固定模板（`index.html:7-8,445-446`; `app.js:253-279,301-305,3016-3037`）。5 个 Node 合同覆盖 hostile HTML、renderer 和 GET-only 契约并通过。 |

本轮未发现 P0/P1/P2 缺陷；真实窄屏/桌面浏览器 smoke 仍属于主 Agent 的收口验收边界。

## 上一轮修复轮复审（历史基线，2026-09-11）

| 修复项 | 结论 | 当前证据 |
|---|---|---|
| 流式错误不再显示重复 POST retry | PASS（上一轮 P1 清除） | 已移除 `messages` 委托中的 retry 分支和 `appendUser:false` 调用；`app.js:1518-1521` 只处理既有论文候选操作。`addConversationError` 仅在 assistant 尚未创建时显示“请确认后重新发送”（`app.js:258-262,1502-1508`）。 |
| 消息加载/历史分页 GET retry | PASS | `loadConversationMessages` 与 `loadOlderConversationMessages` 的失败路径仍使用 `setConversationRetryStatus` 调用 GET 加载函数（`app.js:982-985,1020-1023`），未改变 `before` 游标。 |
| 流式错误后的明确手动重发提示 | PARTIAL — P2 | 若流在 `meta` 前失败，`addConversationError` 有明确文案；若已创建 assistant 后收到 SSE `error` 或连接中断，当前只显示记忆未保存/连接中断提示（`app.js:1483,1489-1499`），没有统一“请确认后重新发送”文案。输入框仍可用，用户可手动重新填写发送，但提示不一致。 |
| 移动菜单关闭焦点 | PASS（移动菜单路径）/FAIL（桌面回归） | `menuButton` 现在 `closeFloatingMenu(false); closeMobileDrawer(true); handler()`（`app.js:833-837`），移动抽屉打开时可回到可见 toggle；但桌面时 `mobileNavToggle` 是 `display:none`，无条件 `closeMobileDrawer(true)` 可能把焦点交给隐藏 toggle，随后 dialog close 继续恢复到隐藏/失焦目标。 |
| 移动项目新建 dialog 焦点 | **FAIL — P1** | `app.js:1574` 仍保存 `dialogState.restoreFocus = newProjectButton`；移动侧栏委托在 `app.js:1563` 用 `closeMobileDrawer(false)` 收起，`projectDialog` close 在 `app.js:1585-1587` 再聚焦该已移出视口的按钮。dialog 打开时焦点在输入框，但关闭后触发器不可见。 |
| project/menu/nav/conversation 触控目标 | PARTIAL — P2 | 移动 CSS 已覆盖 project tree toggle/menu、最近会话菜单、new-chat/nav、项目/会话行和行菜单，主体均 `min-height:44px`，菜单主体 `min-width:44px`（`styles.css:1862-1865`）。但 `#new-project-button` 不在选择器中，仍沿用 `.icon-button` 的约 8px padding，未保证 44×44。 |
| 桌面、资源版本、XSS/DOM | PASS（静态） | 旧 Task09/Task10 合同和新增合同均通过；实际资源为 `app.js?v=32`、`styles.css?v=32`，动态文案走 `textContent`，Markdown 仍经 DOMPurify；桌面焦点路径需修复后再做真实 smoke。 |

## 上一轮逐项核对（历史基线）

| 检查项 | 结论 | 证据与说明 |
|---|---|---|
| 单一 sidebar/抽屉、无第二套业务状态 | PASS | `index.html:14` 只有一个 `.sidebar#mobile-sidebar`；移动抽屉仅使用 `mobileDrawerState` 保存 UI 焦点，项目/会话仍复用 `projectState`、`conversationState`，见 `app.js:87-114`。未发现第二套项目/会话 DOM 或存储。 |
| 窄屏项目/会话入口可达 | PASS（静态） | `index.html:11-32` 提供同一侧栏的移动入口、项目树、最近会话和历史按钮；`app.js:1576-1588` 复用既有项目/会话点击路径，`selectProjectContext`/`openConversationFromWorkspace` 不另建业务状态。 |
| 记忆入口可达 | PASS（静态） | 记忆导航仍在同一侧栏 `index.html:35-41`，导航点击由 `showView` 处理；移动侧栏委托点击后关闭抽屉并恢复入口焦点。 |
| 历史分页/滚动保持 | PASS（静态） | `app.js:1008-1043` 使用既有 `messageCursor`、`before` 游标和 `scrollHeight` 补偿；`app.js:1645-1651` 同时保留顶部滚动触发。失败路径有可操作重试按钮。 |
| 处理过程与 RAG 来源可达 | PASS（静态） | 处理过程在同一 assistant bubble 内并置于回答前，使用稳定 `step_id` 原位更新（`app.js:438-513`）；来源 renderer 使用按钮、`textContent` 和详情滚动（`conversation-research.js:89-139`，移动 44px 触控及详情滚动见 `styles.css:1875-1879`）。 |
| Esc、遮罩关闭、普通选择后的焦点恢复 | PASS | `app.js:116-135`、`1576-1588`、`1614-1618` 覆盖 toggle/关闭按钮/遮罩/Esc/选择后关闭；目标使用 `mobileDrawerState.restoreFocus`。 |
| dialog/浮动菜单关闭后的焦点恢复 | **FAIL — P1** | 移动新建项目点击在 `app.js:1596` 将 `restoreFocus` 保存为侧栏内的 `#new-project-button`，随后 `app.js:1585` 用 `closeMobileDrawer(false)` 将侧栏移出视口；`app.js:1609` 关闭 dialog 时仍聚焦该 off-canvas 控件。项目/会话菜单项在 `app.js:848` 先移除浮动菜单并收起抽屉，再进入 `openActionDialog`/`confirmAction`，`dialogState.restoreFocus` 可能捕获 body 或已断开菜单项。 |
| 触控目标、safe-area、软键盘、100dvh | **PARTIAL — P2** | safe-area、侧栏/聊天 `100dvh`、输入区高度与来源详情滚动已覆盖（`styles.css:1802-1882`）。但移动媒体查询只给项目/会话行、菜单、历史按钮、来源/重试等加 44px；`.new-chat`、`.nav-item`、`.project-tree-toggle`、项目树/最近会话菜单触发器仍沿用约 18–35px 的桌面 padding（`styles.css:8,139,143,162`），核心项目/记忆入口触控目标不一致。 |
| 无横向溢出、reduced-motion | PASS（静态） | `body`、`.main-area` 与移动 bubble 设置 overflow 防护（`styles.css:3,1867,1871`）；`prefers-reduced-motion` 关闭 processing running 动画（`styles.css:1796-1799`）。真实设备布局尚未 smoke。 |
| 桌面 Task09/Task10 行为无回归 | PASS（静态/合同） | Task09/Task10 前端最终报告均为 GO；本轮受影响前端合同 48 项全部通过。移动规则集中在 `@media (max-width:760px)`，桌面资源和 DOM 旧契约保留。 |
| 资源版本、XSS、DOM 契约 | PASS | 实际加载资源为 `app.js?v=32`、`styles.css?v=32`（`index.html:7-8,445-446`），旧 `v=30/v=31` 仅作为兼容标记；动态项目/会话/记忆/来源内容使用 `textContent`，回答 Markdown 经过 DOMPurify（`app.js:3020-3042`），相关旧合同与 Node renderer 合同通过。 |
| 重试不重复发送消息 | **FAIL — P1** | `app.js:1531-1538` 的 `appendUser:false` 只阻止再次追加 DOM user 节点；`app.js:1469-1475` 仍向同一 `POST /api/conversations/{id}/messages` 发送完整 content。该路由每次在 `backend/app/api/routes_conversations.py:363-365` 执行 `repo.create_message` 新建 user/assistant，因此会产生重复持久化消息；旧 retry 按 `querySelectorAll('.message.user').at(-1)` 取最后一个 DOM user，也可能重试错误的 turn。 |

## 最终 P0/P1/P2 清单

| 级别 | 数量 | 结论 |
|---|---:|---|
| P0 | 0 | 未发现会导致服务不可用、数据越权或不可逆重复写入的前端阻断项 |
| P1 | 0 | 最终复审未发现阻断项；上一轮焦点与重复 POST 风险均已清除 |
| P2 | 0 | 最终复审未发现需延期的前端缺陷 |

历史复审中的 P1/P2 仅保留作追溯，不代表当前代码状态；最终证据见“最终修复复审”表。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_frontend_task06_mobile_contract.py tests/test_frontend_task10_system_rule_contract.py tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_management_contract.py tests/test_frontend_task05_repair_contract.py --tb=short` | 0 | **49 passed** |
| `node --check frontend/app.js` | 0 | PASS |
| `node --check frontend/conversation-research.js` | 0 | PASS |
| `node tests/test_frontend_conversation_research.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_interaction.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_pdf.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0 | PASS |
| `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css tests/test_frontend_task06_mobile_contract.py` | 0 | PASS |
| 相关文件冲突标记检查 | 0 | 未发现 `<<<<<<<`、`=======`、`>>>>>>>` |

本轮未运行后端 pytest、全量回归、部署或真实 Chromium/手机尺寸 smoke，符合前端定向复审边界；GO 仅表示前端定向合同与静态复审通过，不替代主 Agent 的运行时验收。

## 主 Agent 后续动作

1. 由主 Agent/测试角色执行真实窄屏抽屉、键盘、dialog 焦点、软键盘、历史滚动、RAG 展开与桌面回归 smoke。
2. 在可用依赖环境完成 Spec022 收口所需的跨端/全量回归、部署验证和状态台账；本报告不替代这些收口门禁。

## 签字

- 前端 Reviewer：**GO（P0=0，P1=0，P2=0；前端定向复审通过）**
- 签字时间：2026-09-11（Asia/Shanghai）
