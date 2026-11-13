# Spec-048 · task-04 · 缺陷修复报告（frontend-dev / SDD 当前 Task 内修复复审）

| 项 | 值 |
|---|---|
| 角色 | `frontend-dev`（ECC tdd-guide 精神：先真实复现 RED，再最小实现转 GREEN） |
| Spec / Task | Spec-048 / task-04 |
| 日期 | 2026-11-13（执行时段约 03:17–03:30） |
| 依据 | `docs/sdd/plans/048/runs/task-04/frontend-regression.md`（frontend-tester：全量 `626 passed / 2 failed / EXIT=1`） |
| 边界 | **只改 2 个文件**：`tests/frontend/test_frontend_button_affordance_contract.py`、`frontend/literature-maps.css`；产出本报告 + 进展日志。禁改 `literature-maps.js`、其它测试、spec、台账、其它视图；未执行 git / push / 合并 |
| 结论 | **PASS**：全量 `628 passed / 0 failed / EXIT=0`，B1 / B2 两个阻塞项闭合 |

## 一、B1 根因与修复（基线精确同步，非放宽容错）

- **失败**：`test_frontend_button_affordance_contract.py::test_button_count_is_frozen`，`assert 56 == 58`（:107），`EXIT=1`，稳定复现（`1 failed in 1.42s`）。
- **根因**：Spec-048 移除 header 的「新建地图」「刷新状态」两个 `secondary-button btn-outline` 文字按钮；刷新按钮迁到画布工具区，改为 `createElement('button', 'icon-button literature-map-tool')`（两参数、无可见文字、带 `aria-label="刷新状态"`），不再带 `secondary-button` token。真实 `TOKEN.findall(literature-maps.js)` 由 58 精确降为 56（-2）。冻结基线 `BASELINE_COUNTS["literature-maps.js"] = 58`（原 :49）未随源码同步。
- **修复**（`test_frontend_button_affordance_contract.py:43-53`）：
  - `BASELINE_COUNTS["literature-maps.js"]`：`58 → 56`（现 :52）；
  - 相邻注释（:45-47）追加 3 行，写明 Spec-048 移除 2 个 header 文字按钮、刷新改 `icon-button literature-map-tool` 同族图标按钮、`secondary-button` token 由 58 精确降为 56；
  - 其余 3 个基线 `index.html:28` / `app.js:29` / `research-tasks.js:11` **逐字不动**；
  - `TOKEN` 正则（:41）、`test_button_count_is_frozen` 的 `assert actual == expected`（:104-107）**逐字不动**；无 skip / xfail / 正则放宽 / 容差。
- **性质**：精确基线同步，不是放宽容错。

## 二、B2 根因与修复（只改 CSS，未动测试断言 / 阈值 / 参数）

- **失败**：`test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]`，`assert 144 >= 150`（:237），`EXIT=1`，稳定复现（`1 failed in 1.98s`）。
- **复现 metrics（修复前）**：`canvas.top=450`、`detail.rect={top:594, height:306}`（fixed）、`visibleMap.height=144`。B2 的 `visibleMap` = canvas∩视口扣除 fixed detail panel 后的最大矩形；390px 下 detail 恒占 `[594,900]`，故 `visibleMap.height = 594 - canvas.top`，需 `canvas.top ≤ 444`（上移 ≥6px）。
- **Playwright 实测盒子高度（390px，`/tmp` 临时脚本，复用测试模块 `_open_map` / `_real_graph_replay`，未留在仓库）**：

  | 元素 | 实测 |
  |---|---|
  | `.literature-map-app` | padTop 12、rowGap 14、高 1032（`display:grid`） |
  | `.literature-map-header` | 高 136 |
  | `.literature-map-main-tabs` | **top 162、高 54**（pad 4+4 + border 1+1 + tab min-height 44） |
  | `.literature-map-notice` | 高 30 |
  | `#literature-map-tabpanel-maps` | top 274（= 12+136+14+54+14+30+14） |
  | `.literature-map-grid` / `.literature-map-canvas-panel` | top 274、高 740 / 710 |
  | `.literature-map-canvas` | **top 450**、高 478.91 |
  | `.literature-map-detail-panel` | fixed top 594、高 306 |

- **6px 根因**：Spec-048 新增 `.literature-map-main-tabs` 作为 `.literature-map-app`（`display:grid; gap:14px`，:5）的新 grid 行（54px），并在其前后各引入 14px row-gap，叠加 `#literature-map-tabpanel-maps` 新容器，把整条文档流下推，canvas 随之下移到 `top=450`，使 `visibleMap.height` 由 ≥150 跌到 144。detail panel 为 `position:fixed`，不受文档流影响（恒 594）。
- **修复**（`frontend/literature-maps.css:598-606`，仅 `@media (max-width: 760px)` 块内）：
  - 新增注释（:600-603）+ 一条规则（:604）：`#literature-maps-view .literature-map-main-tabs { padding: 0 4px; }`；
  - 只在窄屏把 tab **容器**上下 padding `4px → 0`（保留左右 4px 与 1px 边框），使其高 54→46（-8px），canvas 上移 8px；桌面（>760px）基础规则（:590）逐字不动；
  - **未**用 `overflow:hidden` 裁内容 / `transform` 造假 / `display:none` 隐藏 tab；
  - **未**修改 `tests/frontend/test_frontend_map_layout_viewport.py` 任何内容（断言 / 阈值 / 参数逐字未动）。
- **修复后 GREEN metrics**（`pytest -q -s` 捕获 print JSON）：`canvas.top=442`、`canvas.height=478.90625`（不变）、`detail.rect.top=594`（不变）、`visibleMap.height=152`（≥150，余量 2px）、`detailOverlaysCanvas=True`、`hitNodeId` 命中目标、`pageerror=[]`。

## 三、验证（真实命令 / 退出码 / 通过数）

| # | 命令 | 真实输出 | 退出码 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q 'tests/frontend/test_frontend_button_affordance_contract.py::test_button_count_is_frozen'` | `1 passed in 0.21s` | **0** |
| 2 | `.venv/bin/python -m pytest -q 'tests/frontend/test_frontend_map_layout_viewport.py::test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]'` | `1 passed in 1.34s` | **0** |
| 3 | `.venv/bin/python -m pytest -q tests/frontend/`（全量；nohup 后台，`/tmp/spec048_full.exit` 取回真实退出码） | `628 passed in 129.25s (0:02:09)` | **0** |
| 4a | `node --check frontend/literature-maps.js` | 无输出（语法通过） | **0** |
| 4b | `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | **0** |
| 附 | C9 / 边界 6、9 定向复核（4 文件：`test_literature_map_tabs_and_refresh_icon.py` / `test_frontend_map_header_actions_readability.py` / `test_frontend_map_mobile_contract.py` / `test_frontend_button_affordance_contract.py`） | `52 passed in 20.69s` | **0** |

> 全量由 frontend-tester 的 `626 passed / 2 failed / EXIT=1` 变为 `628 passed / 0 failed / EXIT=0`（626+2=628 精确对齐，无新增失败）。若仍失败将如实报告、不改松断言 / 阈值 / skip / xfail——本次实测无失败。

## 四、三项自查（regression-guard 前端第 1–4 条）

1. **DOM 契约 / class↔CSS**：本次未新增 / 修改任何 class 名；改动的 `.literature-map-main-tabs` 规则 Grep 反向核对在 `literature-maps.js:997-998` 被 `createElement` 渲染、在 CSS（:590 基础 / :604 覆盖）有定义。✓
2. **资源版本号 `?v=N`**：本次改的是 `literature-maps.css`（非 `app.js` / `styles.css`）。**核对后决定不升 `?v=N`**，依据：① 任务边界锁定只改 2 个文件、明确禁改 `index.html` 与 fixture（其它视图）；② ≥6 个测试文件精确冻结 live `literature-maps.css?v=35`（`test_literature_map_tabs_and_refresh_icon.py:47` `css_live == ["35"]`、`test_frontend_map_header_actions_readability.py:27/291/318` `MAP_CSS_VERSION=35`、fixture 的 `?v=35` 等），升版本必破坏全量与 C8；③ B2 经 `FIXTURE.as_uri()`（`file://`）直接读取 CSS 文件内容，无 HTTP 缓存陈旧问题，`?v=` 在 fixture 仅为标记；④ 属 SDD 缺陷修复的最小 CSS 微调，版本号按 C8 由 closing task 统一 bump。实测 `index.html:11` `css?v=35`、`:903` `js?v=48`、marker `:918/:919`、`:8/:905` `?v=77` 逐字未动。✓（如实披露，非遗漏）
3. **XSS**：未改任何 JS；`literature-maps.js` 实测 `innerHTML=0`，动态文本沿用 `textContent` / `input.value`；本次新增内容仅为 CSS 注释与一条 padding 声明，无 DOM 拼接。✓
4. **CSS 作用域**：新增选择器完整保留 `#literature-maps-view` 前缀、位于窄屏 media 块内；未触碰全局 `.secondary-button` / `.icon-button` / `.btn-outline`；`literature-maps.css` 全部规则仍以视图容器为边界。✓

## 五、C9 与边界 6 / 9 复核

- **C9**（新增 CSS 前缀 / 不改全局基础样式 / media query 补齐 / 不误开抽屉；窄屏 tab 可点 `min-height≥44px`、刷新图标 `≥44px`、创建表单可滚动）：
  - `literature-maps.css:599` `.literature-map-main-tab { min-height: 44px; ... }` 逐字保留 → tab 触摸目标 ≥44px、可点；
  - `:605` `#literature-map-tabpanel-create { max-height: calc(100dvh - 200px); overflow-y: auto; ... }` 逐字保留 → 创建表单可滚动；
  - `:619` `#literature-map-refresh-button { min-width: 44px; min-height: 44px; }` 逐字保留 → 刷新图标 ≥44px；
  - 新增规则 `:604` 带 `#literature-maps-view` 前缀，未新增 / 删除任何 media 块、未改全局按钮基类；新建入口仍走 `activateMapTab`，未引入 `openMobilePanel('list')`；
  - 定向 `test_literature_map_tabs_and_refresh_icon.py`（含 `test_tab_css_is_scoped_to_map_view` / `test_mobile_refresh_button_keeps_44px_touch_target`）在全量与定向复核中均通过。✓
- **边界 6**（`readability.py` 契约同步、三态 / 尺寸 / 对比度逐字保留）：`test_frontend_map_header_actions_readability.py` 的 `_desktop_effective` 排除所有 media 块内规则、断言 `font-size:12px` / `font-weight:600` / `padding:9px 14px` / `min-height:36px` / 高对比配色 / hover-focus-disabled 三态；本次只在 media 块内新增一条 `.literature-map-main-tabs` 规则，不影响上述取值；`test_map_overrides_never_target_bare_secondary_button` 遍历所有规则仅对含 `.secondary-button` 的选择器要求前缀，新规则不含之。定向复核通过。✓
- **边界 9**（≤760px tab 可点 / 表单可滚动 / 不误开抽屉 / 图标 ≥44px）：`test_frontend_map_mobile_contract.py` 定向通过；B2 `[390]` 真实浏览器用例由 `assert 144 >= 150` 转为 `1 passed`（`visibleMap.height=152`、`hitNodeId` 命中、`pageerror=[]`）；其余 4 个宽度（1440 / 1280 / 1180 / 900，均 >760px）不受窄屏规则影响。✓
- 定向复核合计 `52 passed / EXIT=0`；全量 `628 passed / EXIT=0`。

## 六、改动文件与行（仅 2 个业务文件）

| 文件 | 改动 |
|---|---|
| `tests/frontend/test_frontend_button_affordance_contract.py` | :45-47 新增 3 行 Spec-048 根因注释；:52 `literature-maps.js` 基线 `58 → 56`（原 :49）。净 +3 行、改 1 值 |
| `frontend/literature-maps.css` | :600-603 新增 4 行注释、:604 新增 `#literature-maps-view .literature-map-main-tabs { padding: 0 4px; }`（598-606 窄屏 media 块内）。净 +5 行 |

> 未改 `literature-maps.js`、`index.html`、`app.js`、`styles.css`、fixture、其它测试、spec、台账、其它视图；未执行 git / push / 合并。

## 七、风险与遗留

- **余量 2px**：B2 修复后 `visibleMap.height=152`（阈值 150）。CSS 像素为确定性布局计算（两次复现均精确 144、修复后精确 152，无浮点抖动），2px 余量在固定 Playwright chromium / 390×900 视口下可靠；若将来窄屏 tab 或 header 再增高，需重新复核该阈值。
- **版本号未升**：见 §四.2，属边界与冻结断言约束下的显式决策，非遗漏；若后续 closing task 统一 bump `literature-maps.css?v=36`，需同步 ≥6 处冻结断言与 fixture，本 Task 不做。
- **本报告不替代复审**：按 SDD「已确认范围内的小缺陷留在当前 Task 修复并复审」，建议 frontend-tester / reviewer 据本报告复核全量 `628 passed` 与两处最小改动。

## 八、签字

`frontend-dev` · 2026-11-13

产出文件：`docs/sdd/plans/048/runs/task-04/defect-fix.md`
进展日志：`.codebuddy/agent-logs/spec-048/task-04/frontend-dev-fix/20261113-031715.md`
