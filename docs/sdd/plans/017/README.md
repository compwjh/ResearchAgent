# Spec017 任务索引：后端限界上下文彻底重构

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md)

| 任务 | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](task-02-contract-baseline.md) | 建立迁移清单与对外契约基线（硬门禁） | 01 | 已完成 |
| [03](task-03-api-platform.md) | 拆分 API 与平台装配（含设置拆分、composition root、跨域 port） | 02 | 已完成 |
| [05](task-05-knowledge-base.md) | 迁移知识库模块（先提供 KB application facade） | 03 | 已完成 |
| [04](task-04-paper-discovery.md) | 迁移论文发现模块（消费 KB port） | 05 | 已完成 |
| [06](task-06-article-chat.md) | 迁移文章助手与聊天模块 | 03 | 已完成（含 2026-09-08 收口修复） |
| [07](task-07-remove-legacy-boundaries.md) | 删除旧结构并验证边界 | 04, 05, 06 | 已完成 |
| [08](task-08-review-deploy-retro.md) | 评审、部署与复盘 | 07 | 已完成（重新验收） |

**执行顺序**：`02 → 03 → 05 → 04 → 06 → 07 → 08`。Task04 依赖 Task05 的 KB application contract；Task06 在目录不重叠时可与 Task04 并行，但不得同时移动同一个 settings repository 或数据文件。所有任务必须串行协调文件移动，同一文件只归属一个任务。
## 2026-09-08 审计收口

审计发现旧 `agents/article_agent.py`、`core/config.py`、`api/routes.py` 兼容 facade 和未接线的 PaperImportPort 与原 Spec 边界不一致；本轮已完成修复并重新回归。定向回归 `131 passed`，全量回归 `653 passed, 38 subtests, 5 warnings`。详细证据见 [`017-remediation-acceptance-review.md`](../../reviews/017-remediation-acceptance-review.md)。
