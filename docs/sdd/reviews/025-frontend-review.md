# Spec 025 前端评审（frontend/**）

> 评审方式：**代行，非独立评审**（hy3 子代理分派连续触发 429 限流，由主会话架构师按四项必守逐项核对）。

## 结论：GO

## 核对项（frontend-patterns 四项必守 + regression-guard）

| 项 | 结论 | 依据 |
|---|---|---|
| DOM 契约 | 通过。新元素全部在 `index.html` 的 composer 内声明，`app.js` 只操作既有 id；新 class 均在 `styles.css` 存在 | `index.html` composer 段；`styles.css` spec-025 分节；`tests/test_frontend_spec025_context_meter.py` 双向断言 |
| 资源版本号 | 通过。`app.js?v=33→34`、`styles.css?v=33→34` 同提交迁移；唯一的 v=33 硬断言已同步为 v=34；历史兼容注释保留，其它契约测试的 v=31/30 断言不受影响 | `index.html:8,494`；`tests/test_frontend_skill_tool_contract.py:83` |
| XSS | 通过。占比与状态文案只走 `textContent`，新增代码段内无 `innerHTML`（`sendButton` 的 `•••` 既有例外未扩大） | `app.js` Spec025 代码段；契约测试 `test_no_innerhtml_in_context_meter_code` |
| CSS 作用域 | 通过。新增选择器均为 spec-025 专属类，且 `.composer { flex-wrap: wrap; }` 的补充不污染其它视图 | `styles.css` spec-025 分节 |
| 按钮 in-flight 保护 | 通过。`contextState.inflight` + `disabled` + `try/finally` 复位，409 单独提示「压缩进行中」 | `app.js:compactConversationContext`；契约测试 `test_compact_button_has_inflight_guard` |
| 刷新时机（无常驻轮询） | 通过。只在 `openConversation` 与流式 `finally` 两处调用 `loadContextUsage()`；手动压缩后为**有上限**的跟随刷新（最多 6 次 × 2s，终止即停），用于收口「压缩中」中态，非常驻轮询 | `app.js`；契约测试 `test_refresh_only_on_load_and_after_message` |
| 可访问性 | 通过。`role="progressbar"` + `aria-valuemin/max/now`，`aria-valuenow` 与视觉宽度同源（同一个 `percent`）；状态区 `role="status" aria-live="polite"` | `index.html`；`app.js:renderContextUsage` |
| 边界处理 | 通过。`ratio` 渲染前 clamp 到 `[0,1]`；无会话时隐藏占比条；请求失败隐藏并保留可用输入 | `app.js:renderContextUsage` |

## 静态与运行时证据

- `node --check frontend/app.js` 通过。
- 契约测试 `tests/test_frontend_spec025_context_meter.py`：**12 passed**。
- 运行时（http://127.0.0.1:8000）：首页 HTML 含 `context-compact-button`；`/assets/app.js?v=34` 与 `/assets/styles.css?v=34` 均返回 200 且分别含 `context-usage` 与 `context-progress-fill`。

## 备注

- 本机 Ollama 无可用模型，未能完成"真实对话使占比上升并自动压缩"的端到端交互验证；该路径由后端 smoke（手动压缩 + 端点）与单元/契约测试覆盖，属环境限制，需在 Ollama 可用时补验。
