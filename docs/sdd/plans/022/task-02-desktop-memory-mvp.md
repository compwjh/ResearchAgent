# Task 02：桌面端项目、会话与项目记忆 MVP

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Spec022 已确认；被依赖：Task03；当前状态：`已完成`

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

### 实现前契约性澄清（需求/技术评审 R1–R4、T1–T7）

- 正式演示按“创建项目 → 会话 A 写入偏好 → 显示新增记忆 → 同项目会话 B 使用 → 未绑定会话负例 → 刷新/重启恢复”执行，每步均须有可观察结果。
- `explicit` 写入项目记忆并发送 `memory(status=saved)`；`ambiguous` 不入库，仅发送 `memory(status=needs_confirmation)`；`none` 不写入也不发送新增记忆。分类器不可用时聊天继续，记忆标记未分析/未保存。
- 项目创建后，A、B 显式绑定同一项目；负例保持 `project_id=null`。客户端不得提交完整历史或越权指定记忆范围。
- 数据库固定为 `data/memory/memory.sqlite3`，schema version=1，独立于论文/知识库/文章任务库；启用 WAL、busy timeout、幂等迁移、事务和服务端 owner 隔离。
- 首条消息按“校验 → 事务创建会话、用户消息、assistant pending → 提交 → 流式执行”顺序；SSE 固定 `meta → progress/memory/token → done`，失败/中断持久化 assistant 非 completed 状态。
- 消息和会话列表使用服务端校验的不透明游标；消息按 `created_at/message_id` 倒序累计 `target_chars`，单批最多 50 条，不截断单条消息。
- 新入口只新增 `/api/conversations/messages` 及其会话消息接口，旧 `/api/chat`、`/api/agent/run` 保持兼容；聊天编排通过 adapter 复用，不复制论文/知识库逻辑。

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

### 固定演示验收映射

1. 创建“记忆测试”项目，确认返回稳定 `project_id`，侧栏可见项目。
2. 在绑定项目的会话 A 发送“以后回答时先给结论，再补充解释”，确认首条消息后才创建会话，并收到 `memory(status=saved)`。
3. 打开项目会话 B 发送普通问题，确认回答上下文使用该项目记忆，并收到 memory 使用事件。
4. 创建未绑定会话发送同一问题，确认不出现该项目记忆或项目指令。
5. 刷新页面并重启服务，使用稳定会话 URL 重新加载消息、项目和记忆。
6. 构造 `ambiguous`、`none` 和分类器不可用场景，确认分别提示待确认、不写入和降级继续聊天。

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

已完成。桌面端项目会话与项目记忆最小纵向闭环已交付并通过验收：项目创建、惰性首条消息建会话、SSE 处理过程、明确记忆写入、同项目会话召回、未绑定会话隔离、历史游标加载和服务重启后的 SQLite 持久化均有自动化或受控运行时证据。Task02 不包含全局记忆治理、自动候选整理、项目文档或移动端。

- 精确测试：35 passed；旧聊天兼容回归：16 passed。
- 前端语法：`node --check frontend/app.js` 通过；`git diff --check` 通过。
- 受控部署 smoke：health=200、项目创建=201、SSE 事件顺序符合契约、记忆 saved/used 均出现、临时项目删除=204。
- 验收结论：`docs/sdd/reviews/022-acceptance-review.md` 为 PASS。

## 变更日志

- 2026-09-11：创建纵向 MVP Task；明确桌面优先和固定演示硬门。
- 2026-09-11：Task02 实现、精确测试和受控部署验收完成，状态更新为已完成；全量回归按 Task08 执行。
