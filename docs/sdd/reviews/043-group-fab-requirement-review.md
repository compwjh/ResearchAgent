# Spec043 增量 · 节点分组画布左下角入口改造 — 需求评审（Requirement Review）

| 项 | 值 |
|---|---|
| **评审者** | `architect` 子代理（本轮 Spec043 增量评审，Gate 2 需求评审） |
| **角色** | 架构师 / `architect`（需求评审 + 技术评审 + 验收签字 + 合并裁决参考） |
| **模型** | Deepseek-V4.1-Flash（按 spec 执行配置表 `docs/sdd/specs/043-literature-map-topic-exploration.md:884`；上下文上限 32k 档，本文件与配套技术评审分两份落盘以规避上限） |
| **分派方式** | 主会话单次分派：只读 spec 三段（758–907 已确认段 / 616–631 地图标签作废段 / 476–482 紧凑布局作废段）+ 实读代码事实，产出本文件与 `043-group-fab-tech-review.md`；**禁改 spec / 业务代码 / 测试 / 版本号，禁部署、禁重启服务、禁 git 操作** |

## 评审基线（如实标注）

- 本轮是 **A 裁决后、实现前的增量需求评审**。方向上不做重新裁决：用户回复「按照A」= 以用户最新亲自澄清为准，实施「节点分组画布左下角入口改造」；「地图标签与卡片设置菜单」及「卡片显示所属标签」继续作废；本轮「按默认」视为对历史清单批量批复（`spec:623-627`、`spec:863`）。
- 状态已由主会话从 `待确认` 改为 `已确认`（`spec:760`），8 个默认值逐条冻结（`spec:865-874`）。
- **本次评审不采信 spec 里未经核实的数字与行号**，凡引用代码一律给 `文件:行` 实测值；凡与实测不符的，单列为 P 项。

---

## 一、结论

# 结论：**通过（附强制约束清单）**

目标清晰可测、7 条需求拆解与 8 条冻结裁定**语义一致、无实质遗漏**、边界与「明确不做」覆盖完整、A 裁决后**无残留方向冲突**。但存在 **4 个 P0 需求侧缺口**（全部集中在"验收不可执行"与"文档一致性"，不涉及方向变更），必须回填 spec 后才能放行实现；否则前端开发与测试会在验收环节各自解释规则。

**P0 阻断（放行前必须闭合）**

| 编号 | 缺口 | 落点 | 为什么是 P0 |
|---|---|---|---|
| R-P0-1 | 任务拆分与真实改动面不符：浏览器用例唯一宿主 `tests/frontend/fixtures/literature_map_component.html`（1123 行）不在任何任务格，且 4 个既有测试文件对**将被移除的 DOM** 有硬断言 | `spec:895-896` vs `tests/frontend/fixtures/literature_map_component.html:8,1120`、`test_frontend_map_groups_exports.py:23-25,63-69,80`、`test_frontend_literature_map_expansion.py:125`、`test_frontend_map_mobile_contract.py:286-309`、`test_frontend_map_palette.py:136-201` | "FE-2 只 2 文件"不成立 → 按拆分派活必然漏改夹具/漏改断言，CI 红 |
| R-P0-2 | 验收数字不可信：spec 写「396 passed 基线」，实测 `tests/frontend/*.py` 为 **48 个文件**；本轮必须改 4 个既有测试文件，"396"必然变化 | `spec:843`、`spec:844` | 不给出"改后应为 N"，测试无法判绿，只能靠人肉判断 |
| R-P0-3 | 「节点样式跟随分组」与「已有节点/分组可再次设置样式」的**落点未写成可验收句子**：裁定 1 只写"节点可切换所属分组"，但未规定**节点详情里分组选择器之外是否还允许任何颜色操作**、**是否有任一 UI 能让单节点颜色 ≠ 所属分组色** | `spec:867` + `spec:838` | 这是需求原文里唯一的历史歧义；结论对了，但缺"如何判定做到了"的一句话 |
| R-P0-4 | 高亮态与既有「扩展高亮」并存规则未定义：已有 `state.expansionHighlightNodeIds` → `.literature-map-node.is-expansion-highlighted`（`literature-maps.js:4950,4954`）与新增 `data-group-highlight` 是**两套节点强调机制**，spec 未规定同时存在时的视觉与清除优先级 | `spec:807`、`spec:816` vs `frontend/literature-maps.js:4950-4954`、`frontend/literature-maps.css:236` | 两套 `<g>`/`<circle>` 强调规则会互相 `!important` 打架，验收无判据 |

**P1（放行前应一并写明，否则验收返工）**

| 编号 | 缺口 | 落点 |
|---|---|---|
| R-P1-1 | 需求拆解表第 6 行仍写「歧义，见待确认问题 1」（`spec:775`），与 `spec:760` 的"已确认"自相矛盾 | `spec:775` |
| R-P1-2 | 「产品使用步骤」7 条**未逐条映射到验收点**，`spec:831` 自述"初稿"，而执行配置表又把 `doc-updater` 标为"不适用"（`spec:883`）—— 没人负责补 | `spec:831-839`、`spec:883` |
| R-P1-3 | 边界写「每条对应一条测试」（`spec:812`），但 8 条边界里 **3 条没有任何可断言的 DOM/属性锚点**（缩放/拖动不错位、三档宽度不遮挡、移动端抽屉不溢出），需指定"用哪个选择器 + 哪个几何断言" | `spec:812-821` |
| R-P1-4 | 冻结文件边界写 `frontend/index.html`（版本号）在范围内（`spec:876`），但任务拆分把 `index.html` 分给 FE-2 且与"新增 1 个定向测试文件"同格 —— 与 R-P0-1 叠加后该格实际是 1+1+1+4+1 文件 | `spec:876`、`spec:896` |
| R-P1-5 | 「图例条保留」（裁定 6）与「浮层列出全部分组及颜色」形成**两处同源信息**；spec 未规定两处色块是否都要响应高亮点击（判据：只读 vs 可点） | `spec:872`、`spec:835` |

**P2（建议，非阻塞）**

- R-P2-1 `spec:760` 与 `spec:863-874` 重复叙述"用户回复按照A"，可将 `spec:760` 压缩为状态行 + 指针。
- R-P2-2 「未分组」项已进浮层（`spec:805`）与图例条（`literature-maps.js:1940-1944`），文案需统一（浮层用"未分组"，图例条也用"未分组"，已一致，仅提示保持）。
- R-P2-3 `spec:822` 的 XSS 边界只提"分组名"，应扩到**分组名的 `title` 属性、`aria-label` 插值**（现有实现在 `literature-maps.js:1958,1967` 用 `setAttribute`/`title`，`createElement` 走 `textContent`，做法已正确，需在 spec 写明"沿用该做法"）。

---

## 二、逐条判定依据

### 2.1 目标是否清晰可测 —— 通过

| 需求拆解（`spec:768-776`） | 冻结裁定 | 判定 | 依据 |
|---|---|---|---|
| 1 节点分组功能保留 | 裁定 1/2/3 | **一致** | 后端 `/groups`、`PUT /nodes/{id}/group` 契约未改（`routes_literature_maps.py:401-462`）；`GroupPatchRequest` 仅 name/color 且 `extra="forbid"`（`:181-186`），与裁定 2「仅颜色、不扩字段」吻合 |
| 2 入口移到画布左下角 icon | `spec:805` | **一致** | 挂点成立：`div.literature-map-canvas` 已 `position:relative`（CSS:74），同级 `.literature-map-canvas-empty` 绝对定位（JS:1265-1267、CSS:76-77） |
| 3 浮层列出分组及颜色 | `spec:805` | **一致** | 数据源 `state.groups`（`loadGroups()` JS:1994-2008），色块渲染方式已有先例 `renderGroupLegend()` JS:1932-1939 |
| 4 点样式高亮该组节点 | 裁定 5 | **一致，但缺并存规则**（→ R-P0-4） | 命中/未命中判据可落在 `data-group-id`（JS:4954），无后端需求 |
| 5 「设置新组」icon + 样式设置 | 裁定 2 | **一致** | 复用 `#literature-map-group-form`/`-name`/`-color`/`-create`（JS:1062-1084）+ `validateGroupForm()`（JS:804-814） |
| 6 已有节点/分组可再次设置样式 | 裁定 1（A+B） | **一致，但不可测**（→ R-P0-3） | 分组侧：`PATCH /groups/{id}` 改色（JS:2242-2270）；节点侧：`renderNodeGroupSelector()`（JS:6631-6653）切组 —— 两句都在，但缺验收句 |
| 7 节点不再单独调样式、样式跟随分组 | 裁定 1/4 | **一致** | 移除对象已定位：`renderNodeColorControls()` JS:6655-6660（注入点 6740）、`selectionPalette` JS:1242-1244、`followGroup` JS:775-786；保留对象 `fill_mode`/`fill_opacity` 属视图级（JS:1333-1371） |

**结论**：7 条拆解与 8 条裁定无矛盾、无遗漏项。裁定 4「全局节点样式 disclosure 保留」与拆解 7「节点不再单独设置样式」不冲突——前者是视图级填充模式，后者的宾语是"单个论文节点"，spec 已显式区分（`spec:810`），**该区分成立**，且被代码结构证实（`nodeStyle` 存 `view_settings`，`color_override` 存节点）。

### 2.2 8 条裁定 vs 7 条需求拆解是否一致无遗漏 —— 通过（附 P1 文档一致性）

逐条对齐结果：裁定 1↔拆解 6+7、裁定 2↔拆解 5、裁定 3↔拆解 7、裁定 4↔（跨拆解 7 的反向约束）、裁定 5↔拆解 4、裁定 6↔拆解 2+3、裁定 7↔（作废段处置）、裁定 8↔（批次编排）。**覆盖完整**。

唯一硬伤：拆解表第 6 行仍留「歧义，见待确认问题 1」（`spec:775`），而问题 1 已冻结为 A+B（`spec:867`）。这是**状态未收口**，不是方向冲突 → R-P1-1（P1，不阻断）。

### 2.3 边界 /「明确不做」是否完整 —— 基本完整（2 处需补）

`spec:812-821` 8 条边界 + `spec:823-829` 5 条"明确不做"，覆盖面良好，尤其三点值得肯定：
- 明确「不新建数据模型、不升 `EXPORT_SCHEMA_VERSION`」（`spec:827`）——与后端实测一致（`service.py:2749-2769` 导出恒含 `color_override`，不改后端即无需升版本）。
- 明确「高亮不持久化、不进导出、不改 `revision`」（`spec:816,828`）——技术可行，见技术评审 T-P0-2。
- 明确「不改 `PATCH /view` 与 409 策略」（`spec:828`）——避免撞历史 P0（revision 收口）。

**缺口**：
1. 高亮 vs 扩展高亮并存规则（R-P0-4）。
2. 「明确不做」少了**一条反向护栏**：节点详情里除分组选择器外，**不得以任何形式写 `color_override`**（含隐藏入口）。当前代码里唯一的写入方是 `applyNodeColor(target)`（JS:766-769 → 2102 起 `updateGraphColorOverrides`），删面板后该函数变无调用者——必须进"明确不做/必须清除"清单，否则 dev 可能"留着不删"，与拆解 7 语义冲突。

### 2.4 「产品使用步骤」是否可操作、能否映射验收点 —— 不足（P1-2）

7 条步骤（`spec:833-839`）**可操作**（都能变成点击动作），但**未映射**到验证方式的 6 条（`spec:843-848`）。映射建议（供主会话回填，不是新需求）：

| 使用步骤 | 应落到的验收点 |
|---|---|
| 1 左下角 icon 存在、列表下方无面板 | 验证 1 DOM 契约（画布内 `position:absolute`、`pointer-events:auto`）+ `#literature-map-groups` 不存在断言 |
| 2 浮层展开列出分组/色块/新建/未分组 | 验证 1 浮层开关 + `aria-expanded` + 3 档宽度 |
| 3 点色块高亮、再点/清除恢复 | 验证 1 + 验证 3 E2E（`data-group-highlight` on/off） |
| 4 新建组设样式 | 验证 1（`validateGroupForm` 复用）+ 验证 3（`POST /groups` body 断言） |
| 5 已有分组改色/改名；节点切组后色变 | 验证 1 + 验证 3（`PATCH /groups`、`PUT /nodes/{id}/group`） |
| 6 详情无节点外观调色板；多选无颜色面板 | 验证 1（移除断言，选择器级） |
| 7 空态/重名/非法色/删除回落/跨图不串/不写库/键盘/移动端 | 验证 1 + 验证 2 回归 + 验证 4 |

且 `spec:883` 把 `doc-updater` 标为"不适用"，与 `spec:831`「确认后由 doc-updater 补齐可执行验收案例」直接矛盾。**二者必须择一**：要么保留 doc-updater 一格，要么由主会话在本段内把上表落成文字。→ R-P1-2。

### 2.5 A 裁决后是否还有残留语义冲突 —— 无方向冲突，有 1 处机制冲突

重点核查「已有节点也可以再次设置样式」vs「节点样式跟随分组」：
- 裁定 1 的解释（节点=切组、分组=改色、节点不单独调色）**是唯一自洽解**，且与末句"样式跟着它的分组走"一致。**判定：矛盾已消解，不构成打回理由。**
- 但**机制层**存在一个 spec 未处理的重叠：高亮（新）与扩展高亮（旧）都是"节点强调"，前者在 `<g>` 上写 `data-group-highlight`，后者用类 `.is-expansion-highlighted` + CSS `stroke: #f08c00 !important`（CSS:236）。若用户先做扩展预览勾选候选、再点分组高亮，两者同时命中同一节点时视觉规则未定义 → R-P0-4。

---

## 三、Spec 强制约束清单（供主会话回填 spec，逐条可验证）

> 全部为本轮评审新增约束，来源标注"评审"；未标注的来自 spec 原文，仅做收敛表述。

**A. 任务拆分与文件边界（改）**
1. 任务拆分表必须显式包含 `tests/frontend/fixtures/literature_map_component.html`（1123 行，浏览器用例唯一宿主；现有 `?v=` 在 `:8` css=28、`:1120` js=42）。**评审依据**：`test_frontend_map_groups_exports.py:43-44`、`test_frontend_map_mobile_contract.py:97-98` 断言该夹具版本号；`test_frontend_map_palette.py` / `_expansion.py` / `_map_mobile_contract.py` 全部 `page.goto(FIXTURE...)`。
2. 任务拆分必须把 **4 个既有测试文件**列为"需同步修改"，不得写成"仅新增 1 个文件"：
   - `tests/frontend/test_frontend_map_groups_exports.py`（`:23-25` marker 断言、`:63-69` 面板操作、`:80` 列表选择器、`:18-19,43-44` 版本号）
   - `tests/frontend/test_frontend_literature_map_expansion.py`（`:125` `#literature-map-groups .literature-map-group-row` 可见性）
   - `tests/frontend/test_frontend_map_mobile_contract.py`（`:286-309` 移动端抽屉内 `#literature-map-groups` 触摸滚动）
   - `tests/frontend/test_frontend_map_palette.py`（`:136-201` `.literature-map-group-color-trigger`、`:242-253` node 调色板、`:389-395,412` `color_override` 导出断言）
3. 每任务 ≤2 文件的上限**保留**，但必须重排为 ≥4 格（建议 FE-1 js+css / FE-2 夹具+既有测试改造 / FE-3 新增定向测试+`index.html` 版本号），不得为凑格数把夹具塞进"新增测试"同格后仍宣称 2 文件。
4. 版本号契约写死：**升 `literature-maps.js?v=42→43`、`literature-maps.css?v=28→29`，并同步 6 个测试文件的硬编码断言**（`_literature_map_contract.py:28-29`、`_literature_map_expansion.py:28-29`、`_map_analysis_contract.py:34-35`、`_map_groups_exports.py:18-19,43-44`、`_map_header_actions_readability.py:26,276,303`、`_map_mobile_contract.py:94-98`）与夹具 `:8,:1120`。若只改其一，必须在 spec 写明"本次仅 js 变更"并解释为何 css 不动（现状下 CSS 必然要加浮层/高亮规则，故 css 必升）。

**B. 验收数字（改）**
5. 删除可信度缺失的「396 passed 基线」（`spec:843`），改为"改动后 `tests/frontend` 全量应为 **N passed**"，并写明 N 由 dev 首次全量跑出后**回填**；同时要求记录"改前实测值"，避免用历史数字冒充。
6. `spec:844` 的「既有基线 240 passed」同样需标注来源与复现命令（`cd backend && source ../.venv/bin/activate && python -m pytest tests/literature_maps -q`），且注明**本轮不新增后端用例**。

**C. 语义收口（改）**
7. 需求拆解表第 6 行「歧义，见待确认问题 1」改为「已裁定 A+B（见冻结表 #1）」（`spec:775`）。
8. 新增可验收句：「节点详情的分组选择器 `#literature-map-node-group` 是**唯一**可改变单节点颜色的入口；全站不存在任何直接写 `node.color_override` 的 UI 路径」。验收方式：`grep -c "updateGraphColorOverrides\|applyNodeColor" frontend/literature-maps.js` 结果为 0 或被证明不可达。
9. 新增并存规则：「分组高亮与扩展高亮（`.is-expansion-highlighted`，CSS:236）同时命中同一节点时，**扩展高亮优先**（保留橙色 `!important` 描边），分组高亮只作用于其余节点；退出扩展面板后分组高亮态不变」。或反向定义，但**必须择一定义**。
10. 新增：「`renderGroupLegend()` 图例条保持**只读**，不承接点击高亮；浮层是唯一高亮入口」（裁定 6 的执行细则，避免两处同源信息各有行为）。

**D. 边界可断言化（改）**
11. 三条"无锚点"边界补断言锚点：
    - 左下角不遮挡缩放控件：断言 FAB 与 `.literature-map-tools` 的 `getBoundingClientRect()` 无交叠；
    - 三档宽度：在 1440 / 1024 / 375 三个视口下断言 FAB 完整在 `.literature-map-canvas` 内（`rect` 包含关系）；
    - 移动端不溢出：375 视口下断言 `document.documentElement.scrollWidth <= innerWidth`。
12. XSS 边界扩写：分组名的写入必须走 `textContent`（`createElement` 的第三参，JS:191-196）与 `setAttribute('aria-label'/'title', ...)`，**禁止字符串拼接进 `innerHTML`/`insertAdjacentHTML`**；验收加断言 `assert 'innerHTML' not in MODULE`（该断言已存在于 `test_frontend_map_groups_exports.py:38`，沿用即可）。

**E. 批次（不改，确认）**
13. 裁定 8「独立成批次、不共用版本号」与裁定 7③「顶部按钮已收口」一致，无需调整。

---

## 四、阻塞项 → 放行条件

| 门槛 | 条件 |
|---|---|
| 需求评审放行 | R-P0-1 ~ R-P0-4 已回填 spec；R-P1-1/R-P1-2/R-P1-4 至少写明处置人（谁补） |
| 技术评审放行 | 见 `docs/sdd/reviews/043-group-fab-tech-review.md` 的 T-P0-x 清单 |
| 合并裁决 | 两份评审均"通过"或"通过附意见且 P0 已闭合" |

---

## 五、评审记录

- 2026-11-06 ｜ `architect`（子代理）｜ 增量需求评审完成，结论 **通过（附 13 条强制约束）**；P0 4 项、P1 5 项、P2 3 项。无方向性打回。
- 本文件为只读评审产出，未修改 spec / 业务代码 / 测试 / 版本号。
