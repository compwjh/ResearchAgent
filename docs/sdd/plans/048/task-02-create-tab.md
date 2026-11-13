# task-02 页面级 tab：新建地图入口 tab 化

> 关联：[spec-048](../../specs/048-literature-map-create-tab-and-refresh-icon.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`
> 产出性质：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 变更日志 / 状态台账 2026-11-13 条）。

## 1. 状态与一句话目标

`已完成`。把「新建地图」从左栏弹出的 `#literature-map-create-panel` 大卡片，改为与深度研究一致的页面级 `地图` / `新建地图` tab 切换，表单节点与交互语义不变。

## 2. 背景与前置条件

- spec-048 已 `已确认`；本任务在任务 01 之后、任务 03 之前。
- 现状：`frontend/literature-maps.js:1076-1079` 建 `createPanel`，`:1155` `listPanel.append(createPanel)`；`:1529-1539` 点 `#literature-map-new-button` 切 `hidden` 并在移动端先开列表抽屉；`closeCreatePanel()` 关闭并重置。
- 参考：`frontend/index.html:221-243`（tablist / tab / tabpanel）、`frontend/research-tasks.js:895-922`（`activateResearchTab()` 只改 `hidden` / `aria-selected` / `tabIndex`，不重建面板；`moveResearchTab()` 方向键）。

## 3. 数据、配置与接口

不适用：无后端、无接口、无数据模型变化。新增 DOM 契约：`#literature-map-main-tabs`（`role="tablist"`）、`#literature-map-tab-maps` / `#literature-map-tab-create`（`role="tab"`、`aria-controls`、`aria-selected`、`tabindex`）、`#literature-map-tabpanel-maps` / `#literature-map-tabpanel-create`（`role="tabpanel"`、`hidden`）。表单所有既有 `id` 保持。

## 4. 实施步骤与文件边界

只改 `frontend/literature-maps.js` 与 `frontend/literature-maps.css`（`index.html` 版本升留到任务 04）：

1. 在 `.literature-map-header` 之后插入 tablist；把既有 `grid` 包进 `#literature-map-tabpanel-maps`，把 `createPanel` 从 `listPanel` 移到新建的 `#literature-map-tabpanel-create`。
2. 实现 `activateMapTab(name, focus)`，沿用 `activateResearchTab()` 口径；`state.createPanelOpen` 与 tab 态同源。
3. 移除 header 的 `#literature-map-new-button` 及其点击处理；取消按钮 / 创建成功 / 离开视图统一切回「地图」tab 并聚焦；移动端不再触发 `openMobilePanel('list', ...)`。
4. 新增 `#literature-maps-view` 作用域限定的 tab 样式（对齐 `.research-main-tabs` 视觉；窄屏可换行、触摸目标 ≥44px）。
5. 三项自查：新增 class 与 CSS 一一对应、`?v=N` 留给任务 04、无 `innerHTML` / 无内联 SVG。

## 5. 子代理分派

`Task(frontend-dev)`，最小上下文 = spec-048「关键设计决定 1–3 / 边界 1–4,9」+ 本文件 + 上述文件行号；单次只改本任务 2 个文件；回传片段后由架构师读回真实文件校验；进展日志 `.codebuddy/agent-logs/spec-048/task-02/frontend-dev/`。

## 6. 边界与明确不做

不改表单字段 / 校验 / 提交流程，不改 header 其它作业按钮，不改全局 `.secondary-button`，不动 `app.js` / `styles.css`，不删既有测试；不放宽断言。

## 7. 验收、风险与回滚

- 静态契约：tab 结构属性齐全、默认「地图」选中、create panel 默认 `hidden`、`activateMapTab` 不重建面板。
- 浏览器：tab 往返后已填表单值保留；取消 / 创建成功回到「地图」tab；键盘 `←/→` 可切；窄屏 tab 可点、表单可滚动。
- 风险：移动抽屉逻辑依赖 `createPanel` 位于 `listPanel`；搬 DOM 后须复核 `openMobilePanel` / `closeMobilePanel` 不误触发。回滚：`git revert` 本任务 commit。

## 8. 产出物、执行结果与变更日志

待执行后填写：实现自测报告落 `docs/sdd/plans/048/runs/task-02/`，含真实命令与退出码。
