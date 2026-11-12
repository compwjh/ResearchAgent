# task-20 追加范围五：前端遗留清理（A + B + D）

> **产出性质**：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 追加范围五 §7 / 状态台账 2026-11-12 收口条）。
> **状态**：`已完成`；**分派**：`frontend-dev`（唯一含 `.html` / `.css` / 前端测试的实现分派）。

## 一、目标与前置条件

前置：用户「遗留你也改一下」+ 连续「请继续」构成等价确认，spec 追加范围五已转 `实施中`；工作区已从 `origin/main 42bbc188` 新建 `feature/spec-047-followup-cleanup` 恢复。

目标：A 升 `research-tasks.js?v=25 → v=26` 并加 `v=25` 纯属性 marker；B 同步 2 处 P2 失败文案、函数名与注释；D 仅在 `[data-status="needs_ground_truth"]` 限定下把灰卡 4 类文字色改 `var(--muted-strong)`，CSS 升 `styles.css?v=76 → v=77`，加 `v=76` marker，同步 6 处精确 live 断言并新增 R1 静态契约。

## 二、实施与文件边界

只改 `frontend/index.html`、`frontend/styles.css` 与 `tests/frontend/` 下 6 个测试文件；**不改 `frontend/app.js`、不改 `backend/**`、不改 `:root`、不动 `computed` / `degraded` / `unavailable` 配色**。新 marker 必须置于 `index.html` 末尾注释区，不含 `<script` / `<link` 标签字面串，避免污染 `active_version`。

## 三、验收

- `node --check frontend/app.js` EXIT=0；`pytest -q tests/frontend/` `616 passed` / EXIT=0（RED `10 failed / 48 passed` → GREEN）。
- 6 处精确 live 断言同步为 `77` / `["77"]`，9 处 `in INDEX` 冻结断言靠 marker 继续通过，未删测试 / 未 skip / 未 xfail / 未放宽。
- 真实 Chromium `getComputedStyle`：灰卡 `rgb(90, 93, 102)`（6.0947:1），computed 仍绿。

## 四、风险与回滚

风险：marker 若插入 `<head>` 会破坏 `test_frontend_map_header_actions_readability.py` 取首个 `styles.css?v=` 的语义；CSS 升版遗漏会造成浏览器缓存命中旧样式。回滚：`git revert` 本任务 commit 即可恢复全部 live 版本与断言。

## 五、产出与执行结果

- 实现自测报告：`docs/sdd/plans/047/runs/task-20/frontend-implementation.md`（已读回校验）。
- 浏览器复核：`runs/task-20/r1-computed-style.txt`、`task-20-gray.png`。
- 代码评审：`docs/sdd/reviews/047-followup-frontend-review.md` **APPROVE**（P0=0 / P1=0 / P2=2）。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-20/frontend-dev/20261112-214742.md`。
- **执行结果：`已完成`**，无 P0 / P1。
