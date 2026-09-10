# spec-021 论文导入异步化与进度反馈 · 任务索引

> 关联：[spec-021 论文导入异步化与进度反馈](../../specs/021-paper-import-async-progress.md)

## 目标

1. 论文批量导入**入队即返回**：`POST /api/papers/imports` 只创建批次（`state=queued`）并立即返回，后台执行，不再占用 HTTP 请求线程下载/建索引。
2. 导入**进度真实可见**：前端沿用 2.5s 轮询，逐条展示 `queued / downloading / validating / indexing / completed / failed / waiting_login / cancelled` 与失败原因。
3. 环境故障**可诊断**：知识库存储被另一个实例独占时返回 `KB_STORAGE_LOCKED` 与可行动文案，不再一律压成 `KB_IMPORT_FAILED`。
4. 重试**粒度可选**：整批重试之外新增单条目重试路由；两者都入队后立即返回，由轮询呈现进展。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-021 | [spec 本体](../../specs/021-paper-import-async-progress.md) | — | 待确认 |
| 02 | 后端：批次入队即返回 + 后台单飞执行 + 启动恢复 | [task-02-backend-async-batch-runner.md](./task-02-backend-async-batch-runner.md) | 01 | 已完成（待评审） |
| 03 | 后端：`KB_STORAGE_LOCKED` 语义、单条目重试路由与唯一索引冲突可读化 | [task-03-backend-error-semantics-and-item-retry.md](./task-03-backend-error-semantics-and-item-retry.md) | 02 | 进行中 |
| 04 | 前端：真实轮询进度、取消与软超时提示 | [task-04-frontend-progress-cancel-timeout.md](./task-04-frontend-progress-cancel-timeout.md) | 03 | 待执行 |
| 05 | 评审、部署与复盘 | [task-05-review-deploy-retro.md](./task-05-review-deploy-retro.md) | 02,03,04 | 待执行 |

## 执行约定

- 只以已落盘 spec/task/评审文档为输入，不依赖聊天上下文。
- 后端只碰 `backend/**` 与后端测试，前端只碰 `frontend/**`；跨端拆成两次分派。
- 子代理按 `progress-logging` 把进展日志写到 `.codebuddy/agent-logs/spec-021/task-<TT>/<role>/<时间戳>.md`，回传摘要必须给日志路径。
- 后端改动后**必须重启服务**（uvicorn 无 `--reload`）才生效。
- 不改 `paper_import_batch_store.py` 的 CAS / 租约语义；不引入 MQ / Celery 等外部队列。

## 前置条件（由用户决策，非本 plan 自动执行）

- 本机当前存在同项目两个 uvicorn 实例（8123 / 8002），共用 `data/kb/qdrant`；**只有释放占用后，运行时验收（导入真正成功）才可能通过**。停哪个实例由用户决定，本 plan 不自动 kill 任何进程。
