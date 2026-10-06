# SPEC-037 首屏就绪缺口与 UX bug 合集

## 状态

**当前状态：已完成**（Bug 1-10 全部完成并验证）

> 本 spec 经 grill with docs（第一轮 5 问）确定边界；用户已答：Q1=A（并补充「恒定上下文必须计入统计」），Q2/Q3/Q4/Q5 按架构师建议执行。

## 一句话目标

补上 `feat/startup-readiness`（已合入，`beba8b9`）遗留的首屏"看得见、但也得看得懂"缺口，并修复 4 个让用户困惑的 UX bug：**上下文模块始终可见且计入恒定上下文**、**知识库计数不再先显示 0**、**v2 索引失败态可读且能自愈**、**审批卡片与侧边栏三点菜单不再出现点了没反应的可点元素**；并追加三项对话布局调整（**模型选择器靠右**、**聊天面板限高约两个屏幕**、**滚动时左侧栏固定**）。

## 背景与事实核查（已逐条定位到代码行）

`feat/startup-readiness` **确实已合入 main**（`beba8b9` + `1c4d10f` merge），它落地了后台预热、`/api/ready`、模型数徽标 spinner、上下文 `is-loading` 转圈态。但覆盖面存在明确缺口，本 spec 处理的是**缺口与回归**，不是重做它。

| 现象 | 已核实根因 |
|---|---|
| 打开网站上下文模块整个看不到 | `frontend/app.js:884` 无会话时 `classList.toggle('is-idle')` → `styles.css:39` `visibility:hidden`。转圈态（`showContextUsageLoading`，`app.js:837`）只在**加载会话**时启用 |
| 知识库计数先 0 后变准 | `frontend/index.html:398` 硬编码 `<span id="kb-count">0</span>`；model-count 有 spinner 处理，kb-count 漏了 |
| v2 索引无法重建 | **实测可重试成功**（2026-09-16 手动重试 3 篇：2 篇 indexed、1 篇 indexing、failed 归零）。历史 failed 是环境故障期（Qdrant 本地锁冲突 / 代际门禁未 finalize）留下的**陈旧失败态**，错误原文 `索引任务异常终止：INDEX_FINALIZE_REQUIRED` 对用户不可读，且失败态永不自愈 |
| 计划审批卡片显示"已approved"却仍可点 | 两处渲染点 `research-tasks.js:866-872` 与 `app.js:2010-2014`：非 pending 时**仍渲染**批准/拒绝按钮（仅 `disabled`），而 `research-session-command:disabled` **无任何禁用视觉样式**；状态文案为模板串 `` `已${approval.status}` `` → 拼出"已approved" |
| 本地工作区三点菜单点了没反应 | `frontend/index.html:116` `<span class="more">···</span>` 是**纯装饰 span**：无事件、无 `aria-haspopup`、无菜单。对比 `app.js:2488/2521` 的会话/项目菜单是真 `<button>` + 处理函数 |

## 修复范围（10 项，互相独立，可单独验收）

> Bug 1-5 已于 2026-09-16 完成并部署验证；Bug 6-8 为用户追加的三项对话布局诉求（原拟另立 spec-039，按用户裁决**并入本合集**）；Bug 9 为运行中暴露的 fd 泄漏（按用户裁决**并入本合集**并由主会话修复）。

### Bug 1：上下文模块始终可见，且必须计入恒定上下文

**根因**：无会话 → `is-idle` → 组件整体 `visibility:hidden`；且 `compute_context_usage`（`routes_conversations.py:389-431`）覆盖不到"恒定上下文"。

**关键口径（用户明确要求）**：不存在"没有上下文"的状态——**系统规则、USER.md/MEMORY.md（用户记忆）、项目 MD** 是恒定注入的上下文，必须计入占比与明细。

**方案**：
1. 前端：移除"无会话即隐藏"逻辑，组件永远可见。三态明确——
   - 加载中：`is-loading` + spinner（沿用 `app.js:837` 既有实现）；
   - 有数据：显示真实百分比（含只有恒定上下文时的基线百分比）；
   - 失败：`is-error` + `—` + 重试按钮（沿用 `app.js:858` 既有实现）。
   **无会话不再等于 0% / 隐藏**，而是渲染"仅恒定上下文"的基线占比。
2. 后端：`compute_context_usage` 必须与真实装配同源计入恒定段。已核实 `routes_conversations.py:409-413` 调用 `compose_chat_prompt` 时**未传 `system_rule`**，而真实对话路径（`app.js` 对应后端 `routes_conversations.py:796`）传了 `system_rule=user_memory`——dry-run 存在漏算。实现时须补齐，并复核 `compose_chat_prompt` 内部对文件记忆（USER.md / MEMORY.md / 项目 MD）的读盘是否已在 dry-run 中执行，未执行则一并纳入。
3. 明细（breakdown）中恒定段须有可读中文 label（复用 `_CONTEXT_BREAKDOWN_LABELS`，`routes_conversations.py:359-368` 已有 `file_memory`＝"文件记忆 (USER.md / MEMORY.md)"；系统规则段如缺失则新增）。

**边界**：详见下方「边界」第 6 条关于 `CONTEXT.md` 的核实要求。

### Bug 2：知识库计数首屏加载态

**方案**：`#kb-count` 对齐既有 model-count 模式（`styles.css:53` `.async-slot-spinner`、`#model-count.model-count-fade`）——
- 初始渲染占位/转圈，**不再硬编码 0**；
- 数据到达后淡入真实数字；
- 加载失败显示 `!` + 可点重试。

### Bug 3：v2 索引失败态可读 + 一次自愈

**方案**：
1. 前端：失败卡片展示可读文案（`INDEX_FINALIZE_REQUIRED` →「索引代际尚未完成提交，请重试重建」类中文）与显式「重试」入口，不展示原始错误码。
2. 后端：服务启动时把 `status=failed` 的 chunker 任务自动重新排队，**每文档每 chunker 限 1 次**，避免风暴；重试失败仍保留 failed 态，不无限循环。

**前提说明（必须写进实现注释）**：本项根因是**环境故障**遗留状态，不是切分/索引逻辑 bug；不得把它当成 parser 或 chunker 缺陷去重构。

### Bug 4：审批卡片交互收口

**方案**：两处渲染点（`research-tasks.js`、`app.js`）**一并**修改——
- 非 pending 时**不渲染**批准/拒绝按钮（而非 disabled）；
- 状态文案改中文映射：`approved`→已批准、`rejected`/`declined`→已拒绝、`superseded`→已被新版本替代（参考 `research-session-ui.js:94` 已有映射，须统一）；
- 保留 card 的 `data-status` 着色钩子（`styles.css:197-198`）。

### Bug 5：侧边栏三点菜单

**方案**：把 `index.html:116` 的死 `<span>` 换成真 `<button>`（`aria-haspopup="menu"`、`aria-expanded`），对齐会话/项目菜单的既有实现（`app.js:2488/2521`）弹出菜单，含两项起步：
- **刷新模型列表**（复用 `ollama.refresh_available_models` 对应接口）；
- **打开模型库视图**（导航到既有模型视图）。

### Bug 6：对话框模型选择器靠右

**根因**：`styles.css:34` `.composer-footer` 已是 `justify-content:flex-end`，但 `index.html:149-151` 把 `.model-picker`（`#model-select`）放在 `.composer-footer` 的**第一个子元素**（spec-035 Bug5 移入时保留原顺序），故实际渲染在最左。

**方案**：给 `.composer-footer .model-picker` 加 `margin-left:auto`，使其在底部行靠右呈现。**不改** `#model-select` 的 id、事件绑定与模型联动逻辑（spec-035 契约）。

### Bug 7：聊天面板随回答无限变长，限高约两个屏幕

**根因**：`styles.css:11` `.chat-panel` **只有 `min-height:510px`、没有 `max-height`**；`.messages` 虽有 `overflow-y:auto` 但未被限高，内容增长把整页撑长。

**方案**：为聊天面板新增高度上限（约两个屏幕高度，以 `vh` 表达并扣除 topbar/内边距等既有占位），超出后**内部滚动**、页面不再无限变长。保留既有 `min-height`（含 `.workspace.has-started` 下的 `calc(100vh - 162px)`），只新增上限、不降低下限。限高须加在正确层级，避免同时出现页面滚动条与内部滚动条。

### Bug 8：滚动右侧内容时左侧栏跟着动

**根因**：`styles.css:5` `.app-shell` 为 grid 两列，`.sidebar`（第 6 行）**未设置 sticky**，页面变长后随页面滚出视野。

**方案**：让 `.sidebar` 在页面滚动时保持可见（`position:sticky` + 自身高度与内部滚动）。不得破坏窄屏（≤760px）既有行为——`styles.css:27` 窄屏下 `.app-shell{display:block}`、`.sidebar{display:none}`，移动端抽屉逻辑保持不变。侧边栏内容超出视口时在**侧边栏内部**滚动，不挤压主区。

### Bug 9：ResearchStore 的 SQLite 连接泄漏，耗尽文件句柄导致功能大面积"空白"

**现象**：Ollama 正常，但 `/api/health` 返回 500、模型库空白。实测该进程打开 **88,778 个句柄**，其中 **88,514 个是 REG 且去重后仅 87 个路径，88,778 个全部指向 `data/research/research.sqlite3`**。新进程启动后仅 144 个句柄。

**根因**：`backend/app/research/infrastructure/research_store.py:797` 的 `_connect()` 返回裸 `sqlite3.Connection`，而**全部 89 个调用点**都写作 `with self._connect() as conn:`。`sqlite3.Connection` 作为上下文管理器**只管理事务（提交/回滚），不关闭连接**——这是 Python 经典陷阱。全文件 **0 处 `.close()`**，连接只能等 GC 回收，实测并未及时回收，fd 被耗尽后任何新建 `httpx.Client`（`ssl.create_default_context` → `certifi`）都抛 `OSError: [Errno 24] Too many open files`，于是所有出站 HTTP 失败，表现为"模型库/健康检查莫名空白"。

**方案**：把 `_connect()` 改为 `@contextmanager`，在 `finally` 中显式 `connection.close()`，并在内部保留 `with connection:` 以**维持原有事务语义**（成功提交、异常回滚）。因 89 个调用点**全部**是 `with ... as` 形式，此改动单点生效、无需改任何调用点。

### Bug 10：侧边栏「最近会话 / 工作区」文字重叠（**Bug 8 实施引入的回归**）

**现象**（用户截图 + Playwright 复现）：选中会话后，侧边栏「工作区」标签跑到「最近会话」上方，两者重叠。

**根因**：Bug 8 给 `.sidebar` 加 `max-height:100vh` 后，侧边栏成为**受约束的 flex 容器**；内容总高（738px）超过视口（700px）时 flex 开始压缩子项，而 `.conversation-memory`（承载「项目树 / 最近会话」）自带 `min-height:0`（styles.css:85，为既有滚动设计），于是**被压缩到 0 高**，其内容溢出绘制到下方「工作区 / 对话」区块上。修复前实测：`工作区 top=178 < 最近会话 top=197`。

**方案**：`.sidebar > * { flex-shrink: 0 }`——禁止侧边栏子项被 flex 压缩，内容超高一律走**侧边栏内部滚动**（这正是 Bug 8 的本意）。修复后实测：`工作区 top=412` 在 `最近会话 top=298` 下方、无重叠；`.conversation-memory` 恢复 234px；侧边栏 `scrollHeight 972 > clientHeight 700` 走内部滚动；sticky 与上下文模块契约均未回退。

---

## 数据模型

| 字段 | 类型 | 约束 |
|---|---|---|
| `context-usage.used_tokens` | int | 现含恒定上下文后必然 > 0（仅当系统规则与文件记忆同时为空时才可能趋近 0） |
| `context-usage.breakdown[].kind` | string | 新增/沿用恒定上下文段标识（`file_memory` 已存在；系统规则段缺则补） |
| `catalog_papers` 不涉及 | — | Bug 3 改的是 KB 文档的 chunker 任务状态，不动 paper_discovery 目录表 |

> 本 spec **不新增数据表**，不引入迁移。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `GET /api/conversations/{id}/context-usage` | conversation_id | 同现状，但 `used_tokens` 恒定段计入、`breakdown` 含恒定段 | 现状不变（503 依赖不可用） |
| `POST /api/kb/documents/{id}/reindex` | `{chunker:"v1"\|"v2"\|"all"}` | 契约不变（202 queued） | 契约不变 |
|  Bug 5「刷新模型列表」 | 无 | 复用现有模型列表刷新接口，**不新增端点** | — |

## 边界（每条之后会变成一条测试）

1. 上下文模块在**无会话**时仍可见（`visibility` 非 `hidden`），且不显示 spinner、不显示 0%（除非恒定上下文确实为空）。
2. 上下文模块在**加载中**显示 spinner 与「加载中」文案；10s 未收敛转「仍在加载…」（沿用 `app.js:850`）。
3. 上下文加载失败显示 `—` 与重试按钮，点击可重新拉取。
4. 恒定上下文（系统规则 / USER.md / MEMORY.md / 项目 MD）计入 `used_tokens`，且出现在 `breakdown` 中带中文 label。
5. `#kb-count` 首屏不为空字符串也不为 0 硬编码；数据到达后显示真实条数；接口失败显示 `!` 且可重试。
6. **待核实（必须在实现时确认，不得假定）**：根目录 `CONTEXT.md` 是否被后端装配进 prompt。已核实后端经 `MarkdownMemoryStore` 读取 `USER.md` / `MEMORY.md` / 项目 MD（`conversation_service.py:459`、`markdown_store.py:441`），**未发现读取 `CONTEXT.md` 的代码**。若确未注入，则不计入本 spec 的占比统计，并在评审记录中写明结论；用户如需计入，须先由后端装配它（届时应另立 spec）。
7. v2 重建失败卡片显示中文可读文案与重试入口，**不直接展示 `INDEX_FINALIZE_REQUIRED` 原文**。
8. 服务启动时 `status=failed` 的文档按「每文档每 chunker 最多 1 次」重新排队；重试后仍失败保持 failed 且不再次自动重试。
9. 审批卡片在 `status != pending` 时**不存在**批准/拒绝按钮（DOM 中不可见），状态文案为「已批准 / 已拒绝 / 已被新版本替代」之一，不出现 `已approved` 字样。
10. 侧边栏三点菜单为 `<button>`、带 `aria-haspopup="menu"` 与 `aria-expanded`，点击有可见反馈；"刷新模型列表"与"打开模型库视图"两个入口可用。
11. `#model-select` 仍在 `.composer-footer` 内，id / 事件绑定 / 模型联动逻辑不变，且底线布局下**靠右**呈现。
12. 聊天面板具备 `max-height` 且**不小于**既有 `min-height`（510px）；长对话下页面整体高度收敛、消息区内部可滚动，`.messages` 保留 `overflow-y:auto`（不出现内容被裁且无法滚动）。
13. 页面滚动时 `.sidebar` 保持可见；窄屏（≤760px）行为不变（仍隐藏、抽屉仍可用）；侧边栏内容超高时在侧边栏内部滚动。
14. 上下文占比模块（Bug 1 落地的三态）在本次布局调整后**仍始终可见**——不得回退该契约。
15. 改动涉及 `styles.css` / `index.html` 时，`index.html` 中对应资源 `?v=N` 必须递增。
16. `ResearchStore._connect()` 在**正常返回与抛异常两种路径**下都必须关闭连接（`finally` 保证）。
17. 连续 N 次（如 ≥200）调用 `ResearchStore` 的读/写方法后，进程对该 sqlite 文件持有的句柄数**不随调用次数增长**。
18. 事务语义不变：成功仍提交、异常仍回滚（现有 41 处 `conn.commit()` 与 `with conn:` 行为不得改变）。
19. 选中会话且视口较矮时，侧边栏内「最近会话」「工作区」等区块**不得重叠**（`.conversation-memory` 高度不得被压缩为 0）。
20. 侧边栏内容超过视口时在**侧边栏内部**滚动，sticky 固定与上下文模块可见性不受影响。

## 明确不做（防自由发挥）

- 不重构 `compose_chat_prompt` / `MarkdownMemoryStore` 的读取逻辑；Bug 1 只补 dry-run 的参数与来源，不改装配语义。
- 不修改 token 预算与自动压缩阈值（spec-025 契约不变），不改 `CHAT_TOTAL_TOKEN_BUDGET` / `CHAT_COMPACT_TRIGGER_RATIO`。
- 不新增加密/鉴权/新数据表；不引入新的前端框架或构建步骤（保持无构建静态前端）。
- Bug 3 不重试成功状态的任务，不做无限重试，不引入队列框架。
- 不动会话列表/项目树的既有菜单实现，Bug 5 只处理侧边栏身份区这一个 `"···"`。
- 不顺带修 Reranker 缺失（`degraded=true`，属独立环境缺口）。
- Bug 6 不改模型选择的**逻辑**（列表来源、默认值、能力联动），只改对齐；不把 `#model-select` 移回 `chat-header`。
- Bug 6/7/8 不动消息渲染、Markdown 解析、SSE 流与任何后端逻辑；不改侧边栏导航项内容、交互与菜单（Bug 5 成果保持）。
- 不引入新色系/新字体/新框架/构建步骤；限高优先纯 CSS 实现，不引入 JS 计算高度。
- 不调整 `.topbar`、`.breadcrumb` 等既有结构。
- Bug 9 **只修连接不关闭的问题**：不重构 `ResearchStore` 的表结构/SQL/业务逻辑，不改成连接池或全局单连接，不改其它模块的连接管理（本次仅 research 模块实测存在该泄漏）。

## 产品使用步骤（由产品经理在 spec 确认后填写）

- 步骤 1：
- 步骤 2：
- 验收场景：

## 执行配置（由架构师填写，落盘可查）

> 按 `AGENTS.md` 实测修订：全部角色 agent 的 `model` 均为 `hy3`，必须与 `.codebuddy/agents/*.md` 逐字一致。架构师行填「自身」，不写死模型代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验与收口 |
| 产品经理 | `hy3` | 32k | `Task(doc-updater)` | 梳理产品使用步骤、用户旅程、验收场景 |
| 开发主管 | `hy3` | 32k | `Task(architect)` | 需求/技术评审、任务拆分、代码审查、合并裁决 |
| 初级开发 | `hy3` | 32k | `Task(frontend-dev)` / `Task(backend-dev)` | 已确认范围内的编码实现（严格按端拆分） |
| 测试 | `hy3` | 32k | `Task(frontend-tester)` / `Task(backend-tester)` / `Task(tester)` | 测试编写/执行、验收、Bug 复现 |

## 任务计划

> 本 bug 合集的 5 项已在本 spec「修复范围」中逐条写清根因、方案与验收；详细的执行步骤在 spec 确认后拆分到 `docs/sdd/plans/037/`（届时补寫 task 文件，避免 spec 未经确认就产出将被改写的实施文件）。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-037（含 grill 边界确认） | 本文件 | — | 完成 |
| 02 | 后端：context-usage 计入恒定上下文（同源修复） | [`task-02`](../plans/037/task-02-context-usage-constant-sections.md) | 01 | 待执行 |
| 03 | 前端：上下文模块始终可见 + KB 计数加载态 | [`task-03`](../plans/037/task-03-context-meter-and-kb-count.md) | 01 | 待执行 |
| 04 | 前端：审批卡片交互收口（两处渲染点） | [`task-04`](../plans/037/task-04-approval-card-interaction.md) | 01 | 待执行 |
| 05 | 前端：侧边栏三点菜单改真按钮 | [`task-05`](../plans/037/task-05-sidebar-profile-menu.md) | 01 | 待执行 |
| 06 | v2 重建失败态：中文文案 + 启动自愈 | [`task-06`](../plans/037/task-06-v2-reindex-failure-recovery.md) | 01 | 待执行 |
| 07 | 回归、部署与复盘 | [`task-07`](../plans/037/task-07-regression-deploy-retro.md) | 02-06 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/037-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/037-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/037-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-16 | 架构师(自身) | 编写本 spec：经 grill with docs 确定 5 项边界；逐条核实 `feat/startup-readiness` 已合入及其覆盖缺口，并把 `#kb-count` 硬编码 0、`--- 三点菜单为死 span`、审批卡片两处渲染点、v2 陈旧失败态等根因落到具体代码行 |

---

**六条自检**：①每条边界均可转为测试（含第 6 条须先核实再断言）；②spec 只描述需求，实施细节留给后续 task；③任务链接无失效占位；④范围已划死（明确不做 7 条）；⑤执行配置五行齐全且与 agents 文件一致；⑥产品使用步骤待 PM 在确认后补寫并可映射验收点。
