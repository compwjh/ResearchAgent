# Task04 防护活动与确认界面

关联：[Spec050](../../specs/050-agent-safety-and-factuality.md) · [任务索引](README.md)

> 状态与结果回填由主会话代行（纯文档/配置改动，无代码文件）；代码改动由 `frontend-dev` 完成，回归由 `frontend-tester` 承担，主会话读回文件并落地校验。Spec050 整体仍为「待确认」、Gate 1/2 未执行，本条只记录 Task04 实现与定向验收结论，不代表 Spec 级验收签字。

依赖：Task03。当前状态：已完成（实现 + 定向验收 + 真实部署验证）。

## 目标、数据与接口

复用聊天处理过程和研究时间线，呈现已执行、阻止、失败及下一步；添加任务内单动作确认与刷新水合。

## 分派与边界

角色：frontend-dev / frontend-reviewer / frontend-tester。模型与预算引用 Spec 执行配置和当次用户指派。只读取本任务契约、相关路径及直接依赖产物。涉及前后端分别分派。改动及交接结果需读回核对。

## 验收与回滚

界面与真实事件一致；并发/过期/取消提示清晰；重连去重；脱敏及 XSS 契约通过。

发现缺陷先定向修复。发现超范围需求退回 Spec 评审。候选验证失败时维持既有可用版本与硬安全约束，记录具体阻塞。

## 产物、结果与变更

### 实现文件

- `frontend/guard-activity.js`：接入 `GET /api/guard/status` 三态与 `GET /api/guard/stream` 的 `EventSource`（`event: guard`）；`streamEventIds` 按 `event_id` 重连去重；`guard-activity-toast` 实时提示；pending 时自动展开面板；保留 5s 轮询作断线回退。
- `frontend/guard-activity.css`：toast 与「未启用」折叠入口的作用域样式（全部以 `#guard-activity-root` 开头），`[hidden]` 规则、触控目标与窄屏适配不回退。
- `frontend/index.html`：guard 的 CSS/JS 版本号 `?v=1 → ?v=2`；`app.js?v=77` 与主会话 SSE handler 未改动（避免破坏 `event_seq` 序列校验）。
- 测试：`frontend/contract-tests/guard-activity-interaction.test.mjs`（新增 6 个 SSE/可见性用例）、`tests/frontend/test_guard_activity_contract.py`；另同步 `test_frontend_button_affordance_contract.py` 与 `test_memory_return_global_contract.py` 的脚本数冻结基线（10 → 11 + 显式白名单）。

### 本次修好的真实问题

1. **P0**：`buildRoot()` 设 `root.hidden=true` 后全文无解隐藏，真实页面上看不到确认界面。现在 `enabled=true` 显示完整面板并启动 SSE + 轮询；`enabled=false` 显示折叠的「执行防护未启用」入口且零 SSE / 零轮询 / 零数据请求；status 失败或旧后端返回缺字段时保持隐藏并退回轮询。
2. 事件流只靠 5s 轮询、无 SSE：接入 `event: guard` 增量帧，重连由 `Last-Event-ID` + 前端 `event_id` 去重保证不重复插入；SSE 采用追加而非整体重渲染，不吞掉刷新时从服务端重建的历史。
3. 前端全量回归 2 个失败（`INDEX.count("<script src=") == 10` 冻结基线未跟上第 11 个 guard 脚本）：改为「显式白名单断言 + 总数封顶 11」，避免靠猜数字通过。
4. 服务端文本继续全部走 `textContent` / `el()` / `safeText`，无 `.innerHTML =`；恶意文本与未知状态/原因码用例通过。

### 验证（命令 / 退出码 / 结果）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `node --check frontend/guard-activity.js`（及全部 `.test.mjs`） | 0 | 6/6 文件通过 |
| `node --test frontend/contract-tests/guard-activity-interaction.test.mjs` | 0 | `12 tests / 12 pass` |
| `node --test frontend/contract-tests/*.test.mjs` | 0 | `45 tests / 45 pass / 0 fail` |
| `pytest -q tests/frontend/test_guard_activity_contract.py` | 0 | `15 passed` |
| `pytest -q tests/frontend`（修复冻结基线后） | 0 | `643 passed` |
| `git diff --check` | 0 | 通过 |

### 运行时验收与回滚证据

- 真实部署 `http://127.0.0.1:8317` 上 `/`、`guard-activity.js?v=2`、`guard-activity.css?v=2` 均 200；`/api/guard/status` 返回 `enabled=true`；`GET /api/guard/stream` 返回 `text/event-stream` 并推出 7 个 `event: guard` 帧。完整请求/响应/实体 ID/最终状态见 `runs/task-03/api-e2e-success-case.json`。
- 三项自查：新增 4 个 CSS class 与 JS 渲染双向对应；guard 资源 `?v=` 已升 2、无 `?v=1` 残留；无 `innerHTML` / `document.write` 赋值；CSS 36/36 选择器限定在 `#guard-activity-root` 内。
- 回滚：开关默认关闭时前端显示折叠的「未启用」入口，不建立 SSE、不发起轮询、不触碰 `app.js` 主会话流；如需完全移除界面，只删 `index.html` 中两行 guard 资源挂载即可，主会话行为不受影响。
