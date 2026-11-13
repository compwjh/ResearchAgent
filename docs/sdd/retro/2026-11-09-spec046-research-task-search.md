# 复盘：Spec046 研究任务搜索与 ID 定位（2026-11-09 收口）

> 用户反馈「找不到研究任务 `2eb327f2…`，添加搜索功能」→ 按推荐方案确认 spec → 全流程交付。
> 分支 `feature/spec-046-research-task-search`；**不 push、不合 main**，`origin/main` 仍 `1b26c76c`。

## 1. 结果

| 项 | 结果 |
|---|---|
| D1–D5 | 全部按推荐确认：B 直查 / 五字段过滤 / 卡片可复制 ID / 不做带参 hash / 不改后端 |
| 三道门禁 | 需求评审通过（P0=0/P1=4）、技术评审通过（P0=0/P1=5）、验收评审通过且架构师签字；准备度 **9/10**、P0/P1=0 |
| 单端回归 | `33 passed`（指定契约）/ `337 passed`（35 份前端精确集合）/ Node 8/8 / `node --check` 0 / `innerHTML=0` |
| 当前部署版本 E2E | M1 直查选中历史任务 + 四项指标可见；M2 前缀过滤 `1/101`；M3 404 空态 + 重试；17 请求 16×200 + 1×404、`pageErrors=[]` |

## 2. 关键决策

1. **根因不是「没有搜索框」**：研究视图列表其实是**会话列表**，`/api/research-sessions?limit=100` 只返回最近 100 条且 `next_cursor` 非空，目标历史任务命中 0 —— 从未进入 DOM。因此「纯前端过滤已加载列表」（D1-A）**根本解决不了用户这次的问题**。
2. **D1-B 用既有端点做全域定位**：`GET /api/research-tasks/{id}` 真实返回 200 且实体含 `research_session_id`（`routes_research.py:1528-1529`），前端识别 32 位 hex → 反引号模板字符串直查 → `await selectTask(id, sid)`（第三参 `knownSession` **必须省略**，`selectTask:3346` 内部自拉 session、`:3358` upsert 补齐）。零后端改动、零新增端点，能定位任意历史任务。
3. **不改 hash 路由（D4）**：`#research-view?task=<id>` 涉及 `app.js` 与 `research-tasks.js` 两处视图同步器，成本与回归风险高于收益，明确不做。
4. **分端纪律**：纯前端改动只派 `frontend-dev` / `frontend-tester` / `tester` / `architect` / `doc-updater`，未派 `backend-dev` / `backend-tester`、未跑后端全量 pytest。

## 3. 踩坑与修复（可复用经验）

| 现象 | 根因 / 处置 |
|---|---|
| 静态契约锁死 `research-tasks.js?v=21` | live tag 升 `?v=22`，把 `?v=21` 作为 **HTML 注释兼容标记**保留在 `index.html`，满足 `in INDEX` 字符串断言且无需改测试；`styles.css?v=70` / `app.js?v=72` 一律不动 |
| 单引号 legacy 字面量被禁 | `test_research_session_workspace_contract.py:17` 只禁 `requestJson('/api/research-tasks'`，用反引号模板字符串 `/api/research-tasks/${encodeURIComponent(id)}` 合规（`:3320` 已有同款范例） |
| 首轮真机 M1 计数显示 `1/1`，疑似状态污染 | 实为**列表尚未加载完就直查**的时序现象；等 `state.sessions.length >= 100` 后重跑得 `1/101`（列表 101 条被 ID 过滤成 1 条）。另用不存在关键字验证过滤确实生效（`0/100` + 空态） |
| 5 个 `test_frontend_map_*.js` 失败 | 既有 `ReferenceError: closeGroupsPopover is not defined`（`literature-maps.js:2607`），5 个文件均不加载 `research-tasks.js`，`git diff --name-only` 不含相关文件 → 完整隔离，非本改动引入 |
| `selectTask` 第三参误传 task 实体 | `knownSession` 是 **session 详情对象**，不是 task 实体；省略即可，前端不要单独 `GET /api/research-sessions/{sid}` |
| 需求评审 4 条 P1 | M1 步骤 2 残留「待 D1/D2 确认」、数据模型「建议 128」草案语气、E2E 产物路径 `<task>` 占位、步骤 5 缺 SSE 回放等待条件与失败恢复 → 交 `doc-updater` 定点修订，六要素齐全 |

## 4. 分工与门禁执行

`architect`（编写 spec / 需求+技术评审 / 拆任务 / Gate 5 签字）、`doc-updater`（产品使用步骤 P1）、
`frontend-dev`（红→绿实现与三项自查）、`frontend-tester`（单端回归与既有失败隔离）、
`tester`（跨端验收总控与准备度打分）、主会话（编排、真实 API/真机 E2E、台账、复盘、部署确认、本地 commit）。

三份评审有真实结论、验收签字栏已填、台账已追加、引用路径存在、复盘已落盘，满足 DoD 后转 `已完成`。

## 5. 已声明边界与后续建议（非本次范围）

- D4 带参 hash / 可分享链接不做；`next_cursor` 未消费，前端过滤只覆盖已加载 ≤100 条（由 D1-B 直查兜底）；
- B8 刷新/选中态无自动化覆盖（真机已验证直查后 `1/101` 与 upsert，刷新态未自动化）；
- B5 404、B9 直查命中计数以真机 E2E 覆盖，静态仅 marker；`selectTask` 内部幂等重复直查一次；
- 复制按钮依赖 `navigator.clipboard`，非 secure context 降级为中文提示；
- 项目无覆盖率采集/阈值配置，`docs/github.md` 的 CI / 覆盖率 / PR approval 三项门禁**未验证**，未宣称通过；
- 若后续要「按目标全文检索所有历史任务」，需 D1-C 服务端检索 → 回 spec 修订并重新评审（D5 接口增量）。

## 6. 交付物速查

- spec：`docs/sdd/specs/046-research-task-search.md`（`已完成`）
- 三份评审：`docs/sdd/reviews/046-{requirement,tech,acceptance}-review.md`
- 证据：`docs/sdd/plans/046/runs/task-04/implementation.md`、`runs/task-05/frontend-regression.md`、
  `runs/task-05/search-e2e.json`、`M1-id-lookup.png` / `M2-filter.png` / `M3-not-found.png`
- 台账：`docs/sdd/spec-status-changelog.md` 末条（`实施中 → 已完成`）
