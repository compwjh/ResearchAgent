# 043 UX 缺陷修复 — 前端回归报告

- 角色：frontend-tester（ECC `e2e-runner` / `verification-loop`）
- 范围：仅前端静态与契约核对（`frontend/**` + `tests/frontend/**`），不跑后端 pytest、不改业务代码
- 环境：node v26.7.0；`.venv/bin/python` = Python 3.11.16（`import playwright, langchain_ollama` 均成功）
- 日志：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261106-002204.md`

## 结论

**BLOCKED** —— 1 个前端用例稳定失败（`test_first_open_fits_a_tiny_saved_view_to_the_real_canvas`），且 `literature-maps.css` 有实质改动但版本号未升。

## 逐项结果

| # | 检查项 | 命令 | 退出码 | 结果 |
|---|--------|------|--------|------|
| 1 | JS 语法 | `node --check frontend/literature-maps.js` | 0 | PASS |
| 1 | JS 语法 | `node --check frontend/app.js` | 0 | PASS |
| 2 | node vm 测试 | `for f in tests/frontend/test_*.js; do node $f; done` | 0 | PASS（20/20） |
| 2 | 附带 contract-tests | `for f in frontend/contract-tests/*.mjs; do node $f; done` | 0 | PASS（4/4） |
| 3 | pytest 全量 | `.venv/bin/python -m pytest tests/frontend -q`（分 5 批） | 1 | **FAIL（395 passed / 1 failed，共 396）** |
| 4 | 版本号一致性 | `grep -n "?v=" frontend/index.html` + 全 tests 断言比对 | 0 | **PARTIAL**（js/app/styles 一致；literature-maps.css 未升） |
| 5 | class ↔ CSS 双向 | `grep -rn "kb-item-jump-target"` / `grep -rn "data-availability"` | 0 | PASS |
| 6 | XSS | `git diff -U0 frontend/ \| grep "^+.*innerHTML"` | 1（0 命中） | PASS |
| 7 | DOM 契约（筛选/篇数） | `grep -n "filteredMaps\|listStatus"` / `sed -n 1805,1809p` | 0 | PASS（筛选）/ **偏差**（篇数回落） |
| 8 | 冲突标记 | `grep -rn '^<<<<<<<\|^>>>>>>>' frontend/ tests/frontend/` | 1（0 命中） | PASS |

## 详细证据

### 1. 语法检查
```
node --check frontend/literature-maps.js   # EXIT=0
node --check frontend/app.js               # EXIT=0
```
补充：`node --check` 传入 `.css` 返回 `ERR_UNKNOWN_FILE_EXTENSION`（引擎不支持该扩展名，非缺陷），CSS 侧改用 diff + class 双向核对。

### 2. node vm 测试
```
JS_PASS=20  JS_FAIL=0      # tests/frontend/test_*.js 共 20 个
MJS_PASS=4  MJS_FAIL=0     # frontend/contract-tests/*.mjs 共 4 个
```
本轮新增的 `test_frontend_kb_jump_focus.js`、`test_frontend_map_card_count_and_availability_badge.js`、`test_frontend_map_view_keep_local_on_return.js`、`test_frontend_map_view_save_on_leave.js` 全部通过。

### 3. pytest（`.venv/bin/python`，必须用 venv）
`--collect-only` 收集 **396 tests**。一次性全量运行会超出工具执行时限（`--timeout` 插件未安装，带该参数报 `EXIT=4 unrecognized arguments`），故按 45 个 py 文件每批 9 个分 5 批：

| 批次 | 结果 |
|------|------|
| BATCH1 | EXIT=0 — 84 passed |
| BATCH2 | EXIT=1 — **1 failed**, 84 passed |
| BATCH3 | EXIT=0 — 78 passed |
| BATCH4 | EXIT=0 — 106 passed |
| BATCH5 | EXIT=0 — 43 passed |

合计 396 = **395 passed + 1 failed**。上一轮子代理报告的 `playwright` / `langchain_ollama` `ModuleNotFoundError` 属**系统 python 误用**导致的环境误判，与代码无关；`.venv/bin/python` 下依赖导入正常。

**唯一失败用例**：`tests/frontend/test_frontend_map_graphics.py::test_first_open_fits_a_tiny_saved_view_to_the_real_canvas`

```
>       assert metrics["scale"] > 1
E       assert 0.35 > 1
tests/frontend/test_frontend_map_graphics.py:141: AssertionError
```
- 稳定性：整文件复跑 `1 failed, 6 passed`（EXIT=1）；单用例复跑 `1 failed`（EXIT=1）→ **100% 稳定复现，非 flaky**。
- 场景：fixture `?tiny-saved-view` 把保存视口设为 `{x:218.19, y:185.00, scale:0.35}`，测试期望首次打开时被判定为「不可用的过小视图」并自动 fit 到 `scale > 1`。
- 根因（本轮 diff 引入）：`frontend/literature-maps.js:2544-2557` 新增 `resolveInitialFitPending()` 取消了原有「最小缩放即未初始化」启发式。旧实现（HEAD 父提交）为：
  ```js
  state.initialFitPending = !Number.isFinite(savedScale)
    || savedScale <= MIN_MAP_SCALE + INITIAL_FIT_SCALE_EPSILON
    || (savedX === 0 && savedY === 0 && savedScale === 1);
  ```
  新实现走第 4 条保守分支 `272`：`hasOwnViewport` 为真、`savedScale=0.35` 有限，最终 `return savedX===0 && savedY===0 && savedScale===1` → `false`，即**不再 fit**，`state.view.scale` 停留 0.35。
- 断言依据来源：该测试由提交 `61096ed6 fix(maps): fit unreadable opening views` 引入，正是本轮 UX 修复要「保留用户视图」的反向约束 —— 新逻辑为了不覆盖用户保存的 `0.35` 缩放，牺牲了「极小缩放视为不可读、首次打开应 fit」的既有契约。
- 附带断言（`:142-146`：节点宽高占比、43px 边距、无标签重叠、`window.__viewBodies == []`）在 scale=0.35 下同样会失败，属同一根因。

### 4. 版本号一致性
`frontend/index.html` 实况：
```
line 8:   <link rel="stylesheet" href="/assets/styles.css?v=68">
line 9:   <link rel="stylesheet" href="/assets/literature-maps.css?v=26">
line 805: <script src="/assets/literature-maps.js?v=41"></script>
line 807: <script src="/assets/app.js?v=69"></script>
```
本轮 `git diff frontend/index.html` 已完成的三处升级：`styles.css 67→68`、`literature-maps.js 40→41`、`app.js 68→69`。

断言比对（全部命中一致）：

| 资源 | index.html | 测试断言位置 |
|------|-----------|--------------|
| `styles.css?v=68` | ✔ | `test_frontend_management_contract.py:79` |
| `app.js?v=69` | ✔ | `test_frontend_management_contract.py:80` |
| `literature-maps.js?v=41` | ✔ | `test_frontend_map_analysis_contract.py:34`、`test_frontend_literature_map_expansion.py:28`、`test_frontend_literature_map_contract.py:28`、`test_frontend_map_groups_exports.py:18,44`、`test_frontend_map_mobile_contract.py:94,97` |
| fixture `literature-maps.js?v=41` | ✔ | `tests/frontend/fixtures/literature_map_component.html:1120` |

**问题**：`frontend/literature-maps.css` 本轮有实质改动（新增 `#literature-maps-view .literature-map-badge[data-availability="usable"]` 规则，diff +3 行），但 `index.html:9` 仍为 `?v=26` **未升版本**。已发布的旧缓存会让「可用」徽章继续套用 `partial` 的橙色样式，正好抵消本次修复的视觉目标。建议升到 `?v=27`（并同步 `test_frontend_map_analysis_contract.py:35`、`test_frontend_literature_map_expansion.py:29` 中的 `literature-maps.css?v=26` 断言）。历史兼容标记行（line 7 / 806 / 809 / 810）为旧版本号存档，无需改动。

### 5. class ↔ CSS 双向
```
styles.css:804  #kb-view .kb-item.kb-item-jump-target { ... }
styles.css:809  #kb-view .kb-item.kb-item-jump-target:focus { ... }
app.js:5106     const KB_JUMP_HIGHLIGHT_CLASS = 'kb-item-jump-target';
app.js:5127-5128  clearKbJumpHighlight() → classList.remove
app.js:5135       applyKbJumpFocus()     → classList.add
```
```
literature-maps.css:37  #literature-maps-view .literature-map-badge[data-availability="usable"] { ... }
literature-maps.js:1824 badge.dataset.availability = 'usable';
```
两处新增样式均**有 JS 实际渲染**，无死样式；CSS 选择器均限定在 `#kb-view` / `#literature-maps-view` 容器内，未污染全局。

### 6. XSS
```bash
git diff -U0 frontend/ | grep "^+.*innerHTML"                                    # 0 命中
git diff -U0 frontend/ | grep "^+.*\(insertAdjacentHTML\|outerHTML\|document.write\)"  # 0 命中
```
新增动态文本处理全部安全：
- `app.js:5136/5163/5178` — `kbStatus.textContent = ...`（含模板变量走 textContent，不拼 HTML）
- `literature-maps.js:1821` — `badge.textContent = mapStatusLabel('ready')`
- `literature-maps.js:1822-1823` — `badge.setAttribute('title'/'aria-label', ...)`
- `literature-maps.js:1836` — `createElement('span', '', \`${cardNodeCount} 篇\`)`（数字经 `normalizeMapNodeCount` 归一）
- 跳转定位只用 `dataset.documentId / dataset.paperId` 比较与 `classList` 操作，不注入 HTML。

### 7. DOM 契约
- **状态筛选下拉仍含 `partial`**：`literature-maps.js:1039` `[['all','全部状态'],['generating','生成中'],['ready','可用'],['partial','部分完成'],['failed','失败'],['stopped','已停止']]` —— PASS；测试 `test_frontend_map_card_count_and_availability_badge.js:271-272` 亦断言该项保持不变。
- **`filteredMaps` 按原始 status**：`literature-maps.js:1642` `map?.status === state.listStatus` —— PASS。`data-status` 在徽标映射中也刻意为 `partial`（`:1824` 只加 `data-availability`，测试 `:229` 断言），筛选不会被「可用」文案污染。
- **卡片篇数**：`mapCardNodeCount`（`:1805-1809`）**先取 `node_count`，非法/缺失时回落 `requested_count`**，与本次任务口径「只取 node_count」**不一致**。该回落是既有契约（`test_frontend_map_card_count_and_availability_badge.js:191-199` 明确断言回落行为），因此按「契约自洽」判 PASS，但记录为**偏差项**：若产品要求严格只显 node_count，需同时改实现与该组测试。
- 徽标映射仅限卡片局部（`mapCardStatusBadge`），`mapStatusLabel` 全局文案表未改（测试 `:269` 断言）。

### 8. 冲突标记
```bash
grep -rn '^<<<<<<<\|^>>>>>>>' frontend/ tests/frontend/   # 0 / 0 命中
# 扩到全仓 *.py/*.js/*.html/*.css/*.md（排除 .venv/node_modules/__pycache__）: 0
```
`.py` docstring 中的 `====` 表格分隔线未被误计（正则只匹配 `^<<<<<<<` / `^>>>>>>>`）。

## 阻塞项

1. **[阻塞] `test_frontend_map_graphics.py::test_first_open_fits_a_tiny_saved_view_to_the_real_canvas` 稳定失败**（`assert 0.35 > 1`）。本轮 `resolveInitialFitPending()` 取消「最小缩放视为未初始化」启发式后，`?tiny-saved-view`（savedScale=0.35）不再自动 fit。需二选一：
   - 保留新语义（尊重所有保存视口）→ 同步更新该测试的期望值与 `?tiny-saved-view` fixture 语义（并复核 `:142-146` 附带断言）；
   - 或在新判定里补一条下限阈值（如 `savedScale < 可读阈值` 仍 fit），保住既有 UX 契约。
   两者都必须让实现与测试重新自洽。
2. **[阻塞] `literature-maps.css` 版本号未升**（仍 `?v=26`，`index.html:9`）。用户浏览器缓存旧 CSS 会导致「可用」徽章不生效。建议升 `?v=27` 并同步两处 pytest 断言。

## 非阻塞偏差

3. `mapCardNodeCount` 仍回落 `requested_count`，与任务描述「只取 node_count」口径不一致（既有测试明确要求回落，改动需连带改测试）。


---

## 第二轮复核（P0/P1 修复后）

- 角色：frontend-tester（ECC `e2e-runner` / `verification-loop`）
- 复核时间：2026-11-06（本机时间 00:43–00:58）
- 范围：仅前端静态与契约核对（`frontend/**` + `tests/frontend/**`），只读、未改任何代码/测试/spec/台账
- 日志：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261106-004348.md`
- 环境：node v26.7.0；`.venv/bin/python`（Python 3.11，pytest 7.4.0 / 9.1.1 并存）

### 最终结论

**READY** —— 上轮两个阻塞项均已闭合，全部核对项 PASS，无残留阻塞。

### 逐项结果

| # | 检查项 | 命令 | 退出码 | 结果 |
|---|--------|------|--------|------|
| 1 | 上轮失败文件 | `.venv/bin/python -m pytest tests/frontend/test_frontend_map_graphics.py -q` | 0 | **PASS（7 passed）**，连跑 3 次稳定 7/7 |
| 2 | pytest 全量 | `.venv/bin/python -m pytest tests/frontend -q`（分 5 批） | 0 | **PASS（396 passed / 0 failed）** |
| 3 | JS 语法 | `node --check frontend/literature-maps.js` | 0 | PASS |
| 3 | JS 语法 | `node --check frontend/app.js` | 0 | PASS |
| 3 | node 测试 | `for f in tests/frontend/test_*.js; do node "$f"; done` | 0 | **PASS（22/22，failed=0）** |
| 4 | 旧版本号清零 | `grep -rn 'literature-maps.css?v=26' frontend/ tests/frontend/ --exclude-dir=__pycache__` | 1 | **PASS（0 命中）** |
| 4 | 新版本号一致 | `grep -rn 'literature-maps.css?v=27' ...` | 0 | **PASS（index + fixture + 5 py / 7 断言全覆盖）** |
| 5 | 冻结版本 | `app.js?v=69` / `literature-maps.js?v=41` / `styles.css?v=68` | 0 | **PASS（未变且断言自洽）** |
| 6 | 冲突标记 | `grep -rn '^<<<<<<<\|^>>>>>>>' frontend/ tests/frontend/` | 1 | **PASS（0 命中）** |
| 6 | XSS | `git diff -U0 HEAD -- frontend/ \| grep '^+' \| grep -c 'innerHTML\|insertAdjacentHTML\|outerHTML\|document.write'` | 1 | **PASS（0 命中 / 376 新增行）** |

### 1. 阻塞项① 复核：`test_first_open_fits_a_tiny_saved_view_to_the_real_canvas`

```
$ .venv/bin/python -m pytest tests/frontend/test_frontend_map_graphics.py -q
.......                                                                  [100%]
7 passed in 4.78s                                     # EXIT=0
```
稳定性（非 flaky）：
```
整文件连跑 3 次：7 passed in 4.54s / 7 passed in 4.39s / 7 passed in 4.47s
单用例连跑 3 次：1 passed in 0.79s / 1 passed in 0.77s / 1 passed in 0.72s
```
**闭合性质核验（关键，防「改测试凑绿」）**：
- `git status --porcelain tests/frontend/test_frontend_map_graphics.py` → **空**，该测试文件本轮零改动，`assert metrics["scale"] > 1` 等断言原样保留。
- 修复走的是上轮建议的第 2 条路径（实现侧补可读下限），而非改期望值。`frontend/literature-maps.js:2553-2567` 现状：
  ```js
  const explicit = normalizeMapViewInitialized(map);
  if (explicit === true) return false;      // 用户显式保存过 → 绝不 fit
  if (state.viewSavedOnce) return false;    // 本次会话已保存过 → 绝不 fit
  if (explicit === false) return true;      // 后端明确未初始化 → fit
  if (!hasOwnViewport) return true;         // 完全没有视口 → fit
  const scaleKnown = Number.isFinite(viewportInfo.savedScale) && viewportInfo.savedScale > 0;
  if (!scaleKnown) return true;
  if (viewportInfo.savedScale <= MIN_MAP_SCALE + INITIAL_FIT_SCALE_EPSILON) return true;  // ← 本轮补回
  return viewportInfo.savedX === 0 && viewportInfo.savedY === 0 && viewportInfo.savedScale === 1;
  ```
- fixture `?tiny-saved-view` 只把 viewport 设为 `{218.19, 185.00, 0.35}`，**不带 `view_initialized`**（`tests/frontend/fixtures/literature_map_component.html:189`，mockMap 基线 `:162` 亦无该字段），因此命中「无显式证据 + 极小缩放不可读」分支 → 首开 fit，`scale > 1`，`:142-146` 的节点占比 / 43px 边距 / 零标签重叠 / `window.__viewBodies == []` 附带断言同时满足。
- 新语义未被牺牲：新增 `tests/frontend/test_frontend_map_initial_fit_and_positions_guard.js` 用 node:vm 直接驱动真实函数，5 个场景全 PASS —— 无标记 0.35→fit、超阈值→不 fit、`view_initialized:true` + 0.35→不 fit、`viewSavedOnce`→不 fit、`view_initialized:false`→fit（`:229/239/247/256/265/273`）。
- 结论：实现与测试**双向自洽**，旧 UX 契约（61096ed6「极小缩放不可读就 fit」）与本次「不覆盖用户显式保存视图」新语义共存，**闭合成立**。

### 2. pytest 全量（`.venv/bin/python`，必须用 venv）

`--collect-only -q` → **396 tests collected**（45 个 `test_*.py`）。一次性跑会超工具时限，按每批 9 文件分 5 批：

| 批次 | 文件区间 | 退出码 | 结果 |
|------|----------|--------|------|
| BATCH1 | 1–9 | 0 | 84 passed in 9.24s |
| BATCH2 | 10–18 | 0 | 85 passed in 68.54s |
| BATCH3 | 19–27 | 0 | 78 passed in 51.83s |
| BATCH4 | 28–36 | 0 | 106 passed in 1.95s |
| BATCH5 | 37–45 | 0 | 43 passed in 0.76s |

合计 84+85+78+106+43 = **396 passed，failed = 0**（上轮 395 passed / 1 failed）。

### 3. JS 语法 + node 测试

```
node --check frontend/literature-maps.js   # EXIT=0
node --check frontend/app.js               # EXIT=0   node v26.7.0
JS_PASS=22  JS_FAIL=0  FAILED_LIST=(空)     # tests/frontend/test_*.js 共 22 个
```
新增 6 个 JS 测试（未跟踪文件）全部通过：
```
ok - kb jump focus (...)
ok - map card count (node_count) and availability badge (...)
ok - map initial fit / cross-map positions guard / revision sync (...)
ok - map view keep local on return (...)
ok - map view revision on reentry (...)
ok - map view save on leave (...)
```

### 4. 版本号：`literature-maps.css` 26 → 27

```
$ grep -rn 'literature-maps.css?v=26' frontend/ tests/frontend/ --exclude-dir=__pycache__
（无输出，EXIT=1 → 0 命中）

$ grep -rn 'literature-maps.css?v=27' frontend/ tests/frontend/
frontend/index.html:9                                                  ✔ 实际引用
tests/frontend/fixtures/literature_map_component.html:8                ✔ fixture
tests/frontend/test_frontend_literature_map_contract.py:29             ✔
tests/frontend/test_frontend_literature_map_expansion.py:29            ✔
tests/frontend/test_frontend_map_analysis_contract.py:35               ✔
tests/frontend/test_frontend_map_groups_exports.py:19,43               ✔（INDEX + fixture 各一）
tests/frontend/test_frontend_map_mobile_contract.py:95,98              ✔（INDEX + FIXTURE 各一）
```
- `frontend/index.html:9` → `<link rel="stylesheet" href="/assets/literature-maps.css?v=27">`，与上轮 `+3` 行的 CSS 改动配套，缓存问题解除。
- 说明：`grep` 不加 `--exclude-dir=__pycache__` 时会在 `tests/frontend/__pycache__/*.pyc` 二进制里匹配到旧串，属历史字节码残留，非源码命中，不影响结论。
- **结论：阻塞项②闭合。**

### 5. 版本号冻结核对（三项均未变）

| 资源 | `frontend/index.html` | 断言位置 | 结果 |
|------|----------------------|----------|------|
| `app.js?v=69` | line 807 | `test_frontend_management_contract.py:80` | PASS（未变） |
| `literature-maps.js?v=41` | line 805 | `test_frontend_literature_map_contract.py:28`、`test_frontend_literature_map_expansion.py:28`、`test_frontend_map_analysis_contract.py:34`、`test_frontend_map_groups_exports.py:18,44`、`test_frontend_map_mobile_contract.py:94,97`、`fixtures/literature_map_component.html:1120` | PASS（未变） |
| `styles.css?v=68` | line 8 | `test_frontend_management_contract.py:79` | PASS（未变） |

历史兼容标记行（`index.html` 第 7 / 799 / 803 / 806 / 808-810 行注释）为旧版本号存档，无需改动；它们不影响 `in INDEX` 形式的断言。

### 6. 冲突标记 + XSS

```
$ grep -rn '^<<<<<<<\|^>>>>>>>' frontend/ tests/frontend/    # 0 命中，EXIT=1

$ git diff -U0 HEAD -- frontend/ | grep '^+' > /tmp/added.txt
$ wc -l < /tmp/added.txt            → 376   （本轮前端新增行）
$ grep -c 'innerHTML|insertAdjacentHTML|outerHTML|document.write' /tmp/added.txt → 0   （EXIT=1）
```
新增行文本处理全部安全（4 处 `textContent` + 2 处 `setAttribute`）：
```
+  if (kbStatus) kbStatus.textContent = `已定位到知识库中的该文档（${String(identifier)}）。`;
+  if (kbStatus) kbStatus.textContent = KB_JUMP_NEED_ID_TEXT;
+  if (kbStatus) kbStatus.textContent = KB_JUMP_NOT_FOUND_TEXT;
+  badge.textContent = mapStatusLabel('ready');
+  badge.setAttribute('title', PARTIAL_MAP_CARD_NOTICE);
+  badge.setAttribute('aria-label', `${mapStatusLabel('ready')}：${PARTIAL_MAP_CARD_NOTICE}`);
```
模板变量经 `String(identifier)` 归一后写入 `textContent`，不进入 HTML 解析路径。

### 阻塞项闭合状态

| 上轮阻塞 | 状态 | 判定依据 |
|----------|------|----------|
| ① `test_first_open_fits_a_tiny_saved_view_to_the_real_canvas` 稳定失败（scale 0.35） | **CLOSED** | 文件 7 passed；单文件/单用例各连跑 3 次全绿；测试文件零改动；实现 `:2565` 补回极小缩放 fit 下限；新增 JS 契约测试覆盖 5 场景全 PASS |
| ② `literature-maps.css` 改动但 `index.html` 仍 `?v=26` | **CLOSED** | `?v=26` 源码 0 命中；`?v=27` 在 index / fixture / 5 个 py 的 7 条断言中全覆盖 |

### 非阻塞提示（沿用上轮，未复核处理情况）

- `mapCardNodeCount` 仍保留「`node_count` 非法/缺失时回落 `requested_count`」的既有契约，与「只取 node_count」口径的字面差异仍在；既有 JS 测试 `test_frontend_map_card_count_and_availability_badge.js:191-199` 明确断言回落行为，改动需连带改测试。**不影响本次发布判定。**

### VERIFICATION REPORT

```
VERIFICATION REPORT（前端第二轮复核）
====================================
Syntax:    PASS   (node --check app.js / literature-maps.js 均 EXIT=0)
Contract:  PASS   (pytest tests/frontend 396 passed / 0 failed；node 测试 22/22)
Version:   PASS   (literature-maps.css 26→27 全链路一致；app.js=69 / literature-maps.js=41 / styles.css=68 冻结未变)
XSS:       PASS   (376 新增行，innerHTML/insertAdjacentHTML/outerHTML/document.write 0 命中)
Conflicts: PASS   (0 冲突标记)
Diff:      12 files changed (frontend 5 + tests/frontend 7)

Overall:   READY
```
