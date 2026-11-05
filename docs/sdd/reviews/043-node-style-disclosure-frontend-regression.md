# Spec043 前端回归报告 — 文献地图「节点样式」浮层改为点击才展开

- **回归角色**：frontend-tester（ECC `e2e-runner` / `verification-loop`）
- **工作目录**：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`
- **分支**：`codex/spec030-report-quality`
- **执行时间**：2026-11-05 04:49 – 05:12
- **范围声明**：只做前端静态/契约核对与前端测试；**未运行后端 pytest**，未触碰后端代码，未提交。
- **改动规模**：9 files changed, 65 insertions(+), 49 deletions(-) + 1 新增测试文件

## 结论

**PASS —— 可交付。** 无阻塞项。

节点样式浮层已从「视口决定开合」改为「仅用户点击决定开合」：进入地图默认 `open=false`，
点击 summary「节点样式」展开、再点折叠，桌面↔移动视口切换不再改写用户选择；
节点样式的应用/取消预览/导出/移动端既有行为均无回归。

## 验收点逐条核对

| # | 验收点 | 结论 | 证据 |
|---|---|---|---|
| 1 | 进入地图时 `.literature-map-node-style-disclosure` 默认 `open=false` | **PASS** | 新增测试用例 1（mobile=false / true 两态）；`buildNodeStyleDisclosure()` 1311-1313 行不再设置 `open` |
| 2 | 点击 summary 后展开 | **PASS** | 新增测试用例 2（展开 + 再点折叠）；`test_frontend_map_palette.py` 两处真实 playwright 点击 summary 后 `style.wait_for(state="visible")` 通过 |
| 3 | 视口切换不自动展开 | **PASS** | 新增测试用例 3a/3b 走真实 `window resize` → `handleMobileViewportResize()` 路径；该函数内强制改写 `open` 的语句已删除（1401-1402） |
| 4 | 节点样式应用/取消预览/导出/移动端不回归 | **PASS** | `test_frontend_map_palette.py` 16 passed（含 apply/cancel/PNG 导出）、`test_frontend_map_mobile_contract.py` 12 passed、`test_frontend_map_groups_exports.py` 3 passed；`saveNodeStyle`(5263)/`cancelNodeStyleDraft`(5230)/`updateNodeStyleDraft`(5206) 未被改动 |

## 逐项检查结果（含命令 / 退出码 / 数量）

### 1. Syntax — PASS
```
$ node --check frontend/literature-maps.js
（无输出）
EXIT=0
```

### 2. 新增契约测试 — PASS
```
$ node tests/frontend/test_frontend_node_style_disclosure.js
ok - frontend node style disclosure defaults collapsed and survives viewport changes
EXIT=0
```

该测试不是纯文本断言：它用正则从 `frontend/literature-maps.js` **原样摘出**
`createElement()` / `buildNodeStyleDisclosure()` / `handleMobileViewportResize()` 三段真实源码，
连同源码中真实的 `window.addEventListener('resize', handleMobileViewportResize);` 绑定，
放进 `node:vm` 沙箱 + 最小 DOM 桩上执行，因此断言的是真实实现行为。

### 3. 测试布局检查 — PASS
```
$ /Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
test layout: ok
EXIT=0
```
说明：worktree 内无 `.venv`，按任务授权只读借用主工作区 `/Users/wjh/ResearchAgent/.venv/bin/python`
（仅用于执行脚本与 pytest，未写入主工作区）。

### 4. 资源版本号一致性 — PASS
```
$ grep -rn 'literature-maps.js?v=' frontend/index.html tests/frontend/ --include='*.py' --include='*.html'
frontend/index.html:805                                              .../literature-maps.js?v=38
tests/frontend/test_frontend_map_analysis_contract.py:34            .../literature-maps.js?v=38
tests/frontend/test_frontend_literature_map_expansion.py:28         .../literature-maps.js?v=38
tests/frontend/test_frontend_literature_map_contract.py:28          .../literature-maps.js?v=38
tests/frontend/test_frontend_map_groups_exports.py:18               .../literature-maps.js?v=38
tests/frontend/test_frontend_map_groups_exports.py:44               .../literature-maps.js?v=38
tests/frontend/test_frontend_map_mobile_contract.py:94              .../literature-maps.js?v=38
tests/frontend/test_frontend_map_mobile_contract.py:97              .../literature-maps.js?v=38
tests/frontend/fixtures/literature_map_component.html:1120          .../literature-maps.js?v=38
```
- 9 处全部为 `v=38`，**无 v=37 残留**。
- 已改 `frontend/literature-maps.js` → `index.html` 版本号已升 `v=37 → v=38`，缓存刷新要求满足。
- 8 处测试/fixture 版本断言已同步（与任务描述一致）。

### 5. XSS — PASS
```
$ git diff -U0 -- frontend/ | grep '^+' | grep -i innerHTML
（无输出，exit 1 = 未命中）
EXIT=1（grep 未命中，符合预期）

$ grep -c 'innerHTML' frontend/literature-maps.js
0
```
新增代码路径纯用 `createElement(tag, className, text)` 构建，动态文本走 text 参数（等价 `textContent`），无 `innerHTML` 拼接。

### 6. DOM / CSS 契约 — PASS
```
$ grep -n 'literature-map-node-style-disclosure' frontend/literature-maps.css
286: #literature-maps-view .literature-map-node-style-disclosure { display: flex; ... }
287: #literature-maps-view .literature-map-node-style-disclosure > summary { ... cursor: pointer; ... }
288: #literature-maps-view .literature-map-node-style-disclosure > summary::-webkit-details-marker { display: none; }
289: #literature-maps-view .literature-map-node-style-disclosure[open] > summary { border-color: #d8d2ff; background: #f7f5ff; }
```
- JS 使用的 class 在 CSS 中存在，且 `[open] > summary` 有展开态样式 → 折叠/展开都有视觉反馈。
- 其余 class 覆盖：`literature-map-node-style` 11、`-mode` 2、`-opacity-label` 1、`-opacity-value` 1。
- 备注（非本 spec 缺陷）：`literature-map-node-style-apply` / `-cancel` 在 CSS 中无独立规则，
  依赖 `send-button` / `secondary-button` 基类；该状态改动前既有，本次 diff 未触及。
- 引用完整性：`refs.nodeStyle` / `refs.nodeStyleDisclosure` 经第 1262 行 `Object.assign(refs, {...})` 挂载，
  解构出的两个变量均已使用；`refs.nodeStyleDisclosure` 全文件已无任何引用（删除干净）；
  `isMobileViewport()` 另有 15 处调用，非死代码。

### 7. 受影响前端测试（分批执行）— PASS，72 passed / 0 failed
| 命令 | 结果 | 退出码 |
|---|---|---|
| `pytest tests/frontend/test_frontend_map_palette.py -q` | 16 passed (11.71s) | 0 |
| `pytest tests/frontend/test_frontend_map_mobile_contract.py -q` | 12 passed (20.46s) | 0 |
| `pytest tests/frontend/test_frontend_map_groups_exports.py -q` | 3 passed (0.94s) | 0 |
| `pytest tests/frontend/test_frontend_literature_map_contract.py -q` | 5 passed (5.86s) | 0 |
| `pytest tests/frontend/test_frontend_literature_map_expansion.py -q` | 32 passed (31.24s) | 0 |
| `pytest tests/frontend/test_frontend_map_analysis_contract.py -q` | 4 passed (3.15s) | 0 |

- 全部使用 `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest`（worktree 无 venv）。
- 每个文件单独一条命令执行，避免长命令超时。
- **playwright 环境可用**：`test_frontend_map_palette.py` 的交互用例（含本次改动涉及的两个
  `test_style_preview_does_not_write_until_apply_and_png_uses_saved_outline_style`、
  `test_exports_are_blocked_while_color_or_style_preview_is_unapplied`）真实执行并通过，非 skip。

### 8. 变异验证（测试有效性）— PASS
变异内容：在 `buildNodeStyleDisclosure()` 中插回旧实现 `nodeStyleDisclosure.open = !isMobileViewport();`

```
$ node --check frontend/literature-maps.js
EXIT=0                     # 语法仍合法，排除“语法报错导致的假失败”

$ node tests/frontend/test_frontend_node_style_disclosure.js
AssertionError [ERR_ASSERTION]: 打开地图后节点样式浮层必须默认折叠 open=false（mobile=false，用户要求点击后才弹出）
true !== false
EXIT=1                     # ✅ 新增测试确实捕获回归
```

复原后：
```
$ node tests/frontend/test_frontend_node_style_disclosure.js
ok - frontend node style disclosure defaults collapsed and survives viewport changes
EXIT=0

$ node --check frontend/literature-maps.js
EXIT=0

$ grep -n 'nodeStyleDisclosure.open' frontend/literature-maps.js
（无匹配，EXIT=1）          # ✅ 强制改写语句已彻底移除

$ grep -n 'open = !isMobileViewport' frontend/literature-maps.js
（无匹配，EXIT=1）          # ✅ 变异残留为零

$ pytest tests/frontend/test_frontend_map_palette.py -q
16 passed (11.67s)  EXIT=0  # ✅ 复原后复跑通过

$ git diff --stat -- frontend/literature-maps.js
1 file changed, 44 insertions(+), 38 deletions(-)   # ✅ 与变异前完全一致，复原精确
```

结论：新增测试具备真实防回归能力（非空转），且变异已被精确复原，工作树无遗留副作用。

## 阻塞项

**无。** playwright 可用，无 skip、无伪造通过；未使用任何 stubbed 结果。

## 遗留观察（不阻塞、不属本 spec）

1. `literature-map-node-style-apply` / `-cancel` 无独立 CSS 规则，仅靠 `send-button`/`secondary-button` 基类。
   改动前既有，本次 diff 未触及；若后续需要浮层内按钮与基类不同，可另开单。
2. `frontend/literature-maps.css` 本次未改动，故 `literature-maps.css?v=25` 未升版——正确。

## COMPLIANCE

- 未改任何业务代码（仅变异验证期间临时改 1 行并已精确复原，`git diff --stat` 与变异前一致）。
- 未执行 git commit / push / merge。
- 未触碰主工作区 `/Users/wjh/ResearchAgent` 的任何文件（仅只读借用其 `.venv` 解释器）。
- 未运行后端 pytest。
- 进展日志：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-044920.md`

---

# 第二轮回归（补修：折叠态真实可见性）

- **执行时间**：2026-11-05 04:58 – 05:52
- **触发原因**：主会话真实浏览器复测发现第一轮遗留缺陷——`open=false` 属性正确，但 `frontend/literature-maps.css:285/286`
  的 `.literature-map-node-style { display: flex }` 与 `details { display: flex }` 均为**作者样式**，
  压过了 UA 对 `details:not([open])` 非 summary 子元素的隐藏，浮层以一条竖边继续渲染在画布上方。
  第一轮只断言了 `open` 属性，因此在缺陷下误报通过。
- **本轮改动**：`frontend/literature-maps.css` 新增折叠态隐藏规则；`frontend/index.html:9` CSS `?v=25 → v=26`；
  8 处测试/fixture 版本断言同步；新增 `tests/frontend/test_frontend_node_style_visibility.py`（4 个真实浏览器可见性用例）。
  第一轮 JS 改动（`literature-maps.js?v=38`）保持不变。

## 第二轮结论

**READY —— 可交付。无阻塞项。**

折叠态浮层内容现在真的不可见（computed `display:none` / 零面积），点击 summary 后恢复原有 flex 布局，
视口切换不改写用户开合选择；节点样式保存/预览/导出/移动端行为均无回归。
新增可见性测试经变异验证具备真实防回归能力（移除 CSS 规则 → 4/4 失败；复原 → 4/4 通过）。

## 改动核对（本轮 diff）

```
$ git --no-pager diff -- frontend/literature-maps.css frontend/index.html
frontend/index.html:9      - /assets/literature-maps.css?v=25  →  + /assets/literature-maps.css?v=26
frontend/literature-maps.css
  +/* 折叠态必须真的看不见：… 只在容器作用域内生效。 */
  +#literature-maps-view .literature-map-node-style-disclosure:not([open]) > .literature-map-node-style { display: none; }
```

```
$ git --no-pager diff --stat
 frontend/index.html                                |  4 +-
 frontend/literature-maps.css                       |  4 ++
 frontend/literature-maps.js                        | 82 ++++++++-----------   (第一轮改动，未再变)
 tests/frontend/fixtures/literature_map_component.html            |  4 +-
 tests/frontend/test_frontend_literature_map_contract.py          |  4 +-
 tests/frontend/test_frontend_literature_map_expansion.py         |  4 +-
 tests/frontend/test_frontend_map_analysis_contract.py            |  4 +-
 tests/frontend/test_frontend_map_groups_exports.py               | 10 +-
 tests/frontend/test_frontend_map_mobile_contract.py              | 10 +-
 tests/frontend/test_frontend_map_palette.py                      | 10 +++
 10 files changed, 78 insertions(+), 58 deletions(-)
（另有 2 个新增测试文件 untracked：test_frontend_node_style_disclosure.js / test_frontend_node_style_visibility.py）
```

## 第二轮逐项检查（命令 / 退出码 / 数量）

### R1. 新增可见性 pytest（真实浏览器）— PASS，4 passed / 0 failed
```
$ /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_node_style_visibility.py -q
....                                                                     [100%]
4 passed in 2.47s
EXIT=0
```
- 说明：worktree 内仍无 `.venv`，按授权**只读**借用主工作区 `/Users/wjh/ResearchAgent/.venv/bin/python`
  （未写入主工作区任何文件）。
- `....` 全为 passed（skip 会显示 `s`），即 playwright 真实执行，**未走 `pytest.skip("真实浏览器阻塞…")` 兜底分支**。
- 4 个用例覆盖：`[1440]`、`[390]` 两视口的折叠不可见 + 展开恢复 flex；视口切换不改写开合；隐藏规则作用域静态护栏。

### R2. 第一轮 JS 契约不回归 — PASS
```
$ node tests/frontend/test_frontend_node_style_disclosure.js
ok - frontend node style disclosure defaults collapsed and survives viewport changes
EXIT=0
```

### R3. Syntax — PASS
```
$ node --check frontend/literature-maps.js
（无输出）
EXIT=0
```

### R4. 测试布局检查 — PASS
```
$ /Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
test layout: ok
EXIT=0
```

### R5. 资源版本号一致性 — PASS
```
$ grep -rn 'literature-maps.css?v=' frontend/index.html tests/frontend/ --include='*.py' --include='*.html'
frontend/index.html:9                                              .../literature-maps.css?v=26
tests/frontend/test_frontend_map_analysis_contract.py:35           .../literature-maps.css?v=26
tests/frontend/test_frontend_literature_map_expansion.py:29        .../literature-maps.css?v=26
tests/frontend/test_frontend_literature_map_contract.py:29         .../literature-maps.css?v=26
tests/frontend/test_frontend_map_groups_exports.py:19              .../literature-maps.css?v=26
tests/frontend/test_frontend_map_groups_exports.py:43              .../literature-maps.css?v=26
tests/frontend/test_frontend_map_mobile_contract.py:95             .../literature-maps.css?v=26
tests/frontend/test_frontend_map_mobile_contract.py:98             .../literature-maps.css?v=26
tests/frontend/fixtures/literature_map_component.html:8            .../literature-maps.css?v=26

$ grep -rn 'literature-maps\.css?v=25' frontend/index.html tests/frontend/ --include='*.py' --include='*.html'
（无命中，EXIT=1）                          # ✅ 源码/测试/fixture 均无 v=25 残留
```
- CSS 共 9 处全部为 `v=26`：源码 1 处 + 测试断言 7 处 + fixture 1 处（=「8 处断言/fixture 同步」）。
- JS 版本未变，`literature-maps.js?v=38` 共 9 处（`frontend/index.html:805` + 7 处测试断言 + fixture:1120），**无 v=37 残留**。

### R6. XSS — PASS
```
$ git diff -U0 -- frontend/ | grep '^+' | grep -i innerHTML
（无输出）
EXIT=1（grep 未命中，符合预期）
```
- 本轮 frontend diff **未新增任何 `innerHTML`**；`frontend/literature-maps.js` 内 `innerHTML` 计数仍为 0。
- `grep -rn innerHTML frontend/` 的命中均为本轮之前既有代码（`app.js` 的 `renderMarkdown` + DOMPurify 净化链路、
  `vendor/purify.min.js`、`contract-tests` 的属性 stub），本轮 diff 未触及，不属本 spec 范围。
- 新增测试文件内无 `innerHTML`。

### R7. DOM / CSS 契约 — PASS
新增规则的选择器两端均已在渲染侧核实存在：
```
$ grep -rn 'literature-map-node-style-disclosure' frontend/ tests/frontend/fixtures/literature_map_component.html
frontend/literature-maps.js:1311   const nodeStyleDisclosure = createElement('details', 'literature-map-node-style-disclosure');
frontend/literature-maps.css:286   …-disclosure { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; max-width: 100%; }
frontend/literature-maps.css:293   …-disclosure:not([open]) > .literature-map-node-style { display: none; }

$ grep -rnE 'literature-map-node-style(["'"'"' >{,.]|$)' frontend/literature-maps.js
frontend/literature-maps.js:1277   const nodeStyle = createElement('fieldset', 'literature-map-node-style');
frontend/literature-maps.js:1278   nodeStyle.id = 'literature-map-node-style';
```
父子关系（`literature-maps.js:1311-1312`）：
```
nodeStyleDisclosure.append(createElement('summary', '', '节点样式'), nodeStyle);
```
→ `details.literature-map-node-style-disclosure > fieldset.literature-map-node-style#literature-map-node-style`，
新增规则 `:not([open]) > .literature-map-node-style` 精确命中该 fieldset；`[open]` 时选择器不匹配、
`display:flex`（css:285）自然生效，展开布局不变。
- 作用域：选择器以 `#literature-maps-view` 前缀限定，不污染全局；**未使用 `!important`**（静态护栏用例亦断言此点）。
- 反向核对：CSS 中 `display:flex` 的两个作者样式源（css:285 `.literature-map-node-style`、css:286 `…-disclosure`）与
  注释所述「压过 UA 隐藏」的原因一致，修复方向正确。

### R8. 受影响前端测试（分批执行）— PASS，72 passed / 0 failed
| 批次 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 1 | `pytest test_frontend_map_palette.py test_frontend_map_analysis_contract.py test_frontend_literature_map_contract.py -q` | 25 passed (20.09s) | 0 |
| 2 | `pytest test_frontend_map_groups_exports.py test_frontend_literature_map_expansion.py -q` | 35 passed (31.59s) | 0 |
| 3 | `pytest test_frontend_map_mobile_contract.py -q` | 12 passed (20.57s) | 0 |

- 全部分批执行（3 批）以避免超时；均使用 `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest`。
- 覆盖：palette（含 apply/cancel/PNG 导出的真实点击）、map_analysis_contract、literature_map_contract、
  groups_exports（含 fixture 版本断言）、expansion、mobile_contract（12 项移动端行为）。
- 合计 25+35+12 = **72 passed，0 failed，0 skip**。

### R9. 变异验证（测试有效性）— PASS
变异内容：**移除** `frontend/literature-maps.css:293` 的折叠态隐藏规则。

```
# 变异前备份并校验
$ cp frontend/literature-maps.css /tmp/spec043_css_backup.css
$ sha1sum frontend/literature-maps.css /tmp/spec043_css_backup.css
36a241bea5a565b03ab173cca5538788d0916651  frontend/literature-maps.css
36a241bea5a565b03ab173cca5538788d0916651  /tmp/spec043_css_backup.css

# 变异（移除规则，断言 count==1 后删除）
mutated: rule removed
$ grep -c 'literature-map-node-style-disclosure:not(\[open\])' frontend/literature-maps.css
0
$ sha1sum frontend/literature-maps.css
92241c63d7e390953a2cf51b9b8ce76389146c5e

# 变异后跑可见性测试 → 应红
$ pytest tests/frontend/test_frontend_node_style_visibility.py -q
FAILED …::test_collapsed_node_style_fieldset_is_not_rendered_until_summary_is_clicked[1440]
FAILED …::test_collapsed_node_style_fieldset_is_not_rendered_until_summary_is_clicked[390]
FAILED …::test_node_style_fieldset_visibility_survives_viewport_switch
FAILED …::test_hide_rule_is_scoped_to_the_disclosure_container
4 failed in 7.41s
EXIT=1                          # ✅ 4/4 变红，测试对该缺陷真实敏感
（浏览器两态用例报 Playwright TimeoutError：等待展开后宽度>0 超时；静态护栏报「必须存在折叠态隐藏规则 assert []」）

# 复原并校验回到变异前
$ cp /tmp/spec043_css_backup.css frontend/literature-maps.css
$ sha1sum frontend/literature-maps.css
36a241bea5a565b03ab173cca5538788d0916651   # ✅ 与变异前逐字节一致
$ grep -n 'literature-map-node-style-disclosure:not(\[open\])' frontend/literature-maps.css
293:#literature-maps-view .literature-map-node-style-disclosure:not([open]) > .literature-map-node-style { display: none; }
$ git --no-pager diff --stat -- frontend/literature-maps.css
 frontend/literature-maps.css | 4 ++++      # ✅ 回到变异前 4 行新增

# 复原后复跑 → 应绿
$ pytest tests/frontend/test_frontend_node_style_visibility.py -q
4 passed in 2.37s   EXIT=0                  # ✅
$ node tests/frontend/test_frontend_node_style_disclosure.js
ok - frontend node style disclosure defaults collapsed and survives viewport changes   EXIT=0
$ git status --short -- frontend tests       # ✅ 与变异前完全一致，无残留
```

结论：新增测试**不是空转断言**——它对「折叠态未真正隐藏」这一具体缺陷变异即红、复原即绿；
变异已被 sha1 级精确复原，工作树无遗留副作用。

## 主会话真实浏览器复测（补充证据，非本角色执行）

| 场景 | 观测 |
|---|---|
| 1280 视口 + 折叠态 | fieldset computed `display:none`，rect `0×0` |
| 点击 summary 后展开 | `display:flex`，rect `416×47` |
| 700 ↔ 1280 视口切换 | 仍保持折叠（未自动展开） |

与本轮自动化用例（1440 / 390 两视口、视口切换用例）结论一致，互为交叉验证。

## 与第一轮的关系（含第一轮报告需修正的一处）

1. 第一轮「检查 4 资源版本号」中「`literature-maps.css?v=25` 未升版——正确」的判断**已被本轮补修取代**：
   本轮改了 CSS，故已升 `v=25 → v=26`，且 8 处断言/fixture 全部同步。第一轮遗留观察第 2 条随之作废。
2. 第一轮「用例 1 断言 `open=false`」**不足以证明缺陷已修**——本轮正是该断言的盲区（`open` 正确但视觉未隐藏）。
   新增 `test_frontend_node_style_visibility.py` 以 computed style / getBoundingClientRect 为准，补齐盲区。
   第一轮 `test_frontend_node_style_disclosure.js` 仍保留并继续通过（职责不同：断言开合状态机，不断言可见性）。
3. 第一轮遗留观察第 1 条（`-apply` / `-cancel` 无独立 CSS 规则）仍在，本轮未触及，继续不阻塞。

## 阻塞项

**无。**
- playwright 可用，4 个可见性用例真实执行，**无 skip、无伪造通过**。
- 未使用任何 stubbed 结果；变异验证的临时改动已 sha1 级复原。

## COMPLIANCE

- 未改任何业务代码（变异验证期间临时删除 1 行 CSS，已用备份精确复原，sha1 `36a241be…` 前后一致，`git diff --stat` 回到 `4 ++++`）。
- 未执行 git commit / push / merge。
- 未触碰主工作区 `/Users/wjh/ResearchAgent` 的任何文件（仅**只读**借用其 `.venv` 解释器；临时文件写在 `/tmp`）。
- 未运行后端 pytest。
- 日志（第二轮）：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-045928.md`
- 日志（第一轮）：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-044920.md`

---

# 第三轮回归（补修：应用外观保存成功后自动收起）

- **执行时间**：2026-11-05 16:04 – 16:40
- **触发原因**：主会话真实浏览器复测发现第三处遗留缺陷——用户点开 summary「节点样式」调好填充/透明度、点「应用外观」，
  后端已保存成功、提示「节点外观已保存。」，但 `details` 仍 `open=true`，面板继续铺在画布上方，
  用户必须手动再点一次 summary 才能继续看图。前两轮只覆盖「开合状态机」与「折叠态可见性」，
  **没有覆盖「保存成功后收起」这条交互终点**。
- **本轮改动**：
  1. `frontend/literature-maps.js` `updateSavedNodeStyle()` 成功末尾新增 1 行 `if (refs.nodeStyleDisclosure) refs.nodeStyleDisclosure.open = false;`（+2 行注释，共 +3 行）；
  2. `frontend/index.html:805` JS `?v=38 → v=39`；
  3. 9 处版本断言/fixture 同步（7 处测试断言 + fixture 1 处 + 源码 1 处）；
  4. 新增 `tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js`（`node:vm`，7 场景，4 条保存路径）；
  5. `tests/frontend/test_frontend_node_style_visibility.py` 新增真实浏览器用例 `test_applying_node_style_collapses_the_panel_after_save_succeeds`（4 → 5 用例）；
  6. **CSS 未改动**，保持 `literature-maps.css?v=26`。

## 第三轮结论

**READY —— 可交付。无阻塞项。**

「应用外观」保存成功（含「已重新读取核实」成功）后浮层自动收起：`details.open=false`、内容 computed `display:none` / 零面积；
summary「节点样式」仍可见可点，再次展开能看到已保存的取值。失败 / 409 冲突 / 结果未确认 / 草稿仍保留时**保持展开**以便重试；
「取消预览」行为不变；视口切换不改写开合。前两轮的开合契约与折叠态可见性契约均不回归。

## 改动核对（本轮 diff，`git diff -- frontend/`）

```
frontend/index.html
  @@ -802,7 +802,7 @@
  -    <script src="/assets/literature-maps.js?v=38"></script>
  +    <script src="/assets/literature-maps.js?v=39"></script>

frontend/literature-maps.js
  @@ -5246,6 +5246,9 @@
       state.nodeStyleDraft = { ...nextStyle };
       renderNodeStyleControls();
       renderGraph();
  +    // 保存已确认成功（主成功或重新读取核实成功）后收起面板，让出画布；
  +    // 只有走到这里的成功路径才会收起：失败 / 409 / 结果未确认仍保持展开以便重试。
  +    if (refs.nodeStyleDisclosure) refs.nodeStyleDisclosure.open = false;
     }
```

```
$ git --no-pager diff --stat
 docs/sdd/reviews/043-node-style-disclosure-frontend-review.md   | 176 ++++++  (非本角色产物，见 COMPLIANCE)
 frontend/index.html                                |   2 +-
 frontend/literature-maps.js                        |   3 +
 tests/frontend/fixtures/literature_map_component.html            |   2 +-
 tests/frontend/test_frontend_literature_map_contract.py          |   2 +-
 tests/frontend/test_frontend_literature_map_expansion.py         |   2 +-
 tests/frontend/test_frontend_map_analysis_contract.py            |   2 +-
 tests/frontend/test_frontend_map_groups_exports.py               |   6 +-
 tests/frontend/test_frontend_map_mobile_contract.py              |   6 +-
 tests/frontend/test_frontend_node_style_visibility.py            |  61 +++++
 10 files changed, 251 insertions(+), 11 deletions(-)
（另有 untracked 新增测试：tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js）
$ git --no-pager diff --stat -- frontend/literature-maps.css
（无输出 → CSS 本轮零改动，v=26 保持不变正确）
```

### 收起语句的位置正确性（为什么只有成功路径会收起）

`updateSavedNodeStyle()` 在文件中只有 **2 个调用点**，均位于成功分支：

```
$ grep -n 'updateSavedNodeStyle' frontend/literature-maps.js
5236:  function updateSavedNodeStyle(mapId, nodeStyle, revision) {
5280:      updateSavedNodeStyle(mapId, payload.map?.view_settings?.node_style || draft, payload.map?.revision);   // 主 PATCH 成功
5297:            updateSavedNodeStyle(mapId, saved, payload.map?.revision);                                      // 重读核实一致
```

非成功分支全部 `return` 或走 `else`，**不经过** `updateSavedNodeStyle`：

| 分支 | 代码位置 | 是否收起 |
|---|---|---|
| 主 PATCH 成功 | 5280 `updateSavedNodeStyle(...)` → 5251 | **收起** |
| PATCH 断连 → 重读值与草稿一致 | 5297 `updateSavedNodeStyle(...)` → 5251 | **收起** |
| 409 冲突 | 5280-5287 `if (error.status === 409) { rereadNodeStyleAfterConflict(...); return; }` | 保持展开 |
| 结果未确认（重读值与草稿不一致） | 5299-5304 `else { ...setStatus('…结果未能确认…'); }` | 保持展开 |
| 明确失败 / 非可重试 | 5308 `setStatus('外观保存失败：…')` | 保持展开 |
| 早退（地图已切换 / 非当前地图） | 5237 首行 `return` | 不碰面板 |

`refs.nodeStyleDisclosure` 生命周期完整，非死代码：1176 解构 → 1177 `layerTools.append()` → 1262 `Object.assign(refs, {...})` 挂载 → 5251 消费。

## 第三轮逐项检查（命令 / 退出码 / 数量）

### T1. Syntax — PASS
```
$ node --check frontend/literature-maps.js
（无输出）
EXIT=0
$ node --check frontend/app.js
（无输出）
EXIT=0
```

### T2. 新增收起契约测试（node:vm 真实执行）— PASS
```
$ node tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js
ok - node style panel collapses only after a confirmed successful apply
EXIT=0
```
- **不是文本断言**：测试用正则从 `frontend/literature-maps.js` **原样摘出** `LiteratureMapError`、
  `updateSavedNodeStyle()`、`rereadNodeStyleAfterConflict()`、`saveNodeStyle()` 四段真实源码，
  放进 `node:vm` 沙箱（最小 `state`/`refs`/`document` 桩 + 可编程 `request()`），
  通过「用户点应用外观 → `await saveNodeStyle()`」**真实执行**四条保存路径。
- 覆盖 7 个场景：① 主成功 → `open=false` 且 `getAttribute('open')===null`；② 断连后重读核实一致 → 收起；
  ③ 409 冲突 → 草稿原样保留且**保持展开**；④ 结果未确认 → 保持展开；⑤ 明确失败（503）→ 保持展开；
  ⑥ 取消预览不收起；⑦ 非当前地图回调早退不误收起别人的面板。
- 额外断言「收起不是禁用」：summary 仍在、`disabled !== true`，用户可再次展开。

### T3. 前两轮开合契约不回归 — PASS
```
$ node tests/frontend/test_frontend_node_style_disclosure.js
ok - frontend node style disclosure defaults collapsed and survives viewport changes
EXIT=0
```

### T4. 可见性 + 新增真实浏览器用例 — PASS，5 passed / 0 failed / 0 skip
```
$ /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_node_style_visibility.py -q
.....                                                                    [100%]
5 passed in 4.66s
EXIT=0

$ … -q -rs | grep -i skip
（无输出，grep EXIT=1 → 无 skip，playwright 真实执行，未走 skip 兜底分支）
```
说明：worktree 内无 `.venv`（`ls -d .venv` 无命中），按授权**只读**借用主工作区
`/Users/wjh/ResearchAgent/.venv/bin/python`（Python 3.11.16 / pytest 9.1.1），未写入主工作区任何文件。

新增用例 `test_applying_node_style_collapses_the_panel_after_save_succeeds`（1440×900 真实浏览器）链路：
点开 summary → 等 fieldset 宽度 > 0 → 改 `fill_opacity=0.65` → 断言预览阶段 `__viewBodies.length === 0`（未写服务端）
→ 点「应用外观」→ 等 `__viewBodies.length === 1` 且状态含「节点外观已保存」→ 校验 PATCH body 为
`{"fill_mode":"filled","fill_opacity":0.65}` → 断言 `get_attribute("open") is None` → 断言 computed 隐藏
（`_VISIBILITY_JS`：display/visibility/矩形面积）+ `field.is_hidden()` → 断言 summary `is_visible()` →
再点 summary → 断言透明度 `0.65`、填充模式 `filled` 均已回填。

### T5. 受影响的精确前端测试（分批，避免超时）— PASS，86 passed / 0 failed / 0 skip
| 批次 | 命令 | 结果 | 耗时 | 退出码 |
|---|---|---|---|---|
| 1 | `pytest test_frontend_map_palette.py test_frontend_map_analysis_contract.py test_frontend_literature_map_contract.py -q` | 25 passed | 28.21s | 0 |
| 2 | `pytest test_frontend_map_groups_exports.py test_frontend_literature_map_expansion.py -q` | 35 passed | 40.95s | 0 |
| 3 | `pytest test_frontend_map_mobile_contract.py -q` | 12 passed | 23.74s | 0 |
| 4 | `pytest test_frontend_map_layout_viewport.py -q` | 14 passed | 14.60s | 0 |

- 均为 `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest`，每个批次一条命令单独执行。
- 覆盖本轮 9 处版本断言的全部持有文件（map_analysis_contract / literature_map_expansion / literature_map_contract /
  map_groups_exports / map_mobile_contract），以及 palette（含 apply/cancel/PNG 导出的真实点击）、
  layout_viewport（视口切换不改写开合）。合计 **86 passed，0 failed，0 skip**。

### T6. 资源版本号一致性 — PASS
```
$ grep -n 'literature-maps.js?v=' frontend/index.html
805:    <script src="/assets/literature-maps.js?v=39"></script>
```
结构化统计（`frontend/index.html` + `tests/frontend/**` 全量递归）：
```
JS 版本分布: Counter({'39': 9})
CSS 版本分布: Counter({'26': 9})
JS 非 39 的命中: []      # 源码/测试/fixture 无旧版本
CSS 非 26 的命中: []     # CSS 未改动，版本号未误升
```
```
$ grep -rn 'literature-maps\.js?v=38' frontend/ tests/ --include='*.py' --include='*.html' --include='*.js'
（无输出，EXIT=1）        # ✅ 无 v=38 残留
```
9 处 JS 版本点：`frontend/index.html:805`、`map_analysis_contract.py:34`、`literature_map_expansion.py:28`、
`literature_map_contract.py:28`、`map_groups_exports.py:18`、`map_groups_exports.py:44`（fixture 断言）、
`map_mobile_contract.py:94`、`map_mobile_contract.py:97`（fixture 断言）、`fixtures/literature_map_component.html:1120`
= 源码 1 + 测试断言 7 + fixture 1，与任务「9 处同步」一致。

裸 `"38"` 断言核对：`grep -rn '\b38\b' frontend/index.html tests/frontend/`(排除 app.js/styles.css 版本行) 命中均为**无关文件**
（`test_frontend_kb_inspection_pdf.js` 的 `pdfjs 4.10.38`、`test_frontend_map_graphics.py:86` 的 `len(label) <= 38`、
`literature_map_performance.html:149` 的 `y: 38 + row * 67` 坐标），**无遗留文献地图版本裸 38 断言**。

### T7. XSS — PASS
```
$ git diff -U0 -- frontend/ | grep '^+' | grep -i innerHTML
（无输出）
EXIT=1（grep 未命中，符合预期）

$ grep -c 'innerHTML' frontend/literature-maps.js
0
$ grep -in 'innerHTML' tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js
（无输出，EXIT=1）
$ git diff -U0 -- tests/frontend/ | grep '^+' | grep -i innerHTML
（无输出，EXIT=1）
```
- 本轮 frontend diff 仅新增 1 条布尔赋值 `refs.nodeStyleDisclosure.open = false`，**无任何文本写入面**，不存在 XSS 风险。
- 新增测试文件内零 `innerHTML`（DOM 桩用 `textContent` 与 `append`）。

### T8. 测试布局检查 — PASS
```
$ /Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py
test layout: ok
EXIT=0
```
新增 `test_frontend_node_style_panel_collapse_on_apply.js` 落在既有 `tests/frontend/` 约定命名下，布局检查通过。

### T9. 变异验证（测试有效性）— PASS
变异内容：**删除** `frontend/literature-maps.js:5251` 的收起语句（保留 +2 行注释）。

```
# 变异前备份并校验
$ cp frontend/literature-maps.js /tmp/spec043_r3_js_backup.js
$ shasum -a 256 frontend/literature-maps.js /tmp/spec043_r3_js_backup.js
ea7a1b90078dcae790acee1fb8505d4d48392adfc2ae144a6ccd319bb3e8b081  frontend/literature-maps.js
ea7a1b90078dcae790acee1fb8505d4d48392adfc2ae144a6ccd319bb3e8b081  /tmp/spec043_r3_js_backup.js

# 变异（定位校验后删除该行，并断言删掉的正是收起语句）
mutated: 5251 line removed
$ node --check frontend/literature-maps.js
EXIT=0                     # 语法仍合法 → 排除“语法报错导致的假红”
$ grep -n 'nodeStyleDisclosure.open = false' frontend/literature-maps.js
（无输出，EXIT=1）

# 变异后 vm 测试 → 应红
$ node tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js
AssertionError [ERR_ASSERTION]: 应用外观保存成功后，节点样式浮层必须自动收起（open=false）
true !== false
    at tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js:194:12
EXIT=1                     # ✅ 场景 1 捕获回归

# 变异后真实浏览器用例 → 应红（且只红新增那一个）
$ pytest tests/frontend/test_frontend_node_style_visibility.py -q
FAILED tests/frontend/test_frontend_node_style_visibility.py::test_applying_node_style_collapses_the_panel_after_save_succeeds
E  AssertionError: 「应用外观」保存成功后节点样式浮层必须自动收起（details.open === false）
E  assert '' is None
1 failed, 4 passed in 6.28s
EXIT=1                     # ✅ 新增浏览器用例捕获回归；4 个既有可见性用例仍绿 → 变异面精准

# 复原并校验逐字节一致
$ cp /tmp/spec043_r3_js_backup.js frontend/literature-maps.js
$ shasum -a 256 frontend/literature-maps.js
ea7a1b90078dcae790acee1fb8505d4d48392adfc2ae144a6ccd319bb3e8b081   # ✅ 与变异前一致
$ sed -n '5251p' frontend/literature-maps.js
    if (refs.nodeStyleDisclosure) refs.nodeStyleDisclosure.open = false;
$ git --no-pager diff --stat -- frontend/
 frontend/index.html         | 2 +-
 frontend/literature-maps.js | 3 +++
 2 files changed, 4 insertions(+), 1 deletion(-)      # ✅ 回到变异前 +4/-1

# 复原后复跑 → 应绿
$ node tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js
ok - node style panel collapses only after a confirmed successful apply   EXIT=0
$ pytest tests/frontend/test_frontend_node_style_visibility.py -q
5 passed in 4.56s   EXIT=0
$ node tests/frontend/test_frontend_node_style_disclosure.js
ok - frontend node style disclosure defaults collapsed and survives viewport changes   EXIT=0
```

结论：vm 测试与浏览器用例都是**真实敏感**的（删掉 1 行实现即红，复原即绿），不是空转断言；
变异已 sha256 级精确复原，工作树无遗留副作用。

## 验收点逐条核对（本轮）

| # | 验收点 | 结论 | 证据 |
|---|---|---|---|
| 1 | 应用外观**保存成功** → `details.open=false` | **PASS** | vm 场景 1（`open` 与 `getAttribute('open')===null`）+ 浏览器用例 `get_attribute("open") is None` |
| 2 | 保存成功后内容 **`display:none` / 0×0** | **PASS** | 浏览器用例 `_VISIBILITY_JS` 读 computed style + `getBoundingClientRect`，并由 `field.is_hidden()` 复核（依赖第二轮 CSS:293 规则，本轮未改） |
| 3 | **失败 / 409 / 结果未确认** → 保持展开 | **PASS** | vm 场景 3（409，草稿原样保留）/ 4（未确认，草稿保留）/ 5（503 失败），均断言 `open===true`；代码侧 5282-5287、5299-5304、5308 不经过 `updateSavedNodeStyle` |
| 4 | **取消预览**行为不变 | **PASS** | `cancelNodeStyleDraft()`(5226-5230) 本轮 diff 未触及，只重置草稿 + 重绘、不碰 `open`；vm 场景 6 断言取消后仍展开 |
| 5 | **视口切换**不改写开合 | **PASS** | 第二轮 `nodeStyleDisclosure.open` 强制改写已删除，本轮未引入新的 resize→open 路径；`test_frontend_map_layout_viewport.py` 14 passed、`test_frontend_map_mobile_contract.py` 12 passed |
| 6 | 收起不是禁用，可再次展开且看到已保存值 | **PASS** | 浏览器用例：summary `is_visible()` 为真 → 再点展开 → `fill_opacity=0.65`、`fill_mode=filled` 已回填；vm 场景 1 断言 summary 仍在且未 disabled |
| 7 | 前两轮契约不回归 | **PASS** | `test_frontend_node_style_disclosure.js` ok；`test_frontend_node_style_visibility.py` 5 passed（含第二轮 4 个既有用例） |

## VERIFICATION REPORT

```
VERIFICATION REPORT（第三轮前段回归）
=====================================

Build:       PASS   (node --check literature-maps.js / app.js 均 EXIT=0)
Types:       N/A    (原生 JS 无类型层；以 node --check + pytest 契约代替)
Lint:        PASS   (scripts/check_test_layout.py → test layout: ok)
Tests:       PASS   (vm 2/2 ok；pytest 5 + 86 = 91 passed, 0 failed, 0 skip)
Contract:    PASS   (open 语义 + computed display:none/0×0 双证；CSS:293 规则命中 details>fieldset)
Version:     PASS   (JS 9 处 v=39、v=38 残留 0；CSS 9 处 v=26 未误升)
XSS:         PASS   (frontend diff 新增 innerHTML 0 命中；仅 1 条布尔赋值)
Mutation:    PASS   (删 5251 → vm EXIT=1 + 浏览器 1 failed/4 passed；复原 sha256 一致，复跑全绿)
Security:    PASS   (无新增 innerHTML / 无新增外链 / 无凭据)
Diff:        10 files changed (+251/−11) + 1 新增测试文件（frontend 仅 index.html 2 + literature-maps.js 3）

Overall:     READY
```

## 与前两轮的关系

1. 第一轮断言「`open=false` 默认折叠」、第二轮断言「折叠态真正不可见」，本轮补上第三条交互终点
   「**保存成功后收起**」——三轮分别覆盖开合状态机 / 视觉可见性 / 保存终点行为，互补而非重复。
2. 第二轮 CSS 折叠隐藏规则（`literature-maps.css:293`）是本轮「收起后内容 0×0」的**前提**；
   本轮复用该规则而**未改动 CSS**，故 `literature-maps.css?v=26` 保持不变是正确的（若升版反而说明误改）。
3. 第二轮报告 R5 记录「JS 版本 9 处 v=38」已由本轮升级为 **v=39**，属预期演进。

## 阻塞项

**无。**
- playwright 可用，5 个可见性/收起用例真实执行，**无 skip、无伪造通过**。
- 未使用任何 stubbed 结果；变异验证的临时删除已 sha256 级复原。

## 遗留观察（不阻塞、不属本 spec）

1. `literature-map-node-style-apply` / `-cancel` 仍无独立 CSS 规则，依赖 `send-button` / `secondary-button` 基类
   （第一轮即记录，本轮未触及）。
2. 收起后若用户再次展开，`renderNodeStyleControls()` 已在 `updateSavedNodeStyle()` 内先行执行，
   控件取值与服务端一致；但面板「无 dirty 时 apply/cancel 置灰」为既有逻辑，与本轮无关。

## COMPLIANCE

- 未改任何业务代码（变异验证期间临时删除 1 行 JS，已用备份精确复原，sha256 `ea7a1b90…b081` 前后一致，
  `git diff --stat -- frontend/` 回到 `index.html 2 +-` / `literature-maps.js 3 +++`）。
- 未执行 git commit / push / merge。
- 未触碰主工作区 `/Users/wjh/ResearchAgent` 的任何文件（仅**只读**借用其 `.venv` 解释器；临时备份写在 `/tmp`）。
- 未运行后端 pytest。
- 注：`docs/sdd/reviews/043-node-style-disclosure-frontend-review.md` 的改动为**其他角色产物**，本角色未编辑该文件
  （本角色只追加本报告文件）。
- 日志（第三轮）：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-160457.md`
- 日志（第二轮）：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-045928.md`
- 日志（第一轮）：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-044920.md`

---

# 第四轮单端回归（人工验收第 4 轮 UX 缺陷修复）

- 时间：2026-11-05 17:23–17:37
- 分支 / HEAD：`main` @ `6307d0db`（工作区含本轮未提交改动）
- 范围：`frontend/literature-maps.js` 两处 UX 修复 + `frontend/index.html` 版本号 + 相关测试
- 角色边界：仅前端静态 / 契约核对，**未跑后端 pytest**、未改业务代码、未 git add/commit/merge/push

## 本轮修复内容（回归基线）

| 缺陷 | 修复点 | 源码位置 |
| --- | --- | --- |
| A「应用外观」无变更时点击无反应 | 新增无变更早退分支：零请求、`open=false` 收起、状态文案「外观未变更，已收起节点样式设置。」；`apply` 不再因无改动而 disabled | `literature-maps.js:5228`、`5277–5284` |
| B 多选「应用到 N 篇」后面板不消失 | 新增 `state.selectionPaletteDismissed`，参与 `hidden` 计算；主成功与核实成功置 `true`；开启/退出多选、改变节点选择三处重置 | `:76`、`:1787`、`:1801/1814/1838`、`:2117/2137` |

## 命令与结果

### 1. 语法检查
```
node --check frontend/literature-maps.js   → EXIT=0
```

### 2. 前端 JS 测试（逐个执行，共 15 个文件）
```
for f in tests/frontend/*.js; do node "$f"; done
```
**文件总数 15，全部退出码 0（15/15 PASS）**，关键两条真实输出：
- `test_frontend_node_style_panel_collapse_on_apply.js` → `ok - node style panel collapses only after a confirmed successful apply`
- `test_frontend_selection_palette_dismiss_on_apply.js` → `ok - selection color palette dismisses after a successful apply and reopens on selection change`

### 3. 前端契约 pytest（8 个文件）
```
.venv/bin/python -m pytest tests/frontend/test_frontend_node_style_visibility.py \
  tests/frontend/test_frontend_selection_color_palette_ux.py tests/frontend/test_frontend_map_palette.py \
  tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py -q
```
**`80 passed in 79.07s`，EXIT=0；passed=80，failed=0，skip=0。**
真实 Chromium 可用，`test_frontend_node_style_visibility.py` 的 4 个浏览器可见性用例真实执行，**无 skip、未把 skip 冒充通过**。

### 4. 版本契约
```
grep -rn "literature-maps.js?v=" frontend/index.html tests/frontend/   → 全部 v=40
grep -rn "literature-maps.js?v=39" frontend tests/frontend             → 零命中（EXIT=1）
```
命中清单：
- `frontend/index.html:805` → `/assets/literature-maps.js?v=40`
- `tests/frontend/fixtures/literature_map_component.html:1120` → `?v=40`
- 6 个 py 断言全部 v=40（`map_analysis_contract:34`、`literature_map_expansion:28`、`literature_map_contract:28`、`map_groups_exports:18/44`、`map_mobile_contract:94/97`）

其余版本号：`app.js?v=67`、`styles.css?v=67`、`literature-maps.css?v=26` —— 与本轮「app.js / CSS 未改动」的声明一致（升版反而说明误改）。

## VERIFICATION REPORT（第四轮）

```
Syntax:      PASS   (node --check EXIT=0)
Contract:    PASS   (15/15 JS 测试 EXIT=0；py 80 passed / 0 failed / 0 skip；JS↔CSS class 契约齐全)
Version:     PASS   (index.html / fixture / 6 处 py 断言均 v=40；v=39 零命中)
XSS:         PASS   (grep -c innerHTML frontend/literature-maps.js = 0；新增逻辑仅 textContent / hidden / open)
Mutation:    PASS   (2 项变异均被捕获；还原后 sha256 一致、全量复跑全绿)
Diff:        frontend 2 files (index.html 2 +- / literature-maps.js 30 ++++---)
```

## 四项静态核对明细

1. **`node --check`**：PASS，EXIT=0。
2. **class ↔ CSS 对应**：PASS。
   - `literature-map-node-style` 系列在 `literature-maps.css:285–299` 齐备（含 `-disclosure`、`-mode`、`-opacity-label`、`-opacity-value`、`button`）。
   - `literature-map-color-palette` 在 `:304/305/317/320`，其中 `:305` `[hidden] { display: none !important; }` 是 B 缺陷「隐藏生效」的样式前提。
   - 本轮 JS 未引入新的 class 名，既有 class 均有对应规则；CSS 未改动，故无反向核对缺口。
3. **`?v=N` 已升**：PASS（见第 4 节）。
4. **`innerHTML`**：PASS，`frontend/literature-maps.js` 命中数 **0**。

## 变异验证（证明测试非空跑）

基线 sha256：`2168eb055ea235580ce44bdcbf35cd92b5e42627e92c7995454b3d0399836053`

| # | 变异点 | 预期 | 实际 |
| --- | --- | --- | --- |
| 1 | `literature-maps.js:1787` 删去 `\|\| state.selectionPaletteDismissed` | dismiss 测试失败 | `test_frontend_selection_palette_dismiss_on_apply.js` **EXIT=1** —「颜色保存成功后设置面板必须隐藏（不得继续挡住画布）false !== true」(L165)；py `test_selection_palette_hides_after_apply_and_reappears_on_reselecting_a_node` **FAILED** — `assert palette.is_hidden()` → `False`（1 failed, 1 passed） |
| 2 | `literature-maps.js:5281` 无变更分支 `open = false → true` | collapse 测试失败 | `test_frontend_node_style_panel_collapse_on_apply.js` **EXIT=1** —「无变更点击「应用外观」也必须收起浮层（不得点了没反应）true !== false」(L310) |

**还原校验**：备份回写后 sha256 再次等于 `2168eb05…6053`；Read 读回 `:1787` 含 `|| state.selectionPaletteDismissed`、`:5281` 为 `open = false`；`git diff --stat -- frontend/` 回到 `index.html 2 +-` / `literature-maps.js 30 ++++---`；复跑 `node --check` OK、15 个 JS 测试全 EXIT=0、两个关键 py 文件 `8 passed`。临时备份 `/tmp/lm_backup_spec043_r4.js` 已删除，**无任何临时改动残留**。

## 测试覆盖真实性抽查

- `test_frontend_node_style_panel_collapse_on_apply.js`：`fs.readFileSync('../../frontend/literature-maps.js')` 原样摘出函数（L25），投入 `vm.createContext / vm.runInContext`（L138–139）**真实执行**保存路径；断言的是 `details.open` 与状态文案等用户可见行为，非文本匹配。
- `test_frontend_selection_palette_dismiss_on_apply.js`：同法读真实源码（L23），vm 沙箱执行 `renderMultiSelectControls()` 等（L134–135），断言 `selectionPalette.hidden`。
- `test_frontend_selection_color_palette_ux.py:60`：真实浏览器 `palette.is_hidden()` 断言保存成功后不可见。
- `test_frontend_node_style_visibility.py`：`_is_hidden()` 在移动/桌面/展开/收起 4 处真实可见性断言 + 静态护栏（`:not([open])` 容器限定且不依赖 `!important`）。

结论：新增测试读取真实源码、断言用户可见性，**不是空跑**。

## 阻塞项

**无。**

## 最终结论

**READY** —— A、B 两处 UX 缺陷修复在静态契约、版本一致性、XSS、测试覆盖与变异验证六个维度全部通过；
后端回归不在本角色范围（交由 `backend-tester`）。

## COMPLIANCE

- 未改任何业务代码：变异验证期间临时修改 2 次 JS，均已用备份精确复原并 sha256 级校验，`git diff --stat -- frontend/` 与回归前一致。
- 只修改本报告一份文档（追加，不覆盖第一至三轮历史）；未改其它报告 / spec / 台账。
- 未执行 git add / commit / merge / push。
- 未运行后端 pytest。
- 注：`.playwright-cli/` 与 `artifacts/jd-agent-infra-capability-map.md` 为先前遗留未跟踪文件，与本次回归无关，未纳入结论、未删除。
- 日志（第四轮）：`.codebuddy/agent-logs/spec-043/task-00/frontend-tester/20261105-172334.md`
