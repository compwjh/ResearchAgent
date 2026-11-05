# Spec043 前端评审：文献地图「节点样式」浮层默认折叠

- 评审角色：frontend-reviewer（独立只读评审）
- 工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`（分支 `codex/spec030-report-quality`）
- 评审范围：`frontend/**`、`tests/frontend/**`（`backend/**` 不在本次范围）
- 评审基线：`git diff`（工作区未提交改动，9 文件修改 + 1 文件新增）
- 结论：**通过（Approve）**，无 CRITICAL / HIGH 阻塞项；4 项 LOW 建议不阻塞合并

---

## 0. 缺陷与根因确认（代码事实）

| 项 | 事实 | 位置 |
|----|------|------|
| 根因 1 | 桌面端 `<details>` 被强制设为展开 | 修复前 `frontend/literature-maps.js:1211`：`nodeStyleDisclosure.open = !isMobileViewport();`（diff 中已删除） |
| 根因 2 | 视口从移动切回桌面时再次强制展开 | 修复前 `frontend/literature-maps.js:1398`：`if (refs.nodeStyleDisclosure) refs.nodeStyleDisclosure.open = !currentMobileViewport;`（diff 中已删除） |
| 现状 | 全模块已无任何 `.open =` 赋值 | `grep -n "\.open\s*=" frontend/literature-maps.js` → **无命中** |

结论：两个根因均已消除，且**不存在第三条改写 `open` 的路径**（见 §4）。

---

## 1. 必查项一：DOM 契约与重构等价性 — **PASS**

### 1.1 子控件逐项比对（原 1171–1210 行 vs 现 `literature-maps.js:1276-1314`）

| 子控件 / 属性 | 原实现 | 现实现 | 结论 |
|---|---|---|---|
| `fieldset.literature-map-node-style` + `id="literature-map-node-style"` | 1171-1172 | 1277-1278 | 一致 |
| `legend` 文案「节点填充」 | 1173 | 1279 | 一致 |
| radio `fill_mode`：`filled`「填充」/ `outline`「仅描边」（含 `name`、`value`、`checked` 绑定草稿） | 1174-1182 | 1280-1290 | 一致 |
| radio `change` → `updateNodeStyleDraft()` | 1180 | 1287 | 一致 |
| `label.literature-map-node-style-opacity-label`「填充透明度」 | 1183 | 1291 | 一致 |
| range `fill_opacity`：`min=0 / max=1 / step=0.05 / value=草稿` | 1184-1190 | 1292-1298 | 一致 |
| range `input` → `updateNodeStyleDraft()` | 1190 | 1299 | 一致 |
| `output.literature-map-node-style-opacity-value` 文案 `${round*100}%` | 1191 | 1300 | 一致 |
| `button.send-button.literature-map-node-style-apply`「应用外观」+ `disabled=true` + `click` → `saveNodeStyle(btn)` | 1192-1195 | 1302-1305 | 一致 |
| `button.secondary-button.literature-map-node-style-cancel`「取消预览」+ `disabled=true` + `click` → `cancelNodeStyleDraft()` | 1196-1199 | 1306-1309 | 一致 |
| `details.literature-map-node-style-disclosure` + `summary`「节点样式」+ 追加顺序（summary 在前、fieldset 在后） | 1200-1202 | 1311-1312 | 一致 |
| **唯一实质差异** | `details.open = !isMobileViewport()` | **已删除** | 预期改动（本次缺陷修复本体） |

> 逐字核对 `git diff frontend/literature-maps.js`：抽出的函数体与原内联块**文本完全相同**，仅 (a) 删除 `open` 赋值、(b) 末尾 `return { nodeStyleDisclosure, nodeStyle }`。无字段遗漏、无 class 改名、无 id 变更、无事件监听丢失。

### 1.2 `refs` 赋值正确性

- `literature-maps.js:1176`：`const { nodeStyleDisclosure, nodeStyle } = buildNodeStyleDisclosure();`
- `literature-maps.js:1262`：同一 `Object.assign(refs, { … nodeStyleDisclosure, nodeStyle, … })` 中仍以**同名变量**简写赋值 → `refs.nodeStyleDisclosure` / `refs.nodeStyle` 指向的对象与重构前完全等价。
- 下游消费方全部走 `refs.nodeStyle`，未受影响：`renderNodeStyleControls()` `:5205-5219`（查找 `input[name="fill_mode"]`、`input[name="fill_opacity"]`、`.literature-map-node-style-opacity-value`、`-apply`、`-cancel`）、`updateNodeStyleDraft()` `:5221-5226`。

### 1.3 构造顺序 / 变量作用域 / 初始化时机

- 调用点位于原内联位置（`multiSelectToggle` 之后、`layerTools.append` 之前），`layerTools` 子节点顺序不变 → CSS `flex` 布局与视觉顺序不变。
- `buildNodeStyleDisclosure()` 是函数声明，**提升**至作用域顶部，`:1176` 调用早于 `:1276` 定义不会触发 TDZ（函数声明非 `let/const`）。
- 函数内部只读取 `state.nodeStyleDraft`（模块闭包变量，`:2399-2400` 在 `applySavedView` 中初始化），并在创建时读取一次以设置 `checked`/`value`；与原内联块同一时机。`applySavedView` 随后调用 `renderNodeStyleControls()` 再同步一次，`refs.nodeStyle` 此时已赋值 → 无「读到旧草稿」回归。

### 1.4 `details/summary` 原生开合

- `details` 未设置 `open` 属性 → 浏览器默认折叠（HTML 标准语义）。
- `summary` 未被设为 `disabled`、未被 CSS 隐藏：`literature-maps.css:287` 仅 `list-style: none` 与 `::-webkit-details-marker { display: none }`（隐藏默认三角，保留自定义样式），`cursor: pointer` 仍可点击。
- 折叠时内容不可见由 UA 默认 `content-visibility`/display 语义保证，CSS 中**无** `details > *:not(summary) { display: flex }` 之类会强制显示的规则（`grep "details|summary" frontend/literature-maps.css` 仅命中 `:286-289` 及无关的 `.literature-map-analysis-summary` / `-expansion-batch-summary`）。
- 动态证据：`node tests/frontend/test_frontend_node_style_disclosure.js` → 初始 `open === false`（桌面/移动两种视口）、点击后 `true`、再点 `false`。Playwright 侧 `test_frontend_map_mobile_contract.py:145-150` 亦断言初始 `open is None`、点击可见、再点 `open is None`。

### 1.5 DOM 契约（class ↔ CSS 双向 grep）

```
grep -n "literature-map-node-style" frontend/literature-maps.css
```
命中 `frontend/literature-maps.css:285-295`：`.literature-map-node-style`、`-disclosure`、`-disclosure > summary`、`-disclosure[open] > summary`、`legend`、`-mode`、`-opacity-label`、`input[name="fill_opacity"]`、`-opacity-value`、`button` —— **JS（`:1277-1312`）生成的每个 class 都在 CSS 中真实存在**，反向亦无孤立钩子。**PASS**

---

## 2. 必查项二：`?v=N` — **PASS**

```
grep -rn "v=37" frontend/ tests/          # 仅命中 tests/frontend/__pycache__/*.pyc（编译缓存，非源码）
grep -rn "v=38" frontend/ tests/          # 命中 index.html:805、fixture:1120、7 处 py 断言
```

| 位置 | 内容 | 状态 |
|---|---|---|
| `frontend/index.html:805` | `<script src="/assets/literature-maps.js?v=38">` | 唯一真实引用，37→38 ✅（只改一处） |
| `tests/frontend/fixtures/literature_map_component.html:1120` | `…literature-maps.js?v=38` | ✅ |
| `test_frontend_literature_map_contract.py:28` | `'/assets/literature-maps.js?v=38'` | ✅ |
| `test_frontend_literature_map_expansion.py:28` | `"/assets/literature-maps.js?v=38"` | ✅ |
| `test_frontend_map_analysis_contract.py:34` | `"/assets/literature-maps.js?v=38"` | ✅ |
| `test_frontend_map_groups_exports.py:18` | `"/assets/literature-maps.js?v=38"` | ✅ |
| `test_frontend_map_groups_exports.py:44` | fixture 断言 `v=38` | ✅ |
| `test_frontend_map_groups_exports.py:45` | `re.findall(...)[-1] == "38"` | ✅ |
| `test_frontend_map_mobile_contract.py:94 / :97 / :119` | `v=38` ×3（含 `[-1] == "38"`） | ✅ |

- 8 处断言 + fixture 全部同步，**无遗漏的 v=37 源码引用**。
- 历史 compatibility 注释**原样保留**：`index.html:803`（Task05 research-tasks）、`:806`（Legacy asset-version）、`:808`、`:809`（Task09/Task10）、`:810`（Spec037）均未改动，diff 只动 `:805` 一行。
- 断言自洽性：`[-1] == "38"` 取 index.html 中**最后**一个 `literature-maps.js?v=` 匹配——`:805` 是该文件唯一的 literature-maps.js 引用，取 `[-1]` 即取唯一值，不会因注释行干扰（注释行只含 `app.js`/`styles.css`/`research-tasks.js`）。

---

## 3. 必查项三：XSS — **PASS**

```
grep -n "innerHTML|outerHTML|insertAdjacentHTML|document.write|eval(" frontend/literature-maps.js frontend/index.html   → 无命中 (exit 1)
git diff frontend/ | grep "^+" | grep -n "innerHTML|outerHTML|insertAdjacentHTML|eval("                                    → 无命中
```

- 新增 `buildNodeStyleDisclosure()` 全程使用 `createElement(tag, className, text)`，其实现 `literature-maps.js:176-180` 对文案走 `node.textContent = String(text)`；`input.value`/`input.checked` 均为属性赋值，**无 HTML 拼接**。
- 新增注释与 `return` 语句不引入任何 DOM 注入面。**PASS**

---

## 4. 额外风险问答

### Q1. `handleMobileViewportResize()` 删除 `open` 赋值后，移动端（≤760px）既有面板/抽屉行为有无回归？

**无回归。** 依据：

1. 实际删除的只有 1 行赋值，其余逐行保留（`literature-maps.js:1399-1408`）：`currentMobileViewport`/`previousMobileViewport` 计算、相等短路 `if (previousMobileViewport === currentMobileViewport) return;`、`preserveDesktopDetail` 计算、`closeAllMobilePanels(false, preserveDesktopDetail)`、`scheduleViewportStabilization()` 全部在。
2. 抽屉状态机（`closeMobilePanel` `:1335-1367`、`openMobilePanel` `:1369-1390`、`closeAllMobilePanels` `:1392-1397`、`setMobileDrawerBodyState` `:1331-1333`）**未被本 diff 触碰**。
3. CSS 移动端抽屉规则（`literature-maps.css:246-278`：`position: fixed`、`z-index: 1070`、`is-open` 位移显示）未改动，且 `grep "details|summary"` 确认无任何移动端媒体查询改写 `details` 显示。
4. 移动端原行为本来就是折叠（`!isMobileViewport()` 在 ≤760px 为 `false`），删除赋值后移动端初始态**与修复前完全一致**；变化只发生在桌面端（由「强制展开」变为「保持用户选择」）。
5. 动态证据：`test_frontend_map_mobile_contract.py:145-150` 覆盖移动端折叠→展开→折叠；`:129-143` 覆盖列表抽屉开合与焦点回归（`activeElement.id === 'literature-map-mobile-list-open'`）；`:166-176` 覆盖详情抽屉与焦点回到 `data-node-id`。

### Q2. 视口切换时是否还有其它路径会重新展开浮层？

**没有。** `grep -n "\.open\s*=" frontend/literature-maps.js` → 0 命中；`grep -n "createElement('details'"` → 仅 `:1311` 一处。即：
- 不存在 `refs.nodeStyleDisclosure.open = …` 的任何残余；
- 不存在 `details` 元素被二次创建；
- 不存在 `setAttribute('open', …)` / `toggleAttribute('open')` / `matchMedia` 监听改写该元素的写入点。

### Q3. `test_frontend_map_palette.py` 补点击 summary 是否只是适配新交互，还是掩盖了真实缺陷？

**只是适配新交互，未掩盖缺陷。** 依据：

1. 两处新增（`test_frontend_map_palette.py:347-352`、`:431-436`）在点击前**主动断言 `open is None`**——这是把「默认折叠」变成可失败的前置检查，方向与掩盖缺陷相反（若实现回退为默认展开，这两条会直接失败）。且 `test_frontend_map_palette.py` 在同一 spec 内由 `test_frontend_map_mobile_contract.py:146` 同步做了同性质断言，形成双保险。
2. Playwright 中 `check()` 作用于 `display:none` 的 `details` 内容会超时；新增 `style.wait_for(state="visible")` 明确等待展开完成，避免了靠超时掩盖交互时序问题的写法。
3. 被测试的业务断言**全部保留且强度不变**：「应用前不写入（`__viewBodies.length == 0`）」「仅描边时 `fill-opacity == '0'`」「PNG 使用已保存的 outline 样式」「预览未应用时导出被拦截」等均未放宽。
4. 无任何测试因改动被 `skip` / 断言被删除（`git diff tests/frontend/` 检查：py 侧均为 `37→38` 版本串替换 + palette 的两处展开步骤新增；无 `pytest.skip` 新增）。

### Q4. 是否存在「地图重绘 / 重新 mount 时 details 被重建并再次默认展开」的路径？

**不存在永久重建路径；且即使重建也只会折叠（不会违背用户预期）。** 依据：

1. `renderShell()` `:908-910`：`if (!mount || state.mounted) return;` —— **首帧 mount 后不再重建**。`setActive()` `:6894-6921` 每次切换视图都调用 `renderShell()`，但 `state.mounted`（`:1269` 置 true）使其成为幂等 no-op。
2. `renderGraph()` `:4701-4710` 只 `replaceChildren()` 于 `refs.edgesGroup` / `refs.nodesGroup`（SVG 图层），完全不触碰 `layerTools` / `nodeStyleDisclosure`；`grep -n "createElement('details'"` 全局唯一命中 `:1311`。
3. 打开另一张地图走 `selectMap()` → `applySavedView()` `:2380-2404`，其中 `renderNodeStyleControls()` `:5205` 只改写 `checked/value/disabled`，**不写 `open`** → 用户已展开的面板在切换地图后保持展开，草稿被同步刷新（正确行为）。
4. 唯一「重建」场景是整页刷新 / 视图模块被重新加载：此时 `details` 从无到有、折叠态初始化——这正是用户要求的默认行为，不构成缺陷。

### Q5. 是否存在「顺带改变节点样式保存/预览/导出行为」？

**没有。** 本 diff 在行为维度上严格限于「默认折叠 + 点击展开」：

- 预览链路：`updateNodeStyleDraft()` `:5221-5226` → 草稿与重绘，**未改**；
- 保存链路：`saveNodeStyle()` `:5263`、`updateSavedNodeStyle()` `:5236`、`nodeStyleIsDirty()` `:5200`，**未改**；
- 导出拦截：`test_exports_are_blocked_while_color_or_style_preview_is_unapplied` 断言原样保留（`__serializedExportSvg == null`、`__requestLog` 无 export、`__viewBodies.length == 0`）；
- `renderNodeStyleControls()` 的 `disabled` 计算逻辑（`:5214-5218`）未改，仍依赖 `state.map.map_id` / `nodeStyleIsDirty()` / `nodeStyleSaveInFlight`；
- 所有 `ARIA`/焦点管理代码（`restoreMobileFocus`、`restoreDesktopPanelAccessibility`）未改。

---

## 5. ECC 评审维度检查

| 维度 | 结论 | 依据 |
|---|---|---|
| 函数体量（>50 行告警） | 注意 | `buildNodeStyleDisclosure()` 39 行（`:1276-1314`），约 40 行、低于阈值；但重复嵌套 `.forEach` + 6 个元素构造，可读性一般（见 LOW-2） |
| 文件体量（>800 行） | 既有问题 | `frontend/literature-maps.js` 6925 行，远超 800 行阈值；**属既有负债，非本 diff 引入**，不阻塞本次 |
| 深层嵌套（>4 层） | PASS | 抽取后 `layerTools` 构造函数**减少**一层内联嵌套 |
| 调试输出 | PASS | 新增 `console.log` 仅出现在测试文件末尾（`:213`，作为成功信号，与项目既有 `*.js` 约定一致） |
| 闭包捕获过期变量 | PASS | `buildNodeStyleDisclosure()` 内读取 `state.nodeStyleDraft` 为创建时快照，与重构前一致；后续同步由 `renderNodeStyleControls()` 负责 |
| 死代码 | PASS | 删除的 `open` 赋值无残留引用；`refs.nodeStyleDisclosure` 仍被 `:1262` 赋值，`refs.nodeStyle` 仍被 `:5206/5222` 消费；`refs.nodeStyleDisclosure` 目前**无读取方**（详见 LOW-1） |
| 命名 / 注释 | PASS | 函数名动词化、注释解释 WHY（为何不随视口变化）而非 WHAT |
| 测试覆盖 | PASS（含 LOW-3） | 新增 Node 契约测试覆盖初始折叠/点击展开/视口保持；Playwright 覆盖移动端与桌面端真实交互 |

---

## 6. 问题清单

### CRITICAL / HIGH

无。

### MEDIUM

无。

### LOW（建议，不阻塞）

| ID | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| LOW-1 | LOW | `frontend/literature-maps.js:1262` | 删除 `handleMobileViewportResize()` 中的唯一读取点后，`refs.nodeStyleDisclosure` 成为**只写不读**的悬挂引用（`grep` 确认无其他消费方） | 若后续无计划使用，可在下次触碰时移除该 `refs` 键以降低误导；当前保留无害 |
| LOW-2 | LOW | `frontend/literature-maps.js:1276-1314` | `buildNodeStyleDisclosure()` 内层 `.forEach` + 逐字段构造 39 行，注释说「不得由视口决定」但代码没有断言性防护，未来有人重新加 `open = …` 不会被守卫（除新增测试外） | 已由 `test_frontend_node_style_disclosure.js` 兜住，可暂不动 |
| LOW-3 | LOW | `tests/frontend/test_frontend_node_style_disclosure.js` | 未被任何 `.py` / CI 配置显式引用，只靠 `node tests/frontend/*.js` 全量跑；若 CI 只跑 pytest，此测试会静默不执行 | 属项目既有约定（`tests/e2e/README.md:7`、`docs/sdd/plans/039-test-infra-validation.md:21` 记录 `node tests/frontend/*.js` 为既定跑法），建议交付说明中显式写出该命令 |
| LOW-4 | LOW | `tests/frontend/__pycache__/*.pyc` | 缓存目录仍含旧 `v=37` 字符串字节（非源码，不影响测试判定，但会污染 `grep v=37` 的排查结果） | 提交前清理 `__pycache__`（如已 gitignore 可忽略）；确认 `.gitignore` 覆盖 |

---

## 7. 本项目四项必守逐条判定

| # | 必守项 | 判定 | 核对依据 |
|---|---|---|---|
| 1 | **DOM 契约** | **PASS** | JS 新增/保留的 class `.literature-map-node-style`、`-disclosure`、`-mode`、`-opacity-label`、`-opacity-value`、`-apply`、`-cancel` 均在 `frontend/literature-maps.css:285-295` 真实存在；反向 grep CSS 的 `literature-map-node-style*` 钩子在 JS `:1277-1312` 均有对应生成点。本次**未新增** class 名 |
| 2 | **版本号 `?v=N`** | **PASS** | `frontend/index.html:805` `v=37 → v=38`（唯一真实引用）；`grep -rn "v=37" frontend/ tests/` 仅命中 `__pycache__/*.pyc`，源码零残留；8 处断言 + fixture 全部 `v=38`；`index.html:803/806/808/809/810` compatibility 注释原样保留 |
| 3 | **XSS** | **PASS** | `grep -n "innerHTML|outerHTML|insertAdjacentHTML|document.write|eval(" frontend/literature-maps.js frontend/index.html` 无命中；diff `+` 行同样无命中；新增 DOM 一律经 `createElement()` → `textContent`（`:176-180`） |
| 4 | **CSS 作用域** | **PASS** | 本 diff **未改动** `frontend/literature-maps.css`；既有相关选择器全部以 `#literature-maps-view .literature-map-node-style*` 前缀 + `>` 直系组合子限定，无裸标签选择器 |

---

## 8. 结论

**通过（Approve）。**

- 被评审改动**严格限定**在「节点样式浮层默认折叠 + 仅由用户点击展开」这一行为面内：仅删除 2 处 `open` 改写、抽出一个等价构造函数、同步版本号与测试断言，未顺带改变保存 / 预览 / 导出 / 抽屉 / 焦点管理等任何既有行为。
- 根因两个写入点均已消除，全模块已无任何 `.open =` 赋值，不存在第三条重新展开路径。
- 四项必守全部 PASS，无 CRITICAL / HIGH / MEDIUM 问题；4 项 LOW 建议可不阻塞合并。
- 阻塞项：**无**。

## 评审摘要

| 严重级别 | 数量 | 状态 |
|----------|------|------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 4 | note |

结论：**Approve**——无阻塞项，可合并。

### 复现用的校验命令

```bash
node --check frontend/literature-maps.js                                  # OK
grep -n "?v=" frontend/index.html                                        # :805 v=38
grep -rn "v=37" frontend/ tests/                                         # 仅 __pycache__/*.pyc
grep -n "\.open\s*=" frontend/literature-maps.js                          # 无命中
node tests/frontend/test_frontend_node_style_disclosure.js               # ok
for f in tests/frontend/*.js; do node "$f"; done                         # 13/13 exit 0
```

---

# 第二轮补修复审（2026-11-05，独立复审）

- 追加原因：第一轮评审只核到「`open` 属性已无改写」，未验证**折叠态内容是否真的不可见**。主会话真实浏览器复测发现 `<details open=false>` 下 `#literature-map-node-style` 仍为 `display:flex; visibility:visible; rect [16,383]`（内容缩成竖条继续渲染在画布上方）。
- 复审范围：`frontend/**`、`tests/frontend/**` 的**全部未提交改动**（含第一轮遗留改动与第二轮新增），`backend/**` 不在范围。
- 复审方式：只读；`git diff` + Read/Grep 逐行核对真实落盘，另引用主会话真实浏览器复测结果作为运行时证据。

## R1. 必查项一：CSS 规则作用域与优先级 — **PASS**

新增规则 `frontend/literature-maps.css:293`：

```css
#literature-maps-view .literature-map-node-style-disclosure:not([open]) > .literature-map-node-style { display: none; }
```

| 子问题 | 结论 | 依据（文件:行） |
|---|---|---|
| 是否只命中该浮层 | **只命中** | 规则以 `#literature-maps-view` 收敛作用域；`> .literature-map-node-style` 为直系子元素组合子，仅匹配 `literature-maps.js:1277` 创建的 `<fieldset id="literature-map-node-style">`。全 CSS 中 `literature-map-node-style*` 共 16 行（`literature-maps.css:285-299`），无第二条 `:not([open])` 规则 |
| 特异性是否足够压过 `display:flex` | **足够（双保险）** | 285 行 `.literature-map-node-style { display:flex }` = (1,2,0)；293 行 = `#id`(1) + `.disclosure`(1) + `:not([open])`(1) + `.node-style`(1) = **(1,3,0)**，且位置在 285 之后 → 特异性与顺序均占优 |
| 展开态 `[open]` 是否完全恢复原布局 | **完全恢复** | `[open]` 时 `:not([open])` 不匹配 → 293 行失效 → fieldset 回到 285 行 `display:flex; flex-wrap:wrap; ...`。主会话实测展开态 `display:flex / rect 416×47`，与缺陷前布局一致 |
| 是否影响内部 radio/range/button | **不影响** | 294-299 行对内部子元素只声明 `padding/font-size/width/accent-color/inline-flex`，均被父级 `display:none` 一并隐藏；无 `display` 冲突声明 |
| 是否影响其它 `<details>` 组件 | **不影响** | 项目内 `literature-map-node-style-disclosure` 类仅此一处（`literature-maps.js:1311` 创建）；`grep -rn "literature-map-node-style-disclosure" frontend/` 只有该处 + CSS 286-293 |
| 是否被后续规则覆盖 | **未被覆盖** | 294 行之后无任何对 `.literature-map-node-style` 自身 `display` 的再声明（`grep "literature-map-node-style" literature-maps.css \| grep display` 只有 285/286/288/293/295） |
| 是否使用 `!important` | **未使用** | 293 行原文无 `!important`；测试 `test_frontend_node_style_visibility.py:171` 亦显式断言 `"!important" not in rule` |

## R2. 必查项二：`?v=N` 同步 — **PASS**

| 位置 | 变化 | 核对 |
|---|---|---|
| `frontend/index.html:9` | `literature-maps.css?v=25 → v=26` | 唯一真实 CSS 引用，已升版 |
| `frontend/index.html:805` | `literature-maps.js?v=38` | 第一轮已升，本轮保持 |
| `tests/frontend/fixtures/literature_map_component.html:8 / 1120` | `css?v=26` / `js?v=38` | 已同步 |
| `test_frontend_literature_map_contract.py:28-29` | v=38 / v=26 | 已同步 |
| `test_frontend_literature_map_expansion.py:28-29` | v=38 / v=26 | 已同步 |
| `test_frontend_map_analysis_contract.py:34-35` | v=38 / v=26 | 已同步 |
| `test_frontend_map_groups_exports.py:18-19, 43-45` | v=38 / v=26，且 `re.findall(...)[-1] == "38"` | 已同步 |
| `test_frontend_map_mobile_contract.py:94-99, 119` | v=38 / v=26 | 已同步 |

- `grep -rn "literature-maps\.css?v=25\|literature-maps\.js?v=37" --include=*.py --include=*.html --include=*.js` → **源码零命中**（仅命中 `docs/` 与 `.codebuddy/agent-logs/` 的历史快照，属时间点记录，不应修改）。校验命令返回 exit=0 系命中文档所致，非源码残留。
- 历史 compatibility 注释保留：`index.html:7`（styles.css 系列）、`index.html:803`（research-tasks 系列）、`index.html:807`（app.js/styles.css 旧版本行）均未删除。
- 额外核对：`test_frontend_map_palette.py:348-353 / 432-438` 新增「先断言默认折叠 → 点 summary → `wait_for(state="visible")`」，属对折叠默认值的**必要适配**，未削弱任何原有断言（无 try/except 吞异常）。

## R3. 必查项三：XSS / DOM 契约 / 测试真实性 — **PASS**

| 检查 | 结论 | 依据 |
|---|---|---|
| 新增 CSS 行引入注入面 | 无 | CSS 纯静态声明，无 `url()`、无 `expression()` |
| `frontend/literature-maps.js` 含 `innerHTML` 等 | 无 | `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|document.write\|eval(" frontend/literature-maps.js` → 0 命中；`node --check` → OK |
| 新测试是否断言真实可见性 | **是** | `test_frontend_node_style_visibility.py:29-46` 采集 `getComputedStyle` 的 `display/visibility/opacity` + `getBoundingClientRect` 面积；`:52-60` `_is_hidden()` 三条件判定；`:88-98` 折叠态断言 `_is_hidden(collapsed)`，并**前置**断言 `open is None` —— 缺陷场景（`open=false` 但 `display:flex`/rect>0）会被判负，正是第一轮漏掉的层 |
| 展开态断言是否同样严格 | 是 | `:107-115` 断言 `display == "flex"`、`visibility == "visible"`、宽高阈值（桌面 ≥380×30、移动 ≥300×60），失败信息带实际快照 |
| 浏览器缺失时是否静默通过 | 否 | `:47-50` `except → pytest.skip("真实浏览器阻塞，未将静态检查冒充通过")`，skip 与 pass 在报告中可区分 |
| 静态护栏 | 有 | `:157-171` 断言规则存在、`startswith("#literature-maps-view ")`、含 `display: none` 且不含 `!important`、`>` 直接命子元素 |

## R4. 必查项四：风险问答

**Q1：第一轮复审/回归为何漏掉了这层？**

三层原因，均为可核事实：

1. **验证口径错位**：第一轮全部证据停留在「HTML 属性/JS 状态」层——`grep "\.open\s*="` 无命中、`open === false` 断言通过。而 CSS 层是另一套机制，属性正确 ≠ 不可见。第一轮的静态断言（`test_frontend_literature_map_contract.py` 等）只校验版本号与字符串存在，不含 computed style。
2. **测试替身无渲染语义**：`tests/frontend/test_frontend_node_style_disclosure.js` 用 vm 沙箱抽取源码执行 DOM 逻辑，只验证"是否赋值 open"，没有真实排版引擎，天然无法发现 `display:flex` 覆盖 UA 隐藏。
3. **配置组合未被覆盖**：UA 对关闭态 `<details>` 的非 summary 子元素用 `content-visibility/display` 内部机制隐藏，作者显式 `display:flex` 会覆盖它。`literature-maps.css:285` 的 `display:flex` 在浮层默认折叠**之前**就存在且无害，折叠一旦成为默认值，这个既有声明立刻转为缺陷放大器。第一轮没有把「既有 CSS」与「新默认值」放在一起推演。

**Q2：本轮证据是否足以闭合？**

**足以闭合。** 证据链覆盖两侧边界：

| 场景 | 主会话实测 | 与代码预期一致 |
|---|---|---|
| 1280×800 折叠态 | `open=false / display:none / rect 0×0 / summary 可见` | ✅ 293 行规则生效 |
| 点击 summary | `open=true / display:flex / rect 416×47` | ✅ 293 行失效，回 285 行 |
| 收起 → 700 宽 → 回 1280 | `open=false / display:none / summary 可见` | ✅ 视口切换不再改写 open（JS 侧改动保持），且规则对 attributes 变化即时生效 |
| 自动化用例 | `test_frontend_node_style_visibility.py` 4 用例（1440/390 折叠+展开、视口往返、静态护栏） | ✅ 断言的是 computed style/rect，非 `open` |

补充说明：`summary` 在折叠态仍可见是**设计预期**（否则用户无法展开），不属缺陷。

**Q3：是否还存在其它让浮层内容在折叠态渲染的路径？**

已穷举排查，**未发现第三条路径**：

| 可能的路径 | 排查结论 | 依据 |
|---|---|---|
| 其它 CSS 规则再声明 `display` | 无 | `grep -n "literature-map-node-style" literature-maps.css` 共 16 行（285-299），声明 fieldset `display` 的只有 285（flex）与 293（none，条件匹配） |
| 移动端 media query 特例 | 无 | `literature-maps.css:200-285`（`@media` 段）内不含 `.literature-map-node-style`（`awk` 段内 grep → 0 命中） |
| JS 直接写 `style.display` / `open` | 无 | `grep -n "\.open =\|style\.display" frontend/literature-maps.js` → 无命中 |
| JS 重绘导致重复挂载/属性丢失 | 无 | `layerTools` 只 append 一次（`literature-maps.js:1147-1178`），`buildNodeStyleDisclosure()` 只在 `:1176` 调用一次 |
| 运行时加 class 绕过 `:not([open])` | 无 | 折叠态不再有任何代码路径切换该 details 的 class 或 open；开合完全由浏览器 summary 语义驱动 |
| 与 `isMobileViewport` 联动 | 已解除 | `refs.nodeStyleDisclosure.open` 两处写入均已删除；`isMobileViewport` 仍有 14 处其它调用（非死代码） |

## R5. 四项必守逐条判定（第二轮）

| # | 必守项 | 判定 | 核对依据（命令 + 命中行） |
|---|---|---|---|
| 1 | **DOM 契约** | **PASS** | 双向 grep：CSS 侧 `literature-map-node-style-disclosure` 出现在 `literature-maps.css:286-289,293`；JS 侧 `literature-maps.js:1311` `createElement('details', 'literature-map-node-style-disclosure')`；`literature-map-node-style` CSS 在 `:285,293,294-299`，JS 在 `:1277-1278`。新增选择器两个 class 均有真实生成点，无孤儿钩子 |
| 2 | **版本号 `?v=N`** | **PASS** | `grep -n "?v=" frontend/index.html` → `:9 css?v=26`、`:805 js?v=38`；`grep -rn "literature-maps\.css?v=25\|literature-maps\.js?v=37"` 在 `*.py/*.html/*.js` 源码 → 0 命中（仅 docs/logs 历史记录） |
| 3 | **XSS** | **PASS** | `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|document.write\|eval(" frontend/literature-maps.js` → 0 命中；新增测试与 fixture 新增行同样 0 命中；`node --check frontend/literature-maps.js` → OK |
| 4 | **CSS 作用域** | **PASS** | 293 行以 `#literature-maps-view` 开头，无裸标签选择器；`> .literature-map-node-style` 直系限定；`!important` 0 处；与 285 行特异性对比 (1,3,0) vs (1,2,0) 成立 |

## R6. 问题清单（第二轮）

| 级别 | 问题 | 位置 | 说明 / 建议 |
|---|---|---|---|
| LOW | details 容器自身仍为 `display:flex` | `frontend/literature-maps.css:286` | 折叠时它是只含 summary 的 flex 容器，无可见残留（实测 fieldset rect 0×0、summary 正常可见）。属可接受的冗余，不建议本轮改动（改它需重排 summary 与 fieldset 的 gap 行为，风险大于收益） |
| LOW | `refs.nodeStyleDisclosure` 现仅被写入、无读取 | `frontend/literature-maps.js:1262` | 第一轮遗留；可用于未来调试或外部契约，暂留无功能影响 |
| LOW | 任务描述称「8 处断言/fixture」，实际为 7 个文件 10 个断言点 + palette 2 处适配 | `tests/frontend/**` | 仅口径差异，实际同步更完整，无遗漏 |
| note | `docs` 与历史日志中仍存 `v=25/v=37` | `docs/sdd/plans/043/*`、`.codebuddy/agent-logs/*` | 时间点快照，属历史记录，**不应修改**，不构成残留 |

无 CRITICAL / HIGH / MEDIUM 问题。

## R7. 第二轮结论

**通过（Approve），可合并。**

- 第二轮的修复方向正确且最小：用一条作用域受限、特异性足够、无 `!important` 的作者样式规则，显式恢复浏览器在折叠态本应提供的隐藏；展开态布局零变化。
- 第一轮 JS 改动保持有效，`open` 的两个写入点已彻底移除；本轮 CSS 规则与 JS 改动互补，共同构成「默认折叠且真的看不见」的完整闭环。
- 新测试把断言层从「属性」提升到「computed style + 几何矩形」，正是本次漏检的根因面，可防止同类回归（含 `display:flex` 类作者样式覆盖 UA 隐藏的场景）。
- 阻塞项：**无**。

### 第二轮评审摘要

| 严重级别 | 数量 | 状态 |
|----------|------|------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 3 | note |

Verdict: **Approve** —— 无阻塞项；3 项 LOW 为可选优化，不阻塞合并。

### 第二轮复现用校验命令

```bash
cd /Users/wjh/.codex/worktrees/map-usability/ResearchAgent
node --check frontend/literature-maps.js                                   # OK
grep -n "?v=" frontend/index.html                                         # :9 v=26, :805 v=38
grep -rn "literature-maps\.css?v=25\|literature-maps\.js?v=37" \
  --include=*.py --include=*.html --include=*.js .                        # 源码 0 命中（仅 docs/logs）
grep -n "literature-map-node-style" frontend/literature-maps.css          # 285-299，仅 293 为折叠隐藏
grep -n "\.open =\|style\.display" frontend/literature-maps.js            # 无命中
python -m pytest tests/frontend/test_frontend_node_style_visibility.py -q  # 需真实 Chromium
```

---

# 第三轮补修复审（文档 + 保存确认后自动收起）· 2026-11-05

> 复审角色：`frontend-reviewer`（只读，未改任何代码，未 commit，未跑后端 pytest）。
> 复审范围：`frontend/**`、`tests/frontend/**`；后端改动不在本轮范围。
> 工作目录：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`（主工作区未触碰）。
> 日志：`.codebuddy/agent-logs/spec-043/task-00/frontend-reviewer/20261105-160456.md`

## R8. 本轮真实落盘（git diff 核对，非描述采信）

```
frontend/index.html                                  | 2 +-   (:805 literature-maps.js?v=38 → v=39)
frontend/literature-maps.js                          | 3 ++    (:5249-5251 三行，含注释)
tests/frontend/fixtures/literature_map_component.html| 2 +-   (:1120 → v=39)
tests/frontend/test_frontend_literature_map_contract.py       | 2 +-
tests/frontend/test_frontend_literature_map_expansion.py      | 2 +-
tests/frontend/test_frontend_map_analysis_contract.py         | 2 +-
tests/frontend/test_frontend_map_groups_exports.py            | 6 +--  (:18、:44 含裸数字断言 "38"→"39")
tests/frontend/test_frontend_map_mobile_contract.py           | 6 +--  (:94、:97、:119 含裸数字断言)
tests/frontend/test_frontend_node_style_visibility.py         | 61 +++  (新增 1 个真实浏览器用例)
tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js | 新增（**未跟踪**，见 M1）
```

`frontend/literature-maps.css` 零改动（`git diff` 无该文件），v=26 保持不变。与「本轮只改 JS 收起点」的描述一致。

## R9. 必查项 1：收起时机正确性 — **PASS（含 1 项 LOW）**

### R9.1 收起点位置与调用者

| 事实 | 证据 |
|---|---|
| 新增行位于 `updateSavedNodeStyle()` 末尾，语义是「已采纳服务端返回值」 | `frontend/literature-maps.js:5249-5251` |
| 该函数开头有早退保护，非当前地图直接 return（**不会**收起别人的面板） | `frontend/literature-maps.js:5237` `if (mapId !== state.selectedMapId \|\| !state.map \|\| state.map.map_id !== mapId) return;` |
| 全文件仅两处调用，均为成功分支 | `:5280`（PATCH 成功主分支）、`:5297`（断连后重新读取、值与草稿一致的分支） |
| 第三处 `nodeStyle` 相关读写不涉及关闭 | `:5439` 仅只读校验 |

`grep -n "updateSavedNodeStyle\|nodeStyleDisclosure" frontend/literature-maps.js` 命中行：`1176`（解构）、`1262`（收进 refs）、`5236`（定义）、`5251`（新增写）、`5280`、`5297`。**无其它调用者**。

### R9.2 逐路径核对（是否误收起 / 漏收起）

| 路径 | 代码位置 | 是否到达 `:5251` | 结论 |
|---|---|---|---|
| PATCH 成功 | `:5279-5281` | 到达 | 收起 ✅ 符合预期 |
| 断连 / 超时后重读，值与草稿一致 | `:5290-5298` | 到达 | 收起 ✅ 符合预期（已确认落库） |
| 断连后重读，值与草稿**不一致**（结果未确认） | `:5299-5305` | 不到达 | 保持展开 ✅ 不漏收起 / 不误收起 |
| 重读请求本身抛错 | `:5306-5308` | 不到达 | 保持展开 ✅ |
| 409 冲突 → 重读成功并保留草稿 | `:5284-5288` → `rereadNodeStyleAfterConflict` `:5254-5264` | 不到达（该函数**不碰 open**） | 保持展开、草稿保留 ✅ |
| 409 且重读也失败 | `:5285-5287` catch | 不到达 | 保持展开 ✅ |
| 明确失败（非 409、非 retryable） | `:5311` | 不到达 | 保持展开 ✅ |
| 响应回来时 `state.active` 失效 / 已切图 | `:5279`、`:5283`、`:5293` 三处 `return` | 不到达 | 不误收起 ✅ |
| 点击时前置条件不满足（未 dirty / 无地图 / 在飞） | `:5267` | 不到达 | 不误收起 ✅ |

**结论：收起严格等价于「服务端返回值已被采纳为当前地图已保存状态」，无任何失败/未确认分支能触发收起，也无成功分支漏收起。**

### R9.3 `finally` 中的 `renderNodeStyleControls()` 是否会重新展开

- `:5312-5316` 的 `finally` 只做三件事：复位 `state.nodeStyleSaveInFlight`、恢复按钮 `disabled`、调 `renderNodeStyleControls()`。
- `renderNodeStyleControls()`（`:5205-5219`）只写 `input.checked`、`input.value`、`output.textContent` 与两个按钮的 `disabled`，**不触碰 `.open`，也不重建 details**。
- `buildNodeStyleDisclosure()` 未对 details 设 `open`（`:1311-1313`），details 只在 `:1176-1177` mount 一次，保存流程不会重建它。

**结论：不会重新展开。** 收起后 draft 已在 `:5246` 被同步为已保存值，重开时 `renderNodeStyleControls()` 展示的是已保存取值。

## R10. 必查项 2：与既有 CSS 折叠规则（v=26）配合 — **PASS**

| 检查 | 证据 | 结论 |
|---|---|---|
| `open=false` 后内容真的不可见 | `frontend/literature-maps.css:293` `#literature-maps-view .literature-map-node-style-disclosure:not([open]) > .literature-map-node-style { display: none; }` | ✅ 与第二轮同一条规则，本轮未改 |
| 该规则特异性压过 `:285` 的 `display:flex` | (1,3,0) vs (1,2,0)，且多一个属性选择器条件 | ✅ |
| summary 仍可再次展开 | `:287` 仅 `list-style:none`（去三角）+ `cursor:pointer`，未设 `pointer-events:none`、未 disable；`:1312` summary 始终是 details 的直系子节点 | ✅ 原生 `details` 语义生效 |
| 收起后 `[open]` 高亮态是否残留 | `:289` `[open] > summary` 只在展开时生效，`open=false` 自动回落 `:287` 的白底样式 | ✅ 视觉一致 |
| 是否存在其它 CSS 覆盖 | `grep -n "literature-map-node-style" frontend/literature-maps.css` → 285-299 共 15 行，只有 `:285`（flex）与 `:293`（条件 none）两条 display 声明 | ✅ |

## R11. 必查项 3：`?v=N` 与 XSS — **PASS**

| 检查 | 命令 | 结果 |
|---|---|---|
| JS 唯一真实引用为 v=39 | `grep -n "?v=" frontend/index.html` | `:805 <script src="/assets/literature-maps.js?v=39">` ✅ |
| 断言 / fixture 同步（共 8 处，+1 真实引用 = 9 处） | `grep -rn "literature-maps.js?v=39"` | `index.html:805`、`test_frontend_map_analysis_contract.py:34`、`test_frontend_map_groups_exports.py:18,44`、`test_frontend_literature_map_contract.py:28`、`test_frontend_literature_map_expansion.py:28`、`test_frontend_map_mobile_contract.py:94,97`、`fixtures/literature_map_component.html:1120` ✅ |
| 裸数字断言同步 | `re.findall(r"literature-maps\.js\?v=(\d+)", INDEX)[-1] == "39"` | `test_frontend_map_groups_exports.py:45`、`test_frontend_map_mobile_contract.py:119` 均改为 `"39"` ✅ |
| **v=38 源码残留** | `grep -rn "literature-maps.js?v=38"`（排除 `.git`/`__pycache__`） | **源码 0 命中**；仅 `docs/sdd/reviews/*`、`docs/sdd/spec-status-changelog.md` 的历史快照（时间点记录，**不可改**）| ✅ |
| CSS 保持 v=26 | `frontend/index.html:9` + `git diff` 无 css 文件 | ✅ |
| 历史 compatibility 注释保留 | `index.html:7,796-810` 各条 Task05/Task09/Task10/Legacy/Spec037 marker 全在，本轮 diff 未删任何一行注释 | ✅ |
| 新增行无 `innerHTML` | `grep -c "innerHTML" frontend/literature-maps.js` → `0`；新增 3 行为注释 + `if (...) refs.nodeStyleDisclosure.open = false;` | ✅ |
| 语法 | `node --check frontend/literature-maps.js` | `JS_OK` ✅ |

## R12. 必查项 4：行为边界 — **PASS**

| 边界 | 证据 | 结论 |
|---|---|---|
| 「取消预览」不顺带收起 | `cancelNodeStyleDraft()`（`:5230-5234`）只做 `state.nodeStyleDraft = {...state.nodeStyle}` + 两次重绘，完全不涉 open；按钮绑定 `:1306-1309` 直连该函数，不经过 `saveNodeStyle` | ✅ 原行为不变 |
| 视口切换不改写开合 | `grep -n "\.open ="` 全文件只有 `:5251` 一处（新）；`buildNodeStyleDisclosure` 无 open 初始化；第二轮已删除的两处强制 `open=true` 未见回归 | ✅ |
| 节点样式预览（拖动滑杆）不受影响 | `updateNodeStyleDraft()`（`:5221-5228`）只更新草稿并 `renderGraph()`；收起发生在保存成功之后 | ✅ |
| 导出行为 | `hasUnappliedVisualDraft()`（`:5379-5381`）依赖 `nodeStyleIsDirty()`；保存成功后草稿已同步（`:5246`）故 dirty=false，导出不被误拦；失败路径草稿保留故仍正确拦截 | ✅ 无回归 |
| 移动端 | 收起逻辑与视口无关，读写同一 `refs.nodeStyleDisclosure`；`literature-maps.css` 的 `@media` 段内无 `.literature-map-node-style` 覆盖 | ✅ 无回归 |
| js 合同全量 | `for f in tests/frontend/*.js; do node "$f"; done` | **14/14 exit 0**（含新增用例）✅ |

## R13. 风险问答

**Q1：`updateSavedNodeStyle` 会不会在「保存失败」路径被调用，导致误收起？**
不会。该函数只在 `:5280` 与 `:5297` 两处调用，两处的前置条件分别是「PATCH 返回成功」与「重读值与草稿逐字段相等」。409、未确认、明确失败、`!state.active` 四条路径在到达之前都已 `return`（见 R9.2 表）。函数自身还有 `:5237` 的 mapId 早退保护，异步回调落在已切换地图时不会收起当前面板。

**Q2：收起后用户会不会以为数据没保存？**
有 `setStatus('节点外观已保存。')`（`:5281`）与「已重新读取核实」（`:5298`）两条成功提示作为确认反馈，收起同时 status 落地。实测新用例断言了 status 文案，避免「静默收起」。

**Q3：收起是否会让「草稿仍保留、可重试」的路径失去上下文？**
不会。所有保留草稿的路径（409 / 未确认 / 失败）都**不收起**，面板保持展开，用户可直接再点「应用外观」。这正是本轮刻意选择的边界，且被 `test_frontend_node_style_panel_collapse_on_apply.js` 用例 3/4/5 分别锁死。

**Q4：`finally` 里再渲染一次会不会把 open 又设回 true？**
不会，`renderNodeStyleControls()` 与 details 的 `open` 无交集（见 R9.3）。这是本轮最需要确认的「隐含反转」点，已逐行核对。

**Q5：CSS 未改、JS 变了，缓存是否正确失效？**
JS `?v=38→39` 已升，浏览器会重新拉取改动后的 JS。CSS 无改动故 v=26 不动是正确的最小化选择（反向「为了看起来一致而乱升版本」才是坏味道）。

**Q6：COST / 复杂度**
本轮 +3 行（含 2 行注释）、0 新增抽象、0 新增全局状态，复用既有 `updateSavedNodeStyle` 成功汇聚点而非在两个分支各写一遍（DRY 正确）。不引入模型成本相关逻辑。

## R14. 四项必守逐条判定（第三轮）

| # | 必守项 | 判定 | 核对依据（命令 + 命中行） |
|---|---|---|---|
| 1 | **DOM 契约** | **PASS** | `grep -n "literature-map-node-style" frontend/literature-maps.css` → `:285-299`；`grep -n "literature-map-node-style" frontend/literature-maps.js` → `:1277,1278,1281,1291,1300,1302,1306,1311`。本轮新增行只引用既有 ref（`refs.nodeStyleDisclosure`，来自 `:1262` 的 `literature-map-node-style-disclosure`，CSS `:286` 存在），**未新增任何 class 名**，无孤儿钩子 |
| 2 | **版本号 `?v=N`** | **PASS** | `grep -n "?v=" frontend/index.html` → `:9 css?v=26`、`:805 js?v=39`；`grep -rn "literature-maps.js?v=38"`（排除 .git/__pycache__）源码 0 命中，仅 docs 历史记录；9 处断言/fixture 一致（见 R11） |
| 3 | **XSS** | **PASS** | `grep -c "innerHTML" frontend/literature-maps.js` → `0`；新增 3 行不含任何 HTML 字符串、不含 `innerHTML/outerHTML/insertAdjacentHTML/document.write`；`node --check` → `JS_OK` |
| 4 | **CSS 作用域** | **PASS** | 本轮 **CSS 零改动**（`git diff` 无 `frontend/literature-maps.css`）；既有规则 `:293` 仍以 `#literature-maps-view` 限定，无裸标签选择器，`!important` 0 处 |

## R15. 问题清单（第三轮）

| 级别 | 问题 | 位置 | 说明 / 建议 |
|---|---|---|---|
| **MEDIUM** | 新增 js 测试**未被 git 跟踪**，且无任何 `.py`/CI 显式执行它 | `tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js` | `git ls-files --error-unmatch` 报 "Did you forget to 'git add'?"。项目对 js 合同的既定跑法是 `node tests/frontend/*.js` 全量 glob（`tests/e2e/README.md:7`、本报告 R6 第二轮命令），**工作区跑会执行、但若按文件清单提交即整文件丢失**，本轮最关键的回归护栏会静默消失。修复：`git add` 该文件，并在交付说明显式写出 `node tests/frontend/*.js`。注：这是打包/交付风险，不影响已落盘的实现正确性 |
| LOW | 用例 6「取消预览」是**恒真断言** | `tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js:279-286` | 块内只 `makeHarness` + `assert.equal(h.details.open, true)` 两次，**未调用真实 `cancelNodeStyleDraft()`**，无论实现对错都会通过。建议从源码抽 `cancelNodeStyleDraft()` 进沙箱、执行后断言 open 仍为 true（与用例 7 同一手法）。当前不掩盖本轮缺陷（用例 1-5 已覆盖收起语义），故 LOW |
| LOW | 任务描述「9 处断言/fixture」实际为 8 处测试/fixture + 1 处真实引用 | `tests/frontend/**` + `frontend/index.html:805` | 口径差异，实际同步更完整，无遗漏 |
| LOW | 第二轮 LOW「`refs.nodeStyleDisclosure` 只写不读」**已消解** | `frontend/literature-maps.js:5251` | 本轮该 ref 已成为功能读点（写 `.open`），此 LOW 关闭 |
| note | `docs/**` 与历史日志仍存 `literature-maps.js?v=38` | `docs/sdd/reviews/043-*`、`docs/sdd/spec-status-changelog.md:622` | 时间点快照，**不应修改**，不构成源码残留 |

无 CRITICAL / HIGH 问题。

## R16. 第三轮结论

**通过（Approve），可合并；1 项 MEDIUM 建议合入前顺手处理。**

- 根因修复到位：收起点放在「成功路径唯一汇聚函数」`updateSavedNodeStyle()` 的末尾，且该函数自带 mapId 早退保护，语义上等价于「已确认落库才收起」，不需要在两个成功分支各写一遍（避免漏改其一）。
- 边界选择正确：失败 / 409 / 结果未确认 / 草稿保留 / `state.active` 失效五类路径全部「保持展开」，用户重试上下文不丢；`finally` 的重渲染与 `open` 无交集，不存在「收起又被展开」的隐含反转。
- 与 v=26 CSS 规则咬合完好：`open=false` → `:not([open]) > fieldset { display:none }` 生效，summary 未被禁用，`:289` 的高亮态随 open 自动回落。
- 版本号最小化正确：只升 JS（38→39），CSS 零改动故 v=26 不动；9 处一致，源码无 v=38 残留。
- 唯一实质风险是**测试文件未跟踪**（MEDIUM），属交付完整性而非实现正确性；建议 `git add` 后按 `node tests/frontend/*.js` 全量复跑（本轮实测 14/14 exit 0）。
- 阻塞项：**无 CRITICAL/HIGH**。若项目要求「新增回归测试必须入库」作为合并门禁，则 M1 应视作合入前必办项。

### 第三轮评审摘要

| 严重级别 | 数量 | 状态 |
|----------|-------|------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | warn（测试未跟踪，合入前 `git add`） |
| LOW | 3 | note |

Verdict: **Approve** —— 实现无阻塞；MEDIUM 为交付/打包风险，一行 `git add` 即可消解，不阻塞逻辑正确性判定。

### 第三轮复现用校验命令

```bash
cd /Users/wjh/.codex/worktrees/map-usability/ResearchAgent
node --check frontend/literature-maps.js                                  # JS_OK
grep -n "?v=" frontend/index.html                                        # :9 css v=26, :805 js v=39
grep -rn "literature-maps.js?v=38" --include=*.py --include=*.html --include=*.js .   # 0 命中
grep -n "updateSavedNodeStyle\|nodeStyleDisclosure" frontend/literature-maps.js        # 1176/1262/5236/5251/5280/5297
grep -n "\.open =" frontend/literature-maps.js                           # 仅 :5251
grep -c "innerHTML" frontend/literature-maps.js                          # 0
grep -n "literature-map-node-style" frontend/literature-maps.css         # 285-299；仅 :293 为折叠隐藏
node tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js  # ok
for f in tests/frontend/*.js; do node "$f" || exit 1; done               # 14/14 exit 0
git ls-files --error-unmatch tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js  # ← 当前报错（M1）
```

---

# R17. 第四轮独立复审（人工验收阶段第四轮 UX 缺陷修复）

- **复审时间点**：main @ `6307d0db`，工作区含未提交改动（第四轮修复）。
- **复审对象**：缺陷 A「节点样式展开后不改值点『应用外观』毫无反应、详情不收起」；缺陷 B「多选模式下点『应用到 N 篇』后颜色设置面板不消失」。
- **复审方式**：只信代码事实。逐一 Read `frontend/literature-maps.js` 真实行段、`frontend/index.html`、`frontend/literature-maps.css`、fixture 与全部新增测试；实跑 `node --check`、15 个 `tests/frontend/*.js`、`.venv` 下 pytest；并在 **临时副本** 上做变异验证（未触碰业务代码）。
- **评审边界**：仅 `frontend/**`；`backend/**` 不在本轮范围（由 `backend-reviewer` 负责）。

## R18. 第四轮结论

**通过（Approve），可合并。P0 = 0，P1 = 0，阻塞 = 0。**

两个缺陷的修复在代码事实上均成立，且失败/冲突/未确认路径未被误收起（保留重试上下文）。遗留 2 项 MEDIUM（交付/测试质量问题，不影响实现正确性判定）。

### 第四轮评审摘要

| 严重级别 | 数量 | 状态 |
|----------|-------|------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 2 | warn（测试未跟踪；一处用例断言偏弱） |
| LOW | 2 | note |

Verdict: **Approve** —— 无阻塞项。MEDIUM 均为交付完整性/测试强度问题，一行 `git add` 与一处断言收紧即可消解。

## R19. 六项复审重点逐项结论

### 1. DOM 契约 — **PASS**

| 契约点 | 核对命令 | 事实 | 判定 |
|---|---|---|---|
| `.literature-map-node-style-disclosure` | `grep -n "node-style-disclosure" frontend/literature-maps.css` | CSS `:286-293`（`:293` 为 `:not([open]) > .literature-map-node-style{display:none}`）；JS `:1314` 生成 | PASS |
| `#literature-map-node-style` | 同上 | `fieldset` 由 `buildNodeStyleDisclosure()` 生成，JS `:5224` `refs.nodeStyle` 读取 | PASS |
| `.literature-map-node-style-apply` | `grep -n "node-style-apply" frontend/literature-maps.js` | `:1305` 创建、`:5225` 查询，class 两侧一致 | PASS |
| `.literature-map-color-palette[data-target="selection"]` | `grep -n "literature-map-color-palette" frontend/literature-maps.css` | CSS `:304/:305`；JS `:659-660` `dataset.target = target`；`:1188` 创建 selection 实例 | PASS |
| `#literature-map-multi-select-toggle` | 测试选择器 | `.venv/bin/python -m pytest tests/frontend/test_frontend_selection_color_palette_ux.py` → 2 passed（真实点击该 id） | PASS |
| 新增 `hidden` 是否真隐藏 | `grep -n "\[hidden\]" frontend/literature-maps.css` | `:305` `.literature-map-color-palette[hidden]{display:none!important}`，同特异性 `!important` 压过 `:304` 的 `display:grid` | PASS |
| 是否引入新 DOM class | `git diff frontend/literature-maps.js \| grep "^+" \| grep createElement/class` | 空。本轮只改 `hidden`/`.open`/`disabled`/`textContent`，**零新增 class** | PASS |

补充：`selectionPalette` 初始 `hidden = true`（`:1189`），`renderMultiSelectControls()` 是唯一隐藏入口（`renderGraph()` 首行 `:4713` 调用它），不存在两套隐藏逻辑打架。

### 2. `?v=N` 与测试断言 — **PASS**

- `grep -rn "literature-maps\.js?v=39" frontend/ tests/`（排除 `__pycache__`）→ **0 命中**；仅 `docs/` 历史报告与变更日志保留 38/39，属时间点快照，不应回改。
- `frontend/index.html:805` = `/assets/literature-maps.js?v=40` ✅
- `literature-maps.css?v=26`（`:9`）、`app.js?v=67`（`:807`）**未被误改** ✅
- `tests/frontend/fixtures/literature_map_component.html:1120` = `v=40` ✅
- 两处正则断言已升 40：`test_frontend_map_groups_exports.py:45`、`test_frontend_map_mobile_contract.py:119`（`re.findall(...)[-1] == "40"`）✅
- 静态断言实测：`'/assets/literature-maps.js?v=40' in INDEX` = True；`re.findall(r'literature-maps\.js\?v=(\d+)', INDEX)[-1]` = `40` ✅
- 6 个 py 契约文件 + fixture 与 `index.html` 版本一致，共 8 处断言/引用同步，无遗漏 ✅

### 3. XSS / 注入 — **PASS**

- `grep -c "innerHTML" frontend/literature-maps.js` → **0**；`git diff frontend/literature-maps.js | grep innerHTML` → 空。
- 本轮新增三条文案均为**静态字符串字面量**，经 `setStatus()` → `refs.status.textContent = message`（`:219-223`），无拼接、无用户输入：
  - `'颜色已保存，设置面板已收起。'`（`frontend/literature-maps.js:2121`）
  - `'颜色已保存（已重新读取核实），设置面板已收起。'`（`:2139`）
  - `'外观未变更，已收起节点样式设置。'`（`:5283`）
- `git diff | grep "console\."` → 空，无调试残留。

### 4. 行为边界 — **PASS**（本轮重点，逐条实测）

**4.1 无变更分支早退保护**（缺陷 A 修复核心）

```js
// frontend/literature-maps.js:5277-5283
if (!state.map?.map_id || !state.active || state.nodeStyleSaveInFlight) return;
if (!nodeStyleIsDirty()) {
  if (refs.nodeStyleDisclosure) refs.nodeStyleDisclosure.open = false;
  setStatus('外观未变更，已收起节点样式设置。');
  return;
}
```

- 三条件早退保护**保留在无变更分支之前**，无变更分支不可绕过 map 未选/页面失活/保存中三种前置 ✅
- 无变更分支**零网络请求**（`request()` 在其后 `:5290` 才调用）、**零 state 写入**（不碰 `nodeStyle` / `map` / `nodeStyleDraft`）✅
- 浏览器实测：`test_frontend_node_style_visibility.py::test_applying_unchanged_node_style_is_not_a_dead_click_and_collapses_the_panel` 断言 `window.__viewBodies.length == 0` 且 `status == "外观未变更，已收起节点样式设置。"`，已通过。
- `cancel` 按钮 disabled 逻辑 `!dirty || inFlight`（`:5229`）**未被误改**；只有 `apply` 去掉了 `!dirty`（`:5228`）✅ 一处改动面收得极准。

**4.2 失败 / 409 / 未确认路径仍保持展开（节点样式）**

收起点收敛在 `updateSavedNodeStyle()` 末尾（`:5262`），而该函数只有两个调用者：`:5297`（主成功）、`:5314`（重读取核实成功）。逐路径核对：

| 路径 | 是否调用 `updateSavedNodeStyle` | 是否收起 | 期望 | 判定 |
|---|---|---|---|---|
| PATCH 成功 | 是（`:5297`） | 收起 | 收起 | PASS |
| 409 冲突 → `rereadNodeStyleAfterConflict` | 否（`:5265-5277`，仅重置草稿并提示重试） | 保持展开 | 保持展开 | PASS |
| 网络异常 + 核实一致 | 是（`:5314`） | 收起 | 收起 | PASS |
| 网络异常 + 核实不一致/核实抛错 | 否（`:5316-5325`） | 保持展开 | 保持展开 | PASS |
| 明确失败（4xx/5xx 非 409） | 否（`:5327`） | 保持展开 | 保持展开 | PASS |
| `finally` 重渲染 | `renderNodeStyleControls()` 不触碰 `open` | 无反转 | 无反转 | PASS |

**4.3 `selectionPaletteDismissed` 生命周期自洽（缺陷 B 修复核心）**

- 置 `true`：仅两个**确认成功**分支 —— `:2117`（主成功）、`:2137`（核实成功）✅
- 重置 `false`：`:1801`（开启多选）、`:1814`（退出多选）、`:1838`（`toggleMultiSelectNode` 调选择）✅
- 失败 / 409 / 未确认：**不写入**，故面板保持可见 ✅ 浏览器用例 `test_selection_palette_keeps_visible_when_conflict` 断言 `palette.is_visible()` 已通过。
- 「应用后立刻又被 render 显示」漏洞：**不存在**。`applyNodeColor()` 的成功分支设 `true` → `finally` 调 `renderMultiSelectControls()`（`:2155`）读到的就是 `true` → 隐藏；`finally` 末尾的 `.literature-map-color-apply` disabled 重算（`:2156`）只改 `disabled` 不改 `hidden`。
- 「永远打不开」漏洞：**不存在**。用户只要再点任一节点触发 `toggleMultiSelectNode`（`:1838`）即重置为 `false`；开关多选（`:1801`/`:1814`）同样重置。浏览器用例已实测「收起 → 再点节点 → `palette.is_visible()`」全链路通过。
- 语义边界说明：应用成功后用户**再点色板改色**不会重开面板（面板已隐藏，点不到），需先点节点；这是既定交互（面板是「选择驱动」而非「常驻」），与 `setStatus` 文案「设置面板已收起」一致，不视为缺陷。

**4.4 是否误伤既有行为 — PASS**

- 单选节点颜色（`target='node'`）：`renderMultiSelectControls()` 只动 `refs.selectionPalette`（多选专用）；`target='node'` 走 `renderNodeDetail` 内的 `.literature-map-node-color-section .literature-map-color-palette`，不受 `selectionPaletteDismissed` 影响 ✅
- 分组颜色（`target='group'`）：`applyGroupColor()`（`:2162` 起）完全未触碰新标记 ✅
- 「取消预览」：`cancelNodeStyleDraft()` 未改，仍 `nodeStyleDraft = {...nodeStyle}` + 重渲染，不收起 ✅
- 退出多选：`:1814` 在两处清理后仍 `renderGraph()` 且 `selectionPaletteDismissed` 归 `false`，下次进入不受污染 ✅
- `MAX_MAP_NODES` 超限提示路径（`:1832-1834`）在重置语句**之前** `return`，不会误重置标记 ✅（顺序正确，不影响「收起中」状态）

### 5. 测试有效性 — **PASS**

- **执行真实源码，非复制实现**：两个新 JS 用例用 `extract(name)` 正则从 `frontend/literature-maps.js` **原样摘出函数体**（`updateSavedNodeStyle` / `saveNodeStyle` / `rereadNodeStyleAfterConflict` / `renderMultiSelectControls` / `toggleMultiSelectMode` / `toggleMultiSelectNode`），放进 `node:vm` 沙箱执行；且额外断言 `const state = {...}` 块内**必须含** `selectionPaletteDismissed` 字段，实现删字段时测试会失败而非静默通过 ✅
- **变异验证（决定性证据）**：在 `mktemp -d` 临时副本上把修复回退（palette `hidden` 去掉 `selectionPaletteDismissed`、`apply.disabled` 加回 `!dirty`）→ `test_frontend_selection_palette_dismiss_on_apply.js` **立即失败**（`strictEqual` expected true）。证明该测试真能咬住本缺陷，不是恒真断言。临时副本已删除，业务代码未改 ✅
- **py 用例断言用户可见性**：`test_frontend_selection_color_palette_ux.py` 用 `palette.is_hidden()` / `palette.is_visible()` / `getBoundingClientRect().width > 0`；`test_frontend_node_style_visibility.py` 用 `_is_hidden(computed)` + `field.is_hidden()` + `summary.is_visible()`，不是只断言 `open` 属性 ✅
- **实跑结果**：`.venv/bin/python -m pytest`（6 个 py 文件）→ **62 passed in 65.59s**；`test_frontend_selection_color_palette_ux.py` → **2 passed**；15 个 `tests/frontend/*.js` 连续 6 轮全绿 ✅
- **命名合规**：4 个新增/改动测试文件 `grep "spec0[0-9][0-9]\|task[0-9][0-9]"` → **0 命中**，文件名与函数名不含 spec/task 编号 ✅

### 6. 交付风险 — **有 MEDIUM**

- 3 个**未纳入版本控制**的新测试文件（主会话提交前须显式 `git add`）：
  1. `tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js`
  2. `tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js`
  3. `tests/frontend/test_frontend_selection_color_palette_ux.py`
- 另有 2 个与本任务无关的 untracked 目录/文件（`.playwright-cli/`、`artifacts/jd-agent-infra-capability-map.md`），**建议不要一并提交**。
- 跑法覆盖：项目对 JS 合同测试的既定跑法是 `node tests/frontend/*.js` 全量 glob（无 pytest 收集器、无 Makefile 目标），两个新 JS 文件**会被 glob 覆盖**，不属于「孤岛测试」；但**必须显式写进交付说明**，否则按文件清单提交时极易漏。py 用例由 pytest 正常收集。

## R20. 问题清单（第四轮）

| 级别 | 问题 | 文件:行 | 证据与最小修复建议 |
|---|---|---|---|
| MEDIUM | 3 个新增测试文件**未跟踪**，交付时若不 `git add` 则本轮最关键的回归护栏整文件丢失 | `tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js`、`..._selection_palette_dismiss_on_apply.js`、`..._selection_color_palette_ux.py` | `git status --porcelain` 显示 `??`。修复：提交前 `git add` 这三个文件，并在交付说明写明 `node tests/frontend/*.js` + `.venv/bin/python -m pytest tests/frontend/` |
| MEDIUM | 用例 6「失败路径不得收起」断言偏弱：块内只连调两次 `renderMultiSelectControls()`，未让 `applyNodeColor()` 的 catch 分支真实执行，「失败路径不置位标记」这一关键不变量**未被执行性验证** | `tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js:217-226` | 注释自承「失败分支不会置位收起标记（本轮实现要求）」——靠约定而非执行。修复：像 collapse 用例那样从源码抽 `applyNodeColor()`，注入 `request` 抛出 409/网络错的桩，执行后断言 `hidden === false` 且 `colorDraft` 保留（浏览器侧已有 409 用例兜底，故不升级为 HIGH） |
| LOW | 「无改动点击」用例是**首次运行偶发失败**、后续 26 次批量 + 20 次单跑均无法复现；测试无时序/随机依赖，倾向宿主资源抖动（该次与并行变异脚本同窗口） | `tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js` | 无法稳定复现，如实记录。建议 CI 中该文件跑 2 次或加 `--test-reporter` 留证，避免误判为 flaky 或被 flaky 掩盖 |
| LOW | 应用成功后用户无法**直接再调色**（面板已隐藏，需先点节点才重现） | `frontend/literature-maps.js:1787`、`:1838` | 属既定「选择驱动」交互，与文案一致，不判缺陷。若后续验收希望「保存后仍可微调」，可改为成功后仅折叠色板保留 HEX 输入 |

## R21. 四项必守逐条判定（第四轮）

| 必守项 | 判定 | 核对依据（命令 + 命中行） |
|---|---|---|
| 1. DOM 契约（class 双向存在） | **PASS** | `grep -n "literature-map-color-palette" frontend/literature-maps.css` → `:304/:305`；`grep -n "node-style-disclosure" frontend/literature-maps.css` → `:286-293`；`grep -n "node-style-apply" frontend/literature-maps.js` → `:1305/:5225`；本轮 diff **零新增 class**，新增 `hidden` 由 `:305` 的 `[hidden]{display:none!important}` 保证真隐藏 |
| 2. `?v=N` 同步递增 | **PASS** | `grep -n "?v=" frontend/index.html` → `:805 literature-maps.js?v=40`（38→40）；`:9 literature-maps.css?v=26` 未动；`:807 app.js?v=67` 未动；`grep -rn "literature-maps\.js?v=39" frontend/ tests/` → 0 命中（`__pycache__`/`docs` 除外） |
| 3. XSS（禁 innerHTML 拼用户输入） | **PASS** | `grep -c "innerHTML" frontend/literature-maps.js` → `0`；新增 3 条文案均为静态字面量经 `setStatus()`（`:219-223` `textContent`） |
| 4. CSS 作用域 | **PASS** | 本轮 **CSS 零改动**（`git diff --stat` 无 `literature-maps.css`）。核对既有规则均以 `#literature-maps-view` 前缀限定（`:286-320`），无裸全局标签选择器 |

## R22. 残留风险与建议

1. **必须 `git add` 三个新测试文件**（MEDIUM M1），否则缺陷 A/B 的回归护栏在提交后消失。这是本轮唯一有实质后果的交付项。
2. **收紧「失败路径不收起」用例**（MEDIUM M2）：当前靠注释约定，建议改为执行真实 `applyNodeColor()` 的 catch 分支。
3. 「应用成功后不直接重开色板」是产品交互选择，若下一轮验收仍有异议，按 R20 的 LOW 建议改为「折叠色板保留 HEX」。
4. 偶发首次失败未能复现（LOW L1），建议 CI 对该文件重复执行以留证，避免今后被误标 flaky。

## R23. 第四轮复现用校验命令（全部实跑通过）

```bash
cd /Users/wjh/ResearchAgent
node --check frontend/literature-maps.js                                    # SYNTAX_OK
grep -n "?v=" frontend/index.html                                          # :9 css v=26, :805 js v=40, :807 app.js v=67
grep -rn "literature-maps\.js?v=39" frontend/ tests/ | grep -v __pycache__  # 0 命中
grep -c "innerHTML" frontend/literature-maps.js                            # 0
grep -n "selectionPaletteDismissed" frontend/literature-maps.js            # :76 :1787 :1801 :1814 :1838 :2117 :2137
grep -n "nodeStyleDisclosure" frontend/literature-maps.js                  # :1179 :1265 :1314-1316 :5262 :5281
node tests/frontend/test_frontend_node_style_panel_collapse_on_apply.js     # ok
node tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js     # ok
for f in tests/frontend/*.js; do node "$f" || exit 1; done                 # 15/15 exit 0（连续 6 轮）
.venv/bin/python -m pytest tests/frontend/test_frontend_literature_map_contract.py \
  tests/frontend/test_frontend_literature_map_expansion.py \
  tests/frontend/test_frontend_map_analysis_contract.py \
  tests/frontend/test_frontend_map_groups_exports.py \
  tests/frontend/test_frontend_map_mobile_contract.py \
  tests/frontend/test_frontend_node_style_visibility.py -q                 # 62 passed
.venv/bin/python -m pytest tests/frontend/test_frontend_selection_color_palette_ux.py -q  # 2 passed
git status --porcelain                                                     # 3 个 ?? 新测试（M1）
```

> 注：系统 `python3` 无 playwright，pytest 须用项目 `.venv/bin/python`，否则 44 个用例 collection error。

- **进展日志**：`.codebuddy/agent-logs/spec-043/task-00/frontend-reviewer/20261105-172320.md`
