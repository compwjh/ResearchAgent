> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# 任务 04：前端——审批卡片交互收口（两处渲染点）

## 一句话目标
非 pending 时**不渲染**批准/拒绝按钮，状态文案改中文映射，两处渲染点一并修复。

## 背景与前置条件
- spec-037 Bug 4。
- 渲染点 A：`frontend/app.js:2010-2014`（`.conversation-research-approval`）。
- 渲染点 B：`frontend/research-tasks.js:863-877`（`.research-session-approval`）。
- 现状缺陷：非 pending 时仍渲染按钮（仅 `disabled`），而 `research-session-command:disabled` 无禁用视觉样式 → 看起来可点；状态文案 `` `已${approval.status}` `` → 显示「已approved」。
- 已有中文映射参考：`frontend/research-session-ui.js:94` `{pending:'待处理', approved:'已批准', rejected:'已拒绝', declined:'已拒绝'}`。

## 实施步骤（文件边界：`frontend/app.js`、`frontend/research-tasks.js`，必要时 `frontend/styles.css`）
1. 两处均改为：`status === 'pending'` 时才 append 批准/拒绝按钮；否则**不创建按钮节点**（而非 disabled）。
2. 状态文案统一为中文映射，口径与 `research-session-ui.js` 一致（新增 `superseded`→已被新版本替代）。
3. 保留 `card.dataset.status` 着色钩子（`styles.css:197-198` 依赖 `data-status`）。

## 边界与明确不做
- 不改命令调用逻辑（`submitSessionCommand` / `approve_plan` / `decline_request` 等）与后端契约。
- 不改卡片下方「修改计划 / 取消研究」按钮组（不同语义，不在本任务范围）。
- 不新增端点。

## 验收
- 已 approved 的卡片在 DOM 中**不存在**批准/拒绝按钮。
- 状态文案为「已批准 / 已拒绝 / 已被新版本替代 / 待处理」之一，页面不出现 `已approved`。
- 两个视图（会话内研究面板、研究工作台）行为一致。
- `node --check` 通过；新增/更新契约测试锁定「非 pending 无按钮」。
