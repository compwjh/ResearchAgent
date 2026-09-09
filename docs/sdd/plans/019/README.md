# spec-019 论文导入状态反馈一致性 · 任务索引

> 关联：[spec-019](../../specs/019-paper-import-status-feedback.md)

## 目标

让"添加到知识库"的整条链路只用**一个可信的状态来源**表达进展：提交、进行中、部分成功、完成、失败各有确定且互不覆盖的表达；后端不再把未预期异常一律伪装成"导入服务暂时不可用"；检索上下文不可用时给出可行动指引。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 02 | 只读定位"搜索会话不存在"真实触发路径 | [task-02-diagnose-search-id.md](./task-02-diagnose-search-id.md) | 01(spec) | 已完成 |
| 03 | 前端导入状态反馈统一（单一状态源） | [task-03-unify-import-status.md](./task-03-unify-import-status.md) | 02 | 已完成 |
| 04 | 后端导入错误语义修正（消除 503 兜底） | [task-04-backend-error-semantics.md](./task-04-backend-error-semantics.md) | 02 | 已完成 |
| 05 | 评审、部署与复盘 | [task-05-review-deploy-retro.md](./task-05-review-deploy-retro.md) | 03,04 | 已完成 |

## 执行约定

- 只以已落盘 spec/task/评审文档为输入，不依赖聊天上下文。
- 后端改动只碰 `backend/**`，前端只碰 `frontend/**`；跨端拆成两次分派。
- 每个子代理按 `progress-logging` 要求把进展日志写到
  `.codebuddy/agent-logs/spec-019/task-<TT>/<role>/<时间戳>.md`，回传摘要必须给日志路径。
- 进展日志属运行产物（已 gitignore），不进提交。
