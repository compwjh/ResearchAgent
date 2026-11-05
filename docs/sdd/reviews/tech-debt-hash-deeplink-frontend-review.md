# 前端评审 — hash 直达视图修复 + vm 失败路径用例补强（技术债，无 spec 编号）

- 分支：`main`（HEAD `0c3f4831` + 未提交改动）
- 评审角色：frontend-reviewer（只读评审，只落盘本报告）
- 评审范围：`frontend/app.js`、`frontend/index.html`、`tests/frontend/test_frontend_management_contract.py`、`tests/frontend/test_frontend_view_hash_deeplink.js`（新增）、`tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js` 用例 6
- 越界说明：`backend/**`（task_store / paper_discovery_store）、`deploy/start.sh` 的改动不在本角色范围，未评审，交由 backend-reviewer。
- 日志：`.codebuddy/agent-logs/spec-000/task-00/frontend-reviewer/20261105-185200.md`

## 结论

**通过（Approve）** — P0 = 0，P1 = 0。仅 2 条 P2 非阻塞建议。

修复方向正确且落地干净：初始化由无条件 `showView('chat')` 改为按 `location.hash` 同步，`#research-view` 明确交回 `research-tasks.js`；第四轮遗留的用例 6「假覆盖」MEDIUM 已通过把真实 `async function applyNodeColor()` 摘进 `node:vm` 执行并在失败路径上断言关闭。

## 六项复审逐项结论

### 1. DOM 契约 — PASS
- `MAIN_AREA_VIEW_IDS`（`frontend/app.js:5251-5260`）共 8 项，与 `index.html` 的 8 个 `.main-area` 完全一致：`chat:122` / `research-view:190` / `models-view:378` / `memory-view:388` / `kb-view:480` / `papers-view:587` / `literature-maps-view:687` / `skill-tool-view:693`。
- `HASH_VIEW_MAP`（`app.js:5329-5337`）登记 7 项，恰好覆盖除 `research-view` 外的全部视图，与注释「research-view 由 research-tasks.js 自管」一致，无遗漏也无多余键。
- 单视图互斥未被绕过：`showView` 仍在第 `5277` 行先 `hideAllMainAreas()` 再逐个显隐；`syncViewFromLocationHash` 一律经 `showView()`（`app.js:5351/5356`），不直接改 `hidden`。
- `papers` 回落逻辑保留：`app.js:5271` `const nextView = view === 'papers' && !paperState.enabled ? 'chat' : view;`，同步入口不做二次判断，语义单点维护。
- `#research-view` 确未被接管：`viewForLocationHash` 返回 `null`，`syncViewFromLocationHash` 命中 `#research-view` 直接 `return`（`app.js:5355`），既不调 `showView` 也不改任何 `.main-area` 可见性。`research-tasks.js:3570-3575` 的 `syncHistoryView` 只在 `#research-view` 时 `showView()`、否则 `closeResearchView()`，两者职责不重叠。

### 2. `?v=N` — PASS
- `frontend/index.html:807` 已由 `app.js?v=67` → `?v=68`；`tests/frontend/test_frontend_management_contract.py:80` 同步为 `?v=68`。
- `literature-maps.js?v=40`（`index.html:805`）、`literature-maps.css?v=26`（`index.html:9`）未被误改。
- 全仓 `app.js?v=67` 零残留（`grep -rn "app\.js?v=67" frontend tests` → 0 命中）。`docs/sdd/reviews/*.md` 与 `deploy/run.log` 中的 `v=67` 属历史评审记录与运行日志，非引用。
- 其它 `v=31/35/45/46/47/50/54/55/62` 断言全部落在 `index.html:806/809/810` 的 compatibility 注释块内（如 `?v=46` 见 806 行 Legacy markers），未受影响。

### 3. XSS / 注入 — PASS
- 新增行（`git diff frontend/app.js` 的 `+` 行）内 `innerHTML` / `insertAdjacentHTML` / `document.write` / `eval` 命中数 = 0。
- hash 值只做 `trim().toLowerCase()` 后经 `Object.prototype.hasOwnProperty.call()` 查表（`app.js:5342`），返回值是硬编码短视图名；未拼进 DOM、未作为选择器、未求值。未知值一律落 `null` → `showView('chat')`。
- 注：`Object.prototype.hasOwnProperty.call` 用法正确，避免了 `__proto__`/`constructor` 之类原型链键的误命中。

### 4. 行为边界 — PASS
- 未知 / 空 / `#` / `undefined` / `null` → `viewForLocationHash` 返回 `null` → `showView('chat')`；新测试用例 3（`test_frontend_view_hash_deeplink.js:169-175`）逐项覆盖。
- `hashchange` 与 `.nav-item` click 不冲突：`app.js:5361` click 处理器首行 `event.preventDefault()`，三个带 `href` 的导航项（`#research-view` / `#papers-view` / `#literature-maps-view`）的 hash 变更被拦截，浏览器不会改 hash，故不触发 `hashchange` 二次切换；其余导航项本无 `href`。
- 既有 `showView('chat')` 调用点未被破坏：`openConversation`（`app.js:3004`）、`beginDraft`（`app.js:3055`）、`openConversationFromWorkspace`（`app.js:3327`）仍是函数内直接调用，未经 hash 同步层。且 `updateConversationUrl`（`app.js:2753-2760`）只改 pathname 不改 hash，`beginDraft`（`app.js:3057`）`replaceState` 到 `/`（无 hash）→ 三者均不会因 `history` 变更触发 `hashchange`，不存在「打开会话被切走」风险。

### 5. 用例 6 有效性（重点） — PASS
- **真实函数体**：`extract('applyNodeColor')`（`test_frontend_selection_palette_dismiss_on_apply.js:226`）从 `frontend/literature-maps.js:2080` 原样抽取 `async function applyNodeColor`，与 `colorDraftMatches` / `colorTargetNodeIds` / `renderMultiSelectControls` 一同 `vm.runInContext` 执行，`h.run()`（`:318`）真实 `await` 调用。
- **四条失败路径齐备**：6a 明确失败 `status=500`（`:327`）、6b 409（`:346`）、6c `AbortError` 且核实未确认（`:366-372`）、6d 无 `status` 网络错误且核实未确认（`:392`）。
- **对照组存在**：6e（`:406-416`）在 `verifyNodeColorWrite` 返回 `confirmed: true` 时断言 `selectionPaletteDismissed === true` 且 `colorDraft === null`，证明 6a–6d 的「不置位」不是恒真。
- **断言维度完整**：`selectionPaletteDismissed` 未置位、`selectionPalette.hidden === false`（由**真实** `renderMultiSelectControls()` 渲染得出，非手工赋值）、`colorDraft` 深比较保留、`colorSaveInFlight` 已释放、`statuses` 的 tone/message 文案、409/核实分支未误入。
- **沙箱避坑**：显式注入 `Boolean`/`String`/`Map`（`:262-263`）避免 vm 内 `Boolean` 遮蔽全局；`state` 补齐 `map`/`selectedMapId`/`graph`/`groups`（`:235-248`）避免 `undefined` 早返回导致假通过。
- **原 1–5 用例完整保留**：`git diff` 显示仅删除旧用例 6 的 15 行（`:219-233` 原块），用例 1–5（`:149-220`）未改动。
- **变异验证（本次复审实测）**：
  - 在 `literature-maps.js:2122` catch 首行插入 `state.selectionPaletteDismissed = true;` → 用例在 `:334` 失败，退出码 1。
  - 还原后在「核实未确认」分支（`:2143` 前）插入同样置位 → 用例失败，退出码 1。
  - 两次均从 `/tmp` 备份还原，`git diff --stat frontend/literature-maps.js` 为空，最终重跑 `ok`（EXIT=0）。

### 6. 交付风险 — 部分需注意（非阻塞）
- **新增测试文件是 untracked**：`git status` 显示 `?? tests/frontend/test_frontend_view_hash_deeplink.js`，提交前必须 `git add`，否则新回归门禁不会进仓。
- **无孤岛门禁（P2）**：仓库没有 pre-commit hook 或统一脚本遍历 `tests/frontend/*.js`（`.git/hooks/pre-commit` 不存在，`scripts/`/`deploy/` 内无遍历命令）。新增/改写后的两份 JS 测试依赖人工单跑；建议后续补一个 `for f in tests/frontend/*.js; do node "$f" || exit 1; done` 的入口。
- **测试命名合规**：两份测试文件名与内部描述均不含 `specNNN` / `taskNN`，符合命名纪律。
- **门禁判读注意**：这些测试用顶层 async IIFE（`:323`），断言失败是「未捕获的 rejection」，进程退出码为 1 但**会先打印 `ok - ...` 行**（本次变异实测：stdout 有 `ok`，stderr 有 `AssertionError`，EXIT=1）。若 CI 只看 stdout 关键字或用了 `node xxx.js && ...` 之外的宽松判读，可能误判为通过。建议判门禁一律以退出码为准，或把 IIFE 改为 `main().catch(e => { console.error(e); process.exit(1); })` 并把 `ok` 打印移入 `main()` 末尾（P2）。

## 三项必查（本项目四项必守中与前端资源相关的三项）

| 项 | 结论 | 核对依据 |
|---|---|---|
| DOM 契约 | **PASS** | `grep -n "main-area" frontend/index.html` → 8 个 id（122/190/378/388/480/587/687/693）；`grep -n "MAIN_AREA_VIEW_IDS" frontend/app.js` → 定义于 5251、使用于 5263；两集合逐一对应，无新增 class 缺 CSS、无新增 CSS 钩子缺 JS |
| 版本号 `?v=N` | **PASS** | `index.html:807` = `app.js?v=68`；`test_frontend_management_contract.py:80` = `?v=68`；`grep -rn "app\.js?v=67" frontend tests` → 0；`literature-maps.js?v=40`(:805)、`literature-maps.css?v=26`(:9) 未动；`styles.css` 本轮未改，无需递增 |
| XSS | **PASS** | `git diff frontend/app.js \| grep "^+" \| grep -i "innerHTML\|eval\|document.write\|insertAdjacentHTML"` → 0 命中；hash 仅 `hasOwnProperty` 查表（`app.js:5342`），不落 DOM |

（第四项 CSS 作用域：本轮 `frontend/styles.css` 零改动，`git status` 中无该文件，故无新增选择器风险。）

## 残留风险 / 建议（均 P2，不阻塞）

1. **【P2】`#chat` 与刷新前的残留 hash 语义**：`#chat` 被登记进 `HASH_VIEW_MAP`，但右上角「新建对话 / 打开会话」等入口只改 pathname 不改 hash。若用户停在 `#models-view` 后点「新对话」，URL 仍带 `#models-view`，再刷新会回到模型库而非对话。这是「hash 直达」语义的固有取舍（非本次引入的回归），但与用户直觉可能不一致。建议后续在 `beginDraft` / `openConversation` 里补一次 `history.replaceState({}, '', '/c/xxx')` 式清 hash，或在文档里明确「hash 优先于会话入口」。
2. **【P2】用例 6 的 `ok` 打印时机**：见上文「门禁判读注意」，断言失败时 stdout 仍先出现 `ok - ...`，建议把成功日志移入 async 主体末尾并统一 `process.exit(1)`。

## 变更清单核对

| 文件 | 变更 | 核对 |
|---|---|---|
| `frontend/app.js` | +42/−3：新增 `HASH_VIEW_MAP` / `viewForLocationHash` / `syncViewFromLocationHash`；初始化与 `hashchange` 改走同步入口 | `node --check frontend/app.js` → OK |
| `frontend/index.html` | `app.js?v=67 → ?v=68` | 单点，唯一真实引用 |
| `tests/frontend/test_frontend_management_contract.py` | 版本断言同步 `?v=68` | 一致 |
| `tests/frontend/test_frontend_view_hash_deeplink.js` | 新增（untracked）：6 组用例执行真实实现 | `node tests/frontend/test_frontend_view_hash_deeplink.js` → ok（EXIT=0）；变异 `viewForLocationHash` 返回值 → 用例 1 失败（EXIT=1），已还原 |
| `tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js` | 用例 6 改写 +195/−9 | `node` 单跑 EXIT=0；两处变异均 EXIT=1，已还原 |

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL (P0) | 0 | pass |
| HIGH (P1) | 0 | pass |
| MEDIUM (P2) | 2 | info |
| LOW | 0 | note |

Verdict: **APPROVE** — 0 个 P0/P1 阻塞；2 个 P2 建议（刷新残留 hash 语义、用例失败时 stdout 仍打印 ok）可择机跟进。

提交前待办（非评审阻塞）：`git add tests/frontend/test_frontend_view_hash_deeplink.js`。
