# spec-020 导入即时反馈与 v2 索引补齐 · 任务索引

> 关联：[spec-020 零碎 bug 解决](../../specs/020-misc-bug-fixes.md)

## 目标

1. 点击"批量导入"后**立即**可见反馈（面板展开 + "正在提交 N（≥1）个导入批次…"），批次卡片创建即出现、非终态带动画。
2. 导入路径与上传路径一致，补齐 **v2 异步索引**，知识库不再长期显示"待索引"。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 02 | 前端即时反馈与批次卡片动画 | [task-02-frontend-live-feedback.md](./task-02-frontend-live-feedback.md) | 01(spec) | 已完成 |
| 03 | 导入补齐 v2 异步索引 | [task-03-v2-index-for-imports.md](./task-03-v2-index-for-imports.md) | 01(spec) | 已完成 |
| 04 | 评审、部署与复盘 | [task-04-review-deploy-retro.md](./task-04-review-deploy-retro.md) | 02,03 | 进行中 |
| 05 | 导入面板展示与跳转回归修复（BUG-03） | [task-05-import-panel-and-jump-fix.md](./task-05-import-panel-and-jump-fix.md) | 01(spec) | 已完成 |
| 06 | 导入相位死锁与重试无反馈修复（BUG-04） | [task-06-import-phase-and-retry-feedback.md](./task-06-import-phase-and-retry-feedback.md) | 05 | 进行中 |

## 执行约定

- 只以已落盘 spec/task/评审文档为输入，不依赖聊天上下文。
- 后端只碰 `backend/**`，前端只碰 `frontend/**`；跨端拆成两次分派。
- 子代理按 `progress-logging` 把进展日志写到
  `.codebuddy/agent-logs/spec-020/task-<TT>/<role>/<时间戳>.md`，回传摘要必须给日志路径。
- 后端改动后**必须重启服务**（uvicorn 无 `--reload`）才生效。
