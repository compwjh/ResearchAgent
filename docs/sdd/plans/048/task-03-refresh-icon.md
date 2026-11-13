# task-03 刷新状态按钮图标化并迁入地图展示卡片

> 关联：[spec-048](../../specs/048-literature-map-create-tab-and-refresh-icon.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`
> 产出性质：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 变更日志 / 状态台账 2026-11-13 条）。

## 1. 状态与一句话目标

`已完成`。把「刷新状态」从顶部文字按钮移到画布面板头部工具区，改为无可见文字的转圈图标按钮，刷新语义不变。

## 2. 背景与前置条件

- 任务 02 已完成并读回校验（同一文件 `literature-maps.js` 串行落地，避免覆盖）。
- 现状：`frontend/literature-maps.js:969-973` 在 `.literature-map-header-actions` 建 `#literature-map-refresh-button`（文案「刷新状态」）；事件 `:1520-1523`；画布头部工具区 `:1165-1190` 已有 `icon-button literature-map-tool` 组。
- 图标参考：`frontend/literature-maps.css:448-452` `.literature-map-groups-fab-icon` 用纯 CSS 形状，不引入图标字体 / 内联 SVG。

## 3. 数据、配置与接口

不适用。DOM 契约：保留 `#literature-map-refresh-button`、`title="重新读取地图和作业状态"`、`aria-label="刷新状态"`；按钮移入 `.literature-map-canvas-head .literature-map-tools`；新增 `<span class="literature-map-refresh-icon">` 与旋转态 `is-spinning`；按钮内不得有可见文本节点。

## 4. 实施步骤与文件边界

只改 `frontend/literature-maps.js` 与 `frontend/literature-maps.css`：

1. 从 `headerActions` 移除 `refreshButton` 的创建，改在 `tools` 内以 `icon-button literature-map-tool` 创建；`bindEvents()` 保持接收同一节点引用（`renderShell` 传参调整）。
2. 用 CSS 绘制循环箭头图标（圆环 + 箭头，`::before` / `::after`），点击时加 `is-spinning` 做旋转反馈、请求结束移除；`prefers-reduced-motion` 下不做持续动画；`:disabled` 与 `:focus-visible` 沿用工具按钮三态。
3. 保持移动端 ≥44px 触摸目标，与既有工具按钮一致；不动全局 `.icon-button`。

## 5. 子代理分派

`Task(frontend-dev)`，最小上下文 = spec-048「关键设计决定 4–6 / 边界 5–6,9」+ 本文件 + 上述行号；单次只改本任务 2 个文件；回传片段由架构师读回校验；进展日志 `.codebuddy/agent-logs/spec-048/task-03/frontend-dev/`。

## 6. 边界与明确不做

不改刷新逻辑（`selectMap` / `loadMaps`），不改其它作业按钮，不改 `app.js` / `styles.css`，不用 `innerHTML` / 图标字体 / 内联 SVG，不放宽既有断言；`test_frontend_map_palette.py` 3 处 `#literature-map-refresh-button` 点击依赖保留 id。

## 7. 验收、风险与回滚

- 静态契约：按钮位于 `.literature-map-tools` 内、无文本、`aria-label` 保留、CSS 有转圈形状与 `is-spinning` 规则。
- 浏览器：点击图标 → 旋转反馈 + 状态刷新；悬停提示「刷新状态」；窄屏可见且 ≥44px；无文字残留。
- 风险：`test_frontend_map_header_actions_readability.py:239` 断言「刷新状态」文案需按新契约改写（任务 04 处理，不改松口径）。回滚：`git revert` 本任务 commit。

## 8. 产出物、执行结果与变更日志

待执行后填写：实现自测报告落 `docs/sdd/plans/048/runs/task-03/`，含真实命令与退出码。
