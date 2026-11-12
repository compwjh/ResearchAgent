# Spec-048 任务索引：文献地图新建入口 tab 化与刷新状态图标化

> 关联：[spec-048](../../specs/048-literature-map-create-tab-and-refresh-icon.md)（状态 **`待确认`**）
> 纯前端改动；用户明确确认且需求 / 技术评审通过后才进入执行。

## 任务清单

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-048 | [spec 本体](../../specs/048-literature-map-create-tab-and-refresh-icon.md) | — | 完成 |
| 02 | 页面级 tab：搬 createPanel DOM + `activateMapTab()` + tab 样式 | [task-02-create-tab.md](./task-02-create-tab.md) | 01 | 已完成 |
| 03 | 刷新状态图标化：迁入画布工具区 + CSS 转圈图标 + 旋转反馈 | [task-03-refresh-icon.md](./task-03-refresh-icon.md) | 02 | 已完成 |
| 04 | 版本号 / marker / 静态契约同步 + 浏览器 E2E + 部署验证 + 收口 | [task-04-contracts-and-e2e.md](./task-04-contracts-and-e2e.md) | 03 | 已完成 |

> **收口（2026-11-13）**：全量 `4571 passed / EXIT=0 / 83.01%`、单端 `628 passed / EXIT=0`、真实 Chromium E2E 18/18、部署 4×200；双签批准收口，spec 状态 `已完成`。证据见 `runs/task-04/final-verification.md`、`merge-decision.md`、`docs/sdd/reviews/048-acceptance-review.md`。

> 依赖单向 02 → 03 → 04；`frontend/literature-maps.js` 在 02 / 03 均被改动，必须串行分派并在每次回传后读回校验。
> 实施时按 `AGENTS.md` Gate 4「每任务 ≤2 个文件」拆子任务；含 `.js` / `.css` / `.html` 的改动一律分派 `frontend-dev`，评审分派 `frontend-reviewer`，单端回归分派 `frontend-tester`，验收分派 `tester`。
> 本节与下列 task 文档均为纯文档，由主会话代行创建（三处留痕：文档头部 / spec 变更日志 / 状态台账 2026-11-13 条）；**确认前不改业务代码**。
