# Spec 022 技术评审：Task02 桌面端项目记忆 MVP

## 评审范围与代码依据

本次只核对 Spec022、Task02、计划 README、AGENTS.md 以及当前聊天入口的必要代码：

- `backend/app/api/routes_article.py`：现有 `/api/agent/run` 是文章意图/普通聊天混合入口，并以 `TaskStore` 持久化文章任务。
- `backend/app/api/routes_chat.py`：现有 `/api/chat` 以 `StreamingResponse` 输出流式事件。
- `backend/app/api/common.py`：`stream_event()` 已提供 `data: JSON\\n\\n` 的 SSE 帧格式。
- `backend/app/api/routes.py`、`backend/app/main.py`：路由注册和 FastAPI lifespan 入口。
- `backend/app/chat/application/chat_runner.py`：现有模型流式 adapter，可作为聊天编排接缝复用。
- `frontend/app.js`：当前聊天用 `fetch` + `ReadableStream` 解析 SSE；`frontend/index.html` 已有侧栏、聊天区和模型选择器。
- `backend/app/platform/bootstrap.py`：已有 provider registry，可作为新 memory repository 的组合根测试替换点。

当前未发现 `backend/app/memory/**`、会话/项目仓储或相关 API；因此 Task02 是新增独立领域切片，不能假设已有记忆数据库接口。

## 结论

**通过（实施前冻结下列技术契约；不改变 Spec022 范围）。**

数据模型、接口方向、SSE 事件类别、分页目标、项目隔离和回滚边界已足以拆分后端/前端实现。实现前必须将以下可执行约束写入 Task02 的冻结契约或实现报告；否则前后端容易各自创建第二套会话入口或不同的游标/状态语义。

## 必须冻结的技术契约

### T1 独立存储与迁移

- 新库固定为 `data/memory/memory.sqlite3`，不复用论文发现、文章任务、知识库 metadata/Qdrant 或 Langfuse。
- 首版 schema version 固定为 `1`；至少有 `projects`、`conversations`、`messages`、`memories`、`memory_evidence`、`processing_steps` 表，并声明主键、外键、唯一约束和删除语义。
- 开启 WAL、busy timeout 和事务；迁移必须幂等。启动迁移失败应 fail-closed 到新会话入口，不损坏或覆盖其他数据库。
- 本地用户身份在 v1 使用一个服务端常量/配置值，不能接受客户端 `owner_id` 作为权限依据。

### T2 唯一消息入口与 SSE

- 新入口使用 Spec 规定的 `POST /api/conversations/messages` 和 `POST /api/conversations/{id}/messages`；旧 `/api/chat`、`/api/agent/run` 保持回归兼容，不在两处复制会话持久化逻辑。
- 由于浏览器当前使用 `fetch` 读取 POST 流，新接口可沿用 `StreamingResponse`，但每帧必须是 `data: {"type":...}\\n\\n`，并固定发送 `meta → progress/memory/token → done`，错误发送 `error` 后结束。
- `meta` 必须包含 conversation/message IDs；`done` 必须给出最终消息状态；模型异常、客户端断开和取消分别映射到 `failed`/`interrupted`，不得遗留永久 `streaming`。
- 客户端切换会话时必须取消旧请求；服务端不能把旧流事件写入另一会话。

### T3 惰性创建与失败持久化顺序

1. 校验输入、项目归属、模型可用性和记忆范围；失败时不创建空会话。
2. 在一个事务中创建 conversation、user message 和 pending assistant message，提交后才开始流式执行。
3. 每个 token 只更新当前 assistant message；正常结束置 `completed`，异常保留已生成内容并置 `failed` 或 `interrupted`。
4. 记忆写入、evidence 和 processing step 必须在同一 memory repository 体系内，不能依赖浏览器 localStorage。

### T4 项目记忆隔离

- 召回查询必须同时限制 `owner_id`、`scope=project`、`project_id` 和可用状态；未绑定会话传入 `project_id=null` 时不得查询任意项目记忆。
- 记忆写入必须由服务端根据 conversation 的 project 关系决定 scope，客户端不能直接指定另一个 project ID。
- Task02 只保存 `explicit` 项目记忆；`ambiguous` 只产生 `needs_confirmation` 可见事件，不入库；`none` 不写入。
- 新会话 B 的“使用记忆”应在 SSE `memory` 事件中返回稳定 memory ID、scope 和脱敏 statement，并产生 `last_used_at` 更新；不得回传完整隐藏 Prompt。

### T5 分页与游标

- 会话列表与消息列表使用不透明、服务端校验的稳定游标；禁止用前端数组下标或可伪造 offset 作为权限/顺序依据。
- 消息接口按 `created_at/message_id` 的稳定倒序从最新向前累计 `target_chars`，达到预算后完整包含最后一条，最多 50 条；`before` 继续取更早消息。
- `target_chars` 必须有服务端默认值、最小值和上限；非法/跨会话游标返回稳定 400/404，不回退为全量历史。
- 前端首次加载最新消息，向上滚动加载旧批次并保持锚点；首版不要求移动端布局。

### T6 处理过程和模型分类

- 分类器只输出结构化 `explicit/ambiguous/none` 及 statement/scope/confidence/current_task；解析失败或分类模型不可用必须降级为“不保存记忆、聊天继续”，并记录真实 failed/skipped step。
- `processing_steps` 的 label/summary 是真实阶段摘要，不是模型隐藏推理；UI 只展示这些字段。
- 现有 `chat_runner` 通过 adapter 接入；不得把论文任务、下载或知识库索引逻辑复制进新会话模块。

### T7 组合根与前端接缝

- 在 `backend/app/platform/bootstrap.py` 注册无业务依赖的 provider，在 API/application 层构造 memory repository；测试可 override。
- 新路由只接收已定义 schema，统一错误码/可重试字段；路由注册必须落在现有 `routes.py`，并保持旧路由可用。
- 前端复用现有安全文本渲染和流式 writer；会话 URL 使用 `/c/{conversation_id}`，任何用户内容写入 DOM 都必须走 textContent/现有安全 Markdown 路径。

## 建议的最小测试矩阵

1. migration 幂等、WAL、重启读取和损坏/锁冲突 fail-closed。
2. 两个并发首条请求不产生重复会话或空会话。
3. explicit/ambiguous/none 的写入与 SSE 事件符合 T6。
4. 同项目召回、未绑定负例、跨项目 ID/owner 越权均隔离。
5. 模型异常、流式中断和切换会话后状态与内容不串线。
6. 消息 `target_chars`、最多 50 条、非法 `before` 和滚动锚点。
7. `/api/chat` 与 `/api/agent/run` 的既有测试继续通过。

## 风险、停止条件与回滚

- 若实现需要更改既有 `/api/agent/run` 的响应结构或删除旧入口，应停止并回到 Spec 修订；Task02 只允许新增唯一会话入口并复用 adapter。
- 若 SQLite 迁移无法独立于论文/知识库数据库，或项目隔离只能靠前端过滤，应停止技术实现。
- 若无法区分客户端断开与模型失败，至少必须持久化部分 assistant 内容和非 completed 状态，不得声称恢复能力已满足。
- 回滚时只关闭新会话入口并恢复旧聊天入口；不得删除或覆盖论文知识库及既有用户文件。

## 评审记录

- 评审角色：架构师/开发主管评审（本次为定向门禁评审，不修改业务代码）。
- 评审结论：通过（实施前完成 T1–T7 的契约性冻结）。
- 评审时间：2026-09-11。
