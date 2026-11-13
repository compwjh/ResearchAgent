# Spec-049 Task-02 实施记录（frontend-dev）

## 1. 改动清单（6 个文件）

| 文件 | 位置 | 改动 |
|---|---|---|
| `frontend/literature-maps.js` | `:1579-1588` `bindEvents` 点击回调 | 删除 `refreshSpinTimer` / `clearTimeout` / `setTimeout(..., 700)`；`selectMap(id)`、`loadMaps()` 各链 `.finally(() => refreshButton.classList.remove('is-spinning'))` 与 `.catch(() => {})`；保留 `classList.add('is-spinning')` 与 `if ... else ...` 分支；`bindEvents(refreshButton, closeDetail)` 签名与后续 6 行事件绑定（`:1589-1594`）逐字不变；`loadMaps`（`:3224`）/ `selectMap`（`:3470`）函数体零改动 |
| `frontend/index.html` | `:903` | `literature-maps.js?v=48` → `v=49`；`:8` / `:905` `?v=77`、`:11` `css?v=36`、`:918-919` 两条 marker 逐字不动 |
| `tests/frontend/fixtures/literature_map_component.html` | `:1135` | `literature-maps.js?v=48` → `v=49`；`css?v=36` 不动 |
| `tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | `:46`、`:152-168` | `js_live == ["48"]` → `["49"]`（`:47` `css_live == ["36"]` 不动）；在既有 `test_refresh_button_is_textless_icon_button_in_canvas_tools` 内追加 17 行静态契约断言，未新增 `def test_` |
| `tests/frontend/test_frontend_map_groups_exports.py` | `:53` | `"/literature-maps.js?v=48"` → `v=49`；`:54-55` 逐字不动 |
| `tests/frontend/test_frontend_map_mobile_contract.py` | `:97` | `"/literature-maps.js?v=48"` → `v=49`；`:119-120` 逐字不动 |

新增静态契约断言（`:152-168`）：点击回调段不含 `setTimeout` / `clearTimeout` / `refreshSpinTimer`；含 `.finally(` 且其中执行 `classList.remove('is-spinning')`；含 `.catch(` 兜底 reject。

冻结项核对：`:54-55` / `:119-120` / `:75-76` 共 6 行 `[-1] == "47"/"34"` 逐字在位；`MAP_CSS_VERSION = 36`（`test_frontend_map_header_actions_readability.py:27`）不变；`frontend/literature-maps.css` diff 为空；`grep -rn "in INDEX" tests/frontend | wc -l` = 211；`git diff -- tests/frontend/` 无新增 `skip` / `xfail`、无 assert 删除或放宽。

## 2. TDD 门

| 阶段 | 命令 | 输出 | EXIT |
|---|---|---|---|
| RED | `.venv/bin/python -m pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | `2 failed, 10 passed in 1.59s`（`:46` 实际 `['48']`；`:160` 点击回调仍含 `setTimeout`）；`grep -c "^def test_"` = `12` | 1 |
| GREEN | 同上 | `12 passed in 0.20s` | 0 |

## 3. 六项自查（真实命令输出与退出码）

### 自查 1
- 命令：`grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js`
- 输出：（无行）
- 退出码：`1`（grep 无匹配）
- 结论：0 命中。

### 自查 2
- 命令：`python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"`
- 输出：`47 34`
- 退出码：`0`
- 结论：与期望 `47 34` 一致。

### 自查 3
- 命令：`node --check frontend/literature-maps.js`
- 输出：（无输出）
- 退出码：`0`
- 结论：EXIT=0。

### 自查 4
- 命令：`grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py`
- 输出：`12`
- 退出码：`0`
- 结论：12（C8 基线保持）。

### 自查 5
- 命令：`.venv/bin/python -m pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py`
- 输出：`............                                                             [100%]`、`12 passed in 0.20s`
- 退出码：`0`
- 结论：EXIT=0。

### 自查 6
- 命令：`git diff --stat`
- 输出：
```
 docs/sdd/spec-status-changelog.md                     |  6 ++++++
 frontend/index.html                                   |  2 +-
 frontend/literature-maps.js                           | 11 ++++++-----
 tests/frontend/fixtures/literature_map_component.html |  2 +-
 tests/frontend/test_frontend_map_groups_exports.py    |  2 +-
 tests/frontend/test_frontend_map_mobile_contract.py   |  2 +-
 .../test_literature_map_tabs_and_refresh_icon.py      | 19 ++++++++++++++++++-
 7 files changed, 34 insertions(+), 10 deletions(-)
```
- 退出码：`0`
- 结论：本任务 6 个文件全部在列；另有 1 个白名单外文件（第 5 节）。

## 4. 三项必查与 C1–C10 核对

| 项 | 事实依据（命令 / 文件:行） | 结果 |
|---|---|---|
| class ↔ CSS | `grep -n "is-spinning" frontend/literature-maps.css` | `:613`、`:616` 命中，EXIT=0 |
| `?v=N` 已升 | `grep -n "literature-maps.js?v=49" frontend/index.html tests/frontend/fixtures/literature_map_component.html` | `:903`、`:1135` 命中，EXIT=0 |
| XSS | `grep -c "innerHTML" frontend/literature-maps.js` | `0`，EXIT=1（无匹配） |
| C1 | `sed -n '1579,1587p' frontend/literature-maps.js \| grep -c "setTimeout"` = `0`（EXIT=1）；同段 `grep -c "\.finally"` = `2`（EXIT=0） | 通过 |
| C2 | `git diff -- frontend/literature-maps.js` 仅 `:1577-1589`；diff 内无 `async function loadMaps` / `async function selectMap` 定义行 | 通过 |
| C3 | 同一 diff 无新增 `setTimeout` / 计数变量 / 请求封装 | 通过 |
| C4 | `.finally(...).catch(() => {})` 位于 `:1582-1584`、`:1585-1587` | 通过 |
| C5 | 自查 1 / 2 / 5 | 通过 |
| C6 | `git diff -- frontend/index.html` 仅 `:903` 一行，`:918-919` 不在 diff；`[-1]` 实算 `47 34`；`in INDEX` = 211 | 通过 |
| C7 | `git diff -- frontend/literature-maps.css` 空；`MAP_CSS_VERSION = 36`；三项必查如上 | 通过 |
| C8 | `def test_` = 12；`git diff -- tests/frontend/` 无新增 `skip` / `xfail`、无 assert 删除或放宽 | 通过 |
| C9 | C 类文件 diff 为空；`git status --short` 未跟踪清单未新增条目；`git diff --stat` 白名单外 1 文件（第 5 节） | 白名单外 1 文件，非本任务产生 |
| C10 | 未改 spec；未做 git 写操作（无 add / commit / push）；未跑全量 `tests/frontend/` | 通过 |

## 5. 阻塞项

1. `git diff --stat` 显示 7 个文件，其中 `docs/sdd/spec-status-changelog.md`（`+6` 行）不在本任务 6 文件白名单内。`frontend-dev` 未读取、未编辑、未写入该文件；需主会话确认归属。
2. 未执行全量 `tests/frontend/`；未执行 Chromium E2E。
3. 未执行 git 写操作（不 add / commit / push）；未改 spec；未改历史归档报告。
