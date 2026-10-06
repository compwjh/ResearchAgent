> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# 任务 05：前端——侧边栏三点菜单改真按钮

## 一句话目标
把死掉的装饰 `<span>···</span>` 换成带 `aria-haspopup="menu"` 的真按钮，弹出含「刷新模型列表」「打开模型库视图」的菜单。

## 背景与前置条件
- spec-037 Bug 5。
- `frontend/index.html:116`：`<span class="more">···</span>`，无事件、无 aria、无菜单（死的可供性）。
- 可复用既有实现：`frontend/app.js:2488`（会话项菜单）与 `2521`（项目项菜单）——真 `<button>` + `aria-haspopup="menu"` + `aria-expanded` + 点击处理。
- 不新增端点：「刷新模型列表」复用现有模型列表刷新能力；「打开模型库视图」复用现有视图切换函数。

## 实施步骤（文件边界：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`）
1. `index.html:116` 的 `<span class="more">` 改为 `<button class="icon-button more" id="profile-menu-button" type="button" aria-haspopup="menu" aria-expanded="false" aria-label="本地工作区选项">···</button>`。
2. 在 `app.js` 中按既有菜单模式绑定点击处理：展开/收起菜单、`aria-expanded` 同步、点击外部关闭。
3. 菜单项：①刷新模型列表（调用现有刷新函数并给出可见反馈）；②打开模型库视图（复用现有视图切换函数，目标视图名以代码中实际存在的为准）。

## 边界与明确不做
- 不新增后端端点，不改模型刷新接口契约。
- 不改会话/项目树的既有菜单实现。
- 不追求第三项菜单内容（两项起步）。

## 验收
- 三点菜单是 `<button>`，带 `aria-haspopup="menu"` 与 `aria-expanded`，点击有可见菜单反馈。
- 两个菜单项均可用（刷新后模型列表更新 / 视图切换生效）。
- `node --check` 通过；新增契约测试锁定「是 button 且非 span」。
