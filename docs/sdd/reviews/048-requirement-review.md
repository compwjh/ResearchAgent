# Spec-048 需求评审（Gate 2 · 独立架构师评审）

| 项 | 值 |
|---|---|
| 评审者 | `architect`（架构师评审子代理） |
| 角色 | 架构师（Architect）— Gate 2 需求评审 |
| 模型 | `hy4`（读自 `.codebuddy/agents/architect.md:6` 的 `model` 字段） |
| 分派方式 | `Task(architect)` |
| 日期 | 2026-11-13 |

## 结论

**通过（附意见）** —— 等价于「通过」，非打回。

- **P0 = 0，P1 = 0**；无阻塞项，允许进入 Gate 3（用户确认）。
- 「附意见」已按 `SDD-GATE-CHECKLIST.md:73` 全部沉淀为强制约束清单 `C1–C10`（共 10 条，正文见 `048-tech-review.md` §强制约束清单），下游 `frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester` **只认落盘文档**，本清单与 spec 正文同等强制。
- 本评审基于真实文件事实（Read/Grep 指定行），未使用「应该没问题」式结论；下列每项均附 `文件:行` 依据。

## 一、评审范围与依据（只读）

- `docs/sdd/specs/048-literature-map-create-tab-and-refresh-icon.md`（全文，`状态=待确认`）
- `docs/sdd/SDD-GATE-CHECKLIST.md` §Gate 1（:52-63）、§Gate 2（:65-80）
- 事实核对：`frontend/literature-maps.js:958-1003,1076-1191,1346,1519-1546`；`frontend/index.html:11,221-243,739-743,903-917`；`frontend/research-tasks.js:895-922`；`frontend/literature-maps.css:27-57,187-215,348-363,448-452`
- 受影响静态契约：`tests/frontend/test_frontend_map_header_actions_readability.py:27-36,235-270`；`tests/frontend/test_frontend_literature_map_contract.py:26-30,265-286`
- 角色与型号真源：`.codebuddy/agents/architect.md:6`

## 二、逐项核对

### 2.1 目标清晰、范围可测

| 维度 | 核对结论 | 依据 |
|---|---|---|
| 一句话目标 | 清晰：两件事（新建入口 tab 化 / 刷新状态图标化）、交互与刷新语义不变，边界明确 | `spec:14-16` |
| 诉求—证据—现状三栏齐全 | 三条诉求均给出现场截图证据与当前实现行号，非凭空描述 | `spec:18-24` |
| 参考实现可定位 | 明确指向深度研究 tab 结构 + `activateResearchTab()` 口径，且说明「只改 hidden/aria-selected/tabIndex、不重建面板、表单值保留」 | `spec:26`；`index.html:221-243`；`research-tasks.js:901-916` |
| 范围可测 | 「边界」段声明每条之后变成一条测试；自检①明确 1–10 均可写成静态契约 / 浏览器断言 | `spec:53`；`spec:131` |
| 状态机与准入 | `待确认`、确认前不改代码 / 不跑改状态命令，与 Gate 1/2 准入一致 | `spec:8-12`；`SDD-GATE-CHECKLIST.md:55,67` |

### 2.2 边界 10 条（逐条核对可测性与映射）

| # | 边界要点 | 核对结论 | 依据（`文件:行`） |
|---|---|---|---|
| 1 | 默认「地图」tab `aria-selected="true"`、panel 可见；「新建地图」panel `hidden` | 可测（静态契约 + 浏览器）；与参考实现默认态一致 | `spec:55`；`index.html:222-226` |
| 2 | 只切 `hidden`/`aria-selected`/`tabIndex`，不重建表单，往返保留已填值 | 可测；复用口径成立（约束 C2/C3） | `spec:56`；`research-tasks.js:901-916`；`literature-maps.js:1076-1155` |
| 3 | 取消 / 创建成功回「地图」tab，`#literature-map-create-panel` hidden，`:270,284` 断言继续 | 可测；**但需同步 `contract.py:277` 定位**（约束 C7） | `spec:57`；`test_frontend_literature_map_contract.py:270,277,284` |
| 4 | 键盘 `←/→`/`Home/End`，`role`/`aria-*` 齐全 | 可测；`tabIndex` 同步有现成范式 | `spec:58`；`research-tasks.js:912-916`；`index.html:221-223` |
| 5 | 刷新按钮在画布工具区、无可见文字、有 `title` + `aria-label`、可重复点击 | 可测；**现状无 `aria-label`，「保留」应作「新增」**（约束 C4） | `spec:59`；`literature-maps.js:969-973,1165-1179,1520-1523` |
| 6 | CSS 绘制图标、无 `innerHTML`/SVG/字体、旋转 class 可观察、≥44px 触摸目标 | 可测；纯 CSS 形状有既有先例 | `spec:60`；`literature-maps.css:448-452`；`literature-maps.js:1172-1179` |
| 7 | `?v=47→48` / `?v=34→35` + 旧值纯属性 marker + 精确 live 断言同步，不改松/不删/不 skip/xfail | 可测；末尾注释区具备兼容条件（约束 C8） | `spec:61`；`index.html:11,903-917`；`test_frontend_literature_map_contract.py:28-29` |
| 8 | readability 断言按新契约更新（移除 new、刷新改判无文字 + aria-label），其余逐字保留 | 可测；**需覆盖 `expected` 字典与 `pairs` 字典**（约束 C6） | `spec:62`；`test_frontend_map_header_actions_readability.py:31-36,236-270`；`literature-maps.css:193-215` |
| 9 | ≤760px tab 可点 / 表单滚动 / 不误开列表抽屉 / 图标 ≥44px | 可测；移动端约束现状存在（约束 C9） | `spec:63`；`literature-maps.css:348-363`；`literature-maps.js:1530` |
| 10 | `app.js`/`styles.css` 不受影响、`node --check` 通过 | 可测；「明确不做」:74 锁死版本号 | `spec:64,74`；`index.html:905` |

判断：10 条边界均可写成静态契约 / 浏览器断言，**范围可测结论成立**。

### 2.3 「明确不做」逐项核对（如实计数）

`spec:66-76` 实际为 **9 条**（非分派 prompt 预期的 11 条），逐条如下：

| # | 条目 | 核对结论 | 依据 |
|---|---|---|---|
| 1 | 不改 `backend/**` / API / 数据模型 / 生成轮询逻辑 | 与「数据模型 / 端点接口无变更」段一致 | `spec:68`；`spec:37-51` |
| 2 | 不改表单字段 / 校验 / 提交 / 建图后流程，只搬 DOM | 与「搬 DOM、id/refs 不变」一致 | `spec:69`；`spec:31` |
| 3 | 不删 / 不改 header 其它作业按钮显隐与事件 | 5 个按钮默认 `hidden=true` 现状明确 | `spec:70`；`literature-maps.js:978-1002` |
| 4 | 不改全局 `.secondary-button`/`.icon-button`，新样式限定 `#literature-maps-view` | CSS 注释已声明「不碰全局」，现状全部带前缀 | `spec:71`；`literature-maps.css:189-192,27-57` |
| 5 | 不用 `innerHTML`/图标库/内联 SVG，图标只用 CSS | 纯 CSS 图标先例存在 | `spec:72`；`literature-maps.css:448-452` |
| 6 | 不放宽任何既有断言，marker 兼容、精确同步、不改历史归档路径 | 与边界 7/8 一致 | `spec:73`；`test_frontend_map_header_actions_readability.py:246-248` |
| 7 | 不动 `app.js`/`styles.css` 版本号 | 现状 `app.js?v=77` | `spec:74`；`index.html:905` |
| 8 | 不处理 Langfuse / 404 / lint 债务 / CI 等既有非阻塞项 | 属范围外，明确 | `spec:75` |
| 9 | 不 push / 不合 main / 不 force push；Spec-047 远端任务不并入 | 与角色边界一致 | `spec:76` |

**差异处置（不伪造、不改 spec）**：数量差 2 条。本次 tab 化最易越界的两处——「不得改动 `index.html:221-243` 深度研究 tablist」「不得改动 `research-tasks.js` 及其 `?v` 冻结」——在 spec「明确不做」中未单列，本评审以强制约束 **C1 / C2** 固化（见 `048-tech-review.md`），等效补齐这两条边界，不修改 spec 原文。9 条已覆盖后端 / 表单 / 其它按钮 / 全局样式 / XSS / 断言 / 版本号 / 既有债务 / 合主干，**边界划清结论成立**。

### 2.4 产品使用步骤可操作

- 步骤 1–4 给出控件、动作、预期结果，`验收场景` 覆盖桌面 / ≤760px / 键盘 / 文字残留，`初稿只写核心场景` 并声明确认后由 `doc-updater` 补齐（`spec:80,96`）。**可操作结论成立**。
- 意见（非阻塞，转 C10）：`spec:80` 要求的「等待条件 / 失败恢复 / 产物路径」当前为初稿未补齐项，确认后须由 `doc-updater` 补齐，产品步骤 1–4 不得省略。
- 依据：`spec:78-86`；`spec:96`（执行配置 doc-updater 行）。

### 2.5 验收点可映射

- 自检⑥明确「产品步骤 1–4 映射边界 1/2/5/9」（`spec:131`）；实核：步骤1→边界1、步骤2→边界2、步骤3→边界3、步骤4→边界5、验收场景→边界4/6/9；边界 7/8/10 属静态契约 / `node --check` 校验，由 `frontend-tester` 单端静态核对承担，不依赖人工步骤。
- 依据：`spec:86,131`；`SDD-GATE-CHECKLIST.md:42-43,108-110`。
- **可映射结论成立**；边界 3 的 `contract.py:277` 定位同步缺口由 C7 补录，不破坏映射。

## 三、事实偏差与意见（均 P2，非阻塞）

1. **刷新按钮 `aria-label`**：`literature-maps.js:969-973` 现状仅有 `title='重新读取地图和作业状态'`，**无** `aria-label="刷新状态"`。spec `:34,:59` 措辞「保留 `aria-label="刷新状态"`」与代码事实不符；按「新增」执行（C4）。
2. **E2E 新建入口定位**：`test_frontend_literature_map_contract.py:277` 用 `get_by_role('button', name='新建地图')`，入口改 `role="tab"`（spec 边界4）后该定位失效；spec 边界3 仅点名 `:270,:284`（C7）。
3. **readability 契约更新范围**：spec 边界8 点名 `HEADER_ACTION_IDS`/文案断言，未点名 `:238-243 expected` 字典、`:249-252` 逐字正则、`:265-270 pairs` 字典、`:27 MAP_CSS_VERSION`（C6/C8）。
4. **明确不做计数**：实为 9 条，见 §2.3（C1/C2 补齐）。
5. **tab DOM 生成方式**：参考实现是静态 HTML（`index.html:221-243`），但文献地图整个 UI 由 `renderShell()` 动态创建（`literature-maps.js:958-1003`）并挂到 `#literature-maps-mount`（`index.html:743`）；spec「参考实现」表述易误导为改静态 HTML / 跨视图（C1）。

## 四、阻塞项 / P0 / P1 判定

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 0 | 无数据 / 接口 / 安全 / 范围失控问题 |
| P1 | 0 | 上述 5 项均为「契约点名不全 / 措辞准确性 / 实施清单」，方向正确且已有「精确断言同步、不放宽」兜底（`spec:62,73`），不构成返工级阻塞 |
| P2（意见） | 5 | 已全部转为强制约束 C1–C10 |

无阻塞项 → **不打回**。

## 五、结论生效条件

本「通过（附意见）」以 `048-tech-review.md` §强制约束清单 `C1–C10`（10 条）为满足条件的硬约束；开发 / 评审 / 测试任一环节未按该清单同步契约，视为未满足本评审通过条件。架构决策与跨端边界以落盘文档为准。
