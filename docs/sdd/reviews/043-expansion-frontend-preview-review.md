# Spec 043 / Task 11 前端阶段一评审

日期：2026-10-28  
范围：仅当前未提交的 `frontend/**` 与 `tests/frontend/**`。未评审并行的 `backend/**` diff。评审边界为统一双方向预览、候选分页、跨方向选择与草稿恢复；批量确认禁用、阶段二重核/布局/批次进度视为已确认的阶段边界，不列为缺陷。

## 初次评审结论（JS32）

**Approve**（0 项 CRITICAL、0 项 HIGH；保留 1 项 MEDIUM，建议在 Task 11 内修复）。

## 初次评审发现（JS32，之后已修复）

- **[MEDIUM] 预览轮询的次数上限和退避被每次响应重置。** `frontend/literature-maps.js:2818` 在每次成功 GET 后都把 `side.pollAttempts` 归零；即使响应中的 `pagination.state` 仍为 `loading`，也会接着调用 `scheduleExpansionPoll()`。因此 `scheduleExpansionPoll()` 的 80 次停止条件和递增间隔无法生效，计数会一直回到 1，面板保持打开时会以约 1.2 秒间隔无限轮询。如果后台作业持续卡在 loading，浏览器会持续请求预览 GET。建议只在预览不再 loading/已进入终态时重置计数；loading 状态应保留递增次数，并在上限到达后显示停止自动读取、可手动重读的提示。

  依据：`frontend/literature-maps.js:2789-2796` 设置了 80 次上限和递增间隔；`frontend/literature-maps.js:2813-2820` 成功读取时无条件清零并在 loading 时重新排程。新增组件用例覆盖了即时 ready、手动续页和失败页重试，未覆盖一直处于 loading 的预览。

## 四项前端必守

| 项目 | 结果 | 核对依据 |
|---|---|---|
| DOM 契约 | PASS | 新增扩展类与 `frontend/literature-maps.css:169-186`、移动端规则 `:232-233` 对应；所有新增规则都以 `#literature-maps-view` 限定。复用的 `secondary-button` 与 `send-button` 已在 `frontend/styles.css` 定义。 |
| 资源版本 | PASS | `frontend/index.html:9` 使用 `literature-maps.css?v=20`，`:798` 使用 `literature-maps.js?v=32`；组件 fixture 也同步为 CSS20/JS32。检查范围内无旧 CSS19/JS31 引用。 |
| XSS | PASS | `frontend/literature-maps.js` 中没有 `innerHTML`；`createElement()`（`:170-174`）通过 `textContent` 写文本，候选标题、作者和提示由该路径渲染。 |
| CSS 作用域 | PASS | 本次新增桌面与移动端 CSS 规则均限定在 `#literature-maps-view` 内。 |

## 静态核对

- `node --check frontend/literature-maps.js`：通过。
- `git diff --check -- frontend/index.html frontend/literature-maps.js frontend/literature-maps.css tests/frontend`：通过。
- DOM/CSS、资源版本与文本写入方式：按上表核对通过。
- 本次没有运行测试或浏览器；开发交接报告记载的 14 个组件用例、8 个静态合同用例及 1 个环境权限 skip 未在本次重新执行。Chromium bootstrap 权限问题不作为代码缺陷证据。

## 初次评审摘要（JS32）

| 严重级别 | 数量 | 状态 |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | note |

**初次 Verdict: APPROVE** — 未发现阻塞合并的 CRITICAL/HIGH 问题；当时建议跟进上述轮询次数上限问题，当前状态见下方复核追加。

## 复核追加：MEDIUM 轮询问题已修复（JS33）

复核日期：2026-10-28。复核仅针对轮询计数、停止/恢复、旧 generation 防护与资源版本。

- **计数与停止：已通过。** `frontend/literature-maps.js:2792-2800` 每次自动轮询前递增并持久化计数，间隔由 1.2 秒递增、最高 4 秒；`frontend/literature-maps.js:2822-2827` 在仍为 loading 时不再清零，最多排程 80 次，非 loading 状态才重置。达到上限后，`frontend/literature-maps.js:3013-3020` 显示“自动读取已暂停”和“手动刷新状态”。
- **重开与显式恢复：已通过。** 每侧 `poll_attempts` 写入 owner/map/seed 草稿并在读取时限制在 0–80（`frontend/literature-maps.js:2687-2702, 2718-2732`）。达到上限后重开只 GET 当前 preview，不会自动续轮；手动刷新只发 GET 并重置预算（`:2880-2888`）。创建新 preview、加载更多、状态完成也会重置预算（`:2761`, `:2825-2827`, `:2860-2864`）。
- **旧 generation：已通过。** 关闭面板会清理两侧 timer 并增加 generation（`frontend/literature-maps.js:3151-3158`）；切 map 和打开其他 seed 都先关闭旧面板（`:2265-2269`, `:3100-3114`）；异步 GET 在写回前检查对象、generation、map、owner 与 active 状态（`:2673-2676`, `:2817-2818`）。新增窄用例覆盖持续 loading 后切 seed/map。
- **资源合同：已通过。** `frontend/index.html:798` 与组件 fixture `tests/frontend/fixtures/literature_map_component.html:913` 使用 JS33；CSS 保持 CSS20，精确合同同步更新。
- **验证证据：** 开发交接报告记录本修复后的精确前端命令 exit 0、10 passed（3.68s），包括持续 loading 停止/预算恢复与切 seed/map 停止旧轮询用例。本次复核未重新运行测试；另运行 `node --check frontend/literature-maps.js` 与对本轮前端 diff 的 `git diff --check`，均通过。

**当前复核结论：APPROVE；原 MEDIUM 问题已关闭，当前未留 CRITICAL/HIGH/MEDIUM/LOW 发现。**
