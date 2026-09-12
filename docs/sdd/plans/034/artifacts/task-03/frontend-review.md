# Spec034 Task03 前端评审报告

## 固定字段

- spec：034 — 会话式深度研究与真实子 Agent Runtime
- task：Task03 — 会话意图、Deep Research Skill 与 Intake
- reviewer：frontend-reviewer（当前执行 Agent）
- review_base：当前工作树相对 `1879fb3` 的前端实际差异
- review_scope：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`、`tests/test_frontend_conversation_contract.py`；只读评审
- conclusion：GO
- blocking_levels：P0=0，P1=0，P2=0

## 结论

GO。新增 SSE 类型已接入既有 assistant 消息流，字段 provenance、Skill 摘要、choice 白名单和安全 DOM 写入符合合同；资源版本同步升至 `v44`。历史 `intake/research_intake` projection 现在复用与实时事件相同的终态收口：完整参数且无 choices/missing 的面板折叠，clarification、active_conflict 或仍缺字段/待选择项的面板保持展开；普通消息不会附带 Intake，且后端 projection 使用 owner/字段/choice/Skill 白名单并不泄露 Skill 正文。

## Findings

### 已关闭：历史 Intake 投影与实时交互

- 后端现已在 `backend/app/api/routes_conversations.py:104-193,196-255,1162-1175` 将持久化 projection 以 owner 过滤、字段/choice/Skill ID 白名单和无正文摘要形式附加到 assistant 历史消息；前端 `frontend/app.js:1179-1180` 能读取 `intake/research_intake`。
- `tests/test_spec034_task03_contract.py:264-310` 已验证刷新恢复、普通消息无 Intake、字段 provenance 和 Skill body 不泄露；本项关闭。

### 已关闭：未完成 Intake 与 active conflict 保持展开

- 位置：`frontend/app.js:1408-1423`、`frontend/app.js:2542-2552`。
- `finalizeConversationIntake` 现根据 `clarification`、`active_conflict`、可见 missing 和 choice 判断 `needsUserAction`；`done=completed` 时待用户动作的面板保持展开，完整 Intake 才折叠。本项关闭。

### 已关闭：历史恢复后的完整 Intake 终态折叠

- 位置：`frontend/app.js:1179-1185`、`frontend/app.js:1325-1347`、`frontend/app.js:1412-1423`。
- 历史消息渲染先调用 `updateConversationIntake`，随后调用同一 `finalizeConversationIntake`；后端完整 projection（`status="intake", missing=[]`）因此折叠，`clarification`、`active_conflict`、可见 missing 或 choices 则由 `needsUserAction` 保持展开。实时/刷新展示状态一致，本项关闭。
- `tests/test_frontend_conversation_contract.py:219-226` 已覆盖历史 projection 使用 `updateConversationIntake` 与 `finalizeConversationIntake` 的同一终态规则。

## 已通过项

- **既有消息/SSE renderer 接线**：`KNOWN_CONVERSATION_EVENT_TYPES`、`appendConversationEvent` 和 `sendConversationMessage` 均识别 `skill_activation`、`intake`，面板挂在同一 assistant message，不新建独立消息流（`frontend/app.js:930,2407-2416,2503-2507`）。
- **Skill/字段摘要**：Skill 名称/简介/版本/快照摘要、字段名称/value、`source`、`confidence`、`confirmation_status`、missing 均映射到明确 CSS class；对象值通过 `JSON.stringify` 后 `textContent` 展示。
- **三选一白名单**：只接受 `modify_current`、`cancel_then_new`、`new_conversation`，按钮文本和 `data-intake-choice` 均来自固定映射，不信任服务端 label。
- **XSS/DOM 边界**：新增 Intake renderer 使用 `createElement`、`textContent`、`replaceChildren`，该 renderer 没有 `innerHTML`；动态 Skill、字段、问题和 choices 均不进入 HTML 字符串。既有 Markdown answer 的 `innerHTML` 仍走原 `renderMarkdown`/DOMPurify 路径，未由本次 Intake renderer 扩大风险。
- **终态/可访问性基础**：面板有 `aria-label`、`aria-busy`，toggle 有 `aria-expanded`，choice 使用 `aria-pressed`；CSS 提供 running/completed/failed 状态和折叠 body。
- **CSS/资源契约**：新增 `.conversation-intake*` class 均在 `frontend/styles.css` 定义；`frontend/index.html` 的 `app.js` 与 `styles.css` 实际 URL 同步为 `?v=44`，保留历史兼容标记。

## P0/P1/P2

- P0：无。
- P1：无。
- P2：无。未发现新增资源版本、CSS class、XSS 或 JavaScript 语法问题。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_conversation_contract.py` | 0 | 20 passed |
| 静态 DOM/XSS/version 检查：`rg` 核对 Intake renderer、`textContent`、新增 class、资源 `?v=44` 与现有 `innerHTML` 边界 | 0 | 通过静态匹配 |
| `git diff --check 1879fb3 -- frontend/app.js frontend/index.html frontend/styles.css tests/test_frontend_conversation_contract.py` | 0 | 通过 |
| `git diff --check 1879fb3 --` | 0 | 通过 |

## 复审边界

- 本次仅读取前端代码、后端历史响应契约、Spec/Task 文档并更新本报告；未修改业务代码、Spec 或状态台账，未 commit/push/merge/reset/stash/clean。
- 前端合同 pytest 为静态合同测试，未替代真实浏览器 SSE/刷新 smoke；历史完整/未完成/冲突的折叠结论由代码路径、合同测试和现有后端响应字段共同确认。
