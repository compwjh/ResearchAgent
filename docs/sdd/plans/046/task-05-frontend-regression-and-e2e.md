> 关联：[spec-046](../../specs/046-research-task-search.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04；当前状态：`已完成`（2026-11-09 单端回归 `runs/task-05/frontend-regression.md` + 真机 E2E `search-e2e.json`/三张截图）

# Task 05 — 前端契约 / 静态 / 单测与真实浏览器 E2E（单端回归）

## 状态与一句话目标

`待执行`。对 task-04 纯前端改动跑**单端回归**（前端契约 pytest + 静态检查 + Node 纯函数单测）与**真实浏览器 E2E**，产出可查的截图 / 取证文件；不 mock 冒充真实 E2E。

## 背景与前置条件

- 前置：任务 04 实现完成且 `node --check` 通过、既有契约未被破坏。
- 必读：spec「验证方式」（`:114-120`）、「边界 B1–B12」（`:88-101`）、「产品使用步骤 M1–M3」（`:122-150`）；`046-tech-review.md` P1-2 / P1-5；本目录 `task-04` 的验收点。
- 单端原则：D5 纯前端改动 → **只跑前端契约 / 静态检查，不跑后端 pytest**（`AGENTS.md` §前后端分派原则；`spec:119`）。
- 证据基线（真实值，本轮已读回）：`docs/sdd/plans/045/runs/task-07/benchmark-summary.event.json` = `event_seq:40`、四项指标 `38478.927 / 19.735 / 106070016 / 0.0`。

## 数据、配置与接口

- 新增测试文件（**只写 `tests/frontend/**`**）：
  1. 前端静态契约 pytest（仿 `tests/frontend/test_frontend_literature_map_expansion.py:30`）：断言 `input[type=search]#research-task-search` 存在、`research_task_id` 进入 haystack、`"innerHTML" not in research-tasks.js`、`?v=` 已升且 `?v=21` 兼容标记在、`requestJson('/api/research-sessions?limit=100')` 字面量仍在（`test_research_session_workspace_contract.py:14`）、反引号模板字符串直查存在且 `requestJson('/api/research-tasks'` 单引号 legacy 未出现（`:17`）。
  2. Node 纯过滤函数单测（仿 `tests/frontend/test_research_report_notifications.js`）：覆盖 B1（空 / 空格）、B2（大小写 / 中英文 / 中文 `goal_excerpt` 片段）、B3（1000 字符受控结果、不进 URL）、B4（特殊字符 `<img src=x onerror=alert(1)>` / `'` / `"` / `&` / 中文标点仅作字面量）、B7（`research_task_id` 为 null 降级）、B9（`3/100`、`0/100`、直查命中三种计数）、B10（乱序 resolve 两个 mock 请求，只应用最新 `requestSeq`）。
- **不改后端、不改既有契约测试期望值**（用兼容标记满足，见 task-04 步骤 A）。

## 实施步骤与文件边界

- **步骤 1（静态 / 契约）**：`node --check frontend/research-tasks.js`；`Grep innerHTML frontend/research-tasks.js`（期望 0）；跑 `tests/frontend/` 契约 pytest（含 `test_research_session_workspace_contract.py` / `test_paper_issue_ui_contract.py` / `test_frontend_paper_contract.py` / `test_frontend_management_contract.py` / 新增 046 契约），确认 **live tag 与测试期望一致**（B11）、全绿、退出码 0。
- **步骤 2（纯函数单测）**：跑新增 Node 单测，B1/B2/B3/B4/B7/B9/B10 全过；测试断言不得恒真 / 不得静默失效（`regression-guard` 增补第 12 条：用 `assert` 真实样本数，不用 `if not candidates: return` 守卫）。
- **步骤 3（真实浏览器 E2E）**：服务**真实启动**，用真实浏览器（Playwright/Chromium，参考 `045-acceptance-review.md:54` 的 `benchmark-card-browser.txt` 取证方式）执行：
  - **M1**：打开 `#research-view` → 粘贴 `2eb327f2cefb5fc7b5ac60e0454294f6` → 等直查返回 → 等 **SSE 回放 seq 40 后四项指标出现再断言**（P1-5：`:3360` 首帧为空态，属既有行为）→ 断言四项指标可见（`median_ttft_ms≈38478.927`、`throughput_completion_tokens_per_s≈19.735`、`peak_memory_bytes≈106070016`、`failure_rate=0.0`）、`sectionHidden=false`。**不得用 mock / 内部函数 / 仅表单调用代替**。
  - **M2**：输入 `goal_excerpt` 片段 / `会话` → 即时过滤 + `N/M`（如 `3/100`）；清空恢复 100 条。
  - **M3**：输入合法但不存在的 `00000000000000000000000000000000` → 404 友好空态、列表保持、无未捕获 JS 异常。
  - 失败恢复：404 / 超时 / 网络失败 →「重试」按钮重发直查成功。
- **步骤 4（产物落盘）**：截图与取证写入 **`docs/sdd/plans/046/runs/task-05/screenshots/`**（执行时创建；`M1-*.png`、`M2-filter.png`、`M3-not-found.png`）与 E2E 报告 / 取证 JSON（`runs/task-05/`）。**这是 spec 中 `<task>` 占位符的具体化**（需求评审 P1-3）。
- **文件边界**：只写 `tests/frontend/**` 新增测试 + `docs/sdd/plans/046/runs/task-05/**` 产物；不改 `backend/**`、不改业务代码、不改既有契约测试期望值。

## 子代理分派

- 角色：`frontend-tester`（单端回归 + 真实 E2E）/ 跨端验收签字由 `tester` 在 task-06 处理；**不派 `backend-tester`**（D5）。
- 模型 / 上下文：`hy4` / 32k（`spec:162`），分派前以 agent 文件实时 `model` 值为准；最小上下文 = spec 验证方式 / 边界 / M1–M3 + 本任务验收点 + 目标文件路径。
- 单次文件范围：新增契约 pytest 1 份 / Node 单测 1 份 / 产物目录；回传附真实命令、退出码、截图路径，主会话 `Read` 读回截图证据（真实 PNG 校验）与报告。

## 边界与明确不做

- **不 mock 冒充真实 E2E**：M1 必须在真实服务 + 真实浏览器 + 真实 API 上跑通并记录状态码（`spec:120` §56）；`runs/task-05/` 取证须为真实产物。
- 不跑后端 pytest / 不改后端；不宣称准备度分数；不代写验收评审 / 不替 architect 签字；不把 spec 状态改为 `已完成` / `实施中`；不写台账 / 不 push / 不合 main。
- 不得用「测试全绿」替代「M1 四项指标真实可见」；两者都要。

## 验收、风险与回滚

- 验收：前端契约 pytest 全绿（EXIT=0）、`node --check` 无错、Node 单测覆盖 B1/B2/B3/B4/B7/B9/B10、真实 E2E M1/M2/M3 通过且截图 / 取证落盘可读、live tag 与契约期望一致。
- 风险：SSE 回放时序（P1-5，等四项指标出现再断言）；`?v=` 兼容（P1-2，契约测试验证）；测试恒真 / 静默失效（用可数样本断言）。
- 回滚：E2E 失败 → 退回 task-04 修复，不进入 task-06；契约测试因升版失败 → 检查 `?v=21` 兼容标记是否保留，不改测试期望值蒙混。

## 产出物、执行结果与变更日志

- 产出：`tests/frontend/` 新增 046 契约 pytest + Node 单测；`docs/sdd/plans/046/runs/task-05/screenshots/M1-*.png` / `M2-filter.png` / `M3-not-found.png`、E2E 报告与取证 JSON。
- 执行结果：待执行后填写（真实命令、退出码、`file` 校验 PNG、四项指标实测值）。
- 变更日志：待执行后填写。
