# 2026-11-10 遗留项修复批次 · 前端/测试只读评审报告

- 评审角色：frontend-reviewer（只读）
- 基线：工作树相对 `efec3c06`（`git status` / `git diff HEAD`；暂存区为空），Refs: spec-045
- 评审范围：`frontend/**`（index.html、literature-maps.css、literature-maps.js、research-tasks.js）与 `tests/frontend/**`、T 所在的 `tests/e2e/test_research_lifecycle_e2e.py` 契约诚实性核对；版本号/文案同步的其余 `tests/frontend/*.py`
- 明确不评审：`backend/**`（reranker.py / retrieve.py / repository.py）、`deploy/**`、`scripts/**`、`docs/sdd/plans/**`、`tests/kb/**`、`tests/memory/**`、`tests/research/**`、`tests/system/**`——按文件边界交 backend-reviewer / 主会话
- 只读声明：**除本报告与 `.codebuddy` 进展日志外，未修改任何业务代码、测试、spec、数据；未执行任何 git 写操作（无 add/commit/push/reset/stash/clean）；未运行 pytest / 未启动服务 / 未跑浏览器**（只读静态核对 + `node --check` + `ast.parse` 语法校验 + grep/CSS-DOM 双向脚本核对）
- 进展日志：`.codebuddy/agent-logs/spec-045/task-00/frontend-reviewer/20261110-035335.md`
- 参考：`docs/sdd/reviews/045-acceptance-review.md`（本批次之前的验收，含 K2 真实失败证据）、`docs/sdd/reviews/20261109-frontend-ux-fix-review.md`（前一批次评审）

---

## 结论：**通过（Approve / WARNING 级提示）**

四项必守全部 PASS；无 CRITICAL、无 HIGH。K2/Q 的测试度量口径改动**不构成变相反宽**：三档阈值与 `== 8` 逐字未改，被测路径无新增 skip/xfail/sleep，`layoutIterations` 屏障确定性成立且有 `045-acceptance-review.md` 记录的真实失败证据（`assert 7 == 8`）。P 的行为变更是有产品意图的修复（留在深度研究视图），有静态+行为双层契约锁定，与 app.js 的 history guard 不冲突。T 的 `to_be_visible→to_be_hidden` 是纠正与状态机矛盾的过时期望，不是放宽。

下列 MEDIUM/LOW 为**改进建议与遗留风险记录**，不阻断合并；请主会话按需排期。

---

## 一、四项必守逐条 PASS / FAIL（逐条附核对依据）

### 1. DOM 契约 —— **PASS**

- 核对命令：`git diff HEAD -- frontend/literature-maps.css | grep "^+"` 提取新增行的类选择器 → 仅 `literature-map-canvas-meta`、`literature-map-tools`；二者在 `frontend/literature-maps.js` 均真实存在：`literature-maps.js:1124`（`sourceOptions.id='literature-map-source-options'`）、`:1163`（`currentMeta.id='literature-map-current-meta'`）、`:1346`（`Object.assign(refs, {... sourceOptions, ... projectNotice ...})`）、CSS `:58/:71/:72/:316` 均有真实规则。
- 反向核对命令：`git diff HEAD -- frontend/*.js | grep "^+" | grep -iE "className|classList|setAttribute\('class|createElement"` → **空**（本批次 JS 未新增任何 class 名，只有 `replaceChildren()` / `insertBefore()` / `replaceState()` 等既有节点操作）。
- 既有 id 零删改（权威集合对比脚本）：`REMOVED ids: []`、`ADDED ids: []`、`count old/new: 342 342`、`DUPLICATE ids: {}`。
- `aria-*`/键盘：本批次 index.html 仅 3 行 `?v=` 变化，未触碰任何 id/class/aria；`index.html:219` 的 `research-task-recover-button` 仍 `hidden aria-hidden="true"`。

### 2. 版本号 `?v=N` —— **PASS**

- 核对命令：`grep -n "?v=" frontend/index.html` + 逐行排除 HTML 注释行的脚本 → 真实生效引用 7 行与最终值**全部一致**：`index.html:8 styles.css?v=71`、`:11 literature-maps.css?v=34`、`:837 research-session-ui.js?v=3`、`:838 conversation-research.js?v=3`、`:841 research-tasks.js?v=24`、`:842 literature-maps.js?v=47`、`:844 app.js?v=73`。
- 本批次实际改动 3 个前端文件（literature-maps.css、literature-maps.js、research-tasks.js），对应 3 处 `?v=` **全部同步递增**（33→34、46→47、22→24）；fixture 同步：`tests/frontend/fixtures/literature_map_component.html:8`（css 34）、`:1135`（js 47）。
- **动态 `re.findall(...)[-1]` 断言甄别**：全库此类断言仅 4 条（`test_frontend_map_groups_exports.py:54-55`、`test_frontend_map_mobile_contract.py:119-120`），全部作用于 `literature-maps.js` / `literature-maps.css`——这两个 asset 在 INDEX 中**无历史 marker**，`findall` 结果分别为 `['47']` / `['34']`，`[-1]` 恰为生效版本，断言 `== "47"` / `== "34"` 正确。
- **历史 marker 甄别**：`research-tasks.js` 的 `findall` 为 `['2','3','9','10','24','2','3','9','11']`（`[-1]=11` 来自 `index.html:847` Spec037 marker）、`app.js` 的 `[-1]=54`、`styles.css` 的 `[-1]=53`，但**没有任何测试对这三者用 `[-1]` 断言**；旧版契约（如 `test_frontend_conversation_contract.py:64-66`、`:221-222`，`test_research_plan_cards_contract.py:86-87` 等）依赖 `index.html:7/840/843/845/846/847` 的 legacy comment marker 存活，脚本核对这些 marker **全部 IN**，未被误删。全库 grep 残留旧值断言（`v=22/46/33/72/70`）：**0 条**。

### 3. XSS —— **PASS**

- 核对命令：`git diff HEAD -- frontend/ tests/frontend/ tests/e2e/ | grep "^+" | grep -iE "innerHTML|insertAdjacentHTML|document.write|outerHTML|dangerouslySetInnerHTML|eval\("` → **空**。
- untracked 4 个新契约文件逐一 grep：仅 `test_create_task_view_contract.py:60` 出现字面量 `.innerHTML`，且是 `assert ".innerHTML" not in helper` 的**反向断言**（护栏），非使用。
- 新增的 DOM 写入全部是安全 API：`literature-maps.js:1670-1675` 用 `replaceChildren()` / `renderSelectionNotice()`（内部 `node.textContent = message`：`:1710`）/ `renderProjectOptions()`（`createElement`+`append`，`:1774-1787`）；`research-tasks.js:3814` 用 `encodeURIComponent(conversationId)` 拼接 URL；`tests/frontend/fixtures/literature_map_performance.html` 与 `literature_map_component.html` 新增行均为 `window.__*` 探针变量、`textContent`（几何测试 `:60`），无 HTML 拼接。

### 4. CSS 作用域 —— **PASS**

- 核对命令：`git diff HEAD -- frontend/literature-maps.css | grep "^+" | grep -E "\{|@media"` → 所有新增规则的选择器均带 `#literature-maps-view` 作用域前缀：
  - `:71` `#literature-maps-view .literature-map-canvas-meta { ... overflow/text-overflow/white-space ... }`
  - `:315-317` `@media (min-width: 761px) { #literature-maps-view .literature-map-tools { flex-shrink: 0; } }`
- 无裸写全局标签选择器。K1 桌面 `flex-shrink:0` **未越界**：`min-width:761px` 与既有 `max-width:760px`（`:324` 等）互补不重叠；与 `max-width:1180px`（`:318`）在 761–1180 区间共存，但后者只改 grid/detail，不改 tools 的 flex 行为，两条规则无冲突；D8 的意图（工具列不收缩、标题列承担全部收缩量）由作用域前缀限定在文献地图视图内，不影响其它页面。

---

## 二、评审要点逐条结论

### 要点 1 · 测试诚实性（最高优先）：**PASS（非变相反宽），附 2 条区分度观察**

**(a) 阈值逐字未改 —— 确认。** `tests/frontend/test_frontend_map_feasibility.py`：
- `:231` `assert final["maxInteractionDurationMs"] < 50`
- `:232` `assert final["maxFrameDurationMs"] < 50`
- `:233` `assert final["maxLayoutFrameDurationMs"] < 50`
- `:237` `assert final["maxGestureWallMs"] < 1000, final`
- `:238` `assert final["maxRenderWallMs"] < 250, final`
- `:127` `assert initial["metrics"]["layoutIterations"] == 8`

以上 6 条在 `git diff HEAD` 中**均为上下文行（无 `-`/`+`）**，逐字未改。`:286-293` 的 `thresholds` 证据字典（`max_gesture_wall_ms:1000` / `max_render_wall_ms:250` / 三档 50 / `max_layout_iterations:8`）亦未改。

**(b) 断言仍非恒真、有真实失败证据 —— 确认。** `docs/sdd/reviews/045-acceptance-review.md:107` 记录该用例 3 次连跑 1 次 FAIL；`:110` 原文：`E assert 7 == 8`，位置 `test_frontend_map_feasibility.py:114 assert initial["metrics"]["layoutIterations"] == 8`（实际 7），并明确「属布局迭代计数/时序口径的偶发漂移，**并非阈值 `< 1000` 放宽问题**」。说明 `== 8` 有真实可失败路径，非恒真。另外本批次**新增**了两处收紧断言：
- `:133` `assert 0 < initial["metrics"]["maxLayoutFrameDurationMs"] < 50`——在 reset **之前**要求非零真实观测，专门防止该指标「恒为 0 而静默通过」（对应 regression-guard 项目附加第 12 条）。
- `:204-208` reset 后 4 条 `== 0` 断言 + `renderRafCount == before_reset`——防止清桶失效（若不清桶，`snapshot()` 的 `Math.max` 仍报页面生命周期最大值，这 4 条会 FAIL）。这是**收紧**，不是放宽。
- `:219-229` 新增 `print` 把各 max* 实测值打到 stdout，便于失败时读取证据（045 报告正是靠 `Captured stdout` 定位 flaky）。

**(c) 是否新增 skip/xfail/sleep —— 被测路径无新增，且净减一个 sleep。**
- `_load_profile` 的 `page.wait_for_timeout(1000)` **被移除**，替换为 `wait_for_function(... === 8, polling=100, timeout=15000)`（`:94-98`）。
- 全批次新增行 grep `skip|xfail|sleep|wait_for_timeout|setTimeout`：命中仅为注释文字（"fixed sleep"）、`_open_browser_or_skip` 调用、以及注释里 "fixed sleep" 措辞；**无新增 `pytest.skip` / `xfail` / 新增定时 sleep** 在 K2/Q 被测路径。
- `_open_browser_or_skip`（`:76-80`）与 e2e `:22-25` skipif 为**既有**环境门槛，未改。untracked 新契约的 skip（`test_create_task_view_contract.py:73` node 不存在、`test_frontend_map_canvas_head_narrow_desktop.py:27` 浏览器阻塞）沿袭既有惯例且明确写「未将静态检查冒充...通过」，属诚实的环境降级。
- K1 fixture 把固定 `setTimeout(resolve,160)` 改为可控 gate（`:601-603`），是把"时序猜测"改为"确定性门控"，与 Q 同向。

**(d) 清桶与计时口径是否让 `maxGestureWallMs` 失去区分度 —— 有下降，但未失效，非变相放宽。**
- 清桶（`fixture:101-112` 扩展清空 `gestureWallDurations`/`renderWallDurations`/`frameDurations`/`layoutFrameDurations`）的效果是：`final` 的 `Math.max` 只反映 reset 之后那一次 burst，而不再混入 startup 阶段/前面各次交互的历史最大值。burst 仍真实产生 gesture（`final["interactionCount"] > 0`、`:216 mouse.up()` 触发 `endPointer` 的 `rAF` push，`fixture:409-411`），配合 `:230` `layoutIterations == initial`、`:239` `longTaskCount == 0`、`:240` `interactionCount > 0`、`:241` `renderRafCount > initial`，断言链仍有真实输入。
- 计时口径（`fixture:408` `lastMoveAt ?? startedAt`）：把 `pointerdown → ... → 最后一次 pointermove` 的**输入派发时间**（CDP 往返 / 合成输入 rAF 节奏）从手势墙钟里剔除，只保留「最后一次 move 到渲染响应」的耗时。理由见 `fixture:404-407` 注释，属于**度量口径修正**：CDP round-trip 与被测 SVG 渲染性能无关，计入会让 `< 1000` 受宿主/驱动抖动污染。045 报告 `:110` 的实测 `maxGestureWallMs=32.00` 也印证该值远小于 1000，原 flaky 根因是 `== 8` 时序而非该阈值。
- **观察 1（LOW）**：计时窗口变窄客观上让 `maxGestureWallMs` 的数值更小、`< 1000` 的 margin 更大，该条断言的"捕获卡死交互"灵敏度有所下降。但它**不是恒真**（burst 卡死仍会 push 大值），且 `< 250`/`< 50` 三档逐字未改、`:239` `longTaskCount == 0` 由真实 `PerformanceObserver` 驱动（`:184-195` 的 busy loop 证明其可非零）。综合不构成"变相反宽"。
- **观察 2（LOW）**：清桶后 `layoutFrameDurations` 为空且 burst 不再触发 `runBoundedLayout`（8 帧已收敛），故 `:233` `final["maxLayoutFrameDurationMs"] < 50` 实际上恒为 `0 < 50`。但新增的 `:133`（reset 前 `0 < ... < 50`）已把该指标的区分度移到 initial 段，`:207` `after_reset.maxLayoutFrameDurationMs == 0` 又锁定清桶语义，属于"断言位置迁移 + 语义补位"，不是静默失效。

**(e) `layoutIterations` 屏障确定性 —— 成立。** `fixture:454-478`：`runBoundedLayout` 每帧末（`frameDuration`/`layoutFrameDurations.push` 之后）才 `window.__layoutSettledCount = layout.iterations`（`:472`），第 8 帧且仅第 8 帧 `resolveLayoutSettled(...)`（`:476`）；`MAX_LAYOUT_ITERATIONS = 8`，`:455` 有 `>=` 早退保护，count 单调且上限恰好 8，不会出现 `9`。`snapshot().layoutIterations` 与 count 同源（`layout.iterations`，`:122`），因此 `wait_for_function("=== 8 && instanceof Promise")` 成立后 `== 8` 必然成立——这是**用确定性屏障消掉固定 sleep 的竞态**，正是 Q 的目的，且 045 报告的 `7 == 8` 证明改前确有实败。`polling=100`（timed polling）刻意不注入额外 rAF 以免饿死布局链（`py:92-93` 注释），`timeout=15000` 在极端帧停时 **fail-closed（超时报错，而非伪绿）**。注意 `instanceof Promise` 这一半条件几乎恒真（promise 已构造），但 `=== 8` 是真正的门控，不影响确定性。

### 要点 2 · P 行为变更（去掉 `openConversationFromResearch`）：**PASS（意图明确，双层契约锁定），附 1 条一致性风险**

- **"会话与聊天历史关联"语义未丢失，只是从"前台跳转"改为"后台关联"**：`research-tasks.js:3812-3817` `associateConversationInBackground()` 做三件事——`replaceState('/c/<id>#research-view')`、`state.conversationId = conversationId`、`showView()`。`state.conversationId` 在模块内有真实语义（`:976` `conversationFromUrl`、`:1077` 通知过滤、`:3687` 关联 task 查找、`:3745` 创建请求携带 `conversation_id`、`:3910` boot 解析）。URL 仍指向 `/c/<id>`，`app.js:4247-4251`（popstate）与 `:4253-4257`（reload `loadProjects().then`）按 `pathname=/^\/c\/([^/]+)$/` 调 `openConversation(...)` 恢复聊天历史——注释 `:3809-3810` 与此一致。
- **用户主动跳转语义保留**：`openConversationFromResearch`（`:3797-3804`）未删除，列表卡片「打开对应会话」按钮仍绑定（`:1155`）；`test_create_task_view_contract.py:63-66` 专门锁这一点。
- **`replaceState` 与 history guard / popstate 冲突 —— 不冲突**：`guardedHistoryMethod`（`:3887-3891`）在 `pushState`/`replaceState` 后仅当 `root.location.hash !== '#research-view'` 才 `closeResearchView()`；本 helper 的 URL **带** `#research-view`，因此不会触发隐藏。`showView()`（`:946-956`）第一行就按 `.main-area` 把 `research-view` 设为可见，且 `:955` 因 hash 已匹配不再二次 `replaceState`。`syncHistoryView`（`:3895-3898`）对 `#research-view` 也是 `showView()` 分支。行为契约 `test_create_task_view_contract.js:76-85` 复现了 guardedHistoryMethod，断言 `researchView.hidden === false`（`:157-158`）。
- **无新增隐藏/闪烁**：改前 `openConversationFromResearch → app.js openConversation → showView('chat')`（`app.js:3164`）+ `hideAllMainAreas()` 会隐藏 `#research-view`，这正是 045 报告 `:60` 记录的「`_wait_task_opened():89` element is not visible」E2E 失败根因；改后不再进入该路径。T 的 e2e `:96-97` 相应新增 `wait_for_selector("#research-view:not([hidden])")` 作为前置，属配套修正。
- **MEDIUM 风险（一致性，非阻断）**：`associateConversationInBackground` 与既有 `openForConversation`（`:3788-3795`）功能高度重叠，但**少了 `conversationFromUrl()` 与 `refreshWorkspace()` 两个调用**。后果：(1) 创建成功后 `#research-current-conversation`（`:983`/`:987`）不会刷新为新会话标题/ID，`#research-create-status`（`:3777`）虽被 `setText` 覆盖为成功文案，但「当前会话」指示可能仍是旧值；(2) 不触发 `refreshWorkspace()`（`selectTask` 会各自刷新详情，但整体一致性弱于既有路径）。建议：要么让 helper 复用 `openForConversation`（DRY，coding-standards），要么在 helper 中补 `conversationFromUrl()` 并说明为何省略 `refreshWorkspace()`；同时补一条契约断言「创建后 `#research-current-conversation` 反映新会话」。当前静态契约 `:53-60` 只断言 `#research-view`/`showView()`/`state.conversationId`，未覆盖该 DOM 文案，属契约盲区（详见要点 3 的探针侧问题）。

### 要点 3 · P 能力分支（`typeof insertBefore` + try/catch + 降级 appendChild）：**PASS（设计有据，双侧契约覆盖），附 2 条改进建议**

- **是否掩盖真实 DOM 错误**：`research-tasks.js:1228-1229` 的 `catch (_) { /* ... */ }` 是**空 catch**，会静默吞掉 `insertBefore` 抛出的任何异常（不只是预期的"cursor 被并发移除"），且 `:1231` `cursor = item` 在异常后仍推进，可能让后续 `insertBefore(item, cursor)` 以错误参照继续、产生顺序错乱而无任何日志。注释 `:1217-1220` 给出了正当理由（渲染异常冒泡到 `loadTasks`/`selectTask` 的 catch 会清空 `state.tasks` 并跳过 `loadReport`），且 `045-acceptance-review.md:93-95` 记录了 `test_report_action_race.js` 曾「稳定真实回归 4/4 rc=1」——即该降级确实修了一个真实 bug。**结论：动机与修复成立，但空 catch 无 `console.warn`/计数是诊断盲区（MEDIUM，见下）**。
- **是否破坏 D6 焦点契约与任务 B key 化 diff**：主路径（有 `insertBefore`）仍按 `ordered` 反向做最小移动，`:1227` 的 `item.parentNode !== list || (item !== cursor && item.nextSibling !== cursor)` 保证"已就位节点不移动"，`:1183-1188` 的 `existing` Map + `:1201-1207` 复用节点、`:1210-1213` 移除多余节点均保留——keyed diff 未破坏。
- **产品侧正确性有真实覆盖**：`test_research_view_stability.js` 的 fake DOM 补齐了 `nextSibling` getter（`:92-97`）、`focus()` 设置 `activeElement`（`:100`）、`appendChild`/`insertBefore` 移动时 `blurIfFocusMoved`（`:20-28`、`:59-79`），新增 3b 段（`:222-232`）断言「全量 `renderTaskList` 后焦点仍在卡片按钮上」。这是**产品侧**契约，不是只在探针侧补齐 fake DOM；且 fake DOM 现在会在移动节点时模拟真实浏览器的失焦行为，使 D6 契约真正有区分度（改前该 fake DOM 的 `focus()` 是空实现、移动不失焦，契约形同虚设——本次修复了这一点，值得肯定）。
- **降级路径的行为缺口（MEDIUM）**：`:1233-1238` 的 `appendChild` 降级**只挂载 `parentNode !== list` 的新节点，不重排已挂载但位置不符的节点**。若真实环境出现"有 `appendChild` 无 `insertBefore`"且任务顺序变化（新建任务插到最前），降级结果会把旧卡片留在原位、只把新卡片 append 到末尾，顺序错误。`test_report_action_race.js:833-838` 的 (1) 断言了 `childNodes.length === 2`（数量对），但 (2)（`:840-846`）在 `list.childNodes.length = 0` 之后**只断言 `doesNotThrow` + `state` 不清零，没有再断言降级后挂载数量/顺序**。建议在降级分支补一次正序重排（对已挂载节点用 `appendChild` 按 `ordered` 顺序重挂，会失焦但受限环境无焦点语义可权衡），或至少在契约里补 `list.childNodes.length === ordered.length` 与顺序断言，避免"探针侧只证明不抛错"。
- **空 catch 诊断（MEDIUM，与上条合并处理）**：建议 catch 内改为 `catch (error) { console.warn('[research-tasks] insertBefore degraded', error); }` 或累加一个 `state.renderDegradedCount` 供探针断言，既不冒泡污染数据层，又保留可观测性。

### 要点 4 · DOM / 可访问性契约：**PASS**

见「四项必守」第 1、2 条：既有 id 零删改（342→342，无增删/重复）；class ↔ CSS 双向核对无悬挂；aria/键盘本批次零改动；7 行 `?v=` 与全部断言期望值一致；动态 `re.findall(...)[-1]` 只用于无 marker 的 `literature-maps.*`，历史 marker 全部保留且未被误当作生效引用。`test_research_view_stability_contract.py:179-183`、`test_frontend_task_j_contract.py:179-189`、`test_frontend_button_affordance_contract.py:194-203` 等冻结断言均已同步到 24/47/34，全库无残留旧值断言（grep 0 条）。

### 要点 5 · T 断言纠正（`to_be_visible → to_be_hidden`）：**PASS（是纠正，不是放宽）**

- 依据充分且可复核：`frontend/research-tasks.js:203-209` `TASK_ACTION_STATUSES.recover = new Set(['interrupted','recovery_required'])`；`:1411-1412` `button.hidden = !available` 由 `TASK_ACTION_STATUSES[action].has(status)` 驱动；`:1423` 恢复提示条同样用 `status === 'interrupted' || status === 'recovery_required'`；`frontend/index.html:219` 该按钮默认 `hidden`。因此 **`running` 状态下 recover 按钮必须隐藏**——改前的 `to_be_visible()` 是与产品状态机矛盾的过时期望（045 报告 `:60` 的 E2E 失败正是此路径未走到/recover 期望错误的历史遗留）。改为 `to_be_hidden()` 是**收紧到正确语义**，不是放宽。spec-028 的「running 有有效 owner，恢复入口不提供」也在新注释中写明（`e2e:222-224`）。
- **新增静态契约有真实区分度**：`tests/frontend/test_research_task_actions_recover_visibility_contract.py` 的 `_action_statuses()`（`:28-43`）用正则从**真实源码**解析 `Object.freeze({...})` 字面量，`:35` 有 `assert block`（防止整块被删时静默通过，对应 regression-guard 第 12 条），`:49-54` 断言 `recover == {interrupted, recovery_required}` / `running in pause` / `running not in recover`，`:59-73` 断言 `const available = Boolean(taskId) && TASK_ACTION_STATUSES[action].has(status)`、`button.hidden = !available;`、提示条同源语义、index 默认 hidden。我用脚本复现该解析：`block found: True`，`parsed` 正确，`recover == {interrupted, recovery_required}: True`，4 条正则断言全部 `True`——契约**可真实命中且一旦白名单被加宽（如加入 running）或按钮硬编码可见即 FAIL**，不是恒真/静默失效。
- **`1 skipped` 如实记录**：`tests/e2e/test_research_lifecycle_e2e.py` 的 skip 共 5 处（`:142` LLM 不可用、`:173` 未进入运行/完成、`:176` 会话失败、`:220` 时间线未渲染、`:238` 重型阶段依赖 LLM+外部检索），均为**环境依赖**且带 `print` 诊断（`:218`）；模块级 `:22-25` skipif `RUN_E2E` 亦如实。本批次 diff **未删除/未放宽任何 skip 为 pass**，未新增 xfail；`to_be_hidden` 断言本身在 `if _status() == "running":` 分支内（见要点 7）。文档字符串（`e2e:2-9`）与 `:205-208` 注释同步更新为新语义。用户所述「1 passed, 1 skipped（skip 为 spec029/030 重型阶段依赖外部 LLM 未达）」与代码事实一致——本评审未实跑 E2E（只读），据代码与 `045-acceptance-review.md` 如实记录，不宣称"全通过"。

### 要点 6 · XSS：**PASS**

见四项必守第 3 条：新增代码零 `innerHTML` / `insertAdjacentHTML` / `document.write` / `outerHTML` / `eval`；`test_frontend_map_feasibility.py:38`（`assert "innerHTML" not in source`）、`test_frontend_literature_map_expansion.py`、`test_frontend_map_groups_exports.py`、`test_frontend_map_mobile_contract.py`、`test_create_task_view_contract.py:60` 均有反向护栏。`encodeURIComponent`（`research-tasks.js:3790/:3799/:3814`）用于 URL 拼接，安全。

### 要点 7 · 风险与遗留：**已逐项核对，均非阻断**

| 项 | 核对事实 | 结论 |
| --- | --- | --- |
| `if _status() == "running"` 分支覆盖局限 | `e2e:221-224`：仅当状态恰为 `running` 才断言 pause 可见 / recover 隐藏；`waiting_approval`/`planning`/`completed` 等状态**不进入断言**。若时间线已渲染但状态漂移，两条 expect 被跳过，用例仍可能 PASS | **LOW/MEDIUM**：确为覆盖局限。补偿是新增静态契约（白名单层面全覆盖）+ `:238` 之后的 skip 说明。建议把 `to_be_hidden()` 提到分支外（recover 在**所有非 interrupted 状态**都应隐藏），使 E2E 断言不依赖单一状态采样 |
| `e2e:212-219` 的 `pytest.skip` | 等待运行期时间线 600000ms 超时即 `pytest.skip("任务未在窗口内进入运行期")`，带 `print` 打印 `data-status` | **既有**环境降级，未改、未放宽；与 `:238` 的 spec029/030 skip 共同构成"1 skipped"来源。如实记录即可 |
| `polling=100` 极端帧停调度风险 | `py:94-98` timed polling（100ms）不注入 rAF；若 headless 页面 rAF 完全停摆，`__layoutSettledCount` 永不到 8 → 15s 后 `wait_for_function` 抛超时异常 | **fail-closed（超时报错，不是伪绿）**；相比改前 `wait_for_timeout(1000)` 后偶得 7 更确定性。LOW：仅影响极端宿主，且失败信号明确 |
| K1 桌面 `flex-shrink:0` 是否越界 | `literature-maps.css:315-317` 仅 `@media (min-width:761px)` + `#literature-maps-view .literature-map-tools`；与 `:318 max-width:1180px`、`:324 max-width:760px` 无重叠冲突；`test_frontend_map_canvas_head_narrow_desktop.py` 用 1024/900 两个宽度做真实浏览器几何断言（`after <= before + 1`）+ 静态兜底（三条截断声明必须在首个 `@media` 之前） | **未越界**。静态+几何双断言有区分度（若把截断移回 760 media，1024/900 会撑高 head 而 FAIL） |
| `tests/conftest.py`（新增，根级 autouse） | 每个用例前后 `from backend.app.platform.warmup import reset_warmup`；位于 `tests/` 根级，作用域覆盖 `tests/frontend/**` 全套 | **交叉边界提示（不属本角色评审范围）**：若 backend 包导入在纯前端契约环境失败，autouse fixture 会影响全套前端用例。请 backend-reviewer / 主会话确认 `pytest tests/frontend` 在该 fixture 下仍全绿。本评审不评其业务语义 |

---

## 三、问题清单（按严重度）

| # | 严重度 | 文件:行 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| M1 | MEDIUM | `frontend/research-tasks.js:3812-3817`（对比 `:3788-3795`） | `associateConversationInBackground()` 与既有 `openForConversation()` 重复，且省略 `conversationFromUrl()` / `refreshWorkspace()`，创建成功后 `#research-current-conversation` 可能不刷新为新会话；静态契约 `test_create_task_view_contract.py:53-60` 未覆盖该 DOM 文案 | 复用 `openForConversation` 或补 `conversationFromUrl()`；补契约断言创建后「当前会话」指示指向新 ID |
| M2 | MEDIUM | `frontend/research-tasks.js:1228-1229`、`:1233-1238` | `insertBefore` 的 `catch (_) {}` 为空、无任何日志/计数且异常后 `cursor` 仍推进；降级 `appendChild` 只挂未挂载节点、不重排已就位节点，受限环境下顺序可能错乱 | catch 内 `console.warn` 或累加 `renderDegradedCount`；降级分支按 `ordered` 正序重挂，或显式说明"降级不保证顺序"并补契约 |
| M3 | MEDIUM | `tests/frontend/test_report_action_race.js:840-846` | 竞态用例 (2) 清空 `childNodes` 后仅断言 `doesNotThrow` + `state` 不清零，**未断言降级后挂载数量/顺序**——降级路径的正确性只在"探针侧"被部分证明 | 补 `assert.equal(list.childNodes.length, 2)` 与 `ordered` 顺序断言，使降级契约与产品侧 D6 契约（`test_research_view_stability.js:222-232`）对称 |
| M4 | MEDIUM | `tests/e2e/test_research_lifecycle_e2e.py:221-224` | `to_be_hidden()` 被包在 `if _status()=="running"` 内，非 running 状态采样时断言被跳过，E2E 对该语义的覆盖依赖单次状态命中 | 把 recover 隐藏断言提到分支外（recover 在所有非 interrupted 状态都应隐藏），静态契约继续兜底 |
| L1 | LOW | `tests/frontend/test_frontend_map_feasibility.py:237` + `fixtures/literature_map_performance.html:408` | `lastMoveAt ?? startedAt` 缩小计时窗口，`maxGestureWallMs < 1000` 的区分度下降（非恒真，三档 `<50` 与 `<250` 仍逐字有效） | 在注释/报告中记录口径变更的 trade-off；如需保留"捕获卡死手势"能力，可另设一条基于 `startedAt` 的独立上界断言 |
| L2 | LOW | `tests/frontend/test_frontend_map_feasibility.py:233` | 清桶后 `final.maxLayoutFrameDurationMs` 恒为 0，`< 50` 实际恒真（区分度已由新增 `:133` initial 断言与 `:207` after_reset 断言承载） | 把 `:233` 改为 `== 0` 并注明"burst 不得重跑布局"，使断言语义与其真实行为一致、避免恒真表述 |
| L3 | LOW | `tests/frontend/test_frontend_map_feasibility.py:219-229` | 新增 `print` 诊断输出（8 个指标），生产无影响但会进 pytest stdout | 保留即可（045 报告正靠它定位 flaky）；如嫌噪音可加 `LITMAP_VERBOSE` 门控 |
| L4 | LOW | `tests/frontend/test_frontend_map_feasibility.py:94-98` | `polling=100` 在 rAF 完全停摆时 15s 超时 fail-closed | 可接受；如需更快失败可缩短 timeout 或同时监听 `__layoutSettled` promise（当前只校验 `instanceof Promise`，未真正 await） |
| L5 | LOW | `tests/frontend/test_create_task_view_contract.py:69-84`、`test_frontend_map_canvas_head_narrow_desktop.py:19-27` | 新契约的 `pytest.skip`（node 缺失 / 浏览器阻塞）是环境降级 | 属既有惯例且文案诚实；主会话在 CI 确认 node/chromium 可用即可 |

**统计**：CRITICAL 0 / HIGH 0 / MEDIUM 4 / LOW 5。

---

## 四、值得肯定的点

1. **测试诚实性守得住**：三档阈值与 `== 8` 逐字未改，且用 `045-acceptance-review.md` 里的真实失败（`assert 7 == 8`）反证断言非恒真；Q 用「帧末发布 + 第 8 帧 resolve 的屏障」替代固定 1000ms sleep，是**消除 flaky 的正解**（把"猜时序"变成"等确定信号"），K1 fixture 的 160ms → 可控 gate 同思路。新增的 reset 清零断言与 `0 < initial[...] < 50` 是**主动收紧**，且 `print` 让失败可诊断——方向与"变相反宽"相反。
2. **四项必守零违规**：7 行 `?v=` 与全部冻结断言同步；`re.findall(...)[-1]` 只用于无历史 marker 的两个 asset，legacy marker 全部保留；既有 id 342→342 零删改；XSS 新增行零命中；CSS 新增规则全带 `#literature-maps-view` 前缀且断点互补。
3. **P 修的是真回归且有双层契约**：静态契约（`test_create_task_view_contract.py`）+ 行为探针（`test_create_task_view_contract.js` 真实 `require` 产品模块、复现 `guardedHistoryMethod` 与 `openConversation` 的隐藏效果）+ `api.createTask` 探针导出（`:3944`），把「创建后不得切聊天视图」锁成可复现的因果链；「打开对应会话」按钮语义单独锁定，未误删。
4. **D6 焦点契约这次真正有了区分度**：`test_research_view_stability.js` 给 fake DOM 补 `activeElement`/`focus()`/`nextSibling` 与 `blurIfFocusMoved`，使"移动含焦点节点会失焦"被真实模拟——改前 fake DOM 的 `focus()` 是空实现，该契约形同虚设。这是产品侧正确性补齐，不是只糊探针。
5. **T 是纠正而非放宽**：`to_be_hidden()` 与 `TASK_ACTION_STATUSES.recover`、`button.hidden=!available`、index 默认 hidden 三方一致；新增静态契约从源码解析白名单并带 `assert block` 防静默失效，能捕获"白名单加宽/按钮硬编码可见"的回归。E2E 的 `1 skipped` 及 5 处环境 skip 如实保留，未伪称通过。
6. **几何回归有真实度量**：`test_frontend_map_canvas_head_narrow_desktop.py` 用 1024/900 两档窄桌面 + `getBoundingClientRect().height` 前后对比（`<= before+1`），配静态兜底，比只断言 CSS 字符串更有说服力。
7. 语法校验：`node --check` 5 个改动/新增 JS 全 OK；`ast.parse` 21 个改动/新增 PY 全 OK。

---

## 五、ECC Summary Format

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 4     | info   |
| LOW      | 5     | note   |

**Verdict: APPROVE（WARNING 级提示）** — 无 CRITICAL/HIGH；4 个 MEDIUM 为契约覆盖与诊断可观测性改进建议，不阻断合并。四项必守 4/4 PASS；K2/Q 未构成变相反宽；P 与 app.js history guard/popstate 不冲突；T 为纠正过时期望；XSS 零命中。

### 四项必守逐条 PASS/FAIL（汇总）

| # | 项目 | 结论 | 核心依据 |
| --- | --- | --- | --- |
| 1 | DOM 契约 | **PASS** | CSS 新增类选择器 `literature-map-canvas-meta`/`literature-map-tools` 在 `literature-maps.js:1124/1163/1346` 有渲染；JS 无新增 class；id 342→342 零增删/零重复 |
| 2 | 版本号 `?v=N` | **PASS** | `index.html:8/11/837/838/841/842/844` 7 行与最终值全一致；3 处改动全递增；动态 `findall[-1]` 仅用于无 marker 的 `literature-maps.*`；legacy marker 全存活、旧值断言 0 残留 |
| 3 | XSS | **PASS** | 全部新增行 grep `innerHTML/insertAdjacentHTML/document.write/outerHTML/eval` 为空；新增 DOM 写入均为 `textContent`/`createElement`/`replaceChildren`/`encodeURIComponent` |
| 4 | CSS 作用域 | **PASS** | `literature-maps.css:71/316` 均带 `#literature-maps-view` 前缀；`@media(min-width:761px)` 与 `max-width:760px` 互补、`max-width:1180px` 无冲突；无全局裸标签选择器 |

---

## 六、只读声明

本次评审**仅新增**本文件与进展日志 `.codebuddy/agent-logs/spec-045/task-00/frontend-reviewer/20261110-035335.md`；未修改任何业务代码、测试、fixture、spec、数据；未执行任何 git 写操作；未运行 pytest、未启动后端、未跑浏览器（结论基于 `git diff HEAD` 全量阅读、Read/Grep 脚本化双向核对、`node --check`、`ast.parse` 静态语法校验，以及 `docs/sdd/reviews/045-acceptance-review.md` 中已落盘的历史执行证据）。E2E「1 passed, 1 skipped」为委托方提供的执行结果，本报告据代码如实转录，未独立复跑、未宣称"全通过"。
