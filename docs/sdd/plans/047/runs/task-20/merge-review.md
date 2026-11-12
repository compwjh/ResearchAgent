# Spec-047 追加范围五「遗留项清理」· 独立架构师评审 / 合并裁决

| 项 | 值 |
|---|---|
| 评审者 | architect |
| 角色 | 架构师（评审·合并） |
| 模型 | `hy4` |
| 分派方式 | `Task(architect)` |

> 模型依据：`.codebuddy/agents/architect.md:6` `model: hy4`（该角色描述行中的旧型号叙述不作为型号真源；spec:1275 规定「型号唯一真源 = `.codebuddy/agents/<role>.md`」）。

- 评审对象：`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:1200-1294`「追加范围五」（当前状态 `实施中`）。
- 基线 / 分支：`origin/main 42bbc188`（PR #5 squash 后），工作分支 `feature/spec-047-followup-cleanup`（spec:1205-1206）。
- 评审性质：**一次独立只读评审 + 合并裁决，非自批**（spec:1270-1271、SDD-GATE-CHECKLIST.md:106-112 Gate 5）。
- 日期：2026-11-12。
- 结论摘要：① 需求评审 **通过**；② 技术评审 **通过**；③ 验收合并裁决 **批准收口**；P0=0 / P1=0 / P2=0，阻塞项 **无**；已知非阻塞项 7 项如实登记于 §6。

---

## ① 需求评审结论：**通过**

逐项依据（均为已 Read 的真实文件行，非推断）：

| 评审维度 | 判定 | 文件:行 依据 |
|---|---|---|
| 目标是否清晰 | 通过 | spec:1219-1222「消除上一轮交付登记的 5 类遗留（缓存版本、诊断文案、测试布局合规、灰卡文字对比度、覆盖率可观测），且不改变任何用户可见的功能行为、不破坏既有闸门、不制造新的红灯」；spec:1209-1217 A–E 逐条「勘察事实 → 处置」表，每项均有可核对的勘察证据 |
| 边界与「明确不做」是否写清 | 通过 | spec:1226-1238 共 9 条「明确不做」（无真实 CI workflow、不设 `--cov-fail-under=80`、不改 `app.js`/`backend/**` 业务逻辑、不改 `:root` 且灰化规则带状态限定、不重写历史报告旧路径、不改松断言/不删测试/不 skip/不 xfail、不主动合 main/不 force push、不处理 Langfuse `:3000` 与其它视图 404、闭环后仅本地 commit 不 push）；spec:1224 把「非目标」显式指向 §2 |
| 验证方式是否可操作 | 通过 | spec:1260-1271：单端定向（`node --check`、`pytest -q tests/frontend/`、`check_test_layout.py` EXIT=0、4 个改名测试与 conftest 迁移后定向）、真实 Chromium `getComputedStyle` 复核、覆盖率 `--cov=backend/app --cov-report=term-missing` 落盘、最终候选全量 `pytest -q` 记录命令/退出码/通过数、部署验证 4×200、收口「独立 architect 需求/技术/验收合并裁决 + tester 验收签字 → 实施中 → 已完成」；每条均给出可执行命令或可判定判据 |
| 实现契约与验证点一一对应 | 通过 | spec:1246-1258 A1–E1 契约表：每条契约带对应验证点，无悬空目标 |
| 状态机与门禁一致 | 通过 | spec:1202-1207（待确认 → 已确认 → 实施中；不新增 spec 编号 / `plans/048/`；历史收口结论、四份评审签字逐字保留不翻案）；SDD-GATE-CHECKLIST.md:106-112（Gate 5：tester 出报告 + architect 签字，签字栏留空不得转 `已完成`）；SDD-GATE-CHECKLIST.md:128-138（§3 收口清单） |
| 任务计划 / RACI 可追溯 | 通过 | spec:1273-1282：任务 20（frontend-dev，A+B+D）/21（backend-dev·主会话，C+E1）/22（architect·tester·主会话，独立评审+回归+浏览器+部署+签字+台账/复盘/本地 commit）；spec:1275 明确不新增模型列、架构师填「自身」；spec:1284-1287 评审记录预留本文件 `plans/047/runs/task-20/merge-review.md` |
| spec 未被翻案 / 未被改写 | 通过 | `git diff HEAD --numstat`：`047-...fixes.md` 为 `96 0`（96 行纯追加、0 删除）；`git diff HEAD -- docs/sdd/specs/047-...` 删除行 grep 为空；`docs/sdd/spec-status-changelog.md` 为 `4 0` 纯增（追加范围四合并交付记录 + 追加范围五状态流转） |

**需求评审无阻塞项**：目标、边界、不做清单、验证方式、状态机五项齐备且可操作，符合 Gate 2 需求评审要求。

---

## ② 技术评审结论：**通过**

### 2.1 数据模型 / 并发 / 事务 / 外键
- **无新增数据模型字段、无后端改动**：spec:1240-1244 明确「五端点、22 key、`METRIC_KEYS` / `METRIC_GROUPS`、`status` 取值域、`detail.reason`、`sample_count`、稳定错误码全部不变」；`git status --short` 与 `git diff HEAD --numstat` 中**无任何 `backend/**` 文件**，本范围仅涉及前端静态资源版本号、CSS 颜色、测试文件命名/位置、诊断文案与本地覆盖率配置。
- **并发 / 事务 / 外键**：本范围无 DB 迁移、无 SQL、无外键改动（regression-guard 项目附录第 5/6 条 SQLite 迁移与单条条件 `UPDATE ... RETURNING` 抢锁条款 **N/A**，如实登记，不假装有事务面）。唯一涉及并发语义的是根 `conftest.py` 迁入的 `_drain_and_reset()`（`conftest.py:103-121`，`time.monotonic()` 有界等待在飞预热收敛后 `reset_warmup()`），该逻辑**逐字复制**自原 `tests/conftest.py`（`backend-implementation.md:28-39` 记录 `diff -u` EXIT=0），未改一行，不构成新并发设计。
- 结论：**通过**，数据模型零变化、并发面无新增风险。

### 2.2 接口 / SSRF / 来源可信
- **接口零变化**：spec:1242-1244；`git status --short` 无 `frontend/app.js`（`frontend-implementation.md:26` `node --check frontend/app.js` EXIT=0，报告 §3③ grep `innerHTML` 0 命中、本任务未改 app.js）；未新增字段 / 端点 / 五端点之外的路由。
- **SSRF / 来源可信**：regression-guard 项目附录第 7/8 条要求「外发请求须白名单/内网隔离、禁止对任意用户输入 URL 直连」及「USENIX 来源可信同源」。本轮改动为 HTML 注释 marker、CSS 颜色规则、Python 静态断言、测试改名、`.coveragerc` 配置；**无新增跨库/跨服务调用、无用户输入 URL 拼接、无新增第三方依赖、无新端点**，故该项 **N/A 且已核查**（不是「应该没问题」，而是 diff 中确无此类代码）。
- 结论：**通过**，无新增攻击面。

### 2.3 模块划分与边界 / 复用（禁止第二套）
- **跨端边界**：前端 A+B+D 由 `frontend-dev` 独立完成（`frontend-implementation.md:4` 只改 `frontend/**` 与 `tests/frontend/**`）；后端 C 与 E1 由 `backend-dev` / 主会话完成（`backend-implementation.md:5` 只改 `tests/**` 命名/位置与根 `conftest.py`）；两端互不越界，`git status --short` 可逐文件核对。
- **复用既有实现，无第二套**：
  - `clean_warmup_registry` / `_drain_and_reset` 逐字迁入根 `conftest.py`，根文件原有 5 个 `autouse=True` fixture **0 行删除**（`backend-implementation.md:32-39`）；未重写、未新增第二套隔离 fixture。
  - `scripts/check_test_layout.py` 未改（`backend-implementation.md:64`），靠 4 个真实改名 + `tests/` 根移除 `.py` 源文件使 EXIT=1 → EXIT=0（`backend-implementation.md:46`、:58）。
  - 版本解析复用既有 `_live_versions()`，仅扩展 `research-tasks.js` 分支（`tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` diff :33-36），非第二套版本解析器。
  - 4 个改名文件 `git diff --cached --summary` 为 **R100，`0 insertions / 0 deletions`**（`backend-implementation.md:28`；`git diff HEAD --numstat` 复核 4 个 `0 0` 改名行）。
  - `tests/system/conftest.py` / `tests/kb/conftest.py` 以**形参名**引用（非 import），全仓 Grep 无 `from conftest import` / `import conftest` 形式依赖（`backend-implementation.md:62`），`pytest --fixtures` 显示 `clean_warmup_registry -- conftest.py:124`（`backend-implementation.md:51`），符号无断链。
- 结论：**通过**，边界清晰、复用既有实现、无重复实现。

### 2.4 版本契约（A1 / A2 / D2 / 静态断言）
| 契约 | 复核事实 | 依据 |
|---|---|---|
| A1 | `frontend/index.html:902` `<script src="/assets/research-tasks.js?v=25">` → `?v=26` | `git diff HEAD -- frontend/index.html` |
| A2 | 末尾注释区新增 2 条**纯属性片段** marker：`src="/assets/research-tasks.js?v=25"`、`href="/assets/styles.css?v=76"`（在 HTML 注释内、不含 `<script` / `<link` 标签字面串）；`test_research_task_search.py:38` 的 `v=22` marker 不变 | `git diff HEAD -- frontend/index.html`（:913/:914）；`frontend-implementation.md:45`；新增静态断言 `gray_contract.py` 逐条校验 marker 恰好 1 条且在注释内 |
| D2 | `frontend/index.html:8` live `styles.css?v=76 → ?v=77`；`app.js?v=77` **不动** | `git diff HEAD -- frontend/index.html`；`deploy-verification.json:13-14` live 字段复核 |
| 6 处精确 live 断言同步 `77` | `test_evaluation_asset_versions.py:100,118`、`test_evaluation_dataset_count_rendering.py:87`、`test_evaluation_metric_grouping.py:189`、`test_research_detail_actions_placement_contract.py:223`、`test_memory_return_global_contract.py:210`，另 `gray_contract.py:127` 内部同步 | `git diff HEAD -- tests/frontend/` 逐文件复核（`["76"]` → `["77"]` / `[76]` → `[77]`） |
| 9 处 `in INDEX` 冻结断言 | 靠 2 条新 marker 继续满足，冻结断言本身未改 | `frontend-implementation.md:20,44`；新增 marker 的 diff |
| `active_version > 68` 不污染 | `:8` 首个 `styles.css?v=` = 77，marker 为纯属性片段不被 `_live_versions` 前缀正则误算 | `frontend-implementation.md:45`；`test_evaluation_asset_versions.py` `test_new_compatibility_marker_is_pure_attribute_fragment` |
| 新增精确断言 | `_live_versions("research-tasks.js") == [26]`（spec:1250 A1 验证点） | `gray_contract.py` 新增 `test_r1_grey_text_wcag_and_live_asset_versions` |

### 2.5 CSS 边界（D1 / D3）
- `frontend/styles.css` diff：灰卡 `-value` `var(--muted)` → `var(--muted-strong)`；新增 `-samples` / `-detail-row` / `-params` 3 条规则，连同既有 `-label` / `-params > summary`，共 **6 条 `--muted-strong` 规则**（`deploy-verification.json:15` `gray_muted_strong_rules: 6`），**全部带 `[data-status="needs_ground_truth"]` 限定**；非灰卡基础规则（:4396/:4401/:4403/:4404 的 `var(--muted)`）逐字未动；`:root` 变量定义未动；`computed` 绿 / `degraded` 橙 / `unavailable` 红配色逐字未触及；无 `opacity` / `filter` / `display:none`。
- WCAG：`#5a5d66` / `#f6f6f8` = **6.0947:1 ≥ 4.5:1**（`frontend-implementation.md:54`；`gray_contract.py` `test_r1_grey_text_wcag_and_live_asset_versions` 复算）；浏览器实测灰卡文字 `rgb(90, 93, 102)` = `#5a5d66`（`r1-computed-style.txt:2`）。
- 结论：**通过**，静态契约与真实浏览器一致（见 §3）。

**技术评审无阻塞项**：模块划分、复用、版本契约、CSS 作用域、数据模型/接口/安全维度逐项有真实文件与命令证据。

---

## ③ 验收合并裁决：**批准收口**

### 3.1 命令 / 退出码 / 通过数（全部为落盘真实输出，非自测摘要转述）
| 命令 | 退出码 | 真实结果 | 依据 |
|---|---|---|---|
| `.venv/bin/python -m pytest -q`（最终候选全量） | **0** | `4559 passed, 2 skipped, 5 warnings, 69 subtests passed in 887.98s (0:14:47)` | `full-regression-coverage.exit` = `0`；`full-regression-coverage.txt:295` |
| `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing`（spec:1258/1266） | 0（同一全量） | `TOTAL 51890 8811 83.02%` | `full-regression-coverage.txt:77-78,294` |
| `.venv/bin/python -m pytest -q tests/frontend/` | 0 | `616 passed in 129.77s (0:02:09)` | `frontend-implementation.md:27`（后台执行 + 结果文件取回真实退出码，非跳过/截断，见 :31） |
| `.venv/bin/python scripts/check_test_layout.py` | **0** | `test layout: ok`（迁移前 RED 基线 EXIT=1，5 项历史编号） | `frontend-implementation.md:29`；`backend-implementation.md:12,46,58`；`deploy-verification.json:18` |
| `node --check frontend/app.js` | 0 | 通过（本任务未改 app.js） | `frontend-implementation.md:26` |
| 4 个改名测试定向 pytest | 0 | `39 passed`（迁移前 `39 passed`） | `backend-implementation.md:13,47` |
| `pytest -q tests/system/test_startup_warmup.py tests/kb/test_kb_routes.py` | 0 | `37 passed`（迁移前 `37 passed`） | `backend-implementation.md:14,48` |
| `pytest --fixtures tests/system/test_startup_warmup.py` | 0 | `rootdir: /Users/wjh/ResearchAgent`；`clean_warmup_registry -- conftest.py:124` | `backend-implementation.md:51` |
| `git diff --check` / `git diff HEAD --check` | 0 | 无空白 / 冲突标记输出 | `frontend-implementation.md:28`；`backend-implementation.md:49-50` |
| `.venv/bin/python -m ruff check conftest.py` | 0 | `All checks passed!` | `backend-implementation.md:52` |

- **通过数一致性核对**：追加范围四收口全量为 `4557 passed, 2 skipped, 69 subtests`（`docs/sdd/spec-status-changelog.md`「实施中 → 已完成」条目）；本轮 `4559 passed` 净 **+2**，恰对应 `gray_contract.py` 新增的 2 个 R1 静态契约测试（`test_r1_four_grey_card_text_rules_use_muted_strong`、`test_r1_grey_text_wcag_and_live_asset_versions`，见 `git diff HEAD -- tests/frontend/`），与 spec:1235「不删测试 / 不 skip / 不 xfail」一致，无测试丢失。
- **覆盖率如实登记**：本轮实测 **83.02%**（`TOTAL 51890 8811 83.02%`，`full-regression-coverage.txt:294`）。`.coveragerc:11-22` 明确「刻意不设置 fail_under」，未设 `--cov-fail-under`、未放宽阈值、未虚报（此处如实写 83.02%，不以「≥80%」模糊表述代替实测值），符合 spec:1230 与 §2「明确不做」。
- **5 warnings 如实登记**：`full-regression-coverage.txt:64-75` 全为 `<frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked / SwigPyObject / swigvarlink has no __module__ attribute`，系既有第三方 SWIG 绑定告警，非失败、非本轮引入。

### 3.2 浏览器证据（真实 Chromium `getComputedStyle`）
`r1-computed-style.txt:2`（Playwright 代码见 :3-6）：
- 卡片总数 `total:22`，`counts: {needs_ground_truth:10, computed:12}`（10 灰 + 12 computed，与追加范围四验收同口径）。
- 灰卡 `value` / `samples` / `detailRow` 均为 **`rgb(90, 93, 102)`**（= `--muted-strong #5a5d66`），`borderLeftColor: rgb(201, 203, 211)`（= V1 `#c9cbd3`）。
- `computed` 卡 `borderLeftColor: rgb(40, 124, 67)`（**绿**）、`value: rgb(37, 39, 43)`，证实 computed 配色逐字未变、D3 不回归。
- `liveCss: ["/assets/styles.css?v=77"]`，生效 CSS 唯一且为 77。
- `grey.params: null` 为**非阻塞**：该灰卡无 `.evaluation-metric-params` 节点，`pick()` 返回 null 属查询无节点而非色值错误；静态 CSS 契约已验证 6 条 `--muted-strong` 规则（`deploy-verification.json:15` `gray_muted_strong_rules: 6`、`gray_contract.py` `test_r1_four_grey_card_text_rules_use_muted_strong`）。

### 3.3 部署证据
`deploy-verification.json`（`conclusion: PASS`）：
- `health: 200`、`index: 200`、`styles_css_v77: 200`、`research_tasks_js_v26: 200`、`evaluation_options: 200`（全 200）。
- `live_stylesheet: <link rel="stylesheet" href="/assets/styles.css?v=77">`、`live_research_js: <script src="/assets/research-tasks.js?v=26"></script>`（A1 / D2 生效版本部署侧复核一致）。
- `gray_muted_strong_rules: 6`、`search_layer_present: 3`、`layout_check: test layout: ok / EXIT=0`。

**裁决**：以上命令退出码全 0、全量 0 failed / 0 error、静态契约与真实浏览器一致、部署 5×200 且 PASS、覆盖率如实量化，满足 spec:1260-1271 全部验证方式与 Gate 5 运行时验证（服务真实启动、跑通主链路，SDD-GATE-CHECKLIST.md:110）。**批准收口**。

---

## ④ P0 / P1 / P2 缺陷清单

| 级别 | 数量 | 证据 |
|---|---|---|
| **P0** | **0** | 最终候选全量 `full-regression-coverage.exit=0`，`4559 passed / 0 failed / 0 error`（`full-regression-coverage.txt:295`）；部署 5×200 + `PASS`；`git status --short` 无 `backend/**` / `frontend/app.js` 业务改动，无接口/数据模型变化；无 API E2E 失败、无关键产物缺失 |
| **P1** | **0** | 6 条灰卡 CSS 静态契约（`gray_contract.py` 新增断言）与 `getComputedStyle` 实测 `rgb(90,93,102)` 一致；WCAG 6.0947:1 ≥ 4.5:1；`check_test_layout.py` EXIT=1 → EXIT=0 且 4 个改名 `R100 / 0 行变化`；conftest 迁移后 `pytest --fixtures` 定位 `conftest.py:124`、两组定向 39+37 passed 不回归；spec 96 行纯追加 0 删除（不翻案） |
| **P2** | **0** | B1 文案 / 命名 / 注释同步已落地（`test_evaluation_metric_grouping.py` 函数名 `_77_and_75 → _77_and_76`、2 处 f-string「为 75」→「为 76」、`dataset_count_rendering.py:86` 注释同步，见 `git diff HEAD -- tests/frontend/`）；改动文件 `conftest.py` 单独 `ruff check` EXIT=0，全仓 185 errors 为**既有** lint 债务、0 新增（`backend-implementation.md:56`）；所有已知项均归入 §6 已知非阻塞项，不构成本轮缺陷 |

> 「0」的判定基于 Read / Grep / `git diff` 与退出码文件的真实事实，非「应该没问题」式结论。**阻塞项：无**。

---

## ⑤ 十项人工验收准备度自评（10/10 就绪，≥9/10 门槛）

| # | 验收准备项 | 准备度 | 证据 |
|---|---|---|---|
| 1 | A 静态资源缓存版本可验收 | 就绪 | `index.html:902 ?v=26` + 2 条纯属性 marker + `_live_versions("research-tasks.js")==[26]` 静态断言；`deploy-verification.json` `research_tasks_js_v26:200` |
| 2 | B P2 诊断文案 / 命名可验收 | 就绪 | 函数名、注释、2 处 f-string 均同步（`git diff HEAD -- tests/frontend/`）；无残留误导性生效文案 |
| 3 | C 测试布局合规可验收 | 就绪 | `check_test_layout.py` EXIT=0 `test layout: ok`；4 个 R100 改名；根 `conftest.py` 收集确认（`pytest --fixtures`） |
| 4 | D 灰卡文字色 WCAG 可验收 | 就绪 | 6 条 `--muted-strong` 静态规则 + 浏览器 `rgb(90,93,102)` + 6.0947:1；computed 绿未回归 |
| 5 | E 覆盖率采集可验收 | 就绪 | `.coveragerc`（`source=backend/app`、无 `fail_under`）+ `TOTAL 83.02%` 实测报告落盘 |
| 6 | 全量回归与单端回归可复核 | 就绪 | `full-regression-coverage.exit=0`、`4559 passed`、`616 passed`、4 条命令 EXIT=0 记录齐备 |
| 7 | 真实浏览器复核产物可复核 | 就绪 | `r1-computed-style.txt`（22 卡 / 10 灰 / 12 computed / 计算样式 / liveCss v=77）含 Playwright 代码可复跑 |
| 8 | 部署 / API 主链路可复核 | 就绪 | `deploy-verification.json` 5×200 + `PASS` + live 资源版本 + `layout_check` |
| 9 | 不翻案 / 台账 / 引用路径可复核 | 就绪 | spec `96+/0 删`、台账 `4+/0 删` 纯增；`git diff --check` / `git diff HEAD --check` EXIT=0；历史评审与四份签字逐字保留 |
| 10 | 双签并列 / 状态流转前置条件 | 就绪（待并列签字） | 本裁决完成 architect 独立评审签字（非自批）；`tester` 验收报告另行出具，双签齐备后由主会话按 §3 将 `实施中 → 已完成`；本代理不自行转状态 |

说明：第 10 项「就绪（待并列签字）」指材料与前置条件齐备、不构成阻塞；按 SDD-GATE-CHECKLIST.md:111/133，tester 签字未落前 spec 保持 `实施中`，与本裁决不代行 tester 签字一致。

---

## ⑥ 已知非阻塞项与「明确不做」逐条核对

### 6.1 已知非阻塞项（如实登记，均不构成本轮缺陷 / 不阻塞收口）
| # | 项 | 事实与证据 | 处置 |
|---|---|---|---|
| 1 | 全仓 `ruff check .` 既有 **185 errors** | `backend-implementation.md:56`：`EXIT=1 / Found 185 errors ([*] 97 fixable)`，分布在 `.codebuddy/skills/**`、`backend/**`、`docs/**`、`scripts/**`、`tests/**` 等，含 4 个改名文件原本就有的 F401/C408/I001；本次唯一有内容改动的 `conftest.py` 单独 `ruff check` EXIT=0，4 个改名文件 0 行变化，**0 新增** | 历史 lint 债务，非本轮引入；未越界顺手修（spec:1235「不改松断言 / 最小改动」精神） |
| 2 | Langfuse `:3000` span 导出超时 / 连接拒绝告警 | `backend-implementation.md:16,54`：迁移前后 stderr 均出现 `Failed to export span batch ... Connection refused`，退出码与通过数不受影响（39→39、37→37、全量 0） | spec:1237 明确不处理（环境依赖 / 超出范围） |
| 3 | Playwright 某灰卡 `.evaluation-metric-params` 取到 `null` | `r1-computed-style.txt:2` `grey.params: null`；该卡无对应 DOM 节点，`pick()` 返回 null 属查询无节点；静态 CSS 契约已验证 6 条规则（`deploy-verification.json:15`、`gray_contract.py` 新增断言）；另 4 类文字色 value/samples/detailRow 均实测 `rgb(90,93,102)` | 非阻塞，静态契约 + 部署侧 6 规则已交叉验证 |
| 4 | 无真实 GitHub Actions workflow | `git status --short` 无 `.github/workflows/**` 改动；spec:1228-1229 说明本环境无法验证平台侧运行且全量测试依赖本地 Ollama / Qdrant / Langfuse | spec §2「明确不做」，另起基础设施 spec |
| 5 | 平台 branch protection 未配置 | 台账「追加范围四成果远程合并」条目已披露该门禁偏差；本轮未改平台配置 | 如实登记为既有门禁偏差，不本轮补配 |
| 6 | 覆盖率阈值门禁未启用 | `.coveragerc:11-22` 刻意不设 `fail_under`；实测 83.02% 如实登记但**未**据此启用 `--cov-fail-under` | spec:1230 明确不做；达标与否如实登记、不虚报、不放宽 |
| 7 | 全量回归 5 warnings | `full-regression-coverage.txt:64-75` 全为 `<frozen importlib._bootstrap>:241` 的 `SwigPyPacked` / `SwigPyObject` / `swigvarlink` `DeprecationWarning` | 既有第三方 SWIG 绑定告警，非失败、非本轮引入 |

> 补充：上一轮遗留「覆盖率未量化」已由 E1 本轮量化为 83.02%（不再遗留）；「`research-tasks.js?v=25` 缓存风险」「R1 灰卡 3.0365:1」「P2 两处文案」「`check_test_layout.py` 5 项历史编号」4 项已由 A/B/C/D 本轮闭环。

### 6.2 「明确不做」逐条核对（spec:1226-1238）
| # | 明确不做 | 核对结果 | 依据 |
|---|---|---|---|
| 1 | 不新增真实 GitHub Actions workflow | ✔ 未新增 | `git status --short` 无 workflow 文件；spec:1228 |
| 2 | 不设 `--cov-fail-under=80` 默认门禁 | ✔ 未设 | `.coveragerc:11-22`（注释明确不设 fail_under + 理由）；实测 83.02% 仅登记 |
| 3 | 不改 `frontend/app.js` / `backend/**` 业务逻辑；不动 22 key / 5 group / 五端点；不加字段或端点 | ✔ 未改 | `git status --short` / `git diff HEAD --numstat` 无 `backend/**`、无 `frontend/app.js`；`node --check` EXIT=0；spec:1242-1244 |
| 4 | 不改 `:root`；灰化规则带 `[data-status="needs_ground_truth"]` 限定；computed/degraded/unavailable 配色逐字不变；不用 `opacity`/`filter`/`display:none` | ✔ 遵守 | `git diff HEAD -- frontend/styles.css`：仅 1 行改色 + 3 行新增，全部带状态限定，`:root` / 基础规则 / 其它状态零改动；浏览器 computed 仍绿 |
| 5 | 不重写历史归档报告中的旧测试路径 | ✔ 未重写 | `backend-implementation.md:69`；4 个改名文件 `R100 / 0 行变化`（docstring 历史编号逐字保留）；`tests/system/conftest.py` / `tests/kb/conftest.py` docstring 保留 |
| 6 | 不改松断言 / 不删测试 / 不 skip / 不 xfail | ✔ 遵守 | 6 处精确断言为**期望值同步**（76→77），`gray_contract.py` 由 `count("var(--muted)")==1` 收紧为 `==0` 并新增 50 行断言；全量通过数 4557→4559（+2 新测试）；无 `skip`/`xfail` 新增 |
| 7 | 不主动合到 `main`、不 force push | ✔ 遵守 | 见 §8 边界确认；本地 `main 440d9e33` 落后 `origin/main 42bbc188` 属既有状态未快进（spec:1236） |
| 8 | 不处理 Langfuse `:3000` 启动与浏览器控制台 4 个其它视图 404 | ✔ 未处理 | `backend-implementation.md:73`；本轮无相关改动，登记为 §6.1 #2 非阻塞项 |
| 9 | 闭环后仅本地 `git commit`，不 push / 不合 main | ✔ 遵守（本代理未执行 commit） | 本代理只读评审，仅落盘本裁决 + 进展日志；spec:1238 |

---

## ⑦ 架构师签字栏

> **结论：批准收口**

- **需求评审**：通过（P0=0 / P1=0 / P2=0，阻塞项无）。
- **技术评审**：通过（数据模型 / 接口 / 边界 / 版本契约逐项有真实文件与命令证据）。
- **验收合并裁决**：批准收口（全量 `EXIT=0` / `4559 passed` / 覆盖率 `83.02%` / 真实 Chromium `getComputedStyle` / 部署 5×200 `PASS`）。
- **验收签字确认**：架构师 `architect` 于本裁决完成独立只读评审与合并裁决签字（签字 **A**，非自批），日期 **2026-11-12**。
- **双签并列、非自批**：`tester` 子代理的验收报告（`docs/sdd/reviews/047-acceptance-review.md`，含通过/不通过结论 + 逐项文件:行依据）**另行出具**，其签字与架构师签字并列构成 Gate 5 双签；本裁决**不代行** tester 签字、**不翻案**历史四份评审签字、**不自行**把 spec 从 `实施中` 转 `已完成`。按 SDD-GATE-CHECKLIST.md:111/133 与 spec:1270-1271，状态流转、台账补记、复盘与本地 commit 由主会话在 tester 报告与签字齐备后执行。
- 评审性质复核：本次为 spec:1270 要求的「一次独立只读评审，非自批」，符合 Gate 5（SDD-GATE-CHECKLIST.md:106-112）。

| 签字方 | 角色 | 结论 | 日期 |
|---|---|---|---|
| `architect`（本文件） | 架构师（评审·合并） | 批准收口 | 2026-11-12 |
| `tester`（另行出具） | 验收子代理 | 待验收报告出具（双签并列） | 2026-11-12 |

---

## ⑧ 边界确认

- **不 push**：本代理未执行、也不会执行 `git push`；分支 `feature/spec-047-followup-cleanup` 保持本地。
- **不合 main**：未执行、也不会执行任何合并到 `main` / `origin/main` 的操作；`origin/main 42bbc188` 保持不动。
- **不 force push**：未执行、也不会执行 `git push --force` / `--force-with-lease` 或 `git reset --hard`。
- **只读评审边界**：本代理仅落盘 `docs/sdd/plans/047/runs/task-20/merge-review.md`（本文件）与进展日志 `.codebuddy/agent-logs/spec-047/task-22/architect/20261112-000407.md`；**未修改任何业务代码、spec 文件、历史评审文档、台账或其它文件**；未执行 `git add` / `git commit`；未新增 spec 编号 / `plans/048/`；未新增真实 GitHub Actions workflow；未设 `--cov-fail-under`；未翻案历史评审与门禁。
- 裁决权仅体现于本落盘结论文档；下游角色只认本文件。

---

## 附：评审依据文件清单（均已 Read / Grep / `git diff` 复核）
1. `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:1200-1294`（追加范围五；`git diff HEAD` 确认 96 行纯追加、0 删除）
2. `docs/sdd/plans/047/runs/task-20/frontend-implementation.md`、`backend-implementation.md`（两端自测报告）
3. `docs/sdd/plans/047/runs/task-20/full-regression-coverage.exit`（`0`）、`full-regression-coverage.txt`（:64-78 warnings/coverage 头、:294 `TOTAL 51890 8811 83.02%`、:295 `4559 passed, 2 skipped, 5 warnings, 69 subtests passed in 887.98s`）
4. `docs/sdd/plans/047/runs/task-20/r1-computed-style.txt`（真实 Chromium `getComputedStyle`）
5. `docs/sdd/plans/047/runs/task-20/deploy-verification.json`（5×200 + `PASS`）
6. `git status --short`、`git diff HEAD --numstat`、`git diff HEAD -- frontend/index.html frontend/styles.css conftest.py tests/conftest.py tests/frontend/ docs/sdd/spec-status-changelog.md`；`.coveragerc`（未跟踪新文件，全文 Read）
7. `docs/sdd/SDD-GATE-CHECKLIST.md:106-112`（Gate 5）、:116-126（子代理产出落地：读回校验）、:128-138（§3 收口清单）
8. `.codebuddy/agents/architect.md:6`（`model: hy4`）；技能文件 `progress-logging` / `coding-standards` / `regression-guard` / `backend-patterns` / `frontend-patterns`（评审维度与项目附录）

> 本文件创建后已按 §2.5 规则 2「不信任回传摘要，必须读回文件确认」执行 Read 读回校验。
