# spec-047 追加范围四 / task-18 前端代码评审：不相关指标灰色弱化

| 项 | 内容 |
|---|---|
| **评审者** | `frontend-reviewer` |
| **角色** | 前端代码评审（独立**只读**；对应 ECC `code-reviewer`，文件边界硬约束为仅 `frontend/**`，`backend/**` 交 `backend-reviewer`）。依据 `.codebuddy/agents/frontend-reviewer.md:259-262` |
| **模型** | `hy4`（Tencent Hunyuan Hy）；依据 `.codebuddy/agents/frontend-reviewer.md:6` `model: hy4` |
| **分派方式** | 主会话独立 `Task(frontend-reviewer)` 分派（task-18）；与 `frontend-tester` 为**两次独立 `Task`、互不代行**（`plans/047/task-18-evaluation-gray-style-review.md:5`）。本评审未代行 tester 产出的回归报告，仅以自身只读 Read / Grep / 只读 Python / 定向 pytest 取证 |

> **证据时点**：2026-11-12 06:23:12 CST；HEAD `cdbb83cc`（cdbb83cc7bb8488d02f231bfe4cc9ce9019908d8，2026-11-12 05:18:57 +0800，`feat(spec-047): 集成评测 P2 与观测修复成果到主干 (#4)`）。`git diff --staged` 为空；工作树含未提交改动，评审对象为 task-17 的 8 个文件（`frontend/index.html`、`frontend/styles.css`、5 个 `tests/frontend/*.py`、新增 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`）。
>
> **裁决口径（下游只认落盘文档）**：`specs/047-...md` 文末「追加范围四 §13」强制覆盖 §3 V3 与 §4 边界 6；`reviews/047-tech-review.md`「追加范围四技术评审」§5.3/§5.4/§5.6；`reviews/047-requirement-review.md` §16；`plans/047/task-17-...md`、`task-18-...md`；`runs/task-17/implementation.md`。**未照抄 spec §3 的 `#6b6e78` 与 §4「4 处」**。
>
> **启动必读**：已按顺序 Read `progress-logging` / `frontend-patterns` / `regression-guard` / `coding-standards` 四份 `SKILL.md` 及 agent 定义；未读 `AGENTS.md` 全文（按任务要求）。

---

## 一、评审结论

**通过（Approve）**。

- **P0 = 0，P1 = 0，P2 = 1**（P2-1 为断言失败提示文案残留 `75`，非语义缺陷、不影响门禁判定，见 §3.6）。
- 四项必守（DOM 契约 / `?v=N` / XSS / CSS 作用域）**逐条 PASS**；task-18 六项必查**全部 PASS**。
- 未发现真实 P0/P1，按任务书「发现真实 P0/P1 必须如实打回」的反向约束，本评审**不打回**。
- 结论仅针对 `frontend/**` 及随附的前端静态契约测试；后端 `backend/**` 不在本评审范围。

---

## 二、四项必守逐条 PASS / FAIL（含核对依据）

### 必守 1 · DOM 契约 — **PASS**

- **核对依据**：只读 Python 精确切片 `frontend/styles.css:4406-4410`（`lines[4405:4410]`）逐字打印，5 行全部 `startswith('#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]')` = `[True, True, True, True, True]`，全部含 `#evaluation-view`。
- **双向核对**：新增/复用的 class 均既有 —— `.evaluation-metric-card` / `-label` / `-value` / `-status` / `-params > summary` 定义于 `styles.css:4390/4395/4396/4400/4404/4405`；由 `app.js:7748` `card.className`、`:7753`、`:7758`、`:7788`、`:7793`、`:7805`、`:7824` 经 `createElement` 渲染。**无新增 class**。
- CSS 侧新增的 5 个 `[data-status="needs_ground_truth"]` 钩子对应的 DOM 属性由 `app.js:7749` `card.dataset.status = String(metric.status || 'unavailable')` 渲染，新增契约 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py:137-139` 双向锁定。
- `git --no-pager diff -- frontend/app.js` **输出为空**（逐字未改）；`node --check frontend/app.js` EXIT=0；新增契约 `:138-139` 断言 `card.className` 与 `card.dataset.status` 仍在（实测 True）。

### 必守 2 · 版本号 `?v=N` — **PASS**

- `frontend/styles.css` 确实改动（+5 行，diff `@@ -4403,6 +4403,11 @@`）→ `frontend/index.html:8` 由 `styles.css?v=75` 递增为 **`?v=76`**（grep -n `?v=` 命中 `8:    <link rel="stylesheet" href="/assets/styles.css?v=76">`）。
- `frontend/app.js` 未改 → `index.html:905` `<script src="/assets/app.js?v=77"></script>` **逐字不动**，符合「未改不无谓 bump」。
- 6 处精确 live 断言逐处同步为 `76` / `["76"]`（详见 §3.2 表）；9 处冻结断言与 2 处范围断言未被误改。
- `index.html:912` 新增 `v=75` 兼容 marker 为**纯属性片段**（`<!-- Merge compatibility marker: href="/assets/styles.css?v=75" -->`），实测：行内含 `<!--`/`-->`、不含 `<link`/`<script`、位于 `907-911` 之后与 `</body>`(`:916`) 之前、`</head>` 之前 = False。

### 必守 3 · XSS — **PASS**

- **本次改动零 `innerHTML` 引入**：`app.js` git diff 为空；评测卡片渲染段（`renderEvaluationMetricCard`，`app.js:7746-7837`）实测 `innerHTML` = **False**，`textContent` 出现 **9** 次；后端文本一律 `String(...)` + `textContent`（`:7754`、`:7759`、`:7789`、`:7795`、`:7806`、`:7814`、`:7826`、`:7831`）。
- 如实说明（非本次改动、不构成发现）：`frontend/app.js` 全局存在 17 处既有 `innerHTML` 命中（`Grep pattern innerHTML|outerHTML|insertAdjacentHTML|document.write`），抽查 `app.js:323-326` 为**静态模板字符串**且用户输入 `text` 由 `:326` `textContent` 写入；`:1789`/`:6922` 为 `renderMarkdown` 且 `:6550` 注明「先净化、后 innerHTML」。均属未改动代码，按 ECC「Skip issues in unchanged code unless CRITICAL」不列为问题。
- 新增契约 `:137-139` 与本评审 §3.3 共同确认评测信息层无注入面。

### 必守 4 · CSS 作用域 — **PASS**

- `styles.css:4406-4410` 五行全部以 `#evaluation-view` 容器 ID 起始，且带 `[data-status="needs_ground_truth"]` 与既有 `.evaluation-metric-*` class 限定；**无裸写全局标签选择器**，未污染既有页面。
- 层叠正确性：基础卡片规则在 `4390-4394`，灰化规则在 `4406-4410` 之后；`4406` 与 `4393` 选择器**完全相同**（同特异性）故后者胜；`4407-4410` 比 `4395/4396/4400/4405` 多 `.evaluation-metric-card` + 属性选择器，特异性更高。只读 Python 扫描 `styles.css:4411` 之后 `evaluation-metric-*` 选择器命中数 = **0**，不存在后续覆盖。

---

## 三、task-18 六项必查逐项结论

### 3.1 DOM 契约（**PASS**）

- `styles.css:4406-4410` 5 条灰化规则**全部**带 `[data-status="needs_ground_truth"]` 限定（逐行实测 `[True×5]`），全部位于基础规则之后，`4410` 之后无覆盖规则（见必守 1 / 必守 4）。
- `app.js` 逐字未改（diff 为空），`card.dataset.status` 渲染仍在（`:7749`），**无新 class、无 `innerHTML`**。
- 层叠结果：仅 `needs_ground_truth` 卡片被灰化；`computed` / `degraded` / `unavailable` 因选择器精确匹配而不受影响。

### 3.2 版本号与契约（**PASS**）

**live 版本**：`styles.css?v=76`（`index.html:8`）、`app.js?v=77`（`index.html:905`）；只读 Python 实测 `re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)` = `['76']`，`app.js` = `['77']`。

**`v=75` 兼容 marker 与 `active_version`**：`test_frontend_map_header_actions_readability.py:298` 正则 `href="(?:/assets/)?styles\.css\?v=(\d+)"` 取**第一个**匹配，实测命中 `index.html:8` → `active_version = 76`（`:301` `> 68` PASS）。marker 在 `:912`、位于 `</head>` 之后（实测 `marker in INDEX.split("</head>")[0]` = False），**未污染 `active_version` 语义**。marker 提供的字符串 `href="/assets/styles.css?v=75" in INDEX` 实测 True，9 处冻结断言由此继续满足。

**技术评审列出的 6 处精确 live 断言逐处核实（全部同步为 76 / ["76"]）**：

| # | 文件:行 | 改动（diff 显示） | 本轮 Read 读回 | 结论 |
|---|---|---|---|---|
| 1 | `tests/frontend/test_evaluation_asset_versions.py:100` | `[75] → [76]` | `assert _live_versions("styles.css") == [76]` | ✅ |
| 2 | `tests/frontend/test_evaluation_asset_versions.py:118` | `[75] → [76]` | `assert _live_versions("styles.css") == [76]` | ✅ |
| 3 | `tests/frontend/test_evaluation_dataset_count_rendering.py:87` | `v=75 → v=76` | `INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=76">') == 1` | ✅ |
| 4 | `tests/frontend/test_evaluation_metric_grouping.py:189` | `v=75 → v=76` | 同上 `v=76` | ✅ |
| 5 | `tests/frontend/test_research_detail_actions_placement_contract.py:223` | `["75"] → ["76"]` | `assert live_css == ["76"]` | ✅（文案见 §3.6） |
| 6 | `tests/frontend/test_memory_return_global_contract.py:210` | `["75"] → ["76"]` | `assert live_css == ["76"]` | ✅（文案见 §3.6） |

**9 处 `in INDEX` 冻结断言（Grep 复核期望值仍为 `v=75`，未被误改）**：`test_frontend_button_affordance_contract.py:198`、`test_frontend_management_contract.py:79`、`test_frontend_task_d_contract.py:190`、`test_frontend_task_j_contract.py:180`、`test_memory_return_global_contract.py:191`、`test_research_detail_actions_placement_contract.py:218`、`test_research_tab_width_stability_contract.py:125`、`test_research_view_stability_contract.py:180`、`test_frontend_map_header_actions_readability.py:284`（`STYLES_VERSION = 75` 定义于该文件的 `:30`）。

**2 处范围断言（保持原样）**：`test_frontend_literature_map_contract.py:33` `int(style_versions[-1]) >= 57`、`test_frontend_map_header_actions_readability.py:301` `active_version > 68`。

**依据**：`git --no-pager diff -- frontend/index.html frontend/styles.css tests/frontend/` 中仅出现 5 个测试文件（asset_versions / dataset_count / metric_grouping / research_detail / memory_return），且每个文件 diff **仅 1–2 行期望值**；上述 9+2 处所在文件均**未出现在 diff 中**。

**app.js 相关断言未受影响**：`asset_versions:99,117`、`dataset_count:85`、`metric_grouping:188`、`research_detail:225`、`memory_return:209`、`test_evaluation_strategy_label_rendering.py:108`、新增契约 `:126` 全部为 `77` / `["77"]` / `[77]`，逐字未动（Grep 汇总 8 处命中）。

**定向只读验证**：`.venv/bin/python -m pytest -q tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` → `9 passed in 0.25s` EXIT=0；6 个断言所在文件（含 `map_header`）→ `58 passed in 0.38s` EXIT=0。

### 3.3 XSS / 反伪造 / 不降级（**PASS**）

- 无 `innerHTML`（本次改动面）；见必守 3。
- **非 `computed` 仍 `value=null → —`**：`app.js:7734-7744` `formatEvaluationMetricValue()` — `status !== 'computed' || value == null` → `'—'`；且 `:7763` 仅在 computed 且非 `—` 时绘分数条，不伪造 0 分。
- **`detail.reason` 可见**：`app.js:7803-7807` 在 `<details>` 之外渲染 `原因：${detailObject.reason}` 到 `.evaluation-metric-detail-row`（`:7798` 注释明确「不随折叠收起」）。
- **`sample_count` 真实**：`app.js:7794-7795` `Number(metric.sample_count)` → `样本数：${sampleCount}`；`:7809-7815` 另渲染判官样本数差异。
- **灰卡不隐藏 / `<details>` 可展开**：灰化块内 `opacity` / `grayscale` / `filter` / `display:none` / `visibility:hidden` 实测**全 False**；`app.js:7819-7835` 用原生 `<details>`/`<summary>`、默认收起（不设 open）、有参数才渲染。
- **四条基础规则逐字未变、未被灰化**：Python 实测 `all(rule in CSS for rule in [...])` = **True**（`#287c43` 绿 / `#c8871a`+`#fffdf7` 橙 / `#6d5dfc`+`#faf9ff` / `#b13a3a`+`#fff8f8` 红，位于 `styles.css:4391-4394`）；灰化选择器仅匹配 `needs_ground_truth`，三状态不受影响。

### 3.4 WCAG（**PASS**）

用**独立只读 Python**（自带 WCAG 2.x 相对亮度公式，不调用被评审测试模块）复算，`L = 0.2126·lin(R) + 0.7152·lin(G) + 0.0722·lin(B)`，`lin(c) = c/12.92 (c≤0.03928) 否则 ((c+0.055)/1.055)^2.4`，比值 `(L_light+0.05)/(L_dark+0.05)`：

| 组合 | 前景 | 背景 | L_fg | L_bg | **实测比值** | AA ≥4.5 |
|---|---|---|---|---|---|---|
| **V3 徽章（生效）** | `#5f626c` | `#e9eaee` | 0.122510 | 0.823423 | **5.0630:1** | **PASS** |
| **V4 标题（生效）** | `#5a5d66`（=`var(--muted-strong)`） | `#f6f6f8` | 0.109617 | 0.922817 | **6.0947:1** | **PASS** |
| 作废值对照 | `#6b6e78` | `#e9eaee` | 0.156337 | 0.823423 | 4.2330:1 | FAIL（故 §13 裁决作废） |
| V5/V7 已知基线 | `#8b8e96`（=`var(--muted)`） | `#f6f6f8` | 0.270370 | 0.922817 | 3.0365:1 | 既有基线退化，见下 |

- 变量真实值经 `frontend/styles.css:1` Grep 核实：`:root { --ink:#25272b; --muted:#8b8e96; --muted-strong:#5a5d66; ... }`，且 `:root` **未在 diff 中**（未改）；V4 名称与 `#5a5d66` 一致。
- **作废色值 `#6b6e78`**：`frontend/styles.css` 全文件出现 **0 次**、灰化块内 0 次（Python `css.count` + 切片）；新增契约 `:92` 有 `assert "#6b6e78" not in _grey_block()` 静态守卫；`:86` 断言 `color:#5f626c` 存在。
- **V5/V7 说明（非问题、不列 P1）**：`--muted`/灰底 3.0365:1，改动前淡紫底 `#faf9ff` 为 3.1306:1，均本就低于 4.5；属 spec §13 R1 与技术评审已书面裁决接受的「既有基线轻微退化」，明确「不得用 `opacity`/`filter` 补救」，V5 用 `var(--muted)` 是 task-17 §1.2 V5 指定实现。信息层（`:7792-7835`）完整保留、不丢失，故不构成打回项，移交 task-19 `getComputedStyle` 复核。

### 3.5 凑绿排查（**PASS**）

- **完整 diff 核查**：`git --no-pager diff -- frontend/index.html frontend/styles.css tests/frontend/` 只有：CSS +5 行、`index.html` 1 行升版 +1 行 marker、5 个测试文件各 1–2 行**期望值**变更。**无删断言、无改松正则、无 skip / xfail、无重算失败快照迁就实现**。
- **新增 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`（140 行，能力命名、位于 `tests/frontend/`、不含编号）断言真实可失败**：只读 importlib 加载该模块（模块级 `CSS`/`INDEX`/`APP` 已在内存中替换为违规变体，**磁盘零改动**）：
  - 基准态 9 个用例全 PASS；
  - 删除全部 5 条灰化规则 → `AssertionError 缺少 V1 灰化卡片规则`；
  - V3 色值回退 `#6b6e78` → `AssertionError V3 徽章文字（§13 裁决达标色值）`；
  - 注入 `#6b6e78` → `AssertionError §3 作废的 #6b6e78 不得出现在灰化规则中`；
  - 注入 `opacity` → `AssertionError 灰化规则不得含 opacity`；
  - 删除 computed 基础规则 → `AssertionError 基础状态规则被改动`；
  - live 版本回退 `v=76→v=75` → `AssertionError styles.css 生效版本唯一且为 76`；
  - 删除 `v=75` marker → `AssertionError v=75 纯属性兼容 marker 须恰好 1 条`；
  - 删除 `card.dataset.status` → `AssertionError needs_ground_truth 状态仍由 dataset.status 渲染`。
  - **8/8 违规变体均被拦截**，非恒真、不可静默失效（符合 `regression-guard` 第 12 条）。
- **如实记录的一处设计观察（不构成凑绿、不列问题）**：`test_wcag_aa_contrast_for_badge_and_title`（`:113-120`）复算的是**硬编码裁决常量** `#5f626c`/`#e9eaee` 与 `#5a5d66`/`#f6f6f8`，单独把 CSS 色值改成 `#6b6e78` 时该用例仍 PASS（内存实测「仍 PASS」）。但其 `:118` 注释已写明意图是「锁定到 §13 裁决复算值，防止公式写错却仍 >=4.5 的恒真通过」，且 task-17 §1.4 本就要求「用 WCAG 公式复算」；实际 CSS 色值由同文件 `test_v1_to_v6_grey_colours`（`:86` 断言 `color:#5f626c`）与 `test_deprecated_badge_colour_is_absent`（`:92`）锁定，**组合门禁有效**，整体仍能拦截实现退化。
- `.venv/bin/python scripts/check_test_layout.py` EXIT=1，报错 5 项**均为仓库既有 tracked 文件**（`tests/conftest.py`、`tests/evaluation/test_task03_reproducibility.py`、`test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py`）；新增契约文件**未出现在报错列表**（与 `runs/task-17/implementation.md` 自测一致）。本评审未改这些文件凑绿。

### 3.6 额外核实（主会话读回发现）— **明确意见：应同步，但列 P2（非阻塞），不影响通过结论**

**事实（真实读回）**：

- `tests/frontend/test_research_detail_actions_placement_contract.py:223`：`assert live_css == ["76"], f"生效 styles.css 版本唯一且为 75：{live_css}"`
- `tests/frontend/test_memory_return_global_contract.py:210`：`assert live_css == ["76"], f"生效 styles.css 版本唯一且为 75：{live_css}"`

两行均为本次 diff **直接改动的行**（`["75"] → ["76"]`），但行内 f-string **失败提示**仍写 `75`，属本次改动引入的文案不一致。同类（未改动行，仅建议一并整理）：`test_evaluation_metric_grouping.py:187` 函数名 `test_live_asset_versions_bumped_to_77_and_75`、`test_evaluation_dataset_count_rendering.py:86` 注释「合并远程 main 后 live CSS 为 v=75」。

**判定意见**：

1. **不是语义缺陷、不影响门禁结论**：f-string 是 `assert` 的 message，仅在断言失败时展示，不参与判定；断言值 `["76"]` 正确，6 处精确断言全绿（定向 pytest 58 passed）。因此**不构成 P0/P1，不打回**。
2. **但确实属于应同步的文案缺陷，建议列 P2**：本项目「下游只认落盘文档」，§13 与技术评审 §5.6 已把 live 口径钉死为 `76`；失败信息残留 `75` 会在回归红灯时误导排查者以为仍处 `v=75` 基线、与 §4 边界 6 的旧「4 处」口径混淆，属可维护性债。建议在 task-19 或收尾时把两处 message 改为 `76`，并顺手统一上述函数名/注释。
3. **不误报的边界**：`test_research_detail_actions_placement_contract.py:218`、`test_memory_return_global_contract.py:191`、`test_research_tab_width_stability_contract.py:125` 等 **冻结断言**的文案仍写 `?v=75` 是**正确**的（它们断言的字符串本就是 `href="/assets/styles.css?v=75"`，靠新增 marker 满足，技术评审 §5.4/§5.6 明确「不改期望值」），**不属于缺陷**，不在 P2 范围内。
4. 按 `confidence-based filtering`，未改动行的历史文案不计为本次新发现，仅作为同类建议提及。

---

## 四、问题清单（P0 / P1 / P2）

### P0（阻断）— 0 项

无。

### P1（须修复后再验收）— 0 项

无。四项必守与六项必查均基于真实文件核对通过；未发现 CRITICAL / HIGH 级问题。

### P2（非阻塞，建议后续同步）— 1 项

**[P2-1 / LOW] 6 处精确断言中 2 处的失败提示文案仍写 `75`，与断言值 `["76"]` 不一致**

- `File: tests/frontend/test_research_detail_actions_placement_contract.py:223`
- `File: tests/frontend/test_memory_return_global_contract.py:210`
- Issue：本次 diff 把 `["75"]` 同步为 `["76"]`，但同一行的 f-string message 仍为「生效 styles.css 版本唯一且为 75」。断言判定正确、不影响门禁；仅在断言失败时输出误导性诊断，与 §13 / 技术评审 §5.6 的 `76` 口径冲突。
- Fix（建议，非阻断）：把两处 message 的 `75` 改为 `76`；可一并整理 `test_evaluation_metric_grouping.py:187` 函数名与 `test_evaluation_dataset_count_rendering.py:86` 注释。**本评审只读，未作任何修改**。
- 同类但**不算缺陷**：`:218` / `:191` / `:125` 等冻结断言文案（其断言字符串本就是 `v=75`）。

### 不计为问题的如实记录（观察项，非缺陷）

1. **V5/V7 对比度 3.0365:1**：改动前 3.1306:1，属 spec §13 R1 已裁决接受的既有基线轻微退化；V5 用 `var(--muted)` 为 task-17 §1.2 指定；明确禁用 `opacity`/`filter` 补救，信息层不丢失 → 不列 P1，移交 task-19 `getComputedStyle` 复核。
2. **`app.js` 全局 17 处既有 `innerHTML`**：均为未改动代码（静态模板 / DOMPurify 净化后 markdown / 按钮图标），评测渲染段全 `textContent` → 按 ECC「Skip unchanged code」不列问题。
3. **新增契约的 WCAG 用例复算硬编码常量**：其意图为锁定公式复算值；实际 CSS 色值由同文件另 2 个静态断言锁定，组合门禁经 8 类内存变体验证有效 → 不构成凑绿。
4. **`check_test_layout.py` EXIT=1**：5 项报错均为既有 tracked 文件，新文件不在列表；自测已如实回报，本评审未改测试凑绿。
5. **`node --check frontend/app.js` EXIT=0**、`git diff --check` EXIT=0、`git diff -- frontend/app.js` 为空。

---

## 五、ECC Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 1     | note   |

> 项目口径映射：P0=0 / P1=0 / P2=1（P2-1 ↔ LOW）。

**Verdict: APPROVE — 0 CRITICAL / 0 HIGH；1 项 LOW（P2-1 断言提示文案）非阻塞，建议后续同步，不需要打回。**

---

## 六、纪律声明

- 本评审为**独立只读评审**：未写任何业务代码 / 测试 / 配置 / spec / 状态台账 / 任务文档 / 评审历史；仅新建本报告 `docs/sdd/reviews/047-frontend-gray-style-review.md` 与本角色进展日志。
- 未执行 `git commit` / `push` / 合 `main` / `reset` / `stash` / `clean` / `add`；仅执行 `git status` / `git diff` / `git log` / `git rev-parse` 等只读命令与 `node --check`、`.venv/bin/python -m pytest -q`（定向）、`.venv/bin/python scripts/check_test_layout.py`、只读 Python 复算。
- 只读 Python 的「违规变体」仅在**内存**中替换 `CSS`/`INDEX`/`APP` 模块常量并复原，**磁盘零改动**；WCAG 比值用独立公式复算，未调用被评审的测试模块；定向 pytest 未使用 `-k` 过滤、未 skip / xfail、未改任何测试。
- 所有判定基于 Read / Grep / 只读 Python 打开的**真实文件**，每条附 `文件:行`；四项必守逐条给 PASS/FAIL 并附核对依据；未凭 spec 描述或回传摘要下结论，未使用「应该没问题」式表述。
- 文件边界：仅评审 `frontend/**` 与随附的前端静态契约测试；`backend/**` 交 `backend-reviewer`。未代行 `frontend-tester` 的回归报告，未读 `AGENTS.md` 全文（按任务要求）。
- 未翻案 / 未改写 spec §13、技术评审、需求评审 §16 的任何既有结论。

## 七、证据命令清单（本轮真实执行）

```
git status --short ; git diff --staged --stat ; git diff --stat ; git log --oneline -5
git rev-parse --short HEAD ; git log -1 --format='%H %ci %s'
grep -n "?v=" frontend/index.html
git --no-pager diff -- frontend/app.js                     # 输出为空
node --check frontend/app.js                              # EXIT=0
git diff --check                                          # EXIT=0
git --no-pager diff -- frontend/index.html frontend/styles.css tests/frontend/
.venv/bin/python -m pytest -q tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py            # 9 passed EXIT=0
.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py ... test_frontend_map_header_actions_readability.py  # 58 passed EXIT=0
.venv/bin/python scripts/check_test_layout.py              # EXIT=1（5 项既有基线，新文件不在列表）
只读 Python：styles.css:4406-4410 精确切片 / 4411+ 覆盖扫描 / :root 变量 / index.html active_version 正则 / WCAG 相对亮度复算 / importlib 内存变体 9 类
Grep：innerHTML|outerHTML|... (app.js)、card.dataset.status、--muted-strong:|--muted: (styles.css)、STYLES_VERSION|active_version|> 68|>= 57|styles.css?v=75 (tests/frontend)、== ["77"]|app.js?v=77 (tests/frontend)
```
