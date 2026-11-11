# Spec046 Task05 — 前端单端回归报告（frontend-regression）

> 角色 / 分支：`frontend-tester` / `feature/spec-046-research-task-search` ｜ 日期：2026-11-09
> 范围：D5 纯前端单端改动，只核对 `frontend/**` 与 `tests/frontend/**`；**不跑后端 pytest**、不改业务代码、不 commit / push / 合 main。
> 本轮文件边界：仅写本报告 + 进展日志；**未改** `frontend/**`、`backend/**`、`tests/**`、spec/plan 其它文档、状态台账、reviews。
> 真实浏览器 E2E（M1/M2/M3）由主会话负责，本角色**不跑、不 mock 冒充**，只在 §6 列出待核对 DOM id 与判据。
> 进展日志：`.codebuddy/agent-logs/spec-046/task-05/frontend-tester/20261109-020643.md`

---

## VERIFICATION REPORT

```
Syntax:    PASS   node --check frontend/research-tasks.js → EXIT=0
Contract:  PASS   pytest 33/33 + 精确集合 337/337 + Node 精确集合 8/8；DOM class 5/5 在 styles.css
Version:   PASS   ?v=22 live / ?v=21 HTML 注释兼容 / styles.css?v=70 & app.js?v=72 未动
XSS:       PASS   innerHTML 命中 0；input.value / textContent / createElement；hex 白名单 + encodeURIComponent
Tests:     PASS   Node 单测 EXIT=0；pytest 指定 4 份 33 passed；精确集合 337 passed（均无既有失败）
Diff:      3 tracked files（changelog / index.html / research-tasks.js）；backend、app.js、styles.css 零改动

Overall:   单端回归 —— 通过
```

- **命中项**：B11 升版与兼容标记（`?v=22` live 唯一 + `?v=21` 注释保留，使 `test_paper_issue_ui_contract.py:65` 继续成立）；URL 字面量契约 `requestJson('/api/research-sessions?limit=100')` 保留、单引号 legacy 0；反引号模板串直查 + `^[0-9a-f]{32}$` 白名单 + `encodeURIComponent`；`input.value` 受控输入、全量 `textContent`、零 `innerHTML`；新增/复用 5 个 class 均已在 `styles.css` 存在。
- **阻塞项**：**无**。P0=0 / P1=0（本改动引入的代码缺陷为「无」）。覆盖缺口（B8 / B9 直查命中计数 / B5 运行时 mock）与 E2E 待办属「验证未覆盖」，非代码缺陷，见 §4、§6；已知既有失败见 §5，已隔离。
- **结论边界**：本「通过」仅指**单端静态 / 契约 / 单测回归**，不得据此宣称 M1/M2/M3 真机 E2E 或全量验收通过。

---

## 1. 必做核对（真实命令 / 退出码 / 通过数）

### 核对 1 — 语法与 Node 纯函数单测

```
$ node --check frontend/research-tasks.js
CMD1_EXIT=0                              # 无语法错误

$ node tests/frontend/test_research_task_search.js
research task search contract: PASS (B1/B2/B3/B4/B6/B7/B9/B10 pure functions)
CMD2_EXIT=0                              # 断言全部通过，1/1 测试文件
```

### 核对 2 — 指定 4 份前端契约 pytest

```
$ .venv/bin/python -m pytest tests/frontend/test_research_task_search.py \
    tests/frontend/test_paper_issue_ui_contract.py \
    tests/frontend/test_research_session_workspace_contract.py \
    tests/frontend/test_frontend_management_contract.py -q
.................................  [100%]
33 passed in 0.31s
CMD3_EXIT=0
```

### 核对 3 — 前端精确回归集合（自行 grep 定位）+ 既有失败隔离

集合作法：`tests/frontend/` 下引用 `research-tasks.js` 或 `index.html` 的契约测试，由 grep 精确列出（不跑全仓后端 pytest，不跑 `tests/backend/`）。

```
# 3a. pytest 精确集合（py 契约）
$ FILES=$(grep -rlnE 'research-tasks\.js|index\.html' tests/frontend --include='*.py' | sort | tr '\n' ' ')
$ echo $FILES | wc -w
35
$ .venv/bin/python -m pytest $FILES -q
........................................................................ [ 21%] ... [100%]
337 passed in 63.27s (0:01:03)
CMD4_EXIT=0                              # 无既有失败

# 3b. Node 精确集合（引用 research-tasks.js 的 .js 测试，逐文件退出码）
$ for f in $(grep -rlnF 'research-tasks.js' tests/frontend --include='*.js' | sort); do node "$f"; done
EXIT=0 tests/frontend/test_frontend_view_exclusivity.js        :: ok - frontend view exclusivity contract
EXIT=0 tests/frontend/test_frontend_view_exclusivity_runtime.js :: ok - ... (showView executed)
EXIT=0 tests/frontend/test_frontend_view_hash_deeplink.js      :: ok - ... (syncViewFromLocationHash executed)
EXIT=0 tests/frontend/test_plan_approval_select.js
EXIT=0 tests/frontend/test_report_action_race.js               :: Report action race contract: PASS
EXIT=0 tests/frontend/test_research_report_notifications.js    :: Task08 frontend contract: PASS
EXIT=0 tests/frontend/test_research_session_workspace.js       :: Task09 ... contract: PASS
EXIT=0 tests/frontend/test_research_task_search.js             :: research task search contract: PASS
CMD5：8/8 EXIT=0                         # 无既有失败

# 3c. 已知既有失败探针（test_frontend_map_*.js，Node 全量附加回归的 outliers）
$ for f in tests/frontend/test_frontend_map_*.js; do node "$f"; done
EXIT=0 tests/frontend/test_frontend_map_card_count_and_availability_badge.js
EXIT=1 tests/frontend/test_frontend_map_initial_fit_and_positions_guard.js  :: ReferenceError: closeGroupsPopover is not defined
EXIT=1 tests/frontend/test_frontend_map_view_flush_when_hidden.js          :: ReferenceError: closeGroupsPopover is not defined
EXIT=1 tests/frontend/test_frontend_map_view_keep_local_on_return.js       :: ReferenceError: closeGroupsPopover is not defined
EXIT=1 tests/frontend/test_frontend_map_view_revision_on_reentry.js        :: ReferenceError: closeGroupsPopover is not defined
EXIT=1 tests/frontend/test_frontend_map_view_save_on_leave.js              :: ReferenceError: closeGroupsPopover is not defined
CMD6：5/6 EXIT=1（逐文件），shell 整体 EXIT=0
```

- **精确集合结论**：py 契约 337/337、Node 8/8，全部 EXIT=0，**精确回归集合内无既有失败**。
- **是否本改动引入**：**否**。5 个 map 失败均为既有 `ReferenceError: closeGroupsPopover is not defined`，完整隔离论证见 §5。

---

## 2. 核对 4 — 静态核对明细（含 DOM 契约 / 版本号 / URL / XSS）

| # | 判据 | 真实命令 / 命中行 | 结论 |
|---|---|---|---|
| 4.1 | `grep -c innerHTML frontend/research-tasks.js` = 0 | `grep -cF innerHTML` → `0`（grep 进程 `EXIT=1` 是 no-match 的**正常语义**，判据是命中数 0） | PASS |
| 4.2 | live tag `research-tasks.js?v=22` | `index.html:815 <script src="/assets/research-tasks.js?v=22">`；`grep -cF` → `1`（唯一 live） | PASS |
| 4.3 | `?v=21` 以 HTML 注释兼容标记保留 | `index.html:814 <!-- Compatibility marker ... /assets/research-tasks.js?v=21 -->`；使 `test_paper_issue_ui_contract.py:65` 的 `in INDEX` 成立 | PASS |
| 4.4 | `styles.css?v=70` / `app.js?v=72` 未动 | `index.html:8` / `:818`；`git diff --name-only` 无 `styles.css`/`app.js`；`test_frontend_management_contract.py:79-80` 锁死且通过 | PASS |
| 4.5 | `requestJson('/api/research-sessions?limit=100')` 字面量仍在 | `research-tasks.js:1307`；`test_research_session_workspace_contract.py:14` 断言且通过 | PASS |
| 4.6 | 无单引号 legacy `requestJson('/api/research-tasks'` 新增 | `grep -cF "requestJson('/api/research-tasks'"` → `0`；`test_research_session_workspace_contract.py:17` / `test_research_task_search.py:46` 反向断言且通过 | PASS |
| 4.7 | 反引号模板串 `/api/research-tasks/${...}` 合规 | `grep -nF` `EXIT=0`：新增直查 `research-tasks.js:1196` `requestJson(\`/api/research-tasks/${encodeURIComponent(taskId)}\`)`；既有 `:1287`、`:3538` 同款；`test_research_task_search.py:98` 锁该字面量 | PASS |
| 4.8 | 搜索输入落 `input.value` | `research-tasks.js:1233` `applyTaskQuery(input.value, false)`、`:1237` Enter、`:1251` `input.value = limited`；`index.html:219` `type="search"` + `maxlength="128"` | PASS |
| 4.9 | 动态文本用 `textContent` | `textContent` 125 处 / `.value` 40 处；`:1050` 任务 ID、`:1138` `${matched}/${total}`、`:1160` 状态文案、`:1044` 空态全 `textContent`；`replaceChildren()` 存在（`test_research_task_search.py:34`） | PASS |
| 4.10 | 直查 id 过 `^[0-9a-f]{32}$` 白名单 + `encodeURIComponent` | `research-tasks.js:188` `FULL_TASK_ID_PATTERN = /^[0-9a-f]{32}$/`、`:1089` `.test(value)`、`:1254` 仅 `isTaskId` 才 `scheduleTaskIdLookup`、`:1196` `encodeURIComponent(taskId)`（全文件 19 处）；零非 hex 进 URL | PASS |
| 4.11 | DOM 契约：新增/复用 class 在 `styles.css` 存在 | `.research-status` 6、`.research-empty` 2、`.secondary-button` 17、`.research-task-card-meta` 2、`.research-open-session` 3；`index.html:218-224` 容器用内联 style，**未新增 class、未改 styles.css**（P1-3） | PASS |

B11 契约行号核对：`test_paper_issue_ui_contract.py:65`（`?v=21`）、`test_research_session_workspace_contract.py:14/17`（URL 字面量）、`test_frontend_management_contract.py:79-80`（styles/app live）、`test_frontend_paper_contract.py:90/104/105`（`_current_asset_version` 只读 live tag，不锁 research-tasks.js 版本）、`test_research_task_search.py:38-41`（`?v=22` + 兼容标记 + styles/app 未动）——均在 CMD3/CMD4 全绿。

`git diff --stat`：`docs/sdd/spec-status-changelog.md | 9 ++`、`frontend/index.html | 10 +-`、`frontend/research-tasks.js | 224 ++++-`（3 files, 240 insertions, 3 deletions）。`git diff --name-only` 经 grep 确认：`tests/frontend/`、`literature-maps.js`、`app.js`、`styles.css`、`backend/` **均未被修改**；新增测试 `tests/frontend/test_research_task_search.{js,py}` 为 untracked（本轮产物，非本角色改）。

---

## 3. 核对 5 — 边界 B1–B12 覆盖逐项判定

| 边界 | 覆盖来源（测试 / 代码行） | 结论 |
|---|---|---|
| **B1** 空输入 / 纯空格 | Node `test_research_task_search.js:22-26`（`''`/`'   '` 返回全量、`normalizeTaskQuery('   ').value=''`）；`research-tasks.js:1084` `trim().toLowerCase()`、`:1107` `if (!value) return list.slice()` | 覆盖 |
| **B2** 大小写与中文 | Node `:29-32`（`联邦学习`、`A`×32 大写 ID、`COMPLETED`、`2026-02`）；`:1084/:1101` 双侧 `toLowerCase()`、`:1093-1101` 五字段 haystack | 覆盖 |
| **B3** 超长 128 | Node `:35-40`（1000 字符 → `length=128`、`truncated=true`、`isTaskId=false`、不抛、过滤 0 命中）；`:188` 常量、`:1085` `slice(0,128)`、`:1250` `applyTaskQuery` 再截断；`test_research_task_search.py:58` 锁常量 | 覆盖 |
| **B4** 特殊字符 / XSS | Node `:43-49`（`<img src=x onerror=alert(1)>`、`'\"&`、`O'Reilly`、`<b>中文</b>`）；`:1109` 纯 `String.includes()` 字面量；`grep -c innerHTML=0`（§2 4.1）、`test_research_task_search.py:31-34` | 覆盖（静态 + 纯函数） |
| **B5** 404 空态 | `test_research_task_search.py:84-103`（`TASK_NOT_FOUND`/`未找到该任务`/`定位失败，请重试`/`renderTaskList() not in lookup_layer` 列表保持）；代码 `:1199-1205`（404→miss、文案、重试、不清空）；`:1164` 重试显隐 | **部分覆盖**：静态契约锁文案与「列表保持」marker，**无运行时 404 mock 断言**（Node 单测未含 B5）；行为判据由 E2E M3 真机覆盖 |
| **B6** 100 条截断走直查 | Node `:52-63`（构造 100 条不含 `TARGET_ID` → `filter`=0 命中、`normalizeTaskQuery(TARGET_ID).isTaskId=true` 走直查；31 位前缀 / 带 `z` 非 hex 不进 URL）；`:1254-1258` `isTaskId` → `scheduleTaskIdLookup` | 覆盖 |
| **B7** null `research_task_id` | Node `:66-69`（含 null 样本不抛、`s-3` 按 session_id 命中、undefined 字段降级）；`:1096` `session?.research_task_id`、`:1101` null→`''`、`:1209` sid 可能 null | 覆盖 |
| **B8** 刷新 / 选中态 | **无自动化覆盖**：Node 单测 / pytest 均无 B8；实现按「不改 `loadTasks()` 既有行为」保持原样 | **缺口**：见 §4。交接 `implementation.md §6-2` 自陈并建议 task-05 覆盖；须 E2E 真机验证刷新后查询态 / 选中态一致 |
| **B9** `N/M` 计数 | Node `:72-82`（`3/100`、`0/100`、`100/100` N=M）；代码 `:1134-1147` `renderTaskSearchCount` `${matched}/${total}`、`:1272` `state.taskSearchCount`；`test_research_task_search.py:66` 锁 marker | **部分覆盖**：前端过滤计数覆盖；「直查命中时计数 / 文案与前端过滤区分」**无独立断言**（仅静态 marker），待 E2E M1 核对 |
| **B10** `requestSeq` 竞态 | Node `:85-94`（stale `seq=1` 丢弃、latest `seq=2` 应用、future `seq=3` 丢弃、null 降级、纯函数不改入参）；代码 `:1112-1123`、`:1177-1189` 单调递增、`:1198/:1207` 守卫；`test_research_task_search.py:72-81` | 覆盖 |
| **B11** 版本契约 | `test_research_task_search.py:37-41`、`test_paper_issue_ui_contract.py:65`、`test_frontend_management_contract.py:79-80`、`test_frontend_paper_contract.py:90-105`；§2 4.2–4.4 grep 复核；CMD3/CMD4 全绿 | 覆盖 |
| **B12** 带参 hash 本期不做 | spec D4 / B12 / 「明确不做」明确不修；无新增带参 hash 测试（符合范围）；`test_frontend_view_hash_deeplink.js` 在 Node 精确集合 `EXIT=0`，确认既有 hash 路由**未被破坏** | 符合「明确不做」，无缺口 |

---

## 4. P0 / P1 缺陷列表与覆盖缺口

**P0（阻塞）缺陷：无。**
**P1（本改动引入）缺陷：无。**

> 用户要求「没有写『无』」——以上两项即为「无」。以下为**非缺陷的覆盖缺口 / 风险提示**，如实列出供主会话 E2E 与 task-06 决策，不影响本单端回归「通过」结论：

1. **B8 刷新 / 选中态无自动化覆盖**（关注度 P1）：`implementation.md §6-2` 自陈——直查命中的历史任务经 `selectTask`→`upsertSessionTask` 并入 `state.tasks`；此后若 `loadTasks()` 刷新，会从 sessions 列表重建 `state.tasks`，该历史任务可能不再出现在卡片列表（详情 / 选中态仍由 `selectTask` 保持，不冲突、不重复渲染）。本期按「不改 `loadTasks()` 既有行为」保持原样。**须 E2E 真机验证刷新场景**；非代码缺陷，属已知取舍。
2. **B9 直查命中计数、`B5` 404 运行时行为缺独立运行时断言**：task-05 文档步骤 2 期望 Node 单测含「直查命中三种计数」与 404/网络错误 mock；现有 `test_research_task_search.js` 覆盖 B1/B2/B3/B4/B6/B7/B9(过滤)/B10，`test_research_task_search.py` 以静态 marker 锁 404/网络文案与「列表保持」。行为判据由 E2E M1/M3 真机覆盖。属验证深度缺口，非本改动回归。
3. **真实浏览器 E2E 本角色未跑**（按分工由主会话负责）：M1 四项指标须等 SSE 回放 seq 40 后再断言（P1-5，`:3360` 首帧空态为既有行为），不得 mock 冒充。见 §6。
4. 工作区既有状态：`docs/sdd/spec-status-changelog.md` 有未提交改动、`tests/frontend/test_research_task_search.{js,py}` 等为 untracked、`?? docs/sdd/plans/046/` 等——均非本角色本轮所写（本轮只写本报告 + 日志），如实记录，未触碰。

---

## 5. 已知既有失败的隔离说明（对照 `git diff`）

- **失败集合**：Node 全量附加回归中 5 个 `test_frontend_map_*.js` 退出码 1，错误逐一同为 `ReferenceError: closeGroupsPopover is not defined`（CMD6 复现，见 §1 核对 3c）。第 6 个 `test_frontend_map_card_count_and_availability_badge.js` EXIT=0。
- **错误源定位**：`grep -rn closeGroupsPopover frontend/literature-maps.js` → 定义于 `frontend/literature-maps.js:2607`，调用散布 `:2627/:2633/:2653/:2720/:3056/:7903`；`tests/frontend/` 内无该字符串。即失败源自 **`frontend/literature-maps.js`** 的模块片段执行，与 `research-tasks.js` 无关。
- **与本改动无因果关系（三重证据）**：
  1. `git diff --name-only` = `docs/sdd/spec-status-changelog.md`、`frontend/index.html`、`frontend/research-tasks.js` —— **不含**任何 `tests/frontend/` 既有测试、`frontend/literature-maps.js`、`app.js`、`styles.css`、`backend/**`（`git diff --name-only | grep -E "tests/frontend|literature-maps|app\.js|styles\.css|backend/"` → 空）。
  2. `grep -lF "research-tasks.js" tests/frontend/test_frontend_map_*.js` → 空：5 个失败文件**均不加载** `research-tasks.js`，精确回归集合（§1 3a/3b）本就不含它们。
  3. `implementation.md §6-5` 已在 task-04 交接中登记同一既有失败（27 个 Node 测试中 5 个，报错一致），早于本轮验收存在。
- **py 契约层面**：`test_frontend_map_analysis_contract.py`、`test_frontend_map_groups_exports.py`、`test_frontend_map_header_actions_readability.py`、`test_frontend_map_mobile_contract.py` 均在 CMD4 精确集合内且 **337 passed**，无既有失败。
- **判定**：既有失败与 Spec046 前端改动**完全隔离**，不计入本轮 P0/P1，不阻塞单端回归「通过」。修复属 `literature-maps.js` 独立范围，须另行立项，本角色不改。

---

## 6. E2E 待核对项（本角色不跑，交主会话 M1/M2/M3 真机取证）

### 6.1 DOM id 清单（取自 `runs/task-04/implementation.md §2`）

| 稳定 id / 选择器 | 元素 | 用途 / 状态 |
|---|---|---|
| `research-task-search` | `input[type=search]` | 主入口；`placeholder="按目标 / ID 搜索研究任务"` `maxlength="128"` `aria-label`；M1 粘贴 ID / M2 输入关键字 |
| `research-task-search-bar` | `div`（内联样式） | 搜索栏容器 |
| `research-task-search-count` | `span.research-status` | `N/M`，`textContent = \`${matched}/${total}\``（`3/100`、`0/100`） |
| `research-task-search-status` | `p.research-status` | loading「正在按 ID 定位任务…」/ 命中「已定位并选中历史任务 …」/ 404「未找到该任务，请检查 ID」/ 网络「定位失败，请重试」；`hidden` 切换 |
| `research-task-search-empty` | `p.research-empty` | 「无匹配结果」空态；`hidden` 切换 |
| `research-task-search-retry` | `button.secondary-button` | 「重试」；仅 miss/error 显示 |
| `button[data-copy-task-id]` | 卡片内按钮 | 复制完整 `research_task_id`（`navigator.clipboard` 降级不抛错） |
| `button[data-task-id]`（既有） | 卡片 | 点击选中；`.research-task-card.is-selected` 为选中态 |

### 6.2 通过判据

- **M1（主案例，必须）**：服务真实启动 + 真实浏览器（Playwright/Chromium），打开 `#research-view` → 粘贴 `2eb327f2cefb5fc7b5ac60e0454294f6` → 等直查 `GET /api/research-tasks/{id}` 200（记录状态码）→ 等 **SSE 回放 seq 40 后四项指标出现再断言**（P1-5，`:3360` 首帧空态属既有行为，不得提前判失败，不得 mock）→ 断言 `median_ttft_ms≈38478.927`、`throughput_completion_tokens_per_s≈19.735`、`peak_memory_bytes≈106070016`、`failure_rate=0.0` 可见（基线 `docs/sdd/plans/045/runs/task-07/benchmark-summary.event.json`，`event_seq:40`）、`.is-selected` 选中态、`sectionHidden=false`、列表不清空、无未捕获 JS 异常。
- **M2**：输入 `goal_excerpt` 片段 / `会话` → 即时过滤（无网络等待、无 loading）+ `N/M`（如 `3/100`）；空态 `0/100` +「无匹配结果」；清空恢复 100 条；卡片文本不引入 `innerHTML`。
- **M3**：输入合法但不存在的 `00000000000000000000000000000000` → 404 友好空态「未找到该任务，请检查 ID」、列表保持、无未捕获 JS 异常。
- **失败恢复**：404 / 超时 / 网络失败 →「重试」按钮重发直查成功；期间列表与已加载结果保持原状、不 blank 视图。
- **B8 附加核对**（§4-1）：M1 命中后触发一次列表刷新，核对查询态 / 选中态 / 详情面板一致、不重复渲染。
- **产物**：截图 `docs/sdd/plans/046/runs/task-05/screenshots/M1-*.png`、`M2-filter.png`、`M3-not-found.png`，E2E 报告与取证 JSON 落 `runs/task-05/`；PNG 须真实可读（`file` 校验）。

---

## 7. 声明

- 本轮**未跑**后端 pytest 全量、**未跑**真实浏览器 E2E、**未改动**任何业务代码 / 测试 / spec / 台账 / reviews、**未** commit / push / 合 main。
- `docs/sdd/spec-status-changelog.md` 的工作区改动为既有状态（非本角色所写），如实记录、未触碰。
- 报告由 Bash heredoc 创建后经 `Read` 读回校验；进展日志逐步骤写于 `.codebuddy/agent-logs/spec-046/task-05/frontend-tester/20261109-020643.md`。
