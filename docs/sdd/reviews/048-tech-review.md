# Spec-048 技术评审（Gate 2 · 独立架构师评审）

| 项 | 值 |
|---|---|
| 评审者 | `architect`（架构师评审子代理） |
| 角色 | 架构师（Architect）— Gate 2 技术评审 |
| 模型 | `hy4`（读自 `.codebuddy/agents/architect.md:6` 的 `model` 字段） |
| 分派方式 | `Task(architect)` |
| 日期 | 2026-11-13 |

## 结论

**通过（附意见）** —— 等价于「通过」，非打回。

- **P0 = 0，P1 = 0**；无阻塞项。
- 纯前端改动，模块边界、复用口径、可测性、资源版本、样式作用域、单端分派六维度均基于代码事实核对通过。
- 「附意见」按 `SDD-GATE-CHECKLIST.md:73` 沉淀为 **§强制约束清单 C1–C10（10 条）**。本清单写在评审文档内，**不修改 spec**；下游只认落盘文档，与 spec 正文同等强制。

## 一、评审范围与依据（只读，非全项目扫描）

技能：`regression-guard`（`SKILL.md:497-525` 前端回归清单：DOM 契约 / 资源版本号 / XSS / CSS 作用域 / 禁止重复实现）、`frontend-patterns`（`SKILL.md:664-673` 原生 JS/CSS/HTML 约定）、`coding-standards`、`backend-patterns`。
事实行与静态契约同 `048-requirement-review.md` §一；型号真源 `.codebuddy/agents/architect.md:6`。

## 二、六维度逐项核对

### 2.1 数据模型 / 接口无变化

| 核对 | 结论 | 依据 |
|---|---|---|
| spec 声明 | 「无新增 / 无变更」：字段、状态取值域、localStorage、端点、请求/响应、错误码全部不变 | `spec:37-51` |
| 刷新语义 | 仍为 `selectMap(state.selectedMapId)` 或 `loadMaps()`，无新 `fetch` / 端点 / payload | `literature-maps.js:1519-1523`；`spec:47` |
| 改动面 | 仅 `renderShell()` 内 DOM 组装（`:958-1191`）、`bindEvents` 内入口绑定（`:1519-1546`）、CSS 局部样式；无 store/API 层 | `literature-maps.js:958-1003,1076-1191,1519-1546` |

结论：**成立**。无并发 / 事务 / 外键 / SSRF 面（纯前端 DOM 重组，无后端写入、无外发 URL）；`regression-guard` 后端条款 5–14 本次不触发。**通过**。

### 2.2 tab DOM 契约与 `activateResearchTab()` 复用可行性

| 核对 | 结论 | 依据 |
|---|---|---|
| 参考 tab 结构 | 深度研究为**静态 HTML** tablist：`role="tablist"` + 2×`role="tab"`（`aria-controls`/`aria-selected`/`tabindex`）+ 2×`role="tabpanel"`（`aria-labelledby`），create panel 默认 `hidden` | `index.html:221-243` |
| 文献地图视图结构 | `#literature-maps-view`（hidden）内仅 `#literature-maps-mount` 空挂载点，全部 UI 由 JS `createElement` 动态生成 | `index.html:739-743`；`literature-maps.js:958-1003,1155,1157-1191` |
| 复用函数可见性 | `activateResearchTab()` 定义在 `research-tasks.js` 模块闭包内（`RESEARCH_TAB_IDS`/`RESEARCH_TAB_ORDER` 私有 const），只切 `hidden`/`aria-selected`/`tabIndex`、`state.activeResearchTab`、可选 `focus`，**不重建面板** | `research-tasks.js:895-922` |
| createPanel 现状 | `.literature-map-create-panel` 挂 `listPanel.append(createPanel)`，含 h3「新建主题地图」与完整表单 id | `literature-maps.js:1076-1155`；`literature-maps.js:1346`（refs 指针） |

结论：**可行性成立，但「复用」须限定为「复用口径、不跨文件直调、不抽公共函数」**。
- `activateResearchTab()` 是另一视图闭包私有函数，`literature-maps.js` 无法直接调用；且抽公共函数会改动 `research-tasks.js`，触发 `index.html:906,913,915` 的 `research-tasks.js?v=` 冻结断言，属 `regression-guard:512`「禁止第二套 / 复用优先」的反面（不必要的跨视图扩散）。
- tab DOM 必须在本视图 `renderShell()` 内动态生成，不得改 `index.html:221-243`（那是深度研究视图，跨视图串改）、也不得在 `index.html` 新增静态 tab 节点。
→ 以强制约束 **C1 / C2 / C3** 固化。**通过（附意见）**。

### 2.3 刷新按钮保留 id 与 aria-label 的可测性

| 核对 | 结论 | 依据 |
|---|---|---|
| 现状 | `refreshButton.id='literature-map-refresh-button'`、文案「刷新状态」、`title='重新读取地图和作业状态'`；**无 `aria-label`** | `literature-maps.js:969-973` |
| 事件链 | `bindEvents(newButton, refreshButton, closeDetail)` 以参数传递，点击仍触发刷新 | `literature-maps.js:1519-1523` |
| 静态契约 | `HEADER_ACTION_IDS` 含该 id；`:239` 期望文案「刷新状态」；`:245` 校验 `id = '...'`；`:249-252` 逐字正则 `createElement('button','secondary-button btn-outline','刷新状态')`；`:266` pairs 绑定 `refreshButton` | `test_frontend_map_header_actions_readability.py:31-36,236-270` |
| 工具区既有范式 | `.literature-map-tools`（`:1165`）内 6 个 `icon-button literature-map-tool` 均 `setAttribute('aria-label', title)`，是可复用的「图标按钮 + 可访问名称」样式位 | `literature-maps.js:1165-1179` |

结论：**保留 `id` 即可维持 `:245,:259-260,:266` 的 id / 事件断言**；但「无可见文字」后，`:249-252` 的文案逐字正则必须按新契约改写，且 `aria-label="刷新状态"` 是**新增**而非「保留」（现状无该属性、title 值也不是「刷新状态」）。不得依赖 title 作唯一可访问名称。→ **C4 / C5 / C6**。**通过（附意见）**。

### 2.4 `?v=N` 升版 + 纯属性 marker 兼容性

| 核对 | 结论 | 依据 |
|---|---|---|
| live 版本 | `literature-maps.css?v=34`（head）、`literature-maps.js?v=47`（body 末） | `index.html:11,903` |
| 冻结断言 | `'/assets/literature-maps.js?v=47'`、`'/assets/literature-maps.css?v=34'` 精确 `in INDEX` | `test_frontend_literature_map_contract.py:28-29` |
| marker 注释区 | `:904-917` 为文件末尾注释区，全部是 `src=`/`href=`/`/assets/...?v=N` **纯属性片段**，无 `<script`/`<link` 字面串，不在 `<head>` | `index.html:904-917` |
| 版本常量 | `MAP_CSS_VERSION=34`、`APP_JS_VERSION=74`、`STYLES_VERSION=75` | `test_frontend_map_header_actions_readability.py:27-30` |

结论：**兼容方案成立**——升 `v=48`/`v=35` 后把两条旧值作为纯属性片段追加到 `:904-917` 注释区，可让 10+ 处 `in INDEX` 冻结断言继续通过，同时精确 live 断言与 fixture 内字符串同步新值，符合 `regression-guard:503`「改 app.js/styles.css 升 ?v=N」与 `frontend-patterns:667`。风险点：spec 边界7 未点名 `readability.py:27 MAP_CSS_VERSION` 是否用于 css 版本断言，须核对同步（C8）；`app.js?v=77`（`index.html:905`）/ styles.css 版本号按 `spec:74` 不动。**通过（附意见）**。

### 2.5 移动端与全局样式作用域

| 核对 | 结论 | 依据 |
|---|---|---|
| 作用域现状 | 所读全部选择器均以 `#literature-maps-view` 前缀限定，含注释「不碰全局 `.secondary-button`」 | `literature-maps.css:27-57,187-215,448-452`；`literature-maps.css:189-192` |
| 可读性 / 尺寸约束 | `.literature-map-job-actions button` min-height 36px、对比度 9.09:1、focus-visible；移动端 `:361-363` min-height 44px、可换行 | `literature-maps.css:193-215,361-363` |
| 移动端 create 面板 | `max-height:52dvh; overflow-y:auto`、form-grid 单列、`mobile-list-open` 显示 | `literature-maps.css:348-363` |
| 纯 CSS 图标先例 | `.literature-map-groups-fab-icon` 用 `::before/::after` 画形状，作用域带前缀 | `literature-maps.css:448-452` |
| 移动端误开抽屉 | 现状 newButton 点击含 `isMobileViewport() && openMobilePanel('list', newButton)` | `literature-maps.js:1529-1530` |

结论：符合 `regression-guard:505`「CSS 作用域」与 `frontend-patterns:669`。新增 tab / refresh-icon / `is-spinning` / `@keyframes` 必须沿用前缀（C9），移动端补齐 ≥44px 与 `prefers-reduced-motion`（`spec:34,60,63`），且新入口不得再触发 `openMobilePanel('list', ...)`。**通过（附意见）**。

### 2.6 跨端分派与上下文预算

| 核对 | 结论 | 依据 |
|---|---|---|
| 执行配置 | 五行齐全，型号读 agent 真源，架构师行填「自身」 | `spec:88-99`；`SDD-GATE-CHECKLIST.md:56-58` |
| 单端原则 | 明确「纯前端，只派 `frontend-dev`/`frontend-reviewer`/`frontend-tester`，不派后端、不跑后端 pytest 单端回归」，`tester` 为跨端验收总控 | `spec:91,98-99`；`SDD-GATE-CHECKLIST.md:45-46` |
| 上下文预算 | 最小上下文 = spec 数据模型(无)/接口(无)/边界/明确不做 + 目标文件路径；`literature-maps.js` 两处改动串行落地避免互相覆盖 | `spec:91,105` |
| 不存在的角色 | `junior-dev`/`pm`/`tech-lead` 明令不分派 | `spec:91`；`SDD-GATE-CHECKLIST.md:46` |

结论：**分派集合 = `frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester`（+ `doc-updater` 补产品步骤）**，与任务一致；无后端角色、无后端单端回归，符合省资源原则。**通过（附意见，C10）**。

## 三、安全 / 复用维度（`regression-guard`）

- **XSS**：图标用 CSS 形状 + `textContent`/属性，禁止 `innerHTML` 拼接（`regression-guard:504,512`）；spec `:72` 已锁死 → C5。
- **禁止第二套**：不得新建第二套 tab 框架跨视图共享、不得改动 `research-tasks.js`（`regression-guard:512`）→ C2。
- **DOM 契约**：新增 class（tab / refresh-icon / is-spinning）必须在 `literature-maps.css` 有对应选择器，且反向确认 JS 渲染（`regression-guard:502`）→ C1/C9。
- **资源版本号 / 作用域**：见 §2.4 / §2.5 → C8/C9。
- 后端条款（事务 / 并发领用 / SSRF / 来源可信 / 稳定错误体）本次无触发面，非「应该没问题」式豁免，而是基于「改动文件仅 `frontend/**` 且无网络/DB 写入」的事实判定（`spec:37-51,68`；`literature-maps.js:1519-1523`）。

## 四、关键决策

1. tab 化与图标化均为**视图内 DOM/样式重组**，不动数据模型 / 接口 / 表单语义 / 其它作业按钮。
2. tab 切换**复用「只改属性、不重建面板」口径，但新建本视图 `activateMapTab()`**；不跨视图调用、不抽公共函数、不改 `research-tasks.js`。
3. 刷新按钮 **`id` 与事件链保留不变**，`aria-label="刷新状态"` 按「新增」落地，移除可见文字，图标 CSS 绘制。
4. `?v=N` 升版用**末尾注释区纯属性 marker** 兼容冻结断言，精确断言真实同步，不放宽 / 不删 / 不 skip / 不 xfail。
5. 分派锁定前端四角色，单端静态契约核对 + 浏览器 E2E，`literature-maps.js` 两处改动串行。

## 五、阻塞项 / P0 / P1 判定

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 0 | 无数据 / 接口 / 安全 / 范围失控 |
| P1 | 0 | 5 项事实偏差均为「契约点名不全 / 措辞准确性 / 实施清单」，方向正确且 spec 已有「精确同步、不放宽」兜底 |
| P2（意见） | 5 | 已全部沉淀为 C1–C10 |

无阻塞项 → **不打回**。

## 六、强制约束清单（spec 级，C1–C10，共 10 条）

> 本清单为「通过（附意见）」的意见沉淀，**不修改 spec 原文**，但为下游 `frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester` 的硬约束；违反任一维度视为未满足 Gate 2 通过条件。

- **C1（tab DOM 生成位置 / 跨视图边界）**：tab（`role="tablist"` + `地图`/`新建地图` 两 `role="tab"` + 两 `role="tabpanel"`、`aria-controls`/`aria-labelledby`）必须在 `frontend/literature-maps.js` 的 `renderShell()`（`:958` 起）内以 `createElement` 动态生成，挂在 `#literature-maps-mount`（`index.html:743`）内 `.literature-map-app` 下、`.literature-map-header`（`:963`）之后 / `.literature-map-grid` 之前（对应 `spec:30`）。**不得**在 `index.html` 新增静态 tab 节点，**不得**改动 `index.html:221-243` 的深度研究 tablist。依据：`index.html:221-243,739-743`；`literature-maps.js:958-1003,1155,1157-1191`。
- **C2（切换实现 / 禁止第二套）**：在本视图闭包内新建 `activateMapTab()`，严格复用 `research-tasks.js:904-921` 的「只改 `hidden`/`aria-selected`/`tabIndex` + 可选 `focus`、面板不重建、表单值保留」口径；**不得**跨文件直接调用 `activateResearchTab()`（其为 `research-tasks.js` 私有函数）、**不得**抽取公共函数、**不得**改动 `frontend/research-tasks.js`（否则触发 `index.html:906,913,915` 的 `research-tasks.js?v=` 冻结断言）。键盘 `←/→`/`Home/End` 与 `tabIndex` 同步按 `spec:58` 实现。依据：`research-tasks.js:895-922`；`index.html:906,913,915`；`regression-guard:512`。
- **C3（createPanel 搬迁 / 隐藏断言）**：把 `createPanel`（`literature-maps.js:1076-1079`）从 `listPanel.append(createPanel)`（`:1155`）迁入新 `#literature-map-create-tabpanel`，表单节点、`h3`「新建主题地图」与所有 id（`:1081-1151`）、`refs` 指针（`:1346`）**逐字不变**；取消 / 创建成功 / 离开视图切回「地图」tab，`test_frontend_literature_map_contract.py:270,284` 的 `#literature-map-create-panel.is_hidden()` 断言继续成立。依据：`literature-maps.js:1076-1155,1346`；`test_frontend_literature_map_contract.py:270,284`；`spec:31,57`。
- **C4（刷新按钮 id / 可访问名称 / 事件链）**：保留 `id='literature-map-refresh-button'`（`literature-maps.js:971`），移除可见文字；**必须新增** `aria-label="刷新状态"`（现状 `:969-973` 无此属性、`title` 为「重新读取地图和作业状态」，spec `:34,:59`「保留」措辞按「新增」执行），**不得**依赖 title 作唯一可访问名称；事件继续走 `bindEvents(newButton, refreshButton, ...)` 的 `refreshButton` 参数（`:1519-1523`），不改 `selectMap`/`loadMaps` 语义、保证可重复点击。依据：`literature-maps.js:969-973,1519-1523`；`test_frontend_map_header_actions_readability.py:239,245,266`。
- **C5（图标实现 / XSS）**：图标为 CSS 绘制的 `<span class="literature-map-refresh-icon">` + `::before/::after`（参照 `literature-maps.css:448-452 .literature-map-groups-fab-icon`），与 `icon-button literature-map-tool` 同族（`literature-maps.js:1172-1179`）；**不得** `innerHTML` / 内联 SVG 字符串 / 图标字体；`is-spinning` 旋转态 class 可观察，`prefers-reduced-motion` 与禁用态不做持续动画，不影响按钮尺寸。依据：`literature-maps.css:448-452`；`literature-maps.js:1172-1179`；`spec:34,60`；`regression-guard:504`。
- **C6（readability 静态契约同步）**：`HEADER_ACTION_IDS`（`readability.py:31-36`）移除 `literature-map-new-button`；`test_four_header_buttons_keep_id_text_and_hidden_contract`（`:236-260`）的 `expected` 字典删除 new 条目、刷新按钮改判「无可见文字 + `aria-label`」，`:249-252` 的 `createElement('button','secondary-button btn-outline','刷新状态')` 逐字正则按新契约改写；`test_header_button_event_bindings_are_unchanged`（`:263-270`）的 `pairs` 同步移除 new→newButton；其余三态（`hidden`）/ 尺寸（min-height 36/44px）/ 对比度（9.09:1）约束（`literature-maps.css:193-215,361-363`）**逐字保留**，遵守「不改松 / 不删 / 不 skip / 不 xfail」。依据：`test_frontend_map_header_actions_readability.py:31-36,236-270`；`literature-maps.css:193-215,361-363`；`spec:62,73`。
- **C7（E2E 入口定位同步，spec 边界3 未点名之补录）**：`test_frontend_literature_map_contract.py:277` 的 `get_by_role('button', name='新建地图')` 因入口改 `role="tab"`（`spec:58`）必须同步为 `get_by_role('tab', name='新建地图')`；`:278-285` 的填写 / 提交 / 回 tab 流程保持可跑，`:270,284` 隐藏断言不变。依据：`test_frontend_literature_map_contract.py:277-285`；`spec:57-58`。
- **C8（版本升版 + marker 兼容）**：`literature-maps.js?v=47→v=48`（`index.html:903`）、`literature-maps.css?v=34→v=35`（`index.html:11`）；两条旧版本作为**纯属性片段** marker 追加到 `index.html:904-917` 末尾注释区（不放 `<head>`、不含 `<script`/`<link` 字面串），使 `test_frontend_literature_map_contract.py:28-29` 冻结断言与精确 live 断言同步；核对 `test_frontend_map_header_actions_readability.py:27 MAP_CSS_VERSION=34` 是否用于 css 版本断言，如是则同步 34→35；`app.js?v=77`（`index.html:905`）与 styles.css 版本号（`readability.py:28,30`）**不动**。依据：`index.html:11,903-917`；`test_frontend_literature_map_contract.py:28-30`；`test_frontend_map_header_actions_readability.py:27-30`；`spec:61,74`。
- **C9（样式作用域 / 移动端）**：所有新增 CSS（tab、`.literature-map-refresh-icon`、`is-spinning`、`@keyframes`）选择器一律以 `#literature-maps-view` 为前缀（沿用 `literature-maps.css:27-57,187-215,448-452` 现状），**不改**全局 `.secondary-button`/`.icon-button` 基础样式；移动端 media query（`literature-maps.css:348-363`）内补齐 tab 可点、表单可滚动、图标按钮 ≥44px 触摸目标、`prefers-reduced-motion` 降级；新建入口不再触发 `openMobilePanel('list', ...)`（`literature-maps.js:1530`）。依据：`literature-maps.css:27-57,187-215,348-363,448-452`；`literature-maps.js:1529-1539`；`spec:63,71`。
- **C10（分派 / 上下文预算 / 文档收口）**：分派集合锁定 `frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester`（+ `doc-updater` 补产品步骤），**不派** backend-dev/backend-reviewer/backend-tester、**不跑**后端 pytest 单端回归（`spec:91`；`SDD-GATE-CHECKLIST.md:45-46`）；最小上下文 = spec 边界(`:55-64`)/明确不做(`:68-76`)/目标文件路径，`literature-maps.js` 两处改动（tab DOM / 刷新图标）串行落地避免互相覆盖（`spec:105`）；确认后由 `doc-updater` 按 `spec:80` 补齐「等待条件 / 失败恢复 / 产物路径」，产品步骤 1–4（`spec:82-86`）不得省略；`node --check` 通过、三项自查（class↔CSS / `?v=N` 已升 / 无 `innerHTML`）齐全。依据：`spec:78-99,105`；`SDD-GATE-CHECKLIST.md:45-46,97`。

## 七、结论生效条件

本「通过（附意见）」以上述 C1–C10 为满足条件的硬约束；`frontend-reviewer` / `frontend-tester` 须逐条核对 C1–C10 落盘情况，`tester` 在 `048-acceptance-review.md` 按 spec 产品步骤 / 边界逐项判定。架构决策与跨端边界以本落盘文档为准。
