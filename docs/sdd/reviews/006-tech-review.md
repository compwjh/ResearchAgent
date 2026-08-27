# 技术评审 - 006 修复左侧"模型库"Tab 点击无反应

- 评审角色：开发主管（子模型 qwen3.8:27b，本地 Ollama）
- 评审对象：`docs/sdd/specs/006-fix-models-tab-no-response.md`
- 结论：**通过**

## 意见

1. **数据模型**：复用 `GET /api/health` 的 `{model, models:[...]}`，`model` 即当前选中，`models` 即列表数据源。零新增字段、零 schema 变更，风险极低。
2. **接口**：明确不新增后端端点，前端在视图切换时复用同一次（或缓存的）health 响应渲染列表，避免重复请求。若模型列表变化频率低（本地 Ollama），可考虑仅在切入模型库视图时 fetch 一次，无需轮询。
3. **模块拆分**：改动面收敛在纯前端两层——
   - **视图层**（index.html）：补一个 `#models-view` 容器（模型列表 + 占位），与现有 `#chat-view` 并列，用 `.active` class 控制显隐。
   - **逻辑层**（app.js）：给 `.nav-item` 统一加 `click` 监听（`preventDefault` 拦截原 `<a href="#models">` 锚点跳转，防抖动）；点击模型项时更新 `#model-select.value`、侧栏 `.model-label` 文本、列表高亮 class；切回对话视图时同步导航高亮。
   - 不触碰后端、不引第三方库，改动量预估 < 80 行（HTML + JS），一次 MR 可完成。
4. **模型与上下文预算**：
   - 开发（deepseek-coder:33b）：纯前端 HTML/JS 小改，33B 代码生成能力充足，单轮上下文放得下 index.html + app.js 相关片段，合理。
   - 测试（qwen3.5:9b）：验证 DOM 切换、联动赋值、空态、重复点击等 UI 行为，9B 足够，无需大模型。
   - 开发主管（qwen3.8:27b）：做本评审 + 任务拆解，规模匹配。
   - 未过度分配，预算合理。

## 实现注意点（给初级开发 Agent 的约束，非阻塞）

- 原 `<a href="#models">` 必须 `event.preventDefault()`，否则每次点击会触发 hash 跳转 + 页面微滚，违反"重复点击不抖动"边界。更优做法是将 `href` 去掉或改为 `href="javascript:void(0)"`，保留语义可访问性（加 `role="button"` + `tabindex="0"`）。
- 切换视图用 `classList.toggle('active')` 控制 `display:none / block`，**不要** `innerHTML` 重建节点，否则 `#chat-view` 内的消息 DOM 会被销毁，违反"切换不丢对话消息"。
- 模型列表渲染时给当前 `model` 字段对应的项加 `.current` class，而非用 inline style，方便测试断言。

综上，spec 质量满足 Bug-fix 级别交付标准，可以进入开发排期。
