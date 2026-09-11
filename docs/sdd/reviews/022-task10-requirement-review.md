# Spec 022 Task10 需求评审：系统规则、项目优先记忆与桌面导航修复

## 固定字段

- **评审角色**：架构师（临时 Luna high）
- **评审时间**：2026-09-11 16:33 +0800
- **评审范围**：Task10 需求门禁；只读业务代码，不修改业务实现
- **结论**：**GO**
- **报告路径**：`docs/sdd/reviews/022-task10-requirement-review.md`
- **进展日志**：`.codebuddy/agent-logs/spec-022/task-10/architect/20260911-1633-requirement-review.md`

## 评审依据

- `docs/sdd/specs/022-project-conversation-memory.md`：Task10 增量目标、数据模型、优先级、边界、产品使用步骤与验收方式。
- `docs/sdd/plans/022/task-10-system-rule-project-memory-navigation.md`：当前证据、阶段 A/B/C、API 增量、停止条件和定向验收标准。
- `docs/sdd/plans/022/README.md`、仓库 `README.md`：Task 依赖、里程碑、部署和回归边界。
- `docs/sdd/plans/022/artifacts/task-09/acceptance-report.md`：Task09 定向验收 PASS（47 项后端/前端合同测试通过；全量回归仍属于 Task08）。
- `docs/sdd/reviews/022-task09-requirement-review.md`、`022-task09-tech-review.md`：Task09 已冻结的树、菜单、移动和归档边界。
- 当前实现的必要只读证据：
  - `frontend/app.js:951-988` 的 `openConversation()` 更新 URL/消息，但未调用 `showView('chat')`；`frontend/app.js:2495-2504` 的“对话”导航还会清空项目/草稿上下文。
  - `frontend/app.js:795-815` 仍以文本 `▰` 表示项目图标，项目头包含旧的独立 toggle；`frontend/styles.css:119` 的旧双列 `.project-item` 规则未被 Task09 后续规则完整重置，确有把子会话放入第二列的回归风险。
  - `backend/app/chat/application/conversation_service.py:470-496` 当前可直接采用分类器返回的 `global` scope；缺少“原始用户文本明确表达全局意图”的服务端硬门禁。
  - `backend/app/chat/application/chat_runner.py:76-108` 当前以单一文本调用模型；`backend/app/api/routes_conversations.py:213-228` 当前通过 `compose_chat_prompt()` 后调用 `run_chat()`，尚未形成独立 system-role 消息。

## 结论与放行条件

Task10 的目标、用户价值和增量边界清晰，依赖 Task09 已完成，四条新增用户旅程均可映射到 DOM、URL、API、持久化记录或模型调用载荷等可观察证据。阶段 A（导航/布局）、阶段 B（project-first 记忆）和阶段 C（唯一 SystemRule）均没有要求重建论文知识库、文章任务或第二套会话 API，符合 Spec022 的复用与硬性禁止边界。

本报告 **GO 不等同于用户已确认实施**。仍须先完成 Task10 技术评审，并在用户明确确认 Spec022/Task10 后才可进入实现。实现交接前应把下列 P1 契约写入 Task10 实现/测试报告；这些是使现有目标可重复验收的必要澄清，不是范围扩张。

## 需求完整性评估

### 1. 会话直达与管理页返回

需求已明确“从记忆管理或其他工作区点击会话，一次切回对话、打开稳定 URL、展开所属项目并高亮；返回管理页恢复筛选和滚动位置”。当前缺陷证据与 Task10 阶段 A 一致，Task09 的会话行已统一调用 `openConversation()`，因此可在既有路径内修复。

可测证据应至少包括：

- 绑定会话：`#memory-view`（或任一非 chat 视图）点击会话后，`#chat.hidden === false`、地址为 `/c/{id}`、所属项目展开、对应行 `aria-selected=true`。
- 未绑定会话：同样进入 chat，项目上下文保持未绑定，最近会话行高亮。
- 返回管理页：打开前的 scope/status/project 筛选、列表滚动位置和展开项目快照恢复；不得通过模拟“对话”导航清空草稿或项目上下文。

### 2. 项目树、图标与名称布局

需求同时冻结了信息层级和视觉语义：唯一“项目 ▼”标题、项目只允许整体折叠、具体项目用自绘闭合/打开文件夹 SVG，点击文件夹或名称均展开/收起，项目名称在空/短/长名称下都可见。Task09 已通过基本项目树与菜单验收，但 Task10 的当前 CSS/DOM 证据确实留下双列覆盖和旧符号问题，因此增量目标明确且可独立验收。

可测证据应包括：项目头/子列表是单列布局；三种名称长度渲染后有可见文本；文件夹 `aria-expanded` 与图形状态同步；顶部三角位于文字右侧；项目节点无三角、平行四边形或 `▰` 旧装饰符号；SVG 来自项目代码而非附件素材。

### 3. project-first 记忆

需求边界完整覆盖了绑定项目、未绑定会话、明确全局意图、项目快照、用户确认和“不做 scope 转换”。这与 `MemoryAnalysisJob.project_id_snapshot` 和现有异步结果区相容：回答不等待分类，分析结果绑定发送时快照，会话移动不能改变正在运行任务的 scope。

可测证据应包括服务端持久化结果而非只看 UI：绑定项目普通“记住……”即使分类器返回 `global` 也只能产生该项目记录；未绑定普通记忆意图只能是待确认，必须选现有 active 项目后才保存；原文明确全局意图才允许 global；跨项目选择只能来自 owner 可见的 active 项目；项目删除/快照失效不改写到其他项目。

### 4. 唯一、无历史的 SystemRule

需求已定义唯一键、内容上限、启停/覆盖/清空语义、与普通 MemoryRecord 隔离、下一消息生效、发送时快照、真正 system role、后台模型不注入和读取失败 fail-closed。CRUD 及 12,000/12,001 字符、重启、owner 隔离均能写成自动化验收。

需要在实现前明确“所有用户可见回答入口”的清单和每个入口的可观察载荷；当前仓库至少存在会话消息、旧 `/api/chat`、文章 Agent 的普通聊天分支和知识库问答入口。否则“所有入口”无法被验收总控完整证明。会话 SSE 中“已应用系统规则”步骤应与真正注入绑定，而旧入口若没有处理过程 UI，应验证模型调用载荷而不是凭空新增展示。

## 验收可测性映射

| 需求 | 最小验收证据 | 判定标准 |
|---|---|---|
| 管理页会话直达 | 浏览器视图状态、`/c/{id}` URL、项目展开、高亮、返回快照 | 绑定/未绑定均一次进入正确会话；不清空项目/草稿状态 |
| 项目名称与图标 | DOM/CSS 合同 + Chromium 三种长度截图/可见性断言 | 单列；名称可见；顶部 `项目 ▼`；SVG 状态与 `aria-expanded` 一致 |
| 绑定项目记忆 | 分析 job/item 与 `memories` 持久化行 | 普通意图只到 snapshot 项目；模型伪造 global 不能越权 |
| 未绑定记忆 | analysis item `pending_confirmation` + 项目选择 API 请求 | 不自动 global；选 active 项目后仅写所选项目，或忽略 |
| SystemRule CRUD | API + SQLite 重启 + owner 隔离 | 0–12,000 通过；12,001 拒绝；停用可恢复；清空后内容为空且 disabled、无历史 |
| 真正 system role | 模型 adapter 捕获的 `[{role, content}, ...]` | 平台规则/SystemRule 为 system；用户问题为 user；后台分类/RAG 等无 SystemRule |
| 失败关闭与快照 | 注入读取失败的 SSE/旧入口响应及并发修改测试 | 无回答 token；稳定 `SYSTEM_RULE_UNAVAILABLE`；当前回答用发送快照，下一条才用新值 |
| 规则处理步骤 | 会话 processing_steps/SSE | 仅启用且实际注入时出现一次“已应用系统规则”；未启用不出现 |

## 风险分级与具体修订建议

### P0

- **无 P0。** 当前没有发现会阻止目标在既有领域边界内实现的致命范围冲突、数据源复用冲突或不可回滚要求。

### P1（实现前必须落盘冻结）

1. **全局意图判定不可只依赖分类器输出。** 当前分类器可能返回 `scope=global` 并在高置信度下自动保存。请在 Task10 实现/测试契约中规定一个服务端确定性门禁：只有原始用户文本命中明确的全局范围表达（例如“全局”“所有项目”“以后所有对话/系统偏好”等经产品确认的中文/英文 fixture）才允许 global；模型 scope 只能作为建议，不能提升权限。补充正例、项目语境下的反例和“设为系统规则”反例矩阵。

2. **SystemRule 的入口覆盖和 adapter 载荷未枚举。** 将“所有用户可见回答入口”具体列为会话两条 POST、旧 `/api/chat`、文章 Agent 的 chat 分支、知识库问答（若其属于用户可见回答）；规定统一的 role-aware adapter 输入、system 消息顺序和每个入口的测试捕获点。明确后台分类、摘要、embedding、reranker 不接收该规则。

3. **读取失败的传输语义需固定。** 明确 conversation SSE 在读取启用规则失败时发送 `error.code=SYSTEM_RULE_UNAVAILABLE`、不发送任何 `token`、assistant 持久化为 `failed`、`done.status=failed`（以及 HTTP/旧入口对应状态）；这样“fail-closed”才可由测试稳定判定，而不是只检查一条错误文案。

4. **管理页返回状态的保存边界需固定。** 指定由前端工作区状态保存 `memory` 的 scope/status/project、滚动 offset 和项目展开快照，或指定 History API/state 方案；规定打开失败、刷新和删除会话时的恢复/清理行为。当前目标虽可理解，但未指定实现可观察点，容易出现“只切回 chat、不恢复筛选”的半完成。

5. **SystemRule 处理步骤的适用范围需澄清。** 要求会话 SSE/processing_steps 出现该步骤，同时又要求旧回答入口全部注入。请在 Task10 验收中区分：会话入口检查步骤；无处理过程契约的旧入口只检查 role payload，避免为兼容入口引入第二套 processing 记录。

### P2（建议补充，避免边界解释不一致）

1. **字符上限定义。** 将“12,000 个 Unicode 字符”明确为服务端 Python Unicode code point（或产品指定的用户可见字符/ grapheme）并补充中英文、emoji、组合字符和空白边界用例；拒绝时保持不截断。

2. **文件夹 SVG 可访问语义。** 固定 SVG 为装饰性 `aria-hidden=true`，按钮/项目行承担 `aria-label` 和 `aria-expanded`；这样视觉图形和可访问状态不会各自漂移。验收加入键盘 Enter/Space 和焦点回归。

3. **未绑定项目选择的一致输入契约。** 明确 `save_project` 必须携带服务端验证的 `project_id`，不接受名称或自由文本；选择列表只展示 active、owner 可见项目，并在项目删除/归档竞态下返回稳定错误且不改变候选项状态。

4. **Task09 回归边界显式保留。** Task09 验收报告为定向 PASS 而非全量回归；Task10 定向测试应继续覆盖 47 项相关合同的关键子集，Task08 再执行全量回归和最终部署，不得在 Task10 报告中把定向通过写成 Spec022 收口。

## 明确不做与依赖核对

- 不做手机端布局/入口（由 Task06 复用同一 API 与状态）。
- 不新增第二套分类器、队列、会话消息入口或模型客户端；不改论文下载、知识库索引/RAG、文章任务或 Agent 安全边界。
- 不做普通 global↔project 记忆迁移、复制、降级，不保存 SystemRule 历史版本；聊天识别“设为系统规则”只能建议/预填，须用户显式保存。
- Task09 的项目活动排序、cursor、菜单 portal、移动事务和归档语义继续作为前置契约；Task10 只承接已确认的四项增量。
- 用户确认前保持 Spec022 `待确认`，不得因本需求评审 GO 直接修改业务代码或将状态改为 `已确认`。

## 评审记录

- **结论**：**GO**（需求门禁通过；按本报告 P1/P2 契约补齐后进入技术评审/用户确认流程）。
- **P0/P1/P2 摘要**：P0 0 项；P1 5 项；P2 4 项。
- **业务代码改动**：无。
- **下一步**：由技术评审核对上述入口/adapter、scope 门禁、错误体和持久化边界；用户明确确认后，再按 Task10 阶段 A/B/C 分派实现与定向测试。
