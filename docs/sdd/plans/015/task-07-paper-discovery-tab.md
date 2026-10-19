# 任务 07 — 新增论文检索 Tab 与完整交互

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 03、04、05、06
> 当前状态：`阻塞`

## 一句话目标

在现有单页应用中新增独立“论文检索”Tab，完成方向输入、会议/年份筛选、相关度结果、单篇/批量导入、登录续传和知识库跳转的完整用户流程。

## 背景与前置条件

- 复用 `frontend/index.html` 和 `frontend/app.js` 当前 `showView` Tab 机制，不重建前端框架。
- 依赖任务 03–06 的稳定接口和错误码，不在前端推测论文 URL 或导入状态。
- 前端静态资源由 FastAPI 直接托管，不新增构建系统。

## 数据、配置与接口

- 新增导航项与 `#papers-view`，状态与 chat/models/kb 互斥但不销毁其他视图。
- 前端状态至少包含会议配置、查询、年份、搜索结果、选中项、批次进度和登录等待项。
- 使用服务端返回的 `candidate_id/search_id` 导入，严禁在 DOM 中拼接任意下载 URL。

## 实施步骤与文件边界

1. 在 HTML 中增加 Tab、输入区、会议多选、年份范围、搜索按钮、状态区、结果区和批量操作区。
2. 扩展 `showView` 和首次加载逻辑；功能关闭时不展示 Tab，不影响现有页面。
3. 加载默认会议和年份；提供会议搜索、添加、编辑别名、启停和删除用户会议的轻量弹层。
4. 搜索期间显示 loading 并禁用重复提交；新查询取消旧渲染，响应必须与当前 `search_id` 匹配。
5. 结果按服务端 rank 渲染，不在前端重新排序；显示标题、作者、年份、会议、摘要状态、相关度、PDF 状态和已入库状态。
6. 支持单篇添加和勾选后批量添加；已入库项禁用重复按钮。
7. 轮询当前批次，逐项显示下载、等待登录、校验、索引、完成和失败；离开 Tab 后仍保留任务。
8. 等待登录项提供“打开登录”和“登录完成，继续”操作；浏览器不可用或无权限显示后端错误。
9. 成功项提供跳转知识库并定位论文的动作。
10. 所有用户文本用安全 DOM API 渲染；无 `innerHTML` 注入标题、作者、摘要或错误内容。
11. 更新 CSS 和静态资源版本，验证窄屏、长标题、长作者列表、空结果和大批次布局。

## 子代理分派

- 分派 A（`junior-dev`）：HTML 结构与可访问性，最多 2 文件。
- 分派 B（`junior-dev`）：Tab/会议/搜索交互，最多 2 文件。
- 分派 C（`junior-dev`）：选择、批次、登录续传和知识库跳转，最多 2 文件。
- 分派 D（`junior-dev`）：CSS 与前端契约测试，最多 2 文件。
- 最小上下文只包含本 task、相关后端契约及现有 Tab/知识库渲染函数；每次回传后浏览器实际检查。

## 边界与明确不做

- 空查询、无会议、非法年份、过期搜索、空结果、部分源失败均有清晰状态。
- 结果很多时必须可滚动，批量工具条和登录动作不可被卡片遮挡。
- 前端不得自行访问 DBLP、OpenAlex、ACM 或 IEEE，不持有出版商 Cookie。
- 不引入 React/Vue、独立构建链、复杂路由或订阅通知。
- 不改变聊天、模型库、知识库现有主要交互。

## 验收标准

- Tab 可切换且其他视图状态不丢失；开关关闭时入口和请求均不出现。
- 默认四大顶会和五年正确，用户可搜索新增会议。
- 研究方向结果严格沿服务端排名展示，长内容布局可用且无 XSS。
- 单篇、批量、等待登录、失败重试、已入库和知识库跳转均可完成。
- 离开再返回 Tab 后仍能看到当前批次状态，重复点击不重复提交。
- 桌面和窄屏下按钮可见、列表可滚动、键盘焦点与错误提示可用。

## 风险、回滚与产出

- 风险：在现有大文件中改动易冲突；按函数/区域小步分派并集成 spec-013/014 最终版本。
- 回滚：隐藏导航和视图，后端关闭功能开关；不影响已导入论文。
- 产出：论文检索 Tab、会议管理、结果卡片、批量与登录交互、前端测试。
- 执行结果：HTML/JS/CSS 及会议搜索 API 已完成；最终 Tech Lead 与 QA 确认 Node、前端契约、论文相关回归和全量回归通过（全量 511 passed，38 subtests）。功能开关在途响应、导航 aria-current、受控会议搜索、跨响应 DOI/DBLP/标题去重、稳定 tie-break、多批次独立渲染和 XSS 边界已闭合。A3 自定义会议仍受 Task02 DBLP Venue Search 外部阻塞；真实 GUI/窄屏与 ACM/IEEE 登录续传受当前无 Playwright/合法账号环境限制，保持阻塞。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-05 | junior-dev / Tech Lead / tester | 完成论文 Tab HTML/JS/CSS、会议搜索 API 及三轮门禁修复；最终离线回归通过，保留 A3/真实 GUI/登录环境阻塞 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-07",
  "spec_id": "015",
  "title": "# 任务 07 — 新增论文检索 Tab 与完整交互",
  "status": "blocked",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-03",
    "spec-015-task-04",
    "spec-015-task-05",
    "spec-015-task-06"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-07-paper-discovery-tab.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-015",
    "branch": "feature/spec-015-security-paper-discovery",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-tester
Read: ["docs/sdd/plans/015/task-07-paper-discovery-tab.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-07-paper-discovery-tab.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
