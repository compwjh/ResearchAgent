> 关联：[spec-025](../../specs/025-conversation-context-compaction.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04；当前状态：`已完成`

# Task 05 — 前端占比指示与手动压缩按钮

## 1. 状态与一句话目标

`已完成`。在输入框区域交付「上下文占预算百分比」指示与「一键压缩」按钮，含中态、失败提示与版本号同步。

## 2. 背景与前置条件

- Spec025「边界」中占比与按钮相关条目为唯一依据。
- composer 结构：`frontend/index.html:82-87` `.composer#chat-form > textarea#question + .composer-footer(.composer-tip, button#submit#send-button)`。
- 百分比条可复用先例：`app.js:3456-3470` `div.kb-progress[role=progressbar][aria-valuenow] > .kb-progress-fill`，CSS `styles.css:548-573`。
- 按钮先例：`app.js:3404-3419`（`disabled` + `try/finally` + `textContent` 回写）。
- 网络调用复用 `conversationFetch`（`app.js:346-358`）。
- 版本号 `?v=33`（`index.html:8,492`），测试硬断言在 `tests/test_frontend_skill_tool_contract.py:81-83` 等。

## 3. 数据、配置与接口

- `GET /api/conversations/{id}/context-usage` → `used_tokens / budget_tokens / ratio / segment_count / compaction_status`。
- `POST /api/conversations/{id}/compactions` → `job_id / status / trigger`；409 表示已有进行中任务。
- 刷新时机**只有两处**：加载会话后、每轮消息完成后。**不做常驻轮询**。

## 4. 实施步骤与文件边界

1. `index.html`：composer 区域新增占比指示容器与 `button#context-compress-button`，`role="status" aria-live="polite"`。
2. `app.js`：新增 `loadContextUsage()` 与 `compactContext()`；按钮 `disabled` + in-flight 保护 + `try/finally` 复位；`textContent` 写中态与结果文案。
3. 在「加载会话后」与「消息完成后」两个位置调用刷新；`ratio` 渲染前 clamp 到 `[0,1]`，`aria-valuenow` 与视觉宽度同源。
4. `styles.css`：新增类限定在本项目 composer 容器内，不污染全局。
5. **bump `?v=33 → ?v=34`**（`index.html:8,492`）并同步更新契约测试断言。

可观察结果：占比随消息增长而变化；点击压缩后按钮禁用、完成后占比下降；快速重复点击只发一次请求。

## 5. 子代理分派

- `frontend-dev`（hy3，64k）：单次只改一个前端文件；回传后架构师读回校验 DOM 契约与版本号。
- `frontend-tester`（hy3，32k）：只做契约与静态检查（`node --check` + grep），不跑后端 pytest。

## 6. 边界与明确不做

- 不做二次确认弹窗、不做逐条勾选、不做压缩程度选择。
- 不做常驻轮询、不新增 SSE 事件、不引入 EventSource。
- 动态文本只用 `textContent`，禁止 `innerHTML` 拼接（唯一既有例外是发送按钮的 `•••` 指示器，不得扩大）。
- 不改 RAG、论文、知识库等其它视图；不修改 `messages` 渲染逻辑。
- 不自行新增 CSS 全局选择器。

## 7. 验收、风险与回滚

- 验收：`node --check` 通过；新 class 在 `styles.css` 存在；`?v=34` 与测试断言一致；409 时提示"压缩进行中"且不重复请求；压缩失败时只提示失败，历史消息与输入框不受影响；`ratio` 越界不产生异常渲染。
- 风险：版本号 bump 会连带多个契约测试——必须同一次提交迁移所有断言（retro 2026-09-11 spec-022 教训）。
- 回滚：revert 前端三个文件与测试断言。

## 8. 产出物、执行结果与变更日志

- `index.html`：composer 内新增 `.composer-context`（占比条 + 文案 + `#context-compact-button`）与 `#context-status`（role=status/aria-live）；`app.js?v=33→34`、`styles.css?v=33→34`。
- `app.js`：Spec025 代码段（`renderContextUsage` / `loadContextUsage` / `compactConversationContext` / 有上限跟随刷新）；刷新点两处：`openConversation` 与流式 `finally`。
- `styles.css`：spec-025 分节（作用域限定 composer）。
- 测试：`node --check frontend/app.js` 通过；`tests/test_frontend_spec025_context_meter.py` → 12 passed；`tests/test_frontend_skill_tool_contract.py` 的 v=33 断言已同步为 v=34。
