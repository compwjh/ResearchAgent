# Spec046 Task04 — 前端实现交接报告

- 角色 / 分支：`frontend-dev`（纯前端单端，D5） / `feature/spec-046-research-task-search`
- 范围：仅 `frontend/**` + 新增 `tests/frontend/**`；**零后端改动、零新增业务端点**。未改 spec/plan 其它文档、状态台账、`docs/sdd/reviews/**`、`backend/**`、`scripts/**`；未 commit / push / 合 main。
- 结论：实现完成、单端自测通过。**本报告不含验收结论**（验收归 task-05 / task-06）。

## 1. 改动清单

| 文件 | 关键行 | 内容 |
|---|---|---|
| `frontend/index.html` | `:218-224` | 研究视图任务列表上方新增搜索栏容器、搜索框、N/M 计数、状态/无结果/重试空态容器（复用既有 class，容器用内联 style，**未改 styles.css**） |
| `frontend/index.html` | `:814-815` | live tag `research-tasks.js?v=21` → `?v=22`；新增一行 HTML 注释保留 `/assets/research-tasks.js?v=21` 兼容标记 |
| `frontend/research-tasks.js` | `:181-190` | `state` 新增 `taskQuery` / `taskIdLookup` / `taskSearchCount` / `taskSearchDebounceTimer`；常量 `TASK_QUERY_MAX_LENGTH = 128`、`FULL_TASK_ID_PATTERN = /^[0-9a-f]{32}$/`、`TASK_LOOKUP_DEBOUNCE_MS = 250` |
| `frontend/research-tasks.js` | `:1046-1076` | D3：卡片显示完整 `任务 ID：<32位>`（`textContent`）+ 复制按钮（`dataset.copyTaskId`、`navigator.clipboard` 降级不抛错） |
| `frontend/research-tasks.js` | `:1082-1128` | 纯函数 `normalizeTaskQuery`（trim+toLowerCase+128 截断+isTaskId）、`taskQueryHaystack`（五字段）、`filterSessionsByQuery`（纯字面量 `String.includes()`，null 降级）、`isCurrentLookupRequest`、`applyTaskIdLookupResult`（竞态纯 reducer）、`copyTaskIdToClipboard` |
| `frontend/research-tasks.js` | `:1130-1228` | `renderTaskSearchCount`（`N/M` + 无结果空态）、`renderTaskSearchStatus`（loading/命中/404/网络错误 + 重试）、`resetTaskIdLookup`、`startTaskIdLookup`（requestSeq 单调递增）、`runTaskIdLookup`（反引号模板串直查 + `await selectTask(taskId, sid)`，第三参省略）、`scheduleTaskIdLookup`（250ms 防抖） |
| `frontend/research-tasks.js` | `:1230-1263` | `bindTaskSearch`（input 即触发过滤 / 完整 hex 或 Enter 触发直查 / 重试按钮）、`applyTaskQuery`（128 截断、非 hex 永不进 URL） |
| `frontend/research-tasks.js` | `:1265-1277` | `renderTaskList` 接入 `filterSessionsByQuery` 与 `state.taskSearchCount`，既有 `loadTasks` / `next_cursor` / 空态文案行为不变 |
| `frontend/research-tasks.js` | `:3805` / `:3824-3825` | `boot()` 调 `bindTaskSearch()`；`api` 导出 5 个纯函数 |
| `tests/frontend/test_research_task_search.js` | 新增 | Node 纯函数单测：B1/B2/B3/B4/B6/B7/B9/B10 |
| `tests/frontend/test_research_task_search.py` | 新增 | 8 条 pytest 静态契约：DOM id / 无 innerHTML / ?v= 契约 / URL 字面量 / 五字段 / 防抖竞态 / 404 与网络错误直查层 / D3 复制 |

未改 `selectTask` 逻辑、未改 hash 路由、未改 SSE 协议、未改 `loadTasks()` 的 `requestJson('/api/research-sessions?limit=100')` 字面量。

## 2. DOM id 清单（供 task-05 E2E）

| 稳定 id | 元素 | 用途 / 状态 |
|---|---|---|
| `research-task-search` | `input[type=search]` | 主入口；`placeholder="按目标 / ID 搜索研究任务"`、`maxlength="128"`、`aria-label`；M1 粘贴 ID / M2 输入关键字 |
| `research-task-search-bar` | `div` | 搜索栏容器（内联样式，无 class） |
| `research-task-search-count` | `span.research-status` | `N/M` 计数，`textContent = \`${matched}/${total}\``（如 `3/100`、`0/100`） |
| `research-task-search-status` | `p.research-status` | loading「正在按 ID 定位任务…」/ 命中「已定位并选中历史任务 …」/ 404「未找到该任务，请检查 ID」/ 网络「定位失败，请重试」；`hidden` 切换 |
| `research-task-search-empty` | `p.research-empty` | 「无匹配结果」空态；`hidden` 切换 |
| `research-task-search-retry` | `button.secondary-button` | 「重试」入口；仅 miss/error 显示 |
| `button[data-copy-task-id]` | 卡片内按钮 | 复制完整 `research_task_id`（E2E 可按此属性定位） |
| `button[data-task-id]`（既有） | 卡片 | 点击选中；`.research-task-card.is-selected` 为选中态 |

## 3. `window.ResearchTasks` 新增 api

`normalizeTaskQuery`、`taskQueryHaystack`、`filterSessionsByQuery`、`isCurrentLookupRequest`、`applyTaskIdLookupResult`（同时经 `module.exports` 供 Node 单测 `require`）。`selectTask` 未新增暴露（既有已在 api 内，本轮不动）。

## 4. 红绿记录（真实命令 / 退出码 / 通过数）

**RED（实现前）**
- `node tests/frontend/test_research_task_search.js` → **exit 1**，首断言 `filterSessionsByQuery must be exported`（`'undefined'` vs `'function'`）。
- `.venv/bin/python -m pytest tests/frontend/test_research_task_search.py -q` → **exit 1**，`6 failed, 2 passed`（失败集中于新增 DOM id / `?v=22` / 纯函数与直查层 marker）。

**GREEN 首轮（暴露 2 处实现细节，测试零改动）**
- `node --check frontend/research-tasks.js` exit 0；新 Node 单测 exit 0；既有 3 份契约 `25 passed` exit 0；ruff exit 0。
- 新静态契约 `2 failed, 6 passed` exit 1：① 注释含 `innerHTML` 字样；② `applyTaskQuery` 的 `renderTaskList()` 落入测试锁定的直查层区间。按「实现服从测试」修正：注释改措辞、`applyTaskQuery` 移到 `bindTaskSearch` 之后。

**GREEN 终轮（全部通过）**
- `node --check frontend/research-tasks.js` → **exit 0**
- `node tests/frontend/test_research_task_search.js` → **exit 0**，`research task search contract: PASS`
- `.venv/bin/python -m pytest tests/frontend/test_research_task_search.py -q` → **8 passed**, exit 0
- `.venv/bin/python -m pytest tests/frontend/test_paper_issue_ui_contract.py tests/frontend/test_research_session_workspace_contract.py -q` → **15 passed**, exit 0（任务指定）
- `.venv/bin/python -m pytest tests/frontend/test_frontend_management_contract.py -q` → **10 passed**, exit 0
- `.venv/bin/python -m ruff check tests/frontend/test_research_task_search.py` → **All checks passed!**, exit 0

## 5. 契约与三项自查

- **URL 契约**：`requestJson('/api/research-sessions?limit=100')` 单引号字面量保留（`test_research_session_workspace_contract.py:14`）；`requestJson('/api/research-tasks'` 单引号 legacy 未出现（`:17`）；新增直查为反引号 `` `/api/research-tasks/${encodeURIComponent(taskId)}` ``，id 先过 `^[0-9a-f]{32}$` 白名单。
- **① class ↔ CSS**：JS 复用 `research-task-card-meta`（`styles.css:3496`）、`research-open-session`（`styles.css:3510`），均在 CSS 存在；index.html 静态复用 `research-status` / `research-empty` / `secondary-button`；容器用内联 style，**未新增 class、未改 styles.css**（P1-3）。
- **② 版本号**：改了 `research-tasks.js` → live tag 升 `?v=22`（`index.html:815`）；`app.js?v=72` / `styles.css?v=70` 未改故不升（且被 `test_frontend_management_contract.py:78-80` 锁死）。
- **③ XSS**：`grep -c innerHTML frontend/research-tasks.js` = **0**；动态文本全部 `textContent` / `input.value`，卡片与空态全 `createElement`；特殊字符 / 中文 / 超长输入仅作字面量 `String.includes()` 匹配。
- **?v=21 兼容**：`index.html:814` 注释 `<!-- Compatibility marker ... /assets/research-tasks.js?v=21 -->` 使 `test_paper_issue_ui_contract.py:65` 的 `in INDEX` 断言继续成立；既有 `:813` 等大量兼容注释未动。

## 6. 剩余风险 / 阻塞

1. **M1 真实 E2E 未在本次执行**：四项指标须等 SSE 回放 seq 40 后才渲染（P1-5），本任务只做静态契约 + Node 纯函数单测；真实浏览器验证归 task-05，不得 mock 冒充。
2. **B8 刷新边界**：直查命中的历史任务经 `selectTask` 的 `upsertSessionTask` 并入列表；此后若 `loadTasks()` 刷新，会从 sessions 列表重建 `state.tasks`，该历史任务可能不再出现在卡片列表（详情/选中态仍由 `selectTask` 保持，不冲突、不重复渲染）。本期按「不改 `loadTasks()` 既有行为」保持原样，建议 task-05 覆盖该刷新场景。
3. **幂等重复直查**：`selectTask` 内部会再直查一次同一 GET（P1-4，评审已接受），未为消除它改既有逻辑。
4. **复制按钮**依赖 `navigator.clipboard`（需 secure context）；不可用时降级为中文提示、不抛错。
5. **Node 全量附加回归**：`node tests/frontend/*.js` 27 个中 5 个 `test_frontend_map_*` 失败，报错均为既有 `ReferenceError: closeGroupsPopover is not defined`，且这 5 个文件**均不加载 `research-tasks.js`**，与本改动无关、非本任务范围。
6. **无阻塞项**；未发现需要后端接口改动的情况（D5 保持）。
