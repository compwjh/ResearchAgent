# Spec044 技术评审（独立）

> 本文件为 Gate 2 技术评审结论，由架构师评审子代理独立产出；不修改 spec 状态、不修改任何业务代码、不跑测试、不部署、不 git 提交。结论基于 Grep/Read 真实代码文件，无「应该没问题」式断言。

## 评审元数据

- **评审对象**：`docs/sdd/specs/044-conversation-answer-display-and-provenance.md`（当前状态：`待确认`，标题「会话答案展示与溯源增强」）
- **评审角色**：`architect`（独立技术评审）
- **评审者模型与分派方式**：`Task(subagent_name="architect")` 由主会话独立分派；模型按 `.codebuddy/agents/architect.md` 的 `model` 字段如实填写为 `hy3`；**本轮因默认档账号级 429 临时换档，任务结束后由主会话还原，不作为长期配置**。
- **评审时间**：2026-11-07（Asia/Shanghai）
- **评审范围**：后端 `repository.py` / `routes_conversations.py` / `prompts.py` / `session_search.py` / `models.py`；前端 `app.js` / `conversation-research.js` / `kb-inspection.js` / `processing-tree.js` / `index.html` / `vendor/`；`decision-baseline.md` 的 C1~C13、D1/D8/D10；安全约束清单 S1-1~S4-4；测试命名规则（S4-1~S4-4）；task-07 结构与依赖；版本号同步。

## 结论

**打回**

发现 **1 项 P1 数据契约缺陷**（脱敏函数深度上限与 `step-evidence-v1` 的 `source_ref` 嵌套不兼容，会导致 `source_ref` 字段在落库前被整键丢弃，破坏 A 域来源动作路由）与 **1 项 P1 计划依赖边缺失**（task-05 未声明依赖 task-07，C 域契约/E2E 可能先于实现被执行）。两项均须在 spec/plan 修订并重新评审后方可进入 Gate 3。

评审打回 **不改变 spec 的 `待确认` 状态**，也 **不等于** 已完成真实 API/浏览器验收。

> **复审结论见文末「## 复审（第二轮，2026-11-07）」章：通过（附意见）；原「打回」记录保留，未篡改。**

## 一、代码事实抽样核对（逐条，均附 file:line）

### 1. step-evidence-v1 数据契约与既有脱敏函数兼容性  ❌ P1 缺陷
- 既有脱敏函数 `backend/app/memory/repository.py:62-93`：
  - `:58` `_PROCESSING_DETAIL_MAX_CHARS = 4000`；`:59` `_PROCESSING_DETAIL_BLOCKED` 含 `"url"`；`:77` 黑名单按**键名子串**匹配（`any(blocked in str(key).casefold())`）。
  - `:71-87` `clean(item, depth=0)`：`depth > 3` 返回 `None`（`:72-73`）；列表 `item[:32]`（`:84`）；字符串 `item[:500]`（`:86`）；总长 >4000 整体降级 `'{"truncated":true}'`（`:93`）。
- `step-evidence-v1` 嵌套层级（spec「数据模型」）：顶层 `detail_json`(depth0) → `records[]`(depth1) → 单条 `record`(depth2) → `source_ref`(depth3) → 其字段 `document_id/chunk_id/conversation_id/ref_id/target/kind`(depth4)。
- **缺陷推导（基于真实代码）**：`clean` 在 depth4 处 `return None`，且 `:79-81` 仅当 `safe is not None` 才写入键。故 `source_ref` 各字段（depth4 的值）全部被丢弃，`source_ref` 脱敏后变为 `{}`。
- **后果**：A 域浮层「来源动作」依赖 `source_ref` 的 `conversation_id`/`ref_id`（跳会话/记忆）、`document_id`/`chunk_id`（跳知识库片段）做路由；这些字段落库前即被清空，A 域来源跳转将无法工作（fail-closed 为只读，失去「可解释→可溯源」核心能力）。B 域不受影响（B 域消费 SSE `sources` 帧既有 `chunk_id`/`document_id`，不读 `source_ref`）。
- **与冻结决策冲突**：decision-baseline D8「嵌套深度沿用既有上限（深度 3）」「复用 `_sanitize_processing_detail_json()`」与 spec「明确不做：不复制第二套脱敏逻辑（D8）」「数据模型：冻结内部结构」的「兼容」表述**不成立**。
- **所需修订（三选一，由 architect 冻结）**：(a) 抬高脱敏 `depth` 上限（如允许至 4）；(b) 重构 schema 使 `source_ref` 字段深度 ≤3（如将 `document_id/chunk_id` 等提升到 record 顶层或扁平化）；(c) 对 `source_ref` 子树豁免深度裁剪。无论哪种，须保证 `source_ref` 全部字段在落库后保留，且**不新增第二套脱敏逻辑**（维持 D8 精神）。

### 2. 唯一接口与 SSE 帧体  ✅ 通过
- 唯一接口 `GET /api/messages/{message_id}/processing-steps`（`routes_conversations.py:2329-2337`）返回 `{"steps":[s.to_dict()...]}`；`ProcessingStep.to_dict()` 含 `detail_json`（`models.py:129`），`_processing_step_from_row` 透传 `detail_json`（`repository.py:1694`）；消息不存在返回 404（`:2332-2333`）。✅ D1 成立。
- SSE `progress` / `processing_step` 帧（`routes_conversations.py:1251/1288/1881-1903`）字段仅 `step_id/kind/label/status/summary`，**不含 `detail_json`**，保持轻量。✅ D10 成立，与「明细只经历史水合接口读取」一致。

### 3. `create_processing_step` 生效签名  ✅ 通过
- `repository.py` 仅 2 处同名定义：`:1623`（旧，无 `detail_json`，9 列 INSERT）被 `:1729`（生效，含 `detail_json`，17 参数）覆盖；Python 类内后者胜出。`detail_json` 经 `:1738` `_sanitize_processing_detail_json(detail_json)` 脱敏、`:1757` INSERT 落库。✅ C3 成立，task-02 须命中 `:1729` 并以 `detail_json=` 传参。

### 4. B 域共用链路（jumpToKnowledgeBase + focusChunk）  ✅ 通过（设计一致，待实现）
- `jumpToKnowledgeBase(paperId)`（`app.js:5161`）当前单参数；须扩展为可携带 `document_id + chunk_id` 且兼容既有 4 处单参数调用（C11）。`createConversationSources`（`app.js:2522-2526`）`factory({document, container})` 无回调，须注入可选 `onLocateChunk`（C11）。✅ 设计一致。
- `conversation-research.js`：`SOURCE_ROUTE` 正则（`:8`）；`appendSourceLink`（`:46-64`）仅一个 `<a>`（文案「打开知识库原文」，`link.href/target=_blank/rel=noopener noreferrer nofollow`），B-4 原 PDF 链接行为有基线可依；`:81` 已把 `chunk_id` 展示为「切片」；`createSourceRenderer({document, container})`（`:89`）无回调，须新增可选 `onLocateChunk` 且仅当 `chunk_id` 与回调都存在时渲染第二入口（C10）。✅
- `kb-inspection.js` 公开 API（`:1269-1276`）确为 6 项 `{activateTab, activatePane, cancel, loadDocuments, loadInspection, state}`；`focusChunk` **不存在**（须 task-04 新增）；`selectFromChunk`（`:645`）/`scrollAndFocus`（`:593`）/`clearHighlights`（`:588`）为内部函数，可复用，不复制第二套高亮（C6/C12）。`data-chunk-id` 在 `:574`/`:1051`。✅ 与裁决④一致。

### 5. C 域两段式安全渲染  ✅ 通过（设计一致，待实现）
- `renderMarkdown`（`app.js:6093-6103`）：`marked.parse(text,{gfm:true,breaks:true})` → `DOMPurify.sanitize(html,{FORBID_TAGS:[...],FORBID_ATTR:['style','onerror','onload','onclick','onmouseover']})`；`style` 在 `FORBID_ATTR`，**不得全局放开**（C-5/S3-2 成立）。`:6096` `escapeHtml` 降级（库未加载 → 纯文本，C-4）。
- `createMarkdownWriter`（`app.js:6117-6152`）：`requestAnimationFrame` 节流 + `element.innerHTML = renderMarkdown(raw)` 逐帧重绘；两段式占位符替换须在 `renderMarkdown` 内部完成（marked 前提取、净化后注入），不破坏逐帧契约（C9）。✅
- 顺序与收敛（C-1/C-5/C-6/S3-1~S3-4）：源码存 JS 侧 Map 不进 DOM 属性（S3-1）；`marked.parse → DOMPurify.sanitize → 注入 KaTeX`（S3-2）；KaTeX 参数冻结 `throwOnError:false / trust:false / output:'htmlAndMathml' / maxExpand:1000 / maxSize:10`（C-6/S3-3，拒绝 `\href`/`\includegraphics`、防展开型 DoS）；未闭合/非法公式、KaTeX 故障降级为已转义纯文本且不中断 SSE（S3-4）；源码一律 `textContent`（S2-1/C-8）。✅ 设计冻结正确，与既有 `renderMarkdown`/`createMarkdownWriter` 契约吻合。

### 6. 依赖授权边界  ✅ 通过
- 唯一新增第三方依赖为本地 `frontend/vendor/katex/`（JS+CSS+字体）；`frontend/vendor/` 当前仅 `marked.min.js`/`purify.min.js`/`pdfjs/`，**无 katex**（C13）；`index.html` 未引入 katex（`:796-807`）。无 CDN/npm/运行时网络请求/新框架/组件库。✅ 与裁决②一致。

### 7. 版本号同步  ✅ 通过（设计一致，待实现）
- `index.html`：`styles.css?v=69`（`:8`）、`purify.min.js?v=13`（`:796`）、`marked.min.js?v=13`（`:797`）、`conversation-research.js?v=1`（`:801`）、`processing-tree.js?v=1`（`:802`）、`app.js?v=71`（`:807`）。与 spec/task-05 要求的版本号一致；task-05 须同步 `?v=` 与 `tests/frontend/` 硬编码断言并保留历史兼容注释（D12）。✅

### 8. 安全约束清单 S1-1~S4-4 可测性  ✅ 通过（除 S1-1 受 P1 牵连需随修订）
- S1-1（脱敏复用/总长 4000/`{"truncated":true}` 识别）：函数与降级形态已核对（repository.py:62-93, :93），但 `source_ref` 字段受 P1 缺陷牵连会被丢弃，须随第 1 项修订一并确认 `source_ref` 字段保留。
- S1-2（不得落库 url/source_url）：黑名单含 `"url"` 且子串匹配键名（repository.py:59,77），`source_ref` 字段集（kind/ref_id/document_id/chunk_id/conversation_id/target）均不含 `url` 子串，安全；原文入口由前端按 `paper_id` 拼白名单（prompts.py:70 `source_url` 仅用于 SSE `sources` 帧、不落库）。✅
- S1-3（≤120 字摘要、不展示完整原文）、S1-4（缺失省略/null、不造 ID/分数/来源、记忆无 score）：与 D7/C4/历史不回填一致（session_search.py:84 仅 6 字段无 score）。✅
- S2-1~S2-5（textContent/白名单 kind/深链 fail-closed/第二入口 fail-closed/原 PDF 链接不变）：边界与 task-04 验收 B-1~B-5 可逐条映射。✅
- S3-1~S3-6（两段式顺序、KaTeX 参数冻结、降级不中断 SSE、依赖收敛仅本地 katex）：与 C-1~C-12 可逐条映射。✅
- S4-1~S4-4（测试按能力命名禁编号、`test_conversation_source_chunk_link.py`/`test_answer_math_rendering_contract.py`、布局校验、`check_test_layout.py`、断言不恒真/不静默失效）：task-05 已落地命名规则与校验命令要求。✅

### 9. 测试命名规则落地到 task-05  ✅ 通过
- task-05 §4 明确 B/C 测试文件名（`test_conversation_source_chunk_link.py` / `test_answer_math_rendering_contract.py`），禁止含 `044/spec/task` 编号，须跑 `.venv/bin/python scripts/check_test_layout.py` 与 `pytest --collect-only -q`（S4-1~S4-3）。✅

### 10. task-07 依赖与结构  ❌ P1（依赖边，见下）
- task-07 头部声明「依赖：任务 01」，README 依赖链把 `07` 画成从 `04` 分出、与 `05` 平行、不回灌 `05`；但 task-05 验收覆盖 C 域（C-1~C-12）。严格按声明依赖边会先于 `07` 执行 `05`，使 C 域 E2E 无实现可验。结构（8 节齐全：状态/背景/数据/步骤/分派/边界/验收/产出）与 README/spec 任务计划双向链接一致。⚠️ 见缺陷 2。

## 二、P1 缺陷清单（阻塞项）

- **P1-1（数据契约）**：`step-evidence-v1` 的 `source_ref` 嵌套深度（字段处于脱敏 depth4）超过 `_sanitize_processing_detail_json` 的 `depth>3` 丢弃阈值，落库后 `source_ref` 变为 `{}`，A 域来源动作路由数据丢失。须修订 spec/decision-baseline（D8）与 task-02 的脱敏策略（见第一节第 1 项三选一方案），并同步 S1-1 表述。
- **P1-2（计划依赖边）**：`task-05` 须显式声明依赖 `task-07`（或补 `07→05` 边 / 写「07 须在 05 之前完成」），否则 C 域契约/E2E 可能先于实现执行。

## 三、所需修订（修订后须重新评审）

1. 修订 spec「数据模型 / 明确不做」与 `decision-baseline.md` D8：明确 `source_ref` 字段在脱敏后必须保留，给出脱敏深度/豁免策略（P1-1），并相应修正 S1-1 与 task-02 §3/§6 的脱敏描述（维持「不复制第二套脱敏逻辑」精神）。
2. 修订 `task-05` 头部依赖为「依赖：任务 04、任务 07」，并在 `README` 依赖链图中补 `07 → 05`（或显式顺序约束）（P1-2）。
3. 上述修订完成后，重新执行 Gate 2 技术评审，全部 P1 关闭方可进入 Gate 3。

## 四、其余一致性确认

- A/B/C 三域边界、共用链路、净化白名单、依赖授权与版本号同步均已在第一节逐条核对，设计侧自洽；B/C 零后端改动、不改 SSE 帧体、不新增端点/表/迁移与代码事实一致。
- 本结论不声称任何 API 端到端成功、浏览器验证、CI 全绿或部署完成；上述待实施阶段真实产出后由验收评审（Gate 5）判定。

## 复审（第二轮，2026-11-07）

> 复审由架构师独立执行；基于修订后真实文件 Read 与 `repository.py:62-93` 复核，不修改任何业务代码、不跑测试、不部署、不 git 提交。原「打回」结论（上文）保留作历史记录，未篡改。

### 复审结论

**通过（附意见）** —— P1-1 与 P1-2 两项阻塞均已按冻结的「扁平化 schema」方案与依赖补边闭合；原「打回」理由不再成立。复审通过不改变 spec 的 `待确认` 状态，也不等于已完成真实 API/浏览器验收。

### 逐条核对

#### P1-1（数据契约）— 已闭合
- **扁平化后字段深度与 `clean()` 行为（代码复算）**：修订后 schema 为 `detail_json(d0)→records(d1 list)→record(d2 dict)→字段(d3 标量)`。`clean()` 入口 `clean(parsed)` 以 `depth=0` 调用（`repository.py:89`）；`records` 列表在 `depth=1`（`:84`）；`record` dict 在 `depth=2`；各字段标量在 `depth=3`。标量经 `clean(标量, 3)`：`depth>3`（`:72-73`）为 `3>3=False`，不返回 None；落入 `:85-86` 直接返回（字符串 `:500` 截断），**全部保留**。对比原嵌套 `source_ref` 方案：字段处于 `depth=4`，`4>3=True` 被整键丢弃（`source_ref` 脱敏后变 `{}`）——该根因已通过扁平化消除。
- **字段名无 `url`**：扁平后字段名 `source_kind`/`ref_id`/`document_id`/`chunk_id`/`conversation_id`/`target` 均不含 `url` 子串；黑名单（`repository.py:59,77`）不会误杀，C1 继续成立；`target` 仅存白名单目标标识，不存任意 URL。
- **C3 生效签名**：task-02 仍以 `detail_json=` 命中 `repository.py:1729` 生效签名，未引用旧 `:1623`（C3 不变）。
- **D8 未破坏**：服务端仍复用 `_sanitize_processing_detail_json()`，未抬高全局 `depth` 上限（仍为 3）、未新增第二套脱敏、未改 `repository.py` 任何代码；仅调整本 spec schema 书写（移除非嵌套 `source_ref`）。D8 精神（单一脱敏、最小暴露）保持。
- **S1-1 修订**：已补「扁平化后 record 全部字段 depth ≤3、脱敏后 `source_kind`/`document_id`/`chunk_id`/`conversation_id`/`ref_id`/`target` 必须保留」；task-02 §3 已加「投影后服务端须自检这些字段未被裁掉」。

#### P1-2（计划依赖边）— 已闭合
- **task-05 依赖**：spec 任务计划表 `05` 依赖列已为 `04、07`（spec 行 456）；`task-05` 头部 `依赖` 行已为「任务 04、任务 07」；`task-05` §2 补「依赖 task-07」前置、§4 补 C 域断言须在 task-07 完成后执行、§7 补依赖顺序校验与风险。
- **task-07 顺序约束**：spec 任务计划表 `07` 行已注「须在 05 之前完成」（spec 行 458）；`task-07` §2 已补「本任务须在 task-05 之前完成」；`README` 依赖链图已补 `07 → 05` 汇聚边、备注「07 可在 02–04 期间并行实施，但须在 05 前完成」。
- **三处一致**：spec 任务计划 / `task-05` / `task-07` / `README` 四处对 `07→05` 顺序与 `05 依赖 04、07` 的表述一致，无环、无缺口。

#### F1 / F2 / F3（需求评审附意见沉淀）— 已闭合为强制约束
- **F1（依赖边）**：已沉淀为 spec「Gate 2 附意见」`Gate2-F1` 可测约束，并与 P1-2 同步落地。
- **F2（脱敏/schema 表述）**：已沉淀为 `Gate2-F2`，spec「数据模型」硬约束段、`明确不做`、decision-baseline D8/C14 已统一为「扁平化 schema、depth ≤3」表述；`repository.py` 不被改动。
- **F3（不冒充已验证）**：spec 全文（含八节产物路径、十一节 B/C 验收场景、评审记录、变更日志）维持 `待确认` 设计稿口径，未新增任何「已通过测试 / API 成功 / 浏览器验证 / 部署完成」等已验证表述。

### 剩余非阻塞约束（不阻断 Gate 3，供实施阶段关注）
- 实施阶段 task-04 前端须按新扁平字段读取（`record.source_kind` / `record.conversation_id` / `record.document_id` / `record.chunk_id`），不得再访问 `record.source_ref.*`；task-02 投影须落扁平字段并自检未被脱敏裁掉。
- 实施阶段须按 `task-05` §4 新增的静态契约断言验证扁平化字段在脱敏 depth ≤3 内保留（防 P1-1 回归）。
- 本复审不声称任何 API 端到端成功、浏览器验证、CI 全绿或部署完成；上述待实施阶段真实产出后由验收评审（Gate 5）判定。
