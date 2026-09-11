# Spec 022 Task10 技术评审：系统规则、项目优先记忆与桌面导航修复

## 评审范围与依据

本评审为 Task10 实施前定向技术门禁，只读业务实现，不修改业务代码。依据如下：

- `docs/sdd/specs/022-project-conversation-memory.md`（SystemRule、上下文优先级、异步分析、端点、失败边界和复用/禁止约束）。
- `docs/sdd/plans/022/task-10-system-rule-project-memory-navigation.md`（阶段 A–C、文件边界、停止条件和验收标准）。
- Task09 最新交接材料：`docs/sdd/reviews/022-task09-tech-review.md`、`docs/sdd/plans/022/artifacts/task-09/backend-implementation-report.md`、`frontend-implementation-report.md`、`frontend-review-report.md`、`acceptance-report.md`。Task09 的终局追加复审为 GO，定向验收 PASS；本评审不回写或重开 Task09。
- 必要现状代码：`backend/app/memory/repository.py`、`backend/app/memory/models.py`、`backend/app/chat/application/conversation_service.py`、`backend/app/chat/application/chat_runner.py`、`backend/app/chat/application/chat_graph.py`、`backend/app/platform/ollama_direct.py`、`backend/app/api/routes_conversations.py`、`routes_chat.py`、`routes_article.py`、`routes_kb.py`、`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`。

## 结论

**NO-GO（P0=0，P1=5，P2=2；完成下列契约整改后可重新评审 GO）。**

Task10 的目标和增量范围是可实现的，Task09 已提供可复用的项目/会话 owner 隔离、稳定 cursor、浮层菜单和桌面树基础；但当前实现还没有达到 Task10 必须满足的技术前置条件。尤其是模型 adapter 尚不能传递独立 system role，异步分析和人工决策 API 仍信任模型给出的 global scope，且没有统一的系统规则读取失败接缝。若直接编码，容易出现只有会话入口生效、旧 `/api/chat` 或 `/api/kb/ask` 漏注入，或未绑定消息被手动保存为 global 的部分实现。

## 现状证据

### 1. SystemRule 数据层尚不存在

- `backend/app/memory/repository.py:36` 当前 `SCHEMA_VERSION = 5`；初始化流程只验证/迁移到 v5（约 `:111-145`），`backend/app/memory/models.py` 没有 `SystemRule` 数据类，数据库也没有独立规则表。
- 现有 `projects`、`conversations`、`memories` 均以 `owner_id` 做服务端过滤；这可复用，但不能把规则塞进 `MemoryRecord`，否则会被 `list_memories()` / `list_recall_memories()` 搜索、召回和预算逻辑消费。
- Task10 已规定 `owner_id` 主键、无历史版本、停用保留内容、清空不可恢复；实施时还必须把布尔值和空内容约束落在 SQLite/API 两层，而不只依赖浏览器。

### 2. project-first 门禁目前可被分类结果绕过

- `conversation_service.py:472-512` 的 `_decide_candidate()` 直接采用 `candidate.scope`；project scope 使用 `job.project_id_snapshot`，global scope 则直接使用 `project_id=None`。`explicit && confidence >= .85` 即可自动保存。
- `routes_conversations.py:443-490` 的人工决策同样按客户端 `save_global` 选择 global，只检查 project 保存时的项目有效性，没有重新检查原始用户消息是否明确表达“全局/所有项目/系统偏好”等范围。
- 因此即使分类器错误地将“记住我喜欢……”标成 global，绑定项目消息仍可能写 global；未绑定消息的待确认项也可能被 API 客户端直接保存为 global。模型建议的 `suggested_scope` 不能成为权限依据。

### 3. 当前模型调用没有真正的 system-role 接缝

- `chat_runner.py:76-103` 的 `run_chat()` 只有 `question`/可选字符串 `prompt`；direct 分支在 `:102` 固定构造 `[{'role': 'user', 'content': text}]`。
- `chat_graph.py:8-16` 的 graph state 只有字符串 `question`，并调用 `model.stream(state['question'])`；这不能证明或保持 system/user/assistant 的消息角色。
- 会话回答在 `routes_conversations.py:213-228` 通过 `compose_chat_prompt()` 将项目指令、记忆、RAG、历史和当前问题拼成字符串后调用 `run_chat`。这与“当前问题保持 user-role、系统规则独立 system-role”的契约不符。
- 用户可见模型入口至少包括普通 `/api/chat`（`routes_chat.py:36-100`）、Agent 的 chat 分支 `/api/agent/run`（`routes_article.py:97-151`）、项目会话 SSE（`routes_conversations.py:136-284`）和知识库 `/api/kb/ask`（`routes_kb.py:921-1026`）。Task10 阶段 C 的“所有用户可见回答入口”必须覆盖这四条；分类、摘要、embedding、reranker 等后台调用不得通过隐式全局注入拿到规则。

### 4. 失败关闭与发送时快照尚未形成统一协议

- 会话链路对记忆召回异常在 `routes_conversations.py:149-162` 明确降级为空记忆，这是 Spec 允许的“记忆召回失败不阻断聊天”；但 SystemRule 读取异常不能沿用此 catch-and-continue 行为。
- 当前没有 `get_system_rule()` 或稳定的 `SYSTEM_RULE_UNAVAILABLE` 异常/错误体。若在模型调用后才读取，可能已经发出 token；若各路由自行读取，又会产生不同的快照和错误处理。
- Task10 必须定义一个 application 层读取快照的接缝：无记录或 disabled 返回空快照；读取/迁移/锁失败统一 fail-closed；快照在模型调用前取得并贯穿该次生成，规则编辑只影响下一条消息。

### 5. Task09 前端现状仍有 Task10 指定的两处缺陷

- `frontend/app.js:951-981` 的 `openConversation()` 更新 URL、项目状态和消息，但不调用 `showView('chat')`。反之导航点击处理（约 `:2490-2505`）会清空 `projectId`/`draftProjectId`，因此不能用模拟点击“对话”修复管理页直达。
- `frontend/index.html:17` 将顶部 `⌄` 放在“项目”文字左侧；项目行在 `app.js` 的树渲染仍写入文本符号 `▰`/三角。`styles.css` 约 `:119` 与 `:144` 存在历史 `.project-item` 网格规则，必须由 Task10 明确单列覆盖；名称不可见的回归不能只用 DOM 静态存在来判断。

## 必须整改并冻结的技术契约

### T1（P1）统一 role-aware 模型接缝与入口覆盖

实施前在 Task10 交接文档/实现报告中冻结一种唯一消息形态，例如 `list[{'role': 'system'|'user'|'assistant'|'tool', 'content': str}]`，并让 `run_chat()` 显式接收它（或接收等价的 `system_messages` + user/history 参数）。禁止在各 API 路由旁新建第二个 Ollama 客户端。

必须满足：

1. direct 路径将同一消息列表原样交给 `chat_direct_stream()`；LangChain graph 使用同一列表（转换为 `SystemMessage`/`HumanMessage` 或等价受支持类型）调用 `model.stream()`；测试 fake model 必须能观察每条 role。
2. 平台固定约束和启用的用户 SystemRule 作为一个或多个 `system` 消息；当前问题是独立 `user` 消息，不能只把规则文字拼在 prompt 前面。
3. 普通 chat、项目会话、Agent chat 分支和 KB ask 均走同一 application facade/快照接缝。`download_paper_skill`、记忆分类、摘要、embedding、reranker 等后台模型调用必须显式不传用户规则。
4. 观测若记录 prompt，必须使用实际 role 列表并遵守 Spec 的脱敏/不保存完整 Prompt 约束，不能为了兼容旧测试继续伪造“只有 user”。

### T2（P1）原文 global scope 门禁与系统规则建议隔离

新增一个服务端可测试的“原始文本明确 global 范围”判断（词表/正则和否定边界写入实现报告），只允许原文通过时的 `save_global`；分类器的 global、高置信度和前端 `suggested_scope` 都不是授权信号。

- 绑定项目消息：未通过原文门禁时强制写入 `project_id_snapshot`，不能因分类器返回 global 而升格。
- 未绑定消息：未通过原文门禁时只能保持 `pending_confirmation`，人工决策保存 project 时必须选择已有 active、未归档项目；`save_global` 必须返回稳定 409（建议 `GLOBAL_SCOPE_REQUIRES_EXPLICIT_INTENT`）。
- worker 的自动保存和两个人工决策端点必须共用该门禁；项目被移动/删除时仍使用分析 job 的发送时快照。
- “设为系统规则”只产生可见建议/预填编辑器，不能进入 `create_memory()` 或直接写 SystemRule；建议结果应能由前端区分而不靠解析自由文本。

最小定向测试：分类器故意返回 global，但原文仅说“记住……”，绑定项目和未绑定两例均不得写 global；原文明确“所有项目/全局偏好”才可 global；人工 `save_global` 复用同一 job 仍受门禁；系统规则表达不产生普通 MemoryRecord。

### T3（P1）统一 SystemRule snapshot/fail-closed

在 memory application/repository 提供 owner-scoped `get_system_rule()` 和可辨识的读取失败异常；读取结果至少包含 `content`、`enabled`、`updated_at`，无记录返回空 disabled 对象。

- 规则读取、迁移失败、SQLite 锁/损坏等任何无法确定启用规则状态的情况，所有用户可见回答入口在首个模型调用/token 前返回稳定 `SYSTEM_RULE_UNAVAILABLE`；会话入口应持久化 assistant `failed` 并发送 `error.code` 与 `done(status=failed)`，旧 SSE 入口至少发送同码 error 且不调用模型。
- 读取成功后只保存本次生成的不可变快照；生成中修改不改变当前请求，下一条消息重新读取。
- 该读取不能放入 `list_recall_context()` 的“记忆召回失败可跳过”分支，也不能通过 `run_chat()` 的默认参数隐式影响后台模型。

### T4（P1）v6 迁移、owner 唯一性与 API 边界

新增独立 `system_rules` 表并将 schema 升至 v6。建议最小结构：`owner_id TEXT PRIMARY KEY`、`content TEXT NOT NULL DEFAULT ''`、`enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1))`、`updated_at TEXT NOT NULL`；不建历史版本表、不复用 memories 外键。所有读写同时带 owner 条件，禁止客户端提供 owner。

迁移与 repository 必须：

- 在现有 `initialize()` v5→v6 分支中逐语句、事务化、幂等执行；补 `_is_schema_v6()` 结构校验；保持已有 WAL/busy timeout；迁移异常回滚并 fail-closed。重复初始化、进程重启和两个 owner 并发 upsert 都要验证。
- 以 Python Unicode code point 计数 0–12,000，保存时不得截断。`PUT` 的 12,001 字符必须返回 HTTP 400（不要让 Pydantic `max_length` 先变成未约定的 422）；空内容启用返回稳定 409，停用保留内容，DELETE 清空且停用并返回 204。
- 规则表不被普通记忆列表、搜索、证据、召回预算或计数读取；补“全局 memory + system rule 各一条时普通 memory 查询/召回结果不变”的回归测试。

### T5（P1）前端导航、树布局和可访问图标

- 会话点击必须调用内部 `showView('chat')` 后再 `openConversation()`，不能触发会清空项目/草稿上下文的 nav click；绑定会话展开所属项目并高亮，未绑定会话保持最近会话可见。进入记忆页前保存筛选/滚动状态，返回后恢复，而不是重新清空或默认刷新。
- 对 `.project-item` 给出唯一最终单列规则；子会话放在项目行下方，长名/短名/空项目真实 Chromium 渲染均可见。项目折叠按钮与名称/文件夹按钮的 `aria-expanded`、hidden 状态一致。
- 顶部使用紧跟“项目”文字右侧的三角；项目行使用代码内联 SVG 闭合/打开线框文件夹，不复制附件/外部素材，不再渲染旧三角/平行四边形符号。动态名称继续 `textContent`，键盘和 reduced-motion 约束保持。

### T6（P2）任务文件边界与复用检查

- 前端改动限 `frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 及 Task10 定向前端合同；不得回写 Task09 报告或恢复旧 DOM。
- 后端实现虽可在 `backend/**` 内完成，但交接/合并时应给出精确 changed-file allowlist（预期为 memory models/repository、conversation service、chat runner/graph/direct adapter、schemas 及四个用户可见 API route 的最小改动和定向测试）。不得在路由旁复制分类器、队列或模型客户端。
- 必须复用 `ProviderRegistry`、现有异步分析 worker、`chat_runner` 和 SQLite 事务/UTC 约定；SystemRule 只作为独立规则 application 接缝，不能改造论文/知识库/Task ledger 数据库。

## 逐项验收命令与证据

实现后至少提交以下证据，且每项必须在可用依赖环境执行：

| 类别 | 验收证据 |
|---|---|
| migration/owner | 精确 pytest 覆盖 v5→v6、重复初始化、WAL、重启、双 owner 唯一性、跨 owner 读取/写入、0/12,000/12,001 Unicode、空内容启用/停用/清空；错误码和退出码记录在 `artifacts/task-10/backend-implementation-report.md`。 |
| scope gate | worker 与两个决策端点覆盖绑定/未绑定、分类器误报 global、原文明确 global、跨项目选择、系统规则建议不落 MemoryRecord；报告给出真实 pytest 命令/通过数。 |
| role/fail-closed | fake direct、fake LangChain graph、普通 chat、项目 SSE、Agent chat、KB ask 均断言 system/user 分离；后台分类等断言不含用户规则；注入失败断言无 token、稳定 `SYSTEM_RULE_UNAVAILABLE`。 |
| frontend | `node --check frontend/app.js`、Task10 DOM/XSS/resource-version 合同、`git diff --check`、全仓库冲突标记检查；真实 Chromium 覆盖从记忆页直达会话、返回筛选/滚动、绑定/未绑定高亮、长名/空项目单列、SVG 与 `aria-expanded`。 |
| regression boundary | 只跑 Task10 受影响领域的定向测试；Task08 才执行 Spec022 全量回归。Task09 的终局 GO/PASS 作为基线，不以旧报告中早期 NO-GO 追加段代替当前复审。 |

## 停止条件

出现以下任一情况立即停止验收并退回实现：

1. system rule 仍拼入 user prompt、任一用户可见入口漏注入，或后台分类/摘要模型收到用户规则。
2. 原始用户文本未明确 global 仍可由分类器/客户端把普通记忆写入 global。
3. SystemRule 读取失败后继续产生回答 token，或把规则错误吞进普通记忆召回降级。
4. v6 迁移不是幂等事务、owner 主键不唯一、超长输入被静默截断，或规则出现在普通 memory 搜索/计数中。
5. 会话直达通过导航点击清空项目上下文、项目名称在真实布局中消失，或 SVG 状态与可访问语义不一致。

## 评审元数据

- 评审角色：架构师/开发主管（临时 Luna high；仅技术评审）。
- 评审时间：2026-09-11（Asia/Shanghai）。
- 业务代码改动：无。
- 评审日志：`.codebuddy/agent-logs/spec-022/task-10/architect/20260911-163511.md`。
- 结论：**NO-GO，完成 T1–T6 的实现前契约整改后重新提交技术评审。**

## 技术复审（T1–T6 整改后）

### 固定字段

- **评审角色**：架构师/开发主管（临时 Luna high）
- **评审时间**：2026-09-11 16:47 +0800（Asia/Shanghai）
- **评审范围**：Task10 实施前技术契约复审；只读业务代码，不修改业务实现
- **复审依据**：Spec022、Task10 计划、原技术评审及当前 memory/chat/API/frontend 实现基线
- **业务代码改动**：无
- **复审报告路径**：`docs/sdd/reviews/022-task10-tech-review.md`
- **复审进展日志**：`.codebuddy/agent-logs/spec-022/task-10/architect/20260911-164428-rereview.md`
- **结论**：**GO（T1–T6 实现前契约已冻结）**
- **是否允许进入实现**：**允许**；仅在用户明确确认 Spec022/Task10 后进入实现，且仍须按 T1–T6 定向测试和验收门禁执行

### 逐项复审结论

1. **T1：GO。** 已冻结唯一 `list[{role, content}]` role-aware 载荷、system → advisory context → user 的顺序，以及四类用户可见回答入口（会话两条 POST SSE、旧 `/api/chat`、`/api/agent/run` chat 分支、`/api/kb/ask`）。分类、摘要、embedding、reranker 和论文下载等后台模型明确排除用户 SystemRule；fake direct/LangChain 捕获完整 role 列表，观测仅保留脱敏角色数量/状态。当前 `chat_runner`/graph/direct 仍为旧实现，属于待实施项，不影响契约可实现性。
2. **T2：GO。** 已冻结原文确定性 global 门禁、四条允许 global 的最小 fixture、四条拒绝升格/系统规则建议反例、绑定/未绑定 project-first 矩阵、人工 `save_global` 的 `409 GLOBAL_SCOPE_REQUIRES_EXPLICIT_INTENT`、active owner-visible project ID 选择约束。worker 与两个人工决策端点共用门禁，系统规则表达不落普通 MemoryRecord，均有定向测试映射。
3. **T3：GO。** 已冻结 owner-scoped `get_system_rule()`、空 disabled 默认值、读取/迁移/锁/损坏异常、发送时不可变快照和 fail-closed 传输语义：会话 assistant `failed`、无 token、稳定错误体中的 `code=SYSTEM_RULE_UNAVAILABLE`（沿用 `message`/`retryable` 字段约定）、`done.status=failed`；旧 SSE 入口同码且不调用模型。规则读取独立于记忆召回降级和后台模型默认参数。
4. **T4：GO。** 已冻结 v5→v6 独立 `system_rules` 表、owner 主键、SQLite 约束、幂等事务迁移/结构校验/WAL、Python Unicode code point 0/12,000/12,001 边界、400/409/204 语义、停用保留与清空停用、跨 owner 隔离，以及普通 memory 列表/搜索/证据/召回/计数不受影响的回归证据。
5. **T5：GO。** 已冻结会话直达先 `showView('chat')`、绑定/未绑定高亮与展开、管理页筛选/滚动/展开快照恢复及失败清理边界；同时冻结 `.project-item` 单列、长短空名称 Chromium 可见性、顶部右侧三角、内联 SVG `aria-hidden`、按钮 `aria-expanded`/hidden/键盘语义和 reduced-motion 验收。
6. **T6：GO。** 已冻结前端三源码及定向合同测试白名单、后端预期 changed-file allowlist 和新增文件说明义务，并要求复用 ProviderRegistry、异步分析 worker、chat_runner、SQLite 事务/UTC；禁止复制分类器/队列/模型客户端或触碰论文、知识库、Task ledger 数据库。

### 复审判定

原 NO-GO 的 T1–T6 整改项已经具体化为可分派、可实现、可自动化/浏览器验收的契约。当前代码仍明确保留原报告指出的缺口，不能将本复审 GO 误读为实现已完成；实现须在用户确认后开始，并以 Task10 定向测试、双端评审、跨端验收和部署 smoke 作为后续放行条件。未发现需要追加的 P1。
