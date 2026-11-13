# Spec-049 前端代码评审（frontend-reviewer）

> 只读评审。唯一产出：本文档。评审范围：本轮 `git diff` 涉及的 `frontend/**` 与 `tests/frontend/**` 文件。
> 文档只写结论、事实依据（文件:行 / 命令）与验证方式。
> 约束唯一落点：`docs/sdd/reviews/049-tech-review.md:100-113`。

## 1. 结论

**APPROVE**

| P0 | P1 | P2 |
|----|----|----|
| 0  | 0  | 0  |

- 本轮实现评审新增问题计数：P0=0 / P1=0 / P2=0。
- C1–C10 满足数：10/10。三项必查：3/3 PASS。四项必守：4/4 PASS。
- Gate 2 技术评审已登记的 P2-1~P2-5（`docs/sdd/reviews/049-tech-review.md:94-98`）为评审意见条目，不在本轮新增问题内重复计数。

## 2. 范围与只读上下文

- `git diff --staged`：空。`git diff --stat`：`7 files changed, 34 insertions(+), 10 deletions(-)`。`git --no-pager diff`：全文已读。`git status --short`：7 个 `M` 文件。`git --no-pager log --oneline -5`：HEAD `b160c58d`。
- `git --no-pager diff --name-only`（7 文件）：
  - `docs/sdd/spec-status-changelog.md`（归属见 §6）
  - `frontend/index.html`
  - `frontend/literature-maps.js`
  - `tests/frontend/fixtures/literature_map_component.html`
  - `tests/frontend/test_frontend_map_groups_exports.py`
  - `tests/frontend/test_frontend_map_mobile_contract.py`
  - `tests/frontend/test_literature_map_tabs_and_refresh_icon.py`
- `git --no-pager diff -- frontend/literature-maps.css`：空（EXIT=0），CSS 未在改动清单。
- 参照文档：spec `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:73-84`；实现报告 `docs/sdd/plans/049/runs/task-02/implementation.md`；基线 `docs/sdd/plans/049/runs/decision-ledger.md:24-37`。

## 3. 三项必查

| # | 项 | 结果 | 事实依据（命令 / 文件:行） |
|---|---|---|---|
| 1 | DOM 契约 | **PASS** | `grep -n "is-spinning" frontend/literature-maps.css` → `:613`、`:616`；`grep -n "is-spinning" frontend/literature-maps.js` → `:1581`、`:1583`、`:1586`。刷新按钮 `id` `frontend/literature-maps.js:1193`、`title` `:1194`、`aria-label='刷新状态'` `:1195`、两参数 `createElement('button', 'icon-button literature-map-tool')` `:1191`（无可见文字）、`append(refreshIcon)` `:1197`；`prefers-reduced-motion` CSS `:615-617`、`min-width/min-height: 44px` CSS `:619`。JS diff 单 hunk `@@ -1577,13 +1577,14 @@`，上述段落未触及。`activateMapTab` 定义 `:1558`、tab DOM 契约 `:1552-1616` 逐字不变（`test_literature_map_tabs_and_refresh_icon.py:82-128`）。 |
| 2 | `?v=N` 版本 | **PASS** | 五处同步：`frontend/index.html:903` `literature-maps.js?v=49`、`tests/frontend/fixtures/literature_map_component.html:1135`、`test_literature_map_tabs_and_refresh_icon.py:46` `js_live == ["49"]`、`test_frontend_map_groups_exports.py:53`、`test_frontend_map_mobile_contract.py:97`。`grep -rn "literature-maps.js?v=48" frontend tests/frontend --include="*.py" --include="*.html" --include="*.js"` → 0 命中（EXIT=1）。`grep -rn "literature-maps.js?v=49" ...` → 4 处字面命中（第 5 处为 `:46` 的数字断言，非字面 URL）。`index.html:11` `css?v=36`、`:905` `app.js?v=77`、`test_frontend_map_header_actions_readability.py:27` `MAP_CSS_VERSION = 36` 不变。`index.html:918-919` 两条 marker 未动（`git --no-pager diff -- frontend/index.html` 单 hunk `@@ -900,7 +900,7 @@`；`git --no-pager diff -- frontend/index.html \| grep -c "Spec048 compatibility marker"` = `0`）。实算 `python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` → `47 34`。`grep -rn "in INDEX" tests/frontend \| wc -l` → `211`。 |
| 3 | XSS | **PASS** | `grep -c "innerHTML" frontend/literature-maps.js` → `0`（EXIT=1）。新增断言 `test_literature_map_tabs_and_refresh_icon.py:152-168`；`git --no-pager diff -- tests/frontend/ \| grep "^+" \| grep -iE "innerHTML\|<svg\|iconfont\|font-icon"` → 0 命中（EXIT=1）。`test_literature_map_tabs_and_refresh_icon.py:150`、`:179` 断言图标仅 CSS 形状、全模块禁 `innerHTML`；文本渲染路径 `frontend/literature-maps.js:209,232,241,263` 使用 `textContent`。 |

## 4. 四项必守（逐条 PASS/FAIL）

| # | 项 | 判定 | 核对命令与命中行 |
|---|---|---|---|
| 1 | DOM 契约（class ↔ CSS 双向） | **PASS** | 正向 `grep -n "is-spinning" frontend/literature-maps.css` → `:613`、`:616`；JS 侧 `grep -n "is-spinning" frontend/literature-maps.js` → `:1581`、`:1583`、`:1586`。反向：CSS 本轮零改动（`git --no-pager diff -- frontend/literature-maps.css` 空，EXIT=0），无新增 CSS 钩子；刷新按钮与 tab DOM 契约逐字不变（§3 项 1）。 |
| 2 | 版本号 `?v=N` | **PASS** | `git --no-pager diff -- frontend/literature-maps.js` 非空（单 hunk `@@ -1577,13 +1577,14 @@`）→ `grep -n "literature-maps.js?v=" frontend/index.html` → `:903` `v=49`、`:918` `v=47`（marker）；fixture `:1135` 与 3 个测试断言同步（§3 项 2）。`literature-maps.css` 零改动 → `css?v=36`（`:11`）不升。 |
| 3 | XSS（禁 `innerHTML` 拼接用户输入） | **PASS** | `grep -c "innerHTML" frontend/literature-maps.js` → `0`（EXIT=1）；新增断言 diff `^+` 行 0 命中 `innerHTML` / `<svg` / `iconfont` / `font-icon`；`grep -n "node.textContent = String(text)\|content.textContent = text\|refs.status.textContent = message" frontend/literature-maps.js` → `:209,232,241,263`。 |
| 4 | CSS 作用域 | **PASS** | `git --no-pager diff -- frontend/literature-maps.css` 空（本轮零改动）；`grep -n "literature-map-refresh-icon\|literature-map-refresh-button" frontend/literature-maps.css` → `:609`、`:610`、`:611`、`:613`、`:614`、`:616`、`:619`，选择器全部 `#literature-maps-view` 前缀；`grep -nE "^[a-z][a-z0-9]* *\{" frontend/literature-maps.css` → 0 命中（EXIT=1）；`test_literature_map_tabs_and_refresh_icon.py:185-203`、`:206-213` 断言作用域前缀。 |

## 5. C1–C10 逐条判定（`docs/sdd/reviews/049-tech-review.md:100-113`）

| 约束 | 判定 | 事实依据（文件:行 / 命令与输出） |
|---|---|---|
| **C1** 定时器移除 / `.finally` 三路径覆盖 | **满足** | `sed -n '1579,1588p' frontend/literature-maps.js \| grep -c "setTimeout"` = `0`（EXIT=1）；同段 `grep -c "\.finally"` = `2`、`grep -c "\.catch"` = `2`。三路径 Read：`frontend/literature-maps.js:3225-3243`（成功 `:3239` `return true`；catch `'error'` `:3240-3242` `setStatus(..., 'error')` + `return false`）、`:3471-3499`（成功 `:3487-3495`；catch `'error'` `:3496-3499`；requestId 失配提前 `return` `:3478`、`:3481`、`:3483`、`:3485`；`:3472` `!mapId` 提前 `return`），三条路径 Promise 均 settle；移除动作 `:1583`、`:1586`。规格事实依据 `049-tech-review.md:104`。 |
| **C2** 保持 `async` 与既有语义 | **满足** | `git --no-pager diff -- frontend/literature-maps.js \| grep "^@@"` → 仅 `@@ -1577,13 +1577,14 @@`（`bindEvents`，`loadMaps` / `selectMap` 函数体零改动）；`grep -n "async function loadMaps\|async function selectMap\|async function waitForPendingViewFlush" frontend/literature-maps.js` → `:3225`、`:3460`、`:3471`；`node --check frontend/literature-maps.js` EXIT=0；按钮 `id` / `title` / `aria-label` / 无可见文字 `:1191-1197`、reduced-motion `:615-617`、44px `:619` 逐字不变（`test_literature_map_tabs_and_refresh_icon.py:134-151,216-220`）。规格事实依据 `049-tech-review.md:105`。 |
| **C3** 连点不残留 / 禁止第二套 | **满足** | `git --no-pager diff -- frontend/literature-maps.js \| grep "^+" \| grep -iE "setTimeout\|clearTimeout\|counter\|timer\|spinTimer\|request\("` → 0 命中（EXIT=1）；`frontend/literature-maps.js:1580-1588` 每次 click 均 `classList.add('is-spinning')` 并调用 `selectMap(...)` / `loadMaps()`，无 guard / 去重 / 计数器 / 第二套请求封装；调用次数 = 点击次数。规格事实依据 `049-tech-review.md:106`。 |
| **C4** reject 兜底 | **满足** | `.catch(() => {})` 在 `frontend/literature-maps.js:1584`、`:1587`；`waitForPendingViewFlush` `:3460-3468` 的 `await pending` 位于 `try/finally` 内、异常可传播；`selectMap:3473` 该调用位于 `:3476` `try` 之外，reject 路径由调用侧 `.catch` 兜底；`.finally` 对 reject 仍执行 `remove('is-spinning')`（`:1583`、`:1586`）。规格事实依据 `049-tech-review.md:107`、`049-tech-review.md:94`。 |
| **C5** 升版 `v=49` 五处同步 + 常量冻结 | **满足** | 五处：`frontend/index.html:903`、`tests/frontend/fixtures/literature_map_component.html:1135`、`test_literature_map_tabs_and_refresh_icon.py:46`（`js_live == ["49"]`）、`test_frontend_map_groups_exports.py:53`、`test_frontend_map_mobile_contract.py:97`；`grep -rn "literature-maps.js?v=48" frontend tests/frontend --include="*.py" --include="*.html" --include="*.js"` → 0 命中（EXIT=1）；`index.html:11` `css?v=36`、`index.html:905` `app.js?v=77`、`test_frontend_map_header_actions_readability.py:27` `MAP_CSS_VERSION = 36`、`test_literature_map_tabs_and_refresh_icon.py:47` `css_live == ["36"]` 不变。规格事实依据 `049-tech-review.md:108`。 |
| **C6** marker 冻结 / `[-1]` 语义 / 211 行断言 | **满足** | `git --no-pager diff -- frontend/index.html \| grep "^@@"` → 仅 `@@ -900,7 +900,7 @@`；`git --no-pager diff -- frontend/index.html \| grep -c "Spec048 compatibility marker"` = `0`；`index.html:918-919` 两条 marker 逐字在位；`grep -rn '\[-1\] == "47"\|\[-1\] == "34"' tests/frontend/` → 6 行（`test_frontend_map_groups_exports.py:54-55`、`test_frontend_map_mobile_contract.py:119-120`、`test_literature_map_tabs_and_refresh_icon.py:75-76`）；实算 `[-1]` = `47 34`；`grep -rn "in INDEX" tests/frontend \| wc -l` → `211`。规格事实依据 `049-tech-review.md:109`。 |
| **C7** CSS / 常量 / 三项必查 | **满足** | `git --no-pager diff -- frontend/literature-maps.css` 空（EXIT=0）；`MAP_CSS_VERSION = 36`（`test_frontend_map_header_actions_readability.py:27`）；`grep -n "is-spinning" frontend/literature-maps.css` → `:613`、`:616`；`index.html:903` `v=49`；`grep -c "innerHTML" frontend/literature-maps.js` = `0`（EXIT=1）；`index.html:918-919` 之外无新增 `?v=` marker（§3 项 2）。规格事实依据 `049-tech-review.md:110`。 |
| **C8** 断言不放宽 + 基线保持 | **满足** | `grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py` = `12`（`grep -n "^def test_"` → `:43,58,82,99,108,125,134,171,185,206,216,226`）；`test_frontend_button_affordance_contract.py:52` `"literature-maps.js": 56`；`git --no-pager diff -- tests/frontend/ \| grep -E "^[-+].*(assert\|skip\|xfail)"` → 3 行 `-` 均为 `v=48→v=49` 精确值替换、0 行 assert 删除，10 行 `+`（3 行版本精确替换的 `+` 侧 + 7 行新增静态契约断言 `test_literature_map_tabs_and_refresh_icon.py:152-168`）；`git --no-pager diff -- tests/frontend/ \| grep "^+" \| grep -iE "innerHTML\|<svg\|iconfont\|font-icon"` → 0 命中（EXIT=1）；无 `skip` / `xfail` 新增。规格事实依据 `049-tech-review.md:111`。 |
| **C9** C 类零改动 + 台账 + 不虚报 | **满足** | `git --no-pager diff --name-only` → 7 文件，C 类文件（`.github/**`、`.coveragerc`、`ruff.toml`、`frontend/literature-maps.css`、`backend/**`、未跟踪文件）均不在列；`test -d .github` EXIT=1（ABSENT）；`grep -n "^fail_under" .coveragerc` → 0 命中（EXIT=1）；`.venv/bin/ruff check . --no-cache --output-format concise` → `Found 185 errors.`；`docs/sdd/plans/049/runs/decision-ledger.md:11-20`（NB1–NB10 逐条结论 + 依据）、`:41`（C 类 7 项「保持现状、零改动」）；`git diff --stat` 白名单外 1 文件归属见 §6；「不虚报」grep 命中 4 行均为否定式声明（§7）。规格事实依据 `049-tech-review.md:112`。 |
| **C10** 分派 / 真实 API E2E / 交付 | **满足** | `git status --short docs/sdd/specs/049-known-nonblocking-followup-cleanup.md` → `??`；`git --no-pager diff -- docs/sdd/specs/049-known-nonblocking-followup-cleanup.md` 空（EXIT=0）；`git --no-pager log --oneline -1` → `b160c58d`（HEAD 未变，无 add / commit / push）；`implementation.md:95` 记未做 git 写操作。收口真实 API E2E / 全量回归属 task-04 / `tester` 判定范围（§7）。规格事实依据 `049-tech-review.md:113`。 |

## 6. `git diff --stat` 白名单外文件归属

- `git diff --stat` → 7 文件；任务 02 实现白名单 6 文件（`implementation.md:3-12`）；白名单外 1 文件：`docs/sdd/spec-status-changelog.md`（`+6` 行）。
- `docs/sdd/spec-status-changelog.md:1` → `# Spec 状态变更记录`；`git --no-pager diff -- docs/sdd/spec-status-changelog.md \| grep "^+"` → `+6` 行为 Spec049 状态条（新建 spec → 待确认 → 已确认 → 实施中）；`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:3` 列为三处留痕之一；`implementation.md:93` 记「`frontend-dev` 未读取、未编辑、未写入该文件」。
- 归属：**主会话状态台账**。非实现越界、非 C 类改动、非 `frontend/**` 业务代码。C 类 7 项零改动结论（`049-tech-review.md:112`）不受该文件影响。

## 7. 范围外事实（不参与本评审判定）

- `implementation.md:94` 记「未执行全量 `tests/frontend/`；未执行 Chromium E2E」；`049-tech-review.md:113`（C10）收口真实 API E2E / 全量回归属 task-04 / `tester` 判定范围。本评审为静态只读核对。
- 连点共享 `classList`：任一 Promise 先 settle 即提前 `remove('is-spinning')`（`frontend/literature-maps.js:1582-1587`），`049-tech-review.md:95`（P2-2）已登记，边界 3 连点 E2E 由 tester 覆盖。
- `grep -rn "CI 全绿\|branch protection 通过\|覆盖率门禁达标" docs/sdd/reviews/049-*.md docs/sdd/plans/049/ docs/sdd/retro/ 2>/dev/null \| wc -l` → `4`；命中 4 行（`049-requirement-review.md:48`、`:76`、`049-tech-review.md:112`、`plans/049/task-04-verification-and-closure.md:48`）均为「不虚报」否定式声明或验证方式描述，无门禁达标宣称。

## 8. 验证方式汇总（只读命令清单）

| 命令 | 输出 / 退出码 |
|---|---|
| `git diff --staged` | 空 |
| `git diff --stat` | `7 files changed, 34 insertions(+), 10 deletions(-)` |
| `git --no-pager diff` | 全文已读（7 文件） |
| `grep -c "innerHTML" frontend/literature-maps.js` | `0`，EXIT=1 |
| `node --check frontend/literature-maps.js` | 无输出，EXIT=0 |
| `grep -n "is-spinning" frontend/literature-maps.css` | `:613`、`:616` |
| `grep -n "is-spinning" frontend/literature-maps.js` | `:1581`、`:1583`、`:1586` |
| `sed -n '1579,1588p' frontend/literature-maps.js \| grep -c "setTimeout"` | `0`，EXIT=1 |
| `sed -n '1579,1588p' frontend/literature-maps.js \| grep -c "\.finally"` | `2` |
| `sed -n '1579,1588p' frontend/literature-maps.js \| grep -c "\.catch"` | `2` |
| `grep -rn "literature-maps.js?v=48" frontend tests/frontend --include="*.py" --include="*.html" --include="*.js"` | 0 命中，EXIT=1 |
| `grep -rn "literature-maps.js?v=49" frontend tests/frontend --include="*.py" --include="*.html" --include="*.js"` | 4 处字面命中（`:903`、`:1135`、`groups:53`、`mobile:97`）+ 第 5 处 `tabs:46` 数字断言 |
| `python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` | `47 34`，EXIT=0 |
| `grep -rn "in INDEX" tests/frontend \| wc -l` | `211` |
| `grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | `12` |
| `grep -n "async function loadMaps\|async function selectMap\|async function waitForPendingViewFlush" frontend/literature-maps.js` | `:3225`、`:3460`、`:3471` |
| `git --no-pager diff -- frontend/literature-maps.css` | 空，EXIT=0 |
| `git --no-pager diff -- frontend/index.html \| grep "^@@"` | `@@ -900,7 +900,7 @@` |
| `git --no-pager diff -- frontend/literature-maps.js \| grep "^@@"` | `@@ -1577,13 +1577,14 @@` |
| `git --no-pager diff -- tests/frontend/ \| grep -E "^[-+].*(assert\|skip\|xfail)"` | 3 行 `-`（48→49 精确替换）+ 10 行 `+`（3 行版本精确替换的 `+` 侧 + 7 行新增静态契约断言），无 assert 删除 / skip / xfail |
| `test -d .github` | EXIT=1（ABSENT） |
| `grep -n "^fail_under" .coveragerc` | 0 命中，EXIT=1 |
| `.venv/bin/ruff check . --no-cache --output-format concise` | `Found 185 errors.` |
| `git --no-pager log --oneline -1` | `b160c58d` |

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | info   |
| LOW      | 0     | note   |

Verdict: **APPROVE** — 0 CRITICAL / 0 HIGH；P0=0 / P1=0 / P2=0；C1–C10 10/10 满足；三项必查 3/3 PASS；四项必守 4/4 PASS。
