# Spec034 Task12：批准后加载 Task 视图与事件流（时间线渲染）

## 目标

修复「计划批准（approve_plan）后前端停留在会话视图、未加载新建 Task 详情与事件流」的缺口，使批准后 UI 自动选中新建 Task、拉取 Task 事件并渲染运行期时间线，从而让研究会话全生命周期
（spec028 持久化调度与恢复、spec029 全文获取、spec030 证据矩阵与只读报告）在真实浏览器端到端测试中可被验证。

## 现状与根因线索

- **后端正常**（已验证，无需改动）：
  - `POST /api/research-sessions/<id>/commands`（approve_plan）返回 **200 OK** 且无异常/traceback。
  - `approval_service._resume_activity` 在批准后把会话置为 `queued`，并调用 `research_service.start()`；后者在 uvicorn 进程内的**后台线程**执行编排，不需要独立 worker。
  - 事件流可用：curl `/api/research-tasks/<id>/events?after_seq=0` 能拿到 `task` / `processing_step` 事件。
- **前端缺口**（`frontend/research-tasks.js`）：
  - `mergeSessionCommandResult()`（约 1179–1205 行）从命令响应取 `taskId = result.research_task_id || result.task?.research_task_id || state.selectedTask?.research_task_id || null`，并在 `taskId` 非空时执行 `await selectTask(taskId, sessionId)`，否则 `await loadReport(taskId); connectStream();`。
  - `renderTimeline()`（约 1325 行）以 `section.hidden = events.length === 0` 控制时间线面板显示——**拿不到 Task 事件就永不渲染**。
  - `renderTaskHeader()`（约 1001–1003 行）把 `#research-detail-status` 的 `data-status` 设为 `task?.status`，Task 未加载时为空字符串。
- **观测证据**：
  - 批准后 `#research-detail-status` 的 `data-status` 长时间为空，时间线面板始终 `hidden`。
  - 后端访问日志中只有旧 Task 的轮询，**新建 Task 的 events/report 接口从未被请求** → `selectTask`/`loadReport` 链路未真正触发（taskId 为空、或 early return、或异常被吞）。

## 范围（只改 `frontend/**`）

在 `frontend/research-tasks.js` 内修复「批准后进入 Task 视图并加载事件流」：

1. 定位 `mergeSessionCommandResult()` 为何没有真正加载新 Task：确认 `taskId` 取值、`selectTask()` 的 early return 条件与异常路径。
2. 保证批准后加载一次新 Task 详情并连接事件流（`loadReport(taskId)` + `connectStream()`），使 `state.events` 灌入事件、`renderTimeline()` 渲染时间线。
3. 保持幂等：重复调用或崩溃恢复重放时不得重复建立 SSE 管道、不得重复插入会话消息。

## 明确不做

- 不改后端 `approval_service` / `research_service` / Orchestrator 逻辑，不改数据模型与 SSE 协议。
- 不新增接口，不改错误码矩阵。
- 不调整样式与布局，不改动其他视图。

## 验收方式

1. 静态检查：`node --check frontend/research-tasks.js` 通过。
2. 端到端（后端 `:8000` 已启动）：
   `RUN_E2E=1 .venv/bin/python -m pytest tests/e2e/test_research_lifecycle_e2e.py -v`
   - `test_research_task_create_shows_in_list` 继续 **PASSED**；
   - `test_research_lifecycle_follow_through` 不再因「时间线未渲染」SKIP：批准后时间线面板渲染（spec028），运行态下暂停/继续/恢复控件可见。
3. 前端回归：既有 `tests/frontend/*.js`（Node 断言）不回归。
