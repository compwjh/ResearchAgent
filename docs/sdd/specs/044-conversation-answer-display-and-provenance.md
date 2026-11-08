# Spec044 会话答案展示与溯源增强

> 关联：`docs/sdd/plans/044/README.md`（已建档）、`docs/sdd/plans/044/decision-baseline.md`（已冻结基线，D1–D13 / C1–C14 为本 spec 的事实输入）。本 spec 合并三个能力域：A 处理过程步骤证据浮层（可解释）、B 参考来源卡片片段定位（可溯源）、C 回答 LaTeX 公式渲染与源码浮层（可读）。
> 本文件仅描述「做什么、为什么、做到什么程度」；具体实施写于 `docs/sdd/plans/044/task-*.md`。Gate 2 需求/技术双评审已通过（技术评审首轮打回 2 项 P1，修订后复审通过），用户已于 2026-11-08 明确确认并授权实施；Gate 4 实现、Gate 5 验收签字与部署验证均已完成，spec 已收口。

## 状态

> 只能是其一：`待确认` / `已确认` / `实施中` / `已完成` / `阻塞`。

**当前状态：已完成**（2026-11-08：Gate 5 验收通过并经架构师签字，部署验证成功）

## 一句话目标

把回答区域从「只读文本」升级为「可读、可解释、可溯源」的轻量交互：A 处理过程四步骤卡可点击打开悬浮证据卡片（可解释），B 参考来源卡片新增「定位到召回片段」并高亮切片（可溯源），C 回答正文 LaTeX 公式渲染并支持悬浮/键盘 focus 查看源码浮层（可读）；无明细时明确空态，**不猜测、不编造**。

## 能力域与范围

> 本 spec 合并三个能力域；B、C 均不经过 `detail_json`，不改 SSE 帧体，不改 `processing_steps` 表结构。

| 能力域 | 目标 | 用户入口 | 数据来源 | 是否改后端 | 对应 task 文件 |
|---|---|---|---|---|---|
| A 处理过程步骤证据浮层（可解释） | 点击处理过程四步骤卡 → 悬浮证据卡片 → 来源动作 | 处理过程四步骤卡（点击） | `processing_steps.detail_json`（`schema_version: "step-evidence-v1"`） | 需后端投影 | task-02 / task-03 / task-04 |
| B 参考来源卡片片段定位（可溯源） | 参考来源卡片在「打开知识库原文」（PDF）之外新增「定位到召回片段」，跳知识库视图 → 定位文档 → 检查器高亮 `data-chunk-id` 切片 | 参考来源卡片「定位到召回片段」入口 | SSE `sources` 帧已有 `chunk_id` / `document_id`（不新增数据契约） | 零后端改动（直接消费既有 SSE 帧） | task-04（复用 A 的 `jumpToKnowledgeBase` 扩展与 `focusChunk`） |
| C 回答 LaTeX 公式渲染与源码浮层（可读） | 回答正文 LaTeX 公式渲染 + hover/focus 源码浮层（含复制按钮） | 回答正文公式（hover / 键盘 focus） | 回答文本中的公式源码（JS 侧临时 Map，不落库） | 零后端改动 | task-07 |

## 数据模型

> **硬约束**：不改 `processing_steps` 表结构，复用已有字符串列 `detail_json`（经既有 `GET /api/messages/{message_id}/processing-steps` 返回）。冻结内部结构为 `schema_version: "step-evidence-v1"` + 顶层 `records[]`。所有字段缺失时省略或置 `null`，**不得造 ID、造分数、造来源**（D3/D4）。
>
> **扁平化强制约束（Gate 2 打回 P1-1 修订，2026-11-07）**：`records[]` 单条记录**不得**再嵌套 `source_ref` 对象；全部来源字段**提升到 `record` 顶层**（见「单条记录」「来源字段（扁平化，深度 ≤3）」两表）。根因：`_sanitize_processing_detail_json()` 的 `clean()` 在 `depth > 3`（`repository.py:72-73`）即 `return None`，且 `:79-81` 仅当子值非 `None` 才写键；若保留 `detail_json(d0)→records(d1)→record(d2)→source_ref(d3)→字段(d4 标量)` 嵌套，则字段处于脱敏 depth4 被整键丢弃、`source_ref` 脱敏后变 `{}`。改为扁平后 `detail_json(d0)→records(d1)→record(d2)→字段(d3 标量)`，`clean(标量,3)` 因 `3 > 3` 为假而**保留**。**强制：扁平化后每条 `record` 的所有来源字段均处于脱敏 depth ≤3（即 record 顶层），且字段名不得含 `url` 子串（C1 继续成立）**；`source_kind` / `document_id` / `chunk_id` / `conversation_id` / `ref_id` / `target` 落库后必须保留，服务端投影后须自检这些字段未被裁掉。

### 顶层结构（detail_json）

| 字段 | 类型 | 约束（必填？范围？默认？） | 真实来源 |
|---|---|---|---|
| `schema_version` | string | 必填；固定值 `"step-evidence-v1"` | 冻结常量（D2） |
| `records` | array | 必填；可为空数组 `[]` | 由各步骤创建处投影生成（D1、C7） |
| `truncated` | boolean | 仅当整体降级时出现，整段替代为 `{"truncated":true}` | `_PROCESSING_DETAIL_MAX_CHARS=4000` 超限（C2） |

### 单条记录（records[] 元素）

> 注意：`record.kind` 为**记录类型**（取值 `summary | fts_hit | rag_hit | rule | generation`，见下「记录类型 `kind`」）；来源类型另由 `source_kind` 字段承载（见「来源字段（扁平化，深度 ≤3）」表，5 值白名单 `conversation / memory_view / kb_chunk / system_rule / external_trace`）。

| 字段 | 类型 | 约束 | 真实来源 |
|---|---|---|---|
| `kind` | string | 必填；记录类型，取值 `summary \| fts_hit \| rag_hit \| rule \| generation` | 步骤能力分级（D2、D6） |
| `title` | string \| null | 可选；默认 null | 记录标题（文档名 / 会话名 / 规则名） |
| `snippet` | string \| null | 可选；前端展示截断 ≤120 字（D7） | 内容摘要（RAG `text` / 记忆 `content` / 规则描述） |
| `score` | number \| null | 可选；默认 null；**记忆类省略或置 null，不得编造**（C4） | RAG `citation_payloads().score`；记忆类无分数（C4） |
| `occurred_at` | string \| null | 可选；默认 null | 记录发生 / 创建时间 |
| `source_kind` | string \| null | 可选（必填语义：来源类型）；5 值白名单 `conversation / memory_view / kb_chunk / system_rule / external_trace` | 来源引用类型（D2、C1、C5） |
| `ref_id` | string \| null | 可选；默认 null | message_id / MD 相对路径 / paper_id / 规则标识（按 source_kind） |
| `document_id` | string \| null | 可选（仅 `kb_chunk`）；默认 null | `hit.paper_id`（C5） |
| `chunk_id` | string \| null | 可选（仅 `kb_chunk`）；默认 null | `point_id(...)`（C5） |
| `conversation_id` | string \| null | 可选（仅 `conversation` / `memory_view`）；默认 null | `SessionSearchHit.conversation_id`（C4） |
| `target` | string \| null | 可选（仅 `external_trace`）；默认 null；**不得含任意 URL**（C1） | 白名单目标标识（D6） |

### 来源字段（扁平化，深度 ≤3）

> 来源字段**全部位于 `record` 顶层**（不嵌套 `source_ref`），使脱敏后处于 depth ≤3 被保留（见「数据模型」硬约束段 P1-1 说明）。下表为来源定位字段清单；`record.kind`（记录类型）不在此表，单独见「单条记录」表。

| 字段 | 类型 | 约束 | 真实来源 |
|---|---|---|---|
| `source_kind` | string \| null | 可选（必填语义：来源类型）；5 值白名单 `conversation / memory_view / kb_chunk / system_rule / external_trace` | 来源引用类型（D2、C1、C5） |
| `ref_id` | string \| null | 可选；默认 null | message_id / MD 相对路径 / paper_id / 规则标识（按 source_kind） |
| `document_id` | string \| null | 可选（仅 `kb_chunk`）；默认 null | `hit.paper_id`（C5） |
| `chunk_id` | string \| null | 可选（仅 `kb_chunk`）；默认 null | `point_id(...)`（C5） |
| `conversation_id` | string \| null | 可选（仅 `conversation` / `memory_view`）；默认 null | `SessionSearchHit.conversation_id`（C4） |
| `target` | string \| null | 可选（仅 `external_trace`）；默认 null | 白名单目标标识；**不得含任意 URL**（C1） |

> **C1（禁止落库 URL）**：`_PROCESSING_DETAIL_BLOCKED` 含 `"url"`，黑名单按**子串**匹配键名（`repository.py:59,77`），任何含 `url` 的键会被整键丢弃。故**来源字段不得含 `url` / `source_url`**；知识库原文入口由前端按既有规则由 `paper_id` 拼 `/api/kb/documents/{paper_id}/source`（依据 `prompts.py:70`），`external_trace` 只存白名单目标标识。扁平化后字段名（`source_kind`/`ref_id`/`document_id`/`chunk_id`/`conversation_id`/`target`）均不含 `url` 子串，C1 继续成立。
>
> **C2（整体降级）**：序列后总长 >4000 整体降级为 `{"truncated":true}`（`repository.py:58,92-93`）。前端须识别该形态并提示「明细过长已截断」，**不得当作空 records 或渲染异常**；服务端须控制 records 条数与 snippet 长度，避免整段证据丢失。
>
> **C4（记忆无分数）**：`SessionSearchHit.to_dict()` 仅 6 字段（无 `score`），记忆类记录 `score` 省略或 null，**不造分数**；`source_kind` 为 `message` / `memory`，`ref_id` 为 `message_id` 或 MD 相对路径。
>
> **C5（RAG 字段以 `citation_payloads()` 为准）**：输出 `file_name / page / page_end / start_line / end_line / chunk_index / paper_id / document_id / chunk_id / source_url / score / text`，其中 `document_id = hit.paper_id`、`chunk_id = point_id(...)`。当前 `sources` / `citations` 帧只在 SSE 发出、**未落库**（刷新即丢），正是本需求要补的缺口。
>
> **D3 / D4（缺失与历史）**：缺失字段省略或置 null、不造 ID/来源；**历史不回填**，历史步骤 `detail_json` 为空或非本 schema 时步骤不可点，显示「该消息生成时未记录召回明细」。
>
> **source_kind 白名单（5 值）**：`conversation` / `memory_view` / `kb_chunk` / `system_rule` / `external_trace`。
>
> **C7（现状）**：4 类步骤（含 running/completed/failed/interrupted 共 17 处 `create_processing_step` 调用）当前**全部未传** `detail_json`；SSE `sources` 帧只在内存 `pendingSources`，刷新即丢；`processing-tree.js` 叶子节点点击当前直接 `return`，`normalizeStep()` 已用 `...input` 透传任意字段，故 `detail_json` 可透传但无读取点。

## 三域数据边界

> A 冻结 `step-evidence-v1`（见上「顶层结构」「单条记录」「来源字段（扁平化，深度 ≤3）」三表，结构不动）。

- **A（可解释）**：数据来自 `processing_steps.detail_json`，冻结内部结构 `schema_version: "step-evidence-v1"` + 顶层 `records[]`；后端经既有 `GET /api/messages/{message_id}/processing-steps` 投影返回（task-02/03/04）。
- **B（可溯源）**：复用 SSE `sources` 帧既有字段（`chunk_id` / `document_id` / `paper_id` / `source_url` / `score` / `text`，由 `citation_payloads()` 提供）；`frontend/conversation-research.js:81` 已把 `chunk_id` 展示为「切片」；**不新增数据契约**；前端直接消费既有 `chunk_id` / `document_id` 跳知识库视图 → 检查器高亮 `data-chunk-id` 切片（task-04 复用 A 的 `jumpToKnowledgeBase` 扩展与 `focusChunk`）。
- **C（可读）**：公式源码只存在于回答文本与 JS 侧临时 Map，**不落库、不进 `detail_json`、不进 DOM 属性、不进 SSE 帧**；**不新增数据契约**；唯一新增第三方依赖为本地 `frontend/vendor/katex/`（用户已明确授权放宽「不引入第三方依赖」，**仅限此项**，不含 CDN/npm/新框架/新组件库）。
- 保留已有 **C1**（禁止落库 `url` / `source_url`）、**C2**（总长 >4000 整体降级 `{"truncated":true}`）、**C4**（记忆无 score 不造）、**C5**（RAG 字段以 `citation_payloads()` 为准）、**C7**（4 类步骤当前全部未传 `detail_json`）说明。

## 端点 / 接口

> **唯一接口是既有 `GET /api/messages/{message_id}/processing-steps`**（D1）。返回 `steps`，元素 `detail_json` 为上述结构或 `null`；消息不存在返回 404。

| 动作 | 输入 | 成功返回 | 失败情况（状态码） |
|---|---|---|---|
| `GET /api/messages/{message_id}/processing-steps` | `message_id`（路径参数） | 200：`{ "steps": [ { ..., "detail_json": <step-evidence-v1 结构> | null } ] }` | 消息不存在：404；服务错误：500 |

> **明确不新增**：HTTP 端点 / 数据库表 / 迁移 / 第三方依赖。**SSE `progress` / `processing_step` 帧保持轻量**（字段仅 `step_id/kind/label/status/summary`，D10），不携带大明细；明细只经历史水合接口读取。
>
> **B、C 不新增任何 HTTP 端点**：唯一接口仍是既有 `GET /api/messages/{message_id}/processing-steps`；B 直接消费既有 SSE `sources` 帧、C 为纯前端公式渲染与源码浮层，均不新增端点、表或迁移。

## 边界

> 每条边界对应一条可测项。

- **空态**：`detail_json` 为 `null` 或 `records` 为空数组 → 步骤不可点，或点击显示明确空态「该消息生成时未记录召回明细」，**不编造**。
- **非法 JSON**：`detail_json` 解析失败 → fail-closed，按无明细处理，页面不崩溃、不抛未捕获异常。
- **非本 schema**：`schema_version` 不等于 `"step-evidence-v1"` → 视为历史/未知，按无明细处理。
- **整体 truncated**：`detail_json == {"truncated":true}` → 前端识别并提示「明细过长已截断」，**不得当空 records 或渲染异常**。
- **records 空**：`records` 存在但为空 → 明确空态，不展示占位假记录。
- **未知 source_kind**：`source_kind` 不在白名单 5 值 → 只展示只读来源信息，不假跳转（fail-closed）。
- **缺 chunk_id 或定位失败**：`kb_chunk` 无 `chunk_id` 或前端片段定位不可用 → 中文提示「无法定位片段」，**不静默失败**。
- **历史消息无明细**：历史消息 `detail_json` 为空或非本 schema → 步骤不可点并显示历史提示。
- **一次只开一个浮层**：打开新步骤浮层须先关闭其他浮层。
- **Esc 与点外关闭**：`Esc` / 点击浮层外部 / 关闭按钮 / 切换步骤均关闭浮层；关闭后焦点回到触发按钮。
- **窄屏不溢出**：≤760px 浮层 `position: fixed`、宽度 ≤ `100vw - 32px`、最大高度受限并内部滚动、触摸目标 ≥ 44px。
- **动态文本不用 innerHTML**：所有记录/来源文本用 `textContent` / 安全属性写入，禁止拼接 `innerHTML`。
- **深链参数非白名单 fail-closed**：深链/跳转参数不在白名单 → 拒绝跳转，不静默放行。
- **不得编造阶段**：严格遵循 spec-022「只展示真实阶段」，未记录的步骤不得冒充真实事件。

### B 能力域（可溯源：参考来源卡片片段定位）边界

- **B-1（渲染第二入口）**：参考来源卡片有 `chunk_id` 且已注入定位回调 → 渲染「定位到召回片段」第二入口。
- **B-2（缺字段不渲染）**：缺 `chunk_id` / `document_id` → 不渲染第二入口、不假跳转。
- **B-3（定位失败提示）**：片段定位失败 → 中文提示「无法定位片段」。
- **B-4（原 PDF 链接行为不变）**：原「打开知识库原文」PDF 链接的 `href` / `target=_blank` / `rel=noopener noreferrer nofollow` / `SOURCE_ROUTE` 白名单行为不变。
- **B-5（深链非白名单 fail-closed）**：深链参数非白名单 → 拒绝跳转（fail-closed）。

### C 能力域（可读：LaTeX 公式渲染与源码浮层）边界

- **C-1（占位符提取）**：`marked` 解析前提取 `$…$` / `$$…$$`（及 `\(…\)` / `\[…\]`）为占位符，源码存 JS 侧 Map 而非 DOM 属性。
- **C-2（未闭合公式降级）**：流式未闭合公式按已转义纯文本降级，不渲染破损 DOM、不抛未捕获异常中断 SSE。
- **C-3（非法公式降级）**：非法公式按原始源码纯文本降级并中文提示。
- **C-4（KaTeX 故障降级）**：KaTeX 未加载 / 渲染异常 → 降级为已转义纯文本。
- **C-5（净化后注入）**：`marked.parse` → `DOMPurify.sanitize` 之后才把 KaTeX 输出写入占位节点；**不全局放开 `FORBID_ATTR` 的 `style`**，不放宽 MathML 白名单。
- **C-6（KaTeX 参数冻结）**：KaTeX 参数冻结 `throwOnError:false`、`trust:false`、`output:'htmlAndMathml'`、`maxExpand:1000`、`maxSize:10`（拒绝 `\href` / `\includegraphics`、防展开型 DoS）。
- **C-7（浮层开关）**：悬浮 / 键盘 focus 打开源码浮层、`Esc` / 点外 / 切换公式关闭、一次只开一个、焦点回公式。
- **C-8（源码 textContent）**：源码一律 `textContent` 写入，用户 / 模型文本全程不参与 `innerHTML` 拼接。
- **C-9（复制失败提示）**：复制失败中文提示。
- **C-10（窄屏可达）**：760px 窄屏点按可触发、触摸目标 ≥44px、块级公式可横向滚动、浮层不溢出。
- **C-11（reduced-motion）**：`prefers-reduced-motion` 下无动效。
- **C-12（非公式不回归）**：非公式 Markdown 渲染结果不回归。

## 明确不做

- **不回填历史明细**（D4）。
- **不展示完整原文**，只展示截断摘要（前端 ≤120 字）（D7）；完整原文仅在跳转后的既有页面查看。
- **不造 ID、不造分数、不造来源**（D3；记忆类 `score` 省略/null，C4）。
- **不新增 HTTP 端点**（仅复用既有 `processing-steps` 接口）。
- **不新增表、迁移、字段**（不改 `processing_steps` 表结构，D1）。
- **不引入新第三方依赖**（D1）。
- **不引入 React 或组件库**（复用既有 `app.js` / `processing-tree.js` 浮层基础，D5）。
- **不改 SSE `progress` / `processing_step` 帧体**（保持轻量，明细只经历史水合接口读取，D10）。
- **本轮不实现业务代码、不跑测试、不部署**（D13）。
- **不违反 spec-022「只展示真实阶段」**（D4）。
- **不复制第二套脱敏逻辑**（复用 `_sanitize_processing_detail_json()`，D8）。
- **不把 URL 落库**（来源字段不得含 `url` / `source_url`，C1）。
- **不引入 CDN / npm / 新框架 / 新组件库**（仅本地 `frontend/vendor/katex/` 例外，用户已明确授权放宽「不引入第三方依赖」，**仅限此项**，不含 CDN/npm/新框架/新组件库）。
- **不改 SSE 帧体**（B 直接消费既有 `sources` 帧，C 不进 SSE）。
- **不改非公式 Markdown 渲染结果**（C 仅介入公式，不动既有 Markdown 渲染）。
- **不改原 PDF 链接行为**（B 在既有「打开知识库原文」之外新增入口，不改其 `href` / `target` / `rel` / `SOURCE_ROUTE` 白名单行为）。
- **不全局放开 DOMPurify `style`**（C 净化后注入，不放宽 MathML 白名单）。
- **不把公式源码拼进 `innerHTML` 或落库**（C 源码只存 JS 侧 Map、以 `textContent` 写入）。
- **不做 PDF 阅读器内定位**（B 跳知识库视图由检查器高亮切片，不进 PDF 阅读器内部）。
- **不复制第二套片段高亮逻辑**（B 复用 A 的 `jumpToKnowledgeBase` 扩展与 `focusChunk`）。
- **B / C 不新增端点、表或迁移**（唯一接口仍是既有 `processing-steps`）。

## 安全约束清单（regression-guard 收口，Gate 2 逐条核对）

> 本清单为**强制约束**，由 `regression-guard` 与 `test-naming` 技能收口产生；每条均映射到「边界」中的可测编号，Gate 2 需求/技术评审须逐条核对。本轮只冻结约束，不实现、不验证。

### S1 证据明细的敏感信息与展示粒度

| 编号 | 强制约束 | 对应边界 |
|---|---|---|
| S1-1 | 服务端复用 `_sanitize_processing_detail_json()`，不新增第二套脱敏；沿用列表截 32、字符串截 500、深度 3、总长 4000 上限；超限时前端识别 `{"truncated":true}` 并提示「明细过长已截断」。**扁平化后 `record` 全部字段处于脱敏 depth ≤3（不得再嵌套 `source_ref`），脱敏后 `source_kind` / `document_id` / `chunk_id` / `conversation_id` / `ref_id` / `target` 必须保留**（P1-1 修订；服务端投影后须自检这些字段未被裁掉） | 整体 truncated / D8 / P1-1 |
| S1-2 | 来源字段**不得含 `url` / `source_url`**（黑名单按键名子串匹配，扁平化后字段名均不含 `url` 子串）；原文入口由前端按 `document_id` 拼白名单路径 | C1 / 不把 URL 落库 |
| S1-3 | 浮层只展示 ≤120 字截断摘要、来源类型、得分、时间、文档名，**不展示完整原文**；完整原文仅在跳转后的既有页面查看 | 不展示完整原文 / D7 |
| S1-4 | 缺失字段省略或置 `null`，**不造 ID、不造分数、不造来源**；记忆类 `score` 省略或 null；历史不回填、不得编造阶段（spec-022） | 空态 / 历史消息无明细 / 不得编造阶段 |

### S2 XSS、注入与深链

| 编号 | 强制约束 | 对应边界 |
|---|---|---|
| S2-1 | 所有记录、来源、公式源码文本一律 `textContent` / 安全属性写入，用户或模型文本**全程不参与 `innerHTML` 拼接** | 动态文本不用 innerHTML / C-8 |
| S2-2 | `source_kind` 5 值白名单（`conversation` / `memory_view` / `kb_chunk` / `system_rule` / `external_trace`）；未知 kind 只给只读来源信息，不假跳转 | 未知 source_kind |
| S2-3 | 深链 / 跳转参数白名单化、fail-closed；非白名单拒绝跳转，不静默放行；沿用 `SOURCE_ROUTE` 正则 | 深链参数非白名单 fail-closed / B-5 |
| S2-4 | 第二入口 fail-closed：缺 `chunk_id`、缺定位回调、定位失败 → 不渲染或中文提示「无法定位片段」，**不假跳转、不静默失败** | B-2 / B-3 / 缺 chunk_id 或定位失败 |
| S2-5 | 原「打开知识库原文」PDF 入口的 `href` / `target=_blank` / `rel=noopener noreferrer nofollow` / `SOURCE_ROUTE` 行为**不变** | B-4 |

### S3 公式渲染链路的净化收敛（C 域）

| 编号 | 强制约束 | 对应边界 |
|---|---|---|
| S3-1 | 公式提取在 `marked.parse` **之前**，原始源码只存 JS 侧按 token id 索引的 Map，**不写进 DOM 属性**（因此无需为 `data-*` 放宽 DOMPurify） | C-1 |
| S3-2 | 顺序固定为「提取占位符 → `marked.parse` → `DOMPurify.sanitize` → 注入 KaTeX 可信输出」；**不全局放开 `FORBID_ATTR` 的 `style`**、不放宽 MathML 白名单 | C-5 |
| S3-3 | KaTeX 参数冻结 `throwOnError:false` / `trust:false`（拒绝 `\href`、`\includegraphics`）/ `output:'htmlAndMathml'` / `maxExpand:1000` / `maxSize:10`，防展开型 DoS | C-6 |
| S3-4 | 未闭合 / 非法公式、KaTeX 未加载、渲染异常 → 降级为已转义纯文本，**不抛未捕获异常、不中断 SSE 流式写入**；非公式 Markdown 渲染结果不回归 | C-2 / C-3 / C-4 / C-12 |
| S3-5 | 复制走 `navigator.clipboard.writeText`，失败给中文提示，不静默；浮层 `Esc` / 点外 / 切换公式关闭、一次只开一个、焦点回公式 | C-7 / C-9 |
| S3-6 | 依赖收敛：唯一新增第三方依赖为本地 `frontend/vendor/katex/`（JS + CSS + 字体），**无 CDN、无 npm、无运行时网络请求、无新框架/组件库**；用户授权放宽仅限此项 | 三域数据边界 / 明确不做 |

### S4 测试命名与布局（test-naming 收口）

- **S4-1**：测试文件与用例**按被测能力命名**，文件名不得含 `spec\d+` / `task\d+` 等编号子串，也不得含 `044` / `spec` / `task` 字样；必须以 `test_` 前缀 + `.py` / `.js` 结尾。
- **S4-2**：B 域测试命名为 `tests/frontend/test_conversation_source_chunk_link.py`，C 域为 `tests/frontend/test_answer_math_rendering_contract.py`；跨领域测试放 `tests/integration/`，全局 fixture 放仓库根 `conftest.py`，根目录只保留目录。
- **S4-3**：新增或整理测试后必须执行 `.venv/bin/python scripts/check_test_layout.py` 校验布局与编号命名约束，并用 `pytest --collect-only -q` 确认无 `ERROR collecting`、收集用例数与预期一致。
- **S4-4**：测试断言不得恒真、不得可静默失效（如 `if not candidates: return` 式守卫）；改名/移动后须复核 `Path(__file__).resolve().parents[N]` 等相对路径。

## 产品使用步骤

> 本段由 doc-updater 基于已冻结 spec 与决策基线（D1–D13、C1–C7）补齐，为 Gate 2 需求评审用的**设计稿**；当前 spec 仍为 `待确认`，本段不冒充已完成、不引用任何尚未产生的验证结果。

### 一、主路径（自然语言入口，真实用户视角）

- **步骤 1：在对话页发起一次真实提问**
  - 控件：对话页底部输入框（自然语言入口，非表单、非内部 API）→ 输入研究问题 → 点「发送」按钮。
  - 提示：问题进入处理队列，输入框清空并出现「正在思考…」态。
  - 等待与状态：`处理过程` 区域开始渲染四个步骤卡（记忆召回 / 知识库检索 / 系统规则 / 回答生成），每张卡依次从 `running` 变为 `completed`；等待期间卡片展示转圈与步骤名，**不展示任何证据**。
  - 下一步：四个步骤卡全部结束（均 `completed`）后进入步骤 2。

- **步骤 2：点击某个叶子步骤卡，打开浮层**
  - 控件：点击四张卡中可点击的某张（如「知识库检索」叶子卡）。
  - 提示：出现悬浮卡片（浮层）；**一次只开一个**——若已有浮层则先关闭旧浮层再开新浮层。
  - 浮层内容：标题（步骤名）/ 步骤状态（`completed`）/ 记录数量（如「3 条记录」）/ 右上角关闭按钮（×）。
  - 下一步：进入步骤 3。

- **步骤 3：在浮层内查看记录卡**
  - 每张记录卡展示：来源类型（如「知识库检索」）、标题（`title`）、≤120 字截断摘要（`snippet`，D7）、得分（`score`，记忆类省略/null，C4）、时间（`occurred_at`）、文档名。
  - 无记录时显示明确空态（见第三节），**不渲染占位假记录**。
  - 下一步：点击记录卡上的来源动作（步骤 4）。

- **步骤 4：点击来源动作，跳转到真实来源**
  - 控件：记录卡底部的来源动作按钮（文案按 `source_kind` 决定，见第二节）。
  - 提示：页面跳转到对应既有页面（会话 / 知识库片段 / 记忆治理），或失败恢复提示（见第六节）。
  - 下一步：在目标页查看完整原文（浮层只展示截断摘要，完整原文仅在跳转后的既有页面查看，D7）。

### 二、四步分类的来源动作（逐类覆盖 4 类步骤）

① **记忆召回**（`source_kind = conversation` / `memory_view`）
- 记录卡：会话摘要 / L2 命中记录；`score` 省略或 null（记忆类无分数，C4）。
- 来源动作：「查看会话」→ 跳 `/c/{conversation_id}`（由 `conversation_id` 拼接）；或「查看记忆」→ 跳记忆治理页（由 `ref_id` 的 MD 相对路径定位）。
- 点击后：进入既有会话 / 记忆治理页查看消息原文。

② **知识库检索**（`source_kind = kb_chunk`）
- 记录卡：证据记录；`document_id` / `chunk_id` 取自 `citation_payloads()`（C5）。
- 来源动作：「定位知识库片段」→ 高亮目标 `chunk_id`（`focusChunk(chunkId)`，C6）；同时保留「打开原文」入口。
- 原文入口：前端按既有规则由 `document_id` 拼 `/api/kb/documents/{document_id}/source`（C1，**不落库 URL**），跳转到既有原文查看页。

③ **系统规则**（`source_kind = system_rule`）
- 记录卡：规则来源（规则名 + 描述片段）。
- 来源动作：「查看规则」→ 调 `showView('memory')` 并聚焦规则卡（按 `ref_id` 规则标识定位，D6）。

④ **回答生成**（`source_kind = external_trace` 或生成元信息）
- 记录卡：展示状态 / 耗时 / 模型元信息（来自步骤 metadata）。
- 来源动作：可选「查看外部观测」入口；**无真实 `external_trace` 来源时不假跳转**（按钮置灰或省略），对应边界「深链参数非白名单 fail-closed / 不编造」。

### 三、分级场景（按 detail_json 形态）

- **有真实记录**：`records` 非空且为合法 `step-evidence-v1` → 渲染记录列表 + 每条来源动作（主线步骤 3–4）。
- **只有规则来源或生成元信息**：如系统规则步骤仅有 `system_rule` 来源、或回答生成仅含元信息 → 渲染「说明 + 可用入口」，不显示证据列表。
- **空态（4 种触发）**：
  - `detail_json` 为 `null`；
  - `records` 存在但为空数组 `[]`；
  - `detail_json` 非法 JSON（解析失败）；
  - `schema_version` 不等于 `"step-evidence-v1"`（非本 schema）。
  - 上述任一 → 步骤卡可点但点击显示明确空态「该消息生成时未记录召回明细」，**不编造记录**。
- **整体降级**：`detail_json == {"truncated":true}`（C2）→ 浮层提示「明细过长已截断」，**不得当作空 records 或渲染异常**（不显示为空记录）。

### 四、历史消息

- 场景：刷新页面后重新打开一条历史消息的步骤卡。
- 控制：若历史消息 `detail_json` 为空 / 非本 schema（历史未回填，D4）→ 步骤卡**不可点**，并显示「该消息生成时未记录召回明细」；不编造任何记录。

### 五、交互与无障碍

- 关闭方式（任一均生效）：`Esc` 键 / 点击浮层外部遮罩 / 点关闭按钮（×）/ 切换另一张步骤卡（先关后开）。
- 焦点：关闭后焦点回到触发该浮层的步骤卡按钮；按钮可键盘聚焦，`normalizeStep()` 透传 `aria-*` 等属性（D5）。
- 窄屏（≤760px）：浮层 `position: fixed` 贴底全宽，宽度 ≤ `100vw - 32px`，最大高度受限并内部滚动；触摸目标 ≥ 44px；不遮挡底部输入区（D11）。
- 动效：`prefers-reduced-motion` 下关闭淡入/位移动效（D11）；所有记录 / 来源文本一律用 `textContent` / 安全属性注入，禁用 `innerHTML` 拼接（C9/D9）。

### 六、失败恢复

- **未知 `source_kind`**：`source_kind` 不在白名单 5 值 → 只展示只读来源信息（source_kind / ref_id 等），**不假跳转**（fail-closed）。
- **缺 `chunk_id` 或片段定位不可用**：`kb_chunk` 无 `chunk_id`，或前端 `focusChunk(chunkId)` 定位失败（C6）→ 给中文提示「无法定位片段」，**不静默失败**。
- **深链参数非白名单**：跳转目标 / 参数不在白名单 → 拒绝跳转，不静默放行（对应边界「深链参数非白名单 fail-closed」）。
- **返回方式**：任意失败提示下，用户点关闭按钮（或 `Esc` / 点外部）关闭浮层 → 重新点其它步骤卡，或返回对话页重新发起提问（步骤 1）；全程无静默失败、无未捕获异常。

### 七、验收场景（每条映射一条 spec「边界」）

- **验收 1（空态）**：`detail_json` 为 null 或 `records` 为空 → 点击显示「该消息生成时未记录召回明细」，无占位假记录。**对应边界：空态 / records 空**。
- **验收 2（非法 JSON）**：`detail_json` 为非法 JSON → 按无明细处理，页面不崩溃、不抛未捕获异常。**对应边界：非法 JSON**。
- **验收 3（非本 schema）**：`schema_version ≠ "step-evidence-v1"` → 视为历史/未知，按无明细处理。**对应边界：非本 schema**。
- **验收 4（整体 truncated）**：`detail_json == {"truncated":true}` → 提示「明细过长已截断」，不当空 records、不渲染异常。**对应边界：整体 truncated**。
- **验收 5（未知 kind）**：`source_kind` 不在白名单 → 只展示只读来源信息，不假跳转。**对应边界：未知 source_kind**。
- **验收 6（缺 chunk_id）**：`kb_chunk` 无 `chunk_id` 或定位失败 → 提示「无法定位片段」，不静默失败。**对应边界：缺 chunk_id 或定位失败**。
- **验收 7（历史消息无明细）**：刷新后打开历史消息，步骤不可点并显示「该消息生成时未记录召回明细」。**对应边界：历史消息无明细**。
- **验收 8（一次只开一个）**：连续点击两张步骤卡 → 仅最后一个浮层可见，旧浮层先关闭。**对应边界：一次只开一个浮层**。
- **验收 9（Esc 与点外关闭）**：浮层开启时按 `Esc` / 点外部 → 关闭且焦点回到触发按钮。**对应边界：Esc 与点外关闭**。
- **验收 10（窄屏不溢出）**：≤760px 下浮层贴底全宽、内部滚动、触摸目标 ≥ 44px、不遮挡输入区。**对应边界：窄屏不溢出**。
- **验收 11（动态文本不用 innerHTML）**：所有记录 / 来源文本经 `textContent` / 安全属性写入，无 `innerHTML` 拼接注入。**对应边界：动态文本不用 innerHTML**。
- **验收 12（深链参数非白名单 fail-closed）**：深链 / 跳转参数非白名单 → 拒绝跳转。**对应边界：深链参数非白名单 fail-closed**。
- **验收 13（不得编造阶段）**：未记录的步骤不冒充真实事件，仅展示真实阶段（spec-022）。**对应边界：不得编造阶段**。

### 八、产物查看路径

> 以下为 **2026-11-08 实施收口后已真实落盘**的产物路径与实体 ID。实施时证据统一落到仓库根 `artifacts/` 目录（而非设计稿中曾设想的 plans 子目录），此处按实际回填，不伪造未产生的路径。

- **真实 API 端到端成功案例**：`artifacts/spec-044-api-sample.md`（含首次 SSE + 补录的真实 RAG 案例）、`artifacts/spec044-sse-raw.txt`、`artifacts/spec044-processing-steps.json`、`artifacts/spec044-sse-rag-success.txt`、`artifacts/spec044-processing-steps-rag.json`。真实实体：`conversation_id=e23710c72163432585155f12218683c9` / `assistant_message_id=05f0b5efb7b6419288a84fa043a8f655`（首次），RAG 案例 `assistant_message_id=e66eeaa343c64a1aaf7bae5bfdba61d4`；`GET /api/messages/{id}/processing-steps` 均 `HTTP=200`，`detail_json` 为合法 `step-evidence-v1`（首次 3 步 / RAG 4 步）。
- **全量回归日志**：`artifacts/spec044-full-regression.log`（`4030 passed, 2 skipped, 67 subtests passed`，`EXIT=0`）。
- **前端静态契约**：`frontend/processing-tree.js`、`frontend/app.js`、`frontend/kb-inspection.js`、`frontend/conversation-research.js` 均已接入；`frontend/vendor/katex/`（本地 KaTeX 0.16.45，无 CDN）。
- **契约测试**：`tests/frontend/test_conversation_source_chunk_link.py`（B-1~B-5，`7 passed`）、`tests/frontend/test_answer_math_rendering_contract.py`（C-1~C-12，`6 passed`）、`tests/frontend/test_processing_tree_frontend_contract.py`（A 域，`7 passed`）。
- **真实浏览器 E2E**：`artifacts/spec044-b-domain-e2e.py`（可复现 Playwright 脚本）与 `artifacts/spec044-b-domain-e2e.json`（真实 Chromium 结果：文档选中 `55afc3b8f01445429462fe78ed0d4c98`、切片 57 个、高亮 `data-chunk-index=38`、`page_errors=[]`）。
- **验收与评审**：`docs/sdd/reviews/044-requirement-review.md`、`docs/sdd/reviews/044-tech-review.md`、`docs/sdd/reviews/044-acceptance-review.md`（30/30 通过、架构师已签字）。

### 九、B 域主路径：参考来源卡片双入口

> 按真实用户视角（自然语言入口）逐步操作。**2026-11-08 实施已完成**，以下为人工验收可复现步骤；B 域第二入口定位已由真实 Chromium E2E 跑通（见「八、产物查看路径」），A/C 域以静态契约测试与真实 API 样本为准。

- **步骤 1：在对话页发起真实提问并等待回答完成**
  - 控件：对话页底部输入框（自然语言入口，非表单、非内部 API）→ 输入需检索知识库的研究问题 → 点「发送」按钮。
  - 提示：问题进入处理队列，输入框清空并出现「正在思考…」态。
  - 等待与状态：回答以流式输出完成，回答下方出现「参考来源」卡片（每张含文档名 / 切片标识 / 得分等，来自 SSE `sources` 帧既有字段），**不编造来源**。
  - 下一步：确认「参考来源」卡片已出现后进入步骤 2。

- **步骤 2：观察卡片上的两个入口**
  - 控件：每张「参考来源」卡片上并排展示两个入口——既有「打开知识库原文」（PDF，`target=_blank`）与新增「定位到召回片段」。
  - 提示：当 SSE `sources` 帧携带 `chunk_id` / `document_id` 且已注入定位回调时，第二入口「定位到召回片段」出现；缺 `chunk_id` / `document_id` 时不渲染该入口（不假跳转）。
  - 等待与状态：卡片稳定显示两个入口（或仅第一入口，依数据而定）。
  - 下一步：分别点击两个入口（步骤 3）。

- **步骤 3：分别点击两个入口**
  - 第一入口「打开知识库原文」：
    - 控件：点「打开知识库原文」。
    - 点击后：新标签页打开 PDF 原文（`target=_blank`、`rel=noopener noreferrer nofollow`），其 `href` / `SOURCE_ROUTE` 白名单行为不变（对应边界 B-4）。
    - 下一步：切回对话页。
  - 第二入口「定位到召回片段」：
    - 控件：点「定位到召回片段」。
    - 点击后：跳转到知识库视图 → 定位目标文档 → 检查器自动滚动并高亮 `data-chunk-id` 对应切片；零后端改动，直接消费既有 SSE 帧 `chunk_id` / `document_id`。
    - 等待与状态：高亮切片可见于检查器视口内，原 PDF 链接行为不受此入口影响。
    - 下一步：切回对话页或继续查看。

- **步骤 4：失败恢复**
  - 缺 `chunk_id`：第二入口不出现，用户仅能使用「打开知识库原文」；无静默失败。
  - 定位失败：点击第二入口后片段定位不可用 → 显示中文提示「无法定位片段」，不静默失败；用户点关闭浮层 / 切回对话页，可重新提问（回到步骤 1）。
  - 深链非白名单：跳转参数不在白名单 → 拒绝跳转（fail-closed）。
  - 下一步：返回对话页继续（步骤 1）或重新发起提问。

- **步骤 5：窄屏适配**
  - 控件：≤760px 下两个入口上下换行排列，触摸目标 ≥ 44px。
  - 等待与状态：入口不遮挡底部输入区，可正常点击。
  - 下一步：完成双入口验证。

### 十、C 域主路径：回答公式与源码浮层

> 按真实用户视角（自然语言入口）逐步操作。**2026-11-08 实施已完成**，以下为人工验收可复现步骤；B 域第二入口定位已由真实 Chromium E2E 跑通（见「八、产物查看路径」），A/C 域以静态契约测试与真实 API 样本为准。

- **步骤 1：提问含数学公式并等待流式输出完成**
  - 控件：对话页底部输入框（自然语言入口）→ 输入含数学公式的研究问题（公式可混于自然语言）→ 点「发送」。
  - 提示：问题进入处理队列，输入框清空并出现「正在思考…」态。
  - 等待与状态：回答流式输出完成，正文中的行内 `$…$` / `$$…$$`（兼容 `\(…\)` / `\[…\]`）公式由本地 KaTeX 渲染。
  - 下一步：观察公式呈现（步骤 2）。

- **步骤 2：观察公式呈现**
  - 控件：阅读回答正文。
  - 等待与状态：行内公式基线对齐正文、块级公式居中且可横向滚动；非公式 Markdown（标题 / 列表 / 代码 / 表格等）渲染与之前一致（对应边界 C-12）。
  - 下一步：聚焦任意公式（步骤 3）。

- **步骤 3：悬浮 / 键盘聚焦查看源码浮层**
  - 控件：鼠标 hover 到公式，或键盘 `Tab` 聚焦到公式。
  - 点击后：公式旁出现紧凑浮层，显示原始 LaTeX 源码（等宽字体）+「复制」按钮；公式本身不变。
  - 等待与状态：浮层出现、焦点在公式上可读取源码。
  - 下一步：复制源码（步骤 4）。

- **步骤 4：复制源码**
  - 控件：点浮层内「复制」按钮。
  - 点击后：提示复制成功（写入剪贴板）；若复制失败 → 中文提示（对应边界 C-9）。
  - 下一步：关闭浮层（步骤 5）。

- **步骤 5：关闭浮层**
  - 控件：`Esc` / 点击浮层外部 / 点关闭按钮 / 切换到另一公式（任一生效）。
  - 点击后：浮层关闭，且关闭后焦点回到该公式；一次只开一个（打开新公式浮层先关旧浮层）（对应边界 C-7）。
  - 等待与状态：浮层消失、公式保持渲染。
  - 下一步：验证窄屏与降级（步骤 6）。

- **步骤 6：窄屏与可达**
  - 控件：≤760px 下以「点按」触发浮层（替代 hover），触摸目标 ≥ 44px；块级公式可横向滚动；浮层不溢出视口。
  - 等待与状态：窄屏下浮层一次只开一个、不遮挡输入区（对应边界 C-10）。
  - 下一步：验证失败恢复（步骤 7）。

- **步骤 7：失败恢复与降级**
  - 非法公式 / 未闭合公式：流式未闭合或非法公式 → 降级为已转义纯文本显示原始源码 + 中文提示，流式渲染不中断（对应边界 C-2 / C-3）。
  - KaTeX 未加载 / 渲染异常：降级为已转义纯文本（对应边界 C-4），不抛未捕获异常中断 SSE。
  - 动效：`prefers-reduced-motion` 下浮层无淡入 / 位移动效（对应边界 C-11）。
  - 下一步：确认非公式 Markdown 与之前一致（对应边界 C-12）。

### 十一、B/C 域验收场景

> 编号采用前缀 `B-验` / `C-验`，区别于现有「七、验收场景」的验收 1–13，不与之冲突；每条映射一条 spec 边界（B-1~B-5 / C-1~C-12）。

**B 域（对应 B-1~B-5，5 条）**

- **B-验 1（第二入口渲染）**：参考来源卡片有 `chunk_id` 且已注入定位回调 → 渲染「定位到召回片段」第二入口；点击后跳知识库视图并高亮 `data-chunk-id` 切片。**对应边界：B-1（渲染第二入口）**。
- **B-验 2（缺字段不渲染）**：参考来源卡片缺 `chunk_id` / `document_id` → 不渲染第二入口、不假跳转。**对应边界：B-2（缺字段不渲染）**。
- **B-验 3（定位失败提示）**：点击第二入口后片段定位失败 → 显示中文提示「无法定位片段」。**对应边界：B-3（定位失败提示）**。
- **B-验 4（原 PDF 链接行为不变）**：点「打开知识库原文」→ 新标签页打开 PDF，其 `href` / `target=_blank` / `rel` / `SOURCE_ROUTE` 白名单行为不变。**对应边界：B-4（原 PDF 链接行为不变）**。
- **B-验 5（深链非白名单 fail-closed）**：深链 / 跳转参数非白名单 → 拒绝跳转（fail-closed）。**对应边界：B-5（深链非白名单 fail-closed）**。

**C 域（对应 C-1~C-12，12 条）**

- **C-验 1（占位符提取）**：`marked` 解析前将 `$…$` / `$$…$$`（`\(…\)` / `\[…\]`）提取为占位符，源码存 JS 侧 Map 而非 DOM 属性。**对应边界：C-1（占位符提取）**。
- **C-验 2（未闭合公式降级）**：流式未闭合公式 → 按已转义纯文本降级，不渲染破损 DOM、不抛未捕获异常中断 SSE。**对应边界：C-2（未闭合公式降级）**。
- **C-验 3（非法公式降级）**：非法公式 → 按原始源码纯文本降级并中文提示。**对应边界：C-3（非法公式降级）**。
- **C-验 4（KaTeX 故障降级）**：KaTeX 未加载 / 渲染异常 → 降级为已转义纯文本。**对应边界：C-4（KaTeX 故障降级）**。
- **C-验 5（净化后注入）**：`marked.parse` → `DOMPurify.sanitize` 之后才将 KaTeX 输出写入占位节点；不全局放开 `FORBID_ATTR` 的 `style`、不放宽 MathML 白名单。**对应边界：C-5（净化后注入）**。
- **C-验 6（KaTeX 参数冻结）**：KaTeX 参数冻结 `throwOnError:false`、`trust:false`、`output:'htmlAndMathml'`、`maxExpand:1000`、`maxSize:10`（拒绝 `\href` / `\includegraphics`、防展开型 DoS）。**对应边界：C-6（KaTeX 参数冻结）**。
- **C-验 7（浮层开关）**：悬浮 / 键盘 focus 打开源码浮层、`Esc` / 点外 / 切换公式关闭、一次只开一个、焦点回公式。**对应边界：C-7（浮层开关）**。
- **C-验 8（源码 textContent）**：源码一律 `textContent` 写入，用户 / 模型文本全程不参与 `innerHTML` 拼接。**对应边界：C-8（源码 textContent）**。
- **C-验 9（复制失败提示）**：复制失败 → 中文提示。**对应边界：C-9（复制失败提示）**。
- **C-验 10（窄屏可达）**：760px 窄屏点按可触发、触摸目标 ≥ 44px、块级公式可横向滚动、浮层不溢出。**对应边界：C-10（窄屏可达）**。
- **C-验 11（reduced-motion）**：`prefers-reduced-motion` 下浮层无动效。**对应边界：C-11（reduced-motion）**。
- **C-验 12（非公式不回归）**：非公式 Markdown（标题 / 列表 / 代码 / 表格等）渲染结果与之前一致。**对应边界：C-12（非公式不回归）**。

> **实施后回填（2026-11-08）**：上述 17 条验收场景（B-验 1–5 / C-验 1–12）连同 A 域验收 1–13，共 30 条，已在 `docs/sdd/reviews/044-acceptance-review.md` 逐项判定为「通过」，并经架构师签字。真实证据见「八、产物查看路径」；已知限制见验收报告第六节。

## 执行配置

> 设计阶段仅 `architect` + `doc-updater` 参与；**实施阶段真实分派了 `backend-dev` / `frontend-dev`（跨端拆两次）、`tester`（验收）、`architect`（签字）**，见 spec「变更日志」与 `044-acceptance-review.md`。模型与上下文按本表，**架构师行填「自身（不写死模型代号）」**，其余填 `Deepseek-V4.1-Flash`；分派方式 `Task(<真实角色名>)`。严禁 `junior-dev` / `pm` / `tech-lead`。实施期间因 6004 限流按编排规则临时换档，任务结束后 10 个角色的 `model` 均已还原，`git diff -- .codebuddy/agents/` 为空。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| architect（架构师） | 自身（不写死模型代号） | 200k | `Task(architect)` | 编写/修订本 spec、技术决策、落地校验（本轮执行） |
| doc-updater | `Deepseek-V4.1-Flash` | 32k | `Task(doc-updater)` | 补齐产品使用步骤与验收场景（本轮执行） |
| planner | `Deepseek-V4.1-Flash` | 32k | `Task(planner)` | 任务拆分与依赖编排（后续实施阶段适用） |
| backend-dev | `Deepseek-V4.1-Flash` | 32k | `Task(backend-dev)` | 后端 `detail_json` 证据投影（后续实施阶段适用） |
| frontend-dev | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 前端步骤浮层与来源跳转（后续实施阶段适用） |
| backend-reviewer | `Deepseek-V4.1-Flash` | 32k | `Task(backend-reviewer)` | 后端代码评审与合并裁决（后续实施阶段适用） |
| frontend-reviewer | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-reviewer)` | 前端代码评审（后续实施阶段适用） |
| backend-tester | `Deepseek-V4.1-Flash` | 32k | `Task(backend-tester)` | 后端契约测试（后续实施阶段适用） |
| frontend-tester | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-tester)` | 前端交互与响应式测试（后续实施阶段适用） |
| tester | `Deepseek-V4.1-Flash` | 32k | `Task(tester)` | 端到端验收与回归（后续实施阶段适用） |

## 任务计划

> 本章为任务索引，只写标题、链接、依赖与状态；详细步骤写入 `docs/sdd/plans/044/task-*.md`。**2026-11-08 收口：全部 7 个任务已完成。**

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-044（本文件） | 本文件 | — | 已完成 |
| 02 | 后端 detail_json 证据投影 | [`task-02-backend-evidence-projection.md`](../plans/044/task-02-backend-evidence-projection.md) | 01 | 已完成 |
| 03 | 前端步骤浮层与记录列表 | [`task-03-frontend-step-popover.md`](../plans/044/task-03-frontend-step-popover.md) | 02 | 已完成 |
| 04 | 来源跳转与片段定位 | [`task-04-source-link-routing.md`](../plans/044/task-04-source-link-routing.md) | 03 | 已完成 |
| 05 | 契约测试与真实 E2E | [`task-05-contract-tests-and-e2e.md`](../plans/044/task-05-contract-tests-and-e2e.md) | 04、07 | 已完成 |
| 06 | 门禁、验收、台账、复盘、提交 | [`task-06-gates-and-acceptance.md`](../plans/044/task-06-gates-and-acceptance.md) | 05 | 已完成 |
| 07 | 回答 LaTeX 公式渲染与源码浮层（须在 05 之前完成） | [`task-07-answer-math-rendering.md`](../plans/044/task-07-answer-math-rendering.md) | 01 | 已完成 |

> **07 为后补任务**：逻辑位置在 04 与 05 之间，不改动已有文件编号以免破坏已落盘双向链接；依赖顺序 `07 → 05` 已在实际执行中遵守（07 先于 05 完成，C 域契约与 E2E 均有实现可验）。

## P1 修订说明（Gate 2 打回，2026-11-07）

> 本小节如实记录 Gate 2 技术评审「打回」暴露的 P1-1 / P1-2 根因与本轮采用的「扁平化 schema」冻结方案；**不改变用户裁决的三能力域目标、公开接口与 `待确认` 状态**。

### P1-1 根因
- `_sanitize_processing_detail_json()` 内部 `clean(item, depth=0)`（`repository.py:71-87`）在 `depth > 3`（`:72-73`）即 `return None`；`:79-81` 仅当子值 `safe is not None` 才写键；`:77` 黑名单按键名**子串**匹配（`:59` 含 `"url"`）。
- 原契约 `detail_json(d0)→records(d1 list)→record(d2 dict)→source_ref(d3 dict)→其子字段(d4 标量)→clean(标量,4)`：`4 > 3` 为真 → 子字段被丢弃 → `source_ref` 脱敏后变 `{}`。A 域浮层「来源动作」依赖 `source_ref` 的 `conversation_id` / `document_id` / `chunk_id` / `ref_id` 做路由，数据丢失即路由失败。
- 注意：脱敏对空 `source_ref` 的处置是「变 `{}` 而非 `None`」，故前端**不能**靠「判 `source_ref` 是否存在」识别失败，必须显式校验所需字段（如 `conversation_id` / `document_id` / `chunk_id`）是否存在。

### 采用的方案：扁平化 schema（被冻结）
- 移除嵌套 `source_ref` 对象，把来源字段**提升到 `record` 顶层**（见「单条记录」「来源字段（扁平化，深度 ≤3）」两表）。
- 深度验证（修订后）：`detail_json(d0)→records(d1 list)→record(d2 dict)→全部字段为 d3 标量→clean(标量,3)` 因 `3 > 3` 为假而**保留**；`source_ref` 嵌套对象不再存在。字段名（`source_kind`/`ref_id`/`document_id`/`chunk_id`/`conversation_id`/`target`）均不含 `url` 子串，C1 继续成立。
- 前端读取由 `record.source_ref.kind` 改为 `record.source_kind`、`record.source_ref.conversation_id` 改为 `record.conversation_id`，依此类推。
- 服务端仍需以 `detail_json=` 命中 `repository.py:1729` 生效签名（C3），复用既有脱敏（D8），**不改 `repository.py` 任何代码**，不抬全局 `depth` 上限、不新增第二套脱敏。

### 被否决的两方案及否决理由（供审计）
- 方案(a) 抬高全局脱敏 `depth` 上限至 4：否决——会放宽所有 `detail_json` 的嵌套保留深度，使其它 `detail_json` 多保留敏感嵌套层，违背最小暴露原则与 D8 精神。
- 方案(c) 对 `source_ref` 子树豁免深度裁剪：否决——等于在该路径上新增一套「局部脱敏例外」，构成事实上的第二套脱敏分支（与 D8「不复制第二套脱敏」冲突），且豁免逻辑需改 `repository.py`，扩大改动面与回归面。
- 方案(b) 扁平化（采用）：不动全局脱敏函数、不新增第二套脱敏、不改表结构/端点、不扩大范围，仅调整本 spec 的 schema 书写，最小风险闭合 P1-1。

### P1-2 修订
- `task-05` 显式依赖 `04、07`；`task-07` 注明「须在 task-05 之前完成」；依赖链补 `07 → 05` 汇聚边（07 仍依赖 01、可在 02–04 期间并行实施，但 05 必须等 07）。详见「任务计划」表与各 task/README。

## Gate 2 附意见（强制约束）

> 本小节把 Gate 2 需求评审的 F1/F2/F3 沉淀为 spec 强制约束，供后续实施与验收逐条核对。
> **阶段说明（2026-11-08 回填）**：F3 的「不得出现已验证口径」约束仅约束 `待确认` 设计阶段，防止设计稿冒充已验证；用户确认并实施完成后，按真实执行结果回填不属于违反，详见「变更日志」末行说明。

- **Gate2-F1（依赖边）**：`task-05` 必须声明依赖 `task-07`（或在其文件与 `README` 依赖链体现 `07 → 05`、写明「07 须在 05 之前完成」）。可测：修订后 `task-05` 头部 `依赖` 行含 `07`，且 `README` 依赖链图存在 `07` 先于 `05` 的边；无此边即视为未满足 Gate 2 收口。
- **Gate2-F2（脱敏 / schema 表述）**：随 P1-1 修订，spec 的「数据模型 / 明确不做 / decision-baseline D8」中关于「复用 `_sanitize_processing_detail_json()` 且深度 3 兼容」的表述已改为「扁平化 schema，来源字段处于脱敏 depth ≤3 被保留」，明确 `source_kind` / `document_id` / `chunk_id` / `conversation_id` / `ref_id` / `target` 落库后必须保留、字段名不得含 `url`。可测：给出扁平化 schema 与 depth ≤3 约束，且 `repository.py` 不被改动；`task-02` 投影后须自检这些字段未被裁掉。
- **Gate2-F3（不冒充已验证）**：spec「产品使用步骤」八节产物路径与十一节 B/C 域验收场景已声明产物「尚不存在、不冒充已存在」；本轮修订后**不新增任何「已验证 / 已成功」口径**，仍保持 `待确认` 设计稿状态，不引用任何尚未产生的验证结果。可测：全文不得出现「已通过测试 / API 成功 / 浏览器验证 / 部署完成」等已验证口径（八/十一节、评审记录、变更日志均维持设计稿表述）。

## 评审记录

> 初始一律写「待评审（未执行）」；文件尚未产出，不得伪造结论。**三份评审均已产出并含真实结论（见下），验收评审经架构师签字。**

- 需求评审：`docs/sdd/reviews/044-requirement-review.md`（通过（附意见））
- 技术评审：`docs/sdd/reviews/044-tech-review.md`（首轮打回 2 项 P1 → 修订后复审「通过（附意见）」，原打回记录保留）
- 验收评审：`docs/sdd/reviews/044-acceptance-review.md`（**通过**，30/30 验收项、准备度 10/10、无 P0/P1；架构师 `architect` 子代理已于 2026-11-08 签字）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-07 | 架构师(自身) | 编写本 spec，状态待确认 |
| 2026-11-07 | 架构师(自身) | 按用户两项澄清修订为三能力域，标题改为「会话答案展示与溯源增强」并重命名文件；状态仍为待确认 |
| 2026-11-07 | 架构师(自身) | 按 Gate 2 技术评审打回修订 P1-1（扁平化 schema，来源字段提升到 record 顶层、深度 ≤3）/ P1-2（task-05 依赖 04+07、README 补 07→05 边）；状态仍为待确认 |
| 2026-11-08 | 架构师(自身) | 用户明确确认，状态 `待确认 → 已确认`；建 `feature/spec-044-conversation-answer-display-and-provenance` 分支，转 `实施中` |
| 2026-11-08 | `backend-dev` | task-02/04：后端 `step-evidence-v1` 扁平投影；`rag_hit` 投影补 `chunk_index`（`routes_conversations.py:1502`），不改 `repository.py` / 表结构 / SSE 帧体 |
| 2026-11-08 | `frontend-dev` | task-03/04/07：步骤证据浮层与 fail-closed 解析、来源第二入口、单一定位链路、本地 vendor KaTeX 两段式渲染与源码浮层；`?v=` 版本同步升级 |
| 2026-11-08 | `frontend-dev` | 修复 `jumpToKnowledgeBase()` 内两处未定义 `documentId` → 改用同函数 `key`；真实 Chromium 验证文档选中、切片渲染、高亮与 pending 消费全部贯通 |
| 2026-11-08 | 架构师(自身) | 全量回归 `4030 passed / 2 skipped / 67 subtests / EXIT=0`；真实 API E2E（含真实 RAG `sources` 帧与 `chunk_index` 落库）、真实 Chromium B 域 E2E 落盘 `artifacts/` |
| 2026-11-08 | `tester` / `architect` | Gate 5 验收报告 `044-acceptance-review.md` 判定「通过」30/30、准备度 10/10；架构师签字同意收口 |
| 2026-11-08 | 架构师(自身) | 部署验证：重启 `com.researchagent.recovery8000`（PID 88588），首页与 `/api/health` 均 200，新版静态资源全 200；状态 `实施中 → 已完成` |

> Gate2-F3「不冒充已验证」约束适用于 `待确认` 设计阶段；本表与「八、产物查看路径」的实施后回填均为**已真实执行**的验证结果，不属于设计稿预填，故不违反该约束。

## 编号说明

> 如实披露编号冲突，不擅自改号。

- `044` 已被在途 `architecture-boundary-guards` worktree 占用：依据 `docs/sdd/specs/043-literature-map-topic-exploration.md:637` 写明「`044` 已被 `architecture-boundary-guards` 在途分支占用（存在 `chore(spec-044)` 提交），不可复用」；`docs/sdd/reviews/worktree-triage-2026-11-05.md:64-93` 记录该分支状态为「实施中、未合入 main、需用户裁决继续或放弃」。
- 当前工作区 `docs/sdd/specs/` 最大编号仍为 `043`，按「序号按现有最大编号递增、不复用已归档编号」使用 `044` 不违反编号规则（在途分支未归档），但**存在未来两个 `044` 并存的语义冲突**。
- 本轮按用户已确认计划仍用 `044`；若该 `architecture-boundary-guards` 分支先合入 `main`，须由**用户明确指示**后把本 spec、计划目录、评审文件与台账引用整体顺延为 `045`，该改号属范围外变更，**不在本轮自动执行**。
- 文件已由 `044-processing-step-evidence-and-source-links.md` 重命名为 `044-conversation-answer-display-and-provenance.md`（用户 2026-11-07 裁决），台账 / README / 各 task 双向链接 / decision-baseline 已同步；`044` 被在途 worktree 占用的风险与顺延 `045` 规则不变。
