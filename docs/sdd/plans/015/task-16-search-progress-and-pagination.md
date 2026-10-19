# 任务 16 — 实现来源进度与十条分页交互

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 15；被依赖：任务 17
> 当前状态：`完成`
> 主 Skill：`.agents/skills/usenix-paper-catalog-search/SKILL.md`（本任务只做检索进度和冻结结果展示）

## 一句话目标

把论文检索前端切换到异步任务协议，实时展示 USENIX 与 DBLP 两张独立来源卡片，并按同一冻结结果每页稳定展示 10 篇论文。

## 当前证据

- 现有检索表单、结果卡片、导入按钮、批次轮询、登录队列和安全 `textContent` 渲染可以复用。
- 当前 `searchPapers()` 调用同步 `/api/papers/search`；请求没有明确 accepted 路线，失败后统一显示“论文服务暂时不可用”。
- Task15 将提供创建任务、查询状态和分页结果三个接口；前端不得自行组合来源URL或模拟来源状态。

## 前置门禁

1. Task15 API契约和fake集成测试通过，字段名称已经固定。
2. PM 必须复核 Spec015 产品步骤和中文状态文案；文案以 `message_code` 映射，不直接显示后端异常。
3. 保留现有导入/批次/登录交互；本任务只替换搜索创建、进度和结果分页。
4. 使用本地Ollama junior-dev时每次最多2个代码文件、约150行；线上模型无数量限制。

## 界面与状态契约

- 点击“开始检索”后立即显示两个来源卡片：`USENIX Security 官网`、`DBLP 辅助书目`。
- 卡片状态映射：`queued=等待开始`、`checking_cache=正在检查本地目录`、`cached=已使用缓存`、`fetching=正在从该来源获取`、`merging=正在整理元数据`、`completed=检索完成`、`failed=该来源暂时不可用`。
- 卡片可显示受控字段：缓存年份/页面、正在获取年份/页面、已完成单元数、论文数、稳定错误文案；不得显示完整请求URL、异常堆栈或认证信息。
- 任务 `partial` 时显示“部分来源未完成，以下结果来自可用目录”，并保留结果；只有 `failed` 且无结果时才显示整体失败。
- 结果卡展示标题、作者、年份、会议、摘要、官网关键词（有则显示）、出版阶段、来源和导入状态。
- 页码从1开始，每页固定10条；上一页/下一页使用后端 `has_next/total_pages`，不得客户端对全量结果自行切片。
- 切换查询或重新检索时取消旧轮询并生成新 `search_id`；旧请求迟到不得覆盖新任务UI。

## 思维链（可观察执行阶段）

1. 固定前端状态模型和中文文案映射，先写DOM/契约测试。
2. 在现有检索区域增加两个来源卡片和分页控件，复用既有视觉变量与可访问性结构。
3. 将同步搜索改为 POST创建 → GET状态轮询 → GET页结果；使用 generation/search_id 防竞态。
4. 保留导入映射，把冻结结果的 catalog_paper_id 传给既有批量导入接口。
5. 新前端全部通过后删除旧同步后端路由与不再使用的schema，确认不存在双路径。
6. 用浏览器运行完成、缓存、partial、failed、快速重复搜索和翻页场景。

## 子任务拆分与子 Agent 分派

### A：产品文案与交互复核

```text
你是pm，使用qwen3.5:9b。复核Spec015 Task16的用户流程和来源状态文案，不修改代码。
只读取：已确认Spec015的产品步骤/端点/失败规则、Task16、frontend/index.html中论文检索区域和现有前端契约测试。
允许修改：仅docs/sdd/reviews/015-task16-pm-flow.md；日志写.codebuddy/agent-logs/pm-spec015-task16-<timestamp>.md。
禁止：修改代码；设计其他会议功能；暴露技术异常/URL/凭证；git操作。
完成状态：给出每个后端status/message_code的中文文案、空态/partial/failed/分页/重复搜索用户旅程和可验收场景，无未决文案。
必须验证：引用状态与Spec一致；git diff --check -- docs/sdd/reviews/015-task16-pm-flow.md。
固定返回字段：状态摘要、改动文件、验证与退出码、产物、决策、风险阻塞、主Agent动作、起止/耗时、可用时模型token工具统计。
```

### B：来源卡片与分页结构样式

```text
你是junior-dev，使用qwen3.8:27b-mlx。实现Spec015 Task16的来源进度卡片和分页DOM/CSS。
只读取：已确认Spec015、Task16、PM文案、frontend/index.html、frontend/styles.css、tests/test_frontend_paper_contract.py。
允许修改：使用本地Ollama时仅frontend/index.html和frontend/styles.css、约150行；线上模型不受数量限制。JS和后端不得修改。
禁止：引入前端框架/依赖；内联不安全HTML；破坏现有Tab/导入/登录；git reset/stash/clean。
完成状态：两张来源卡、状态/计数区域、partial提示、分页控件和无障碍label存在；窄屏可用；默认隐藏/空态正确。
必须验证：.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py；样式/DOM契约检查；git diff --check。
结果文档：docs/sdd/reviews/015-task16-layout.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task16-layout-<timestamp>.md。
固定返回字段同Task要求。
```

### C：异步轮询、竞态隔离和分页

```text
你是junior-dev，使用qwen3.8:27b-mlx。实现Spec015 Task16的异步搜索前端逻辑。
只读取：已确认Spec015、Task16、PM文案、B后的HTML/CSS、frontend/app.js、tests/test_frontend_paper_contract.py、Task15三个API响应模型。
允许修改：使用本地Ollama时最多frontend/app.js和tests/test_frontend_paper_contract.py、约150行；线上模型不受数量限制。不得修改后端。
禁止：调用旧/api/papers/search；客户端全量分页；用innerHTML渲染来源数据；显示raw exception；让旧轮询覆盖新search_id；git reset/stash/clean。
完成状态：POST创建、状态轮询、来源卡更新、partial结果、固定页读取、上一页/下一页、轮询取消和导入id映射全部工作。
必须验证：node --check frontend/app.js；.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py；覆盖迟到响应、partial、failed、10/10/1分页；git diff --check。
结果文档：docs/sdd/reviews/015-task16-frontend.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task16-js-<timestamp>.md。
固定返回字段同Task要求。
```

### D：移除旧同步路由

```text
你是junior-dev，使用qwen3.8:27b-mlx。前端切换验证通过后，移除Spec015旧同步搜索路径。
只读取：已确认Spec015、Task16、C后的前端调用、backend/app/api/routes.py、schemas.py、tests/test_paper_discovery_api.py，并用rg确认旧调用者。
允许修改：使用本地Ollama时最多2个代码文件、约150行，优先routes/schemas；测试若需修改另行分派。线上模型不受数量限制。
禁止：删除导入/accepted只读目录接口；改变新异步API；保留双写或隐藏兼容；git reset/stash/clean。
完成状态：生产代码和前端无POST /api/papers/search调用/路由；accepted GET只读全局目录、不触发网络；新API和导入接口不变。
必须验证：rg旧路径0生产命中；.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_frontend_paper_contract.py；py_compile；git diff --check。
结果文档：docs/sdd/reviews/015-task16-old-route-removal.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task16-route-<timestamp>.md。
固定返回字段同Task要求。
```

## 子 Agent 必须返回的字段

结果状态/摘要、改动文件、测试命令/退出码/计数、报告与日志、状态文案映射、竞态处理依据、旧路径反查结果、风险阻塞、主Agent动作、起止时间/耗时；可用时模型/token/工具统计。

## 主 Agent 回填校验

1. 读回PM文案与DOM，逐个状态都有用户可理解文本且无raw异常。
2. 模拟POST后USENIX fetching、DBLP cached，再转completed；卡片独立更新。
3. 模拟单源failed+有结果，确认不出现整体“论文服务暂时不可用”。
4. 快速连续发起两次搜索，让第一次响应后到，确认UI仍显示第二次。
5. 冻结21条结果，实际点击下一页验证10/10/1和前页不变。
6. `rg`确认旧同步路由/调用、客户端全量切片和搜索阶段PDF探测均无生产命中。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/pm-spec015-task16-*.md
tail -f .codebuddy/agent-logs/junior-dev-spec015-task16-*.md
.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_discovery_api.py
```

## 测试与验收标准

- 点击后无需等待来源完成即可看到两张状态卡。
- 缓存、fetch、completed、partial、failed均有独立可核对UI。
- 结果固定10条分页，翻页不触发来源/召回且竞态隔离。
- 标题、摘要、关键词和错误信息安全渲染，不存在XSS回归。
- 既有单篇/批量导入、登录续传和已在知识库状态保持可用。
- 旧同步搜索生产路径完全移除，accepted GET只读目录。

## 风险、停止条件与回滚

- Task15响应字段未固定或与Spec不同：停止，不在JS中猜字段。
- 页面现有用户改动与目标区域冲突：停止相应文件并报告，不覆盖。
- 新流程未通过前不得删除旧路由；删除后出现回归则回滚D，不回滚Task13–15数据。

## 产出物

- PM交互复核、来源卡片、异步轮询、固定分页和竞态测试。
- 旧同步搜索路径移除证据。
- 四份实施/复核报告及日志。

## 执行结果

已完成。前端改为异步创建任务 → 状态轮询 → 服务端固定 10 条分页，显示 USENIX/DBLP 独立来源卡片并隔离迟到响应；删除旧同步 `POST /api/papers/search` 路由及其专用校验分支，accepted 入口仅读全局目录且不触发网络。

验证证据：[`015-task17-acceptance-usenix-only.md`](../../reviews/015-task17-acceptance-usenix-only.md) 及 `.codebuddy/agent-logs/backend-dev-task16-remove-legacy-route-*.md`；前端契约 4 passed，异步/API/边界定向 25 passed、9 subtests，`node --check frontend/app.js`、`py_compile` 与 `git diff --check` 通过。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 创建Task16，固定来源卡片、异步轮询、分页、竞态和旧路径删除条件；未执行代码 |
| 2026-09-08 | 架构师（自身） | 用户明确要求继续开发 Task15–17；前端异步检索与来源进度交互已分派给 frontend-dev，模型仅本轮临时使用 Luna high，不固化模型规则 |
| 2026-09-08 | backend-dev / frontend-dev / tester | 完成并复核异步搜索、来源卡片、分页、旧同步路由删除与前端竞态隔离；ACM/IEEE 登录、A14 排序质量和自定义会议留作后续扩展 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-16",
  "spec_id": "015",
  "title": "# 任务 16 — 实现来源进度与十条分页交互",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-15"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-16-search-progress-and-pagination.md",
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
Read: ["docs/sdd/plans/015/task-16-search-progress-and-pagination.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-16-search-progress-and-pagination.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
