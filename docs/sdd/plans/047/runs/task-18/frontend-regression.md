# spec-047 追加范围四 / task-18 前端单端回归报告

- 角色：`frontend-tester`（独立验证角色，与 `frontend-reviewer` 互不代行）
- 日期：2026-11-12（日志时间戳 20261112-062306）
- 输入：`plans/047/task-18-evaluation-gray-style-review.md`、`specs/047-...md` 文末「追加范围四 §13 Gate 2 技术评审裁决」、`reviews/047-tech-review.md`「追加范围四技术评审」（P1-1 达标色值 / P1-2 六处精确断言清单）、`plans/047/runs/task-17/implementation.md`
- 边界：后端代码零改动 → **不跑后端 pytest**；只核对 `frontend/**` 与 `tests/frontend/`；全程未改任何代码 / 测试 / 配置 / spec / 台账，未 git commit / push / 合 main；所有命令为真实执行，未用 mock 冒充实测。

## 一、命令清单（真实执行，逐条退出码 / 通过数量）

| # | 命令 | 退出码 | 通过数量 / 输出 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/frontend/` | **EXIT=0** | **614 passed / 0 failed / 0 skipped / 0 xfailed**，`614 passed in 122.64s (0:02:02)`；`--collect-only -q` 佐证 `614 tests collected in 0.17s`（收集数 = 通过数，覆盖 `tests/frontend/test_*.py` 全部 **69** 个文件，未用 `-k` 过滤 / skip / xfail / 改测试凑绿） |
| 2 | `node --check frontend/app.js` | **EXIT=0** | 无输出（语法通过） |
| 3 | `git diff --check` | **EXIT=0** | 无输出（无空白错误） |
| 4 | `.venv/bin/python scripts/check_test_layout.py` | **EXIT=1** | 报 5 项既有编号违规（逐条见 §四 阻塞项 1），**均为本任务未改动的 tracked 文件** |

### 命令 1 工具超时现象的如实记录

- 原样前台执行时，启动命令的工具返回 `stderr=命令执行超时`、`exitCode=0`、`stdout=PYTEST_BACKGROUND_STARTED pid=63330`——即前台 shell 等待后台作业触发了工具固定超时标记（与 task-17 自测「全量约 100s+ 触发工具超时」一致）。
- 为使**同一条命令 `pytest -q tests/frontend/` 完整跑完一次并拿到真实退出码**，采用 `nohup` 后台启动 + 轮询：日志由 `[ 58%]` 持续增长到 `[100%]`，生成 `/tmp/task18_pytest.done`，`/tmp/task18_pytest_exit=0`，末行 `614 passed in 122.64s (0:02:02)`。进程未被中途 kill，**覆盖全部 69 个文件、不是子集**，因此无需按文件分批等价覆盖；未宣称分批凑绿。
- 额外直接证据（同环境真实执行）：
  - `.venv/bin/python -m pytest -q tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` → **EXIT=0 / 9 passed in 0.21s**
  - `...::test_wcag_aa_contrast_for_badge_and_title` → **EXIT=0 / 1 passed in 0.19s**
  - `.venv/bin/python -m pytest --collect-only -q tests/frontend/` → **EXIT=0 / 614 tests collected in 0.17s**

## 二、逐项复核（文件:行号证据）

### 2.1 技术评审 P1-2：6 处精确 live 断言均已同步为 `76` / `["76"]`

| # | 文件:行号 | 裁决期望 | 实读内容 | 结论 |
|---|---|---|---|---|
| 1 | `tests/frontend/test_evaluation_asset_versions.py:100` | `[76]` | `assert _live_versions("styles.css") == [76]` | PASS |
| 2 | `tests/frontend/test_evaluation_asset_versions.py:118` | `[76]` | `assert _live_versions("styles.css") == [76]` | PASS |
| 3 | `tests/frontend/test_evaluation_dataset_count_rendering.py:87` | `v=76` | `assert INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=76">') == 1` | PASS |
| 4 | `tests/frontend/test_evaluation_metric_grouping.py:189` | `v=76` | `assert INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=76">') == 1` | PASS |
| 5 | `tests/frontend/test_research_detail_actions_placement_contract.py:223` | `["76"]` | `assert live_css == ["76"]` | PASS |
| 6 | `tests/frontend/test_memory_return_global_contract.py:210` | `["76"]` | `assert live_css == ["76"]` | PASS |

- 6/6 全部同步，无遗漏（spec §4 边界 6 误写的「4 处」已按 §13 裁决 2 补齐第 5/6 处）。均为「只改期望值」，未删断言 / 未改正则 / 未放宽。
- 观察（非阻塞）：`:223` 与 `:210` 的 f-string 失败文案仍写「为 75」（历史文案，如 `f"...版本唯一且为 75：{live_css}"`），但实际断言值已是 `["76"]`；不影响断言正确性，属既有文案，未改动。
- 9 处 `in INDEX` 字符串冻结断言与 2 处范围断言（`>=57` / `>68`）由新增 `v=75` 纯属性 marker 继续满足，本次未改，全量 614 passed 佐证。

### 2.2 技术评审 P1-1：达标色值生效、作废色值缺席、WCAG 复算断言真实通过

| 复核项 | 文件:行号证据 | 结论 |
|---|---|---|
| 达标色值 `color:#5f626c` | `frontend/styles.css:4407` — `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"] .evaluation-metric-status { background: #e9eaee; color: #5f626c; }` | PASS（生效） |
| 作废色值 `#6b6e78` 未在灰化规则/全文出现 | 对 `frontend/styles.css` 全文 Grep `#6b6e78` → **Found 0 matching results**；新契约 `:91-92` `test_deprecated_badge_colour_is_absent` 断言其不在 `_grey_block()` | PASS（0 命中） |
| 契约断言使用达标色值 | `test_evaluation_irrelevant_metric_gray_contract.py:86` `assert "color:#5f626c" in flat`；`:87` `var(--muted-strong)` count==2（V4 标题 + V6 summary，`styles.css:4408/4410`） | PASS |
| WCAG 复算断言（真实公式、锁定裁决值防恒真） | 新契约 `:42-56` 相对亮度线性化 / `_contrast_ratio`；`:113-120` `test_wcag_aa_contrast_for_badge_and_title` — badge≥4.5 且 `abs(badge-5.0630)<0.02`、title≥4.5 且 `abs(title-6.0947)<0.02` | PASS |
| WCAG 断言真实通过 | 单文件 `9 passed` EXIT=0；WCAG 单用例 `1 passed` EXIT=0；含于全量 614 passed | PASS |
| 只读独立复算交叉验证（不依赖测试自身公式） | `V3 #5f626c/#e9eaee = 5.063`、`V4 #5a5d66/#f6f6f8 = 6.0947`、作废 `#6b6e78/#e9eaee = 4.233` —— 与 §13 / tech-review 裁决值逐项吻合，证明断言非恒真 | PASS |

### 2.3 `app.js?v=77` 相关精确断言未受影响（7 处逐字保持 77）

| 文件:行号 | 断言 |
|---|---|
| `tests/frontend/test_evaluation_asset_versions.py:99` / `:117` | `assert _live_versions("app.js") == [77]` |
| `tests/frontend/test_evaluation_dataset_count_rendering.py:85` | `INDEX.count('<script src="/assets/app.js?v=77"></script>') == 1` |
| `tests/frontend/test_evaluation_metric_grouping.py:188` | `INDEX.count('<script src="/assets/app.js?v=77"></script>') == 1` |
| `tests/frontend/test_research_detail_actions_placement_contract.py:225` | `assert live_app == ["77"]` |
| `tests/frontend/test_memory_return_global_contract.py:209` | `assert live_app == ["77"]` |
| `tests/frontend/test_evaluation_strategy_label_rendering.py:108` | `assert live == ["77"]` |
| `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py:126` | `assert _live_versions("app.js") == [77]` |

- live 标签：`frontend/index.html:905` `<script src="/assets/app.js?v=77"></script>` 逐字未动；`frontend/app.js` 在 `git diff --stat` 中**不在改动列表**（零改动）。全量 614 passed 佐证 7 处全部通过。

### 2.4 `v=75` 纯属性 marker 位置与形态

- `frontend/index.html:912` → `<!-- Merge compatibility marker: href="/assets/styles.css?v=75" -->`
- 位于 **907–915 末尾注释区**（`:911` 之后），是 HTML 注释内**纯属性片段**（仅 `href="..."`），**不含 `<link` / `<script` 字面串**，未插入 `<head>`（不污染 `test_frontend_map_header_actions_readability.py:298-302` 取第一个 `styles.css?v=` 的 `active_version`）。
- live CSS 已升 `frontend/index.html:8` `<link rel="stylesheet" href="/assets/styles.css?v=76">`。
- 新契约 `:124-133` 断言 marker 恰好 1 条、位于注释内、不含 link/script、不在 `</head>` 之前 → `9 passed` 佐证真实通过。
- 附：`:908` 的 `src="/assets/app.js?v=75"` 是既有 marker（合并基线），非本任务新增；本次新增的是 `:912` 的 `styles.css?v=75`。

### 2.5 DOM 契约 / 资源版本号 / XSS / CSS 作用域（角色静态清单）

- **DOM 契约**：5 条灰化规则 `frontend/styles.css:4406-4410` 全部以 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 限定，复用既有 class（`.evaluation-metric-status/-label/-value/-params > summary`），**无新增 class**；反向在 `frontend/app.js:7753/7758/7788/7824` 确认这些 class 由 `createElement` 渲染，`:7748-7749` `card.className = 'evaluation-metric-card'` / `card.dataset.status = ...` 仍在（新契约 `:137-139` 有守卫）。CSS 选择器限定 `#evaluation-view` 容器，未污染全局。
- **资源版本号**：`styles.css` 改 → `index.html:8` `?v=75 → ?v=76` 已升级；6 处精确断言同步（§2.1）；`app.js` 未改保持 `v=77`；新增 `v=75` marker 维持 9 处冻结断言。
- **XSS**：本任务 `frontend/app.js` 零改动，未引入任何 `innerHTML` 拼接用户输入；评测卡片动态文本走 `textContent` / `createElement`（`:6786`、`:6839` 等），灰化为纯 CSS、不涉及动态文本渲染。如实记录：文件中既存 `innerHTML` 用法（`:25` `sendButton.innerHTML`、`:323`/`:516` 静态模板字符串、`:1789`/`:6922` 经净化后 `renderMarkdown`）属历史基线、非本任务引入，不构成新增注入面。

## 三、VERIFICATION REPORT（verification-loop 格式）

```
VERIFICATION REPORT — spec-047 / task-18 / frontend-tester
=========================================================
Syntax:    PASS  (node --check frontend/app.js EXIT=0；git diff --check EXIT=0)
Contract:  PASS  (P1-2 六处精确断言 6/6 同步；DOM class 双向一致；614/614 passed)
Version:   PASS  (styles.css?v=76 升级 + 6 处断言 + v=75 纯属性 marker；app.js?v=77 不受影响)
XSS:       PASS  (app.js 零改动，无新增 innerHTML 拼接用户输入；动态文本 textContent)
Tests:     PASS  (614/614 passed, 0 failed, 0 skipped, 0 xfailed；collect-only=614)
Diff:      PASS  (12 tracked + 1 新增测试文件，均在本任务范围；无越界改动)
Layout:    EXIT=1 (check_test_layout.py 既有基线 5 项，非本任务引入，见阻塞项)

Overall:   READY — 前端单端回归【通过】
```

命中项：全量 614 passed（含新增契约 9 passed + WCAG 1 passed）、6 处断言同步、达标色值 `5f626c` 生效且独立复算 5.0630:1、作废 `6b6e78` 0 命中、marker 合规、v=77 断言保持。

## 四、阻塞项（如实说明，均非本任务引入 / 非功能阻塞）

1. **`check_test_layout.py` EXIT=1 — 既有基线编号违规（非本任务引入）**。全部 5 项报错：
   - `tests/conftest.py` — `tests root contains test source`
   - `tests/evaluation/test_task03_reproducibility.py` — `test filename contains delivery id`
   - `tests/evaluation/test_task04_idempotency.py` — `test filename contains delivery id`
   - `tests/observability/test_task05_decoupling.py` — `test filename contains delivery id`
   - `tests/platform/test_task06_identity_redaction.py` — `test filename contains delivery id`

   佐证「非本任务引入」：`git diff -- tests/conftest.py tests/evaluation/test_task03_reproducibility.py tests/evaluation/test_task04_idempotency.py tests/observability/test_task05_decoupling.py tests/platform/test_task06_identity_redaction.py` **输出为空**（`DIFF_EMPTY_EXIT=0`）；`git status --porcelain -- <这5个文件>` **0 行**；`git diff --stat` 的 12 个改动文件与 `git status --porcelain` 全量列表均**不含**这 5 个文件。新建的 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` 位于 `tests/frontend/` 子目录、文件名不含 delivery id，**未出现在报错列表**。按「不改测试凑绿 / 不越界」纪律**未改动这些历史文件**，如实回报 EXIT=1，未为凑绿修改。
2. **全量 pytest 前台工具超时标记（非功能阻塞）**：见 §一 说明，同一命令以 nohup 后台完整跑完一次得到 EXIT=0 / 614 passed，`--collect-only` 佐证 614 collected = 614 passed，无 skip/xfail，非「只跑子集宣称全绿」。
3. **R1（既有基线，移交 task-19）**：V5/V7 沿用 `--muted` 在灰底约 3.0365:1 低于 4.5:1，spec §13 / tech-review R1 登记为非阻塞、不扩范围、严禁 `opacity`/`filter` 补救，由 task-19 `getComputedStyle` E2E 如实记录。本单端静态回归不处理。

## 五、前端单端回归结论

**通过**。在如实记录 `check_test_layout.py` EXIT=1（既有基线、非本任务引入）与全量命令工具超时标记（后台完整跑完 EXIT=0）的前提下：4 条命令均真实执行并逐条记录退出码 / 通过数量；技术评审 P1-2 的 6 处精确断言全部同步为 `76`/`["76"]`；P1-1 达标色值 `color:#5f626c` 生效、作废 `#6b6e78` 全文 0 命中、新增契约的 WCAG 复算断言（5.0630:1 / 6.0947:1）真实通过且可独立复现；`app.js?v=77` 相关 7 处精确断言未受影响；`v=75` 纯属性 marker 位于 `index.html:912` 末尾注释区且不含 `<link`/`<script`。后端零改动，未跑后端 pytest；未改任何代码 / 测试 / 配置 / spec / 台账，未 commit / push / 合 main。

- 报告路径：`docs/sdd/plans/047/runs/task-18/frontend-regression.md`
- 日志路径：`.codebuddy/agent-logs/spec-047/task-18/frontend-tester/20261112-062306.md`
