# 任务 02：刷新旋转改为 Promise `finally` 移除 + 版本/断言同步

> 关联：[spec-049](../../specs/049-known-nonblocking-followup-cleanup.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`（`implementation.md`；APPROVE / 单端 628 passed）

## 1. 状态与一句话目标

把画布工具区刷新图标按钮的 `is-spinning` 从「固定 700ms `setTimeout` 移除」改为「状态刷新请求 Promise 结束后移除」，同步 live 资源版本与精确断言，**不改变任何其它交互语义**。

## 2. 背景与前置条件

- 用户已明确确认 spec-049；Gate 2 需求 / 技术评审均通过；C 组定案 `保持现状、零改动`。
- 真实代码：`frontend/literature-maps.js:1579-1587` `bindEvents()`；`loadMaps()` 在 `:3224`、`selectMap()` 在 `:3470`，**均为 `async` 返回 Promise**。
- P2 来源：`docs/sdd/reviews/048-frontend-review.md:100-102,149,183` 与 `docs/sdd/reviews/048-acceptance-review.md:172`。
- 服务可启动：`./deploy/start.sh -d`（端口占用 `PORT=8300`）。

## 3. 数据、配置与接口

- 数据模型 / 端点：**不适用**（无变化）。
- 资源版本：`literature-maps.js?v=48 → v=49`；`literature-maps.css?v=36` **不变**；`app.js?v=77` / `styles.css?v=77` **不变**。
- 冻结语义：`index.html` 末尾纯属性 marker `js?v=47` / `css?v=34` **不新增、不移动**，`re.findall(...)[-1]` 仍为 `47` / `34`。

## 4. 实施步骤与文件边界

| 序 | 目标文件 | 可观察结果 |
|---|---|---|
| 1 | `frontend/literature-maps.js` | `bindEvents()` 内：点击后 `classList.add('is-spinning')`；`clearTimeout` / `setTimeout(..., 700)` **移除**；把 `selectMap(id)` / `loadMaps()` 的 Promise 用 `.finally(() => refreshButton.classList.remove('is-spinning'))` 收尾；保持 `if (state.selectedMapId) ... else ...` 分支与原有 `bindEvents(refreshButton, closeDetail)` 调用链不变 |
| 2 | `frontend/index.html` | 首个 live `<script>` 改 `literature-maps.js?v=49`；**末尾 marker 区零改动** |
| 3 | `tests/frontend/fixtures/literature_map_component.html` | `literature-maps.js?v=48 → v=49`（css 保持 `v=36`） |
| 4 | `tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | `js_live == ["48"] → ["49"]`；新增静态契约断言：源码不含 `setTimeout(...700...)` 旋转移除、含 `.finally(` 移除 `is-spinning`（CSS 版本断言 `["36"]` 不动） |
| 5 | `tests/frontend/test_frontend_map_groups_exports.py`、`test_frontend_map_mobile_contract.py` | fixture / live 精确断言 `v=48 → v=49`；`:54-55` / `:119-120` 的 `[-1] == "47"/"34"` **逐字不动** |
| 6 | `docs/sdd/plans/048/runs/task-04/browser_e2e.py`（若执行时引用 live 版本） | 仅同步版本字样，不改断言逻辑；历史 `browser-e2e.json` / 已归档报告**不改** |

> **单端改动边界**：只碰 `frontend/literature-maps.js`、`frontend/index.html` 与 `tests/frontend/**`；按 Gate 4「每任务 ≤2 个文件」拆子任务串行落地，`literature-maps.js` 与 `index.html` 分两批，避免互相覆盖。

## 5. 子代理分派

| 角色 | 分派 | 最小上下文 | 回传校验 |
|---|---|---|---|
| `frontend-dev` | `Task(frontend-dev)` | 本 task 文件 + spec「边界 1–9」+ 上述 6 个文件路径与行号 | 主会话 `read_file` 读回 6 个文件，确认 `setTimeout` 消失、`finally` 存在、`v=49` 精确一致、marker 未动 |
| `frontend-reviewer` | `Task(frontend-reviewer)` | 改动 diff + spec 边界 1–9 | DOM 契约 / `?v=N` / XSS 三项必查，P0/P1 必须为 0 |
| `frontend-tester` | `Task(frontend-tester)` | `tests/frontend/` 定向用例列表 | `pytest -q tests/frontend/` EXIT=0、`node --check` 0 |

## 6. 边界与明确不做

- 不改 `selectMap` / `loadMaps` 的 `async` 性质、返回值、状态文案或 `catch` 分支。
- 不改刷新按钮 `id` / `title` / `aria-label="刷新状态"` / 无可见文字 / reduced-motion / ≥44px 触摸目标。
- **不改 CSS、不升 `css?v=36`、不新增任何 `?v=` marker、不改 `[-1]` 断言语义**。
- 不改松 / 删 / skip / xfail 任何断言；不因「顺手」改其它 header 作业按钮。
- 不碰 `backend/**` / 数据模型 / 端点 / 其它视图 / 工作区未跟踪文件 / 平台设置。
- 不改历史归档报告中的旧版本口径（Spec-048 已 `已完成`）。

## 7. 验收、风险与回滚

| 验收点 | 判定 |
|---|---|
| 静态：JS 中无 700ms 旋转定时器、有 `finally` 移除 | 新增契约断言通过 |
| 断言：live `js?v=49`、fixture `v=49`、`css` 与 marker 全不动 | `pytest -q tests/frontend/` EXIT=0 |
| 运行时：点击刷新，真实 API 响应结束后 `is-spinning` 移除；快速连点无残留 | Chromium E2E 记录 |
| 全量：`.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` | EXIT=0、通过数 ≥ 4571 |

**风险**：`index.html` 若误新增 `?v=` marker 会破坏 211 处 `in INDEX` 与 3 处 `[-1]` 断言；`selectMap` 内部 `requestId` 失配提前 `return` 仍使 Promise resolve，需确认 `finally` 一定会执行。
**回滚**：失败则回退到任务 02 起点（`v=48` / 700ms 定时器），不越过 Gate 4，不修改历史评审结论。

## 8. 产出物、执行结果与变更日志

- 产出物：上述 6 个文件改动、`docs/sdd/plans/049/runs/task-02/implementation.md`（执行后回填）。
- 执行结果：`implementation.md`；`049-frontend-review.md` `APPROVE`（C1–C10 10/10，P0/P1/P2 全 0）；单端 `628 passed / EXIT=0`；全量 `4571 passed / EXIT=0`；E2E `31/31 PASS`。阻塞项 0。
- 变更日志：2026-11-13 `frontend-dev` 实现 6 文件；`frontend-reviewer` 评审；`frontend-tester` 单端回归；`tester` 收尾修复 E2E 脚本 B007（ruff `186 → 185`）。
