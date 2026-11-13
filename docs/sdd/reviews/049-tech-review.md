# Spec-049 技术评审（Gate 2 · 独立架构师评审）

| 项 | 值 |
|---|---|
| 评审者 | `architect`（架构师评审子代理） |
| 角色 | 架构师（Architect）— Gate 2 技术评审 |
| 模型 | `hy4`（读自 `.codebuddy/agents/architect.md:6` 的 `model` 字段） |
| 分派方式 | `Task(architect)` |
| 日期 | 2026-11-13 |

## 结论

**通过（附意见）** —— 非打回。

- P0 = 0，P1 = 0，P2 = 5；阻塞项 0。
- 评审基于 `Read` / `Grep` / 只读命令的真实文件，无「应该没问题」式结论。
- 附意见按 `SDD-GATE-CHECKLIST.md:73` 沉淀为强制约束清单 C1–C10（10 条，本文件 §强制约束清单），供主会话回填 spec。

## 事实依据（文件:行 / 命令）

### T1 `Promise.finally` 覆盖三条路径

| 路径 | 事实依据 | 结论 |
|---|---|---|
| 成功 | `frontend/literature-maps.js:3224-3242` `async function loadMaps`，`:3238` `return true` | resolve |
| catch `'error'` | `:3239-3241` `setStatus(..., 'error')` + `return false`；`:3495-3498` `setStatus(..., 'error')` 后函数结束 | resolve |
| `requestId` 失配提前 return | `:3477`、`:3480`、`:3482`、`:3484`、`:3496` 五处 `if (requestId !== state.mapRequest ...) return`；`:3471` `if (!mapId) return` | resolve |
| 现状定时器 | `:1580` `let refreshSpinTimer = 0`、`:1582` `classList.add('is-spinning')`、`:1583` `clearTimeout`、`:1584` `setTimeout(..., 700)`、`:1585-1586` 裸调 `selectMap` / `loadMaps` 无 `.finally` | 边界 1 待改 |
| 048 登记 | `docs/sdd/reviews/048-acceptance-review.md:172`、`docs/sdd/plans/048/runs/task-04/final-verification.md:63` | 700ms P2 |

验证方式：`sed -n '3224,3242p;3470,3499p' frontend/literature-maps.js`；`grep -n "return true\|return false\|return;" frontend/literature-maps.js`；`task-02:27,30,57-58` 静态契约断言（源码无 `setTimeout(...700...)`、含 `.finally(` 移除 `is-spinning`）。

### T2 快速连点

- 事实依据：`frontend/literature-maps.js:1583` `clearTimeout` + `:1584` 重新 `setTimeout`；`resetMapSelectionState`（`:3344`）`++state.mapRequest` 使先发请求的 `requestId` 失配并提前 return（`:3477`）。
- 共享 `refreshButton.classList`（`:1582`）下，任一 Promise 的 `.finally` 执行 `remove('is-spinning')` 即移除 class；连点不残留，旋转结束可与末次请求不同步。
- 验证方式：`task-04:29` E2E 连点 3 次「`is-spinning` 残留 0、调用次数 = 点击次数」；`spec:62` 边界 3。→ **C3**。

### T3 `loadMaps` / `selectMap` 保持 `async`

- 事实依据：`grep -n "async function loadMaps\|async function selectMap" frontend/literature-maps.js` = `:3224` / `:3470`；`task-02:27` 只改 `:1585-1586` 调用链，不改函数体。
- 验证方式：`git diff -- frontend/literature-maps.js` 仅含 `:1579-1587` 段；`node --check frontend/literature-maps.js` `EXIT=0`。→ **C2**。

### T4 升版 `v=48 → v=49` 的精确断言面

| 位置 | 当前值 | 目标 |
|---|---|---|
| `frontend/index.html:903` | `<script src="/assets/literature-maps.js?v=48"></script>` | `v=49` |
| `tests/frontend/fixtures/literature_map_component.html:1135` | `literature-maps.js?v=48` | `v=49` |
| `tests/frontend/test_literature_map_tabs_and_refresh_icon.py:46` | `assert js_live == ["48"]` | `["49"]` |
| `tests/frontend/test_frontend_map_groups_exports.py:53` | `"/literature-maps.js?v=48" in fixture` | `v=49` |
| `tests/frontend/test_frontend_map_mobile_contract.py:97` | `"/literature-maps.js?v=48" in FIXTURE...` | `v=49` |

- 冻结项：`test_literature_map_tabs_and_refresh_icon.py:47` `css_live == ["36"]`、`frontend/index.html:11` `css?v=36`、`test_frontend_map_header_actions_readability.py:27` `MAP_CSS_VERSION = 36`（供 `:291` / `:318`）、`frontend/index.html:8,905` `?v=77` 不变。
- 命令实测：`grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js` = 上述 4 处（`index.html` / fixture / groups / mobile）；`grep -rn "js_live" tests/frontend` = `test_literature_map_tabs_and_refresh_icon.py:44,46`。
- 验证方式：升版后 `grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js` = 0 命中；`.venv/bin/python -m pytest -q tests/frontend/` `EXIT=0`、`628 passed`（`final-verification.md:26`）。→ **C5**。

### T5 marker 冻结语义与 211 处 `in INDEX` 断言

- 事实依据：`frontend/index.html:918` `<!-- Spec048 compatibility marker: src="/assets/literature-maps.js?v=47" -->`、`:919` `href="...css?v=34"`，位于 live `:903` / `:11` 之后；`:904-917` 为其它资源的历史 marker 注释区。
- `re.findall(...)[-1] == "47"/"34"` 共 6 行 3 文件：`test_frontend_map_groups_exports.py:54-55`、`test_frontend_map_mobile_contract.py:119-120`、`test_literature_map_tabs_and_refresh_icon.py:75-76`。
- 命令实测：`python -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` = `47 34`；`grep -rn "in INDEX" tests/frontend \| wc -l` = 211（205 行含 `assert` + 6 行非 `assert`）；`grep -ro "in INDEX" tests/frontend \| wc -l` = 214；`grep -rn "literature-maps.js?v=48" ... \| grep "in INDEX"` = 0 命中。
- `211 处 in INDEX` 断言均指向 marker `v=47` / `v=34` / `app.js?v=77` / `styles.css?v=77` 等冻结值（`test_frontend_map_groups_exports.py:18-19`、`test_frontend_map_mobile_contract.py:93-95`、`test_literature_map_tabs_and_refresh_icon.py:72-73`），升版 `v=49` 不改动这些值。→ **C6**。

### T6 C 类 7 项零改动可机械化核对

| 核对点 | 命令 / 事实 | 实测 |
|---|---|---|
| `.github/` | `test -d .github` | ABSENT |
| `.coveragerc` | `grep -n "^fail_under" .coveragerc` | 0 命中；`:21` 仅「刻意不设置 fail_under」注释 |
| ruff 错误数 | `.venv/bin/ruff check . --no-cache --output-format concise` | `Found 185 errors`（`spec:41`） |
| 未跟踪文件 | `git status --short` | 与确认前对照（`task-03:29` 步骤 4） |
| tabs 用例数 | `grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | 12（`spec:68`） |
| 按钮基线 | `test_frontend_button_affordance_contract.py:52` | 56（`spec:68`） |
| NB 台账 | `docs/sdd/plans/049/runs/decision-ledger.md`（`task-03:19`） | 10 行结论 + 依据，C 类逐条「保持现状」 |

- 验证方式：`task-03:29`（确认前后只读状态对照命令输出落盘）、`git diff --stat` 白名单外 0 文件。→ **C9**。

### T7 模块边界 / 复用 / 安全维度

- 模块边界：`spec:25-31` 端点 / 数据模型「无变化」；改动仅 `frontend/literature-maps.js` + `frontend/index.html` + `tests/frontend/**`；`backend/**` 0 改动（`task-02:50`）。并发 / 事务 / 外键 / SSRF / 来源可信维度：本范围无后端 / 端点 / 外发请求 / 凭据改动，不适用。
- 复用（禁止第二套）：`task-02:27` 复用既有 `selectMap` / `loadMaps` 返回的 Promise，不新增定时器 / 计数器 / 请求封装（`regression-guard` 项目加附件第 9 条「禁止重复实现」）。
- 三项必查（`regression-guard:501-504`、`frontend-patterns:666-669`）：`is-spinning` 在 `frontend/literature-maps.css` 有对应选择器；`?v=N` 已升 `v=49`；`grep -c "innerHTML" frontend/literature-maps.js` = 0。
- 验证方式：`git diff --stat`；`node --check frontend/literature-maps.js`；`grep -n "is-spinning" frontend/literature-maps.css`。→ **C2 / C3 / C7**。

## P0 / P1 / P2 判定

| 级别 | 数量 | 条目（事实依据 → 验证方式 → 约束） |
|---|---|---|
| P0 | 0 | 无数据 / 接口 / 安全 / 范围失控 |
| P1 | 0 | 三路径 resolve、版本面 5 处、marker 冻结、C 类核对均有命令实测 |
| P2 | 5 | 见下 |

- **P2-1（reject 传播）**：`frontend/literature-maps.js:3472` `await waitForPendingViewFlush(mapId)` 位于 `:3475` 的 `try` 之外；`waitForPendingViewFlush`（`:3459-3468`）`await pending` 在 `try/finally` 内，异常可传播使 `selectMap` 返回的 Promise reject。`.finally` 对 reject 仍执行移除，调用侧 `.finally` 链须兜底。验证方式：E2E console 无 unhandled rejection；`sed -n '3459,3475p' frontend/literature-maps.js` 静态审阅。→ **C4**。
- **P2-2（连点共享 class）**：`:1582` 共享 `classList`，任一 Promise 先 resolve 即提前 `remove`；不残留成立，旋转结束可与末次请求不同步。验证方式：边界 3 E2E 连点 3 次「残留 0、调用次数 = 点击次数」。→ **C3**。
- **P2-3（升版同步面）**：T4 五处精确值 + `js_live == ["49"]` 须一次同步，任一遗漏即静态断言失败。验证方式：`grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js` = 0 命中；`pytest -q tests/frontend/` `EXIT=0`。→ **C5**。
- **P2-4（三项必查 + 断言不放宽）**：DOM 契约 / `?v=N` / XSS 三项必查与「不改松 / 删 / skip / xfail」。验证方式：`grep -rn "skip\|xfail" tests/frontend/` 无新增；`git diff -- tests/frontend/` 无 assert 删除 / 放宽。→ **C7 / C8**。
- **P2-5（211 / 214 口径）**：行数 211、字面串 214。验证方式：按 `grep -rn "in INDEX" tests/frontend \| wc -l` = 211 核对。→ **C6**。

## 强制约束清单（spec 级，C1–C10，共 10 条）

> 本清单为「通过（附意见）」的意见沉淀，不修改 spec 原文，供主会话回填；下游只认落盘文档，与 spec 正文同等强制。

- **C1（定时器移除 / `.finally` 三路径覆盖）**：必须删除 `frontend/literature-maps.js:1580-1584` 的 `refreshSpinTimer` / `clearTimeout` / `setTimeout(..., 700)`；必须在 `:1585-1586` 的 `selectMap(id)` / `loadMaps()` 调用链接 `.finally(() => refreshButton.classList.remove('is-spinning'))`。事实依据：`literature-maps.js:1580-1586,3224-3242,3470-3499`；`048-acceptance-review.md:172`。验证方式：`sed -n '1579,1587p' frontend/literature-maps.js \| grep -c "setTimeout"` = 0；`sed -n '1579,1587p' frontend/literature-maps.js \| grep -c "\.finally"` ≥ 1；`task-02:57` 静态契约断言 + 边界 2 三场景 E2E。
- **C2（保持 `async` 与既有语义）**：`loadMaps`（`:3224`）与 `selectMap`（`:3470`）保持 `async`，返回值、状态文案、既有 `catch`、`refreshButton` 的 `id` / `title` / `aria-label="刷新状态"` / 无可见文字 / `prefers-reduced-motion` / ≥44px 逐字不变。事实依据：`literature-maps.js:3224,3470`；`048-tech-review.md:128-129,133`（C4/C5/C9）；`spec:63-64`。验证方式：`git diff -- frontend/literature-maps.js` 仅 `:1579-1587` 段；`node --check frontend/literature-maps.js` `EXIT=0`；`test_frontend_map_header_actions_readability.py:239,245,266`。
- **C3（连点不残留 / 禁止第二套）**：快速连点不累积定时器、不残留 `is-spinning`，每次点击逐次触发 `selectMap` / `loadMaps`（调用次数 = 点击次数）；不得新增第二套定时器 / 计数器 / 请求封装。事实依据：`literature-maps.js:1582-1586,3344,3477`；`spec:62`；`regression-guard` 项目加附件第 9 条。验证方式：`task-04:29` E2E 连点 3 次「残留 0、调用次数 = 3」；`git diff -- frontend/literature-maps.js` 无新 `setTimeout` / 计数变量。
- **C4（reject 兜底）**：调用侧 `.finally` 链须对 `selectMap` 的 reject 兜底（`.catch` 或静态确认 `state.viewFlushPromise` 不 reject），不得产生 unhandled rejection。事实依据：`literature-maps.js:3459-3468,3472,3475`。验证方式：E2E console 0 unhandled rejection；`sed -n '3459,3475p' frontend/literature-maps.js` 静态审阅。
- **C5（升版 `v=49` 五处同步 + 常量冻结）**：`frontend/index.html:903`、`tests/frontend/fixtures/literature_map_component.html:1135`、`test_literature_map_tabs_and_refresh_icon.py:46`（`js_live == ["49"]`）、`test_frontend_map_groups_exports.py:53`、`test_frontend_map_mobile_contract.py:97` 同步 `v=48 → v=49`；`css_live == ["36"]`（`:47`）、`MAP_CSS_VERSION = 36`（`test_frontend_map_header_actions_readability.py:27`）、`frontend/index.html:8,905` `?v=77` 不变。事实依据：`spec:65,67`；`task-02:20,28-31`。验证方式：升版后 `grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js` = 0 命中；`.venv/bin/python -m pytest -q tests/frontend/` `EXIT=0`、`628 passed`。
- **C6（marker 冻结 / `[-1]` 语义 / 211 行断言）**：`frontend/index.html:918-919` 两条纯属性注释 marker 不新增 / 不移动 / 不删除；6 行 `re.findall(...)[-1] == "47"/"34"` 逐字不动；`in INDEX` 断言按行数 211 核对（字面串 214 不参与判定）。事实依据：`index.html:903,918-919,11`；`test_frontend_map_groups_exports.py:54-55`、`test_frontend_map_mobile_contract.py:119-120`、`test_literature_map_tabs_and_refresh_icon.py:75-76`；`spec:66`。验证方式：`python -c` 实算 `re.findall(...)[-1]` = `47 34`；`grep -rn "in INDEX" tests/frontend \| wc -l` = 211；`git diff -- frontend/index.html` 不含 `:918-919`。
- **C7（CSS / 常量 / 三项必查）**：`frontend/literature-maps.css` 内容与 `css?v=36` 不变、`MAP_CSS_VERSION = 36` 不变、窄屏 2px 余量不变、不新增 `?v=` marker；`is-spinning` class 在 CSS 有对应选择器、`?v=N` 已升 `v=49`、`innerHTML` 0 命中。事实依据：`spec:67,79`；`regression-guard:501-504`；`frontend-patterns:666-669`。验证方式：`git diff -- frontend/literature-maps.css` 空；`grep -n "is-spinning" frontend/literature-maps.css` 命中；`grep -c "innerHTML" frontend/literature-maps.js` = 0。
- **C8（断言不放宽 + 基线保持）**：不改松 / 删 / skip / xfail 任何断言；`test_literature_map_tabs_and_refresh_icon.py` 12 条与 `test_frontend_button_affordance_contract.py:52` 基线 `56` 保持。事实依据：`spec:68,82`；`final-verification.md:17`（`+12` 条）。验证方式：`grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py` = 12；`grep -rn "skip\|xfail" tests/frontend/` 无新增；`git diff -- tests/frontend/` 无 assert 删除 / 放宽。
- **C9（C 类零改动 + 台账 + 不虚报）**：`.github/` 仍不存在、`.coveragerc` 无生效 `fail_under`、ruff `Found 185 errors` 不变、`git status --short` 未跟踪清单不变；NB1–NB10 逐条「结论 + 事实依据（文件:行 / 命令）」落盘，C 类 7 项写「保持现状」不得写「已修复」；不虚报 CI 全绿 / branch protection 通过 / 覆盖率门禁达标。事实依据：`spec:69-70,75-79`；`task-03:29`；`048-acceptance-review.md:169-181`。验证方式：`test -d .github` = 不存在；`grep -n "^fail_under" .coveragerc` = 0 命中；`git diff --stat` 白名单外 0 文件；`grep -rn "CI 全绿\|branch protection 通过\|覆盖率门禁达标" docs/sdd/reviews/049-*.md docs/sdd/plans/049/ docs/sdd/retro/` = 0 命中。
- **C10（分派 / 真实 API E2E / 交付）**：含 `.js` / `.html` / `.py` 的实现一律由 `frontend-dev` 分派（`spec:140,144`、`SDD-GATE-CHECKLIST.md:90-93`）；收口跑真实 API E2E（点击刷新、捕获真实 API 响应含实体 ID、`is-spinning` 响应结束后移除、连点 3 次无残留、状态栏更新），十项人工验收准备度 ≥9/10、窄屏 checks 判定栏写明口径，全量 `EXIT=0` 且通过数 ≥ 4571（`final-verification.md:13`）；交付省略 PR、fast-forward 直接推送远端 `main`，不 force push、不新建 PR。事实依据：`spec:71,83-84,140,144`；`task-04:28-32,47,57`；`048-acceptance-review.md:187`。验证方式：`task-04:28-30` 命令表；`docs/sdd/reviews/049-acceptance-review.md` 判定行；`git status --short` 无 PR / force 相关改动。

## 结论生效条件

- 本「通过（附意见）」以上述 C1–C10 为硬约束；`frontend-reviewer` / `frontend-tester` 逐条核对 C1–C10 落盘情况，`tester` 按 spec 边界 1–12 / 产品使用步骤逐项判定。
- 架构决策与跨端边界以本落盘文档为准；`spec:162-164` 评审记录三行按真实结论回填。
