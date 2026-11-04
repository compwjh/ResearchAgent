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
