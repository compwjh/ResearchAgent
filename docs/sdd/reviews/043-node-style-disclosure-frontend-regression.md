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
