# Task 10：系统规则、项目优先记忆与桌面导航修复

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task09、Task10 增量确认；被依赖：Task06、Task08；当前状态：`已完成`

## 一句话目标

让侧栏会话在任何工作区都能直接打开，让项目树稳定显示名称与文件夹状态，并让项目优先记忆和每用户唯一系统规则以可验证的真实 system role 生效。

## 当前证据

- `frontend/app.js` 的会话点击路径只调用 `openConversation()`；该函数加载会话、更新 URL 和消息，但不调用 `showView('chat')`，所以从记忆管理点击后仍停留在管理页。
- `frontend/styles.css` 的旧 `.project-item` 双列网格仍参与级联；展开后的子会话进入第二列并挤压第一列，项目名称虽然仍在 DOM 中却不可见。
- 顶部项目标题目前把折叠符号放在文字左侧；具体项目仍使用三角和旧装饰符号，不符合用户确认的闭合/打开文件夹语义。
- 当前异步分类器虽以 project 作为不明确 scope 的提示词回退，但仍允许模型仅凭 global + 高置信度直接保存全局记忆，没有“用户原话必须明确全局”的代码门禁。
- 现有 `MemoryRecord` 会被筛选、裁剪或读取降级，普通编辑也不支持 scope 转换；它不能承担所有回答都必须应用的最高优先级系统规则。
- 当前回答上下文最终拼成单条 user-role 文本；Spec 中声明的优先级尚未形成真正的 system-role 隔离。

## 前置门禁

- 本文、Spec022 和 README 完成落盘后先停止；需求/技术评审通过且用户明确授权实施后才可改业务代码。
- Task09 已完成并提交；本 Task 不篡改其执行结果，只在新任务中承接现场新增范围。
- 开发期只跑本 Task 定向测试；全量回归保留至 Task08。
- Task10 只完成桌面体验，Task06 后续复用相同 API/状态完成手机端。

## 数据与接口增量

### `SystemRule`

- 每个 owner 最多一条当前记录：`owner_id` 主键、`content`、`enabled`、`updated_at`。
- `content` 最多 12,000 个 Unicode 字符；超过限制返回 400，不截断。
- 不建历史版本表。覆盖不可恢复；停用保留内容；清空删除内容并停用。
- 与 `MemoryRecord` 完全隔离，不进入普通记忆列表、计数、搜索、证据、召回或 token 裁剪。
- SQLite 迁移必须幂等、事务化并保持 WAL；不得改造论文、知识库或 Task ledger 数据库。

### API

- `GET /api/system-rule`：读取当前规则；无记录时返回空、disabled 的稳定对象。
- `PUT /api/system-rule`：覆盖内容与 enabled；校验长度、空白和 owner。
- `PATCH /api/system-rule`：只切换 enabled；空内容不能启用，返回 409。
- `DELETE /api/system-rule`：由前端二次确认后清空并停用，返回 204。
- 启用规则读取失败时，用户可见回答入口返回稳定 `SYSTEM_RULE_UNAVAILABLE`，不得静默忽略。
- 不新增 global↔project 普通记忆转换 API。

### 实施前冻结的技术契约（T1–T6）

#### T1：唯一 role-aware 模型接缝与入口清单

- 模型调用统一接收 `list[{role: system|user|assistant|tool, content: str}]`；禁止在路由旁复制 Ollama 客户端。
- system 消息顺序固定为：平台固定规则、启用的用户 SystemRule；随后是可选的 project instructions、global/project advisory memory、RAG/历史摘要。当前问题始终是独立 user 消息。
- 必须覆盖四类用户可见回答入口：会话两条 POST SSE、旧 `/api/chat`、`/api/agent/run` 的 chat 分支、`/api/kb/ask`。后台 memory classification、summary、embedding、reranker 和论文下载模型调用显式不带用户 SystemRule。
- fake model 测试必须捕获完整 role 列表；观测不得保存完整 Prompt，只记录脱敏 role 数量与状态。

#### T2：global 原文门禁与 project-first 矩阵

- 服务端以原始用户文本作确定性授权判断，分类器 `scope`、confidence、前端 `suggested_scope` 均只能是建议。
- 允许 global 的最小 fixture：`全局记住：以后所有项目都遵守先给结论`、`所有对话都使用中文`、`remember this as a global preference`、`make this a preference for every project`。
- 必须拒绝升格的 fixture：`记住我喜欢简洁回答`、`以后这个项目先给结论`、`记住杀杀杀`、`设为系统规则`（后者只生成 SystemRule 编辑建议）。
- 绑定项目 + 非明确 global：强制写入 `project_id_snapshot`；未绑定 + 非明确 global：保持 `pending_confirmation`，人工 `save_global` 返回 `409 GLOBAL_SCOPE_REQUIRES_EXPLICIT_INTENT`。
- `save_project` 只接受 owner 可见、active、未归档项目 ID；不接受项目名或自由文本。

#### T3：SystemRule snapshot 与 fail-closed

- application 层提供 owner-scoped `get_system_rule()`，返回 `content/enabled/updated_at`；无记录返回空 disabled，读取、迁移、锁或损坏导致无法确定状态时抛出可识别异常。
- 快照必须在首个模型调用前取得并贯穿本次生成。启用规则读取失败时：会话 SSE 持久化 assistant `failed`，发送 `error.code=SYSTEM_RULE_UNAVAILABLE` 和 `done.status=failed`，绝不发送 `token`；旧入口返回同码错误且不调用模型。
- SystemRule 读取不得放入“记忆召回失败可跳过”的降级分支，也不得通过 `run_chat()` 默认参数隐式影响后台模型。

#### T4：SQLite v6 与 API 边界

- v5→v6 新增 `system_rules(owner_id TEXT PRIMARY KEY, content TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), updated_at TEXT NOT NULL)`；迁移逐语句事务化、幂等、失败回滚，补结构校验，保持 WAL/busy timeout。
- 服务端按 Python Unicode code point 计数；0–12,000 允许保存，12,001 返回 400，不能让校验层改成未约定的 422；空内容启用返回 409，停用保留内容，DELETE 清空并停用。
- 普通 memories 查询、召回、证据、计数、搜索中不得出现 SystemRule；跨 owner 读写必须为空或稳定 404/403，不得接受客户端 owner。

#### T5：导航、状态快照和可访问图标

- 会话点击先调用内部 `showView('chat')` 再 `openConversation()`，禁止模拟导航项点击；进入管理页前保存 `memory` 的 scope/status/project、滚动 offset 和项目展开快照，返回后恢复；打开失败只清理本次目标，不清空既有快照。
- `.project-item` 唯一单列；项目名对短、长、空项目均可见；顶部三角位于“项目”右侧。文件夹 SVG 为 `aria-hidden=true` 装饰，项目按钮负责 `aria-expanded`、名称、键盘 Enter/Space 和焦点。
- 真实 Chromium smoke 必须覆盖从记忆页直达绑定/未绑定会话、返回筛选/滚动、长名/空项目和文件夹开合。

#### T6：变更文件白名单与复用

- 前端只允许 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 和 Task10 合同测试。
- 后端预期只改 `backend/app/memory/{models.py,repository.py}`、`backend/app/chat/application/{conversation_service.py,chat_runner.py,chat_graph.py}`、`backend/app/platform/ollama_direct.py`、`backend/app/api/{schemas.py,routes_conversations.py,routes_chat.py,routes_article.py,routes_kb.py}` 及 Task10 定向测试；如需新增文件，必须在报告说明原因。
- 必须复用 ProviderRegistry、现有异步分析 worker、chat_runner、SQLite 事务/UTC 规范；不得新增分类器、队列、模型客户端或改动论文/知识库/Task ledger。

## 冻结实现阶段与文件边界

### 阶段 A：桌面导航与项目树

- 只在既有 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 和相关前端测试内修复。
- 会话统一打开路径先切换到 chat 视图，再加载目标会话；不得模拟点击“对话”导航，因为该导航会清空项目/草稿上下文。
- 打开绑定会话时展开所属项目并高亮；打开未绑定会话时保持“最近会话”可见；返回管理页恢复原筛选和滚动位置。
- `.project-item` 显式重置为单列，子会话不得挤压项目名称。
- 顶部显示 `项目 ▼`，三角紧跟文字右侧；具体项目使用项目内联 SVG 的闭合/打开线框文件夹，不直接复制附件素材，不再显示项目三角或平行四边形符号。
- 文件夹和名称共享展开/收起行为；会话点击才切换对话。

### 阶段 B：项目优先记忆

- 在既有异步分析 service/repository/API 上增加服务端门禁，不新建第二套分类器或任务队列。
- 绑定项目会话：普通“记住……”及相近语义固定落入 `project_id_snapshot`；只有原始用户文本明确表达全局范围，才允许 global。
- 未绑定会话：普通记忆成为待确认项，前端提供已有未归档项目选择与忽略；明确全局意图才允许 global。
- “设为系统规则”只产生可见建议并预填规则编辑器，不得自动写 `SystemRule`。
- 不处理全局记忆降为项目记忆，也不复制、迁移或转换既有记录。

### 阶段 C：系统规则与真正 system role

- 在记忆数据库/repository/application/API 中实现唯一 `SystemRule`，沿用既有 owner、事务、UTC 和稳定错误体约定。
- 扩展模型调用抽象，使平台规则与用户系统规则进入 system-role 消息，用户问题保持 user-role；不得只改变字符串拼接顺序冒充 system role。
- 覆盖普通聊天、项目聊天和 Agent 工具编排后的最终用户可见回答；后台分类、摘要、embedding、reranker 不注入。
- 每条消息发送时取得规则快照；编辑后从下一条消息生效，不改变正在生成或历史回答。
- 全局记忆管理页顶部新增独立系统规则卡片：最高优先级标记、启用状态、更新时间、编辑、停用、清空；普通全局记忆列表位于其下。
- 处理过程只在实际启用并注入时新增已完成步骤“已应用系统规则”；未启用时不显示。
- 对话中识别到修改系统规则意图时，回答后提示并可打开预填编辑器，用户保存前不得生效。

## 子 Agent 分派

### 后端开发 Prompt 边界

- 角色：`backend-dev`；读取 Spec022、本 Task、`backend/app/memory/**`、会话 API/service、模型调用 adapter 与相关测试。
- 允许修改：`backend/**` 与本 Task 后端测试；禁止修改前端、其他 Spec、论文/知识库实现。
- 必须返回：schema 迁移、API、scope 门禁、system-role 调用链、稳定错误与精确测试证据。

### 前端开发 Prompt 边界

- 角色：`frontend-dev`；读取 Spec022、本 Task、Task09 前端报告和当前三份前端源码。
- 允许修改：`frontend/**` 与本 Task 前端测试；禁止修改后端或复制第二套状态。
- 必须返回：会话直达、单列项目树、SVG 状态图标、系统规则卡片、项目选择确认和资源版本证据。

### 评审与测试

- backend-reviewer：核对 owner 隔离、迁移幂等、project-first 原文门禁、真正 system role、失败关闭与后台任务隔离。
- frontend-reviewer：核对视图切换不清空上下文、项目名可见、SVG/键盘语义、系统规则确认、XSS 与资源版本。
- backend/frontend tester：只跑本 Task 受影响领域；tester 汇总跨端定向验收。Task08 才执行全量回归。
- 每个角色必须写固定报告到 `artifacts/task-10/`，并返回结果、改动文件、命令/退出码、风险、时间与主 Agent 后续动作。

所有实际分派 Prompt 必须原样写入对应 implementation-report：包含角色和模型、只读文件、允许修改文件、禁止操作、完成状态、验证命令、报告路径与固定回传字段。

## 测试与验收标准

- 从记忆管理点击绑定或未绑定会话，均一次进入正确对话；URL、项目展开、高亮、管理页返回状态正确。
- 展开空项目、短名项目和长名项目时名称均可见；项目容器单列，文件夹开/关状态与 `aria-expanded` 一致。
- 顶部三角在“项目”文字右侧；具体项目不存在三角和平行四边形；SVG 不复制附件文件。
- 已绑定项目的普通记忆意图只能写当前项目；明确全局意图才可写 global；未绑定普通意图必须等待项目选择。
- 对话不能未经确认改写系统规则；普通全局记忆与系统规则互不计数、搜索或覆盖。
- 系统规则 CRUD、空内容、12,000/12,001 字符、启停、不可恢复清空、owner 隔离和 SQLite 重启恢复通过。
- 所有用户可见回答入口收到独立 system-role；后台模型不收到。规则读取失败时无回答 token 且返回 `SYSTEM_RULE_UNAVAILABLE`。
- 规则变更只影响下一条消息；处理中显示一次“已应用系统规则”，未启用时不显示。
- 定向 pytest、`node --check`、前端合同、`git diff --check` 和冲突标记检查通过；部署后执行真实桌面 Chromium smoke。

## 风险、停止条件与回滚

- 若 system rule 仍与 user prompt 拼接、仅靠分类模型猜 global、或读取失败后继续回答，立即停止验收。
- 若会话直达清空项目上下文、项目名仍会消失、SVG 状态与可访问语义不一致，立即停止验收。
- 若模型 adapter 不能表达 role，先扩展既有抽象；不得在 API 路由旁新建第二套模型客户端。
- 回滚只撤销 Task10 迁移/API/UI 增量，恢复 Task09 已提交基线；不 reset、stash、clean 或覆盖用户修改。

## 产出物

- `artifacts/task-10/backend-implementation-report.md`
- `artifacts/task-10/frontend-implementation-report.md`
- `artifacts/task-10/backend-review-report.md`
- `artifacts/task-10/frontend-review-report.md`
- `artifacts/task-10/acceptance-report.md`

## 执行结果

已完成。需求评审与技术复审均为 GO；后端、前端 reviewer 均为 GO；Task10 定向验收 PASS。

- 后端定向测试：64 passed。
- 前端 Task10/受影响合同：44 passed；JavaScript 语法检查通过；5 个 Node 合同通过。
- 运行时：`GET /api/health` HTTP 200，首页 HTTP 200，`GET /api/system-rule` 返回稳定 disabled/空内容对象。
- Chromium 无头 DOM 检查通过：唯一项目树标题、顶部“项目 ▼”、悬浮操作按钮、内联文件夹 SVG、项目名称和记忆治理入口均存在；未发现旧常驻创建表单或旧项目选择器。
- 本轮未运行全量 pytest；Task08 继续负责 Spec022 最终全量回归和收口。

报告：`docs/sdd/plans/022/artifacts/task-10/acceptance-report.md`、`docs/sdd/plans/022/artifacts/task-10/backend-review-report.md`、`docs/sdd/plans/022/artifacts/task-10/frontend-review-report.md`。

## 变更日志

- 2026-09-11：用户通过 Grilling 确认全部边界；不做全局记忆降级，不保留系统规则历史版本，Task09 已完成记录不回写，新增 Task10 承接增量。
