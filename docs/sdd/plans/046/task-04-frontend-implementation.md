> 关联：[spec-046](../../specs/046-research-task-search.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02、03（两份评审均通过）；当前状态：`已完成`（2026-11-09 `frontend-dev` 红→绿，报告 `runs/task-04/implementation.md`）

# Task 04 — 前端实现与自测（D1-B 直查 + D2 过滤 + D3 复制）

## 状态与一句话目标

`待执行`。在 `frontend/**` 内实现研究视图搜索：按目标 / ID 过滤已加载 ≤100 条，按完整 32 位 hex `research_task_id` 直查并选中任意历史任务，卡片显示并可复制完整 ID；**零后端改动**。

## 背景与前置条件

- 前置：任务 02 / 03 评审通过（本轮已完成，`046-requirement-review.md` / `046-tech-review.md` 均「通过（附意见）」）；主会话据评审决定是否把 spec 转 `实施中`（本 task 不代劳）。
- **必读**：spec「状态 / 数据模型 / 端点接口（含本轮补的 D1-B 调用链澄清）/ 边界 B1–B12 / 明确不做 / 产品使用步骤 M1–M3」；`docs/sdd/reviews/046-tech-review.md` **第六节 D1-B 准确调用链**（本任务的实现准则，全文引用）；`docs/sdd/reviews/046-requirement-review.md` 强制约束清单。
- 现状代码锚点（本轮已核实，实现前再次 Read 确认）：
  - `frontend/research-tasks.js`：`state`（`:126` `sessions:[]`、`:140-179`）、`loadTasks()`（`:1089` 单引号字面量 `requestJson('/api/research-sessions?limit=100')` **锁死不改**）、卡片渲染（`:1019` `data-task-id`、`:1024/:1030`）、`requestJson`（`:625`）、`errorFromResponse`（`:614`）、`userError`（`:865`）、`selectTask`（`:3271`）、`upsertSessionTask`（`:1000`）、`renderTaskList` / `clearNode`（`:924` `replaceChildren()`）；
  - `frontend/index.html`：研究视图 `:192-378`、**live tag `:807` `research-tasks.js?v=21`**、兼容标记注释 `:806/:809`、`app.js?v=72` `:810`；
  - `frontend/literature-maps.js:1851-1856`（`N/M` 计数 / 空态既有模式）、`:1008-1010/:1536-1539/:1653-1666`（`createElement` + `textContent` 模式）。

## 数据、配置与接口

- **仅新增前端内存状态**（spec `:57-70`）：`state.taskQuery`（默认 `''`，只经 `input.value`）、归一化查询（`trim`+`toLowerCase`+**上限 128 截断**）、`state.taskIdLookup`（`status/taskId/result/requestSeq`，`requestSeq` 单调递增竞态守卫 B10）、`state.taskSearchCount`（`matched/total`，`total = 当前已加载条数 ≤100`）。
- **接口零新增**，只用既有端点：
  - 直查 `` requestJson(`/api/research-tasks/${encodeURIComponent(id)}`) ``（**反引号模板字符串**；`id` 先过 `^[0-9a-f]{32}$` 白名单；禁止拼进非 hex 输入、禁止超长串进 URL B3）；
  - `selectTask(id, sid)` 内部会自行 `GET /api/research-tasks/{id}`（`:3320`）、`GET /api/research-sessions/{sid}`（`:3346`）、`GET /api/research-tasks/{id}/events`（`:3257`）等既有端点 —— **前端不重复拉 session、不新增端点**。
- **不改**：DB / `Session.to_dict()` / hydrate / SSE 协议 / `GET /api/research-sessions?limit=100` 字面量 / hash 路由。

## D1-B 准确调用链（本任务实现准则，来自 `046-tech-review.md` 第六节）

```
1. 识别输入：trim + toLowerCase；/^[0-9a-f]{32}$/ → 直查分支；其余 → 已加载 ≤100 条前端过滤分支。
2. 直查前：防抖 250ms；state.taskIdLookup.requestSeq += 1（B10）；置 loading「正在按 ID 定位任务…」，
   列表保持可交互、不清空、计数不置 0（M1 步骤 3）。
3. 直查（驱动 404/网络错误区分、loading、N/M、重试、竞态）：
       const detail = await requestJson(`/api/research-tasks/${encodeURIComponent(id)}`);
   · 404（error.status===404 / code==='TASK_NOT_FOUND'）→「未找到该任务，请检查 ID」空态（B5/M3）；
   · error.code==='NETWORK_ERROR'（无 status）/ 超时 / 503 →「定位失败，请重试」+ 重试按钮；
   · 三类均保持列表原状、旧直查结果不被污染；旧请求晚到按 requestSeq 丢弃（B10）。
4. detail.research_session_id 由后端 routes_research.py:1528-1529 注入、可得（可能 null → B7 降级）；sid = 该值。
5. 选中：await selectTask(id, sid);   // 第三参 knownSession 省略 = null，禁止把 detail 当 knownSession 传入
   selectTask 内部（既有，前端无需重复做）：:3320 自带反引号直查（幂等 GET，重复一次，见 P1-4 接受）→
   :3341 解析 sid → :3346 自行拉 session 详情（失败 :3353 catch 降级不抛错）→
   :3358 upsertSessionTask 把不在 100 条内的历史任务并入 state.tasks 并 renderTaskList →
   :3360 renderBenchmarkSummary → :3362 loadMatrix+loadReport（各自 try/catch）→
   :3364 connectStream → SSE 回放 seq 40 → applyEvent → renderSummary → 四项指标可见。
6. 命中提示「已定位并选中历史任务 …」，N/M 按直查命中口径（B9）；下一步查看受控基准摘要四项指标。
```

**关键禁令**：`research_session_id` 来自直查响应、无需另造；`knownSession` 传 `null`（它是 session 详情对象，非 task 实体）；前端**不单独** `GET /api/research-sessions/{sid}` 再 `selectTask`（该步由 `selectTask:3346` 完成）；`selectTask` 保持模块内部调用、不对外暴露（`spec:111`）；接受 `selectTask:3320` 的一次幂等重复直查，**不得为消除它改 `selectTask` 既有逻辑或引入第二套数据装配**。

## 实施步骤与文件边界（≤2 文件/步，Gate 4 :95）

- **步骤 A（结构 + 版本号）**：`frontend/index.html` —— 研究视图（`:192-378`）新增 `input[type=search]#research-task-search`（占位符「按目标 / ID 搜索研究任务」）+ 计数 / 空态容器（复用既有 class 或 `#research-view` 作用域内联样式，**不动 `styles.css`**）；`:807` live tag 升 `research-tasks.js?v=21` → `?v=22`（或更大），并**把 `/assets/research-tasks.js?v=21` 保留为注释兼容标记**（`:806/:809` 既有模式，满足 `test_paper_issue_ui_contract.py:65`）。**不改 `app.js?v=72` / `styles.css?v=70`**（`test_frontend_management_contract.py:78-80`）。
- **步骤 B（逻辑）**：`frontend/research-tasks.js` —— 新增纯过滤函数（五字段 haystack：`research_task_id`/`research_session_id`/`goal_excerpt`/状态/时间；字面量 `String.includes()`；`null` 降级 B7；导出供 Node 单测）、`state.taskQuery/taskIdLookup/taskSearchCount`、输入事件（即触发过滤、完整 hex 或 Enter 触发直查、250ms 防抖、128 截断）、上述 D1-B 调用链、D3 卡片完整 ID 显示 + 复制按钮（`createElement`+`textContent`+`navigator.clipboard`，失败中文提示，参考 spec-044 复制失败约定）、`N/M` 计数与空态、loading / 错误 / 重试态、B8 刷新后查询态与选中态一致。
- **步骤 C（自测）**：`node --check frontend/research-tasks.js`；`Grep innerHTML frontend/research-tasks.js` 应为 0 命中；确认 `:14` 单引号字面量仍在、`:17` 禁则未被触发。
- **文件边界**：只改 `frontend/index.html`、`frontend/research-tasks.js`（以及被明确允许时 `frontend/styles.css`）；**不改 `backend/**`、不改 `app.js`、不改任何既有契约测试**。若步骤 A 确需改 `styles.css` 升 `?v=`，须先论证兼容标记并回 `046-tech-review.md` 复核（P1-3）。
- 完成后可观察结果：研究视图出现搜索框；输入本例 ID 选中历史任务并可见四项指标；输入目标片段即时过滤并显示 `N/M`；不存在 ID 显示友好空态 + 重试。

## 子代理分派

- 角色：`frontend-dev`（**纯前端单端，D5；不派 `backend-dev`**，`AGENTS.md` §前后端分派原则 / Gate 4 :91）。
- 模型 / 上下文：`hy4` / 32k（`spec:161`），分派前以 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段实时值为准；最小上下文 = spec「数据模型 / 端点接口（含澄清）/ 边界 / 明确不做」+ 本任务「D1-B 准确调用链」+ 目标文件行号。
- 单次文件范围：每步 ≤2 文件（步骤 A / B 分开发起）；回传要求「先给完整代码片段、再给说明」，片段同时写进进展日志（Gate 4 :98 防截断）；主会话对子代理产出做**最小增量修改**并 `Read` 读回 + `node --check`，不整文件覆盖（Gate 4 :101）。

## 边界与明确不做

- D1–D5 裁决不得改变；不新增业务端点 / 不改后端 / 不改 SSE 协议 / 不做服务端检索（`q`/`task_id`）。
- 不做带参 hash / 可分享链接（D4）；不消费 `next_cursor`（`loadTasks()` 忽略逻辑本期不改）；不做全文检索 / 正则 / 模糊搜索。
- 不引入 `innerHTML` 或任何新依赖；不新增跨模块公共 API；不改 hash 路由 / 状态机 / 评测观测逻辑。
- 不擅自改既有契约测试期望值（`:14/:17/:65/:78-80`）来「让测试过」；用兼容标记满足。
- 不在本任务写验收结论 / 不宣称准备度分数 / 不改 spec 状态 / 不写台账 / 不 push / 不合 main。

## 验收、风险与回滚

- 验收点：M1（粘贴 ID → 选中 → 四项指标可见，由 task-05 真实 E2E 复核）、M2（即时过滤 + `N/M`）、M3（404 空态）；B1–B12 逐条由 task-05 静态/单测覆盖；`node --check` 无错；`"innerHTML" not in research-tasks.js`；`:14` 字面量在、`:17` 未触发；live `?v=` 已升且 `?v=21` 兼容标记在。
- 风险：重复幂等直查（P1-4，接受）、`?v=` 契约锁（P1-2，兼容标记）、样式改动（P1-3，尽量不动 styles.css）、首次 `renderBenchmarkSummary` 空态（P1-5，属既有行为，E2E 等 SSE 回放）。
- 回滚：实现破坏既有契约 / 扩大到后端 → 停止执行，回到任务 03 评审结论与 spec 修订；不静默改范围。

## 产出物、执行结果与变更日志

- 产出：`frontend/index.html`（搜索框结构 + `?v=` 升版 + 兼容标记）、`frontend/research-tasks.js`（过滤 / 直查 / 复制 / 状态机）；执行后回填真实 `node --check` 结果与改动清单。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写（含子代理分派记录、真实命令、回传读回校验）。
