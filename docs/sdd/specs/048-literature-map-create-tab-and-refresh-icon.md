# Spec-048 文献地图：新建入口 tab 化与刷新状态图标化

## 状态

> 状态只能是：`待确认` / `已确认` / `实施中` / `已完成` / `阻塞`。
> 每次变更须同步追加 `docs/sdd/spec-status-changelog.md`。

**当前状态：已完成**

> `待确认 → 已确认 → 实施中 → 已完成`（2026-11-13 收口）。用户明确「确认，你开发吧」；Gate 2 需求评审 `048-requirement-review.md`「通过（附意见）」与技术评审 `048-tech-review.md`「通过（附意见）」均独立落盘，P0=0 / P1=0，强制约束 C1–C10 已生效（见「Gate 2 强制约束」段）。
> **收口依据**：最终候选全量 `4571 passed / EXIT=0 / 83.01%`、单端 `628 passed / EXIT=0`、真实 Chromium E2E `18/18 PASS`（88 个真实 API 响应）、部署 4×200 PASS；`tester` 验收「通过」签字 R 与 `architect`「批准收口」签字 A 双签并列非自批；`frontend-reviewer` APPROVE 保持、`frontend-tester` 复审 PASS；十项人工验收准备度 10/10，无 P0/P1、无 API E2E 失败、无关键产物缺失；台账、复盘、人工验收步骤与最终验证记录已落盘（见「评审记录」/「变更日志」与 `docs/sdd/plans/048/runs/task-04/final-verification.md`）。
> 用户同时指示：开发完成后**省略 PR 流程**、直接推送远端；该指示覆盖本 spec 原「不主动 push」条目（见「明确不做」末条）。**不 force push**。
> Spec-047 追加范围五成果（`c6abb7a6`）随本次远端交付一并快进推送，不另开 PR、不并入本 spec 的需求范围。

## 一句话目标

把「新建地图」从左侧栏弹出的大表单卡片，改成与深度研究一致的**页面级 tab 切换**（`地图` / `新建地图` 两个 tab、两个 tabpanel）；把「刷新状态」从顶部文字按钮移到**地图展示卡片（画布面板头部工具区）**，改为**无可见文字的转圈图标按钮**，交互与状态刷新语义不变。

## 用户诉求与现场证据

| 诉求 | 截图 / 现场证据 | 当前实现 |
|---|---|---|
| 新建地图展示方式不合理，改成类似深度研究、加一个 tab | 截图 2：点「新建地图」后出现占满视口的「新建主题地图」大表单卡片（主题 / 名称 / 年份 / 首批数量 / 来源 / 会议 / 项目 / 取消 / 开始建图） | `frontend/literature-maps.js:1076-1079` 建 `.literature-map-create-panel`，`:1155` `listPanel.append(createPanel)`；`:1529-1539` 点「新建地图」只切换 `hidden`，并在移动端先打开列表抽屉 |
| 刷新状态按钮移到地图展示的卡片中 | 截图 1：顶部并排「刷新状态」「新建地图」两个文字按钮 | `frontend/literature-maps.js:969-973` 在 `.literature-map-header-actions` 建 `#literature-map-refresh-button`，文案「刷新状态」；事件 `:1520-1523` |
| 用转圈的 icon 展示，不要用文字 | 同上 | 无图标实现；画布头部 `:1165-1190` 已有一组 `icon-button literature-map-tool`（缩小 / 放大 / 适应 / 定位 / 重置 / 整理间距）可复用样式位 |

**参考实现（"类似深度研究"）**：`frontend/index.html:221-243` 的 `#research-main-tabs`（`role="tablist"`，两个 `role="tab"` + 两个 `role="tabpanel"`，创建面板默认 `hidden`）；切换逻辑 `frontend/research-tasks.js:895-922` `activateResearchTab()` —— 只改 `hidden` / `aria-selected` / `tabIndex`，**不重建面板**，因此表单值在切换后保留；`moveResearchTab()` 支持方向键。

## 关键设计决定（用户已确认）

1. **tab 位置与命名**：在 `.literature-map-header` 之下、`.literature-map-grid` 之上新增一组页面级 tab：`地图`（`data-map-tab="maps"`，默认选中）与 `新建地图`（`data-map-tab="create"`）。选中「地图」时显示既有三栏工作区（列表 + 画布 + 详情），选中「新建地图」时**只显示创建表单 tabpanel**。
2. **表单搬 DOM**：把 `createPanel` 从 `listPanel` 内移到新建的 `#literature-map-create-tabpanel`（`role="tabpanel"`），表单节点与所有 `id` / `refs` 指针**不变**（沿用 `research-tasks.js` 的 "panels never rebuilt" 口径）；`h3` 标题「新建主题地图」保留。取消按钮与创建成功 / 离开视图时切回「地图」tab 并聚焦该 tab，等价于原 `closeCreatePanel()` 语义。
3. **移除 header 的「新建地图」文字按钮**：入口由 tab 唯一承担，不保留重复按钮；`state.createPanelOpen` 改为与 tab 激活态同源。移动端不再因新建入口触发 `openMobilePanel('list', ...)`，tab 在窄屏直接切换整块内容。
4. **「地图展示的卡片」判定**：取右侧**画布面板卡片** `#literature-maps-view .literature-map-canvas-panel` 的头部工具区 `.literature-map-tools`（`literature-maps.js:1157-1191`）——它是展示地图的主卡片，且已有 icon-button 工具组。
5. **刷新图标**：保留 `#literature-map-refresh-button` 与 `title`，**新增** `aria-label="刷新状态"`（现状只有 `title`，Gate 2 C4 修正措辞），**移除可见文字**；按钮改为 `icon-button literature-map-tool` 同族，内部用一个 CSS 绘制的循环箭头 `<span class="literature-map-refresh-icon">`（不引入图标字体 / 内联 SVG 字符串，沿用 `.literature-map-groups-fab-icon` 的纯 CSS 做法）；点击时加 `is-spinning` 类做旋转反馈，请求结束移除。禁用 / `prefers-reduced-motion` 时不做持续动画。
6. **其它 header 作业按钮不动**：「继续搜索」「刷新预览」「打开上次预览」「停止任务」「重试失败单元」保持默认 `hidden` 与事件绑定，不随本次搬迁。

## 数据模型

**无新增 / 无变更**：地图、作业、节点、标签、分组、项目的字段与状态取值域全部不变；无 localStorage / 视图保存格式变化。

| 字段 | 类型 | 约束 |
|---|---|---|
| （不适用） | — | 本次为纯前端 DOM 结构与样式重组 |

## 端点 / 接口

**无新增 / 无变更**：不新增端点、不改请求 / 响应结构、不改错误码；`refresh` 仍走 `selectMap(state.selectedMapId)` 或 `loadMaps()`（`literature-maps.js:1520-1523`）。

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| （不适用） | — | — | — |

## 边界（每条之后会变成一条测试）

1. 默认进入文献地图视图时，「地图」tab `aria-selected="true"`、其 panel 可见；「新建地图」tabpanel `hidden`，表单不可见。
2. 点「新建地图」tab → 只切 `hidden` / `aria-selected` / `tabIndex`，**不重建表单**，已填写的主题 / 名称 / 年份 / 来源 / 会议 / 项目值在 tab 往返后保留。
3. 点「取消」或创建成功后 → 回到「地图」tab，`#literature-map-create-panel` 为 `hidden`；`test_frontend_literature_map_contract.py:270,284` 的隐藏断言继续成立。
4. tab 支持键盘 `←/→`（或 `Home/End`）切换，`tabIndex` 与 `aria-selected` 同步；`role="tablist"` / `role="tab"` / `role="tabpanel"` / `aria-controls` / `aria-labelledby` 齐全。
5. 刷新按钮：`#literature-map-refresh-button` 位于画布面板头部工具区内，**无可见文字**（无文本节点、无文字子节点），有 `title` 与**新增的** `aria-label="刷新状态"`，点击仍触发状态刷新且可重复点击。
6. 图标为 CSS 绘制的转圈形状，DOM 中无 `innerHTML` / 内联 SVG 字符串 / 新增图标字体；旋转态有可观察的 class，且不影响按钮尺寸与 ≥44px 移动端触摸目标。
7. 静态资源：`literature-maps.js?v=47 → v=48`、`literature-maps.css?v=34 → v=36`；两条旧版本**纯属性片段** marker 置于 `frontend/index.html` 末尾注释区（不含 `<script` / `<link` 标签字面串、不插入 `<head>`），使 10+ 处 `in INDEX` 冻结断言继续通过；精确 live 断言与 fixture 内版本字符串同步到新值，**不改松 / 不删 / 不 skip / 不 xfail**。
8. `test_frontend_map_header_actions_readability.py` 的 `HEADER_ACTION_IDS` / 文案断言按新契约更新（移除 `literature-map-new-button`、刷新按钮改判「无可见文字 + aria-label」），其余三态 / 尺寸 / 对比度约束逐字保留。
9. 移动端 ≤760px：tab 可点、表单可滚动、创建入口不再误开列表抽屉；刷新图标按钮在画布头部可见且触摸目标 ≥44px。
10. `app.js` / `styles.css` / 其它视图不受影响；`node --check` 通过。

## 明确不做（划出范围，防自由发挥）

- **不改 `backend/**`、不改任何 API / 数据模型 / 地图生成与轮询逻辑**，不新增字段或端点。
- **不改表单字段、校验规则、提交行为**与「开始建图」后的流程；只搬 DOM 容器与切换方式。
- **不删 / 不改 header 中其它作业按钮**（继续搜索 / 刷新预览 / 打开上次预览 / 停止任务 / 重试失败单元）的默认显隐与事件。
- **不改全局 `.secondary-button` / `.icon-button` 基础样式**；新样式一律限定 `#literature-maps-view` 作用域。
- **不用 `innerHTML`、不引入图标库 / 字体 / 内联 SVG 字符串**；图标只用 CSS 形状。
- **不放宽任何既有断言**：`?v=N` 冻结断言靠纯属性 marker 兼容，精确断言真实同步，不靠正则放宽；不改历史归档报告中的旧路径。
- **不动 `app.js` / `styles.css` 版本号**（本次只升 literature-maps 两个资源）。
- **不处理** Langfuse `:3000`、控制台其它视图 404、全仓 185 个历史 lint 债务、无真实 CI workflow / branch protection 等既有非阻塞项。
- **不 force push、不改受保护分支设置、不新建 PR**（按用户 2026-11-13 当次指示：开发完成后省略 PR 流程，直接以 fast-forward 快进推送远端 `main`）；Spec-047 追加范围五成果随同一交付一并推送。本条覆盖初稿「闭环后仅本地 commit」的口径，除此之外不扩大交付范围。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 初稿只写核心场景；开发收口时必须补齐可执行人工验收案例：每步点击的控件、点击后的提示、等待条件、下一步、失败恢复、产物路径。自然语言入口属于产品主路径时优先验证。

- 步骤 1：左侧导航点「文献地图」→ 页面顶部出现 `地图` / `新建地图` 两个 tab，默认停在「地图」，显示列表 + 画布 + 详情。
- 步骤 2：点「新建地图」tab → 大表单以独立面板呈现（不再挤在左栏卡片里），填写主题后切回「地图」再切回来，已填内容仍在。
- 步骤 3：填完点「开始建图」→ 自动回到「地图」tab，状态栏显示生成中，列表出现新地图。
- 步骤 4：在画布卡片头部找到**转圈图标**（无文字），点击 → 图标旋转、列表 / 作业状态刷新；悬停提示「刷新状态」。
- 验收场景：桌面与 ≤760px 窄屏各走一遍步骤 1–4；键盘 `Tab` + `←/→` 可切 tab；刷新图标点击后状态更新且无文字残留。

### 人工验收案例（可执行，2026-11-13）

> 本节把上文步骤 1–4 细化成可执行验收，**只追加**，不改动步骤 1–4 与「验收场景」原文。验收人：产品 / 测试同学，在已部署版本用真实浏览器操作；桌面（≥1024px）与 ≤760px 窄屏各走一遍。启动服务、硬刷新与资源版本核对见 `artifacts/spec-048-literature-map-tabs-manual-e2e.md` §0。

#### 桌面路径（对应步骤 1–4）

| 步 | 操作（点什么控件） | 点击后提示 / 看到什么结果 | 等待条件 | 下一步 |
|---|---|---|---|---|
| 1 | 左侧导航点「文献地图」 | 页面顶部（`.literature-map-header` 下）出现 `地图` / `新建地图` 两个 tab；`地图` 高亮（`aria-selected="true"`），下方为「列表 + 画布 + 详情」三栏，`新建地图` 面板 `hidden` 不可见（边界 1） | 三栏工作区渲染完成、无加载骨架 | 进入步 2 |
| 2 | 点「新建地图」tab | 整块切到「新建主题地图」表单 tabpanel（独立面板，不再挤在左栏卡片）；`新建地图` 高亮、`地图` 取消高亮（只切 `hidden` / `aria-selected` / `tabIndex`，边界 2 / C2） | 表单字段（主题 / 名称 / 年份 / 首批数量 / 来源 / 会议 / 项目）可编辑 | 填「主题」→ 点回「地图」→ 再点回「新建地图」，确认已填主题仍在；进入步 3 |
| 3 | 表单填完点「开始建图」 | 自动切回「地图」tab；状态栏显示「生成中…」，列表出现新地图条目；`#literature-map-create-panel` 为 `hidden`（边界 3 / C3） | 等「生成中…」稳定、列表可见新地图（不必等全部节点生成完） | 进入步 4 |
| 4 | 在画布卡片头部工具区找到**转圈图标按钮**（无可见文字，紧邻缩小 / 放大 / 适应等工具） | 悬停 tooltip「刷新状态」（`title` + `aria-label`）；点击后图标加 `is-spinning` 开始旋转；按钮无文字残留（边界 5 / 6 / C4 / C5） | 等旋转停止（`is-spinning` 移除 = 请求结束）、列表 / 作业状态更新；按钮可重复点击 | 桌面路径完成 |

#### ≤760px 窄屏路径（对应步骤 1–4）

| 步 | 操作（点什么控件） | 点击后提示 / 看到什么结果 | 等待条件 | 下一步 |
|---|---|---|---|---|
| 1 | 浏览器宽度设 ≤760px（DevTools 设备模式），左侧导航点「文献地图」 | 两个 tab 横向可见可点；`地图` 默认高亮，三栏按窄屏布局折叠呈现 | tab 可点击、无横向溢出遮挡 | 进入步 2 |
| 2 | 点「新建地图」tab | **整块**切到表单面板；**不弹出列表抽屉**（不再触发 `openMobilePanel('list', ...)`）；表单可上下滚动，字段可编辑（边界 9 / C9） | 表单滚动到底可见「取消 / 开始建图」 | 填「主题」→ 来回切 tab 确认值保留；进入步 3 |
| 3 | 点「开始建图」 | 回到「地图」tab，状态栏「生成中…」，列表出现新地图 | 等生成中状态稳定 | 进入步 4 |
| 4 | 画布头部点转圈图标按钮 | 图标按钮可见、触摸目标 ≥44px；点击后旋转并刷新；无可见文字残留（边界 9） | 等旋转停止、状态更新 | 窄屏路径完成 |

#### 键盘切 tab（补充验收，边界 4 / C2）

| 按键 | 操作 | 预期结果 |
|---|---|---|
| `Tab` | 把焦点移入 tablist | 焦点落在当前选中 tab（`tabIndex=0`），未选中 tab `tabIndex=-1` |
| `→` / `←` | 在 tab 上按方向键 | `地图` ⇄ `新建地图` 切换，`aria-selected` 与 `tabIndex` 同步，panel 随之显隐 |
| `Home` / `End` | 在 tab 上按 Home / End | 跳到首个 / 末个 tab，同步 `aria-selected` / `tabIndex` |
| `←` 切走再切回 | 键盘切到「新建地图」填值、切走再切回 | 表单值不丢失（面板不重建） |

#### 失败恢复

| 现象 | 恢复动作 |
|---|---|
| tab 不切换 | ① 硬刷新 `Cmd+Shift+R`；② 查源代码 live 链接是否 `literature-maps.js?v=48`；③ DevTools 核对该元素 `role="tab"` / `aria-controls` / `data-map-tab` 是否齐全；仍不切换则截图记录，回到 `docs/sdd/reviews/048-*.md` 的 DOM 契约核对项，暂停验收并上报 |
| 表单值丢失 | 核对是否走了「重建面板」路径（应只切 `hidden` / `aria-selected` / `tabIndex`）；对照边界 2 与 C2 记录复现步骤，暂停验收并上报，不以重新填写硬凑通过 |
| 图标不旋转 | ① 确认点的是画布头部图标按钮而非其它工具；② 查 `is-spinning` class 是否加上、是否处于禁用态或 `prefers-reduced-motion`（此二者按设计不做持续动画，属预期）；③ 服务不可达会提前结束旋转，见下行 |
| 旧缓存命中 | 硬刷新；查源代码首个 live 链接为 `literature-maps.js?v=48` / `literature-maps.css?v=36`；若仍见 `v=47` / `v=34` 清站点缓存后重刷；`index.html` 末尾注释区的旧版本纯属性 marker 仅注释、不加载，勿误判为生效资源 |
| 服务不可达 | `curl http://127.0.0.1:8000/api/health` 应返回 `{"status":"ok"...}`；`connection refused` 用 `./deploy/start.sh -d` 启动（端口占用改 `PORT=8300 ./deploy/start.sh -d` 并替换地址），仍失败则记录阻塞、不宣称验收通过 |

#### 产物查看路径

| 产物 | 路径 |
|---|---|
| 浏览器 E2E 记录 / 截图 | `docs/sdd/plans/048/runs/task-04/`（E2E 结果、部署验证、回归产物；执行后回填真实文件名） |
| 部署验证 / 全量回归 | `docs/sdd/plans/048/runs/task-04/`（部署 200 校验、静态契约与 `node --check` 回归输出） |
| 需求 / 技术 / 验收 / 代码评审 | `docs/sdd/reviews/048-requirement-review.md`、`docs/sdd/reviews/048-tech-review.md`、`docs/sdd/reviews/048-acceptance-review.md`、`docs/sdd/reviews/048-*.md` |
| 收口复盘 | `docs/sdd/retro/` |
| 本验收可复现步骤清单 | `artifacts/spec-048-literature-map-tabs-manual-e2e.md` |

#### 自然语言入口

本范围**不新增也不修改自然语言交互**（无对话框 / 指令输入等 NL 入口），产品主路径为 tab 点击与图标按钮点击；故自然语言入口验证标记为「不适用（非本范围改动）」，不做形式化验证，也不以内部 API 调用替代主路径点击。

## 执行配置（由架构师填写，落盘可查）

> 型号列按 `MODEL_REGISTRY.md:54-68`：唯一真源是 `.codebuddy/agents/<role>.md` 的 `model` 字段，本次读取结果均为 `hy4`；架构师行填「自身」不写死型号。型号为临时决策，不固化进流程文档。
> 五行齐全；本项目**不存在 `junior-dev` / `pm` / `tech-lead`**，跨端改动拆两端分别分派。本次为**纯前端**改动，只分派 `frontend-dev` / `frontend-reviewer` / `frontend-tester`，不派后端角色、不跑后端 pytest 单端回归（Spec 收口全量回归除外）。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 `architect` | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、需求与技术评审、合并裁决、落地校验 |
| 文档/产品步骤 `doc-updater` | `hy4`（读自 `.codebuddy/agents/doc-updater.md`） | 按 agent 档位 | `Task(doc-updater)` | spec 确认后补产品使用步骤、用户旅程、人工验收场景 |
| 前端开发 `frontend-dev` | `hy4`（读自 `.codebuddy/agents/frontend-dev.md`） | 按 agent 档位 | `Task(frontend-dev)` | 已确认范围内的 `frontend/**` 编码、三项自查（class 与 CSS 对应 / `?v=N` 已升 / 无 `innerHTML`） |
| 前端评审与单端回归 `frontend-reviewer` · `frontend-tester` | `hy4`（分别读自两 agent 的 `model`） | 按 agent 档位 | `Task(frontend-reviewer)` / `Task(frontend-tester)` | DOM 契约 / 版本号 / XSS 三项必查；单端静态契约核对 |
| 跨端验收总控 `tester` | `hy4`（读自 `.codebuddy/agents/tester.md`） | 按 agent 档位 | `Task(tester)` | 真实浏览器 E2E 与部署验证汇总、产出 `048-acceptance-review.md` |

## 任务计划

> 本章是任务索引，只写任务标题、文件链接、依赖和状态。任务 01 = 编写本 spec（不另建 task 文件）。
> `plans/048/` 已建档，链接真实可跳转；状态与 README、task 文件同步。
> 实施时按 `AGENTS.md` Gate 4「每任务 ≤2 个文件」再拆子任务，`literature-maps.js` 的两处改动串行落地避免互相覆盖。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-048（本文件） | 本文件 | — | 完成 |
| 02 | 页面级 tab：搬 createPanel DOM + `activateMapTab()` + tab 样式 | [`task-02-create-tab.md`](../plans/048/task-02-create-tab.md) | 01 | 已完成 |
| 03 | 刷新状态图标化：迁入画布工具区 + CSS 转圈图标 + 旋转反馈 | [`task-03-refresh-icon.md`](../plans/048/task-03-refresh-icon.md) | 02 | 已完成 |
| 04 | 版本号 / marker / 静态契约同步 + 浏览器 E2E + 部署验证 + 收口 | [`task-04-contracts-and-e2e.md`](../plans/048/task-04-contracts-and-e2e.md) | 03 | 已完成 |

## 评审记录

- 需求评审：`docs/sdd/reviews/048-requirement-review.md` — **通过（附意见）**（`Task(architect)` 独立只读，P0=0 / P1=0，2026-11-13）
- 技术评审：`docs/sdd/reviews/048-tech-review.md` — **通过（附意见）**（`Task(architect)` 独立只读，P0=0 / P1=0，强制约束 C1–C10，2026-11-13）
- 验收评审：`docs/sdd/reviews/048-acceptance-review.md` — **通过**（`Task(tester)` 独立只读，边界 10/10、C1–C10 10/10、产品步骤桌面 4/4 + 窄屏 4/4、人工准备度 10/10，**验收签字 R**；2026-11-13）
- 合并裁决：`docs/sdd/plans/048/runs/task-04/merge-decision.md` — **批准收口**（`Task(architect)` 独立只读，P0=0 / P1=0 / P2=1，DoD 回填项如实登记，门禁偏差 4 项披露，**架构师签字 A**；双签并列非自批）
- 代码评审：`docs/sdd/reviews/048-frontend-review.md` — **APPROVE**（`Task(frontend-reviewer)` 独立只读，P0=0 / P1=0 / P2=1，三项必查 PASS、C1–C10 10/10；末尾「二次升版复核」结论 **APPROVE 保持**）
- 单端回归：`docs/sdd/plans/048/runs/task-04/frontend-regression.md` — 初判 **FAIL**（`2 failed / 626 passed`）→ 缺陷修复 + 二次升版后集中复审 **PASS**（`628 passed / EXIT=0`，B1/B2 闭合，原 FAIL 记录逐字保留、不翻案）

## Gate 2 强制约束（C1–C10，唯一落点见 `048-tech-review.md` §六）

> 下列 10 条由技术评审「通过（附意见）」沉淀，与 spec 正文同等强制；下游 `frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester` 须逐条核对，违反任一维度视为未满足 Gate 2 通过条件。

1. **C1** tab DOM 只在 `literature-maps.js:renderShell()` 内用 `createElement` 动态生成，挂在 `.literature-map-header` 之后 / `.literature-map-grid` 之前；不在 `index.html` 新增静态 tab，不动深度研究 tablist。
2. **C2** 本视图闭包内新建 `activateMapTab()`，只改 `hidden` / `aria-selected` / `tabIndex` + 可选 `focus`，不重建面板、表单值保留；不跨文件直调 `activateResearchTab()`、不抽公共函数、不改 `research-tasks.js`；键盘 `←/→` / `Home` / `End` 同步 `tabIndex`。
3. **C3** `createPanel` 从 `listPanel` 迁入 `#literature-map-create-tabpanel`，表单节点 / `h3` / 所有 `id` / `refs` 指针逐字不变；取消 / 建图成功 / 离开视图切回「地图」tab，`test_frontend_literature_map_contract.py:270,284` 隐藏断言继续成立。
4. **C4** 保留 `id='literature-map-refresh-button'` 与 `title`，**新增** `aria-label="刷新状态"`，移除可见文字；事件仍走 `bindEvents(..., refreshButton, ...)`，不改 `selectMap` / `loadMaps` 语义，可重复点击。
5. **C5** 图标为 CSS 绘制的 `<span class="literature-map-refresh-icon">` + `::before/::after`，与 `icon-button literature-map-tool` 同族；无 `innerHTML` / 内联 SVG / 图标字体；`is-spinning` 可观察，`prefers-reduced-motion` 与禁用态不做持续动画。
6. **C6** `HEADER_ACTION_IDS` 移除 `literature-map-new-button`；`test_four_header_buttons_keep_id_text_and_hidden_contract` 的 `expected` 删 new 条目、刷新按钮改判「无可见文字 + `aria-label`」；`test_header_button_event_bindings_are_unchanged` 的 `pairs` 同步；三态 / 尺寸 / 对比度约束逐字保留，不改松 / 不删 / 不 skip / 不 xfail。
7. **C7** `test_frontend_literature_map_contract.py:277` 的 `get_by_role('button', name='新建地图')` 同步为 `get_by_role('tab', name='新建地图')`；`:278-285` 填写 / 提交 / 回 tab 流程保持可跑。
8. **C8** `literature-maps.js?v=47→48`、`literature-maps.css?v=34→36`（缺陷修复改 CSS 后二次升版，见变更日志）；两条旧版本纯属性 marker 追加到 `index.html:904-917` 末尾注释区（不放 `<head>`、无 `<script`/`<link` 字面串）；核对 `readability.py:27 MAP_CSS_VERSION` 用途并同步；`app.js?v=77` 与 styles.css 版本号不动。
9. **C9** 所有新增 CSS 选择器以 `#literature-maps-view` 为前缀，不改全局 `.secondary-button` / `.icon-button`；media query 补齐 tab 可点、表单可滚动、图标按钮 ≥44px、`prefers-reduced-motion` 降级；新建入口不再触发 `openMobilePanel('list', ...)`。
10. **C10** 分派锁定 `frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester` + `doc-updater` 补产品步骤，不派后端角色、不跑后端单端回归；`literature-maps.js` 两处改动串行落地；`node --check` 与三项自查齐全。

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-13 | 架构师（自身） | 计划模式只读勘察（用户 2 张截图；`literature-maps.js:958-1003,1076-1155,1157-1191,1346,1519-1546`；`index.html:11,73-79,208-243,739-743,903-917`；`research-tasks.js:895-922`；`literature-maps.css:27-57,187-215,348-363,448-452`；`tests/frontend/` 版本与按钮断言全扫）；编写本 spec 并置 `待确认`，同步建立 `plans/048/` 索引与 3 份 task 文档。纯文档改动，主会话代行（三处留痕：本表 / task 文档头部 / 状态台账 2026-11-13 条）。 |
| 2026-11-13 | `architect`（独立只读） | Gate 2 需求评审 `048-requirement-review.md`「通过（附意见）」与技术评审 `048-tech-review.md`「通过（附意见）」落盘；P0=0 / P1=0，10 条强制约束 C1–C10；如实指出「明确不做」条数、`aria-label` 应为新增、E2E 定位断言需同步等事实偏差。 |
| 2026-11-13 | 用户 + 主会话 | 用户「确认，你开发吧」→ `待确认 → 已确认 → 实施中`（用户同时指示开发完成后省略 PR 流程、直接推送远端；spec「明确不做」末条按该指示修订，不 force push）。按 Gate 2 意见修订本 spec：状态段、C4 `aria-label` 措辞、边界 5、评审记录、任务 02 状态 `进行中`，并新增「Gate 2 强制约束」段。Spec-047 追加范围五成果随同一交付一并推送。 |
| 2026-11-13 | `frontend-dev` · `doc-updater` | task-02/03：`renderShell()` 内动态生成页面级 tab 与 `activateMapTab()`（只改属性不重建面板、键盘切换），`createPanel` 迁入独立 tabpanel；刷新按钮迁入画布工具区改为纯 CSS 转圈图标、无可见文字、新增 `aria-label`；`doc-updater` 在「产品使用步骤」追加可执行人工验收案例并产出 `artifacts/spec-048-literature-map-tabs-manual-e2e.md`。 |
| 2026-11-13 | `frontend-dev` | task-04：升 `js?v=48` / `css?v=35` + 末尾纯属性 marker、同步 6 处精确断言、新增 12 条静态契约；随后按单端回归 FAIL 定向修复 B1（冻结基线 58→56）与 B2（390px 窄屏 `visibleMap.height` 144→152），并因 CSS 内容变化二次升版 `css?v=36`（不新增 marker、保住 `[-1]=47/34` 冻结语义）。 |
| 2026-11-13 | `frontend-tester` · `frontend-reviewer` | 单端全量初判 FAIL 如实登记（原记录保留）→ 修复后集中复审 **PASS**（628 passed / EXIT=0）；代码评审 **APPROVE 保持**（C1–C10 10/10、三项必查 PASS、P2=1）。 |
| 2026-11-13 | 主会话 | 最终候选全量回归 `4571 passed / EXIT=0 / 83.01%`；真实 Chromium + API E2E 18/18 PASS（88 个响应、2 张截图）；部署 4×200 PASS；`final-verification.md`、`deploy-verification.json`、复盘、人工验收文档、台账与三处任务状态回填；按 Gate 2 意见与二次升版同步 spec 版本口径（边界 7 / C8 / 人工验收案例改为 `v=36`）。 |
| 2026-11-13 | `tester` · `architect` | Gate 5 双签：验收「通过」签字 R（`048-acceptance-review.md`）、合并裁决「批准收口」签字 A（`runs/task-04/merge-decision.md`），非自批；状态 `实施中 → 已完成`。主会话代行的纯文档改动三处留痕（文档头部 / 本表 / 状态台账 2026-11-13 收口条）。 |

---

**六条自检**：①边界 1–10 均可写成静态契约 / 浏览器断言；②本 spec 只描述需求，实施细节下沉 `plans/048/task-*.md`；③三个 task 链接真实、依赖 02→03→04 无环；④「明确不做」划死后端 / 表单 / 其它按钮 / 全局样式；⑤执行配置五行齐全、型号读 agent 真源、架构师填自身；⑥产品使用步骤 1–4 映射边界 1/2/5/9。
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3（状态流转、changelog、三份评审真实结论、引用路径、复盘）。
