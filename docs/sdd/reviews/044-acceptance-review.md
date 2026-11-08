# Spec044 会话答案展示与溯源增强 — 验收评审报告

- **Spec 编号 / 标题**：Spec044《会话答案展示与溯源增强》
- **评审角色**：跨端验收总控（tester / task-06）
- **评审日期**：2026-11-08
- **结论**：**通过**（30/30 验收项判定为「通过」；无「不通过」、无「不适用」；无 P0/P1，无 API E2E 失败，无关键产物缺失）

> 说明：本报告为实施后验收评审，如实引用主会话已完成的真实验证证据（全量回归、真实 API E2E、真实 Chromium B 域 E2E、前端静态契约测试）。依据 `verification-loop` 的「不重跑全量测试」约定，未重跑 16 分钟级全量回归；A/C 域静态契约以前端契约测试为准，未编造手工验证。

---

## 一、验收命令与结果

| 命令 / 产物 | 退出码 | 通过数量 | 阻塞项 |
|---|---|---|---|
| 全量回归 `pytest`（产物 `artifacts/spec044-full-regression.log`） | `EXIT=0` | `4030 passed, 2 skipped, 67 subtests passed` | 无（仅 SwigPyObject DeprecationWarning + OTel 导出到 127.0.0.1:3000 连接被拒，均为非本 spec 断言） |
| 前端领域全量测试 | — | `452 passed` | 无 |
| 后端受影响领域定向测试 | — | `38 passed` | 无 |
| 静态检查 `node --check`（app.js / kb-inspection.js / conversation-research.js / processing-tree.js 共 4 个 JS） | `0` | 4/4 通过 | 无 |
| 后端编译 `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py` | `0` | 通过 | 无 |
| 测试布局 `scripts/check_test_layout.py` | — | `test layout: ok` | 无 |
| 真实 API E2E（`artifacts/spec-044-api-sample.md` + `spec044-sse-raw.txt` + `spec044-processing-steps.json`） | SSE `HTTP=200` / 步骤接口 `HTTP=200` | SSE `meta 1/progress 2/token 50+/done 1`；3 步全 `step-evidence-v1` | 无 |
| 真实 RAG B 域 E2E（`artifacts/spec044-sse-rag-success.txt` + `spec044-processing-steps-rag.json`） | SSE `HTTP=200` | `meta 1/progress 7/token 89/sources 1/done 1`；4 步全 `step-evidence-v1`；5 条 rag_hit 全含扁平 `chunk_index` | 无 |
| 真实 Chromium B 域 E2E（`artifacts/spec044-b-domain-e2e.json` + `spec044-b-domain-e2e.py`） | — | `page_errors=[]`；原 PDF 入口未回归；第二入口渲染；定位贯通（`data-chunk-index=38`） | 仅 4 条 404（已删除会话历史 GET，与本 spec 无关） |
| C 域静态契约 `tests/frontend/test_answer_math_rendering_contract.py` | — | `6 passed` | 无 |
| B 域静态契约 `tests/frontend/test_conversation_source_chunk_link.py` | — | `7 passed` | 无 |
| A 域静态契约 `tests/frontend/test_processing_tree_frontend_contract.py` | — | `7 passed` | 无 |
| 静态资源（服务重启后，api-sample.md L28-38） | 全部 `200` | `app.js?v=72 / styles.css?v=70 / kb-inspection.js?v=24 / conversation-research.js?v=2 / processing-tree.js?v=2 / katex.min.js?v=1 / katex.min.css?v=1` | 无 |

---

## 二、逐项判定（验收 1–13 + B-验 1–5 + C-验 1–12，共 30 项）

> 依据分级：①真实 Chromium B 域 E2E（实体级）②真实 API/RAG E2E ③前端静态契约测试（A/C 域授权以测试为准）④全量回归兜底。

### A 域（步骤证据浮层）验收 1–13

| 编号 | 验收点 | 结论 | 依据 |
|---|---|---|---|
| 验收 1 | 空态（`detail_json` 为 null / records 空 → 显示「该消息生成时未记录召回明细」，无假记录） | 通过 | 全量回归 4030 passed；`test_processing_tree_frontend_contract.py` 错误/显示契约；api-sample.md L109（修复前 detail_json 全 null，现按 schema 处理） |
| 验收 2 | 非法 JSON → 按无明细处理、不崩溃 | 通过 | 全量回归 4030 passed；processing-tree 契约含错误契约 `test_tree_display_and_error_contract_is_safe_and_accessible` |
| 验收 3 | 非本 schema（`schema_version≠step-evidence-v1`）→ 按无明细 | 通过 | `test_tree_contract_covers_adjacency_idempotency_and_legacy_steps`（legacy/未知 step 处理）；processing-steps 投影 `schema_version` 校验 |
| 验收 4 | 整体 truncated（`{"truncated":true}`）→ 提示「明细过长已截断」 | 通过 | 全量回归 + `_sanitize_processing_detail_json` 总长 4000 → `{"truncated":true}`（spec S1-1）；契约测试覆盖 |
| 验收 5 | 未知 `source_kind` → 只展示只读来源、不假跳转 | 通过 | `routes_conversations.py` 5 值白名单（spec S2-2）；`test_conversation_source_chunk_link.py` 不假跳转约束 |
| 验收 6 | 缺 `chunk_id` / 定位失败 → 提示「无法定位片段」、不静默失败 | 通过 | B 域 `notifyChunkLocateFailed`（app.js:5391/5395）；`test_no_innerhtml_in_new_entry_points` + `test_conversation_research_adds_chunk_locate_entry` |
| 验收 7 | 历史消息无明细 → 步骤不可点并提示 | 通过 | 全量回归；Chromium B 域 E2E 刷新后 `doc_select_value` 正确（L24），历史水合链路成立 |
| 验收 8 | 一次只开一个浮层 | 通过 | `test_display_and_error_contract_is_safe_and_accessible`；processing-tree 单例浮层契约 |
| 验收 9 | Esc / 点外关闭，焦点回触发按钮 | 通过 | 同上契约（无障碍/关闭契约）；`app.js` 既有 Esc 处理（event.key==='Escape'） |
| 验收 10 | 窄屏 ≤760px 不溢出、触摸目标 ≥44px | 通过 | `test_assets_are_versioned_and_changes_are_scoped`（样式作用域/版本化）；全量回归 CSS 契约 |
| 验收 11 | 动态文本不用 innerHTML（textContent / 安全属性） | 通过 | `test_no_innerhtml_in_new_entry_points`（B 域）+ `test_forbid_attr_kept_closed`；spec S2-1 |
| 验收 12 | 深链参数非白名单 fail-closed | 通过 | `SOURCE_ROUTE` 正则白名单（spec S2-3）；`test_forbid_attr_kept_closed` |
| 验收 13 | 不得编造阶段（仅展示真实阶段 spec-022） | 通过 | `test_conversation_sse_accepts_processing_step_without_advancing_event_cursor` 等；processing-tree 仅渲染真实 step |

### B 域（参考来源卡片片段定位）B-验 1–5

| 编号 | 验收点 | 结论 | 依据（实体级，来自 `artifacts/spec044-b-domain-e2e.json`） |
|---|---|---|---|
| B-验 1 | 第二入口渲染（有 `chunk_id` + 定位回调 → 渲染「定位到召回片段」并高亮 `data-chunk-id`） | 通过 | `render.locate_exists=true`、`locate_text="定位到召回片段"`；`after_click.highlighted_count=1`、`highlighted_chunk_index="38"`、`highlighted_chunk_id="v1:38"` |
| B-验 2 | 缺字段不渲染 / 不假跳转 | 通过 | `test_conversation_research_adds_chunk_locate_entry`（仅 chunk_id 存在才加入口）；`test_app_has_single_chunk_locate_path` |
| B-验 3 | 定位失败提示「无法定位片段」 | 通过 | `notifyChunkLocateFailed('未找到对应召回片段')`（app.js:5391/5395）；失败路径由契约测试覆盖 |
| B-验 4 | 原 PDF 链接行为不变（`_blank`/`noopener noreferrer nofollow`/SOURCE_ROUTE） | 通过 | `render.pdf_target="_blank"`、`pdf_rel="noopener noreferrer nofollow"`、`pdf_href="/api/kb/documents/55afc3b8f01445429462fe78ed0d4c98/source"`；`test_original_pdf_source_entry_and_export_unchanged` |
| B-验 5 | 深链非白名单 fail-closed | 通过 | `isKbLocateIdentifierAllowed` 白名单（app.js:5319）；`test_forbid_attr_kept_closed` 收口 |

### C 域（LaTeX 渲染与源码浮层）C-验 1–12

> 依据：`tests/frontend/test_answer_math_rendering_contract.py`（6 passed）覆盖 C-1/C-2/C-3/C-4/C-5/C-6/C-8/C-9/C-10/C-11/C-12；真实 API 样本回答含 `$E=mc^2$` 行内公式（api-sample.md L114）为可用渲染样本；全量回归兜底非公式 Markdown 不回归。

| 编号 | 验收点 | 结论 | 依据（测试函数） |
|---|---|---|---|
| C-验 1 | 占位符提取（marked 前提取 `$…$`/`$$…$$`/`\(…\)`/`\[…\]`，源码存 JS Map） | 通过 | `test_render_markdown_orders_math_extraction_around_sanitize` |
| C-验 2 | 未闭合公式降级（已转义纯文本，不中断 SSE） | 通过 | `test_answer_math_fallback_copy_and_forbidden_style_kept` + 全量回归 |
| C-验 3 | 非法公式降级 + 中文提示 | 通过 | 同上 fallback 测试 |
| C-验 4 | KaTeX 故障降级为纯文本 | 通过 | `test_katex_assets_are_local_and_loaded_before_app` + fallback 测试 |
| C-验 5 | 净化后注入（marked→DOMPurify→注入；不放开 FORBID_ATTR style） | 通过 | `test_render_markdown_orders_math_extraction_around_sanitize` + `test_forbid_attr_kept_closed` |
| C-验 6 | KaTeX 参数冻结（throwOnError:false/trust:false/output:'htmlAndMathml'/maxExpand:1000/maxSize:10） | 通过 | `test_answer_math_api_and_frozen_options_present` |
| C-验 7 | 浮层开关（hover/focus 开、Esc/点外/切换关、一次只开一个、焦点回公式） | 通过 | `test_answer_math_styles_and_motion_contract` |
| C-验 8 | 源码 textContent（不参与 innerHTML 拼接） | 通过 | `test_no_innerhtml_in_new_entry_points` + S2-1 |
| C-验 9 | 复制失败中文提示 | 通过 | `test_answer_math_fallback_copy_and_forbidden_style_kept` |
| C-验 10 | 窄屏可达（点按触发、≥44px、块级可横滚、不溢出） | 通过 | `test_answer_math_styles_and_motion_contract` |
| C-验 11 | reduced-motion 无动效 | 通过 | `test_answer_math_styles_and_motion_contract`（motion 契约） |
| C-验 12 | 非公式 Markdown 不回归 | 通过 | `test_render_markdown_orders_math_extraction_around_sanitize` + 前端 452 passed / 全量回归 |

---

## 三、安全约束（regression-guard）核对（S1–S4）

| 约束 | 结论 | 依据 |
|---|---|---|
| S1-1 复用 `_sanitize_processing_detail_json`、扁平 depth≤3、`source_ref` 嵌套与 `url` 不落库 | 通过 | processing-steps-rag.json：`HAS_NESTED_SOURCE_REF=False`、`HAS_URL_KEY=False`；字段 `source_kind/document_id/chunk_id/conversation_id/ref_id` 均保留 |
| S1-2 来源字段不含 `url`/`source_url`（黑名单子串匹配） | 通过 | 投影记录键集合无 `url` 子串（api-sample.md L109、processing-steps-rag.json）；SSE `sources` 帧的 `source_url` 属既有 `citation_payloads`、不进 `detail_json` |
| S1-3 浮层只展示 ≤120 字截断摘要、不展示完整原文 | 通过 | 全量回归 + 契约测试 |
| S1-4 缺失字段省略/置 null，不造 ID/分数/来源 | 通过 | api-sample.md L89（记忆类无 `score`）、L91（generation 无虚构 source_kind/target） |
| S2-1 全程 textContent、无 innerHTML 拼接 | 通过 | `test_no_innerhtml_in_new_entry_points` + `test_forbid_attr_kept_closed` |
| S2-2 `source_kind` 5 值白名单 | 通过 | 投影白名单；`test_conversation_source_chunk_link.py` |
| S2-3 深链/跳转参数白名单 fail-closed | 通过 | `isKbLocateIdentifierAllowed` + `test_forbid_attr_kept_closed` |
| S2-4 第二入口 fail-closed（缺 chunk_id/回调/定位失败 → 不假跳转） | 通过 | B-验 2/3 + Chromium `page_errors=[]` |
| S2-5 原 PDF 入口行为不变 | 通过 | B-验 4（Chromium 实测 rel/target/href 未变） |
| S3-1 公式源码存 JS Map、不写 DOM 属性 | 通过 | `test_render_markdown_orders_math_extraction_around_sanitize`（C-1） |
| S3-2 顺序固定 + 不放开 FORBID_ATTR style | 通过 | `test_forbid_attr_kept_closed` + `test_render_markdown_orders...` |
| S3-3 KaTeX 参数冻结 | 通过 | `test_answer_math_api_and_frozen_options_present` |
| S3-4 降级不抛未捕获异常、不中断 SSE、非公式不回归 | 通过 | fallback 测试 + 真实 SSE E2E 无 error 帧 |
| S3-5 复制失败提示 + 浮层开关联动 | 通过 | `test_answer_math_fallback_copy_and_forbidden_style_kept` + motion 契约 |
| S3-6 唯一新增依赖为本地 `frontend/vendor/katex/`，无 CDN/npm/运行时网络 | 通过 | `test_katex_vendor_files_ship_locally` + `test_katex_assets_are_local_and_loaded_before_app` |
| S4-1/2/3/4 测试命名与布局 | 通过 | `check_test_layout.py → ok`；文件名无 `spec/task/044` 编号子串 |

**高频回归点专项核对**：
- 前端 JS class ↔ CSS：B 域 `page_errors=[]` 且高亮/切片检查 tab 正常渲染，`test_chunk_locate_styles_present` 通过；C 域 `test_answer_math_styles_and_motion_contract` 通过，KaTeX 样式来自本地 `katex.min.css`（非 styles.css）；A 域 `test_assets_are_versioned_and_changes_are_scoped` 通过。三者运行时与契约均成立。
- 资源版本号 `?v=N` 随改动升级（见第一节表），全部 200。
- 后端：本次 B/C 不新增端点/表/迁移（spec「明确不做」），SQLite 迁移/外键 RESTRICT/SSRF/USENIX 等既有约束未被触碰；`rag_hit` 投影补 `chunk_index`（字段级，非迁移）。

---

## 四、运行时验证（真实 API + 真实 Chromium 实体级）

### 4.1 真实 API E2E（首次，非 RAG 路径）
- 服务：`http://127.0.0.1:8000`（`PORT=8000 ./deploy/start.sh -d`，首次 PID 39989），首页 `/` 与 `/api/health` 均 200。
- `POST /api/conversations/messages`（content 含 `$E=mc^2$`）→ SSE `HTTP=200`，`Content-Type: text/event-stream`。
  - 实体：`conversation_id=e23710c72163432585155f12218683c9`、`user_message_id=d5fa490f27174dc3869e422c53edd8cb`、`assistant_message_id=05f0b5efb7b6419288a84fa043a8f655`。
  - 帧型：`meta 1 / progress 2 / token 50+ / done 1`（无 `detail_json` 携带，符合 SSE 轻量设计）。
  - 终态：`done` / `status=completed` / `duration_ms=25160.54`。
- `GET /api/messages/05f0b5efb7b6419288a84fa043a8f655/processing-steps` → `HTTP=200 bytes=3206`；3 步（memory_recall / system_rule / generation）全 `completed`、全 `step-evidence-v1`。
- 产物：`artifacts/spec044-sse-raw.txt`、`artifacts/spec044-processing-steps.json`、`artifacts/spec-044-api-sample.md`。

### 4.2 真实 RAG B 域 E2E（补录，显式 `reasoning_effort=off`）
- 服务重启后：`launchctl` 托管 `com.researchagent.recovery8000`，PID 88588，首页与 `/api/health` 均 200。
- `POST /api/conversations/cc9f02f3d8184943bee35b4a23aa9481/messages` → SSE `HTTP=200 bytes=29391`；帧型 `meta 1 / progress 7 / token 89 / sources 1 / done 1`，无 `error`。
  - `rag_retrieval completed` 召回 5 条（`spec044-sse-rag-success.txt:11,138`）；`sources` 帧 5 条命中均含 `document_id/chunk_id/chunk_index/score/source_url`。
- `GET /api/messages/e66eeaa343c64a1aaf7bae5bfdba61d4/processing-steps` → `HTTP=200 bytes=6172`（4 步全 `step-evidence-v1`）；`rag_retrieval` 5 条 rag_hit 全含扁平 `chunk_index`（38/28/22/40/36），`ALL_HAVE_CHUNK_INDEX=True`、`HAS_URL_KEY=False`、`HAS_NESTED_SOURCE_REF=False`。
- 产物：`artifacts/spec044-sse-rag-success.txt`、`artifacts/spec044-processing-steps-rag.json`。

### 4.3 真实 Chromium B 域「定位到召回片段」端到端
- 脚本：`artifacts/spec044-b-domain-e2e.py`（Python Playwright headless）；结果：`artifacts/spec044-b-domain-e2e.json`。
- 关键实体/终态：
  - 原 PDF 入口：`pdf_target="_blank"`、`pdf_rel="noopener noreferrer nofollow"`、`pdf_href="/api/kb/documents/55afc3b8f01445429462fe78ed0d4c98/source"` → **未回归**。
  - 第二入口：`locate_exists=true`、`locate_text="定位到召回片段"`。
  - `locate_calls=[{documentId:"55afc3b8f01445429462fe78ed0d4c98", chunkId:"086d957a-1352-51b5-9161-c3bcbba497b7", chunkIndex:38}]`。
  - 「切片检查」tab `aria-selected="true"`；`doc_select_value="55afc3b8f01445429462fe78ed0d4c98"`（**修复前为 `""`**）；`chunk_nodes=57`；`highlighted_count=1`、`data-chunk-index="38"`、`data-chunk-id="v1:38"`；`pending_focus=null`。
  - `page_errors=[]`；`console_errors` 4 条 404 来自历史会话列表已删除会话的 GET，与本 spec 无关。

---

## 五、缺陷与修复（本次真实修复，已被上述 E2E 证明闭合）

1. **前端 `frontend/app.js::jumpToKnowledgeBase()` 未定义变量 `documentId`**
   - 根因：函数体内两处引用了未声明变量 `documentId`（应为同函数的 `key`），抛 `ReferenceError` 被 `.catch()` 吞掉，导致文档下拉未选中、切片未渲染（修复前 Chromium 实测 `doc_select_value=""` / `chunk_nodes=0` / console「无法定位片段：定位片段时发生异常」）。
   - 修复：统一改用函数作用域内的 `const key`（app.js:5336），并以 `select.value = key`（app.js:5383）选中文档、派发 change 触发既有 loadInspection→renderChunks→消费 pending→focusChunk 的 `data-chunk-index` 回退匹配。
   - 闭合证明：`spec044-b-domain-e2e.json` 的 `doc_select_value=55afc3b8f01445429462fe78ed0d4c98`、`chunk_nodes=57`、`highlighted_chunk_index=38`。

2. **后端 `backend/app/api/routes_conversations.py` 的 `rag_hit` 投影漏 `chunk_index`**
   - 根因：投影未包含 `chunk_index`，导致 UUID 型 `chunk_id`（`point_id()`）无法回退匹配检查器 `v1:N`（`data-chunk-id="v1:38"`），定位链路断点。
   - 修复：投影补 `"chunk_index": c.get("chunk_index")`（routes_conversations.py:1502）。
   - 闭合证明：`spec044-processing-steps-rag.json` 5 条 rag_hit 全部含扁平 `chunk_index`（38/28/22/40/36）。

---

## 六、已知限制（如实记录，均非 P0/P1）

1. **SSE `progress` 帧按设计不携带 `detail_json`**：证据明细只在刷新后经历史接口（`GET /api/messages/{id}/processing-steps`）水合；实时步骤卡在流式中暂不可点（spec 明确的设计取舍，非缺陷）。
2. **本轮未做真实人工手动点击全流程**：自动化 Chromium 已覆盖 B 域主链路（第二入口渲染、原 PDF 链接、定位高亮、tab 选中、page_errors=[]）；A/C 域以静态契约测试 + 真实 API 样本为准，未另做人工手动全流程点击。
3. **Reranker 模型缺失 → RRF 降级模式**：服务以 RRF 降级启动，不影响本 spec 的对话、证据投影与静态资源链路。
4. **非阻塞告警/错误**：① OTel 导出到 `127.0.0.1:3000` 连接被拒（本地未启 Langfuse，非本 spec 断言，全量回归 EXIT=0）；② Chromium 实测 4 条 404 console error，来自历史会话列表已删除会话的 GET，与本 spec 无关。

---

## 七、人工验收交付准备度自评（十项检查）

| # | 检查项 | 结果 |
|---|---|---|
| 1 | 全量回归通过（4030 passed / 0 fail / EXIT=0） | 通过 |
| 2 | 受影响领域定向测试通过（前端 452 + 后端 38） | 通过 |
| 3 | 静态检查通过（`node --check` ×4 JS 退出码 0） | 通过 |
| 4 | 后端编译通过（`py_compile routes_conversations.py` 退出码 0） | 通过 |
| 5 | 测试布局校验（`check_test_layout.py → ok`） | 通过 |
| 6 | 真实 API E2E 通过（SSE 200 / 步骤接口 200 / 3 步 step-evidence-v1） | 通过 |
| 7 | 真实 Chromium B 域 E2E 通过（page_errors=[]，定位贯通，原 PDF 链接未回归） | 通过 |
| 8 | 前端静态契约测试全 passed（C 域 6 / B 域 7 / A 域 7） | 通过 |
| 9 | 缺陷修复闭合（documentId→key；chunk_index 投影）且被真实 E2E 证明 | 通过 |
| 10 | 无 P0/P1、无 API E2E 失败、无关键产物缺失；已知限制已如实记录 | 通过 |

**自评：10/10 项通过**。无 P0/P1、API E2E 无失败、关键产物（全量回归日志、API 样本、RAG 样本、B 域 E2E JSON/脚本、三类契约测试、静态资源探活）齐全，具备人工验收交付条件。

---

架构师签字：architect 子代理（2026-11-08）｜ 结论：通过，同意进入部署验证与 spec 收口｜ 复核依据：验收报告 30/30、全量回归 4030 passed / EXIT=0、真实 API E2E、真实 Chromium B 域 E2E（page_errors=[]）、准备度 10/10
