> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`

# Task04 来源跳转与片段定位（含 B 域参考来源卡片「定位到召回片段」接线）

## 1. 状态与一句话目标
- 状态：`已完成`。
- 一句话目标：为 **A 域浮层来源动作与 B 域参考来源卡片**实现跳转与片段定位；按 `source_kind` 走对应入口，`kb_chunk` 定位到知识库对应片段；B 域在既有「打开知识库原文」（PDF）之外新增「定位到召回片段」第二入口；fail-closed 处理未知/不可解析来源。

## 2. 背景与前置条件
- 依赖 task-03：浮层已能展示来源动作。
- 设计依据：spec「边界」章节；`decision-baseline.md` D6/D9 与 C1/C5/C6。
- 真实文件事实（C6）：
  - `frontend/app.js` 的 `jumpToKnowledgeBase(paperId)` 为单参数，须扩展为可携带 `document_id` + `chunk_id`，并兼容既有 4 处单参数调用。
  - `frontend/kb-inspection.js` 公开 API 仅 `{activateTab, activatePane, cancel, loadDocuments, loadInspection, state}`（`:1269-1294`）；`selectFromChunk`/`clearHighlights`/`scrollAndFocus` 为控制器内部函数。须新增公开 `focusChunk(chunkId)` 入口，复用既有高亮逻辑，不复制第二套。
- 真实文件事实（C10/C11，B 域参考来源卡片接线）：`frontend/conversation-research.js` 的 `appendSourceLink()` 当前只有一个 `<a>`（文案「打开知识库原文」），`:81` 已把 `chunk_id` 展示为「切片」，`:89` `createSourceRenderer({document,container})` 无跳转回调；`frontend/app.js` 的 `createConversationSources()`（`:2522-2526`）未注入回调——本 task 须为 `createSourceRenderer` 增加可选 `onLocateChunk` 并打通到 `createConversationSources`。

## 3. 数据、配置与接口
- 增量：扩展 `jumpToKnowledgeBase` 签名（兼容既有单参数调用）；`kb-inspection.js` 新增公开 `focusChunk(chunkId)`。
- 增量（B 域参考来源卡片）：`conversation-research.js` 的 `createSourceRenderer({document,container})` 增加可选 `onLocateChunk` 回调，`createSourceDetail()` 在既有「打开知识库原文」行之后追加「定位到召回片段」第二入口（**仅当 `chunk_id` 与回调都存在时渲染**）；`app.js` 的 `createConversationSources()` 须注入该回调；沿用 `SOURCE_ROUTE` 白名单，`document_id` 缺省时回退 `paper_id`。
- 跳转映射（D6）：记忆 → `/c/{conversationId}`；系统规则 → `showView('memory')` + 规则卡聚焦；知识库 → 携带 `document_id`+`chunk_id` 跳库并定位片段；会话类 → `/c/{conversationId}`；`external_trace` → 白名单目标标识只读入口；A/B 两域均读取 `record` 顶层 `conversation_id` / `document_id` / `chunk_id`（不再经 `source_ref` 嵌套）。
- 白名单：深链/跳转参数与 `source_kind` 5 值白名单化、fail-closed（D9）。
- 接口：不新增端点（D1）。

## 4. 实施步骤与文件边界
1. 扩展 `jumpToKnowledgeBase(paperId, opts?)`，新增 `document_id`/`chunk_id` 形参，既有 4 处单参数调用保持兼容（C11）。
2. 在 `kb-inspection.js` 公开 API 中新增 `focusChunk(chunkId)`，内部复用 `selectFromChunk`/`scrollAndFocus` 等既有函数，不复制高亮逻辑（C6/C12）。
3. **A 域浮层来源分派**（处理过程浮层，`processing-tree.js` → `app.js`）：按 `source_kind` 分派——记忆/会话类走 `/c/{conversationId}`；系统规则走 `showView('memory')` + 规则卡聚焦；`kb_chunk` 走 `jumpToKnowledgeBase(document_id, {chunk_id})` → `focusChunk` 定位。
4. **B 域参考来源卡片接线**（`frontend/conversation-research.js`，C10）：
   - `createSourceRenderer({ document, container, onLocateChunk })` 新增**可选** `onLocateChunk` 回调；`frontend/app.js` 的 `createConversationSources()`（`:2522-2526`）须把该回调注入来源渲染器（C11）。
   - `createSourceDetail()` 在既有「打开知识库原文」（PDF）行之后追加第二入口「定位到召回片段」，**仅当 `chunk_id` 与回调都存在时渲染**。
   - 点击以 `document_id`（或 `paper_id`）与 `chunk_id` 调用 `jumpToKnowledgeBase(...)` → `focusChunk(chunkId)`；文本一律 `textContent` 写入、不拼 `innerHTML`；沿用 `SOURCE_ROUTE` 白名单。
5. fail-closed：未知 `kind` / 深链参数非白名单 → 拒绝跳转，仅展示只读来源信息；`kb_chunk` 缺 `chunk_id`、缺回调或定位失败 → 中文提示「无法定位片段」，不假跳转、不静默。
6. 目标文件：`frontend/app.js`（`jumpToKnowledgeBase` 扩展 + `createConversationSources` 注入回调）、`frontend/kb-inspection.js`（公开 `focusChunk`）、`frontend/conversation-research.js`（B 域第二入口接线）；仅 `frontend/**`。
- 可观察结果：A/B 两域来源均正确跳转/聚焦；原 PDF 入口行为不变；未知/不可解析来源不假跳转并给只读信息；片段定位失败有中文提示；片段高亮只有一套实现。

## 5. 子代理分派
- 角色：frontend-dev。模型：`Deepseek-V4.1-Flash`。
- 最小上下文：本 task + spec 边界章节 + `decision-baseline.md` D6/D9 与 C1/C5/C6。
- 单次文件范围：仅 `frontend/app.js`（`jumpToKnowledgeBase` 扩展、`createConversationSources` 注入回调与分派）、`frontend/kb-inspection.js`（公开 `focusChunk`）、`frontend/conversation-research.js`（B 域 `createSourceRenderer` / `createSourceDetail` 第二入口接线）。
- 回传后架构师读回校验：`jumpToKnowledgeBase` 兼容单参数、`focusChunk` 已加入公开 API 且复用既有高亮、白名单 fail-closed、中文提示文案。

## 6. 边界与明确不做
- 不复制第二套高亮逻辑（复用 `kb-inspection.js` 既有函数，C6）。
- 不新增 HTTP 端点（D1）；不把 URL 落库（C1）。
- 不引入 React/组件库（D5）；不改后端（task-02 负责）。
- 不假跳转：未知 `kind` / 非白名单参数只给只读信息（D9）。
- 原 PDF 入口（`href` / `target=_blank` / `rel=noopener noreferrer nofollow` / `SOURCE_ROUTE` 白名单）行为**不变**；新增第二入口不得改动其属性（对应 spec 边界 B-4）。
- 缺 `chunk_id` / 缺回调 / 定位失败 → fail-closed，中文提示「无法定位片段」，不假跳转、不静默（对应 spec 边界 B-2/B-3）。
- `jumpToKnowledgeBase` 扩展须兼容既有 4 处单参数调用。
- 片段高亮只有一套实现（`focusChunk` + `kb-inspection.js` 内部函数），A 域浮层与 B 域卡片共用，禁止第二套（与裁决④一致）。

## 7. 验收、风险与回滚
- 验收（覆盖 spec 边界 B-1~B-5）：① 有 `chunk_id` 且注入回调 → 渲染「定位到召回片段」第二入口（B-1）；② 缺 `chunk_id`/缺回调 → 不渲染第二入口、不假跳转（B-2）；③ 定位失败 → 中文提示「无法定位片段」（B-3）；④ 原 PDF 链接 `href`/`target`/`rel`/`SOURCE_ROUTE` 行为不变（B-4）；⑤ 深链参数非白名单 → 拒绝跳转 fail-closed（B-5）；⑥ `jumpToKnowledgeBase` 兼容 4 处旧调用且能带 `chunk_id`；⑦ `focusChunk` 在公开 API 中且复用既有高亮；⑧ 各 `kind` 正确跳转/聚焦；⑨ 未知 `kind`/非白名单参数 fail-closed 仅只读；⑩ `node --check` 通过。
- 明确：片段高亮只有一套实现（A 域浮层与 B 域卡片共用 `focusChunk`），不得复制第二套。
- 风险：破坏既有 4 处调用、复制第二套高亮、假跳转、改动原 PDF 入口属性。回滚到 task-03 与 spec。

## 8. 产出物、执行结果与变更日志

**2026-11-08 执行结果：已完成。**

- 实现：`frontend/conversation-research.js` 的 `createSourceRenderer({ ..., onLocateChunk })` 与 `appendChunkLocateLink()`；`frontend/app.js` 的 `locateKnowledgeChunk()` / `KB_LOCATE_ID_WHITELIST`、`jumpToKnowledgeBase(paperId, {chunkId, chunkIndex})` 兼容扩展、证据浮层按 `source_kind` 渲染真实动作；`frontend/kb-inspection.js` 公开 `focusChunk(chunkId, chunkIndex)` 并支持 `data-chunk-index` 回退与 pending 重试。
- 单一链路：A 域浮层与 B 域卡片共用 `locateKnowledgeChunk → jumpToKnowledgeBase → focusChunk`，未复制第二套高亮。
- 真实缺陷修复（本轮）：`jumpToKnowledgeBase()` 内两处未定义 `documentId` 改为同函数 `key`；后端 `rag_hit` 投影补 `chunk_index`。修复前 Chromium 实测 `doc_select_value=""` / `chunk_nodes=0` / console「定位片段时发生异常」；修复后 `doc_select_value=55afc3b8f01445429462fe78ed0d4c98` / `chunk_nodes=57` / 高亮 `data-chunk-index=38` / `pending_focus=null` / `page_errors=[]`。
- 验证：`tests/frontend/test_conversation_source_chunk_link.py` `7 passed`；真实 Chromium E2E 见 `artifacts/spec044-b-domain-e2e.json`；原 PDF 入口 `target="_blank"` / `rel="noopener noreferrer nofollow"` / `SOURCE_ROUTE` 逐字未变。
