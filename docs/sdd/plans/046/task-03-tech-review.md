> 关联：[spec-046](../../specs/046-research-task-search.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`（本轮执行）

# Task 03 — 技术评审（Gate 2 总控）+ 4 风险核实 + 拆任务

## 状态与一句话目标

`已完成`。对 spec-046 做技术维度评审，逐条以**代码事实**核实 4 个关键可行性风险，给出 D1-B 准确调用链，判通过 / 打回，并按模板「规范化流程」创建 `plans/046/` 任务文档。

## 背景与前置条件

- 前置：任务 01 完成（spec `已确认`）；任务 02 需求评审通过（可与本任务并行，同属 Gate 2）。
- 必读：spec 全文；`SDD-GATE-CHECKLIST.md:65-80`；`00-sdd-spec-template.md:92-99`；五个技能 SKILL.md 的评审维度。
- 必须核实的代码（本轮已逐文件 Read/Grep，行号为核实结果）：
  - `frontend/research-tasks.js`（`selectTask:3271`、`requestJson:625`、`errorFromResponse:614`、`upsertSessionTask:1000`、`connectStream:3252`、`handleSseEvent:3222`、`applyEvent:3176`、`renderSummary:2533`、`renderBenchmarkSummary:1537`、`benchmarkSummaryFromState:591`、`loadReport:3026`、`loadMatrix:3013`）；
  - `frontend/research-session-ui.js:29-63`（`projectSession`）；`frontend/index.html:803-810`（live `?v=` tag）；
  - `backend/app/api/routes_research.py`（`get_research_task:1516`、`_task_summary:668`、`_error:528`、`get_research_session:1271`、`stream_research_events:1824`、`_event_stream:1863`）；`backend/app/research/application/research_service.py:269-274`；`backend/app/research/infrastructure/research_store.py:1400-1406`；
  - `tests/frontend/test_research_session_workspace_contract.py:13-18`、`test_paper_issue_ui_contract.py:65`、`test_frontend_paper_contract.py:90-110`、`test_frontend_management_contract.py:78-80`；
  - `docs/sdd/plans/045/runs/task-07/benchmark-summary.event.json`（seq 40 证据）。

## 数据、配置与接口

- 结论性事实（写入评审）：`GET /api/research-tasks/{id}` 响应含 `research_session_id`（后端 `routes_research.py:1528-1529` 注入）；`knownSession` 是 session 详情对象，D1-B 场景传 `null`；`selectTask` 只读 `state.tasks` 并自行拉 session + `upsertSessionTask`，session 不在缓存时不抛错；404 = `_error` 稳定错误体 404 `TASK_NOT_FOUND`，owner 隔离由 `research_store.py:1400-1406` 保证；`requestJson` 用 `error.status===404` 与 `error.code==='NETWORK_ERROR'` 区分；反引号模板字符串不撞 `:17`；四项指标经既有 SSE 回放 seq 40、不依赖 session 上下文。
- 接口增量：**零新增业务端点**（D5）；本任务不改任何接口。

## 实施步骤与文件边界

- 产出文件：`docs/sdd/reviews/046-tech-review.md`（头部四项齐全）、`docs/sdd/plans/046/README.md` + `task-02..06` 任务文档。
- 允许同步回填 spec「评审记录」技术评审行、「任务计划」表状态与链接；**仅当** D1-B 调用链与 spec 现行描述不一致时，在「端点/接口」段补一段澄清（本轮已触发）。
- **文件边界**：只写 `docs/sdd/reviews/046-tech-review.md` 与 `docs/sdd/plans/046/*.md`；不改任何业务代码 / 测试。

## 子代理分派

- 角色：架构师（评审/合并）`architect`（本轮即该角色自身执行）。
- 模型 / 上下文：`hy4` / 32k（`spec:160`）；最小上下文 = spec + 上述代码行号清单 + 门禁章节。
- 单次文件范围：评审文档 + plans 目录文档；回传后主会话 `Read` 读回校验。

## 边界与明确不做

- 4 个风险若任一无法在纯前端解决 → 如实判「打回」或写明「需回 spec 修订并请用户确认」，**不得为让评审通过偷偷扩大到后端**。
- 不改后端、不新增端点、不改 D1–D5 裁决；不代写验收评审、不宣称准备度分数、不 mock 冒充 E2E、不把 spec 状态改为 `实施中`、不写台账。
- 不在 task 文档里放无法跳转的占位链接；不创建 `reviews/` 之外的代码文件。

## 验收、风险与回滚

- 验收：评审文档带明确结论 + P0/P1；4 风险逐条附 `文件:行` 依据；D1-B 准确调用链含 `research_session_id` 是否可得；数据模型 / 接口 / 模块拆分 / 上下文预算 / 回归维度各节齐全；plans/046 六份 task + README 链接真实、依赖无环。
- 风险：重复幂等直查（`selectTask:3320` 会再查一次）→ 登记 P1-4，接受而不改既有逻辑；`?v=21` 契约锁 → 登记 P1-2 兼容标记方案。
- 回滚：结论改打回 → 回任务 01 修订 spec 重新确认。

## 产出物、执行结果与变更日志

- 产出：`docs/sdd/reviews/046-tech-review.md`、`docs/sdd/plans/046/README.md`、`task-02..06-*.md`。
- 执行结果（2026-11-09）：**通过（附意见）**；P0=0 / P1=5（调用链澄清、`?v=` 升版兼容、styles.css/app.js 不动、重复幂等直查、M1 等待条件）。4 风险全部查实可在纯前端解决；已在 spec「端点/接口」段补 D1-B 调用链澄清。
- 日志：`.codebuddy/agent-logs/spec-046/architect-gates/20261109-012550.md`。
