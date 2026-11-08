# Spec044 设计树冻结基线（grilling 复核，2026-11-07）

> 状态：**已冻结，frontier 为空**。用户已回复「全部按照推荐」，本轮不再重问已确认问题。
> 关联：`docs/sdd/specs/044-conversation-answer-display-and-provenance.md`（待建档）、`docs/sdd/plans/044/README.md`（待建档）。
> 本文件只记录决策与事实，不含任何业务代码改动。

## 0. 口径与事实披露（先说清哪些东西没有）

- 用户在此前会话中对 grilling 的 Q1–Q7 回复「**全部按照推荐**」，主会话随后补充收敛 R8–R13，并确认了执行计划 `spec044-processing-step-evidence-and-pr`。
- **Q1–Q7 / R8–R13 的逐条问题与推荐答案原文没有落盘**。已对工作区（含 `.codebuddy/`、`.agents/`、`docs/sdd/{specs,plans,reviews,retro}`、根级文档）与 IDE 计划/待办目录做彻底检索：只在 `plans/03893d411d44436c8740f3e0c234f38a/plan.json`、`plan.md`、`.plan-original.md` 及同名 `todos/*.json` 中找到「按已确认的 Q1-Q7 与 R8-R13 继续设计」「全部按照推荐」这类**引用**，没有任何文件保存逐条问答正文；会话数据库为二进制，文本工具无法证实或排除。
- 因此本基线按三类**可核验输入**重建决策点：① 用户「全部按照推荐」的冻结结论；② 已确认计划稿中明确写出的设计决定；③ 本次复核读到的代码事实。
- **D1–D13 是重建后的决策点编号，不是原始问答逐字稿**；本文件不虚构原始题目、选项与推荐理由的措辞。所有「冻结结论」均可回溯到计划稿段落或代码行号。
- C1–C13 是复核中发现的**新增代码事实约束**（其中 C1–C7 为后端、C8–C13 为前端只读核实），不是新的产品决策，不需要用户再裁决，但必须在 spec 中冻结为实现约束。
- 已冻结项边界：本轮只产出待确认 spec、任务计划、产品步骤、双评审与台账；不实现业务代码、不跑实现测试、不部署。

## 1. 已冻结决策（D1–D7，对应 Q1–Q7）

| 编号 | 决策点 | 冻结结论 | 依据 |
|---|---|---|---|
| D1 | 证据数据载体 | 复用已有 `processing_steps.detail_json`，经现有 `GET /api/messages/{message_id}/processing-steps` 返回；**不新增表、不新增迁移、不新增独立明细端点、不引入新依赖** | 计划稿 Implementation Approach；`backend/app/memory/repository.py:1729-1769` 生效签名已含 `detail_json`；`backend/app/memory/models.py:114-133` `to_dict()` 已含 `detail_json` |
| D2 | 内部结构版本化 | 冻结 `schema_version: "step-evidence-v1"`，顶层 `records[]`，单条含 `kind / title / snippet / score / occurred_at / source_kind / ref_id / document_id / chunk_id / conversation_id / target`（**扁平化，不再嵌套 `source_ref`**）；`source_kind` 取值限定 `conversation / memory_view / kb_chunk / system_rule / external_trace` | 计划稿 Key Code Structures |
| D3 | 记录分级展示 | 有真实记录 → 记录列表 + 来源动作；只有规则来源或生成元信息 → 对应说明 + 可用入口；无明细 → 明确空态。**缺失字段省略或置 null，不造 ID、不造分数、不造来源** | 计划稿 Product Overview / Core Features / Key Code Structures |
| D4 | 历史消息 | **不回填历史明细**；历史步骤 `detail_json` 为空或非本 schema 时步骤不可点，并显示「该消息生成时未记录召回明细」 | 计划稿 Implementation Notes；`docs/sdd/specs/022-project-conversation-memory.md:268,275`「只展示真实阶段、不得把编造的阶段冒充真实事件」 |
| D5 | 触发与浮层交互 | 点击触发（不做 hover）；Esc / 点击外部 / 关闭按钮 / 切换步骤均关闭；一次只开一个浮层；键盘可聚焦、关闭后焦点回到触发按钮 | 计划稿 Core Features / Interaction；`frontend/app.js:2762-2779` `openFloatingMenu` / `closeFloatingMenu` 已提供复用基础 |
| D6 | 来源跳转映射 | 记忆召回 → 会话摘要与 L2 命中记录，跳会话 `/c/{conversationId}`、消息或记忆治理；知识库检索 → 证据记录，跳知识库对应片段并保留原文入口；系统规则 → 规则来源，跳记忆治理规则卡；回答生成 → 状态/耗时/模型元信息与可选外部观测入口 | 计划稿 Core Features / Architecture Design；`frontend/app.js:2753-2759`、`5410-5418`、`5161-5189` |
| D7 | 展示粒度与隐私 | 卡片只展示截断摘要（前端 ≤120 字）、来源类型、得分、时间、文档名，**不展示完整原文**；完整原文只在跳转后的既有页面查看 | 计划稿 Core Features / Key Code Structures |

## 2. 补充收敛决策（D8–D13，对应 R8–R13）

| 编号 | 决策点 | 冻结结论 | 依据 |
|---|---|---|---|
| D8 | 脱敏与裁剪 | 服务端复用 `_sanitize_processing_detail_json()`；不新增第二套脱敏逻辑；records 数量、字符串长度、嵌套深度沿用既有上限；**依靠扁平化 schema 保证来源字段处于脱敏 depth ≤3（不抬高全局 depth 上限、不新增第二套脱敏）**；召回投影为 O(n) 且 n 很小 | 计划稿 Implementation Approach；`backend/app/memory/repository.py:58-93` |
| D9 | 安全边界 | 动态文本一律 `textContent` / 安全属性写入；`source_kind` 与深链参数白名单化、fail-closed；无法解析来源时只展示只读来源信息，不假跳转；片段定位不可用时给中文提示，不静默失败 | 计划稿 Implementation Approach（可靠性）；regression-guard 检查项 |
| D10 | 性能与帧负载 | SSE `progress` / `processing_step` 帧保持轻量，不把大明细塞进每帧；明细只经历史水合接口读取；页面同时只渲染一个浮层卡片，避免重复 DOM 与重复定位 | 计划稿 Implementation Approach；`backend/app/api/routes_conversations.py:1250-1251` 帧字段仅 `step_id/kind/label/status/summary` |
| D11 | 视觉与响应式 | 沿用浅紫对话风格 + 紧凑玻璃浮层；120–180ms 淡入与轻微位移，`prefers-reduced-motion` 下关闭；760px 窄屏浮层 `position: fixed`、宽度 ≤ `100vw - 32px`、最大高度受限并内部滚动；触摸目标 ≥ 44px | 计划稿 Design Style / Page Planning / Interaction |
| D12 | 版本与测试命名 | 后续实现须同步 `app.js?v=71`、`styles.css?v=69`、`processing-tree.js?v=1` 及全部硬编码断言，保留 `frontend/index.html` 历史兼容注释；测试文件与用例按被测能力命名，禁止嵌入 spec/task 编号，并执行 `.venv/bin/python scripts/check_test_layout.py` | 计划稿 Implementation Notes / Skill(test-naming)；`frontend/index.html:8,802,807` |
| D13 | 本轮交付边界 | 只产出 PR、初始状态 `待确认` 的 spec、任务计划、产品步骤、双评审与状态台账；生成 spec 后**停等用户明确确认**，不实现业务代码、不跑实现测试、不部署 | 计划稿 User Requirements / Implementation Notes；`AGENTS.md` 强制流程 1–6 |

## 补充澄清裁决（2026-11-07，用户冻结）

> 下列 5 条裁决来自用户对 Spec044 的两轮澄清，已由用户明确冻结；均为只读设计输入的事实记录，不虚构原始问答措辞，且**不新增待裁决项**（frontier 仍为空，见 §5）。

- **裁决①（B 域并入，不另建 spec）**：参考来源卡片「定位到召回片段」并入 044（不另建独立 spec）；目标为「打开知识库视图 → 定位文档 → 检查器滚动并高亮 `data-chunk-id` 对应切片」；保留原「打开知识库原文」（PDF）入口不变（对应 spec 边界 B-4）。
- **裁决②（C 域 LaTeX 渲染）**：LaTeX 用本地 `frontend/vendor/katex/`（用户明确授权放宽「不引入第三方依赖」，**仅限此项**，不含 CDN/npm/新框架/新组件库）；悬停/聚焦浮层显示原始 LaTeX 源码 + 复制按钮；公式本身渲染不变。
- **裁决③（三域合并命名与重命名）**：三条能力合并命名为「会话答案展示与溯源增强」，并同步重命名 spec 文件为 `044-conversation-answer-display-and-provenance.md`（原 `044-processing-step-evidence-and-source-links.md`）。
- **裁决④（片段定位唯一实现）**：片段定位的**唯一实现**是 `jumpToKnowledgeBase` 扩展 + `kb-inspection.js` 公开 `focusChunk(chunkId)`，处理过程浮层（A 域）与参考来源卡片（B 域）共用；**禁止第二套高亮**（与既有 C6 及 spec「明确不做」一致）。
- **裁决⑤（公式两段式渲染）**：公式采用两段式安全渲染——`marked.parse` **之前**提取占位符与源码（源码存 JS 侧 Map，不进 DOM 属性）→ `DOMPurify.sanitize` 净化后注入 KaTeX 输出；不全局放开 DOMPurify `style`，不放宽 MathML 白名单（对应 spec 边界 C-1/C-5）。

## 3. 复核发现的代码事实约束（C1–C13，实现前必须遵守）

- **C1 来源字段不得含 `url` / `source_url` 键。** `_PROCESSING_DETAIL_BLOCKED` 含 `"url"`，黑名单按**子串**匹配键名（`repository.py:59,77`），任何含 `url` 的键会被整键丢弃。计划草案中的 `"url": "string | null"` 因此不可实现。冻结处置：**不落库 URL**；知识库原文入口由前端按既有规则由 `paper_id` 拼 `/api/kb/documents/{paper_id}/source`（依据 `backend/app/knowledge_base/infrastructure/prompts.py:70`），`external_trace` 只存白名单目标标识，不存任意 URL；扁平化后字段名（`source_kind`/`ref_id`/`document_id`/`chunk_id`/`conversation_id`/`target`）均不含 `url` 子串，C1 继续成立。
- **C2 总长超限会整体降级。** `_PROCESSING_DETAIL_MAX_CHARS = 4000`，序列化后超长返回 `'{"truncated":true}'`（`repository.py:58,92-93`）。前端必须识别该形态并提示「明细过长已截断」，不得当作空 records 或渲染异常；服务端须控制 records 条数与 snippet 长度，避免整段证据丢失。
- **C3 `create_processing_step` 有两个同名定义。** `repository.py:1623` 旧签名（9 列 INSERT、无 `detail_json`）被 `:1729` 生效定义覆盖。后续写入必须命中 `:1729` 生效签名并以 `detail_json=` 关键字传参；spec 与 task 不得引用旧签名。
- **C4 记忆召回记录没有真实分数。** `SessionSearchHit.to_dict()` 仅 `source_kind / ref_id / content / conversation_id / role / created_at` 六字段（`backend/app/memory/session_search.py:69-85`），无 `score`。记忆类记录 `score` 省略或置 null，**不得编造**；`source_kind` 为 `message` / `memory`，`ref_id` 为 `message_id` 或 MD 相对路径。
- **C5 RAG 证据字段以 `citation_payloads()` 为准。** 输出 `file_name / page / page_end / start_line / end_line / chunk_index / paper_id / document_id / chunk_id / source_url / score / text`（`prompts.py:54-74`），其中 `document_id = hit.paper_id`、`chunk_id = point_id(...)`。当前 `sources` / `citations` 帧只在 SSE 发出、**未落库**（`routes_conversations.py:1597-1598,1735-1736`；`frontend/app.js:3775` 仅内存 `pendingSources`），刷新即丢 → 这正是本需求要补的缺口。
- **C6 前端两处跳转能力需要扩展，均不涉及新增 HTTP 端点。** ① `jumpToKnowledgeBase(paperId)` 为单参数，`selectKbJumpTarget` 只按 `data-document-id` / `data-paper-id` 匹配（`app.js:5113-5123,5161-5189`），无 chunk 定位；须扩展为可携带 `document_id` + `chunk_id` 并保持既有 4 处单参数调用兼容。② `kb-inspection.js` 的 `data-chunk-id` 与 `selectFromChunk` / `clearHighlights` / `scrollAndFocus` 均为控制器内部函数，公开 API 只有 `{activateTab, activatePane, cancel, loadDocuments, loadInspection, state}`（`kb-inspection.js:1269-1276,1279-1294`）；须新增一个公开的 `focusChunk(chunkId)` 入口，而非复制第二套高亮逻辑。
- **C7 处理过程步骤现状。** 4 类步骤（含 running/completed/failed/interrupted 共 17 处 `create_processing_step` 调用）目前**全部未传** `detail_json`（`routes_conversations.py:1250,1287,1290,1401,1414,1418,1483,1564,1594,1615,1729,1779,1793,1823` 等）；`frontend/processing-tree.js:166-169` 叶子节点点击直接 `return`，`:157-159` 已有 `aria-expanded` / `aria-disabled`；`normalizeStep()`（`:18-45`）用 `...input` 保留任意字段，故 `detail_json` 可透传但当前无读取点。

> 以下 **C8–C13 为前端只读核实的设计输入**（按主会话只读核实结果录入，非本次新增代码）：记录 A 域浮层复用与 C 域两段式渲染所依赖的既有前端实现现状，供 task-04 / task-07 接线时对齐，不虚构未核实行号或结论。

- **C8 `renderMarkdown()` 现状（`frontend/app.js:6093-6103`）。** 当前实现为 `marked.parse(text,{gfm:true,breaks:true})` → `DOMPurify.sanitize(html,{FORBID_TAGS:[...],FORBID_ATTR:['style','onerror','onload','onclick','onmouseover']})`；C 域两段式渲染必须在 `DOMPurify.sanitize` **之后**才注入 KaTeX 输出，且**不全局放开 `FORBID_ATTR` 的 `style`**（对应 spec 边界 C-5）。
- **C9 `createMarkdownWriter()` 现状（`frontend/app.js:6117-6152`）。** 用 `requestAnimationFrame` 节流并 `element.innerHTML = renderMarkdown(raw)` 逐帧重绘；C 域占位符替换须在 `renderMarkdown` 内部完成（marked 解析前提取、净化后注入），不破坏逐帧重绘契约。
- **C10 来源卡片现状（`frontend/conversation-research.js:46-64,81,89`）。** `appendSourceLink()` 当前只有一个 `<a>`（文案「打开知识库原文」）；`:81` 已把 `chunk_id` 展示为「切片」；`:89` `createSourceRenderer({document,container})` 无跳转回调——task-04 须新增**可选** `onLocateChunk` 回调，并在既有「原文」行之后追加第二入口「定位到召回片段」（仅当 `chunk_id` 与回调都存在时渲染）。
- **C11 来源装配与跳转现状（`frontend/app.js:2522-2526,5161`）。** `createConversationSources()`（`:2522-2526`）未注入回调；`jumpToKnowledgeBase(paperId)`（`:5161`）为单参数——task-04 须扩展为可携带 `document_id` + `chunk_id`，兼容既有 4 处单参数调用。
- **C12 知识库检查器公开 API 现状（`frontend/kb-inspection.js:1269-1294`）。** 公开 API 仅 6 项（`{activateTab, activatePane, cancel, loadDocuments, loadInspection, state}`），无 chunk 定位入口——task-04 须新增公开 `focusChunk(chunkId)`，复用内部 `selectFromChunk` / `scrollAndFocus`，不复制第二套高亮（与 C6、裁决④一致）。
- **C13 静态资源与 vendor 现状（`frontend/index.html:796-807`、`frontend/vendor/`）。** `index.html:796-807` 引入 `purify.min.js?v=13`、`marked.min.js?v=13`、`app.js?v=71`、`styles.css?v=69`（另有 `conversation-research.js?v=1`、`processing-tree.js?v=1`）；`frontend/vendor/` 当前仅有 `marked.min.js`、`purify.min.js`、`pdfjs/`，**无 katex**——task-07 须新增本地 `frontend/vendor/katex/`（JS+CSS+字体），并在 `index.html` 中以各自带 `?v=` 引入，同步硬编码版本断言（对应 D12、裁决②）。
- **C14（P1-1 深度裁剪导致嵌套 `source_ref` 失效，2026-11-07 冻结为扁平化）**。`_sanitize_processing_detail_json()` 的 `clean()` 在 `depth > 3`（`repository.py:72-73`）即 `return None`，且 `:79-81` 仅当子值非 `None` 才写键；黑名单按键名子串匹配（`:59` 含 `"url"`）。原 schema 的 `detail_json(d0)→records(d1)→record(d2)→source_ref(d3)→字段(d4 标量)` 使来源字段处于脱敏 depth4 被整键丢弃、`source_ref` 脱敏后变 `{}`（而非 `None`）。冻结处置：**扁平化**——移除嵌套 `source_ref`，来源字段（`source_kind`/`ref_id`/`document_id`/`chunk_id`/`conversation_id`/`target`）提升到 `record` 顶层，全部处于 depth ≤3 被保留；不改 `repository.py`、不抬全局 `depth` 上限、不新增第二套脱敏。前端读取由 `record.source_ref.kind` 改为 `record.source_kind`、由 `record.source_ref.conversation_id` 改为 `record.conversation_id`，依此类推。

## 4. 编号冲突说明（如实披露，不擅自改号）

- 已确认计划稿指定 `044-processing-step-evidence-and-source-links.md` 与 `docs/sdd/plans/044/`、`docs/sdd/reviews/044-*`，本轮**按计划使用 044**。该文件名 `044-processing-step-evidence-and-source-links.md` 后按用户 2026-11-07 裁决重命名为 `044-conversation-answer-display-and-provenance.md`，此处保留旧名仅作历史叙述。
- 但项目内已有明确记录：`docs/sdd/specs/043-literature-map-topic-exploration.md:637` 写明「`044` 已被 `architecture-boundary-guards` 在途分支占用（存在 `chore(spec-044)` 提交），不可复用」；`docs/sdd/reviews/worktree-triage-2026-11-05.md:64-93` 记录该分支状态为「实施中、未合入 main、需用户裁决继续或放弃」；另一 worktree 中实际存在 `044-architecture-optimization-program.md` 与 `docs/sdd/plans/044/`。
- 当前工作区 `docs/sdd/specs/` 最大编号仍为 `043`，故按 `AGENTS.md`「序号按现有最大编号递增、不复用已归档编号」使用 044 **不违反编号规则**（在途分支未归档），但**存在未来两个 044 并存的语义冲突**。
- 处置：本轮不阻塞、不改号；在 spec 与最终交付说明中披露该风险。若 `architecture-boundary-guards` 分支先合入 `main`，须由用户明确指示后把本 spec、计划目录、评审文件与台账引用整体顺延为 `045`，该改号属于范围外变更，不在本轮自动执行。

## 5. Frontier 状态

- 已确认决策：D1–D13 全部冻结，无「/」、无待裁决项、无隐含假设未显式化。
- 新增事实约束：C1–C13 为实现前必须写入 spec 的技术约束（其中 C1–C7 为后端、C8–C13 为前端只读核实），不是待用户裁决的产品选择，故不重开决策轮。
- 已知风险（非未决决策）：044 编号冲突（§4）、原始问答逐条文本不可得（§0）、仓库无真实 CI / 覆盖率门禁（属 Spec043 PR 已披露项）。
- **本基线到此 frontier 为空**；后续 spec 直接以本文件为输入，不再重新询问上述任何问题。

## 6. 可核验依据清单

| 类别 | 路径 |
|---|---|
| 已确认计划稿 | `plans/03893d411d44436c8740f3e0c234f38a/plan.json`（IDE 全局存储，非仓库文件） |
| 步骤创建与 SSE | `backend/app/api/routes_conversations.py:1218-1228,1250-1290,1401-1418,1483-1823,2329-2337` |
| 脱敏与写入 | `backend/app/memory/repository.py:58-93,1729-1802` |
| P1-1 深度裁剪依据（C14） | `backend/app/memory/repository.py:62-93`（`clean()` 的 `depth>3` 丢弃、`:59` `"url"` 子串黑名单、嵌套 `source_ref` 脱敏后变 `{}`） |
| 步骤模型 | `backend/app/memory/models.py:96-133` |
| RAG 证据 | `backend/app/knowledge_base/infrastructure/prompts.py:54-74` |
| 记忆命中 | `backend/app/memory/session_search.py:69-85` |
| 处理树前端 | `frontend/processing-tree.js:18-45,145-177` |
| 浮层 / 跳转 / 水合 | `frontend/app.js:2479-2508,2753-2779,3643-3651,3775-3799,5113-5189,5327-5464` |
| 知识库片段 | `frontend/kb-inspection.js:574-671,1046-1059,1269-1294` |
| 静态资源版本 | `frontend/index.html:8,802,807` |
| 真实阶段约束 | `docs/sdd/specs/022-project-conversation-memory.md:266-275` |
| 编号冲突 | `docs/sdd/specs/043-literature-map-topic-exploration.md:637`、`docs/sdd/reviews/worktree-triage-2026-11-05.md:64-93` |
| Markdown 渲染（前端） | `frontend/app.js:6093-6103,6117-6152,2522-2526,5161`（C8/C9/C11） |
| 来源卡片（前端） | `frontend/conversation-research.js:46-64,81,89`（C10） |
| 知识库检查器（前端） | `frontend/kb-inspection.js:1269-1294`（C12） |
| 静态资源与 vendor（前端） | `frontend/index.html:796-807`、`frontend/vendor/`（C13，无 katex） |
