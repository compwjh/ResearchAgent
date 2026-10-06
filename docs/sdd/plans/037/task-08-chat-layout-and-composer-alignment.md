> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md)（Bug 6/7/8） ｜ 索引：[README](./README.md)
> 依赖：任务 01（与 Bug 1-5 已落地的前端改动共存）；当前状态：`已完成`

# 任务 08：对话布局三项——模型选择器靠右、聊天面板限高、侧边栏固定

## 一句话目标
纯前端三处布局/样式调整：模型选择器在 composer 底部行**靠右**；聊天面板**最多约两个屏幕高**、超出后内部滚动；页面滚动时**左侧栏保持不动**。

## 背景与前置条件（已核实到行，不要再重复排查）
- **Bug 6**：`frontend/styles.css:34` `.composer-footer{flex-wrap:wrap;justify-content:flex-end;gap:12px}` 已是右对齐；但 `frontend/index.html:149-151` 把 `.model-picker`（`#model-select`）放在 `.composer-footer` 的**第一个子元素**（spec-035 Bug5 移入时保留了原顺序），所以实际渲染在最左。
- **Bug 7**：`frontend/styles.css:11` `.chat-panel{min-height:510px;...}` **只有 min-height、没有 max-height**；`.messages{flex:1;overflow-y:auto}` 未被限高 → 内容增长把整页撑长。另有 `.workspace.has-started .chat-panel{min-height:calc(100vh - 162px)}`（约第 28 行区域）。
- **Bug 8**：`frontend/styles.css:5` `.app-shell{display:grid;grid-template-columns:238px minmax(0,1fr);min-height:100vh}`；`.sidebar`（第 6 行）**未设置 sticky** → 页面变长后随页面滚出视野。
- 窄屏既有规则（`styles.css:27`，`@media (max-width:760px)`）：`.app-shell{display:block}`、`.sidebar{display:none}`，移动端抽屉（`mobile-nav-toggle` 等）必须保持可用。
- 上下文占比模块（`#context-meter`）由本 spec Bug 1/任务 03 落地为「始终可见」，本次**不得回退**。

## 实施步骤（文件边界：`frontend/styles.css`、`frontend/index.html`）
1. **Bug 6**：给 `.composer-footer .model-picker` 加 `margin-left:auto`，使其在底部行靠右。**不要**改动 `#model-select` 的 id、DOM 位置顺序、事件绑定与模型联动逻辑。
2. **Bug 7**：为 `.chat-panel` 新增高度上限（约两个屏幕高度，用 `vh` 表达并扣除 topbar/内边距等既有占位），超出后由 `.messages`（已有 `overflow-y:auto`）内部滚动；保留既有 `min-height`，只加上限。限高加在正确层级，避免同时出现页面滚动条与内部滚动条。
3. **Bug 8**：让 `.sidebar` 在页面滚动时保持可见（`position:sticky` + 自身高度与内部滚动），侧边栏内容超高时在侧边栏内部滚动，不挤压主区；**窄屏（≤760px）行为保持不变**。
4. 改了 `styles.css` / `index.html` 就必须递增 `index.html` 中对应资源的 `?v=N`（当前 `app.js?v=53`、`styles.css?v=51`、`research-tasks.js?v=3`）。

## 边界与明确不做
- 只改 `frontend/**`，**不碰 `backend/**`**。
- 不改模型选择逻辑（列表来源、默认值、能力联动）；不把 `#model-select` 移回 `.chat-header`。
- 不动消息渲染、Markdown 解析、SSE 流；不改侧边栏导航项内容与菜单（Bug 5 成果保持）。
- 不引入新色系/新字体/新框架/构建步骤；限高优先纯 CSS，不引入 JS 计算高度。
- 不调整 `.topbar`、`.breadcrumb`。
- **不得让 `#context-meter` 回到「隐藏/不可见」状态**（Bug 1 契约）。

## 验收
- 底线布局下 `#model-select` 在 composer 底部行靠右，且 id/事件/联动不变。
- `.chat-panel` 有 `max-height` 且不小于 `min-height`（510px）；长对话下页面整体高度收敛、消息区内部可滚动。
- 页面滚动时 `.sidebar` 保持可见；窄屏下仍隐藏且抽屉可用；侧边栏内容超高时内部滚动。
- `#context-meter` 始终可见（回归 Bug 1）。
- `node --check` 通过；前端契约测试目录 `node --test frontend/contract-tests/*.test.mjs` 无回归（当前 21/21）。
- 资源 `?v=N` 已递增。
