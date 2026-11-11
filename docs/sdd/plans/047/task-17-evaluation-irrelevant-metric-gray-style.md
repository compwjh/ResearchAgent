# task-17 不相关指标灰色弱化：纯 CSS 实现 + 版本契约

> **产出性质**：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 追加范围四 §13 / `spec-status-changelog.md` 2026-11-12「已确认 → 实施中」条）。
> **状态**：`已完成` → 由 `frontend-dev` 执行；依赖：无（本范围首个任务）。
> **基线**：`feature/spec-047-unrelated-metric-greyout`，`origin/main` = `cdbb83cc`；live `styles.css?v=75` / `app.js?v=77`。
> **下游只认落盘文档**：本任务书 + [spec 追加范围四 §13 强制裁决](../../specs/047-evaluation-p2-and-observability-fixes.md) + [技术评审「追加范围四技术评审」](../../reviews/047-tech-review.md) + [需求评审 §16](../../reviews/047-requirement-review.md)。**不得照抄 spec §3 的 `#6b6e78` 与 §4 边界 6 的「4 处」**。

## 一、实现输入（裁决后的唯一口径）

### 1.1 WCAG 达标色值（P1-1 裁决）

| 元素 | 生效值 | 对比度 |
|---|---|---|
| V3 徽章文字 | **`color:#5f626c`**（底 `#e9eaee`） | **5.0630:1 ≥4.5** |
| V3 徽章背景 | `#e9eaee` | — |
| V4 标题 | `var(--muted-strong)`（`#5a5d66`，底 `#f6f6f8`） | **6.0947:1 ≥4.5** |

spec §3 原文的 `#6b6e78`（4.2330:1）**作废，禁止使用**。V5 数值用 `var(--muted)`；V7 samples / detail-row / params 保持 `--muted` 不重复声明（R1 既有基线退化，如实记录、不得用 `opacity` / `filter` 补救）。

### 1.2 视觉契约 V1–V7（全部带状态限定）

所有规则必须写在**原评测 CSS 块之后**（`frontend/styles.css:4390-4405` 之后），选择器一律以
`#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 开头：

| # | 目标 | 实现 |
|---|---|---|
| V1 | 左边框紫 → 灰 | `border-left-color: #c9cbd3;` |
| V2 | 背景淡紫 → 浅灰 | `background: #f6f6f8;` |
| V3 | 徽章紫 → 灰 | 子选择器 `.evaluation-metric-status { background:#e9eaee; color:#5f626c; }` |
| V4 | 标题 → 中性灰 | 子选择器 `.evaluation-metric-label { color: var(--muted-strong); }` |
| V5 | 数值 → 中性灰 | 子选择器 `.evaluation-metric-value { color: var(--muted); }` |
| V6 | `<summary>` 紫 → 灰 | 子选择器 `.evaluation-metric-params > summary { color: var(--muted-strong); }` |
| V7 | samples / detail-row / params | 不新增声明，保持 `--muted` |

**禁止**：`opacity` / `filter: grayscale()` / `display:none` / `visibility:hidden` / 全局 `.evaluation-metric-*` 无状态限定覆盖 / 改 `:root` 变量定义 / 改 `computed`（`#287c43`）/ `degraded`（`#c8871a`+`#fffdf7`）/ `unavailable`（`#b13a3a`+`#fff8f8`）现有规则。

### 1.3 版本与静态契约（P1-2 裁决：精确断言 **6 处**）

1. `frontend/index.html:8`：`<link rel="stylesheet" href="/assets/styles.css?v=75">` → `?v=76`；`app.js?v=77` 逐字不动；全部 legacy marker 保留。
2. 在 **`frontend/index.html` 末尾注释区（`index.html:907-911` 之后）** 新增**一条**纯属性片段兼容 marker，例如
   `<!-- Merge compatibility marker: href="/assets/styles.css?v=75" -->`：
   必须含 `"styles.css?v=75"` 字符串、必须不含 `<link` / `<script` 标签字面串，**不得插入 `<head>`**
   （否则污染 `test_frontend_map_header_actions_readability.py:298-302` 取第一个 `styles.css?v=` 匹配的 `active_version` 语义）。
3. 同步以下 **6 处精确 live 断言**为 `v=76` / `["76"]`（只改期望值，不删断言、不改正则、不放宽）：
   - `tests/frontend/test_evaluation_asset_versions.py:100,118` — `_live_versions("styles.css") == [75]`
   - `tests/frontend/test_evaluation_dataset_count_rendering.py:87` — `INDEX.count('<link ... styles.css?v=75">') == 1`
   - `tests/frontend/test_evaluation_metric_grouping.py:189` — 同上
   - `tests/frontend/test_research_detail_actions_placement_contract.py:223` — `assert live_css == ["75"]`
   - `tests/frontend/test_memory_return_global_contract.py:210` — `assert live_css == ["75"]`
4. 其余 **9 处 `in INDEX` 字符串冻结断言**由新增 `v=75` 纯属性 marker 继续满足（沿用合并时 `app.js?v=74` marker 的既有口径），**不改**；2 处范围断言（`>=57` / `>68`）升版后自然通过，不改。
5. `app.js` 相关精确断言全部不动；**不改 `frontend/app.js`、不改后端、不改 `:root`、不新增 class、不写 `innerHTML`**。

### 1.4 新增静态契约用例

新建 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`（文件名按能力命名，**不含 spec/task 编号**），逐条断言：

- 5 条灰化规则均存在且每条选择器含 `[data-status="needs_ground_truth"]`；
- V1 `#c9cbd3`、V2 `#f6f6f8`、V3 `#e9eaee` + **`#5f626c`**（并断言 `#6b6e78` 不再出现在灰化规则中）、V4/V6 `var(--muted-strong)`、V5 `var(--muted)`；
- 灰化规则块内无 `opacity` / `grayscale` / `display:none` / `visibility:hidden`；
- `computed` 绿 / `degraded` 橙 + `#fffdf7` / `unavailable` 红 + `#fff8f8` 四条基础规则逐字仍在；
- 用 WCAG 2.x 相对亮度公式复算 `#5f626c`/`#e9eaee` ≥4.5:1 与 `#5a5d66`/`#f6f6f8` ≥4.5:1；
- live `_live_versions("styles.css") == [76]`、`_live_versions("app.js") == [77]`；`v=75` 纯属性 marker 存在且在 HTML 注释内、不含 `<link`/`<script`；
- `frontend/app.js` 中 `card.dataset.status` 渲染契约仍在（DOM 零改动）。

## 二、明确不做

不隐藏 / 折叠 / 删除灰卡；不把 `needs_ground_truth` 改成 `computed` 或伪造 0 分；不灰化 `degraded` / `unavailable` / `computed`；不改后端、不动 22 key / 5 group、不加端点 / 依赖；不改 `frontend/app.js`；不灰化分组标题 / 按组 delta；不 push / 合 main / force push。

## 三、验证（必须真实执行并回报退出码）

- `node --check frontend/app.js`
- `.venv/bin/python -m pytest -q tests/frontend/`（单端回归，后端零改动 → **不跑后端 pytest**）
- `git diff --check`
- `.venv/bin/python scripts/check_test_layout.py`
- 三项自查：①CSS 新选择器与 `index.html` 渲染契约对应（无新 class，仅复用既有 class）；②`styles.css` 已改 → `index.html` live `?v=N` 已升且 6 处精确断言同步；③无 `innerHTML`、用户输入仍走 `textContent` / `input.value`。
- 落盘自测结果到 `docs/sdd/plans/047/runs/task-17/implementation.md`（Bash heredoc 单引号定界符，写后 Read 读回校验）。
- 进展日志 `.codebuddy/agent-logs/spec-047/task-17/frontend-dev/<YYYYmmdd-HHMMSS>.md`，回传必须给日志路径。

## 四、交接

完成后交由 task-18（`frontend-reviewer` + `frontend-tester`）评审与单端回归，再由 task-19 做真实浏览器 E2E 与部署验证。
