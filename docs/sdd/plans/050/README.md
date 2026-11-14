# Spec050 任务索引

关联：[Spec050](../../specs/050-agent-safety-and-factuality.md) · [三轮讨论记录](grilling-decisions.md)

当前状态：**实施中**（2026-11-15 按用户指示由「待确认」补正；用户 11-14 已以明确指令授权实现，当时未同步状态）。Task02 技术盘点与 Task03/04 已完成实现、定向验收与真实部署 API E2E；Task05 第一次交付验收、Task06–09 待执行。Gate 1/2 正式评审文档与验收签字仍未产出，不倒签通过；本表不代表 Spec 级验收签字。第一次交付止于 Task05，第二次交付止于 Task09。

> `runs/task-02/*`、`piguard-training-evidence.md`、`grilling-decisions.md` 中出现的「Spec050 待确认」是各文档产出当时的状态快照，属历史证据，不随本轮状态补正回写。

| Task | 任务 | 依赖 | 状态 |
|---|---|---|---|
| 01 | [Spec 草案](../../specs/050-agent-safety-and-factuality.md) | — | 已起草 |
| 02 | [入口覆盖与可行性](task-02-contract-and-feasibility.md) | 01 | 已完成（技术盘点） |
| 03 | [执行防护与确认后端](task-03-action-guard-runtime.md) | 02 | 已完成（实现 + 验收） |
| 04 | [防护活动与确认界面](task-04-guard-activity-ui.md) | 03 | 已完成（实现 + 验收） |
| 05 | [第一次交付验收](task-05-first-delivery-acceptance.md) | 03、04 | 待执行 |
| 06 | [RAD 与公开对照契约](task-06-rad-and-benchmark-contract.md) | 02、05 | 待执行 |
| 07 | [事实核验与回答发布](task-07-factuality-verification.md) | 02、05 | 待执行 |
| 08 | [PIGuard 接入与公开实测](task-08-security-adapter-and-benchmark.md) | 06、07 | 待执行 |
| 09 | [第二次交付与最终收口](task-09-final-acceptance-and-release.md) | 05、06、07、08 | 待执行 |
