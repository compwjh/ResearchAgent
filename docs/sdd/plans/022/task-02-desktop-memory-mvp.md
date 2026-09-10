# Task 02：桌面端项目、会话与项目记忆 MVP

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Spec022 已确认；被依赖：Task03；当前状态：`待执行`

## 一句话目标

交付一个可在桌面页面现场证明“项目会话 A 写入记忆、同项目会话 B 使用记忆、未绑定会话不使用”的持久化 MVP。

## 当前证据与前置门禁

- 当前聊天无项目、会话、消息持久化或 memory checkpointer；首页实际发送到 `/api/agent/run`。
- 现有侧栏、聊天 DOM、安全 Markdown 和 SSE token writer 可复用；手机宽度下侧栏隐藏，本 Task 明确不处理手机端。
- Spec 必须已完成需求/技术评审并由用户明确确认，才可开始。

## 本任务冻结的契约

- `Project / Conversation / Message / MemoryRecord` 的稳定 ID、scope、status、schema version 和 UTC 时间。
- `data/memory/memory.sqlite3` 的 WAL、事务与 migration 机制。
- 首条消息原子建会话、已有会话发消息、消息 `before + target_chars` 分页和会话 cursor。
- SSE `meta / progress / memory / token / error / done`。
- 项目记忆注入结构、使用记录和最小处理步骤。

## 实施阶段与文件边界

1. 后端建立独立 memory 限界上下文、SQLite repository、application facade 和 API；不得复用论文/任务/KB 数据库。
2. 聊天 application 接受服务端装配的最近消息和项目记忆；现有 Agent 意图/工具编排只能通过 adapter 复用。
3. 模型输出 `explicit / ambiguous / none` 结构；明确意图保存，模糊意图等待确认，未绑定会话不得写项目记忆。
4. 前端在现有侧栏加入项目和会话列表；首页保持草稿，首次发送后进入 `/c/{id}`；历史消息按两屏字符预算向上加载。
5. 展示最小紫色处理过程和本次使用/新增记忆；切换会话取消旧 SSE。
6. 后端/前端定向测试完成后部署，按固定演示执行真实浏览器验收。

预计涉及：`backend/app/memory/**`、chat/application、API schema/route/registry、`frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 及对应测试。实际白名单在开发分派前由架构师按冻结契约细化。

## 子 Agent 分派

- backend-dev（`qwen3.8:27b-mlx`）：分批实现 schema/repository、application/API、chat adapter；每批只读本 Task、Spec 对应章节和点名文件。
- frontend-dev（`qwen3.8:27b-mlx`）：在后端契约冻结后实现桌面 UI、分页、SSE 状态和取消竞态。
- backend-tester / frontend-tester：只跑本 Task 精确测试和受影响领域回归。
- tester：部署后执行固定演示，不跑全量回归。

统一返回：状态摘要、改动文件、测试命令/退出码/数量、接口或 DOM 契约、产物路径、风险阻塞、开始/结束/耗时和主 Agent 后续动作。

## 边界与明确不做

- 不做全局记忆写入、自动扫描全部会话、摘要、完整记忆管理、项目文档或手机端。
- 不展示隐藏思维链；只显示真实处理步骤。
- 不让浏览器提交完整历史，不复制 `/api/agent/run` 的业务逻辑。
- 不执行全量回归。

## 测试与验收

- SQLite migration/WAL、并发首条消息、失败保留、流式中断、跨会话隔离、非法 ID/cursor。
- `explicit / ambiguous / none` 和分类模型不可用降级。
- 最新两屏消息、向上加载、单条超长、最多 50 条、滚动位置不跳。
- 固定演示六步全部通过；重启服务后数据仍在；未绑定负例不得出现项目记忆。
- 桌面浏览器无 console error；切换会话后旧流不得污染新会话。

## 风险、停止条件与回滚

- ID、SSE 或 schema 无法冻结时停止，不让前后端各自猜测。
- 数据写入与流式状态不一致时不得验收通过；回滚到迁移前数据库备份和旧聊天入口。
- 不修改或迁移知识库、论文目录、文章任务和浏览器 profile。

## 产出物

- `docs/sdd/plans/022/artifacts/task-02/implementation-report.md`
- `docs/sdd/plans/022/artifacts/task-02/test-report.md`
- `docs/sdd/plans/022/artifacts/task-02/review-report.md`
- `docs/sdd/plans/022/artifacts/task-02/acceptance-report.md`

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：创建纵向 MVP Task；明确桌面优先和固定演示硬门。

