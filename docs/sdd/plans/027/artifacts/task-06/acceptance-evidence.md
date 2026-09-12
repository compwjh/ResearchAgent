# Spec027 Task06 验收证据索引

| 证据 | 路径/命令 | 结论 |
|---|---|---|
| 复用审计 | [`reuse-audit.md`](./reuse-audit.md) | 通过；无 P0/P1 |
| 全量回归 | [`full-regression.md`](./full-regression.md) | 最终 1700 passed，退出码 0 |
| 部署 Smoke | [`deployment-smoke.md`](./deployment-smoke.md) | 18081 health/home/research 入口通过 |
| 固定样本 | `docs/sdd/plans/027/artifacts/task-05/task05-close-probe.py` | 退出码 0；真实 chat 超时如实记录 |
| 后端/前端评审 | `docs/sdd/reviews/027-tech-review.md`、`027-frontend-review.md` | 历史 P0/P1 已关闭，Task06 复用其签字结论 |

Task06 开始约 `2026-09-13T03:45+08:00`，结束 `2026-09-13T03:54:38+08:00`，约 10 分钟（含一次全量回归重跑和部署授权等待）。执行 Agent：当前执行任务 Agent；模型：自身；未调用子 Agent、网络搜索或插件工具。
