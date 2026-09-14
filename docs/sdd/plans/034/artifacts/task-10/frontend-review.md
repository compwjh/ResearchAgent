# Spec034 Task10 前端最终评审报告

评审角色：frontend-reviewer（只评审 `frontend/**` 与前端合同测试）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：Spec034、Task10 计划、Task07/08/09 前端交付与最终复审、当前工作树；未修改业务代码，未 commit/push，未提前运行全量回归。

## 结论

**GO（前端代码评审通过）**。

当前前端没有发现 P0/P1 阻断：聊天与 Research Tab 共享 Session projection，审批成功后接回同一 Task/ProcessingTree SSE/报告管线；Task07 三级树的 upsert、乱序父子、终态屏障、滚动保护和同步失败态保持有效；Task08 报告 Artifact/通知接缝、XSS/URL 白名单和资源版本保持有效；Task09 真实 Session 标题、嵌套 plan Agent/Tool 摘要和旧入口清理保持有效。

但 Task10 的真实浏览器 smoke 前置尚未满足：`127.0.0.1:8000` 当前未启动，不能把 Fake-DOM/静态合同结果当作真实 UI 验收。该项属于运行环境阻塞，不构成当前前端代码 GO 的 P0/P1 缺陷；主 Agent/Tester 启动服务后仍必须补做完整 Smoke。

## P0/P1/P2 汇总

| 严重级别 | 数量 | 结论 |
|---|---:|---|
| P0/Critical | 0 | 通过 |
| P1/High | 0 | 通过 |
| P2/Medium | 1 | 非阻断，后续修复 |

### P2-01：Session-only 卡片快速切换存在异步选择竞态

证据：`frontend/research-tasks.js:1292` 和 `:1303` 的 `selectTask()` stale guard 使用：

```js
if (state.selectedTaskId !== taskId && state.selectedSessionId !== sessionId) return;
```

在计划批准前的 Session-only 列表中，`taskId` 为 `null`。用户快速先后点击两个 Session 卡片时，前一个请求只要满足 `state.selectedTaskId === null`，即使 `sessionId` 已切换，也可能继续写入旧详情/旧计划。该问题只影响快速连续选择、不会产生后端副作用，也不影响已 materialize Task 的常规路径，因此本轮记为 P2，不阻断 GO。

建议后续使用一次选择 token，或按是否为 Task/Session-only 分别要求对应 ID 同时匹配，再应用异步响应。

## 逐项复核

### 1. Research Tab / 聊天接缝

- `frontend/research-session-ui.js` 提供只读 `projectSession()`/`planField()`；聊天 `app.js` 和 Research Tab `research-tasks.js` 均调用该 canonical projection。
- 聊天按钮与 Tab 按钮都提交 `POST /api/research-sessions/{id}/commands` 的统一 `{command, subject_version, scope_json, idempotency_key}`；按钮双击由 loading/success 状态阻断，跨窗口竞争交由后端 CAS/幂等键处理。
- `app.js:1738-1743` 发布 `research-session-command-success`；Tab `research-tasks.js:1466-1477` 接收后调用 `mergeSessionCommandResult()`，批准产生 Task 时复用 `selectTask()`、报告加载和既有 SSE，而不是创建第二套 Task/SSE 状态模型。
- Research Tab 创建/列表只走 `/api/research-sessions`；普通会话旁旧 `research-conversation-action` 和旧创建旁路未发现。Task09 Final2 已验证真实 conversation 标题优先级与嵌套 `plan.work_items(_json)`/`capabilities(_json)` Agent/Tool 统计，本轮专项测试保持通过。

### 2. ProcessingTree / SSE / 刷新恢复

- Research Tab 的 `applyProcessingStepFrame()` 只把 `processing_step` envelope 送入共享 `ProcessingTree`；raw ResearchEvent 仍只进入事件时间线，不猜测树父子关系。
- `ProcessingTree` 支持 v1/v2、乱序子节点缓存、`source_event_id/node_key/step_id` 幂等别名、终态不可逆、`partial/cancelled/interrupted` 标签、`TRACE_PROJECTION_FAILED`/`trace_syncing` 和真实 `.research-column-body` 滚动容器；localStorage 展开状态与用户非底部阅读位置均保持。
- SSE 以 `after_seq` 重连；`processing_step` 不推进 raw event cursor，合成 terminal 不污染最后一个真实事件序号，符合 Task07 最终复审结论。

### 3. 报告 / Artifact / 通知

- `research-tasks.js` 与聊天报告投影均复用固定 Artifact 路径白名单；仅 `html` 追加固定 `?mode=inline`，Markdown/citation manifest 作为附件下载；外部 URL、已有 query 和恶意参数被拒绝。
- Markdown 报告在聊天与 Tab 均经 `marked → DOMPurify → DOMParser` 安全渲染；缺少依赖或解析异常时退回纯文本。
- 通知仅接受 `completed/partial/failed/waiting_approval/interrupted`，heartbeat/未知 kind/status/非法游标丢弃；列表与 SSE 均按 `event_seq` 去重，点击先调用 owner-scoped read API，再按 conversation/session/task 跳转。失败重试以 `failed` payload 的 `retryable/retry_attempt` 表达，不创建未注册的 `retry` kind。

### 4. XSS / ARIA / CSS 与资源版本

- `frontend/research-tasks.js`、`frontend/research-session-ui.js`、`frontend/processing-tree.js` 的新增动态研究字段使用 `textContent`/DOM API；本轮静态搜索未发现 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、`eval` 或新增 `javascript:` sink。
- Tree toggle 使用 `aria-expanded`/`aria-label`，叶节点标记 `aria-disabled`；处理、列表、通知、报告区域保留 `aria-live`/`role=status`/`aria-label`/`aria-busy`，Research Tab 导航关联 `aria-controls`/`aria-current`；`prefers-reduced-motion` 规则限定在 `#research-view`。
- `frontend/index.html` 当前资源版本为 `styles.css?v=48`、`app.js?v=48`、`research-tasks.js?v=2`、`research-session-ui.js?v=1`、`processing-tree.js?v=1`；兼容 marker 保留，未发现本轮新增未版本化脚本/CSS。

## 验证记录

| 检查 | 退出码/结果 |
|---|---:|
| `node --check frontend/app.js && node --check frontend/research-session-ui.js && node --check frontend/research-tasks.js && node --check frontend/processing-tree.js` | 0 |
| `node tests/test_frontend_processing_tree.js && node tests/test_frontend_spec034_task08.js && node tests/test_frontend_spec034_task09.js && node tests/test_frontend_conversation_research.js` | 0，全部 PASS |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task04_contract.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task09_contract.py` | 0，28 passed |
| `git diff --check -- frontend tests/test_frontend_spec034_task04_contract.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task09_contract.py` | 0 |
| XSS sink、资源版本、研究 CSS 作用域静态检查 | 0/无危险 sink，版本与作用域通过 |
| `curl -sS -o /dev/null -w 'root:%{http_code} bytes:%{size_download}\\n' http://127.0.0.1:8000/` | **7**，连接被拒绝；真实浏览器 Smoke 前置阻塞 |
| `ollama list` | 0；本机存在 `qwen3.8:27b-mlx` 等模型 |

本轮未运行后端 pytest、前端全量回归、真实浏览器/Ollama 端到端 Smoke；这些属于 Task10 后续收口步骤。

## 阻塞项与交接

1. 启动服务后补做真实浏览器流程：会话输入固定研究主题 → Skill/Intake → 真实 Planner → 前端批准 → Search Worker/目录 Tool → Evaluator/Critic/Synthesizer → 三级树 → 刷新/SSE 重连 → Markdown/HTML/manifest 下载与 HTML XSS 检查。
2. Smoke 需记录实际 `resolved_model/reasoning_effort`、Tool 名、`research-event:{task}:{seq}`、三级 ProcessingStep 与 Artifact ID；不能用 Fake-DOM 代替。
3. 非阻断 P2-01 可在后续前端维护中修复；本轮不修改业务代码。

## 评审交接

- 结论：**前端代码 GO；真实浏览器 Smoke 环境阻塞待补**。
- P0/P1：无。
- P2：1（Session-only 快速切换 stale guard）。
- 进展日志：`.codebuddy/agent-logs/spec-034/task-10/frontend-reviewer/20260915-013548.md`
