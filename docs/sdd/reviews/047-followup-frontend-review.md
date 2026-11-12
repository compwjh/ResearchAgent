# Spec-047「追加范围五：遗留项清理」前端 follow-up 代码评审报告

| 文档项 | 值 |
|---|---|
| 评审者 | `frontend-reviewer` |
| 角色 | 前端代码评审 |
| 模型 | `hy4`（读 `.codebuddy/agents/frontend-reviewer.md:6` frontmatter `model: hy4`） |
| 分派方式 | `Task(frontend-reviewer)` |
| 评审对象 | Spec-047 追加范围五 / task-22 前端改动 |
| 评审范围 | `frontend/**`（`index.html` / `styles.css` / `app.js`）与 `tests/frontend/` 前端契约测试 |
| 对比基线 | 工作区 vs `HEAD`（`git diff HEAD`），HEAD 提交 `42bbc188` |
| 签字日期 | 2026-11-12 |

> **独立性**：本报告为独立 follow-up 评审产物，**不覆盖**历史归档 `docs/sdd/reviews/047-frontend-gray-style-review.md`（23722 字节，本次未改，保留原样）。
> **只读评审**：未修改任何业务代码、spec 文件或其它评审文档；本次唯一新增产物为本报告与进展日志。
> **边界**：diff 中的 `backend/**`、`conftest.py`、spec 文本、测试改名/迁移不属于前端评审范围，交 `backend-reviewer` 等角色，本报告不对其下结论。
> **纪律**：以下每条判定均基于 Read/Grep/Bash 打开的真实文件事实，附 `文件:行`；未凭 spec 描述或回传摘要下结论。

---

## 0. 验证依据（实际执行的命令与结果）

| # | 命令 | 结果 |
|---|---|---|
| V1 | `git diff HEAD --stat` / `git status --short` | 16 文件变更；前端仅 `index.html`(6) / `styles.css`(5) 修改，`app.js` 无 M 标记 |
| V2 | `git diff HEAD -- frontend/index.html frontend/styles.css` | 见 §1.1 / §1.2（逐行核对） |
| V3 | `git diff HEAD -- frontend/app.js` | 空输出 |
| V4 | `node --check frontend/app.js` | `NODE_CHECK_EXIT=0` |
| V5 | `git diff --quiet HEAD -- frontend/app.js` | `APP_JS_IDENTICAL_TO_HEAD`（工作区与 HEAD 字节一致） |
| V6 | `git diff HEAD -- tests/frontend/` | 6 文件断言同步 + R1 段新增（见 §1.4） |
| V7 | 定向 pytest（8 个指定契约文件） | `77 passed in 0.57s`，`PYTEST_EXIT=0` |
| V8 | 全量 `tests/frontend/` 分段补跑 | SEG1 `241 passed` + SEG2 `236 passed` + SEG3 `139 passed` = **616 passed / 0 failed**，三段 `EXIT=0`（单次全量调用因工具时限中断于 46%，全程无 `F`/`E`，故改分段补跑） |
| V9 | `python3` 独立复算 WCAG 与静态核对 | 相对亮度 / 对比度 / 84 处 `in INDEX` 断言，见 §4 / §5 |
| V10 | Grep 双向核对（`:root` / 变量 / 三状态 / 红线 / marker / head） | 见 §2 各条 |

启动必读：`.codebuddy/skills/progress-logging/SKILL.md`、`frontend-patterns/SKILL.md`（项目 Addendum L664-L672）、`regression-guard/SKILL.md`（前端 1-4 条 L501-L505、第 12 条「断言不得恒真/静默失效」L520-L523）、`coding-standards/SKILL.md` 已按顺序读完。

---

## 1. 改动事实（逐行，基于 `git diff HEAD`）

### 1.1 `frontend/index.html`（2 处 live 替换 + 2 行新增注释 marker）

| 行 | 变更 | 核对结论 |
|---|---|---|
| `:8` | `<link rel="stylesheet" href="/assets/styles.css?v=76">` → `?v=77` | live CSS 升版，位于 `<head>`（`:3`–`:86`）内 |
| `:902` | `<script src="/assets/research-tasks.js?v=25">` → `?v=26` | live 升版 |
| `:905` | `<script src="/assets/app.js?v=77"></script>` | **上下文行，未改动**（app.js 保持 77） |
| `:913` | 新增 `<!-- Merge compatibility marker: src="/assets/research-tasks.js?v=25" -->` | 纯属性片段 marker |
| `:914` | 新增 `<!-- Merge compatibility marker: href="/assets/styles.css?v=76" -->` | 纯属性片段 marker |
| `:86` | `</head>` | 两条新 marker 均在 `:913`/`:914`，在 `</head>` 之后 |

### 1.2 `frontend/styles.css`（1 处替换 + 3 行新增，全部位于 4406-4413 灰化连续块）

- `:4409` `.evaluation-metric-value` 的文字色 `var(--muted)` → `var(--muted-strong)`（替换）。
- `:4411` 新增 `.evaluation-metric-samples`、`:4412` 新增 `.evaluation-metric-detail-row`、`:4413` 新增 `.evaluation-metric-params`，三条均为 `color: var(--muted-strong);`。
- 4 条规则**全部**以 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 开头（`git diff HEAD -- frontend/styles.css | grep '^+'` 命中 4 行，无其它新增行）。
- `:1` `:root` 定义在 diff 之外（`:root { --ink: #25272b; --muted: #8b8e96; --muted-strong: #5a5d66; ... }`），**未改**。
- `:4391`/`:4392`/`:4394` 三状态基础规则在 diff 之外，逐字未变。

### 1.3 `frontend/app.js`

`git diff HEAD -- frontend/app.js` 无输出（V3），`git diff --quiet` 返回一致（V5），`node --check` EXIT=0（V4）。`git diff HEAD -- frontend/ | grep -E '^\+.*(innerHTML|className|class=)'` 无命中（`NO_NEW_INNERHTML_OR_CLASS_IN_DIFF`）。`app.js` 中现存的 `innerHTML`（`:25/:323/:516/:1789/:4208/:4213/:6922` 等）均为 HEAD 既有、本次未动，且集中在 Markdown 渲染 / 静态骨架，不涉及本次灰卡。

### 1.4 `tests/frontend/`（6 文件，断言同步真实）

| 文件 | 改动 | 是否同步 |
|---|---|---|
| `test_evaluation_asset_versions.py:100,118` | `_live_versions("styles.css") == [76]` → `[77]`（2 处） | 是 |
| `test_evaluation_dataset_count_rendering.py:87` | `INDEX.count('<link ... styles.css?v=76">') == 1` → `?v=77`；`:86` 注释同步 live 口径 | 是 |
| `test_evaluation_irrelevant_metric_gray_contract.py:89,90` | `var(--muted-strong)` 计数 2→3、`var(--muted)` 1→0；`:36-37` 新增 `_live_versions("research-tasks.js")` 分支；`:127` `[76]`→`[77]`；`:139-192` 新增 R1 段（4 项 `GREY_TEXT_CHILDREN` + `_all_grey_rules()` + 2 个测试） | 是 |
| `test_evaluation_metric_grouping.py:187,189` | 函数名 `..._77_and_75`→`..._77_and_76`；`styles.css?v=76`→`?v=77` | 是（文案见 §7 P2-1） |
| `test_memory_return_global_contract.py:210` | `live_css == ["76"]` → `["77"]` | 是（文案见 §7 P2-1） |
| `test_research_detail_actions_placement_contract.py:223` | `live_css == ["76"]` → `["77"]` | 是（文案见 §7 P2-1） |

---

## 2. 四项必守逐条 PASS/FAIL

### 2.1 DOM 契约 — **PASS**

核对依据（Grep 命令与命中行）：

- **CSS 钩子正向**：`git diff HEAD -- frontend/styles.css | grep '^+'` → 4 行，全部含 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 前缀，作用于 `.evaluation-metric-value`(`:4409`)、`-samples`(`:4411`)、`-detail-row`(`:4412`)、`-params`(`:4413`)。这四个 `-value/-samples/-detail-row/-params` 文字色规则**全部**带状态限定，无一条裸写。
- **反向（class 在基础 CSS 真实存在）**：`grep -n -E '#evaluation-view \.evaluation-metric-(value|samples|detail-row|params) \{' frontend/styles.css` → `:4396`(`var(--ink)`)、`:4401`(`var(--muted)`)、`:4403`(`var(--muted)`)、`:4404`(`var(--muted)`)，逐字未变；`test_app_js_metric_card_dom_contract_unchanged`（`test_evaluation_irrelevant_metric_gray_contract.py:139-141`）仍断言 `card.className = 'evaluation-metric-card'` 与 `card.dataset.status = String(metric.status`，定向 pytest 通过。
- **`:root` 变量定义未改**：`python` 扫描 `--muted/--muted-strong/--ink` 赋值行 → 仅 `styles.css:1`；该行不在 diff 中。`--muted-strong: #5a5d66` 真实存在，是 §4 WCAG 复算的前提。
- **三状态逐字未变**：`grep -n -E 'data-status="(computed|degraded|unavailable)"' frontend/styles.css` → `:4391` computed 绿 `#287c43`、`:4392` degraded 橙 `#c8871a`、`:4394` unavailable 红 `#b13a3a`（另有 `:4057`/`:4069` 属 `#research-view`，同样未动）。既有 `test_base_status_rules_are_unchanged`（`:104-111`）逐字断言这 4 条，全量 616 passed 覆盖。
- **未引入 opacity/filter/display:none**：`python` 扫描 `4406-4413` 连续 8 行（lower+去空格）→ 命中 `opacity/grayscale/filter/display:none/visibility:hidden` = `NONE`；块内精确 `var(--muted)` = 0、`var(--muted-strong)` = 6。既有 `test_grey_block_has_no_hiding_or_fading`（`:97-100`）通过。
- **`app.js` 未改**：V3/V4/V5，无新增 class / `innerHTML`。

### 2.2 版本号 `?v=N` — **PASS**

- 改了 `styles.css` → `index.html:8` live `styles.css?v=76→77`；`index.html:902` live `research-tasks.js?v=25→26`；`app.js?v=77`（`:905`）未动（符合 spec §4 D2「`app.js?v=77` 不动」）。
- 6 处精确 live 断言全部同步为 `77`/`["77"]`（`grep -rn -E '== \[77\]|== \["77"\]|count\(.*v=77'` 命中见 §1.4 与 `[J]`）；`grep -rn -E '\[76\]|\["76"\]|== 76'` 无残留（`NO_STALE_LIVE_ASSERT`）。
- 两条新 marker 均为**纯属性片段**，降级保留 `v=25`/`v=76` 供历史 `in INDEX` 冻结断言继续通过（§5）。

### 2.3 XSS — **PASS**

- diff 新增行无 `innerHTML` / 字符串拼接 DOM（`git diff HEAD -- frontend/ | grep -E '^\+.*(innerHTML|className|class=)'` 无命中）；`app.js` 字节未变（V5）。
- 两条新 marker 是 `<!-- ... -->` 纯注释（`index.html:913,914`），经 `python` 逐行核对：`<!--`/`-->` 均在、`含<script=False`、`含<link=False`，不参与 HTML 解析、不进入 DOM、不触发任何脚本/样式加载。
- 既有 XSS 底线用例未回归：`test_research_task_search.py:30-34`（`innerHTML not in RESEARCH`、含 `textContent`/`.value`/`replaceChildren()`）在全量 616 passed 内通过。

### 2.4 CSS 作用域 — **PASS**

`git diff HEAD -- frontend/styles.css | grep '^+'` 的 4 行选择器全部以 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 起头，作用域限定在评测视图容器 + 特定状态卡片内；无裸写全局标签选择器、无 `:root` 级改动、无 `*` 通配。非灰卡（`:4396/:4401/:4403/:4404`）与其它视图规则不受影响。

---

## 3. 三项必查逐项结论（文件:行依据）

| 必查项 | 结论 | 核心依据 |
|---|---|---|
| **DOM 契约** | **PASS** | `styles.css:4409,4411,4412,4413` 四条灰卡文字色规则全部带 `#evaluation-view ...[data-status="needs_ground_truth"]` 限定；`:1` `:root` 未改（`--muted-strong: #5a5d66` 真实定义）；`:4391/:4392/:4394` computed 绿 / degraded 橙 / unavailable 红逐字未变；`:4406-4413` 连续 8 行无 `opacity`/`filter`/`display:none`；`frontend/app.js` 与 HEAD 字节一致、`node --check` EXIT=0、无新增 class / `innerHTML`。 |
| **`?v=N` 版本** | **PASS** | `index.html:8` `styles.css?v=77`、`:902` `research-tasks.js?v=26`、`:905` `app.js?v=77`；两条新 marker 在 `:913`/`:914` 且位于注释内、不含 `<script`/`<link` 字面串；`</head>` 在 `:86`，marker 在 head 之外，首个 `href=...styles.css?v=` 仍为 `:8` 的 77（`re.search` 实测 = 77 > 68），未污染 `active_version`（`test_frontend_map_header_actions_readability.py:298-303`）；6 处精确 live 断言同步为 77，9 处 `in INDEX` 冻结断言由 marker/历史注释满足，未删测试 / 未 skip / 未 xfail / 未放宽容错（§6）。 |
| **XSS** | **PASS** | 无新增 `innerHTML` 或字符串拼接 DOM（diff 新增行 grep 无命中）；marker 为 `:913`/`:914` 纯 HTML 注释，不参与解析；`app.js` 零改动。 |

---

## 4. WCAG 独立复算（`#5a5d66` 对 `#f6f6f8`）

复算不照抄测试：`test_evaluation_irrelevant_metric_gray_contract.py:44-58` 的 `_linearize` 用阈值 `0.03928`（WCAG 2.0 早期文本），本次用现行修正阈值 `0.04045` 独立实现，二者对本例所有通道（均 > 阈值）走同一幂分支，故结果一致。

1. **通道分解（sRGB 8bit → 0..1）**
   - FG `#5a5d66` = `(90, 93, 102)/255`；BG `#f6f6f8` = `(246, 246, 248)/255`。
2. **线性化** `lin(c) = c/12.92`（`c ≤ 0.04045`）否则 `((c+0.055)/1.055)^2.4`；本例 6 个通道全部走幂分支。
3. **相对亮度** `L = 0.2126·lin(R) + 0.7152·lin(G) + 0.0722·lin(B)`
   - `L(FG #5a5d66) = 0.1096167008`
   - `L(BG #f6f6f8) = 0.9228167558`
4. **对比度** `= (L_light + 0.05) / (L_dark + 0.05)`
   - `= (0.9228167558 + 0.05) / (0.1096167008 + 0.05)`
   - `= 0.9728167558 / 0.1596167008`
   - `= 6.0947053213 ≈ **6.0947:1**`
5. **判定**：`6.0947 ≥ 4.5` → WCAG 2.x AA 正文对比度达标（**PASS**），与 spec §13 裁决锁定值 `6.0947:1`（`test_evaluation_irrelevant_metric_gray_contract.py:122` `abs(title - 6.0947) < 0.02`）一致。该值同时是新增 R1 规则（`-value/-samples/-detail-row/-params` 用 `--muted-strong`）落在灰卡浅灰底 `#f6f6f8`（`:4406`）上的实际对比度。

> 附带核对：`--muted`（`#8b8e96`）对 `#f6f6f8` 的对比度约 3.0:1 量级，未达 AA；这正是 D1 把 4 项从 `var(--muted)` 提到 `var(--muted-strong)` 的原因，改动方向正确。

---

## 5. 版本与 marker 安全性核对表

| 检查项 | 事实（文件:行） | 结论 |
|---|---|---|
| live `styles.css?v=77` | `index.html:8`（`<head>` 内，`</head>` 在 `:86`） | PASS |
| live `research-tasks.js?v=26` | `index.html:902` | PASS |
| live `app.js?v=77` 不动 | `index.html:905`（diff 上下文行） | PASS |
| marker `src="/assets/research-tasks.js?v=25"` | `index.html:913`，注释内=True、含 `<script`=False、含 `<link`=False、在 head 内=False | PASS |
| marker `href="/assets/styles.css?v=76"` | `index.html:914`，注释内=True、含 `<script`=False、含 `<link`=False、在 head 内=False | PASS |
| 两条 marker 各恰好 1 条 | `python` 逐行计数命中行 `[913]` / `[914]`；R1 `test_r1_grey_text_wcag_and_live_asset_versions`（`:183-191`）断言 `len(lines) == 1` 通过 | PASS |
| 未插入 `<head>` / 不污染 `active_version` | `</head>` 在 `:86`；marker 在 `:913/:914`；`re.search(r'href="(?:/assets/)?styles\.css\?v=(\d+)"', INDEX)` 首个匹配 = `77` > 68；`test_frontend_map_header_actions_readability.py:298-303` 通过 | PASS |
| 6 处精确 live 断言同步为 77 | `test_evaluation_asset_versions.py:100,118`；`test_evaluation_dataset_count_rendering.py:87`；`gray_contract.py:127,180`；`metric_grouping.py:189`；`memory_return_global_contract.py:210`；`research_detail_actions_placement_contract.py:223`（含 R1 新增 `:180` 与 `research-tasks.js == [26]` `:182`）；`[L]` 无残留 76 | PASS |
| 9 处 `in INDEX` 冻结断言靠 marker 满足 | `research-tasks.js?v=25`→`:913`（`test_paper_issue_ui_contract.py:65`、`test_research_view_stability_contract.py:182`）；`research-tasks.js?v=22`→`:906`（`test_research_task_search.py:38`）；`styles.css?v=75`→`:912`（多处冻结断言）；`styles.css?v=70`→`:909`；`app.js?v=72/74/75`→`:909/:911/:908`；`styles.css?v=76`→`:914`（R1 新增）。静态核对 **84/84** 非 f-string `in INDEX` 字面量断言命中 INDEX，28 行 f-string 断言由 616 passed 覆盖 | PASS |
| 未删测试 / 未 skip / 未 xfail / 未放宽容错 | 6 文件 HEAD→WORK `def test_` 计数 `6/5/9/15/15/6` → `6/5/11/15/15/6`（只增不减），`assert` 计数 `24/36/27/71/64/28` → `24/36/37/71/64/28`；diff 中被删的 assert 行均为 76→77 成对替换（无净删除）；`NO_RELAXATION_ADDED`；6 文件内无 `pytest.mark.skip`/`xfail`（`[K]` 唯一命中是 `:231`「本用例不 skip」注释） | PASS |

---

## 6. 反伪造核对（D1 / D2 静态契约覆盖与双向同步）

- **D1（灰卡 4 项文字色）**：「只改实现不改断言」不成立——`styles.css:4409,4411-4413` 改了 4 条规则，`test_r1_four_grey_card_text_rules_use_muted_strong`（`gray_contract.py:169-174`）用 `_all_grey_rules()`（从 `#c9cbd3` 起连续 8 行）对 `GREY_TEXT_CHILDREN` 4 项逐一断言**精确规则字符串**存在，且断言块内 `var(--muted)` 缺席；「只改测试不改实现」不成立——CSS 真实新增/替换已由 diff 与 §2.1 Grep 证实。实现与断言**双向同步**。非灰卡基础规则 `:4396/:4401/:4403/:4404` 逐字未变（D1 后半句「非灰卡保持原样」实现正确）。
- **D2（CSS 升版 + marker）**：「只改实现不改断言」不成立——6 个测试文件精确 live 断言全部 76→77，且 R1 新增 `_live_versions("research-tasks.js") == [26]` 与两条 marker 的 `len(lines)==1`/注释内/无标签字面串断言；「只改测试不改实现」不成立——`index.html:8,902,913,914` 真实改动。断言未放宽：新断言是**精确等值**（`== [77]`、`count(...) == 1`、精确规则子串），WCAG 断言 `>= 4.5` 另有 `abs(ratio - 6.0947) < 0.02` 锁定（`:122`），规避 regression-guard 第 12 条「恒真断言」反例。
- **静态契约有效性**：`test_five_status_scoped_grey_rules_exist`（`:62-67`）仍精确锁定原 5 条状态限定规则；`test_v1_to_v6_grey_colours`（`:82-90`）计数从 2/1 改为 3/0（更严格）；`_all_grey_rules()` 覆盖新增 3 行后共 8 行。R1 的 4 个精确规则字符串匹配**间接**保证新增 3 行不含 `opacity`/`filter`（多一个字符即不匹配），与 §2.1 的直接扫描结论一致。
- **结论**：未发现「只改测试不改实现」或「只改实现不改断言」缺口；未发现断言恒真 / 静默失效 / 放宽容错。全量 616 passed 佐证。

---

## 7. P0 / P1 / P2 缺陷清单

### P0（阻断） — 0 项

无。三项必查与第四项 CSS 作用域全部 PASS，无 CRITICAL/HIGH。

### P1（须修复） — 0 项

无。

### P2（信息性观察 / 非打回） — 2 项

- **P2-1（LOW）失败提示文案与函数名口径滞后于最终 live 版本**
  - `tests/frontend/test_memory_return_global_contract.py:210` 与 `tests/frontend/test_research_detail_actions_placement_contract.py:223`：断言已同步为 `== ["77"]`，但失败提示 f-string 仍为 `f"生效 styles.css 版本唯一且为 76：{live_css}"`；`tests/frontend/test_evaluation_metric_grouping.py:187` 函数名 `test_live_asset_versions_bumped_to_77_and_76` 与函数体两条 `count(...) == 1`（均为 `?v=77`，`:188-189`）不一致。
  - 依据：spec §4 B1（`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:1252`）**明确要求**「2 处 f-string 失败文案『为 75』→『为 76』、函数名 `..._77_and_75 → ..._77_and_76`」，实现**逐字符合 spec 字面契约**；但同 §4 D2（`:1256`）把最终 live 升到 `?v=77`，导致文案中的「76」滞后一轮。
  - 影响：仅失败时提示字符串 / 测试命名的可读性，断言本身正确、功能与闸门不受影响（616 passed）。判为 LOW 观察项，建议后续统一到 77，**不构成打回**。

- **P2-2（LOW）D1 后半句「非灰卡保持 `var(--muted)`」未显式锁静态断言**
  - `test_r1_four_grey_card_text_rules_use_muted_strong`（`gray_contract.py:169-174`）精确锁定 4 条灰卡规则并断言块内无 `var(--muted)`，覆盖 D1 前半句；但未对 `styles.css:4396`（`--ink`）、`:4401/:4403/:4404`（`var(--muted)`）逐字设断言。
  - 实现事实：这 4 条基础规则逐字未变（`git diff HEAD -- frontend/styles.css` 仅触及 4406-4413），非灰卡行为正确；既有 `test_base_status_rules_are_unchanged`（`:104-111`）锁的是卡片边框状态规则，非文字色基础规则。
  - 影响：若后续误改基础文字色规则，现有 R1 断言不会拦截，属测试覆盖建议（可补一条 `assert '#evaluation-view .evaluation-metric-samples { margin: 0; color: var(--muted); ... }' in CSS` 之类的逐字断言）。非实现缺陷，**不构成打回**。

---

## 8. ECC Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 2     | note   |

`P0 = 0 / P1 = 0 / P2 = 2`（2 项均为信息性观察，非缺陷、非打回）。

Verdict: **APPROVE** — 无 CRITICAL / HIGH 问题；三项必查（DOM 契约 / `?v=N` / XSS）与第四项 CSS 作用域全部 PASS，WCAG 复算 6.0947:1 达标，全量前端契约测试 616 passed / 0 failed，实现与断言双向同步、无伪造缺口。2 项 LOW 建议后续统一，不阻断合并。

---

## 9. 最终结论

**APPROVE**

评审范围 `frontend/**` 与 `tests/frontend/` 内的改动符合 spec §4 A1/A2/B1/D1/D2/D3 与 spec §2「明确不做」的全部红线（不改 app.js、不改 `:root`、三状态配色逐字不变、不用 opacity/filter/display:none、不删测试 / 不 skip / 不 xfail / 不放宽断言）。无 P0、无 P1；P2 两项为可读性与测试覆盖建议，不影响功能、安全与闸门。

签字：`frontend-reviewer`（角色：前端代码评审；模型：`hy4`；分派：`Task(frontend-reviewer)`）
签字日期：**2026-11-12**

评审报告路径：`docs/sdd/reviews/047-followup-frontend-review.md`
进展日志路径：`.codebuddy/agent-logs/spec-047/task-22/frontend-reviewer/20261112-000333.md`
