# spec-047 追加范围四 · 合并到远程 `main` 审批结论（architect 独立 approval）

> 本文件为「把 spec-047 追加范围四（不相关指标灰色弱化）成果合并到远程 `main`」的**独立只读审批结论**；下游只认本落盘文档。
> 与 `runs/task-19/merge-decision.md`（上一轮「批准收口」签字 A）严格区分：那一份批准的是**本地收口**，且 §三签字栏明确「本次不 push、不合 main、不 force push；`origin/main` 保持 `cdbb83cc`」；本份批准的是**合并到远程 `main`**，由本轮独立出具、非实现方自批。

## 头部四项与证据时点

| 项 | 内容 |
|---|---|
| **评审者** | `architect`（架构师·独立 Code Review / 开发主管批准者） |
| **角色** | 架构师（PR 合并裁决 / 独立 approval；与 `tester` 验收签字 R、`frontend-reviewer` 代码评审互不代行、不代签） |
| **模型** | `Tencent Hunyuan Hy`（`hy4`；唯一真源 `.codebuddy/agents/architect.md:6 model: hy4`） |
| **分派方式** | 用户独立授权的只读审查分派（task-19 / architect-merge-approval）：禁止改任何代码 / 测试 / 配置 / spec 正文 / 状态台账 / 评审历史；禁止 `git commit / push / 合 main / reset / stash` |

> **证据时点**：2026-11-12 16:52:53 CST 起，本轮独立只读审查窗口；报告落盘 2026-11-12。
> **git 只读基线**：分支 `feature/spec-047-unrelated-metric-greyout`（`git rev-parse --abbrev-ref HEAD`）；HEAD = `6406609aa166a1482c613dcd5618a153aca75084`（`git log -1 --oneline` = `6406609a feat(spec-047): 不相关指标灰色弱化并按 WCAG 裁决收口`）；基线 `origin/main = cdbb83cc`（PR #4 squash 已完成）；审查对象 `git diff cdbb83cc..HEAD` = **`30 files changed, 5091 insertions(+), 8 deletions(-)`**（`--stat`）。合并方式计划 **PR squash**。
> **独立取证口径**：全部结论基于真实 `Read` / `Grep` / 只读 `git diff | status | log | rev-parse | diff --check` / 只读 Python（WCAG 相对亮度复算）/ `test -e`，逐条附 `文件:行号` 或命令 + 退出码；未凭任务描述或他方回传摘要下结论。`git status --short` 的 8 个未跟踪文件（`.env.bak.*` / `.playwright-cli/` / 各类 `.lock` / 一个 evaluation json）为工作区本地产物，不在本次 diff 内、不进入 PR，不构成合并内容。

---

## 一、实现边界 — **通过**

- `git diff cdbb83cc..HEAD --stat` = 30 files / 5091+ / 8-，与背景一致；`--name-status` 逐项核对如下。
- **`frontend/styles.css:4406-4410`** 仅 `+5` 行，为 5 条 `[data-status="needs_ground_truth"]` 纯 CSS 灰化规则（V1 `border-left-color:#c9cbd3;background:#f6f6f8`、V2/V3 徽章 `#e9eaee`/`#5f626c`、V4 标题 `var(--muted-strong)`、V5 数值 `var(--muted)`、V6 `> summary` `var(--muted-strong)`）；diff hunk `@@ -4403,6 +4403,11 @@`，**无删行、无改行**。
- **`frontend/index.html`** 仅 2 增 1 删：`:8` live `<link ... styles.css?v=75>` → **`?v=76`**；`@@ -909,6 +909,7 @@` 在末尾注释区（`:912`）新增 `<!-- Merge compatibility marker: href="/assets/styles.css?v=75" -->`（纯属性片段、不含 `<link`/`<script`、位于 `</head>` 之后）。
- **6 处测试期望值同步**（5 文件）：`test_evaluation_asset_versions.py:100,118` `[75]→[76]`、`test_evaluation_dataset_count_rendering.py:87` 与 `test_evaluation_metric_grouping.py:189` `v=75→v=76`、`test_research_detail_actions_placement_contract.py:223` 与 `test_memory_return_global_contract.py:210` `["75"]→["76"]`；与 spec §13 裁决 2 / 技术评审 §5.3（`:642-653`）的 6 处清单逐条一致。
- **新增** `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`（139 行静态契约）。
- **`frontend/app.js` 与 `backend/**` 逐字零改动**：`git diff cdbb83cc..HEAD -- frontend/app.js | wc -l` = `0`、`-- backend/` = `0`、`--name-only -- frontend/app.js backend/` 输出为空。
- 判定：纯 CSS + 版本契约 + 静态契约测试的最小改动，无 JS / 后端第二套实现，无跨端越界；符合 regression-guard 前端第 1/2/3/4 条与后端第 9 条（禁重复实现）。

## 二、视觉契约与红线 — **通过**

- **三状态逐字不变**：`grep -nF` 命中 `styles.css:4391` computed `#287c43`（绿）、`:4392` degraded `#c8871a`+`#fffdf7`（橙）、`:4394` unavailable `#b13a3a`+`#fff8f8`（红）、`:4393` needs_ground_truth 基础 `#6d5dfc`+`#faf9ff`；diff 仅 +5 行、未触碰这四条。E2E ③ computed 实测 `rgb(40,124,67)`、⑥ degraded `rgb(200,135,26)`/`rgb(255,253,247)`、⑦ 切 `rag-retrieval` 后 `recall_at_k` 恢复 computed 绿（`gray-style-e2e.json:73-80,103-127`）。
- **只灰化 `needs_ground_truth`**：5 条规则逐行以 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 开头（`sed -n '4406,4410p'` 逐行核实），作用域限定 `#evaluation-view`、复用既有 class（A5 列出 `card/status/label/value/params` 5 个，**无新 class**）。
- **无禁用属性 / 无注入面**：`sed -n '4406,4410p' frontend/styles.css | grep -niE 'opacity|grayscale|filter|display *: *none|visibility *: *hidden|innerHTML'` → `NO_BANNED_PROPS_IN_GREY_BLOCK`；`app.js` 零改动 → 无新增 `innerHTML`。
- **灰卡不隐藏、信息不丢**：`computed-style-raw.txt:2` 真实 `getComputedStyle` 采样 `display:"grid"` / `visibility:"visible"` / `opacity:"1"`；同文件 `grayText` 逐字含 `—` / `样本数：0` / `原因：该评测集没有 relevant_doc_ids…`；E2E ④（`:82-91`）`null_rendered_as_dash / reason_visible / sample_count_zero_visible / no_hidden_cards` 全 `true`；E2E ⑤（`:93-100`）灰卡 `<details>` 展开 `grey_details:1 / open_after_click:1 / param_rows_after_expand:2`（澄清 `computed-style-raw.txt` 的 `grayHasDetails:false` 仅因采样的是第一张无参数灰卡，非 CSS 隐藏）；`value=null → —`、`detail.reason`、`sample_count`、`<details>` 的 DOM 生成逻辑因 `app.js` 零改动而逐字保持（代码评审 `047-frontend-gray-style-review.md:96-100` 附 `app.js:7734-7744/7792-7835` 证据）。
- 判定：反伪造 / 不降级红线完整，V1–V7 与边界 1–7 成立。

## 三、WCAG 独立复算 — **通过**

只读 Python 按 WCAG 2.x 相对亮度公式 `L = 0.2126·lin(R)+0.7152·lin(G)+0.0722·lin(B)`、`lin(c)=c/12.92 (c≤0.03928) 否则 ((c+0.055)/1.055)^2.4`、比值 `(L亮+0.05)/(L暗+0.05)` 复算（不调用被评审测试模块）：

| 组合 | 前景 / 背景 | L_fg / L_bg | **实测比值** | AA ≥4.5:1 |
|---|---|---|---|---|
| **V3 徽章（生效）** | `#5f626c` / `#e9eaee` | 0.122510 / 0.823423 | **5.0630:1** | **PASS** |
| **V4 标题（生效）** | `#5a5d66`（`--muted-strong`）/ `#f6f6f8` | 0.109617 / 0.922817 | **6.0947:1** | **PASS** |
| 作废色值对照 | `#6b6e78` / `#e9eaee` | 0.156337 / 0.823423 | 4.2330:1 | FAIL（故 spec §13 裁决作废） |

- `grep -n '#6b6e78' frontend/styles.css` → `DEPRECATED_6b6e78_ABSENT`（全文件 0 命中）。
- 与新增契约 `test_wcag_aa_contrast_for_badge_and_title`（锁定 `abs(badge-5.0630)<0.02` / `abs(title-6.0947)<0.02` 防恒真）、spec §13 裁决 1（`:1175-1177`）、技术评审 `:630-632`、E2E `wcag.v3_badge=5.063 / v4_title=6.0947 / rejected_v3=4.233 fail`（`:18-43`）逐项吻合 → 断言非恒真、非凑绿。
- **已知非阻塞 R1（如实登记，不隐瞒）**：V5/V7 沿用 `--muted:#8b8e96` 在灰底 `3.0365:1`（改动前紫底 `3.1306:1`），属既有基线轻微退化；spec §13（`:1178-1179`）、技术评审 `:634`、代码评审 `:111,115,174`、E2E `:37-42` 已书面裁决「不扩范围、严禁 `opacity`/`filter` 补救、信息层不丢失」，不构成打回项。

## 四、凑绿排查 — **通过**

- **无删断言**：5 个改动测试文件 `removed assert lines = 6` / `added assert lines = 6`（守恒，逐对为 `[75]→[76]` / `v=75→v=76` / `["75"]→["76"]`）；`git diff ... -- tests/ | grep '^-[^-]' | grep -iE 're\.|findall|snapshot|tolerance'` → `NO_LOOSENED_MATCHERS`；新增契约 `grep -niE 'skip|xfail|pytest.mark|noqa'` → `NO_SKIP_XFAIL`；无重算失败快照迁就实现（snapshot 为真实 Chromium 渲染树，见 E2E 4 项产物）。
- **代码评审** `047-frontend-gray-style-review.md:119-131` 以 8 类内存违规变体（删灰化规则 / 色值回退 / 注入 opacity / 删基础规则 / 版本回退 / 删 marker / 删 dataset.status）验证新增断言**均被拦截**、非恒真、不可静默失效（regression-guard 第 12 条）。
- **`scripts/check_test_layout.py` EXIT=1 的 5 项为既有历史文件**（本轮独立执行复现）：`tests/conftest.py`、`tests/evaluation/test_task03_reproducibility.py`、`tests/evaluation/test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py`；逐一 `git diff cdbb83cc..HEAD -- <5文件>` 全部 `diff_lines=0`；新增契约文件未出现在报错列表。按纪律未改这些历史文件凑绿。
- **回归实数**：`full-regression.txt:77` `4557 passed, 2 skipped, 5 warnings, 69 subtests passed in 731.98s`、`:82` `PYTEST_EXIT=0`；`frontend-regression.md:12` 单端 `614 passed / 0 failed / 0 skipped / 0 xfailed / EXIT=0`，`:24` `--collect-only` `614 tests collected`（收集数＝通过数，未用 `-k` 过滤）；`node --check frontend/app.js` EXIT=0。
- **如实登记**：`full-regression.txt:78-80` 的 OTEL span 导出 transient error（`127.0.0.1:3000` Langfuse 未启动）为遥测噪声，未影响 `PYTEST_EXIT=0`；E2E `known_non_blocking:135-140`、验收 §16.8（`:978-986`）已逐条登记（含 4 个浏览器 404、工具超时标记、P2 文案、R1、layout 5 项、`research-tasks.js?v=25` 缓存风险）。

## 五、门禁三项（`docs/github.md:13`、`docs/sdd/pr-template.md:4`）

### ① CI 全绿 — **以本地等价门禁替代，偏差已披露**

- **事实**：本仓 `ls -d .github/workflows` → `NO_WORKFLOWS_DIR`（`find .github -type f` 无输出）；`docs/github.md:5`「当前仓库若未配置 remote，本文件规则为**规范预留**，待接入 GitHub 后生效」、`:16`「CI/CD 与质量门禁（**规则说明，非真实 workflow**）」。→ **本仓无真实 CI workflow，如实披露，不宣称「CI 全绿」**。
- **替代证据（本地等价门禁，逐条真实退出码）**：最终全量 `4557 passed, 2 skipped / PYTEST_EXIT=0`（`full-regression.txt:77,82`）；单端 `614 passed / EXIT=0`（`frontend-regression.md:12`）；`node --check` EXIT=0；`git diff --check` EXIT=0；部署验证 `4×200`（`deploy-verification.json:8-26`）；真实 Chromium E2E 7 步 PASS（`gray-style-e2e.json:44-128`）；独立代码评审 APPROVE（`047-frontend-gray-style-review.md:193`）。
- 判定：满足 `github.md:18-22` 四道门禁的**本地等价执行**，但平台 CI 缺失按偏差披露（见 §门禁偏差）。

### ② 测试覆盖率 ≥ 80% — **未量化、未验证、不虚报达标；开发主管裁决「不构成放行阻断」**

- **事实（独立核实）**：根目录 `ls pyproject.toml setup.cfg pytest.ini tox.ini .coveragerc Makefile` → `NONE_OF_THOSE`；`grep -niE 'fail_under|--cov|addopts|coverage' <上述配置>` → `NO_COV_OR_FAILUNDER_IN_CONFIGS`；全仓 `--cov|fail_under` 仅命中 `docs/sdd/specs/010-backend-coverage-80.md` 与 `.codebuddy/skills/**`（**规范/技能文档描述，非生效配置**）；`full-regression.txt` 无 coverage 报告。→ **本轮未采集覆盖率、无阈值强制、未量化、未验证；不虚报「≥80% 达标」**。
- **开发主管裁决依据（6 条）**：
  1. **门禁生效前提不存在**：`docs/github.md:13` 虽写「任一不满足则阻断，不得绕过」，但同文件 `:5` 定性为「规范预留」、`:16`「规则说明，非真实 workflow」、`:21`「阈值由开发主管在 spec 执行配置中确认」；无 `fail_under`、无 workflow 则该门禁在当前仓库从未作为自动化阻断执行。
  2. **一致先例**：上一次 PR #4 合并 spec-047 主体（`origin/main = cdbb83cc`）在同等条件下（无真实 CI、覆盖率未量化）已由开发主管裁决放行，且 `docs/sdd/spec-status-changelog.md:791` 明确「门禁偏差『无真实 CI workflow』『覆盖率未量化、不虚报 ≥80%』已在 PR 描述与复审报告逐条落盘披露」；本轮沿用，避免双标。
  3. **改动不新增被测源码行**：本轮仅 +5 CSS 行、2 行 HTML、6 处测试期望值、1 个新增测试文件；`app.js` / `backend/**` 零改动，覆盖率针对源码执行行，故不存在「覆盖率因本轮改动而下降」的风险；新增的是断言（增强门禁）。
  4. **等价且更强的替代验证**：4557 全量 + 614 单端 + 9 条新增静态契约（含 8 类违规变体防恒真）+ 真实浏览器 E2E 7 步 + 部署 4×200 + 独立 WCAG 复算 + 独立代码评审 APPROVE + 本轮独立 approval。
  5. **显式落盘豁免而非静默跳过**：按 `docs/github.md:23`「门禁失败必须阻断并落盘原因……不得静默跳过」，本审批报告 §门禁偏差书面登记「覆盖率未量化/未验证/不虚报达标」并由开发主管签字豁免；`merge-decision.md §五 2`（`:101`）与复盘 `:38` 已登记同一偏差。
  6. **豁免边界**：一次性、有条件、显式，仅适用于本次纯样式/契约改动；不得推广为「覆盖率已达标」或后续 PR 自动豁免；接入 CI 后须补 `pytest-cov` + `fail_under` 并将门禁由「规则预留」转为可执行（列为后续技术债）。
- 判定：**不构成放行阻断**（在显式披露 + 一次性豁免前提下）。这是开发主管对门禁偏差的程序裁决，**不是宣称覆盖率达标**。

### ③ 至少 1 个独立 approval — **满足（本轮出具）**

- `docs/github.md:11`「PR 必须由**开发主管**（或另一 Agent）审查并批准，至少 1 个 approval 才可合并」。
- 本轮由 `architect`（开发主管 / Tech Lead）**独立只读审查**后出具 approval；`047-acceptance-review.md:1008-1016` §16.11「开发主管签字 / 架构师合并裁决」明确**留空交架构师签署**、QA 不代签；实现方（task-17 `frontend-dev`）未自批。
- 并列独立角色（互不代行）：`tester` 验收签字 **R（已填）**（§16.10 `:997-1006`）、`frontend-reviewer` 代码评审 **APPROVE**（`047-frontend-gray-style-review.md:18-24`）、`frontend-tester` 单端回归 `614 passed`（`frontend-regression.md:3,113-115`）。
- 上一轮 `merge-decision.md` 签字 A 为「批准收口」且明确「本次不 push / 不合 main」，**不是本轮合并的 approval**；本轮 approval 为新阶段独立出具。
- **偏差披露**：GitHub 端 branch protection / 平台级 1 approval 未配置为强制（复盘 `:41`、`merge-decision.md:100`），approval 以独立落盘报告为准。

## 六、证据链 — **通过（逐项真实读回）**

| # | 证据 | 结论 / 位置 |
|---|---|---|
| 1 | 需求评审 §16 | `047-requirement-review.md:233-249`「**通过**」P0=0/P1=0；§16.5 登记 2 项技术 P1 由 §13 裁决闭环 |
| 2 | 技术评审「追加范围四」 | `047-tech-review.md:564-696`「**通过（附强制约束）**」P0=0/P1=2；`:687-692` 判「不判打回」、放行前置为「只认 §13 裁决，不得照抄 `#6b6e78` / 4 处」 |
| 3 | 代码评审 | `047-frontend-gray-style-review.md:18-24,193` **APPROVE**（P0=0 / P1=0 / P2=1），`Verdict: APPROVE — 0 CRITICAL / 0 HIGH` |
| 4 | 单端回归 | `runs/task-18/frontend-regression.md:12,115` `614 passed / EXIT=0`「通过」 |
| 5 | 真实 Chromium E2E | `runs/task-19/gray-style-e2e.json:44-128` 步骤 ①–⑦ 全 `PASS`、`conclusion: PASS`、`:129-134` artifacts 4 项；4 项产物逐一 `test -e` 存在 |
| 6 | 部署验证 | `runs/task-19/deploy-verification.json:8-26` health / index / styles_css_v76 / evaluation_options **4×200**、`conclusion: PASS` |
| 7 | 验收评审 §16 | `047-acceptance-review.md:988-995` §16.9「**通过**」/ 准备度 10/10 / 无 P0/P1 遗留 / 0 断链；`:997-1006` §16.10 **验收签字 R（已填）/ 通过 / 2026-11-12** |
| 8 | 上一轮合并裁决 | `runs/task-19/merge-decision.md:74-84` 架构师签字 A「**批准收口**」；`:98-107` §五已知非阻塞偏差逐条如实登记 |
| 9 | spec §13 / 台账 / 复盘 / 人工验收 | `specs/047-...md:1167-1199` §13 裁决 1+2+R1+状态流转；`spec-status-changelog.md:789-797` 2026-11-12 共 5 条（含「实施中→已完成」双签条目）；`retro/2026-11-12-...md:29-41` 证据链与已知限制；`artifacts/spec-047-irrelevant-metric-gray-manual-e2e.md:33-48` 十项准备度 **10/10** |

## 七、机械校验 — **通过**

- **无残留冲突标记**：`git diff cdbb83cc..HEAD | grep -nE '^\+(<<<<<<< |>>>>>>> |=======$)'` → `NO_CONFLICT_MARKERS_IN_ADDED_LINES`；对 8 个主要改动文件全量 `grep -rnE '^(<<<<<<< |=======$|>>>>>>> )'` → 0 命中。
- **`git diff --check cdbb83cc..HEAD`** → `DIFF_CHECK_EXIT=0`（两轮独立执行一致）。
- **引用路径 0 断链**（独立复核，口径 = 本次 diff **新增行**中的仓库相对引用）：抽取 `62` 个唯一引用，跳过 `9` 个占位/省略/通配写法（`...` / `*` / `0X` / `XX`），逐一按多候选基路径 `test -e` → **`BROKEN_LINKS_IN_ADDED_LINES=0`**；另对复盘 §四、人工验收 §6、spec §13、E2E artifacts 所列 **`21` 个核心路径**逐一 `test -e` → **21/21 存在**；E2E 4 项产物逐一存在。
- **宽口径复核的诚实说明**：若把修订后文档全文（含 §1–§15 历史章节）一并扫描，机械脚本报 18 项 `MISSING`；本轮逐一定位（`F1`）确认全部为：① 历史章节叙述中「已修复的旧失效路径」（`artifacts/task-07/ccs-coverage.md` 见 `047-acceptance-review.md:463`，原文同时给出修复后真实路径 `artifacts/spec-032/task-07/ccs-coverage.md`；`artifacts/task-13/carryover.md` 见 `spec:572`）；② 故意引用**已删除**的 `048-evaluation-effect-visualization.md`（`spec:368` 明文「已被主会话删除（本轮核实不存在）」）；③ 占位写法 `runs/task-0X/implementation.md`（`047-acceptance-review.md:97`，`0X` 为通配符）与带 `...` 的示例；④ 相对缩写 `runs/task-05|07|08/*`（真实基路径为 `docs/sdd/plans/045/runs/...`）；⑤ 子目录简写 `tests/test_*.py`（`git ls-files` 佐证 `tests/conversation/test_chat_route.py`、`tests/research/test_research_routing_status_decisions.py`、`tests/research/test_validated_evaluator_candidates.py` 真实存在）。**均非本轮交付物引入的断链，不构成 P0/P1**。

---

## P0 / P1 汇总

| 来源 | P0 | P1 | 处置 |
|---|---|---|---|
| 需求评审 §16 | 0 | 0 | 通过 |
| 技术评审「追加范围四」 | 0 | **2** | 均「必须修复但非阻塞」；已由 spec §13 裁决闭环（V3 `#5f626c` 5.0630:1、6 处精确断言同步），task-17 采纳、task-18/19 复验 PASS（E2E WCAG 5.063 / 6.0947、614 passed、作废色 0 命中） |
| 代码评审 | 0 | 0（P2=1） | APPROVE |
| 验收评审 §16（tester 签字 R） | 0 | 0 | 通过 |
| **本轮独立合并审查** | **0** | **0** | 无真实 P0/P1 发现；门禁偏差 3 项显式披露并裁决（非实现缺陷） |

- 遗留 **P2=1**（非阻塞）：`test_research_detail_actions_placement_contract.py:223` / `test_memory_return_global_contract.py:210` 的 f-string 失败提示仍写「为 75」，断言值已为 `["76"]`；代码评审 `:162-169` 判 P2，建议后续同步，不构成打回。

## 最终裁决

# **通过（Approve）—— 批准合并**

- 审查对象 `git diff cdbb83cc..HEAD`（HEAD `6406609a`，基于 `origin/main = cdbb83cc`），合并方式 **PR squash** 到远程 `main`。
- 上述 7 项逐条独立核实通过：实现边界最小且零 JS/后端改动；视觉契约与反伪造红线完整；WCAG 两处实测 5.0630:1 / 6.0947:1 均达标、作废色缺席；无凑绿；门禁三项在显式披露/一次性豁免下满足；证据链自洽（需求/技术/代码/验收四份评审 + 614 + 4557 + 7 步 E2E + 4×200 + 双签 R/A + 台账/复盘/人工验收）；机械校验 0 冲突标记 / `diff --check` 0 / 0 断链。
- **无真实 P0 / P1**、无实现或证据缺陷、未发现「方案不成立 / 需推倒 / 需用户重新确认」的情形，故按任务「发现真实 P0/P1 必须如实打回」的反向约束**不打回**。
- 本 approval 由 `architect` 独立出具，**非实现方自批**；不代 `tester` 签字 R、不代 `frontend-reviewer` 评审、不虚报全绿。
- 裁决范围仅限「批准合并」；**不改任何代码 / 测试 / 配置 / spec 正文 / 状态台账 / 评审历史，不代行 `git push` / 合 `main`**（`docs/github.md:28-29`：涉及远端动作须经用户确认，本轮用户已授权合并但执行仍由主会话 / 用户进行）。

## 门禁偏差三项落盘披露（`docs/github.md:23` 要求，不得静默跳过）

1. **① 无真实 CI workflow**：`.github/workflows` 不存在；`github.md:5,16` 定性为「规范预留 / 规则说明，非真实 workflow」。以本地最终全量 `4557 passed / PYTEST_EXIT=0`、单端 `614 passed / EXIT=0`、`node --check`、`git diff --check`、部署 4×200、真实 Chromium E2E 7 步 PASS 作为等价门禁替代；**不宣称「CI 全绿」**。
2. **② 覆盖率未量化**：无 `--cov` / `fail_under` 生效配置、本轮未采集 → **未量化、未验证、不虚报「≥80% 达标」**；由开发主管按 §五② 的 6 条依据作**一次性显式豁免**（不构成放行阻断），并登记为后续技术债（接入 CI 时补 `pytest-cov` + `fail_under`）。
3. **③ 平台级 approval 未强制**：GitHub 端 branch protection / 1 approval 未配置；以本轮独立 `architect` approval + `tester` 验收签字 R + `frontend-reviewer` APPROVE 的**落盘报告**为准，不由实现方自批。

> 三项偏差已在 `merge-decision.md §五`（`:98-107`）、复盘 `:38,41`、`spec-status-changelog.md:791`（PR #4 先例）与本报告同步登记；豁免为一次性、有条件，不推广、不掩盖。

## 放行前置条件（主会话 / 用户执行，本审批不代行）

1. 合并前确认分支基于 `origin/main = cdbb83cc` 且线性（`docs/github.md:9` `git rebase main`，如有冲突先解决再提 PR）；PR 标题引用 spec-047，PR 描述须逐条引用本报告「门禁偏差三项」披露，不得静默跳过（`github.md:23`）。
2. 采用 **squash merge**（`github.md:12`、`pr-template.md:3`）；合并后保留上一 `main` commit `cdbb83cc` 以支持回滚、删除源分支（`github.md:14`）。
3. 合并后回填状态台账「已完成」条目、spec `:1148` 评审记录及 task-17/18/19 文档状态（如尚未完成）；本审批不改状态台账 / spec 正文。
4. 将三项门禁偏差与 P2 文案、`research-tasks.js?v=25` 升版登记为后续技术债另案处理；接入真实 CI 后须重新满足覆盖率 ≥80% 的量化门禁。
5. 若合并前基线发生变化（出现新 commit、非 squash 或 diff 不再是 `cdbb83cc..6406609a`），本审批自动失效，须重新出具。
6. 本审批为独立只读结论，**不代行 `git push` / 合 `main`**；远端动作由用户 / 主会话执行。

## 纪律声明

- 本审批为**独立只读审查**：全程仅 `Read` / `Grep` / 只读 `git status | log | rev-parse | diff | diff --check | ls-files` / 只读 Python（WCAG 复算）/ `grep` / `sed` / `wc` / `test -e`；**未改**任何代码 / 测试 / 配置 / spec 正文 / 状态台账 / 评审历史 / E2E 证据 / 复盘 / 人工验收文档。
- **未** `git commit` / `push` / 合 `main` / `reset` / `stash` / `clean` / `add`；未跑破坏性 `--force`、未重启服务、未 mock 冒充真实 E2E、未重算失败快照迁就实现、未改断言凑绿。
- 唯一写入：`docs/sdd/plans/047/runs/task-19/merge-to-main-approval.md`（本报告）与进展日志 `.codebuddy/agent-logs/spec-047/task-19/architect-merge-approval/20261112-165253.md`。
- 不代 `tester` / `frontend-reviewer` / `frontend-tester` 签字，不由实现方自批，不预判并行结论，不虚报全绿，不因推进进度而放行真实 P0/P1；门禁偏差如实披露、覆盖率豁免不推广。
- 下游只认落盘文档：本报告 + `047-acceptance-review.md` §16 + `runs/task-19/merge-decision.md` + spec 追加范围四 §13 + `047-tech-review.md`「追加范围四」+ `047-frontend-gray-style-review.md` + `runs/task-18/frontend-regression.md` + `runs/task-19/{gray-style-e2e.json,deploy-verification.json,full-regression.txt}` + 状态台账。
