# spec-047 追加范围四（不相关指标灰色弱化）· 最终合并裁决（架构师签字 A）

## 头部四项与证据时点

| 项 | 内容 |
|---|---|
| **评审者** | `architect`（架构师·评审/合并裁决子代理 A） |
| **角色** | 架构师（PR 合并裁决 / 签字 A；与 `tester` 验收签字 R **并列**，互不代行） |
| **模型** | `Tencent Hunyuan Hy`（`hy4`；唯一真源 `.codebuddy/agents/architect.md:6 model: hy4`） |
| **分派方式** | 主会话独立 `Task(architect)` 只读裁决分派（task-19），与 `tester` 并行；**不得由实现方自批** |

> **证据时点**：2026-11-12 06:47–06:55 CST。**06:54:04 补记**：`tester` 并行出具的验收评审 §16 已落盘（文件 835 → 1023 行），本裁决已独立读回其 §16.9 最终结论「**通过**」与 §16.10「验收签字 **R（已填）** / 通过 / 2026-11-12」，两签（R ＋ A）齐备。
> **git 只读基线**：分支 `feature/spec-047-unrelated-metric-greyout`；HEAD = `origin/main` = `cdbb83cc`（PR #4 squash 合并已完成）；`git diff --cached --stat` 为空，追加范围四改动全部为工作树未提交，符合「裁决通过后由主会话执行本地 `git commit`」。
> **裁决性质**：独立只读裁决。未改任何代码 / 测试 / 配置 / spec 正文 / 状态台账 / 评审历史；未 `git commit / push / 合 main / reset / stash`。唯一写入＝本裁决文档 ＋ 架构师进展日志（工作树新增的 `M docs/sdd/reviews/047-acceptance-review.md` 为 `tester` 并行 §16 追加，非本裁决所改）。
> **并列签字**：验收评审 `docs/sdd/reviews/047-acceptance-review.md` §16（验收签字 R）由 `tester` 独立出具（§16.0 头部四项 / §16.12 纪律声明 / 前 835 行 sha 未变），本裁决**不代签、不预判**；§16.11「架构师合并裁决」栏留空由本裁决签字补齐。

---

## 一、收口 DoD 逐条结论（7/7 通过，附 `文件:行号` / 命令退出码证据）

### DoD 1｜三份评审有真实结论；代码评审 APPROVE（P0=0 / P1=0）— **通过**
- 需求评审 `docs/sdd/reviews/047-requirement-review.md:243-249` §16「**通过**」，需求侧 **P0=0 / P1=0**；头部四项与证据时点 `:235-239`（2026-11-12 05:53–06:05，独立 `Task(architect)`）。
- 技术评审 `docs/sdd/reviews/047-tech-review.md:564-576`「追加范围四技术评审」「**通过（附强制约束）**」，**P0=0 / P1=2**；`:687-692` 判两项 P1 均「必须修复但非阻塞」、不判打回；`:630-634` 为 WCAG 与 R1 落盘裁决。
- 验收评审：`docs/sdd/reviews/047-acceptance-review.md` 历史 §7「通过」/ §9 架构师签字 / §13 / §14 / §15 各章均为真实落盘结论；**追加范围四 §16 已由 `tester` 独立并行出具并于 2026-11-12 06:54:04 落盘**（文件 835 → 1023 行，`grep -nE '^#{1,3} .*§16'` 命中 `:839`）：`:844-851` 头部四项（评审者 `tester` / 角色 QA / 模型 `hy4` / 独立 `Task(tester)` 分派）；`:988-995` §16.9 最终结论「**通过**」、准备度 **10/10**、无 P0/P1、无关键产物缺失、0 断链、6 项已知非阻塞如实登记；`:997-1006` §16.10 **验收签字 R（已填）／通过／2026-11-12**；`:1008-1016` §16.11「架构师合并裁决」栏留空交本裁决签署；`:1018-1023` §16.12 纪律声明；`:841,857` 声明 §1–§15 逐字保留、前 835 行 sha `1cebd1ae…` 追加前后未变。分派依据 `plans/047/task-19-evaluation-gray-style-e2e.md:25`；并行轨迹见日志 `.codebuddy/agent-logs/spec-047/task-19/tester/20261112-064656.md`。
  - **时点补记（诚实登记）**：本裁决首次取证时点（06:53:40）§16 尚未落盘（文件 835 行 / mtime 05:49:45 / `spec:1148` 仍标「待评审（未执行）」），当时按「两签并列」口径列为**放行硬前置**、不预判 tester 结论；最终签字时点（06:54:04 后）§16 已落盘且结论「通过」，本裁决已独立读回核实，**硬前置已满足、两签齐备**。全过程未代签、未自批、未虚报全绿。
- 代码评审 `docs/sdd/reviews/047-frontend-gray-style-review.md:18-22,193`「**通过（Approve）**」，**P0=0 / P1=0 / P2=1**，`Verdict: APPROVE — 0 CRITICAL / 0 HIGH`；头部四项 `:3-10`（`frontend-reviewer` / `hy4` / 独立 `Task` 分派）。
- **判定**：**通过**（三份评审角色分工独立、结论真实；代码评审 APPROVE；验收 §16 已落盘「通过」＋ 验收签字 R 已填，两签齐备）。

### DoD 2｜单端回归 `614 passed / EXIT=0`；最终全量回归 `4557 passed, 2 skipped / PYTEST_EXIT=0` — **通过**
- 单端 `docs/sdd/plans/047/runs/task-18/frontend-regression.md:12`：`pytest -q tests/frontend/` **EXIT=0 / 614 passed / 0 failed / 0 skipped / 0 xfailed**（`614 passed in 122.64s`）；`:24` `--collect-only` `614 tests collected`（收集数＝通过数，未用 `-k` 过滤）；`:22-23` 新增契约 `9 passed` 与 WCAG 单用例 `1 passed` 均 EXIT=0。
- 最终全量 `docs/sdd/plans/047/runs/task-19/full-regression.txt:77` `4557 passed, 2 skipped, 5 warnings, 69 subtests passed in 731.98s`；`:82` **`PYTEST_EXIT=0`**。

### DoD 3｜真实 API E2E / 部署验证 4 项 200；真实浏览器 E2E 7 步 PASS ＋ 截图 / snapshot 落盘 — **通过**
- `docs/sdd/plans/047/runs/task-19/deploy-verification.json`：`health` / `index` / `styles_css_v76` / `evaluation_options` **4 项 status=200**；`:15` live `<link rel="stylesheet" href="/assets/styles.css?v=76">`、`:19` `needs_ground_truth_rules=6`、`:26` `conclusion=PASS`；服务 `pid=50865`、`RERANKER_ENABLED=false ./deploy/start.sh -d`。
- `docs/sdd/plans/047/runs/task-19/gray-style-e2e.json`：`conclusion=PASS`，`steps` ①–⑦ **全 `PASS`**（22 卡 10 `needs_ground_truth` + 12 `computed` / `getComputedStyle` V1–V6 / computed 绿 / 反伪造 / `<details>` 展开 / degraded 橙 / 切 dataset 恢复 computed）；`:18-43` WCAG `v3_badge=5.063 pass`、`v4_title=6.0947 pass`、`rejected_v3=4.233 fail`（证实未照抄不达标色值）；`:129-134` artifacts 4 项。
- 落盘核实：`computed-style-raw.txt`（真实 `page.evaluate(getComputedStyle)` 原始输出）、`gray-initial.yaml`（1560 行）、`gray-final.yaml`（1725 行）、`gray-cards.png`（155.88 KB）逐一 `test -e` 存在；两套 snapshot 为真实 Chromium 渲染树、截图为真实 PNG。

### DoD 4｜spec 追加范围四 §13 裁决 / 台账 2026-11-12 条目 / 变更日志 — **通过**
- **§13 书面裁决**：`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:1165-1196` —— 裁决 1 V3 `#6b6e78`（4.2330:1）作废 → `#5f626c`（**5.0630:1**）、V4 `6.0947:1`、R1 `3.0365:1` 明令禁 `opacity`/`filter`；裁决 2 精确 live 断言 **6 处**逐条 `文件:行号`（`test_evaluation_asset_versions.py:100,118` / `test_evaluation_dataset_count_rendering.py:87` / `test_evaluation_metric_grouping.py:189` / `test_research_detail_actions_placement_contract.py:223` / `test_memory_return_global_contract.py:210`）；marker 须置 `index.html` 末尾注释区；状态流转 `已确认 → 实施中`。
- **状态台账**：`docs/sdd/spec-status-changelog.md:789,791,793,795` —— 2026-11-12 追加范围四 4 条（`待确认` / 远程合并交付记录 / `待确认 → 已确认` / `已确认 → 实施中`，含两项 P1 裁决与 §13 落盘）齐全。
- **变更日志**：spec 追加范围四 §11 `spec:1151-1157` 三条 2026-11-12；`docs/sdd/plans/047/README.md:132-154`「追加范围四」段（任务清单 17/18/19、证据目录）；`plans/047/task-17-*.md` / `task-18-*.md` / `task-19-*.md` 三份任务文档齐全。
- 说明：`实施中 → 已完成` 与 task 状态回填属**放行前置后续动作**（§四第 2 项），非本 DoD 缺失。

### DoD 5｜引用路径 0 断链 / 复盘 / 人工验收 / 十项准备度 ≥9/10、无 P0/P1、无关键产物缺失 — **通过**
- 复盘 `docs/sdd/retro/2026-11-12-spec047-irrelevant-metric-gray-closure.md`（42 行：完成结果 / 证据链 §四 / 已知限制 §五）落盘；人工验收 `artifacts/spec-047-irrelevant-metric-gray-manual-e2e.md`（57 行：六要素 / 十项准备度 / 已知非阻塞项）落盘。
- 独立断链检查：对复盘 §四、人工验收 §6、spec §13、README 所列 **21 个引用路径**逐一 `test -e`，**0 断链**（无 MISSING 行）；`git diff --check` **EXIT=0**。
- 十项准备度：人工验收文档 `:33-48` 自评 **10/10**（≥9/10 门槛），逐项经本裁决 DoD 1–4 / 6 / 7 独立复核；无 P0/P1、无 API E2E 失败、无关键产物缺失。

### DoD 6｜反伪造 / 不降级红线未被破坏 — **通过**
- `frontend/styles.css:4406-4410` 五条纯 CSS 属性选择器规则，选择器均形如 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"] ...`，仅改 `border-left-color` / `background` / `color`；`computed` / `degraded` / `unavailable` 结构性不受影响 —— E2E ③ computed 绿 `rgb(40,124,67)`、⑥ degraded 橙 `rgb(200,135,26)` / `rgb(255,253,247)`、⑦ 切 `rag-retrieval` 后 `recall_at_k` 恢复 computed 绿。
- 灰卡不隐藏：`computed-style-raw.txt:2` 与 E2E ② `display=grid` / `visibility=visible` / `opacity="1"`；E2E ④ `gray_text` 逐字含 `召回率@k / — / 缺少标注（needs_ground_truth） / 样本数：0 / 原因：该评测集没有 relevant_doc_ids…`，`null_rendered_as_dash=true`、`reason_visible=true`、`sample_count_zero_visible=true`、`no_hidden_cards=true`。
- 无 `opacity` / `filter`：`sed -n '4406,4410p' frontend/styles.css | grep -iE 'opacity|filter|display|visibility|hidden|!important'` **0 命中**；全 `styles.css` 的 `opacity/filter` 均属 welcome 动画 / 菜单 / keyframes 等其它视图，与灰卡无关；E2E `wcag.r1_muted_on_gray` 注「未用 opacity/filter 补救」；spec §13 R1 明令严禁。
- live 版本：`frontend/index.html:8` `<link ... styles.css?v=76>`、`:905` `app.js?v=77` 逐字未动、`:912` 为末尾注释区**纯属性** marker `href="/assets/styles.css?v=75"`（不含 `<link`/`<script` 标签字面）；`frontend/app.js` 与后端零改动（`git diff --stat` 不含）。

### DoD 7｜凑绿排查；`check_test_layout.py` EXIT=1 的 5 项为既有历史文件 — **通过**
- 5 个测试文件 `git diff` 逐行核对：仅 `[75]→[76]` / `["75"]→["76"]` / `<link ...v=75>→v=76` **期望值同步**，**无删断言、无正则放宽、无 skip / xfail**；新增契约 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` `grep -nE 'skip|xfail|pytest.mark'` **0 命中**；单端回归明示 `0 skipped / 0 xfailed`、collect-only 614＝passed 614。
- 快照未迁就实现：`gray-initial.yaml`(1560 行) / `gray-final.yaml`(1725 行) 为真实 Chromium 渲染树，`computed-style-raw.txt` 为真实 `page.evaluate(getComputedStyle)` 原始输出，未见重算失败快照。
- `scripts/check_test_layout.py` EXIT=1 的 5 项**既有历史文件**佐证：独立执行 `git diff -- tests/conftest.py tests/evaluation/test_task03_reproducibility.py tests/evaluation/test_task04_idempotency.py tests/observability/test_task05_decoupling.py tests/platform/test_task06_identity_redaction.py` 输出 **0 行**；`git status --porcelain -- <5文件>` **0 行**；`git diff --stat` 的 12 个改动文件不含这 5 个文件；`git diff --check` **EXIT=0**。

---

## 二、P0 / P1 汇总

| 来源 | P0 | P1 | 处置 |
|---|---|---|---|
| 需求评审 §16 | 0 | 0 | 通过 |
| 技术评审「追加范围四」 | 0 | **2** | 均「必须修复但非阻塞」，spec §13 书面裁决闭环：V3 `#5f626c` 5.0630:1、精确 live 断言 6 处；task-17 采纳、task-18/19 复验 PASS（E2E WCAG 5.063 / 6.0947） |
| 代码评审 | 0 | 0（P2=1） | APPROVE |
| tester 验收视角（并行日志判定） | 0 | 0 | 具备出具 §16「通过」签字条件 |
| **本合并裁决** | **0** | **0（无阻塞项）** | 两项技术 P1 已闭环，不计收口阻塞 |

---

## 三、架构师合并裁决签字栏（已填）

| 项 | 内容 |
|---|---|
| **签字角色** | `architect`（架构师·评审/合并裁决子代理 A；与 tester 验收签字 R 并列） |
| **结论** | **批准收口** |
| **日期** | **2026-11-12** |
| **生效条件** | **已满足**：验收评审 `docs/sdd/reviews/047-acceptance-review.md` §16 于 06:54:04 落盘，§16.9 结论「通过」/ §16.10「验收签字 R（已填）」/ P0=0 / P1=0 已经本裁决独立读回核实；两签（R ＋ A）齐备，本裁决无条件生效。本裁决不代签、不预判 tester 结论（首次取证时点曾列硬前置，见 DoD 1 时点补记）。 |
| **合并边界** | **不 push、不合 main、不 force push**；`origin/main` 保持 `cdbb83cc`。 |

**签字意见**：7 项收口 DoD 逐条独立只读核实通过，证据链完整（三份评审真实 / 代码评审 APPROVE / 单端 614 / 全量 4557 / 部署 4×200 / 浏览器 7 步 PASS / §13 裁决 / 台账与变更日志 / 0 断链 / 复盘与人工验收 10-10 / 反伪造红线 / 凑绿排查）；无真实 P0/P1 阻塞、无实现或证据缺陷。`tester` 验收签字 R（§16.10「通过」）与 `architect` 合并裁决签字 A（本栏）**两签并列齐备**；本裁决不代签、不由实现方自批、不虚报全绿。按 Gate 5 / DoD 批准收口，后续状态流转与本地 commit 由主会话执行。

---

## 四、放行前置后续动作（主会话执行，本裁决不代行）

1. **双签齐备（已完成）**：`tester` 已把 `docs/sdd/reviews/047-acceptance-review.md` §16 落盘（06:54:04）且结论「通过 / 验收签字 R / P0=0 / P1=0」，本裁决已独立读回 §16.9 / §16.10 校验；两签（R ＋ A）齐备。主会话执行后续动作前按既有流程再读回一次即可；本项不再构成阻塞。
2. 把追加范围四状态 **`实施中 → 已完成`**（`spec:11` / `spec:993` / `README.md:134`），并回填 spec `:1148`「评审记录」（验收 §16、代码评审）、`README.md` 任务清单与 task-17/18/19 文档状态。
3. 在 `docs/sdd/spec-status-changelog.md` 追加 2026-11-12 **收口条目**（`实施中 → 已完成`），历史条目逐字保留、不翻案。
4. 执行本地 **`git commit`**（Conventional Commits，例如 `feat(spec-047): 追加范围四不相关指标灰色弱化收口`，提交信息含 `Refs: spec-047`）。
5. **本次不 push / 不合 main / 不 force push**；`origin/main` 保持 `cdbb83cc`。

---

## 五、已知非阻塞偏差（如实登记）

1. **无真实 CI workflow**：GitHub 端 branch protection / 1 approval 未配置为平台级强制，approval 以独立 `architect` 落盘报告为准（复盘 `:41`）。
2. **覆盖率未量化**：未跑 `pytest-cov` / 无 `fail_under` 门禁，不虚报 ≥80%（复盘 `:38`）。
3. **R1 对比度**：V5/V7 沿用 `--muted:#8b8e96` 在灰底 `3.0365:1`（改动前 `3.1306:1`）低于 4.5:1，属既有基线退化；spec §13 R1 裁决不扩范围、严禁 `opacity`/`filter` 补救，E2E `gray-style-e2e.json` 已如实记录。
4. **P2 文案**：`test_research_detail_actions_placement_contract.py:223` / `test_memory_return_global_contract.py:210` 的 f-string 失败提示仍写「为 75」，实际断言值已 `["76"]`；代码评审判 P2 非阻塞。
5. **既有 `scripts/check_test_layout.py`**：EXIT=1 的 5 项为历史编号测试，非本任务引入（`git diff -- <5文件>` 0 行佐证）。
6. **`research-tasks.js?v=25` 缓存风险**：远程合并后净增 223 行未升版，浏览器可能命中旧脚本；PR #4 已披露，另案处理（复盘 `:39`）。
7. 附：浏览器控制台 4 个 404 来自其它视图历史会话资源；Langfuse `:3000` 未启动导致 span 导出 transient error，未影响 `PYTEST_EXIT=0`（`full-regression.txt:78-80`）。
8. **时点说明（非偏差，已闭环）**：验收 §16 在首次取证时点（06:53:40）未落盘，为 tester 独立并行签字；06:54:04 已落盘且结论「通过」、验收签字 R 已填，本裁决独立读回核实（§一 DoD 1 时点补记 / §三生效条件 / §四第 1 项）。全程不预判其结论、不虚报全绿、不代签。

---

## 六、纪律声明

- 本裁决为**独立只读裁决**：全程仅 `Read` / `Grep` / `git status | log | diff | diff --check`（只读）/ `test -e` / `grep` / `sed` / `wc` / `stat` / `head` / `tail`；**未改**任何代码 / 测试 / 配置 / spec 正文 / 状态台账 / 评审历史 / 计划文档。
- 未 `git commit` / `push` / 合 `main` / `reset` / `stash`；未跑破坏性 `--force`、未重启服务、未 mock 冒充 E2E、未重算失败快照迁就实现、未改断言凑绿。
- 唯一写入：`docs/sdd/plans/047/runs/task-19/merge-decision.md`（本裁决文档）与架构师进展日志 `.codebuddy/agent-logs/spec-047/task-19/architect/20261112-064728.md`。
- 不代 `tester` 签字、不代主会话收口、不预判并行 §16 结论、不虚报全绿；下游只认落盘文档：本裁决 ＋ `047-acceptance-review.md` §16 ＋ spec 追加范围四 §13 ＋ 状态台账。
