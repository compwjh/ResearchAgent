# Spec-048 前端代码评审报告

| 项 | 值 |
|---|---|
| 评审者 | `frontend-reviewer` |
| 角色 | 前端代码评审（只读） |
| 模型 | `hy4`（读自 `.codebuddy/agents/frontend-reviewer.md:6` 的 `model: hy4`） |
| 分派方式 | `Task(frontend-reviewer)` |
| 日期 | 2026-11-13 |
| Spec 状态 | 实施中 |
| 评审边界 | 仅 `frontend/**`（`literature-maps.js` / `literature-maps.css` / `index.html`）及随附 `tests/frontend/**` 静态契约；`backend/**` 交 `backend-reviewer`，不越界 |
| 最终结论 | **APPROVE** |

## 0. 事实来源与只读纪律

- **启动必读（按顺序）**：`.codebuddy/skills/progress-logging/SKILL.md`、`frontend-patterns/SKILL.md`（含 Project Addendum 四项 + 验证命令）、`regression-guard/SKILL.md`（Project Addendum 前端高频回归 1–4 条）、`coding-standards/SKILL.md`，以及 `.codebuddy/agents/frontend-reviewer.md`。用 `Glob .codebuddy/skills/**/SKILL.md` 确认技能真实路径共 19 份，未臆断路径。
- **改动全貌**：只读 `git diff HEAD -- frontend/literature-maps.js frontend/literature-maps.css frontend/index.html tests/frontend/`。
- **Read**：spec-048（边界 1–10 / 明确不做 / Gate 2 C1–C10）、`plans/048/runs/task-02|03|04/implementation.md`、`index.html`(:1-15 / :895-921)、`literature-maps.js`(:206-210 / :955-1039 / :1076-1091 / :1170-1230 / :1360-1391 / :1545-1626 / :1708-1762)、`literature-maps.css`(:583-616)、fixture、5 个改动测试 + 1 个新增测试全文。
- **执行命令**：`node --check frontend/literature-maps.js`（EXIT=0）、`grep -n "?v=" frontend/index.html`；双向 Grep（class ↔ CSS）、`@keyframes`、`innerHTML` / `<svg` / `@font-face` / `iconfont`、`literature-map-new-button`、`openMobilePanel('list'`、`skip` / `xfail`、`get_by_role` / `is_hidden`、对比度关键字。
- **纪律**：未写业务代码、未改测试 / spec / 台账 / 其它评审文档；未执行 git 写操作、push、合并；结论全部基于上述文件事实，附 `文件:行`。

## 1. 三项必查逐项结论（frontend-dev 三项自查口径）

| # | 必查项 | 结论 | 核心依据 |
|---|---|---|---|
| 1 | DOM 契约 | **PASS** | `literature-maps.js` 新增 5 个 class（`:997` `literature-map-main-tabs`、`:1001/:1009` `literature-map-main-tab`、`:1026/:1030` `literature-map-tabpanel`、`:1196` `literature-map-refresh-icon`、`:1582` `is-spinning`）均在 `literature-maps.css:590-611` 真实存在；`icon-button literature-map-tool`（`:1191`）为既有同族 class，定义于 `literature-maps.css:73-74`。反向：CSS 新增选择器全部由 `renderShell()` 的 `createElement` 渲染。 |
| 2 | 版本号 `?v=N` | **PASS** | `index.html:11` → `literature-maps.css?v=35`、`:903` → `literature-maps.js?v=48`；`:905` `app.js?v=77`、`:8` `styles.css?v=77` 未动；fixture `literature_map_component.html:8/:1135` 同步 35/48。 |
| 3 | XSS | **PASS** | `createElement` 第三参走 `node.textContent`（`literature-maps.js:209`）；全模块 `innerHTML` **0 命中**；唯一 `<svg` 字面串为 `:6699` `xml.includes('<svg')`（既有导出快照合法性校验，非 DOM 注入）；无 `@font-face` / `iconfont`；图标为空 `<span>` + CSS 形状。 |

## 2. 四项必守逐条 PASS/FAIL（项目附加约束，违反即 CRITICAL）

| # | 必守 | 结论 | 核对命令 / 命中行 |
|---|---|---|---|
| 1 | DOM 契约（双向） | **PASS** | Grep `literature-map-main-tabs\|literature-map-main-tab\|literature-map-tabpanel\|literature-map-refresh-icon\|is-spinning`：`literature-maps.js` 命中 `:997,998,1001,1006,1009,1014,1026,1027,1030,1031,1196,1553,1554,1582,1584`；`literature-maps.css` 命中 `:590-600,604-606,608-609,611`。一一对应。另 Grep `literature-map-tool\|.icon-button\|.literature-map-tools` → CSS `:72,73,74,316`。 |
| 2 | 版本号 `?v=N` | **PASS** | `grep -n "?v=" frontend/index.html` → `:11` `css?v=35`、`:903` `js?v=48`、`:905` `app.js?v=77`、`:8` `styles.css?v=77`；改 JS/CSS 后 live 版本确已递增。`node --check` EXIT=0。 |
| 3 | XSS | **PASS** | Grep `innerHTML\|<svg\|@font-face\|iconfont\|createElement('svg` in `literature-maps.js` → 仅 1 命中 `:6699`（导出校验字符串）。新增节点（`:997-1035,:1191-1198`）全部 `createElement` / `setAttribute` / `textContent`，无拼接。 |
| 4 | CSS 作用域 | **PASS** | `literature-maps.css:590-615` 全部新增选择器以 `#literature-maps-view` 开头；`@keyframes literature-map-refresh-spin`（`:607`）为全局 at-rule（非选择器），命名全仓唯一；未改全局 `.secondary-button` / `.icon-button`（git diff 仅末尾追加）。 |

三项必查与四项必守 **无 FAIL**。

## 3. 评审重点逐项 PASS/FAIL（带 文件:行）

### 3.1 DOM 契约细则

| 子项 | 结论 | 依据 |
|---|---|---|
| tab DOM 只在 `renderShell()` 内动态生成、role/aria/tabindex 齐全 | **PASS** | `renderShell()` 起于 `literature-maps.js:958`（`:1390` 收尾），tab DOM 位于 `:997-1035`：`role=tablist`(`:999`)+`aria-label`(`:1000`)、两个 `role=tab`(`:1004,:1012`)、`data-map-tab`(`:1005,:1013`)、`aria-controls`(`:1006,:1014`)、`aria-selected`(`:1007,:1015`)、`tabindex`(`:1008,:1016`)、两个 `role=tabpanel`(`:1028,:1032`)、`aria-labelledby`(`:1029,:1033`)、create 默认 `hidden`(`:1034`)。位置在 header(`:995`) 之后 / grid(`:1037`) 之前，grid 经 `mapsTabPanel.append(grid)`(`:1369`) 进入 maps panel。`index.html` 的 git diff 只改版本/marker，无静态 tab；深度研究 tablist 未动。 |
| `activateMapTab()` 只改属性不重建面板 | **PASS** | `literature-maps.js:1558-1577`：函数体仅 `setAttribute('aria-selected')`(`:1566`)、`tab.tabIndex`(`:1567`)、`panel.hidden`(`:1569`)、`state.createPanelOpen`(`:1571`)、`refs.createPanel.hidden`(`:1572`)、可选 `.focus()`(`:1575`)；无 `createElement` / `replaceChildren` / `innerHTML` / `appendChild`。键盘 ←/→/↑/↓/Home/End/Enter/Space(`:1603-1616`) 均经 `activateMapTab(..., true)` 同步 tabIndex。新增测试 `test_literature_map_tabs_and_refresh_icon.py:108-122` 用 `_function_body` 限定函数体逐字守此契约。 |
| `createPanel` 搬迁后所有 id / refs 不变 | **PASS** | `listPanel.append(createPanel)` → `createTabPanel.append(createPanel)`（`literature-maps.js:1180`）；`createPanel.hidden = true`(`:1103`)、`h3`「新建主题地图」(`:1104`) 保留；`Object.assign(refs, {...})`(`:1379`) 整行逐字未动（git diff 未触及）。取消 / 建图成功 / 离开视图三处 `closeCreatePanel()` 调用（`:1619,:3306,:8197`）统一经其末尾 `activateMapTab('maps', true)`(`:1758`) 切回，回到 maps 时 `createTabPanel.hidden` 与 `createPanel.hidden` 同为 true。 |
| 刷新按钮在 `.literature-map-canvas-head .literature-map-tools` 内、无可见文字、有 `aria-label="刷新状态"`、保留 id 与事件链 | **PASS** | `canvasPanel`(`:1182`)、`canvasHead`(`:1183`, class `literature-map-panel-head literature-map-canvas-head`)、`tools`(`:1190`)；`refreshButton` 两参数创建无文字(`:1191`)、`id`(`:1193`)、`title`(`:1194`)、`aria-label`(`:1195`)、空 `<span class="literature-map-refresh-icon">`(`:1196`) append(`:1197`)、`tools.append(refreshButton)`(`:1198`)；`canvasHead.append(canvasTitle, tools)`(`:1224`)、`canvasPanel.append(canvasHead)`(`:1225`)。事件链 `bindEvents(refreshButton, closeDetail)`(`:1385`) → `refreshButton.addEventListener('click'`(`:1581`) → `selectMap` / `loadMaps`(`:1585-1586`)。`literature-map-refresh-button` 全模块仅 `:1193` 一处定义。 |
| header 其余 5 个作业按钮未被动到 | **PASS** | `literature-maps.js:969-993`：continue / refresh-preview / open-saved-preview / stop-job / retry-job 五个按钮 id 齐全且逐个 `hidden = true`；事件绑定 `:1588-1592` 齐全。git diff 仅删除原 `refreshButton` / `newButton` 两段（旧 `:966-973`），未触碰上述五行。新增测试 `test_literature_map_tabs_and_refresh_icon.py:209-221` 逐字守 5 个 id + `hidden=true`。 |

### 3.2 `?v=N` 版本细则

| 子项 | 结论 | 依据 |
|---|---|---|
| live `literature-maps.js?v=48` / `literature-maps.css?v=35` | **PASS** | `index.html:903` / `:11`。新增测试 `test_literature_map_tabs_and_refresh_icon.py:43-47` 用严格正则 `js_live == ["48"]` / `css_live == ["35"]` 精确锁定（可失败，非恒真）。 |
| 两条旧版本 marker 在 HTML 注释内、不含 `<script` / `<link` 字面串、不在 `<head>` | **PASS** | `index.html:918-919`：`<!-- Spec048 compatibility marker: src="/assets/literature-maps.js?v=47" -->` / `... href="/assets/literature-maps.css?v=34" -->`，位于 `:920 </body>` 之前的末尾注释区；仅 `src=` / `href=` 纯属性片段。`test_literature_map_tabs_and_refresh_icon.py:58-76` 断言有且仅有 1 条、在注释内、不含标签字面串、且 `> head_end`。 |
| fixture 与精确断言同步 | **PASS** | fixture `literature_map_component.html:8/:1135` → 35/48；`groups_exports.py:52-53`、`mobile_contract.py:97-98`、`readability.py:27 MAP_CSS_VERSION=35`（用于 `:291,:318`）同步。冻结 `in INDEX`（`contract.py:28-29`、`groups_exports.py:18-19`、`mobile_contract.py:93-95`）与 `re.findall[-1]=="47"/"34"`（`groups_exports.py:54-55`）靠末尾 marker 兼容、逐字未改。 |
| `app.js?v=77` / styles.css 版本未动 | **PASS** | `index.html:905` / `:8`；`readability.py:28 APP_JS_VERSION=74`、`:30 STYLES_VERSION=75` 逐字未动；fixture `:7 styles.css?v=62` 未动。 |
| 未删测试 / 未 skip / 未 xfail / 未放宽容错 | **PASS** | git diff 无删除测试函数、无新增 `skip` / `xfail` / `approx` / 正则放宽；`readability.py` 全文 Grep `skip\|xfail\|pytest.mark\|approx\|tolerance` → 0 命中。既有 `_open_browser_or_skip`（`contract.py:125-129`、`groups_exports.py:58-62`）为浏览器不可用时降级、措辞「未将静态检查冒充通过」，git diff 未触及，非本次引入。`test_frontend_map_mobile_contract.py` Grep `skip\|xfail` → 0 命中。 |
| 三态 / 36px / 44px / 9.09:1 约束逐字保留 | **PASS** | `readability.py:148-154`（12px / 600 / 9px 14px / **36px** / nowrap）、`:157-161`（`color=#4a4560` / `background=#fff` 即 9.09:1 配色的逐字锁定）、`:164-178`（**hover / focus-visible / disabled 三态**）、`:184-199`（移动端 **44px** + gap 6px + flex-wrap）、`:212-229`（全局 `.secondary-button` 基类不污染）全部逐字未动（git diff 仅触及 `:27,31-35,235-284`）。C6 改写只发生在 `expected` 字典与 `pairs`，未触碰上述函数。 |

### 3.3 XSS 细则 — **PASS**

- 新增代码无 `innerHTML`：`literature-maps.js` 全文件 Grep 仅 `:6699` 命中 `<svg`（既有 `svgToPngBlob()` 导出校验），且 `contract.py:39` / `groups_exports.py:43` / 新增测试 `:162` 均断言 `assert "innerHTML" not in MODULE`。
- 无内联 SVG 字符串 / 图标字体：Grep `@font-face` / `iconfont` / `createElement('svg` → 0 命中。
- 图标为纯 CSS `<span>`：`literature-maps.js:1196` 空 span（无文本子节点），形状由 `literature-maps.css:604-606` 的 `:before` / `:after` 绘制。
- 动态文本一律 `textContent`（`createElement` 定义 `:209`），tab 文案「地图」「新建地图」为字面量。

### 3.4 反伪造 — **PASS**

- **实现与断言双向同步**：实现侧 `literature-maps.js` / `.css` 真实改动（tab DOM、activateMapTab、图标按钮、CSS 规则），测试侧 5 改 1 新增同步；非「只改测试不改实现」。
- **无恒真 / 静默失效断言**：新增测试 `_function_body`（`:23-37`）在找不到函数时 `assert start != -1` 直接失败、花括号未配对 `raise AssertionError`，符合 regression-guard 第 12 条（无 `if not candidates: return` 静默放行）；live 版本断言 `== ["48"]` / `== ["35"]`（`:46-47`）逐字严格；`activateMapTab` 断言逐字 fragment（`:110-122`）；刷新按钮「旧写法 `not in` + 新写法 `re.search`」双向（`:154-162`、`readability.py:259-269`）。
- **冻结断言靠 marker 兼容系 spec 既定设计**：spec 边界 7 / C8 明确要求「两条旧版本纯属性 marker 使 10+ 处 `in INDEX` 冻结断言继续通过；精确 live 断言与 fixture 内版本字符串同步到新值」。实测 `groups_exports.py:54-55` 的 `re.findall[-1]=="47"/"34"` 现取到 `:918-919` marker 旧值（非恒真，删 marker 即失败），并由新增 `test_live_asset_versions_are_exactly_bumped`（`:43-55`）补足 live 精确值覆盖，形成「旧冻结断言守 marker + 新精确断言守 live」双层。判定合规，不构成伪造。

## 4. Gate 2 强制约束 C1–C10 核对表

| 约束 | 结论 | 证据行号 |
|---|---|---|
| **C1** tab DOM 只在 `renderShell()` 生成、role/aria/tabindex 齐全、不动 index.html 静态 tab 与深度研究 tablist | **满足** | `literature-maps.js:958,997-1035,1369`；`index.html` git diff 无静态 tab |
| **C2** 闭包内 `activateMapTab()` 只改属性不重建、键盘 ←/→/Home/End 同步 tabIndex、不改 research-tasks.js | **满足** | `literature-maps.js:1552-1577,1593-1617`；`git diff` 不含 research-tasks.js；新增测试 `:108-122` |
| **C3** `createPanel` 迁入 `#literature-map-create-tabpanel`、id/refs/h3 不变、取消/成功/离开切回 maps、`:270,:284` 隐藏断言成立 | **满足** | `literature-maps.js:1103-1104,1180,1379,1619,1739-1758,3306,8197`；`contract.py:270,:284` `is_hidden()` 仍在 |
| **C4** 保留 refresh id/title、新增 `aria-label="刷新状态"`、移除可见文字、事件仍走 `bindEvents(...refreshButton...)`、可重复点击 | **满足** | `literature-maps.js:1191-1198,1385,1581-1587`；`refreshSpinTimer` clearTimeout(`:1583`) + 重设(`:1584`) |
| **C5** 图标 CSS `<span>` + `:before/:after`、无 innerHTML/SVG/字体、`is-spinning` 可观察、reduced-motion / :disabled 降级 | **满足** | `literature-maps.js:1196,1582`；`literature-maps.css:604-612`；Grep innerHTML/@font-face → 0 |
| **C6** `HEADER_ACTION_IDS` 移 new、expected/pairs 同步、刷新按钮改判「无文字 + aria-label」、三态/尺寸/对比度逐字保留 | **满足** | `readability.py:27,31-35,235-284`（新 3 条 `:259-269`）；`:148-199` 逐字未动；`APP_JS_VERSION`/`STYLES_VERSION`(`:28,:30`) 未动 |
| **C7** 7 处 `get_by_role('tab', name='新建地图')` 同步合理、`:270,:284` 隐藏断言仍在 | **满足** | `contract.py:140,249,263,277,291,310,320`（7 处均为「点击新建入口」定位；实现 `createTab` 为 `role=tab` + 文本「新建地图」，`literature-maps.js:1009,1012`，保留 button 定位将不可达）；`:28-29` 冻结断言、`:270,:284` `is_hidden()` 逐字未动。同步 7 处是 C7 本质（role 变更 → 定位对齐）的必要落地，非放宽、非 skip |
| **C8** js 47→48 / css 34→35、marker 末尾纯属性、`MAP_CSS_VERSION` 同步、app.js/styles.css 不动 | **满足** | `index.html:11,903,918-919`；`readability.py:27`；`groups_exports.py:52-55`、`mobile_contract.py:97-98`；新增测试 `:43-76` |
| **C9** 新增选择器带 `#literature-maps-view` 前缀、不改全局基类、media query 补齐 44px/滚动/reduced-motion、新建入口不触发列表抽屉 | **满足** | `literature-maps.css:590-615`；`@keyframes literature-map-refresh-spin`(`:607`) 全仓唯一（styles.css 10 个 @keyframes 无重名）；窄屏 tab 44px(`:599`)、表单滚动(`:600`)、图标 44px(`:614`)、reduced-motion(`:610-612`)、`:disabled`(`:609`)。`openMobilePanel('list', ...)` 仅 `:1722` 由 `refs.mobileListButton` 触发（地图列表入口），新建入口 tab click(`:1596-1602`) 不再调用 |
| **C10** 分派锁定、两处改动串行、`node --check` 与三项自查齐全、不越界后端 | **满足** | 本次 `git diff` 全为 `frontend/**` + `tests/frontend/**`，无 `backend/**`；task-02/03 报告记录 02→03 串行落地；`node --check` EXIT=0；三份 implementation.md 三项自查齐全 |

**C1–C10 满足 10 / 10 条**。

## 5. P0 / P1 / P2 缺陷清单

- **P0（阻断 / CRITICAL）：0 条。** 四项必守无 FAIL；无硬编码凭据、SQL 拼接、XSS、路径穿越、认证绕过。
- **P1（HIGH）：0 条。** DOM 契约、版本、XSS、C1–C10 全部满足；无 CRITICAL/HIGH 级问题。
- **P2（LOW / 观察项，非阻塞）：1 条。**

| 编号 | 级别 | 描述 | 依据 | 处置 |
|---|---|---|---|---|
| P2-1 | LOW / note | `is-spinning` 由固定 `700ms` 定时器移除，而 spec 关键设计决定 5 措辞为「请求结束移除」；`selectMap()` / `loadMaps()` 未与动画时长挂钩，旋转时长与真实请求时长不严格同步。 | `literature-maps.js:1581-1587`（`setTimeout(..., 700)` 在 `:1584`）；对比 spec `:34` | 不阻塞。边界 6 / C4 / C5 的可测契约均满足（新增测试 `test_literature_map_tabs_and_refresh_icon.py:168-186` 已守 `is-spinning` / reduced-motion / :disabled），属视觉反馈措辞偏差、非功能或安全缺陷。建议后续若 selectMap/loadMaps 返回 Promise，改在 `finally` 中移除 class。 |

## 6. Review Summary（ECC 统计表）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | info   |
| LOW      | 1     | note   |

Verdict: **APPROVE** — 无 CRITICAL / HIGH 问题；1 条 LOW 非阻塞观察项（P2-1），可在后续迭代处理，不影响本次合并。

## 7. 最终结论与签字

**最终结论：APPROVE**

判定依据（全部为文件事实）：三项必查 PASS / 三项必查无 FAIL；四项必守 PASS 4/4；C1–C10 满足 10/10；7 处 `get_by_role('tab', ...)` 同步必要且 `:270/:284` 隐藏断言仍在；`@keyframes literature-map-refresh-spin` 全仓唯一、所有新增选择器带 `#literature-maps-view` 前缀、reduced-motion 降级齐备；无 `innerHTML` / 内联 SVG / 图标字体；live `v=48` / `v=35` 与两条注释 marker、fixture、精确断言同步且 `app.js?v=77` / `styles.css?v=77` 未动；三态 / 36px / 44px / 9.09:1 配色逐字保留、未删测试 / 未新增 skip / 未 xfail / 未放宽容错；反伪造核对实现与断言双向同步、无恒真或静默失效断言。P0=0 / P1=0 / P2=1（非阻塞）。

- 评审者：`frontend-reviewer`
- 角色：前端代码评审（只读）
- 模型：`hy4`
- 分派方式：`Task(frontend-reviewer)`
- 签字：`frontend-reviewer (hy4)` · 2026-11-13

## 8. 产出与日志

- 本报告：`docs/sdd/reviews/048-frontend-review.md`（唯一评审产出新文件，Bash 单引号 heredoc 创建 + Read 读回校验）
- 进展日志：`.codebuddy/agent-logs/spec-048/task-04/frontend-reviewer/20261113-030433.md`

## 二次升版复核（2026-11-13）

> 复审追加章节（只读复核）。触发：`frontend-dev` 在 `docs/sdd/plans/048/runs/task-04/defect-fix.md` 修复 B1/B2 两处单端回归失败，并在 `version-bump.md` 因 CSS 内容变化将 `literature-maps.css?v=35 → v=36` 二次升版。本章不改写上文 APPROVE 原文，仅复核后追加。必读三份文档 + 只读 `git diff HEAD -- frontend/literature-maps.css frontend/index.html tests/frontend/` + 指定行段均已核对。

### 复核重点逐项 PASS / FAIL（带 文件:行）

| 复核重点 | 结论 | 依据 |
|---|---|---|
| **C8 二次升版**：live `literature-maps.css?v=36` 与 fixture / 精确断言一致（`MAP_CSS_VERSION=36`、`css_live==["36"]`、`groups:52`、`mobile:98`） | **PASS** | `index.html:11` → `css?v=36`（python 实算 head 区位置 806、live 出现恰 1 次、stray `v=35` 0 次）；fixture `literature_map_component.html:8` → `v=36`；`test_literature_map_tabs_and_refresh_icon.py:47` `assert css_live == ["36"]`、`:46` `js_live == ["48"]`；`test_frontend_map_header_actions_readability.py:27` `MAP_CSS_VERSION = 36`（供 `:291/:318` 用）、`:13` docstring 同步 v36；`test_frontend_map_groups_exports.py:52`、`:53` → `v=36`/`v=48`；`test_frontend_map_mobile_contract.py:97`、`:98` → `v=48`/`v=36`。`grep -n "?v=" frontend/index.html` 已核。 |
| **C8**：`literature-maps.js?v=48`、`app.js?v=77`、`styles.css?v=77` 未动 | **PASS** | `index.html:903` `js?v=48`、`:905` `app.js?v=77`、`:8` `styles.css?v=77` 逐字未动；`tabs_and_refresh_icon.py:49-50` 精确冻结 `app.js?v=77`/`styles.css?v=77`、`:52-55` 守首个 `styles.css?v=77` 不被 marker 污染；`readability.py:28 APP_JS_VERSION=74`、`:30 STYLES_VERSION=75` 逐字未动；fixture `:7 styles.css?v=62` 未动。python 实算 js `?v=` 仅 `['48','47']` 两处（live+marker），无新增。 |
| **C8**：未新增任何 INDEX marker，末尾两条 Spec048 marker（`v=47`/`v=34`）内容与位置未变，`re.findall(...)[-1]` 仍为 47/34 | **PASS** | `index.html:918` `<!-- Spec048 compatibility marker: src="/assets/literature-maps.js?v=47" -->`、`:919` `...href="/assets/literature-maps.css?v=34" -->` 内容与行号逐字未变，`</body>` 仍 `:920`。python 实算：js marker 位置 70981、css marker 位置 71060，均 `< body_end 71104` 且 `> head_end 11183`；`re.findall(...)[-1]` js=`47`、css=`34`（`['48','47']`/`['36','34']` 的末位）；`groups_exports.py:54-55` 的 `[-1]=="47"/"34"` 断言逐字未改。`tabs_and_refresh_icon.py:58-76` 守 marker「有且仅有 1 条 / 在注释内 / 不含 `<script`/`<link` 字面串 / 位于末尾注释区」逐字未改。 |
| **C8**：10+ 处 `in INDEX` 冻结断言继续靠 marker 兼容 | **PASS** | Grep `literature-maps\.(js\|css)\?v=(47\|34)` in `tests/frontend/` → 13 命中（`memory_return_global_contract.py:194-195`、`expansion.py:28-29`、`map_analysis.py:34-35`、`tabs_and_refresh_icon.py:72-73`、`task_j:182-183`、`button_affordance:204-206`、`mobile_contract.py:94-95`、`groups_exports.py:18-19`、`literature_map_contract.py:28-29`、`task_d:192-193`）。marker 恒为末次出现、`[-1]` 语义保持，冻结断言继续通过，删 marker 即失败（非恒真）。 |
| **C9 / B2 修复**：窄屏新增 `#literature-maps-view .literature-map-main-tabs { padding: 0 4px; }` 仍在 `#literature-maps-view` 作用域、位于 ≤760px media 块内 | **PASS** | `literature-maps.css:604` 带 `#literature-maps-view` 前缀，位于 `:598 @media (max-width: 760px) {` 与 `:606 }` 之间；`:590` 桌面基础规则（padding:4px）逐字未动，修复仅窄屏生效。 |
| **C9 / B2**：tab 按钮 `min-height:44px`、刷新图标按钮 ≥44px、创建表单 `overflow-y:auto` 未被破坏 | **PASS** | `literature-maps.css:599` `.literature-map-main-tab { min-height: 44px; ... }`；`:618-619` `@media (max-width:760px)` 内 `#literature-map-refresh-button { min-width: 44px; min-height: 44px; }`；`:605` `#literature-map-tabpanel-create { max-height: calc(100dvh - 200px); overflow-y: auto; ... }` 三条逐字保留。 |
| **C9 / B2**：未用 `overflow:hidden` 裁内容 / `transform` 造假 / `display:none` 隐藏 tab；未改全局 `.secondary-button` / `.icon-button` | **PASS** | 可靠重核（固定串，避开 ERE 不支持的负向前瞻）：`:598-620` 内 `overflow:hidden`/`translate`/`scale(`/`display:none` 零命中；`:605` 为 `overflow-y:auto`（可滚动，非裁切）。全文件 `transform` 仅 `:610 rotate(35deg)`（图标 ::before 形状）、`:612 @keyframes rotate(360deg)`（旋转动画）、`:343-347 translateX/Y`（既有移动端抽屉动画、git diff 未触及）——均非「位移/缩放造假 canvas 高度」，修复唯一手段为 `padding`（真实改变文档流盒高，defect-fix.md 实测 canvas.top 450→442）。全文件 `display:none` 命中均为 `[hidden]` 面板既有规则，Grep `main-tab.*display:none` 零命中。Grep 裸 `(^|非#前缀)\.(secondary-button\|icon-button)` in `literature-maps.css` → 0 命中；既有 `.secondary-button` 引用（`:272/:282/:287/:404`）全部带 `#literature-maps-view` 前缀。 |
| **B1 基线同步**：`BASELINE_COUNTS["literature-maps.js"] = 56` 且 `TOKEN` 正则与 `assert actual == expected` 逐字未改，属精确基线同步而非放宽松断言 | **PASS** | `test_frontend_button_affordance_contract.py:52` `= 56`、`:45-47` 追加 3 行根因注释；`:41 TOKEN = re.compile(r"(?<![\w.-])secondary-button(?![\w-])")` 逐字未改；`:107-110` `test_button_count_is_frozen` 的 `actual = len(TOKEN.findall(...))` / `assert actual == expected` 逐字未改；其余 3 基线 `:49-51`（28/29/11）逐字未动。git diff 无 skip / xfail / approx / 正则放宽 / 容差。 |
| **DOM / XSS 复核**：`literature-maps.js` 本轮未改、无 `innerHTML`、三项必查结论仍成立 | **PASS** | 必读 diff 命令特意排除 `literature-maps.js`：`defect-fix.md` / `version-bump.md` 边界均声明禁改 JS，`git diff HEAD -- frontend/literature-maps.js` 显示的全是首次 Spec048 实施（原报告 C1–C10 已审）的累积内容，非本轮增量。Grep `innerHTML` in `frontend/literature-maps.js` → 0 命中；`node --check` EXIT=0。三项必查：① DOM 契约 Grep `literature-map-main-tabs\|main-tab\|tabpanel\|refresh-icon\|is-spinning` → JS `:997-1031,:1196,:1553-1554,:1582,:1584`，CSS `:590-596,:604-605,:609,:613` 双向对应；② `?v=N` live css 已随内容变化升 v36（见 C8）；③ XSS 0 命中、动态文本仍 `textContent`/`createElement` 第三参。结论不变。 |
| **P2-1**（`is-spinning` 700ms 定时器）保持为已知非阻塞观察项 | **保持（不要求修复）** | `literature-maps.js:1584` `window.setTimeout(..., 700)` 逐字未动；本轮未引入新的 P2/P1/P0 缺陷，原报告 §5 P2-1 措辞与处置（建议后续在 Promise `finally` 移除 class）保持不变。 |

**复核重点逐项：全部 PASS，无 FAIL。**

### 四项必守逐条 PASS/FAIL（项目附加约束，违反即 CRITICAL）

| # | 必守 | 结论 | 核对依据（grep 命令与命中行） |
|---|---|---|---|
| 1 | DOM 契约（双向） | **PASS** | Grep `literature-map-main-tabs\|main-tab\|tabpanel\|refresh-icon\|is-spinning` ↔ `frontend/literature-maps.js` 命中 `:997,998,1001,1006,1009,1014,1026,1027,1030,1031,1196,1553,1554,1582,1584`；`frontend/literature-maps.css` 命中 `:590-596,604-605,609,613`。一一对应，无孤儿 class / 无孤儿 CSS 钩子。本轮未新增 / 修改任何 class 名。 |
| 2 | 版本号 `?v=N` | **PASS** | `grep -n "?v=" frontend/index.html` → `:11 css?v=36`、`:903 js?v=48`、`:905 app.js?v=77`、`:8 styles.css?v=77`；`literature-maps.css` 内容变 → live 由 v35 升 v36，fixture `:8` 同步；`node --check frontend/literature-maps.js` EXIT=0。 |
| 3 | XSS | **PASS** | Grep `innerHTML` in `frontend/literature-maps.js` → 0 命中；本轮 JS 未改、新增内容仅 CSS 注释 + `padding` 声明，无 DOM 拼接；用户输入仍走 `textContent`/`input.value`。 |
| 4 | CSS 作用域 | **PASS** | `:589-620` 新增块全部选择器以 `#literature-maps-view` 开头（`@keyframes literature-map-refresh-spin` 为全局唯一命名 at-rule 非选择器）；Grep 裸 `.secondary-button`/`.icon-button` → 0 命中；未污染既有页面全局标签选择器。 |

### C1–C10 是否仍 10/10

| 约束 | 结论 | 依据 |
|---|---|---|
| C1 tab DOM 只在 `renderShell()`、role/aria/tabindex 齐全、不动静态 tab | **满足** | JS 本轮未改；`literature-maps.js:997-1035` 未动；index.html 本轮仅 `:11` 版本字符串，无静态 tab |
| C2 `activateMapTab()` 只改属性不重建、键盘同步、不改 research-tasks.js | **满足** | JS 本轮未改；git diff 不含 research-tasks.js |
| C3 `createPanel` 迁入 tabpanel、id/refs/h3 不变、切回 maps | **满足** | JS 本轮未改；`:1180,:1379,:1758` 未动 |
| C4 刷新 id/title + `aria-label`、无可见文字、事件链、可重复点击 | **满足** | JS 本轮未改；`:1191-1198,:1581-1587` clearTimeout+重设未动 |
| C5 图标 `<span>`+`:before/:after`、无 innerHTML/SVG/字体、reduced-motion/:disabled 降级 | **满足** | CSS `:608-617` 未改；Grep `innerHTML`/`@font-face` → 0 命中 |
| C6 `HEADER_ACTION_IDS` 移 new、expected/pairs 同步、三态/尺寸/对比度逐字保留 | **满足** | `readability.py:27/:13` 仅版本字符串/docstring，`APP_JS_VERSION=74`/`STYLES_VERSION=75`(`:28,:30`) 与 `:148-199` 三态/尺寸/对比度逐字未动 |
| C7 7 处 `get_by_role('tab', ...)`、`:270/:284` 隐藏断言仍在 | **满足** | 首次实施已同步，本轮未触及；`contract.py` git diff 仅版本/marker 相关、隐藏断言逐字未动 |
| C8 js47→48 / css34→36 二次升版、marker 末尾纯属性、精确断言同步、app.js/styles.css 不动 | **满足** | 见上表 C8 四行；`MAP_CSS_VERSION=36`、`css_live==["36"]`、`groups:52`、`mobile:98`、marker 未动、`[-1]=47/34` |
| C9 选择器带 `#literature-maps-view` 前缀、不改全局基类、media 补齐 44px/滚动/reduced-motion | **满足** | `literature-maps.css:589-620`；B2 修复 `:604` 带前缀、位于 ≤760px 块；`:599/:605/:619` 44px/滚动/44px 逐字保留 |
| C10 分派锁定、串行、`node --check` 与三项自查齐全、不越界后端 | **满足** | 本轮 git diff 仅 `frontend/**` + `tests/frontend/**` + docs 报告，无 `backend/**`；`node --check` EXIT=0；defect-fix.md / version-bump.md 三项自查齐全 |

**C1–C10 仍满足 10 / 10 条。**

### P0 / P1 / P2 清单（复审后）

- **P0（CRITICAL）：0 条。** 四项必守 4/4 PASS；无硬编码凭据、SQL 拼接、XSS、路径穿越、认证绕过；二次升版未新增 INDEX marker、`[-1]` 冻结语义未破。
- **P1（HIGH）：0 条。** DOM 契约 / 版本 / XSS / C1–C10 全部满足；B1 为精确基线同步而非放宽松断言，B2 为真实 `padding` 修复而非伪造。
- **P2（LOW / 观察项，非阻塞）：1 条（沿用 P2-1，不要求修复）。** `is-spinning` 由固定 700ms 定时器移除（`literature-maps.js:1584`），旋转时长与真实请求时长不严格同步；属视觉反馈措辞偏差，非功能或安全缺陷。本轮未新增 P2。

### 最终结论与签字

**最终结论：APPROVE 保持（不打回）。**

判定依据（全部文件事实）：C8 二次升版 live `css?v=36` 与 fixture / `MAP_CSS_VERSION=36` / `css_live==["36"]` / `groups:52` / `mobile:98` 精确一致，`js?v=48`、`app.js?v=77`、`styles.css?v=77` 未动，未新增 INDEX marker、两条 Spec048 marker 内容与位置未变、`re.findall(...)[-1]` 实算仍 47/34、13 处 `in INDEX` 冻结断言继续靠 marker 兼容；C9/B2 修复规则带 `#literature-maps-view` 前缀且位于 ≤760px media 块内、tab 44px / 刷新 44px / 表单 `overflow-y:auto` 逐字保留、无 `overflow:hidden` 裁切 / `transform` 造假 / `display:none` 隐藏 tab、未改全局 `.secondary-button`/`.icon-button`；B1 基线精确同步 58→56 且 `TOKEN` 正则与 `assert actual == expected` 逐字未改；`literature-maps.js` 本轮未改、`innerHTML` 0 命中、`node --check` EXIT=0，三项必查与四项必守无 FAIL；C1–C10 仍 10/10；P0=0 / P1=0 / P2=1（P2-1 保持为已知非阻塞观察项）。上文 §1–§7 的 APPROVE 记录逐字保留，本章仅追加。

- 评审者：`frontend-reviewer`（复审子代理，只读复核）
- 角色：前端代码评审（只读）
- 模型：`hy4`
- 签字：`frontend-reviewer (hy4)` · 2026-11-13
- 复核产出：`docs/sdd/reviews/048-frontend-review.md`（末尾追加本章，`cat >>` 单引号 heredoc，Read 读回确认原文仍在）
- 进展日志：`.codebuddy/agent-logs/spec-048/task-04/frontend-reviewer-recheck/20261113-034200.md`
