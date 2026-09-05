---
name: frontend-patterns
description: 本项目前端（原生 JS/CSS/HTML，无构建步骤，由 FastAPI 直接挂载）实现模式：DOM 契约、资源版本号、XSS、CSS 作用域、DOM 结构约定与常用验证命令。frontend-dev / frontend-reviewer / frontend-tester 必读。
---

# 前端实现模式

本项目前端是**纯静态资源**：`frontend/index.html` + `frontend/app.js` + `frontend/styles.css`，由 FastAPI 直接挂载，**没有构建步骤**，改完刷新即可生效。

## 必守四条（事故背景见 `regression-guard` skill）

1. **DOM 契约一致**：JS 渲染的 class/id ⇄ CSS 选择器必须双向 Grep 交叉核对。
2. **静态资源版本号**：改 `app.js` / `styles.css` 后，**必须**同步升 `index.html` 里的 `?v=N`。
3. **XSS**：用户输入只用 `textContent` / `input.value`，**禁止 `innerHTML` 拼接**。
4. **CSS 作用域隔离**：新增样式带视图前缀（如 `#models-view`），避免污染其他视图。

## DOM 结构约定

- 视图以 `<section id="xxx-view">` 之类容器切换，JS 按 id 挂载/显示。
- 列表项 class 命名要与 CSS 选择器逐字一致；**不要凭记忆写 class**，写完必须 Grep 核对。
- 事件绑定用 `addEventListener`，不在 HTML 里内联 `on*`。

## 常用验证命令

```bash
node --check frontend/app.js           # 语法检查
grep -n "?v=" frontend/index.html      # 确认版本号已随改动升级
grep -n "className\|classList" frontend/app.js   # 与 CSS 选择器交叉核对
cd /Users/wjh/ResearchAgent && git diff --check
```
