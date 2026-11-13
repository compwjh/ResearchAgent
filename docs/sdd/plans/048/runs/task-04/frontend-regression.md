# Spec-048 · task-04 · 前端单端回归报告（frontend-tester）

| 项 | 值 |
|---|---|
| 角色 | `frontend-tester`（ECC verification-loop 精神：前端静态契约核对 + 定向 / 全量前端 pytest） |
| Spec / Task | Spec-048 / task-04 |
| 日期 | 2026-11-13（执行时段约 03:04–03:08） |
| 核对范围 | `frontend/**`（`index.html` / `literature-maps.js` / `literature-maps.css` / `app.js` / `styles.css`）与 `tests/frontend/` |
| 边界纪律 | 未跑后端 pytest、未改任何业务代码、未执行 git / push / 合并；唯一新文件为本报告，另产出自身进展日志 |
| 依据 | `docs/sdd/specs/048-literature-map-create-tab-and-refresh-icon.md`（边界 1–10、Gate 2 强制约束 C1–C10、明确不做）、`docs/sdd/plans/048/runs/task-04/implementation.md`、`tests/frontend/test_literature_map_tabs_and_refresh_icon.py` |

## VERIFICATION REPORT

```
VERIFICATION REPORT
===================
Syntax:    PASS   node --check frontend/literature-maps.js EXIT=0（附加 app.js EXIT=0）
Contract:  FAIL   静态 DOM / ARIA / 版本 / CSS 作用域核对逐项命中、定向契约 12/12 PASS；
                  但全量回归中既有冻结契约 test_button_count_is_frozen 失败（56 vs 58，见 B1）
Version:   PASS   live js?v=48 / css?v=35；2 条 Spec048 纯属性 marker 位于末尾注释区；
                  app.js?v=77 / styles.css?v=77 未动；版本冻结断言全量继续通过
XSS:       PASS   literature-maps.js innerHTML = 0；无内联 SVG 字符串 / 图标字体；
                  动态文本沿用 textContent / input.value
Tests:     FAIL   .venv/bin/python -m pytest -q tests/frontend/ → 626 passed / 2 failed / EXIT=1（127.76s）
Diff:      0 个业务文件改动（本角色只读；产出仅本报告 + 进展日志）
Overall:   FAIL   阻塞项 2 个（B1 确定性契约未同步；B2 窄屏浏览器几何回归待复核）
```

> **判定口径**：§三 / §四 判定表是**静态契约与定向测试维度**的逐条结论（本角色职责边界）；命令 2 全量回归是**独立质量门**，其 2 项失败不因静态契约通过而抵消。`implementation.md` 记录的「44 passed / EXIT=0」是 5 个指定文件的定向结果，不能代表全量 `tests/frontend/`。本报告如实记录全量真实失败，不宣称全绿。

## 一、命令执行记录（真实输出摘要 / 退出码 / 通过数）

| # | 命令（均 `cd /Users/wjh/ResearchAgent` 后执行） | 真实输出摘要 | 退出码 | 通过数 |
|---|---|---|---|---|
| 1 | `node --check frontend/literature-maps.js` | 无输出（语法通过）；`node --version` → `v26.7.0` | **0** | —（语法检查，非计数） |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/` | `2 failed, 626 passed in 127.76s (0:02:07)`；FAILED 两条（见 §六） | **1** | **626 passed / 2 failed** |
| 3 | `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | **0** | —（布局检查，非计数） |
| 4 | `.venv/bin/python -m pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | `............ [100%] 12 passed in 0.34s` | **0** | **12 passed / 0 failed** |
| 5 | 定向静态核对（Grep / Read 真实文件，清单见任务） | 逐项命中，详见 §二 | —（只读核对） | — |

**命令 2 执行方式说明**：该全量回归耗时约 2 分钟，按任务预案用后台 `nohup` 执行，输出重定向 `/tmp/spec048_fe_full.log`、退出码写 `/tmp/spec048_fe_full.exit`（临时目录，不污染业务文件）；取回 `/tmp/spec048_fe_full.exit = 1` 为**真实退出码**，日志全文含进度条、两条 FAILURES traceback 与 short test summary。未与其它 pytest 并发（命令 4 先完成）。

**附加核对命令（归因 / 佐证，不替代命令 2 结论）**

| 命令 | 真实输出 | 退出码 |
|---|---|---|
| `node --check frontend/app.js` | 无输出（边界 10 佐证） | 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_button_affordance_contract.py::test_button_count_is_frozen` | `1 failed in 0.40s`（`56 == 58`，稳定复现、非 flaky） | **1** |
| Bash `grep -o 'secondary-button' ... \| wc -l` 等 | `SECONDARY_BUTTON_TOKENS=56` / `INNERHTML_COUNT=0` / `SPEC048_MARKERS=2` / `SCOPED_ICON_RULES=6` | 0 |

> 工具注记：Grep 工具 `outputMode=count` 两次返回 `Found 0 matching results`，与其 `content` 模式及 `Read` 结果不符，判为工具计数模式异常；相关数量改以 Bash `grep -c` / `grep -o | wc -l` 实测为准，此处如实披露。

## 二、定向静态核对（Grep / Read 真实文件）

| 核对项 | 实测命中 | 结论 |
|---|---|---|
| live 版本 `v=48` / `v=35` | `index.html:903` `<script ... literature-maps.js?v=48>`；`:11` `<link ... literature-maps.css?v=35>` | 通过 |
| 两条 marker 在注释内、无标签字面串 | `:918` `<!-- Spec048 compatibility marker: src="/assets/literature-maps.js?v=47" -->`、`:919` `href="...css?v=34"`；位于 `</head>` 之后、`</body>`(:920) 之前末尾注释区；两条均不含 `<script` / `<link`；`SPEC048_MARKERS=2` | 通过 |
| `activateMapTab` 无面板重建 | `literature-maps.js:1558-1577` 函数体仅 `setAttribute('aria-selected')` / `tab.tabIndex` / `panel.hidden` / `state.createPanelOpen` / `refs.createPanel.hidden` / `focus()`；体内无 `replaceChildren` / `createElement` / `innerHTML` | 通过 |
| 刷新按钮无文字 + `aria-label` | `:1191` `createElement('button', 'icon-button literature-map-tool')`（两参数、无文字）、`:1193` id、`:1194` title、`:1195` `aria-label="刷新状态"`、`:1196-1198` span `literature-map-refresh-icon` + `tools.append(refreshButton)`；`:1581-1586` 事件仍绑 `refreshButton`、`is-spinning` 旋转反馈、可重复点击 | 通过 |
| header 其余 5 按钮 id 与 `hidden` 仍在 | `:971/972` continue-search、`:976/977` refresh-preview、`:981/982` open-saved-preview、`:986/987` stop-job、`:991/992` retry-job，均为 `id` + `hidden = true` | 通过 |
| 新增 CSS 选择器作用域前缀 | `literature-maps.css:604/605/606/608/609/611` 六条 `literature-map-refresh-icon` 规则、`:590-600` tab 规则全部以 `#literature-maps-view` 开头；`SCOPED_ICON_RULES=6`；含 `::before/::after`、`@keyframes literature-map-refresh-spin`、`:disabled`、`@media (prefers-reduced-motion: reduce)`、≤760px `min-width/height:44px` 与 `overflow-y:auto` | 通过 |
| 无 `innerHTML` | `literature-maps.js` 实测 `INNERHTML_COUNT=0`；`literature-map-new-button` 与旧 `secondary-button btn-outline` 文字按钮 0 匹配；图标为纯 CSS 形状，无内联 SVG 字符串 / 图标字体 | 通过 |
| 补充：tab DOM / 键盘 / 挂载 | `:999-1033` `role=tablist/tab/tabpanel`、`data-map-tab`、`aria-controls`、`aria-labelledby` 齐全；`:1007-1016` 默认 maps 选中、create `tabindex=-1`；`:1034` `createTabPanel.hidden = true`；`:1603-1615` keydown 支持 `ArrowRight/Down`、`ArrowLeft/Up`、`Home`、`End`；`:1180` `createTabPanel.append(createPanel)`；C1 顺序 `header`(:995)→`mainTabs`(:1018)→`tabpanels`(:1035)→`grid`(:1037)；`index.html:8/905` `styles.css?v=77` / `app.js?v=77` 未动 | 通过 |

## 三、spec 边界 1–10 判定表

| 边界 | 判定 | 依据 / 备注 |
|---|---|---|
| 1 默认 maps tab 选中 / create panel hidden | **通过** | `:1007/1008` maps `aria-selected=true`/`tabindex=0`、`:1015/1016` create `false`/`-1`、`:1034` `createTabPanel.hidden=true`；命令 4 `test_maps_tab_is_selected_by_default_and_create_panel_hidden` PASS |
| 2 切 tab 不重建、表单值保留 | **通过** | `activateMapTab`(:1558-1577) 仅切属性 + focus、函数体无重建 API；命令 4 `test_activate_map_tab_only_toggles_attributes_and_never_rebuilds_panels` PASS |
| 3 取消 / 成功后回 maps tab、create panel hidden | **通过** | 命令 4 `test_close_create_panel_returns_to_maps_tab` PASS；全量 626 passed 内含 `test_frontend_literature_map_contract.py` 的 `:270/:284` 隐藏断言 |
| 4 键盘切 tab + 完整 ARIA | **通过** | keydown(:1603-1615) 四向 + Home/End 同步 `tabIndex`；`:999-1033` role / aria-controls / aria-labelledby 齐全；命令 4 tab 契约测试 PASS |
| 5 刷新按钮在画布工具区、无可见文字、title + aria-label、可重复点击 | **通过** | `:1191-1198`、`bindEvents`(:1579/:1581-1586)；命令 4 `test_refresh_button_is_textless_icon_button_in_canvas_tools` PASS |
| 6 CSS 转圈图标、无 innerHTML / SVG / 图标字体、`is-spinning`、≥44px | **通过** | CSS `:604-614`；`INNERHTML_COUNT=0`；命令 4 CSS 作用域 / 旋转 / reduced-motion / 44px 测试 PASS |
| 7 版本 `v=48`/`v=35`、marker 纯属性注释、冻结断言继续通过、精确断言同步 | **通过** | §二版本与 marker 命中；全量 626 passed 证明 10+ 处 `in INDEX` 与 `re.findall[-1]=47/34` 冻结断言继续通过；命令 4 版本测试 PASS。**备注**：另有 1 项非版本类源码计数冻结断言未同步（B1），不属本边界的版本冻结断言 |
| 8 readability.py 契约同步、三态 / 尺寸 / 对比度逐字保留 | **通过** | `implementation.md` 记录 `HEADER_ACTION_IDS` 移除 new、`expected` / `pairs` / `MAP_CSS_VERSION=35` 同步、三态 / 尺寸 / 对比度逐字未改；全量该文件仅 1 项非 C6 范围的计数冻结断言失败；命令 4 PASS |
| 9 ≤760px tab 可点 / 表单可滚动 / 不误开抽屉 / 图标 ≥44px | **通过（静态契约）** | CSS `:590-600`、`:599` tab `min-height:44px`、`:600` create panel `overflow-y:auto`、`:614` 刷新按钮 `min-width/height:44px`；新建入口走 `activateMapTab`→`loadCreateOptions`(:1615)，无 `openMobilePanel('list')`（`:1722` 为既有移动端列表按钮事件）。**备注**：全量 390px 窄屏浏览器用例 1 项失败（B2），非本边界四项静态要求 |
| 10 `app.js` / `styles.css` / 其它视图不受影响；`node --check` 通过 | **通过** | 命令 1 EXIT=0、附加 `node --check frontend/app.js` EXIT=0；`:8`/`:905` 版本号未动；未改 `backend/**` 与其它视图 |

**边界小计：10 / 10 通过（静态契约维度）**

## 四、Gate 2 强制约束 C1–C10 判定表

| 约束 | 判定 | 依据 / 备注 |
|---|---|---|
| C1 tab DOM 仅 `renderShell()` 内动态生成、header 之后 / grid 之前、不动深度研究 tablist | **通过** | `:997-1018` `createElement` 动态生成 `mainTabs`；顺序 `header`(:995)→`mainTabs`(:1018)→`tabpanels`(:1035)→`grid`(:1037)；`index.html` 无静态 tab；未动 `#research-main-tabs` |
| C2 本视图闭包 `activateMapTab()` 只切属性、键盘同步、不跨文件直调、不改 `research-tasks.js` | **通过** | `:1558-1577` 只改 `aria-selected`/`tabIndex`/`hidden`+`focus`；`:1603-1615` 键盘同步；无 `activateResearchTab` 调用 |
| C3 `createPanel` 迁入 create tabpanel、节点 / id / refs 不变、取消 / 成功回 maps tab | **通过** | `:1180` `createTabPanel.append(createPanel)`；`:1101-1104` id / `h3`「新建主题地图」保留、`:1379` refs 含 `createPanel`；`closeCreatePanel`→`activateMapTab('maps', true)`；全量隐藏断言通过 |
| C4 保留 refresh id / title、新增 aria-label、移除可见文字、事件链与刷新语义不变 | **通过** | `:1193-1195`、`:1191` 两参数无文字；`:1579` `bindEvents(refreshButton, closeDetail)`、`:1585-1586` `selectMap` / `loadMaps` 语义不变 |
| C5 CSS `<span class="literature-map-refresh-icon">` + 伪元素、无 innerHTML / SVG / 图标字体、`is-spinning` 与降级 | **通过** | `:1196` span、CSS `:604-612`；`is-spinning`(:608)、`:disabled`(:609)、`prefers-reduced-motion`(:610-612) 不做持续动画 |
| C6 `HEADER_ACTION_IDS` / `expected` / `pairs` 同步、三态 / 尺寸 / 对比度逐字保留、不放宽 | **通过** | `implementation.md` 与命令 4 已核；readability.py 指定文件全量通过（除 1 项超出 C6 点名范围的计数冻结断言，见 B1）；三态 / 尺寸 / 对比度逐字保留、无 skip / xfail |
| C7 `get_by_role('tab', name='新建地图')` 同步、填写 / 提交 / 回 tab 流程可跑 | **通过** | `implementation.md` 记录 7 处定位同步；全量 626 passed 内 `test_frontend_literature_map_contract.py` 浏览器用例真实跑通、无 skip |
| C8 版本 `47→48` / `34→35`、marker 放末尾注释区、`MAP_CSS_VERSION` 同步、app.js/styles.css 不动 | **通过** | §二命中；`:918-919` marker 不在 `<head>`、无标签字面串；`MAP_CSS_VERSION=35`；`:8`/`:905` 未动；命令 4 版本测试 PASS |
| C9 新增 CSS 前缀 `#literature-maps-view`、不改全局基础样式、media query 补齐、不误开抽屉 | **通过** | `SCOPED_ICON_RULES=6` 且 tab 规则全部带前缀；全局 `.secondary-button` / `.icon-button` 未改；`:599-600`、`:610-614` media query；新建入口无 `openMobilePanel('list')` |
| C10 分派锁定前端角色、不跑后端单端回归、两处改动串行、`node --check` 与三项自查齐全 | **通过** | 本次仅前端静态核对与 `tests/frontend/` pytest，未跑后端 pytest、未派后端角色、未执行 git / push / 合并；命令 1 与 class↔CSS / `?v=N` / 无 innerHTML 三项自查齐全 |

**约束小计：10 / 10 通过（静态契约维度）**

## 五、命中项（Syntax / Contract / Version / XSS）

- **Syntax**：`node --check frontend/literature-maps.js` EXIT=0；附加 `app.js` EXIT=0；新增测试文件由命令 4 真实收集执行 12 项，无语法 / 收集错误。
- **Contract（静态部分）**：`literature-map-main-tabs` / `literature-map-main-tab` / `literature-map-tabpanel` / `literature-map-refresh-icon` / `is-spinning` / `literature-map-tool` 均在 JS 被渲染且在 CSS 有定义（正向 + 反向核对）；tab ARIA / 键盘 / 挂载位置、刷新按钮无文字 + aria-label、header 5 按钮 id + hidden、createPanel 迁移逐项命中；命令 4 `12 passed`。
- **Version**：live `v=48` / `v=35`，2 条旧值纯属性 marker 在末尾注释区，`app.js?v=77` / `styles.css?v=77` 未动，冻结断言全量继续通过。
- **XSS**：`innerHTML` 0 次，图标纯 CSS 形状，动态文本沿用 `textContent` / `input.value`，无内联 SVG 字符串 / 图标字体。

## 六、阻塞项清单（2）

- **B1（确定性、由本次改动引入的契约未同步）** — `test_frontend_button_affordance_contract.py::test_button_count_is_frozen` 失败：`literature-maps.js: 56 secondary-button tokens, expected 58`（`:107`，`assert 56 == 58`）。`BASELINE_COUNTS["literature-maps.js"] = 58`（`:49`）未随源码同步；实测 `secondary-button` 恰为 56（-2 对应移除的 header「新建地图」与「刷新状态」两个 `secondary-button` 文字按钮）。单独复跑 `1 failed in 0.40s` / EXIT=1，稳定复现、非 flaky。该文件正是 `implementation.md` §五.2 自述「未纳入本次 pytest 5 文件」的冻结断言文件之一。违反 spec「明确不做：不放宽 / 不遗漏既有断言」的闭合要求（应同步精确基线为 56，不靠 skip / xfail / 正则放宽）。**本角色只读，不修改；需开发 / 主会话处理。**
- **B2（窄屏浏览器几何回归，待复核）** — `test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]` 失败：`assert 144 >= 150`（`:237`，390px 窄屏 `visibleMap.height=144`）。Playwright 真实浏览器几何断言，差 6px；疑与新增 tab 行占用垂直空间或既有窄屏渲染波动相关。本角色禁改业务文件 / 禁 git，无法跑改动前基线比对，如实列为待复核；不因静差 6px 而判为通过。

> 除上述 2 项外，命令 2 全量 `tests/frontend/` 的其余 **626 项通过**；命令 1 / 3 / 4 均 EXIT=0。

## 七、结论

**FAIL**

理由：命令 2 全量前端单端回归真实退出码 **1**、`626 passed / 2 failed`，存在 2 个阻塞项（B1 确定性契约未同步、B2 窄屏几何回归待复核）。静态契约维度（Syntax / Version / XSS、DOM 契约、边界 1–10、C1–C10）逐项命中且定向测试 `12 passed`，但**全量质量门未通过**，按任务「不得宣称全绿」要求如实判 FAIL。B1 明确由本次改动引入（源码 token 数变化未同步冻结基线），不得因 `implementation.md` 的定向 44 passed 而抵消。建议开发同步 `BASELINE_COUNTS["literature-maps.js"]` 至真实值后重跑全量，并复核 B2 窄屏布局；本报告不替代任何修复。

## 八、签字

`frontend-tester` · 2026-11-13

产出文件：`docs/sdd/plans/048/runs/task-04/frontend-regression.md`（唯一新文件）
进展日志：`.codebuddy/agent-logs/spec-048/task-04/frontend-tester/20261113-030410.md`

## 复审结论（修复 + 二次升版后，2026-11-13）

| 项 | 值 |
|---|---|
| 角色 | `frontend-tester`（复审子代理，ECC verification-loop 精神：只读复核 + 末尾追加） |
| 性质 | **集中复审**；原 FAIL 记录保留、本次为集中复审、不翻案 |
| 依据 | 本报告 §一–§八 原始 FAIL（626 passed / 2 failed / EXIT=1）、`defect-fix.md`、`version-bump.md`、只读 `git diff HEAD`、6 条真实命令 |
| 边界 | 只做只读复核 + 本末尾追加章节；未改业务代码 / 测试 / spec / 台账 / 其它报告正文；未跑后端 pytest；未执行 git / push / 合并 |
| 日期 | 2026-11-13 |

### 一、6 条命令真实输出摘要 / 退出码 / 通过数

| # | 命令（均 `cd /Users/wjh/ResearchAgent` 后执行） | 真实输出摘要 | 退出码 | 通过数 |
|---|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/frontend/` | `628 passed in 128.09s (0:02:08)`；后台 nohup + `/tmp/spec048_recheck_full.exit` 取回**真实**退出码 | **0** | **628 passed / 0 failed** |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_button_affordance_contract.py::test_button_count_is_frozen` | `1 passed in 0.36s` | **0** | 1 passed |
| 3 | `.venv/bin/python -m pytest -q 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]'` | `1 passed in 1.35s` | **0** | 1 passed |
| 4 | `node --check frontend/literature-maps.js` | 无输出（语法通过） | **0** | —（语法检查） |
| 5 | `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | **0** | —（布局检查） |
| 6 | 静态复核（python 实算 + 只读 diff + Grep/Read） | 各项命中，见 §二 | **0**（脚本） | —（静态核对） |

> 附加佐证（非 6 条命令之一）：`.venv/bin/python -m pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py` → `12 passed in 0.30s` / EXIT=0（CSS 作用域 / ≥44px 触摸目标 / marker 纯净性 / `[-1]` 断言）。
> 命令 1 后台启动调用的工具回显「命令执行超时」仅为该启动动作的等待提示，进程 PID 52842 真实存活并写出日志与 `.exit=0`；本结论以 `/tmp/spec048_recheck_full.exit` 与日志 `628 passed` 为准，未与其它 pytest 并发（命令 2/3 在 `.exit` 落盘后串行执行）。

### 二、静态复核（命令 6）逐项命中

| 核对项 | 实测 | 结论 |
|---|---|---|
| `literature-maps.css?v=36` live 与 fixture 精确一致 | 精确 `<link>` 正则：live `['36']` / fixture `['36']`；fixture 以 `../../../frontend/literature-maps.css?v=36` 直引 live 文件（71095 bytes / SHA256 `4615703c139f29a2`），无独立副本；`?v=35` 在 live/fixture 均 0 残留 | PASS |
| `literature-maps.js?v=48` 未动 | live `['48']` / fixture `['48']`；只读 `git diff HEAD` 无 `literature-maps.js` 文件条目（仅 `index.html` / fixture 的版本串变更） | PASS |
| 末尾两条 Spec048 marker 位置未变 | `:918` `src="...js?v=47"`、`:919` `href="...css?v=34"` 逐字未变，`</body>` 仍 `:920` | PASS |
| `re.findall(...)[-1]` 仍 47/34 | 实算 `js_all=['48','47'] → [-1]=47`；`css_all=['36','34'] → [-1]=34`；marker 恒为最后一次出现；全量 10+ 处 `in INDEX` / `[-1]` 冻结断言随 628 passed 继续通过 | PASS |
| `BASELINE_COUNTS["literature-maps.js"] == 56` | python 实算 = `56`；`TOKEN` 正则与 `assert actual == expected` 逐字未动，无 skip / xfail / 容差 / 正则放宽 | PASS |
| B2 CSS 修复未破坏 ≥44px 触摸目标 | `.literature-map-main-tab { min-height: 44px; ... }` 与 `#literature-map-refresh-button { min-width: 44px; min-height: 44px; }` 均命中；新增仅 `#literature-maps-view .literature-map-main-tabs { padding: 0 4px; }`（≤760px media 块内、带前缀）；定向 `12 passed` 佐证 | PASS |

> 口径澄清：首轮宽正则把 marker 的 `href="...css?v=34"` 计入 live_css 得到 `['36','34']`，一度显示 `MATCH_v36=False`；改用测试同款 `<link rel="stylesheet" ...>` 精确标签正则后 live / fixture 均恰为 `['36']`，判定 PASS。此为核对脚本口径修正，非仓库缺陷，如实披露。

### 三、B1 / B2 修复逐条判定

- **B1（基线未同步）→ 闭合 / PASS**：`BASELINE_COUNTS["literature-maps.js"]` 由 `58` 精确同步为 `56`（对应移除 2 个 header `secondary-button` 文字按钮、刷新改 `icon-button literature-map-tool`）；只读 diff 显示仅改该值 + 3 行根因注释，其余 3 个基线、`TOKEN` 正则、`assert` 逐字未动，属**精确基线同步而非放宽容错**。命令 2 `1 passed / EXIT=0`、全量 628 passed；原 `56 == 58` 失败消失。
- **B2（390px 窄屏几何回归）→ 闭合 / PASS**：仅改 `frontend/literature-maps.css` ≤760px media 块内一条容器 padding 规则（`4px → 0`），未改 `test_frontend_map_layout_viewport.py` 的断言 / 阈值 / 参数（只读 diff 中无该文件条目），未用 `overflow:hidden` / `transform` / `display:none` 造假；命令 3 `1 passed / EXIT=0`（`visibleMap.height` 由 144 恢复至 ≥150）、全量含该用例 628 passed；≥44px 触摸目标经 §二第 6 项与定向 12 passed 确认未破坏。

### 四、二次升版（v35→v36）冻结语义判定

- live `index.html:11` `literature-maps.css?v=36`，fixture `:8` 同步 `v=36`，`readability.py` `MAP_CSS_VERSION=36`、`tabs.py:47` `css_live==["36"]`、`groups_exports.py:52` / `mobile_contract.py:98` 精确串同步；只读 diff 与全量 628 passed 证明 7 文件 8 处一致。
- `literature-maps.js?v=48`（`:903` / fixture `:1135`）、`:8 styles.css?v=77`、`:905 app.js?v=77` 逐字未动。
- 两条 Spec048 marker `:918/:919` 未新增 / 未移动 / 未删除，`</body>` 仍 `:920`；`re.findall(...)[-1]` 实算 js `47` / css `34` 保持（`js_all=['48','47']`、`css_all=['36','34']`）；marker 位于 live 引用之后、`</body>` 之前，恒为最后一次出现。
- **判定：PASS**。二次升版只改 live / fixture 版本串与精确断言，未触碰 marker 与 `[-1]` 取值来源，冻结语义完好；`[-1]` 脆弱性（marker 之后不得新增同名 `?v=` 引用）依旧存在但本轮未触发，属既有遗留风险、非本轮阻塞。

### 五、VERIFICATION REPORT（复审）

```
VERIFICATION REPORT (RECHECK)
============================
Syntax:    PASS   node --check frontend/literature-maps.js EXIT=0；全量 / 单项无收集错误
Contract:  PASS   DOM class↔CSS 双向、tab ARIA / 键盘、刷新按钮无文字 + aria-label、header 5 按钮、B1 冻结基线精确同步；定向 12 passed
Version:   PASS   live css?v=36 / js?v=48；live↔fixture 精确一致；marker :918/:919 未动、re.findall[-1]=47/34；app.js/styles.css v77 未动；二次升版冻结语义保持
XSS:       PASS   literature-maps.js innerHTML=0；动态文本沿用 textContent / input.value；修复批次未改 JS（仅 CSS padding + 测试基线 / 注释）
Tests:     PASS   628 passed / 0 failed / EXIT=0（全量）；B1 1 passed、B2 1 passed、定向 12 passed 均 EXIT=0
Diff:      0 个业务文件改动（本角色只读；产出仅本追加章节 + 进展日志）
Overall:   PASS   阻塞项 0 个
```

### 六、边界 1–10 复核结论

| 边界 | 复核结论 |
|---|---|
| 1 默认 maps tab 选中 / create panel hidden | 维持通过（全量 628 passed） |
| 2 切 tab 不重建、表单值保留 | 维持通过（实现未动） |
| 3 取消 / 成功回 maps tab | 维持通过 |
| 4 键盘切 tab + 完整 ARIA | 维持通过（定向 12 passed） |
| 5 刷新按钮无文字 + aria-label + 可重复点击 | 维持通过 |
| 6 CSS 转圈图标 / 无 innerHTML / ≥44px | 维持通过；§二第 6 项复核 ≥44px 未被 B2 修复破坏 |
| 7 版本 / marker / 冻结断言 / 精确断言同步 | **通过且备注消除**：B1 精确基线同步后闭合；二次升版 v36 后 `[-1]`=47/34 与全量冻结断言继续通过 |
| 8 readability.py 契约同步、三态 / 尺寸 / 对比度逐字保留 | **通过且备注消除**：原「1 项计数冻结断言失败」即 B1，已闭合；media 块新增 padding 不影响桌面 `_desktop_effective` 取值 |
| 9 ≤760px tab 可点 / 表单可滚动 / 不误开抽屉 / 图标 ≥44px | **通过且备注消除**：B2 390px 用例 `1 passed`、`visibleMap.height≥150`；≥44px 触摸目标与 `overflow-y:auto` 逐字保留 |
| 10 app.js / styles.css / 其它视图不受影响；node --check | 维持通过（命令 4 EXIT=0；v77 未动；未改后端） |

**边界小计：10 / 10 通过，无遗留备注。**

### 七、C1–C10 复核结论

| 约束 | 复核结论 |
|---|---|
| C1 tab DOM 仅在 renderShell 生成、位置正确 | 维持通过 |
| C2 activateMapTab 只切属性、键盘同步、不跨文件直调 | 维持通过 |
| C3 createPanel 迁入 create tabpanel、取消 / 成功回 maps | 维持通过 |
| C4 保留 refresh id / title、新增 aria-label、事件链不变 | 维持通过 |
| C5 纯 CSS 图标、无 innerHTML / SVG、is-spinning 与降级 | 维持通过 |
| C6 HEADER_ACTION_IDS / expected / pairs 同步、三态不放宽 | **通过且备注消除**：原「超出 C6 点名范围的计数冻结断言失败」即 B1，已精确同步闭合，无 skip / xfail / 放宽 |
| C7 `get_by_role('tab', ...)` 同步、流程可跑 | 维持通过（全量浏览器用例 628 passed） |
| C8 版本 47→48 / 34→35→36、marker 末尾、MAP_CSS_VERSION 同步、app.js / styles.css 不动 | **通过**：二次升版 v36 落地，marker 未动、`[-1]`=47/34 保持（见 §四） |
| C9 CSS 前缀 / 不改全局 / media 补齐 / ≥44px / 不误开抽屉 | **通过**：B2 新增规则带 `#literature-maps-view` 前缀、位于窄屏 media 块内、未碰全局基类；≥44px 与 `overflow-y:auto` 保留（§二第 6 项 + 定向 12 passed） |
| C10 锁定前端角色、不跑后端、node --check 与三项自查齐全 | 维持通过：本复审仅前端只读核对 + `tests/frontend/` pytest，未跑后端 pytest，未执行 git / push / 合并 |

**约束小计：10 / 10 通过。**

### 八、命中项 / 阻塞项 / 最终结论

- **命中项**：Syntax / Contract / Version / XSS 四项全 PASS；B1 / B2 两个原阻塞项均闭合；边界 10/10、约束 10/10 通过；二次升版冻结语义保持。
- **阻塞项：0**（原 B1、B2 均由 `frontend-dev` 修复批次闭合，本复审以命令 2 / 3 与全量 628 passed 独立复验）。
- **最终结论：PASS**（复审维度）。

### 九、声明与签字

- **原 FAIL 记录保留、本次为集中复审、不翻案**：本报告 §一–§八 的原始 FAIL（`626 passed / 2 failed / EXIT=1`）是当时的真实记录，逐字保留、未覆盖 / 未改写；本次仅在末尾追加复审章节，记录修复 + 二次升版后的当前真实状态，**不推翻、不翻案**原始判定。两者对应不同时间点的仓库状态，均如实有效。
- 本角色只读，未改业务代码 / 测试 / spec / 台账 / 其它报告正文；唯一写入为本报告末尾章节与自身进展日志。

`frontend-tester` · 2026-11-13

产出：`docs/sdd/plans/048/runs/task-04/frontend-regression.md`（末尾追加）
进展日志：`.codebuddy/agent-logs/spec-048/task-04/frontend-tester-recheck/20261113-034056.md`
