# Spec 022 Task09 技术评审：桌面项目树与会话菜单重构

## 评审范围与代码依据

- 后端项目列表目前只映射持久字段，`_project_payload()` 未含 `last_activity_at`，见 `backend/app/api/routes_conversations.py:42-44`；repository 也只按项目自身 `updated_at` 查询/编码游标，见 `backend/app/memory/repository.py:501-513`。
- 现有会话列表已支持按 `project_id`（含 `null`）和稳定 cursor 查询，见 `backend/app/api/routes_conversations.py:340-345`、`backend/app/memory/repository.py:604-617`；其按 `updated_at DESC, conversation_id DESC` 排序。
- 现有移动复用 `PATCH /api/conversations/{id}`，而 repository 在事务中验证 active 项目、确认历史策略、更新 binding cutoff 并清理旧项目 evidence，见 `backend/app/memory/repository.py:549-597`。这条路径是 Task09 唯一允许的移动写入路径。
- 前端当前用单一 `conversationState.projectId` 驱动所有列表（`frontend/app.js:67-81,861-876`），项目列表本地按 `updated_at` 排序（`frontend/app.js:743-749`），尚未建树或支持项目内 10 条分页。

## 结论

**GO（技术门禁通过；以下契约必须先冻结到实现/测试交接）。**

无需新增表或改变项目、会话、记忆/RAG 语义。`last_activity_at` 可以作为列表 read model 由单条聚合查询提供；树展示继续消费现有 project 与 conversation 身份，移动继续消费既有 PATCH 原子事务。因此不存在安全或数据一致性阻塞项。

## 冻结的接口与数据模型契约

### T1 `last_activity_at` read model

1. `GET /api/projects` 每个对象增加 ISO-8601 UTC 的只读 `last_activity_at`，值为项目 `updated_at` 与该项目 **status != `deleted`** 的会话最大 `updated_at` 的较晚者；无会话时等于项目 `updated_at`。
2. 不新增列、不修改 `projects` schema，也不改变 `Project` 的领域写入语义。可用 repository projection/包装类型承载该只读字段；API 序列化必须始终输出该字段。
3. 该计算必须在 SQLite 聚合查询中完成，按 `owner_id` 与 `project_id` 关联，禁止前端逐项目拉取会话或 N+1 查询。建议将会话筛选置于 `LEFT JOIN ... AND c.status != 'deleted'`，以保留没有会话的项目。
4. 现有 cursor 以项目 `updated_at` 编码（`backend/app/memory/repository.py:505-512`）。若把 API 服务端页序改为 `last_activity_at`，cursor 的 keyset 字段、并列 `project_id` 和测试必须同时迁移；若保持 API 页序，则前端只能在完整已加载集合中使用本地“最近更新”排序。不得混用新排序字段与旧 cursor。

### T2 会话树与分页

- 未绑定列表调用 `GET /api/conversations?limit=20`，不得传伪造空字符串项目 ID；项目节点按需调用 `GET /api/conversations?project_id={id}&limit=10`，将每个节点的 `items/cursor/loading/error` 单独保存。
- 当前 API 对 `project_id` 校验项目存在（`backend/app/memory/repository.py:604-616`）。项目归档视图不应借 active 树请求绕过此限制；归档列表状态须显式，且恢复后再进入普通树。
- 每条会话在同一次渲染中只能由一个 owner node 产生。PATCH 成功的响应是唯一可采信的 `project_id`，之后原节点删除、目标节点插入或失效重取；失败与 abort 一律保留 API 前快照。

### T3 菜单、对话框与 DOM 安全

- 动态项目名、会话标题、检索结果必须继续以 `textContent` 写入；现有渲染在 `frontend/app.js:754,807-809` 已遵循此模式，Task09 不得以 HTML 字符串拼接替换。
- 浮层必须由集中 menu controller 管理：保存触发按钮、弹层、打开方向和关闭 cleanup；外部 pointer/click、Escape、动作完成、视图切换都关闭，Esc/外部关闭后焦点回到触发器。
- `dialog.showModal()` 已用于新建项目（`frontend/app.js:1337`；DOM 在 `frontend/index.html:401-407`）。Task09 可复用该平台机制或新增用途明确的 dialog；禁止使用原生 `prompt/confirm`。移动选择应是受控搜索/选择列表，提交值固定为 `project_id`，不能从自由文本解析项目名。
- 由于列表容器裁剪溢出，菜单不得继续作为 `.project-list` / `.conversation-list` 的绝对定位子项（裁剪证据：`frontend/styles.css:51,59,117`）。portal/overlay 需按触发器 `getBoundingClientRect()` 定位，并以 viewport 边界决定向上展开。

### T4 不可回退的服务端安全契约

- 保留 `update_conversation()` 的 project owner/active 验证、`confirm_move`、`memory_binding_at`/`memory_binding_message_id` 和 project evidence 清理（`backend/app/memory/repository.py:560-594`）；前端的复选框只映射 `include_prior_history` 或 `from_binding`，不能改写现有消息或 memory evidence。
- 保留删除会话不联动记忆的语义；保留项目删除先解除知识库文档关联、失败即不删项目的 fail-closed 行为（`backend/app/api/routes_conversations.py:103-114`）。Task09 的确认文案不得承诺相反行为。

## 风险分级

- **P1：排序/游标错配。** `last_activity_at` 是新计算排序依据而现 cursor 仍绑定 `projects.updated_at`。实施前须选择并测试 T1 的一种一致策略；否则跨页会重复或遗漏项目。
- **P1：移动 UI 提前乐观更新。** 当前 PATCH 可能因确认、归档项目或不存在项目返回 404/409（`backend/app/api/routes_conversations.py:356-361`）。成功响应前移动 DOM 会造成跨项目展示与真实绑定不一致。
- **P1：overflow 裁剪与焦点泄漏。** 单纯提高 `z-index` 无法越过滚动祖先；实现必须有顶层 overlay，并在触发元素卸载、项目折叠或视图切换时安全关闭。
- **P2：归档状态混入。** 现 repository `list_conversations()` 排除 deleted 但包含 archived（`backend/app/memory/repository.py:615`），前端过滤是当前行为。树/归档视图必须明确以状态分区，不能让归档项出现在普通项目子树。

## 最小测试门槛

1. Repository/API：含无会话、active/archived/deleted 会话、同时间并列的项目；断言 `last_activity_at` 正确、无 N+1 行为证据、cursor 无重复/遗漏且 payload 恒含字段。
2. PATCH：移动至 active 项目、取消前零请求、无效/归档目标失败后 UI 快照不变、两种历史策略均保留现有 binding/evidence 规则。
3. 前端契约：不存在旧选择器/表单/兼容监听；每项目 10 条 cursor，未绑定 20 条 cursor，单项目展开、空项目入口、移动后单一 DOM owner/highlight。
4. 浏览器 smoke：底部翻转且滚动裁剪边缘可见，鼠标/键盘统一，外部点击/Esc 关闭并恢复焦点，归档恢复保留展开与滚动状态。
5. `node --check frontend/app.js`、相关前端契约、后端精确测试和 `git diff --check` 全部为零退出；不运行全量回归。

## 子代理允许修改文件

- **backend-dev：** 仅 `backend/app/memory/repository.py`、必要的 `backend/app/memory/models.py`、`backend/app/api/routes_conversations.py` 和对应精确测试；禁止 schema migration、删除/移动语义重写、RAG/记忆 worker 修改。
- **frontend-dev：** 仅 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 和 Task09 定向前端契约测试；禁止 `backend/**`、mobile Task06、Task05 turn/processing/memory-analysis DOM 契约。
- **backend-reviewer/frontend-reviewer/testers：** 只输出各自评审/验收材料及最小测试；不代行实现。

## 评审记录

- 角色：架构师/开发主管（临时 Terra medium；仅文档评审）。
- 结论：**GO**；T1 的 cursor/排序一致性是实施前必须写入 implementation handoff 的 P1 约束。
- 时间：2026-09-11。
