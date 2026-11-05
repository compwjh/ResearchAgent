# Spec043 三项 UX 缺陷修订 · 跨端验收评审（Acceptance Review）

| 项 | 值 |
|---|---|
| 评审者 | `tester`（跨端验收总控） |
| 角色 | 跨端验收总控（ECC `e2e-runner` / `verification-loop`）；只读验收，**未改任何业务代码 / 测试 / spec / 台账** |
| 模型 | Deepseek-V4.1-Flash（按 `spec:444` 分派） |
| 分派方式 | 主会话按 spec 043「2026-11-05 用户确认与冻结范围」分派；汇总 `backend-tester` / `frontend-tester` 单端报告，并独立执行跨端集成验收 |
| 验收基线 | 工作区当前快照（2026-11-06 02:0x–03:0x），未提交改动 17 文件 + 6 个新前端测试 |
| 依据材料 | `docs/sdd/specs/043-literature-map-topic-exploration.md:424-458`（冻结范围）；`043-ux-defects-requirement-review.md`；`043-ux-defects-tech-review.md`；`043-ux-defects-backend-review.md`；`043-ux-defects-frontend-review.md`；`043-ux-defects-backend-regression.md`；`043-ux-defects-frontend-regression.md`；`043-ux-defects-live-e2e.md` |
| 本评审日志 | `.codebuddy/agent-logs/spec-043/task-00/tester/20261106-020844.md` |
| 评审时间 | 2026-11-06（Asia/Shanghai） |

---

## 一、验收结论

# 结论：**通过（PASS）**

- **P0 = 0，P1 = 0**，无阻塞项。
- 4 项冻结范围全部实现，且用户可见行为在**真实运行服务**上复核成立。
- 「明确不做」6 条**全部未被突破**。
- 全量回归数字**由本验收独立复跑确认**（非仅引用单端报告）：后端 `240 passed`、前端 `396 passed / 0 failed`、node vm `24 PASS / 0 FAIL`、ruff 4 条与 `HEAD` 基线逐条一致。
- 残余 **P2 共 7 条**（去重后），性质为窄口径可观测项、测试覆盖建议与接口面登记，**均不阻塞**。

> 一处**须登记的非阻塞接口面变化**：`GET /api/literature-maps/{id}/export` 的 `map.view_settings` 新增 `view_initialized` 键（纯新增，向后兼容）。详见 §五 P2-1。该项不影响本次验收通过，但需在台账/人工验收材料中说明。

---

## 二、逐项验收点

### 验收点 1 · 4 项冻结范围全部实现且用户可见行为正确 —— **通过**

| 子项 | 结论 | 证据（文件:行 / 实测） |
|---|---|---|
| ① 卡片只显当前篇数（`可用 32 篇`） | **通过** | 后端：`backend/app/api/routes_literature_maps.py:347-353` 单次批量取 `node_counts` 后 `{**item.to_dict(), "node_count": node_counts.get(...)}`；`backend/app/literature_maps/infrastructure/store.py:579-602` `active_node_counts`（占位符参数化、`removed_at IS NULL`、`m.owner_id=?`、`GROUP BY`、空 ids 提前 return）。前端：`frontend/literature-maps.js:1808-1816` `mapCardNodeCount()` 先取 `node_count`，缺失/非数回落 `requested_count`，注释明写「两者不同也不显示『目标 N』」。实测：`GET /api/literature-maps` 7 张地图逐张与 `GET /{id}/graph` 活动节点对照 → **7/7 全等，MISMATCH=0**；目标地图 `node_count=32`、`requested_count=20`（未混用）。真实浏览器 innerText：`… 可用 32 篇`（`043-ux-defects-live-e2e.md:36-38`）。 |
| ② `partial` 徽标在已有活动节点时显示「可用」 | **通过** | `frontend/literature-maps.js:1820-1834` `mapCardStatusBadge()`：仅当 `status==='partial'` **且** `node_count>0` 时 `badge.textContent = mapStatusLabel('ready')`，并保留 `data-status="partial"`（筛选契约不变）、加 `data-availability="usable"` 走绿色样式，`title`/`aria-label` 用 `PARTIAL_MAP_CARD_NOTICE`（`:17`，文案与 `spec:429` 逐字一致）。`styles.css`/`literature-maps.css:39` 有对应 `[data-availability="usable"]` 规则（无死样式）。`node_count=0` 的地图仍显示「部分完成」（实读 `ra_maps.json` 有 2 张 `node_count=0`，与 `spec:429`「已有活动节点时」限定一致，不越界）。**未改后端 `status` 值**：`git diff backend/` 新增行全量列举无任何 `status` 写入。 |
| ③ 知识库跳转定位（缺陷 A） | **通过** | `frontend/app.js:5106-5190`：`selectKbJumpTarget()` **优先 `data-document-id`、兼容 `data-paper-id`**（`:5116-5125`）；`applyKbJumpFocus()` 做 `scrollIntoView({block:'center'})` + `focus()` + `kb-item-jump-target` 类，**并校验 `isConnected` 拒绝旧节点**（`:5145-5152`）；`consumePendingKbJump()` 在 `renderKbPapers()` 末尾消费 `pendingKbPaperId`（`:5160-5166`）；未命中 `/ 缺 ID` 各有明确文案（`:5107-5108`、`:5181-5190`）。冻结范围要求「**仅滚动+高亮，不自动展开详情**」→ `applyKbJumpFocus` 无任何展开/打开动作，符合。`research-tasks.js` **未改动**（`git status` 空）而同入口受益。实测（真实 Chromium，`live-e2e:52-65`）：`highlighted=true, focused=true, rectTop=467, inViewport=true`，修复前对照为 `rectTop=10505, inViewport=false`（假阳性已消除）。 |
| ④ 地图视图保存（缺陷 B/C：`scale 2.3333` 跨视图保持） | **通过** | `frontend/literature-maps.js:7178` `setActive(false)` 改为 `flushPendingViewSave()`（不再仅 `clearTimeout`）；`saveView` 放行离开时的一次写：`:5384` `(!allowInactive && !state.active)`、`:5393` `if (!viewport.valid && !allowInactive) return false`、`:5425-5427` `(state.active \|\| allowInactive)` 落地并清 dirty、置 `viewSavedOnce`；切回不覆盖本地 dirty：`:7164-7172` `keepLocalView` → `selectMap(..., {keepLocalView:true})`；`resolveInitialFitPending()` `:2553-2567` 改**显式标记**判定（`view_initialized===true` / `viewSavedOnce` → 绝不 fit；`===false` / 无 viewport / 极小缩放 → fit），不再以 `(0,0,1)` 猜测定论。实测（活服务只读复核）：`GET /api/literature-maps/0baabeae…` → `revision=288`、`view_initialized=True`、`viewport={scale:2.3333333333333335, x:-597.6964087529543, y:-597.7034759967261}`，与 `live-e2e:105-111` 记录的切回 DOM `scale(2.3333333333333335)` 完全一致。 |

### 验收点 2 · 「明确不做」未被突破 —— **通过（6/6 条守住）**

| # | 「明确不做」项（`spec:433`） | 结论 | 证据 |
|---|---|---|---|
| 1 | 不改后端 `status` 值 / 语义 | **守住** | `git diff backend/` 新增行全量列举仅 4 组：`node_counts` 组装、导出白名单 3 行、`active_node_counts` 方法、`view["view_initialized"]=True`；无任何 `status` 赋值。实测列表返回 `status` 全为原值 `partial`。 |
| 2 | 不改 `PATCH /view` 请求体与 409 策略 | **守住** | `routes_literature_maps.py:74-84` `MapViewRequest` 字段 = `expected_revision / positions / viewport / filters / layers / label_mode / node_style`，`extra="forbid"` 保留，**无 `view_initialized`**；前端 PATCH body（`literature-maps.js:5404-5411`）同 5 键；409 映射（`routes:290-293`）与 `store.py:636/656` `revision conflict` 未改。 |
| 3 | 不改导入／索引流程与 `/api/kb/*` | **守住** | `backend/app/api/routes_kb.py` 未改（`git status` 仅 `routes_literature_maps.py`）；kb 相关改动只有 2 个**新增前端测试文件**。 |
| 4 | 不改 Task11 预览／批次／分析逻辑 | **守住** | `git diff` 未触及 batch/preview/analysis 相关实现；前端 396 passed 全绿兜底（`043-ux-defects-frontend-regression.md:207-219`）。 |
| 5 | `research-tasks.js` 未改 / 无 localStorage 草稿 / 知识库列表分页、搜索未改 | **守住** | `git status --porcelain frontend/research-tasks.js` → 空；`git diff frontend/ \| grep '^+' \| grep -c localStorage` → **0**；`git diff frontend/app.js \| grep -c "kbPage\|kbSearch\|PAGE_SIZE"` → **0**。 |
| 6 | 不改节点拖拽与「整理间距」交互、不改其他视图切换逻辑 | **守住** | 缺陷 B 的修复集中在 `setActive` / `saveView` / `initialFitPending` 判定（`:7160-7185`、`:5383-5445`、`:2553-2567`），拖拽与「整理间距」交互函数无改动；视图互斥逻辑（`showView`）仅消费 `setActive`，未改分支结构。 |

### 验收点 3 · 真实 E2E 证据完整性 —— **通过**

| 要求 | 结论 | 证据 |
|---|---|---|
| 含请求 / 响应 / 实体 ID / 最终状态 / 产物路径 | **通过** | `043-ux-defects-live-e2e.md`：地图 `0baabeae7268429c9f7e4de8098ae1d0`、节点 `065389f0f0b64acda6c5a043cc9b6269`、文档 `1b967ed8638e46569d36e3f6565c51eb`；请求 `GET /api/literature-maps`、`PATCH …/view`、`GET …/graph`；最终 `revision 288 / view_initialized true / node_count 32`；产物 6 个 `/tmp/ra_*.json` + 浏览器快照。 |
| 产物真实存在且内容一致 | **通过（本次独立复核）** | 逐一 `ls`：`/tmp/ra_maps.json`(78979B→实读 7 maps)、`ra_graph.json`、`ra_index.html`、`ra_map_after.json`、`ra_map_after2.json`、`ra_map_final.json`(2033B)、`.playwright-cli/page-2026-11-05T18-05-56-340Z.yml` **均存在**；`ra_maps.json` 实读目标项 `partial/requested 20/node_count 32/rev 286`，`ra_map_final.json` 实读 `revision 288`、`viewport scale 2.3333333333333335`、`view_initialized true` → **与报告逐字一致**。 |
| `/api/health` 200 | **通过** | `curl -o /dev/null -w %{http_code} /api/health` → **200**。 |
| 静态资源实际加载 `app.js?v=70` / `literature-maps.js?v=42` / `literature-maps.css?v=27` / `styles.css?v=68` | **通过** | `curl /` → 非注释行实际引用恰为这 4 条（其余 `v=31..62` 命中均来自 `index.html` 历史兼容注释行，非实际加载）；`live-e2e:15` 记录浏览器 `script[src]`/`link` 实际返回值同此四项。 |

### 验收点 4 · 全量回归数字 —— **通过（本验收独立复跑）**

| 项 | 报告数字 | 本次复跑 | 结论 |
|---|---|---|---|
| 后端 `pytest tests/literature_maps` | 240 passed（`backend-review` 第二轮 / `backend-regression` R2） | `.venv/bin/python -m pytest tests/literature_maps -q` → **240 passed**，EXIT=0 | 一致 |
| 前端 `pytest tests/frontend` | 396 passed / 0 failed（`frontend-regression` 第二轮） | collect → 396；分 5 批 84 / 85 / 78 / 106 / 43 → **396 passed / 0 failed**，各批 EXIT=0 | 一致 |
| node vm `tests/frontend/test_*.js` | 22 PASS / 0 FAIL（报告） | 实跑 **24 个文件，JS_PASS=24 / JS_FAIL=0** | 通过（数量多于报告：后续新增 `test_frontend_kb_jump_rerender.js` 等，全绿） |
| ruff（改动 3 文件） | 4 条既有 SIM 告警 | `ruff check` 改动文件 → **Found 4 errors**；`git show HEAD:` 版本同规则集 → **同为 4 条**（行号因新增 25 行下移） | 确认非本次引入 |

补充核对（项目高频回归点）：`app.js?v=70` / `literature-maps.js?v=42` / `literature-maps.css?v=27` / `styles.css?v=68` 四项在 `frontend/index.html` 与 `tests/frontend/` 的 py 断言及 fixture 中**全部同步命中**（`management_contract:79-80`、`map_analysis_contract:34-35`、`expansion:28-29`、`map_contract:28-29`、`map_groups_exports:18-19/43-44`）→ 版本号链路自洽，缓存问题解除。

### 验收点 5 · P0/P1 = 0，残余 P2 逐条列出且不阻塞 —— **通过**

- P0 = **0**、P1 = **0**（后端复审第二轮 Approve、前端复审第二轮 APPROVE 无保留、本次独立复核一致）。
- 残余 P2 **7 条**，见 §五。全部为窄口径可观测项 / 测试覆盖建议 / 接口面登记，**无阻塞**。

### 验收点 6 · 十项人工验收准备度检查 —— **通过（10/10）**

见 §四。要求「≥9 通过」→ 实际 **10 项全通过**。

---

## 三、命令 / 退出码 / 通过数汇总

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest tests/literature_maps -q` | 0 | **240 passed** in 10.85s |
| 2 | `ls tests/frontend/test_*.py \| sed -n '1,9p' \| xargs .venv/bin/python -m pytest -q` | 0 | 84 passed in 8.91s |
| 3 | 同上（第 10–18 个文件） | 0 | 85 passed in 63.82s |
| 4 | 同上（第 19–27 个文件） | 0 | 78 passed in 50.71s |
| 5 | 同上（第 28–36 个文件） | 0 | 106 passed in 1.87s |
| 6 | 同上（第 37–45 个文件） | 0 | 43 passed in 0.76s |
| 7 | `.venv/bin/python -m pytest tests/frontend -q --collect-only` | 0 | **396 tests collected** |
| 8 | `for f in tests/frontend/test_*.js; do node "$f"; done` | 0 | **JS_PASS=24 / JS_FAIL=0**（24 个文件） |
| 9 | `.venv/bin/ruff check <改动 3 文件>` | 1 | Found **4 errors**（与 `HEAD` 基线同 4 条，既有债） |
| 10 | `ruff check /tmp/ruffbase/`（HEAD 版本导出） | 1 | Found **4 errors**（基线对照） |
| 11 | `curl -o /dev/null -w %{http_code} /api/health` | 0 | **200** |
| 12 | `curl /` + 非注释行版本号解析 | 0 | `app.js?v=70`、`literature-maps.js?v=42`、`literature-maps.css?v=27`、`styles.css?v=68` |
| 13 | `GET /api/literature-maps` × `GET /{id}/graph` 逐张对照 | 0 | 7/7 相等，**MISMATCH=0** |
| 14 | `GET /api/literature-maps/0baabeae…` | 0 | `revision 288` / `view_initialized True` / `viewport scale 2.3333333333333335` |
| 15 | `GET /api/literature-maps/0baabeae…/export` | 0 | schema `literature-map-export-v2`，`view_settings` 含 `view_initialized: True` |
| 16 | `git status --porcelain frontend/research-tasks.js` | 0 | 空（未改） |
| 17 | `git diff frontend/ \| grep '^+' \| grep -c localStorage` | 1 | **0** 命中 |
| 18 | `grep -rn '^<<<<<<<\|^>>>>>>>' frontend/ tests/frontend/` | 1 | **0** 命中（无冲突标记） |

**汇总**：后端 **240**、前端 **396**、node vm **24**、ruff **4 既有** → 全部与单端报告一致或更严格（node vm 实为 24 而非 22，且全绿）。

---

## 四、十项人工验收准备度检查

| # | 检查项 | 结论 | 依据 |
|---|---|---|---|
| 1 | 无 P0 / P1 | **PASS** | P0=0、P1=0（本次复核 + 两端复审结论一致） |
| 2 | API E2E 成功 | **PASS** | 4 条端到端链路（列表 `node_count`、graph 对照、KB 跳转、视图保存）在活服务上成立 |
| 3 | 关键产物存在 | **PASS** | 6 个 `/tmp/ra_*.json` + 1 个 `.playwright-cli` 快照全部实存，内容与报告逐字一致 |
| 4 | 可复现步骤齐备 | **PASS** | `live-e2e:138-144` 5 步逐步点击（硬刷新 → 卡片 → 跳转 → 缩放后切走切回 → 失败恢复），含「等待条件」（1800ms / 列表加载完成） |
| 5 | 失败恢复路径齐备 | **PASS** | ①`live-e2e:144` 旧数字/旧样式 → 先硬刷新并核对 `?v=`，再看状态栏区分「列表加载失败」与「未找到该文档」；②视图保存失败 → `saveView` catch 置 `positionsDirty=true` + 状态文案「视图保存失败：…请重新打开地图后再保存」(`literature-maps.js:5437-5443`)；③409 → 「地图版本或作业状态已变化，请重新读取后重试」(routes:293) |
| 6 | 自然语言／主路径入口可用 | **PASS** | 知识库跳转由地图节点详情按钮「在知识库中查看」触发（真实点击，非内部函数）；卡片、徽标、缩放按钮均为主界面元素 |
| 7 | 部署提示与实际一致 | **PASS** | 报告称部署版本 `app.js?v=70` / `literature-maps.js?v=42` / `literature-maps.css?v=27` / `styles.css?v=68`，与 `curl /` 实读、`index.html` 源码、`index.html` 断言三方一致 |
| 8 | 版本号／缓存一致性（项目回归点） | **PASS** | 四项 `?v=` 已升级且 index ↔ fixture ↔ 5 个 py（8 处断言）全同步；`literature-maps.css?v=26` 源码 0 命中 |
| 9 | class ↔ CSS 双向（项目回归点） | **PASS** | `data-availability="usable"`（`literature-maps.js:1824`）↔ `literature-maps.css:39`；`kb-item-jump-target`（`app.js:5106`）↔ `styles.css:804 / :809`。无死样式、无缺失样式 |
| 10 | 无 XSS 新增／无冲突标记 | **PASS** | 前端 376 新增行中 `innerHTML/insertAdjacentHTML/outerHTML/document.write` **0 命中**；新增动态文本全走 `textContent` / `setAttribute`；冲突标记 0 命中 |

**通过数：10 / 10**（要求 ≥9）。

---

## 五、阻塞项与 P2 清单

### 阻塞项（P0 / P1）

**无。** 0 个 P0，0 个 P1。

> 说明：后端第一轮 P1-1（`service.py` 越表 + 导出面未测）已由两条新增导出用例闭合（`backend-review` 第二轮 §核实 1，含两次反向验证 + `cp` 复原 + `git diff --numstat` 一致性证明），本次活服务 `GET /export` 实测确认 `view_initialized` 已出现在导出中，与测试断言一致。

### 残余 P2（7 条，均不阻塞）

| 编号 | 问题 | 证据 | 建议 | 阻塞 |
|---|---|---|---|---|
| P2-1 | **导出 JSON 新增 `view_initialized` 键**（接口面变化，属纯新增、向后兼容，但需登记） | `service.py:2584-2587`；实测 `GET /{id}/export` → `view_settings` 含 `view_initialized: True` | 在台账 / 人工验收材料登记「导出 JSON 新增该键」；已完成补测 | 否 |
| P2-2 | flush 的 409／网络失败后 `positionsDirty` 残留，`state.active===false` 期间 `scheduleViewSave` 不再排期 → 需下次进入后靠 `applyMapPayload` 新 revision + 用户再动一次才自愈 | `literature-maps.js:5437-5443`、`:5356` | `setActive(true)` 分支补 `if (state.positionsDirty \|\| state.viewDirty) scheduleViewSave();` 显式补偿 | 否 |
| P2-3 | `consumePendingKbJump` 保留 pending 期间，若列表仍有 `indexing`，2.5s 轮询每次重渲染都会再滚动一次（目标不变，体验为「保持可见」） | `app.js:5160-5166`、`:6528` | 可在 `consumePendingKbJump` 记录「已定位目标」跳过重复 scroll，仅保留高亮 | 否 |
| P2-4 | `jumpToKnowledgeBase` 返回的 promise 在两处调用点未被消费 | `app.js:5183`、`:4938`、`:5054` | 调用点加 `void` 前缀表达「故意忽略」；已确认无 unhandled rejection（`loadKbPapers` 内部 catch + `then(_, onRejected)`） | 否 |
| P2-5 | `allowInactive` 放行 + 「测量值不进 PATCH payload」的因果链**无单测覆盖**，仅靠 E2E 验证 | `literature-maps.js:5366-5393`；`grep flushPendingViewSave tests/` → 0 命中 | 补用例：断言 `allowInactive` 时 `viewport.valid===false` 仍发 1 次 PATCH，且 body **不含** `width/height/cssScale` | 否 |
| P2-6 | `state.viewSavedOnce` 为**会话级**标记、不按地图重置 → 会话内保存过 A 图后，再打开「无 `view_initialized` 的旧数据 + 极小缩放」图 B 会停在不可读视图 | `literature-maps.js:110`、`:2560` | 改按地图记录（如 `Set<mapId>`）或在切到不同 mapId 时复位 | 否 |
| P2-7 | `active_node_counts` docstring 未写明 ids ≤100 约束；`view_initialized` 单向单调语义未写入函数 docstring；`_stored_view_json` 直连 `sqlite3.connect` 与其它测试风格不一 | `store.py:579-585`、`store.py:671-672`、`test_map_view_initialized_flag.py:45-51` | 补 docstring 一行 / 注释说明；测试风格统一（含 P2-6、P2-7 可合并为「文档 + 测试卫生」一次性清理） | 否 |

> 上表 7 条已对 `backend-review`（P2-1/2/3/4）、`frontend-review`（P2-1/2/3/4）、`live-e2e`（4 条）去重合并。

---

## 六、VERIFICATION REPORT

```
VERIFICATION REPORT（Spec043 UX 缺陷修订 · 跨端验收）
=====================================================
Build:      PASS   （.venv/bin/python -c "import backend.app.main" → import ok；活服务 /api/health 200）
Types:      N/A    （Python 项目无独立类型门禁，非本阶段要求）
Lint:       PASS*  （改动 3 文件 4 条 SIM 告警；与 git show HEAD: 基线 4 条逐条一致 → 既有债，非本次引入）
Tests-BE:   PASS   （240/240 passed，tests/literature_maps）
Tests-FE:   PASS   （396/396 passed，tests/frontend，分 5 批；node vm 24/24 passed）
Security:   PASS   （SQL 全参数化 + owner 隔离 + removed_at 过滤；前端 376 新增行 0 处 innerHTML 类危险 API；无新密钥）
Integration:PASS   （列表 node_count ↔ graph 活动节点 7/7 相等；view_initialized=true 且 viewport scale 2.3333 跨视图保持）
Diff:       17 文件改动 + 6 新增前端测试（backend 3 / frontend 5 / tests 8+…）

P0: 0    P1: 0    P2: 7（均为窄口径 / 测试覆盖 / 文档卫生，不阻塞）

Overall:   READY —— 通过，可提交架构师签字
```

---

## 七、备注

1. 本评审**未修改任何代码、测试、spec 或台账**；一切结论基于 `Read` / `Grep` / `git diff` 与实跑命令的事实。
2. 本次独立复跑发现两处与单端报告的数字差异，已如实记录：① node vm 实为 **24** 个文件（报告写 22），全绿；② 前端 `?v=` 已由报告冻结的 69/41 升至 **70/42**，本次 396 passed 是在**最新**代码上取得。
3. `git status` 显示本批改动**尚未提交**，`backend/` 与 `frontend/` 均在工作区。建议架构师签字后由主会话统一提交。
4. 后端 P2-1（导出新增键）虽为纯新增且向后兼容，仍建议在人工验收材料中一句话说明，避免下游导出消费者疑问。

---

## 八、架构师签字

> 本栏由 `architect` 子代理后续填写，`tester` 不代签。

| 项 | 内容 |
|---|---|
| 架构师结论 | （待填写：同意 / 有条件同意 / 不同意） |
| 条件与要求 | （待填写） |
| 签字人 | （待填写） |
| 签字时间 | （待填写） |
