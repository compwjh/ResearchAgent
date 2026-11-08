# 2026-11-09 前端 UX 修复全套改动 · 只读评审报告

- 评审角色：frontend-reviewer（只读）
- 评审范围：frontend/**（index.html、app.js、styles.css、literature-maps.css、literature-maps.js、research-tasks.js、research-session-ui.js、conversation-research.js）以及 tests/frontend/** 契约诚实性核对
- 明确不评审：backend/**、.gitignore、docs/sdd/specs/043-*、tests/memory/**、tests/research/**、tests/e2e 业务断言（交 backend-reviewer / 主会话）
- 基线：working tree（git diff，暂存区为空），HEAD 1b26c76c
- 只读声明：仅新增本报告与 .codebuddy 进展日志；未修改任何业务代码、测试、spec、数据；未执行任何 git 写操作；未运行 pytest（只读静态核对 + node --check + ast.parse 语法校验）

## 结论：需修改（BLOCK）

按本项目四项必守「违反即判 CRITICAL」的纪律，DOM 契约存在 1 处 FAIL，必须修复后合并；另有 2 个 MEDIUM 竞态与残留风险建议同批处理。
影响说明：该 CRITICAL 项的实际用户可见影响是项目记忆加载失败时状态文字不变红；失败文案、aria-live 与 data-state 仍正常，功能不阻断，无安全或数据损失，修复成本 1 行。

## 一、四项必守逐条 PASS / FAIL

### 1. DOM 契约 —— FAIL（1 处）

- 脚本化双向核对：从两份 CSS 的 diff 新增行提取 56 个类选择器，检查是否在 frontend/*.js + index.html 出现，结果 MISSING_IN_JS_OR_HTML 为空。但这是假阴性：memory-project-documents-status 是靠 HTML 中同名 id 命中的，并非 class。
- 语义级 Grep 双向核对（class 属性、className 赋值、classList.add 三种形式）：frontend/ 全目录命中 NONE。Grep 该字符串共 3 处命中：frontend/styles.css:497（CSS 类选择器）、frontend/index.html:462（class 为 conversation-status、id 为同名）、frontend/app.js:74（按 id 查询）。
- 事实链：frontend/styles.css:497 定义 #memory-view .memory-project-documents-status[data-state="error"] 红色规则；frontend/index.html:462 元素 class 是 conversation-status；frontend/app.js:3840-3846 只设置 data-state，从未添加该类。故该规则永不匹配，错误态红色强调失效。
- 修复建议：把选择器改为 #memory-view #memory-project-documents-status[data-state="error"]，或在 HTML 该元素补 memory-project-documents-status 类；并补一条契约测试断言 CSS 选择器与 DOM 实际类名一致（现有测试只断言 data-state，未覆盖视觉钩子）。
- 其余契约 PASS：JS 新增或修改的 class（btn-outline、truncate、hash-inline、clamp-3、is-loading、research-records-empty、memory-project-doc-*、literature-map-tag-filter-*、research-main-tab(s)、research-tabpanel）在 styles.css / literature-maps.css / index.html 内联样式中均有真实规则；CSS 新增的其余 55 个类选择器在 JS/HTML 均有真实渲染。
- 既有 id 零删改（权威集合对比）：REMOVED_IDS 为空、DUPLICATE_IDS 为空；ADDED_IDS 仅 11 个新 id（主 tab 5 个、项目记忆 6 个）。创建表单从页面底部整体迁入 tab panel，全部既有表单 id 不变。
- aria 与键盘：主 tab 的 role=tablist/tab/tabpanel、aria-controls、aria-labelledby、aria-selected、tabindex 齐全（index.html:225-230）；Arrow/Home/End/Enter/Space 均有绑定（research-tasks.js:896-941）；标签 chip 有 aria-pressed，+N 更多有 aria-haspopup/aria-expanded 与 Esc、点外部关闭、焦点归还；切换只改 hidden/aria-selected/tabIndex，行为探针断言节点引用不变（tests/frontend/test_research_view_stability.js:153-155）。

### 2. 版本号 ?v=N —— PASS

- 验证命令 grep 实际引用（src 或 href 指向 /assets/ 且带 ?v=）命中 7 处：frontend/index.html:8 styles.css?v=71（原 70）、:11 literature-maps.css?v=32（原 31）、:837 research-session-ui.js?v=3（原 2）、:838 conversation-research.js?v=3（原 2）、:841 research-tasks.js?v=22（原 21）、:842 literature-maps.js?v=46（原 45）、:844 app.js?v=73（原 72）。
- 7 处实际引用全部递增；注释内的 legacy compatibility markers 不是实际引用，不计。
- 用户已说明 literature-maps.css 在任务 F 之后还会再 bump 到 33、由主会话另行处理，按要求不判缺陷（见第三部分合入前提醒）。

### 3. XSS —— PASS

- 命令：git diff -U0 -- frontend/ 取新增行，grep innerHTML / insertAdjacentHTML / document.write / outerHTML → NONE；console.log → NONE。
- 新增动态文本全部走 textContent / el.title / setAttribute：formatShortHash 只做 slice 与省略号拼接，withTooltip 只写 title 与 aria-label（app.js:1-14、research-tasks.js:11-24、literature-maps.js:210-224、conversation-research.js:8-22）。
- 全量 innerHTML 均为存量且已净化：app.js:1784 / :6814 走 renderMarkdown（app.js:6442 注明先 DOMPurify 后 innerHTML）、kb-inspection.js:188 写 sanitizedHtml；本轮未改这些路径。
- 新增行为探针含恶意串逐字断言：tests/frontend/test_frontend_memory_projects.js:161-172（img/onerror 恶意串逐字进 textContent、title 保留全文、DOM 桩不含 innerHTML）、tests/frontend/test_frontend_short_text_helpers.js:66-70（含标签字符的全文只进 title/aria-label）。

### 4. CSS 作用域 —— PASS

- 脚本提取两份 CSS diff 新增行中的裸选择器（不以 # 开头）：仅 .btn-outline 及其 hover/focus-visible/disabled 变体、.truncate、.hash-inline、.clamp-3，以及两条 @media；全部是本次新造的公共 class 工具类，不是全局标签选择器，不会命中既有页面元素。
- 其余新增规则全部带 #memory-view / #research-view / #literature-maps-view 前缀；任务 F 修复位于 @media (max-width:760px) 内且限定 #literature-maps-view（literature-maps.css:325-327）。
- 说明：全站公共类按需求本就需跨视图复用，与项目既有的 .send-button / .secondary-button 裸类惯例一致；本次未新增任何裸标签选择器。

## 二、需求符合性（7 项 + 任务 F）逐条核对

| # | 需求 | 落地事实（文件:行） | 判定 |
|---|---|---|---|
| 1 | 顶部主 tab、表单迁入创建 tab、切换不重建 DOM | index.html:225-230 与 :230-249 创建面板、:250 任务面板；research-tasks.js:896-941 activateResearchTab/bindResearchTabs 只改 hidden/aria-selected/tabIndex；创建成功切回 tasks（:3696）、导航点击保持 tasks（:3750-3755）、chat research 模式跳 create（:3748） | PASS |
| 2 | 防闪烁 | research-tasks.js:3499 generation token、:3571/:3591/:3598 各 await 分支守卫、:1097-1135 updateTaskCard 原地更新、:1175-1225 keyed diff、:3436-3437 applyEvent 单卡、:3611-3650 静默刷新 | 部分（见问题 2、3） |
| 3 | 空态与耗时 | index.html:255 暂无研究任务、:269 暂无执行记录；research-session-ui.js:82-101 与 research-tasks.js:1004-1017 双路径均对 0/负/亚 100ms 返回 —；hydrateSession 改 console.warn + data-error + state.hydrateErrors（:1227-1260） | PASS |
| 4 | 全站按钮可用态 | styles.css:4293-4320 .btn-outline 四态；index.html 26 处、app.js 29 处、research-tasks.js 11 处、literature-maps.js 60 处；.secondary-button 基类（styles.css:23）逐字未改；#papers-view .secondary-button:disabled（:1925-1928）与可用态明显区分 | PASS |
| 5 | 长文本简版 + 悬浮全文 | styles.css:4310-4312 truncate/hash-inline/clamp-3；4 个 JS 内 formatShortHash/withTooltip；报告正文保持 max-height:560px + overflow:auto（test_frontend_button_affordance_contract.py:136-140 明确校验未粗暴截断） | PASS |
| 6 | 标签 Set 多选 OR + 选中优先前 3 + +N 更多下拉 | literature-maps.js:101-105、:1682 OR、:1977-2010 收起态、:2011-2160 下拉浮层（Esc / pointerdown 点外部 / 离开视图 closeTagFilterMenu(false)） | PASS |
| 7 | 项目记忆列表 | index.html:452-464 默认可见区块；app.js:3806-3906 独立 state + generation + loading/error/empty 三态 + 全量渲染 + 点击 switchMemoryDocument('project', id)；:5743 showView('memory') 刷新；OCC 未动 | PASS（视觉钩子见问题 1） |
| F | 375px canvas-meta 折行撑高 | literature-maps.css:325-327 在 @media (max-width:760px) 内单行截断；用例已恢复 PASSED | PASS |

## 三、问题清单（按严重度）

### [CRITICAL] DOM 契约：CSS 新增类钩子在 HTML/JS 无对应，项目记忆错误态红色样式永不生效

- 文件：frontend/styles.css:497、frontend/index.html:462、frontend/app.js:74、frontend/app.js:3840-3846
- 问题：CSS 用类选择器 .memory-project-documents-status[data-state="error"] 定义红色错误态，但 HTML 该元素的 class 是 conversation-status（只有同名 id），JS 按 id 查询且只设置 data-state，从未添加该类；规则永不匹配。
- 影响：失败文案仍可见、aria-live 与 data-state=error 正常，仅错误态缺少红色强调；不阻断功能，无安全或数据损失。
- 建议：把选择器改为 #memory-view #memory-project-documents-status[data-state="error"]，或在 HTML 元素补 memory-project-documents-status 类；并补一条契约测试断言 CSS 选择器与 DOM 实际类名一致。
- 判定依据：本项目四项必守第 1 条「CSS 里新增的钩子也要在 JS/HTML 中有对应」，违反即 CRITICAL（详见第一部分双向核对命令与命中行）。

### [MEDIUM] selectTask 的 finally 未纳入 generation 守卫

- 文件：frontend/research-tasks.js:3604-3608（对照 :3499 generation 声明、:3571/:3591/:3598 各 await 分支守卫）
- 问题：finally 无条件调用 setDetailLoading(false) 与 renderRecordsEmptyState()；try 内 :3586 与 catch :3598 都有 generation 守卫，唯 finally 没有。
- 场景：快速点任务 A 再点 B（taskGeneration 自增），A 的迟到响应进入 finally，提前移除 B 的 is-loading 骨架，并基于混合态计算空态提示；B 数据到达前出现瞬时视觉抖动。
- 建议：finally 内用 if (generation === state.taskGeneration) 包住两个渲染调用；selectTaskInFlight 的 target 判断保持不变。
- 影响：瞬时 UI 抖动，最终状态正确、不丢数据；但从评审要点 3 看，generation token 未覆盖全部异步收尾分支。

### [MEDIUM] 静默刷新未校验选中任务是否仍在列表中，外部删除后详情与报告残留过期数据

- 文件：frontend/research-tasks.js:3637、:1274-1283
- 问题：有选中时直接 return state.tasks；loadTasks() 仅在 currentConversationSessionId 匹配且选中项缺失时 unshift 保底（:1276-1280），其它情况下 state.tasks 会丢掉被删任务，但详情、报告、矩阵、引用与 SSE 连接全部不清（旧实现在此路径会 full reset）。
- 场景：任务在别处被删除后点「刷新任务」，列表卡片消失（keyed diff 会移除），详情区仍显示该任务报告，SSE 仍连旧任务。
- 建议：静默返回前校验 state.tasks 是否仍含 selectedTaskId / selectedSessionId；缺失时清理详情或给出可见提示并重新选择。

### [LOW] 按钮 class 断言由逐字放宽为二选一正则

- 文件：tests/frontend/test_frontend_map_header_actions_readability.py:249
- 问题：原断言逐字要求 secondary-button，新正则允许带或不带 btn-outline；删掉 btn-outline 仍会通过。
- 说明：放宽理由与任务 C 一致、文案仍逐字校验，且新增 test_frontend_button_affordance_contract.py:91-99 的 UNDECORATED 全量断言更强地兜底，整体测试诚实性不因此失效；不阻断。
- 建议：改为显式冻结 secondary-button btn-outline。

### [LOW] 近似恒真弱断言

- 文件：tests/frontend/test_frontend_task_d_contract.py:134
- 问题：仅断言字符串 error 在 app.js 中存在，几乎必然为真，不校验任何行为；同测试其它断言（项目记忆加载失败、memoryProjectDocumentsState.error）为实断言。
- 建议：删除，或改为断言具体调用 memoryProjectDocumentsStatus.setAttribute('data-state', 'error')。

### [LOW] renderTaskList 全量路径无条件重排复用节点，可能导致键盘焦点丢失

- 文件：frontend/research-tasks.js:1216（selectTask 在 :3529 调用全量 renderTaskList）
- 问题：ordered.forEach 对每个已复用节点再次 appendChild；移动含焦点元素会使其失焦，用户点击任务卡片后焦点可能落到 body。
- 建议：仅当顺序或成员变化时做最小 insertBefore 移动，或切换后恢复焦点。此项为键盘可达性观察，建议实机验证。

## 四、合入前提醒（按用户指示不计入缺陷）

- literature-maps.css?v=33 待主会话 bump：frontend/index.html:11 当前为 ?v=32，而 tests/frontend/test_frontend_button_affordance_contract.py:201、test_frontend_task_d_contract.py:188、test_frontend_literature_map_contract.py:29、test_frontend_map_groups_exports.py:52 等断言已锁定 ?v=33，夹具 tests/frontend/fixtures/literature_map_component.html:8 也已是 33。用户说明任务 F 之后还会再 bump 到 33、由主会话另行处理，本评审不判缺陷；但该 bump 完成前相关契约测试会红灯，且用户可能拿到缓存旧 CSS，合入前必须补齐。
- 未运行 pytest：只读评审不改数据与缓存，仅执行 node --check（5 个业务 JS + 4 个新增测试 JS 全通过）与 ast.parse（31 个 Python 契约文件语法通过）；测试 PASS/FAIL 状态以主会话执行结果为准。
- 边界声明：backend/**、.gitignore、spec 043 裁决留痕、tests/memory 与 tests/research 后端测试均未评审，交 backend-reviewer / 主会话。

## 五、值得肯定的点

1. 既有 DOM 契约稳：python 集合对比证明 331 个既有 id 零删除、零改名、无重复；创建表单整体迁入 tab panel 且所有 form id 保留；e2e 只补一句 page.click 切 tab，未改业务流程。
2. 主 tab 实现克制：activateResearchTab 只改 3 个属性，不 replaceChildren / createElement；键盘导航（Arrow/Home/End/Enter/Space）+ tabindex + aria-controls/selected 齐全；创建成功自动切回任务 tab、导航点击保持任务 tab、chat research 模式直达创建 tab，行为分工清晰。
3. 防闪烁主体正确：keyed diff 用 taskId/sessionId 建索引复用节点，updateTaskCard 只写变化的文本/状态，徽章原地更新（行为探针 :184-188 断言节点引用与徽章对象不变）；applyEvent 只刷选中卡；SSE 每帧不再全量重建；loadTasks 有独立 taskListRequestGeneration。
4. 耗时修复无死角：sessionUI.durationText 与 research-tasks 本地 fallback 两条路径都改，行为探针覆盖空对象/0/null/同刻/亚秒/新字段/13 秒共 8 个边界；0.0 秒不再出现。
5. 长文本克制：只处理 hash/版本号/元数据/摘要，报告正文保持 560px 限高内滚，新增契约专门断言不粗暴截断；用户可控文本全程 textContent + title/aria-label，探针含 XSS 恶意串逐字断言。
6. 样式统一无侵入：以追加类覆盖 4 个视图约 126 处真实按钮，.secondary-button 基类逐字不动（新契约 :87 冻结），四态齐全，#papers-view disabled 灰态与可用态明显区分；两份 CSS 新增规则除 4 个公共工具类外全部视图作用域限定。
7. 标签多选实现完整：Set + OR + 再点取消 + 选中优先前 3 + 已选计数 + +N 更多下拉 checkbox + Esc/点外部/离开视图三层清理；执行级探针验证并集（t1 与 t2 命中任一即返回 m1/m2/m3 而非交集 m3）与选中优先顺序 t4/t5/t1。
8. 测试诚实：4 个新增 JS 探针均用 node:vm 从真实源码 sliceFunction 抽取函数执行（非影子实现），含全量列出、XSS 逐字、点击接线、空态/失败态断言；flaky 性能用例 test_frontend_map_feasibility.py 未改动、未固化 skip、未放宽阈值；测试新增行零 skip/xfail；夹具桩补齐（closeTagFilterMenu / loadMemoryProjectDocuments / listTagIds / closeGroupsPopover）均对应真实新增或 HEAD 基线既有调用（git show HEAD 核实 7 处）。
9. 记忆治理隔离：独立 memoryProjectDocumentsState + generation，不触碰 memoryState / OCC / 409；失败态可诊断（message + HTTP 状态 + console），错误时不当作无数据；点击复用现有单文档编辑器。

## 六、验证命令与依据（全部只读）

- git diff --stat 与各文件 git diff：改动范围与逐行证据
- git diff -U0 -- frontend/ 新增行 grep innerHTML/insertAdjacentHTML/document.write/outerHTML → NONE；console.log → NONE
- grep -n '?v=' frontend/index.html：7 处实际引用全部递增
- node --check 5 个业务 JS + 4 个新增测试 JS → ALL_JS_SYNTAX_OK
- python ast.parse 31 个 Python 契约文件 → PY_SYNTAX_OK
- python id 集合对比（git show HEAD:frontend/index.html）→ REMOVED_IDS 为空 / DUPLICATE_IDS 为空
- git diff --name-only -- tests/frontend/test_frontend_map_feasibility.py → 空（flaky 用例未改）
- git diff -U0 -- tests/ 新增行 grep skip/xfail/threshold → NONE
- Grep 双向：memory-project-documents-status 作为 class → NONE；56 个新增 CSS 类选择器逐一核对，仅此 1 处为 id 假阴性已语义复核

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 1     | warn   |
| HIGH     | 0     | pass   |
| MEDIUM   | 2     | info   |
| LOW      | 3     | note   |

Verdict: BLOCK — 1 CRITICAL（DOM 契约）须修复后合并；2 个 MEDIUM 建议同批处理。修复后四项必守可全部 PASS。

- 评审报告：docs/sdd/reviews/20261109-frontend-ux-fix-review.md
- 进展日志：.codebuddy/agent-logs/spec-043/task-00/frontend-reviewer/20261109-054731.md
